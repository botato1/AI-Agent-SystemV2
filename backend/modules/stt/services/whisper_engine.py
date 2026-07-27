import numpy as np
import soundfile as sf
import torch
from transformers import AutoProcessor, WhisperForConditionalGeneration
from faster_whisper.vad import VadOptions, get_speech_timestamps

from ..core.config import logger, REALTIME_SAMPLE_RATE

# Whisper 인코더의 고정 입력 길이. processor가 이보다 긴 오디오를 조용히 잘라버리므로
# (truncate) 긴 오디오는 반드시 이 크기 이하 창(window)으로 쪼개서 처리해야 함.
_WINDOW_SEC = 30
_WINDOW_SAMPLES = _WINDOW_SEC * REALTIME_SAMPLE_RATE

# 창 경계(30초)가 단어/문장 중간을 자르는 걸 완화하기 위한 설정 — realtime_service.py의
# 강제 컷 완화 로직과 동일한 전략. 단, 여기는 30초가 모델의 하드 리밋이라 "넘어서" 자를 수
# 없고, 30초 안에서 최대한 늦게(=최근 구간에서) 자연스러운 지점을 찾아 "덜" 채워서 자름.
_FORCE_CUT_LOOKBACK_SEC = 3.0
_FORCE_CUT_MIN_SILENCE_MS = 100


class Segment:
    """faster_whisper의 Segment와 동일한 속성명을 가진 경량 대체 객체.
    호출부(stt_service.py, realtime_service.py)가 seg.start/end/text/... 로
    접근하는 코드를 엔진 교체 없이 그대로 쓸 수 있게 하기 위함."""

    __slots__ = ("start", "end", "text", "avg_logprob", "no_speech_prob")

    def __init__(self, start: float, end: float, text: str, avg_logprob: float, no_speech_prob: float):
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = avg_logprob
        self.no_speech_prob = no_speech_prob


class TranscribeInfo:
    def __init__(self, language: str):
        self.language = language


