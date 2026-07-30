"""
Qwen3-ASR 기반 STT 엔진.

Whisper 계열 대신 도입한 이유 (실측 근거, 2026-07-30):
  - 팀 전문용어: 컨텍스트 바이어싱으로 용어 재현율 80.7% → 92.8%.
    Whisper는 프롬프트로 용어를 주면 오히려 받침이 깨진다(임베딩→임베딘,
    웹소켓→웹소켛). 학습 단계에 컨텍스트를 넣은 모델과 "앞 문장 이어쓰기"로
    프롬프트를 해석하는 모델의 구조적 차이.
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

타임스탬프에 대하여:
  Qwen 본체는 세그먼트 타임스탬프를 주지 않지만, TransformersWhisperEngine도
  모델이 준 타임스탬프를 쓰지 않는다 — 우리가 30초 창으로 직접 자르고 그 창
  경계를 세그먼트 시각으로 쓴다. 여기서도 같은 창 분할을 적용해 동일한
  granularity를 유지한다. 별도 정렬 모델(Qwen3-ForcedAligner)은 필요 없다.
"""
import numpy as np
import torch
from transformers import AutoProcessor, AutoModelForMultimodalLM

from ..core.config import logger, REALTIME_SAMPLE_RATE
from .whisper_engine import (
    Segment, TranscribeInfo,
    load_audio, find_window_cutoff, trim_silence,
    _WINDOW_SAMPLES,
)

# 한 창에서 생성할 최대 토큰 수. 30초 발화가 이보다 길게 전사되는 경우는 없지만,
# 환각 루프에 빠졌을 때 무한정 생성하는 걸 막는 상한 역할도 한다.
_MAX_NEW_TOKENS = 448


class Qwen3ASREngine:
    """
    faster_whisper.WhisperModel / TransformersWhisperEngine와 동일한 호출 규약
    (`.transcribe(...) -> (segments, info)`, 세그먼트는 start/end/text/avg_logprob/
    no_speech_prob 보유)을 제공한다. 호출부(stt_service, realtime_service,
    refine_service)는 수정 없이 그대로 재사용된다.
    """

    def __init__(self, model_id: str, device: str = "cuda", context: str | None = None):
        """
        context: 회의 도메인 용어/배경 텍스트. 모든 전사에 기본으로 적용된다.
                 전사 호출에서 initial_prompt를 따로 주면 그쪽이 우선한다.
        """
        self.device = device
        self.default_context = context

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

    @torch.inference_mode()
    def transcribe(
        self,
        audio_or_path,
        language: str = "ko",
        beam_size: int = 1,
        vad_filter: bool = True,
        initial_prompt: str | None = None,
        condition_on_previous_text: bool = False,  # 호환용. 창 단위 독립 디코딩만 지원.
    ):
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
            raw_window = audio[window_start: window_start + _WINDOW_SAMPLES]
            if len(raw_window) < REALTIME_SAMPLE_RATE // 20:
                break
            cutoff = find_window_cutoff(raw_window)
            window = raw_window[:cutoff]
            text, avg_logprob = self._generate_window(window, language, beam_size, context)
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

    def _generate_window(self, window: np.ndarray, language: str, beam_size: int, context: str | None):
        """30초 이하 오디오 창 하나를 전사해 (텍스트, avg_logprob)를 반환."""
        inputs = self.processor.apply_chat_template(
            [self._build_conversation(window, language, context)],
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
        ).to(self.model.device, self.model.dtype)

        prompt_len = inputs["input_ids"].shape[1]
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=_MAX_NEW_TOKENS,
            num_beams=max(beam_size, 1),
            do_sample=False,
            return_dict_in_generate=True,
            output_scores=True,
        )
        generated_ids = outputs.sequences[:, prompt_len:]
        text = self.processor.decode(generated_ids, return_format="transcription_only")[0]
        return text.strip(), self._avg_logprob(outputs, generated_ids, beam_size)

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
