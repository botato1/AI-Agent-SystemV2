"""
Qwen3-ASR 기반 STT 엔진.

Whisper 계열 대신 도입한 이유 (실측 근거, 2026-07-30):
  - 전문용어: 컨텍스트 바이어싱으로 용어 재현율 80.7% → 92.8%.
    Whisper는 프롬프트로 용어를 주면 오히려 받침이 깨진다(임베딩→임베딘,
    웹소켓→웹소켛). 학습 단계에 컨텍스트를 넣은 모델과 "앞 문장 이어쓰기"로
    프롬프트를 해석하는 모델의 구조적 차이.
    ⚠️ 2026-08-14: 이 수치는 개발 용어 66개 목록으로 잰 것이다. 타깃 철회로 목록이
       회의 어휘 9개로 줄어 **현재 설정의 이득은 재측정 전까지 알 수 없다.**
       엔진 선택 근거에 직접 걸리는 항목이다 — MODELS.md 2절 경고 참고.
  - 발화 누락: 실제 회의 녹음에서 large-v3가 4문장을 통째로 흘린 구간을
    Qwen은 온전히 잡았다.
  - 속도: 같은 트랙에서 2.4초 vs 5.5초 (2~4배 빠름).

알려진 약점:
  - ITN(숫자 역정규화)을 적용하지 않아 "8002번"을 "팔천이번"으로 출력한다.
    후처리로 해결해야 하는 별도 과제. 컨텍스트에 "숫자는 아라비아 숫자로
    표기" 같은 지시문을 넣는 방법은 실측으로 무효 확인됨(컨텍스트는 어휘에만
    작동하고 출력 형식은 제어하지 못한다).
  - no_speech_prob를 주지 않는다(아래 참고).
  - AI-Hub 평가에서 없는 고유명사를 만들어낸 사례가 있음 — 환각 감시 필요.
  - **컨텍스트를 그대로 받아적는 경우가 있다.** Whisper보다 훨씬 견고하지만 면역은
    아니다 — 짧고 불분명한 구간에서 용어 목록을 출력한 사례가 실제 회의에서
    관측됐다(2026-07-31). _is_context_echo가 그런 출력을 걸러낸다.

타임스탬프에 대하여:
  Qwen 본체는 세그먼트 타임스탬프를 주지 않지만, TransformersWhisperEngine도
  모델이 준 타임스탬프를 쓰지 않는다 — 우리가 30초 창으로 직접 자르고 그 창
  경계를 세그먼트 시각으로 쓴다. 여기서도 같은 창 분할을 적용해 동일한
  granularity를 유지한다. 별도 정렬 모델(Qwen3-ForcedAligner)은 필요 없다.
"""
import os
import threading
import time

import numpy as np
import torch
from transformers import AutoProcessor, AutoModelForMultimodalLM, StoppingCriteria, StoppingCriteriaList

from ..core.config import logger, REALTIME_SAMPLE_RATE, QWEN_ITN_ENABLED, build_qwen_context
from ..utils.korean_itn import to_digits
from .whisper_engine import (
    Segment, TranscribeInfo,
    load_audio, find_window_cutoff, trim_silence,
    _WINDOW_SAMPLES,
)

# 한 창에서 생성할 최대 토큰 수. 30초 발화가 이보다 길게 전사되는 경우는 없지만,
# 환각 루프에 빠졌을 때 무한정 생성하는 걸 막는 상한 역할도 한다.
_MAX_NEW_TOKENS = 448

# fast_decode의 torch.compile을 동적 shape로 돌릴지. 켜면 프롬프트·오디오 길이가 바뀔 때
# 재컴파일(수십 초 정지)을 피하지만 약간 느려질 수 있다. 기본은 꺼짐 — 실측 후 결정한다.
_FAST_DECODE_DYNAMIC = os.getenv("STT_FAST_DECODE_DYNAMIC", "0").strip().lower() in ("1", "true", "yes")