class TransformersWhisperEngine:
    """
    faster-whisper(ctranslate2)가 aarch64+CUDA 조합(예: Grace-Blackwell 서버)에서
    GPU를 못 쓰는 문제 때문에 도입한 순수 PyTorch(transformers) 기반 대체 엔진.

    faster_whisper.WhisperModel과 최대한 동일한 호출 인터페이스
    (`.transcribe(audio, language=..., beam_size=..., vad_filter=..., condition_on_previous_text=...)`
    → `(segments, info)` 튜플, segments는 start/end/text/avg_logprob/no_speech_prob를 가진 이터러블)
    를 제공해서 나머지 코드(stt_service.py, realtime_service.py)를 거의 그대로 재사용한다.

    주의:
    - avg_logprob는 beam search일 땐 transformers가 주는 sequences_scores(선택된 시퀀스의
      길이 정규화 로그확률)를 그대로 쓰고, greedy일 땐 스텝별 argmax 로그확률 평균으로 근사.
      ctranslate2와 100% 동일한 산식은 아니므로 임계값(config.CONF_*)은 실측 재튜닝 여지 있음.
    - no_speech_prob는 근사치이며 신뢰도 낮음 — VAD가 1차로 침묵을 걸러주므로 보조 신호로만 사용.
    - SDPA(scaled_dot_product_attention)를 사용해 flash-attn 같은 별도 CUDA wheel
      설치 없이도 PyTorch 내장 고속 어텐션 커널을 활용함.
    """

    def __init__(self, model_id: str, device: str = "cuda", adapter_path: str | None = None):
        self.device = device
        self.torch_dtype = torch.float16 if device == "cuda" else torch.float32
        self._warned_no_scores = False

        logger.info(f"🧠 transformers Whisper 로딩 중... ({model_id} / {device})")
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = WhisperForConditionalGeneration.from_pretrained(
            model_id,
            torch_dtype=self.torch_dtype,
            attn_implementation="sdpa",
        ).to(device)

        # LoRA 파인튜닝 어댑터(finetune/stt/train_lora.py 결과물)를 얹어서 로드.
        # 임시 검증용 — 정식으로 채택되기 전까지는 환경변수로만 켜지도록 해서 기본 동작엔 영향 없음.
        if adapter_path:
            from peft import PeftModel
            logger.info(f"🧩 LoRA 어댑터 로딩 중... ({adapter_path})")
            peft_model = PeftModel.from_pretrained(self.model, adapter_path)
            # 어댑터를 베이스 가중치에 합쳐서(W ← W + BA·scaling) 원래 모델 구조로 되돌린다.
            # 병합 전에는 적응된 레이어마다 lora_A/lora_B 두 번의 추가 행렬곱과 PeftModel
            # 래퍼를 매 forward마다 타야 해서 추론이 느려짐 — 실측으로 병합 없이 어댑터를
            # 얹었을 때 500건 평가가 2.73초/건 → 3.11초/건(약 14%)으로 느려지는 걸 확인했음.
            # 병합은 수식상 동일한 연산이라 출력이 바뀌지 않음(fp16 반올림 수준의 차이만 존재).
            self.model = peft_model.merge_and_unload()
            logger.info("✅ LoRA 어댑터 병합 완료 (merge_and_unload — 추론 오버헤드 제거)")

        self.model.eval()
        logger.info(f"✅ transformers Whisper 로딩 완료 ({model_id})")

    def _load_audio(self, audio_or_path) -> np.ndarray:
        """numpy 배열(실시간 청크)과 파일 경로(배치 업로드) 둘 다 받을 수 있게 함."""
        if isinstance(audio_or_path, np.ndarray):
            return audio_or_path
        data, sample_rate = sf.read(audio_or_path, dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)  # 스테레오 → 모노
        if sample_rate != REALTIME_SAMPLE_RATE:
            logger.warning(
                f"⚠️ 오디오 샘플레이트({sample_rate}Hz)가 기대값({REALTIME_SAMPLE_RATE}Hz)과 다름. "
                "file_handler.py의 FFmpeg 전처리가 정상 동작했는지 확인 필요."
            )
        return data

    def _find_window_cutoff(self, window: np.ndarray) -> int:
        """
        30초 꽉 찬 창에서만 의미 있음 — 창이 30초 미만이면 뒤에 이어지는 오디오가 없다는
        뜻이므로 그대로 전부 씀. 30초 꽉 찬 경우, 마지막 몇 초 안에서 짧은 틈(≥100ms)을
        찾아 그 지점까지만 쓰고 나머지는 다음 창으로 넘김. 못 찾으면 기존처럼 30초 꽉 채워 자름.
        """
        if len(window) < _WINDOW_SAMPLES:
            return len(window)

        lookback_samples = int(_FORCE_CUT_LOOKBACK_SEC * REALTIME_SAMPLE_RATE)
        tail_start = max(0, len(window) - lookback_samples)
        tail = window[tail_start:]
        speech_spans = get_speech_timestamps(
            tail, VadOptions(min_silence_duration_ms=_FORCE_CUT_MIN_SILENCE_MS),
            sampling_rate=REALTIME_SAMPLE_RATE,
        )
        if len(speech_spans) >= 2:
            return tail_start + speech_spans[-2]["end"]
        return len(window)

    def _trim_silence(self, audio: np.ndarray) -> tuple[np.ndarray, bool, float]:
        """
        무음/노이즈 구간을 모델에 그대로 넣으면 Whisper가 그럴듯한 문장을 지어내는
        환각(hallucination) 현상이 잦아짐. faster-whisper는 vad_filter=True로 이걸
        자동 처리해주지만, transformers 엔진은 직접 안 해주므로 여기서 수동으로 구현.
        (트리밍된 오디오, 발화 감지 여부, 잘린 앞부분의 초 단위 길이)를 반환.
        - 발화가 아예 없으면 호출부가 모델 자체를 안 돌리게 함 (침묵 환각 원천 차단)
        - 잘린 앞부분 길이는 세그먼트 타임스탬프를 원본 오디오 기준으로 보정하는 데 필요
          (화자분리 결과와 시간축을 맞춰 병합하려면 원본 기준 타임스탬프여야 함)
        """
        timestamps = get_speech_timestamps(
            audio, VadOptions(min_silence_duration_ms=300), sampling_rate=REALTIME_SAMPLE_RATE
        )
        if not timestamps:
            return audio, False, 0.0
        start = timestamps[0]["start"]
        end = timestamps[-1]["end"]
        return audio[start:end], True, start / REALTIME_SAMPLE_RATE

    @torch.inference_mode()
    def transcribe(
        self,
        audio_or_path,
        language: str = "ko",
        beam_size: int = 5,
        vad_filter: bool = True,   # True면 발화 앞뒤 무음/노이즈를 잘라내고 모델에 전달 (환각 방지)
        initial_prompt: str = None,
        condition_on_previous_text: bool = False,  # 호환용. 청크/창 단위 독립 디코딩만 지원.
    ):
        audio = self._load_audio(audio_or_path)
        info = TranscribeInfo(language=language)
        trim_offset_sec = 0.0

        if vad_filter:
            audio, has_speech, trim_offset_sec = self._trim_silence(audio)
            if not has_speech:
                # 회의 종료 시 남는 잔여 버퍼(마이크는 켜져 있지만 아무도 말 안 하는 구간) 등에서
                # 순수 침묵을 모델에 넣으면 프롬프트 힌트를 그대로 반복 생성하는 환각이 잘 생김
                return [], info

        if len(audio) < REALTIME_SAMPLE_RATE // 20:  # 0.05초 미만이면 전사 무의미
            return [], info

        prompt_ids = None
        if initial_prompt:
            prompt_ids = self.processor.get_prompt_ids(initial_prompt, return_tensors="pt").to(self.device)

        # 30초 초과 오디오는 창 단위로 쪼개서 순차 전사 (processor의 조용한 truncate 방지).
        # 창이 정확히 30초씩 꽉 차면 단어/문장 중간이 잘릴 수 있어, 마지막 몇 초 안에서
        # 짧은 틈을 찾아 그 지점까지만 쓰고 나머지는 다음 창으로 넘김(_find_window_cutoff).
        segments = []
        window_start = 0
        while window_start < len(audio):
            raw_window = audio[window_start: window_start + _WINDOW_SAMPLES]
            if len(raw_window) < REALTIME_SAMPLE_RATE // 20:
                break
            cutoff = self._find_window_cutoff(raw_window)
            window = raw_window[:cutoff]
            text, avg_logprob, no_speech_prob = self._generate_window(window, language, beam_size, prompt_ids)
            if text:
                segments.append(Segment(
                    # trim_offset을 더해 원본 오디오 기준 타임스탬프로 보정
                    start=round(trim_offset_sec + window_start / REALTIME_SAMPLE_RATE, 2),
                    end=round(trim_offset_sec + (window_start + len(window)) / REALTIME_SAMPLE_RATE, 2),
                    text=text,
                    avg_logprob=avg_logprob,
                    no_speech_prob=no_speech_prob,
                ))
            window_start += cutoff

        return segments, info

    def _generate_window(self, window: np.ndarray, language: str, beam_size: int, prompt_ids):
        """30초 이하 오디오 창 하나를 전사해 (텍스트, avg_logprob, no_speech_prob)를 반환."""
        inputs = self.processor(window, sampling_rate=REALTIME_SAMPLE_RATE, return_tensors="pt")
        input_features = inputs.input_features.to(self.device, dtype=self.torch_dtype)

        generate_kwargs = dict(
            language=language,
            task="transcribe",
            num_beams=max(beam_size, 1),
            return_dict_in_generate=True,
            output_scores=True,
            # 애매한 오디오(노이즈 섞인 짧은 구간 등)에서 같은 구절을 계속 반복 생성하는
            # 환각 루프에 빠지는 걸 막는 안전장치. VAD로 순수 침묵은 이미 걸러내지만,
            # "약한 발화음+노이즈" 같은 경계 상황에 대한 2차 방어선.
            # 3으로 두면 "네, 네" 같은 정상적인 반복 표현까지 강제로 바뀔 수 있어 5로 완화
            # (환각 루프는 보통 훨씬 긴 구절이 통째로 반복되므로 5로도 충분히 잡힘).
            no_repeat_ngram_size=5,
        )
        # 주의: return_timestamps=True를 return_dict_in_generate=True와 같이 쓰면
        # transformers가 장문(long-form) 모드로 전환되면서 반환 구조가 dict로 바뀌어
        # outputs.sequences 접근이 깨짐. 장문 처리는 위의 창 분할 루프가 담당하므로 여기선 사용 안 함.
        if prompt_ids is not None:
            generate_kwargs["prompt_ids"] = prompt_ids

        outputs = self.model.generate(input_features, **generate_kwargs)

        # transformers의 prompt_ids 방식은 (faster-whisper와 달리) 프롬프트 텍스트를
        # sequences 맨 앞에 그대로 포함시켜서 반환함 — HF 공식 문서에도 명시된 동작.
        # 디코딩 전에 프롬프트 길이만큼 잘라내지 않으면 "비고 프로젝트 팀 회의. 용어: ..."가
        # 실제 전사 결과 앞에 그대로 붙어서 나옴.
        sequences = outputs.sequences
        if prompt_ids is not None:
            sequences = sequences[:, prompt_ids.shape[-1]:]
        text = self.processor.batch_decode(sequences, skip_special_tokens=True)[0].strip()
        avg_logprob = self._compute_avg_logprob(outputs)
        no_speech_prob = self._estimate_no_speech_prob(outputs, has_prompt=prompt_ids is not None)
        return text, avg_logprob, no_speech_prob

    def _compute_avg_logprob(self, outputs) -> float:
        """
        선택된 시퀀스의 평균 로그확률 → ctranslate2의 avg_logprob에 대응.
        - beam search: transformers가 계산해주는 sequences_scores(길이 정규화 완료)를 그대로 사용
        - greedy: 스텝별 argmax 로그확률 평균으로 근사 (greedy에선 선택 토큰 = argmax라 정확)
        - scores가 아예 비어있으면(transformers 버전에 따라 output_scores가 무시될 수 있음)
          0.0을 반환하는데, 이는 '완벽한 신뢰도'로 해석돼 게이팅이 무력화되므로 경고를 남김
        """
        seq_scores = getattr(outputs, "sequences_scores", None)
        if seq_scores is not None:
            return float(seq_scores[0].item())

        scores = getattr(outputs, "scores", None)
        if not scores:
            if not self._warned_no_scores:
                self._warned_no_scores = True
                logger.warning(
                    "⚠️ generate()가 scores를 반환하지 않음 — avg_logprob가 항상 0.0이 되어 "
                    "신뢰도 게이팅이 무력화됨. transformers 버전의 output_scores 지원 여부 확인 필요."
                )
            return 0.0
        log_probs = []
        for step_scores in scores:
            log_softmax = torch.log_softmax(step_scores[0].float(), dim=-1)
            log_probs.append(log_softmax.max().item())
        return float(np.mean(log_probs)) if log_probs else 0.0

    @staticmethod
    def _estimate_no_speech_prob(outputs, has_prompt: bool = False) -> float:
        """
        ctranslate2처럼 전용 no_speech 토큰 확률을 직접 노출하는 공식 API가
        transformers엔 없어서, 첫 디코딩 스텝의 불확실성으로 근사.
        첫 스텝이 강제 토큰(언어/태스크)이면 항상 0.0에 가까워 의미가 없을 수 있음 —
        VAD가 1차로 침묵을 걸러주므로 어디까지나 보조 신호로만 사용할 것.

        has_prompt=True면 추정 자체를 포기하고 0.0(=침묵 아님)을 반환한다.
        이 근사는 "첫 스텝은 강제 토큰이라 확률이 1에 가깝다"는 전제에 기대는데,
        initial_prompt를 붙이면 첫 스텝이 '실제 내용 토큰 예측'으로 바뀌어 전제가 깨진다.
        실측(AI Hub held-out 200건, 2026-07-27): 힌트를 켜자 confident 비율이
        95.5% → 72.0%로 떨어졌는데, avg_logprob 중앙값은 -0.153 → -0.163으로 거의
        그대로였고 임계값 미달도 1.0%→3.5%뿐이었다. 즉 하락분의 대부분이 이 값에서
        나왔고, 전사 품질 저하가 아니라 멀쩡한 발화를 침묵으로 오판한 것이었다.
        침묵 차단은 _trim_silence의 VAD가 1차로 담당하므로 이 신호를 버려도 안전망은 남는다.
        """
        if has_prompt:
            return 0.0
        scores = getattr(outputs, "scores", None)
        if not scores:
            return 0.0
        first_step_probs = torch.softmax(scores[0][0].float(), dim=-1)
        return float(1.0 - first_step_probs.max().item())