# 컨텍스트 받아적기 판정 기준 (_is_context_echo).
# 20자 연속 일치 + 출력의 절반 이상 — 실제 발화가 이 조건을 만족하기는 매우 어렵다.
_ECHO_MIN_RUN = 20
_ECHO_MIN_RATIO = 0.5


class _CancelCriteria(StoppingCriteria):
    """
    cancel_event가 set되면 다음 토큰 경계에서 생성을 멈춘다.

    왜 필요한가: asyncio의 future.cancel()은 run_in_executor로 이미 돌고 있는 스레드를
    멈추지 못한다. 화자 전환이 감지돼 버려진 전체 청크 전사가 GPU에서 끝까지 돌며
    턴별 전사와 자원을 나눠 쓰던 문제(전환 청크 지연이 같은 길이에서 약 2배)를
    협력적 취소로 막는다. 취소 지연은 토큰 하나(약 24ms)다.
    """

    def __init__(self, event: threading.Event):
        self.event = event

    def __call__(self, input_ids, scores, **kwargs):
        return torch.full(
            (input_ids.shape[0],), self.event.is_set(), dtype=torch.bool, device=input_ids.device
        )


class Qwen3ASREngine:
    """
    faster_whisper.WhisperModel / TransformersWhisperEngine와 동일한 호출 규약
    (`.transcribe(...) -> (segments, info)`, 세그먼트는 start/end/text/avg_logprob/
    no_speech_prob 보유)을 제공한다. 호출부(stt_service, realtime_service,
    refine_service)는 수정 없이 그대로 재사용된다.
    """

    # 호출부가 transcribe(cancel_event=...)를 넘겨도 되는 엔진인지 알리는 표식.
    supports_cancel = True

    def __init__(
        self, model_id: str, device: str = "cuda", context: str | None = None,
        fast_decode: bool = False,
    ):
        """
        context: 회의 도메인 용어/배경 텍스트. 모든 전사에 기본으로 적용된다.
                 전사 호출에서 initial_prompt를 따로 주면 그쪽이 우선한다.
        fast_decode: 디코더를 int8 가중치 양자화(torchao) + 정적 KV 캐시/torch.compile로
                 돌린다. 토큰당 시간이 절반 이하가 되지만(실측 25 → 10.5ms) 출력이 아주
                 조금 달라질 수 있어 실시간 확정 전용 인스턴스에만 쓴다. 준비에 실패하면
                 예외를 던진다 — 호출부가 일반 인스턴스로 되돌아가야 한다.
        """
        self.device = device
        self.default_context = context
        self.fast_decode = False
        # 정적 캐시는 모델 하나에 캐시 객체를 공유하므로 호출이 겹치면 서로 덮어쓴다.
        # fast_decode일 때만 생성을 한 번에 하나씩 돌린다(일반 경로는 병렬 그대로).
        self._decode_lock = threading.Lock()

        logger.info(f"🧠 Qwen3-ASR 로딩 중... ({model_id} / {device})")
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModelForMultimodalLM.from_pretrained(
            model_id,
            dtype=torch.bfloat16 if device == "cuda" else torch.float32,
            device_map="auto" if device == "cuda" else device,
        )
        self.model.eval()
        logger.info(f"✅ Qwen3-ASR 로딩 완료 ({model_id})")
        if context:
            logger.info(f"📌 컨텍스트 바이어싱 활성 ({len(context)}자)")
        if fast_decode:
            self._enable_fast_decode()

    def _enable_fast_decode(self) -> None:
        """int8 weight-only 양자화 + 정적 캐시 컴파일 워밍업. 실패하면 예외."""
        if self.device != "cuda":
            raise RuntimeError("fast_decode는 CUDA에서만 지원한다")
        from torchao.quantization import quantize_
        try:
            from torchao.quantization import Int8WeightOnlyConfig as make_config
        except ImportError:  # 구버전 이름
            from torchao.quantization import int8_weight_only as make_config

        started = time.perf_counter()
        # 오디오 인코더는 건드리지 않는다 — 디코더 쪽 Linear만(토큰마다 읽히는 가중치).
        quantize_(
            self.model, make_config(),
            filter_fn=lambda m, fqn: isinstance(m, torch.nn.Linear) and "audio" not in fqn.lower(),
        )
        torch.cuda.empty_cache()
        self.fast_decode = True

        # 컴파일을 서버 시작 시점에 끝낸다 — 첫 실사용 청크가 20초 넘게 멈추지 않게.
        # 실제 호출은 회의마다 길이가 다른 컨텍스트(참석자 이름)와 길이가 다른 오디오를
        # 쓰므로, 워밍업도 컨텍스트 길이 × 오디오 길이를 섞어서 돌린다. (2026-10-14 실측:
        # 컨텍스트 없는 워밍업만 했더니 첫 실제 호출이 22초 걸렸다.)
        sample_names = ["문지수", "김나연", "이승주", "가동현", "이준오", "홍길동", "김철수", "박영희"]
        contexts = [self.default_context]
        for n in (3, 8):
            contexts.append(build_qwen_context(sample_names[:n]) or self.default_context)
        rng = np.random.default_rng(0)
        for ctx in contexts:
            for seconds in (3.0, 8.0, 15.0):
                noise = (0.02 * rng.standard_normal(int(seconds * REALTIME_SAMPLE_RATE))).astype(np.float32)
                t_call = time.perf_counter()
                self._generate_window(noise, "ko", 1, ctx)
                logger.info(
                    f"   워밍업 {seconds:.0f}초 / 컨텍스트 {len(ctx or '')}자: "
                    f"{time.perf_counter() - t_call:.1f}초"
                )
        logger.info(f"⚡ fast_decode 준비 완료 (int8 + 정적 캐시/compile, {time.perf_counter() - started:.0f}초)")

    def _decode_kwargs(self) -> dict:
        """generate에 덧붙일 인자. 정적 캐시는 fast_decode일 때만."""
        if not self.fast_decode:
            return {}
        kwargs = {"cache_implementation": "static"}
        if _FAST_DECODE_DYNAMIC:
            from transformers import CompileConfig
            kwargs["compile_config"] = CompileConfig(dynamic=True)
        return kwargs

    @torch.inference_mode()
    def transcribe(
        self,
        audio_or_path,
        language: str = "ko",
        beam_size: int = 1,
        vad_filter: bool = True,
        initial_prompt: str | None = None,
        condition_on_previous_text: bool = False,  # 호환용. 창 단위 독립 디코딩만 지원.
        cancel_event: threading.Event | None = None,
    ):
        """
        cancel_event: set되면 진행 중인 생성을 토큰 경계에서 멈추고 지금까지의 결과를
                      버린 채 빈 목록을 돌려준다. 결과를 쓰지 않을 때(버려진 전사)만 쓸 것.
        """
        audio = load_audio(audio_or_path)
        info = TranscribeInfo(language=language)
        trim_offset_sec = 0.0

        if vad_filter:
            audio, has_speech, trim_offset_sec = trim_silence(audio)
            if not has_speech:
                return [], info

        if len(audio) < REALTIME_SAMPLE_RATE // 20:  # 0.05초 미만이면 전사 무의미
            return [], info

        context = initial_prompt if initial_prompt is not None else self.default_context

        segments = []
        window_start = 0
        while window_start < len(audio):
            if cancel_event is not None and cancel_event.is_set():
                return [], info
            raw_window = audio[window_start: window_start + _WINDOW_SAMPLES]
            if len(raw_window) < REALTIME_SAMPLE_RATE // 20:
                break
            cutoff = find_window_cutoff(raw_window)
            window = raw_window[:cutoff]
            text, avg_logprob = self._generate_window(
                window, language, beam_size, context, cancel_event
            )
            if cancel_event is not None and cancel_event.is_set():
                return [], info  # 중간에 끊긴 창의 불완전한 텍스트는 쓰지 않는다
            if text:
                segments.append(Segment(
                    start=round(trim_offset_sec + window_start / REALTIME_SAMPLE_RATE, 2),
                    end=round(trim_offset_sec + (window_start + len(window)) / REALTIME_SAMPLE_RATE, 2),
                    text=text,
                    avg_logprob=avg_logprob,
                    # Qwen은 no_speech 확률을 내지 않는다. VAD(trim_silence)가 이미
                    # 순수 침묵을 걸러내므로 0.0(=발화 있음)으로 고정한다.
                    # ⚠️ 그 결과 CONF_NO_SPEECH_THRESHOLD 검사는 무력화되고 신뢰도
                    #    판정이 avg_logprob 하나에만 의존한다. Qwen의 avg_logprob 분포는
                    #    Whisper와 다르므로(실측 평균 -0.03 vs -0.12) 임계값을 그대로
                    #    쓰면 전부 confident로 통과한다 — config에서 반드시 재조정할 것.
                    no_speech_prob=0.0,
                ))
            window_start += cutoff

        return segments, info

    # inference_mode가 필수다: 워밍업은 transcribe() 밖에서 이 함수를 직접 부르는데, 그때
    # grad 모드가 켜져 있으면 torch.compile이 역전파까지 포함한 그래프를 컴파일해서
    # (실측 167초) 실제 호출(inference_mode) 때 가드가 달라 또 다시 컴파일한다(105초 정지).
    @torch.inference_mode()
    def _generate_window(
        self, window: np.ndarray, language: str, beam_size: int, context: str | None,
        cancel_event: threading.Event | None = None,
    ):
        """30초 이하 오디오 창 하나를 전사해 (텍스트, avg_logprob)를 반환."""
        inputs = self.processor.apply_chat_template(
            [self._build_conversation(window, language, context)],
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
        ).to(self.model.device, self.model.dtype)

        prompt_len = inputs["input_ids"].shape[1]
        extra = self._decode_kwargs()
        if cancel_event is not None:
            extra["stopping_criteria"] = StoppingCriteriaList([_CancelCriteria(cancel_event)])

        def _run():
            return self.model.generate(
                **inputs,
                **extra,
                max_new_tokens=_MAX_NEW_TOKENS,
                num_beams=max(beam_size, 1),
                do_sample=False,
                return_dict_in_generate=True,
                output_scores=True,
            )

        if self.fast_decode:
            with self._decode_lock:
                # 락을 기다리는 사이 취소됐다면 GPU를 쓰지 않고 돌아간다
                if cancel_event is not None and cancel_event.is_set():
                    return "", 0.0
                outputs = _run()
        else:
            outputs = _run()
        if cancel_event is not None and cancel_event.is_set():
            return "", 0.0  # 호출부(transcribe)가 취소를 보고 결과를 버린다
        generated_ids = outputs.sequences[:, prompt_len:]
        text = self.processor.decode(generated_ids, return_format="transcription_only")[0].strip()
        if self._is_context_echo(text, context):
            # 오디오 대신 컨텍스트를 받아적은 출력 — 회의록에 넣으면 안 된다.
            # 빈 텍스트를 돌려주면 호출부가 세그먼트를 만들지 않는다.
            logger.warning(
                f"⚠️ 컨텍스트 받아적기 감지 — 세그먼트 폐기: {text[:60]}..."
            )
            return "", self._avg_logprob(outputs, generated_ids, beam_size)

        if QWEN_ITN_ENABLED:
            # 발음형 숫자를 아라비아 숫자로 되돌린다 ("팔천이번" → "8002번").
            # 확신할 수 없는 부분은 원문 그대로 남기는 보수적 변환.
            text = to_digits(text)
        return text, self._avg_logprob(outputs, generated_ids, beam_size)

    @staticmethod
    def _is_context_echo(text: str, context: str | None) -> bool:
        """
        전사 결과가 컨텍스트(용어 목록)를 그대로 받아적은 것인지 판정.

        왜 필요한가: 실제 회의에서 관측된 실패다 — 짧거나 불분명한 구간에서 모델이
        오디오 대신 시스템 메시지의 용어 목록을 출력했다.
            "용어: 재논의, 번복, 결정사항, 안건, 시연, 회의록, ..."
        Whisper의 initial_prompt에서 겪은 것과 같은 실패 방식이다. Qwen은 컨텍스트
        주입을 학습으로 배워 훨씬 견고하지만 **면역은 아니다** — 이 전제로 방어한다.

        판정 기준: 출력과 컨텍스트의 최장 공통 부분문자열이 20자 이상이면서
        그것이 출력의 절반 이상을 차지하면 받아적기로 본다.
        실제 발화가 용어를 20자 넘게 연속으로, 그것도 발언 대부분을 채우며
        나열하는 경우는 사실상 없다. 애매하면 통과시킨다 — 멀쩡한 발언을
        지우는 쪽이 더 나쁘다.
        """
        if not context or not text:
            return False

        def squash(s: str) -> str:
            return "".join(ch for ch in s if ch.isalnum())

        a, b = squash(text), squash(context)
        if len(a) < _ECHO_MIN_RUN:
            return False

        # 최장 공통 부분문자열 길이 (짧은 문자열 기준이라 O(len(a)*len(b))로 충분)
        prev = [0] * (len(b) + 1)
        best = 0
        for i in range(1, len(a) + 1):
            cur = [0] * (len(b) + 1)
            for j in range(1, len(b) + 1):
                if a[i - 1] == b[j - 1]:
                    cur[j] = prev[j - 1] + 1
                    best = max(best, cur[j])
            prev = cur

        return best >= _ECHO_MIN_RUN and best >= len(a) * _ECHO_MIN_RATIO

    @staticmethod
    def _build_conversation(audio: np.ndarray, language: str | None, context: str | None) -> list[dict]:
        """
        시스템 메시지 = 언어 힌트 + 컨텍스트, 유저 메시지 = 오디오.

        processor.apply_transcription_request()에는 컨텍스트를 받을 인자가 없다
        (transformers 5.13 기준 `prompt`를 넘기면 조용히 무시된다). 채팅 템플릿이
        시스템 역할의 text 조각을 전부 이어붙이므로 대화를 직접 구성한다.
        언어는 "ko" 같은 코드로 줘도 resolve_language가 전체 이름으로 바꿔준다
        (모델이 학습 때 본 형태가 "Korean"이라 코드 그대로 넣으면 안 됨).
        """
        from transformers.models.qwen3_asr.processing_qwen3_asr import resolve_language

        parts = []
        if language:
            parts.append(resolve_language(language))
        if context:
            parts.append(context)

        return [
            {"role": "system", "content": [{"type": "text", "text": "\n".join(parts)}] if parts else []},
            {"role": "user", "content": [{"type": "audio", "audio": audio}]},
        ]

    @staticmethod
    def _avg_logprob(outputs, generated_ids, beam_size: int) -> float:
        """
        신뢰도 신호. beam search면 generate가 계산해준 길이 정규화 점수를 쓰고,
        greedy면 매 스텝 선택된 토큰의 로그확률을 평균낸다.
        두 방식은 분포가 달라 임계값을 공유하면 안 된다 — Whisper에서 beam 10 → 1로
        바꿨을 때 신뢰도 게이트가 무력화됐던 사례가 있다.
        """
        scores = getattr(outputs, "sequences_scores", None)
        if beam_size > 1 and scores is not None:
            return float(scores[0])

        step_logprobs = []
        for step, logits in enumerate(outputs.scores):
            if step >= generated_ids.shape[1]:
                break
            logprobs = torch.log_softmax(logits[0].float(), dim=-1)
            step_logprobs.append(logprobs[generated_ids[0, step]].item())
        if not step_logprobs:
            return 0.0
        return sum(step_logprobs) / len(step_logprobs)
