import numpy as np
import soundfile as sf
import torch
from transformers import AutoProcessor, WhisperForConditionalGeneration

from ..core.config import logger, REALTIME_SAMPLE_RATE


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
    - avg_logprob / no_speech_prob는 ctranslate2와 100% 동일한 산식이 아니라
      transformers generate() 출력에서 근사적으로 계산한 값. 신뢰도 게이팅 임계값
      (config.CONF_AVG_LOGPROB_THRESHOLD 등)은 실제 서버에서 로그를 보고 재튜닝이 필요할 수 있음.
    - SDPA(scaled_dot_product_attention)를 사용해 flash-attn 같은 별도 CUDA wheel
      설치 없이도 PyTorch 내장 고속 어텐션 커널을 활용함.
    - GPU 서버에서 첫 실행 시 모델 다운로드(수 GB)와 동작 검증이 필요함 — 로컬(Mac)에서는
      import/문법 검증만 했고 실제 추론 호출은 못 해봤음.
    """

    def __init__(self, model_id: str, device: str = "cuda"):
        self.device = device
        self.torch_dtype = torch.float16 if device == "cuda" else torch.float32

        logger.info(f"🧠 transformers Whisper 로딩 중... ({model_id} / {device})")
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = WhisperForConditionalGeneration.from_pretrained(
            model_id,
            torch_dtype=self.torch_dtype,
            attn_implementation="sdpa",
        ).to(device)
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

    @torch.inference_mode()
    def transcribe(
        self,
        audio_or_path,
        language: str = "ko",
        beam_size: int = 5,
        vad_filter: bool = True,   # 호환용 파라미터. VAD는 realtime_service 쪽에서 이미 처리.
        initial_prompt: str = None,
        condition_on_previous_text: bool = False,  # 호환용. 청크 단위 독립 디코딩만 지원.
    ):
        audio = self._load_audio(audio_or_path)

        inputs = self.processor(
            audio, sampling_rate=REALTIME_SAMPLE_RATE, return_tensors="pt"
        )
        input_features = inputs.input_features.to(self.device, dtype=self.torch_dtype)

        generate_kwargs = dict(
            language=language,
            task="transcribe",
            num_beams=max(beam_size, 1),
            return_timestamps=True,
            return_dict_in_generate=True,
            output_scores=True,
        )
        if initial_prompt:
            prompt_ids = self.processor.get_prompt_ids(initial_prompt, return_tensors="pt")
            generate_kwargs["prompt_ids"] = prompt_ids.to(self.device)

        outputs = self.model.generate(input_features, **generate_kwargs)

        text = self.processor.batch_decode(outputs.sequences, skip_special_tokens=True)[0].strip()
        avg_logprob = self._compute_avg_logprob(outputs)
        no_speech_prob = self._estimate_no_speech_prob(outputs)

        duration_sec = round(len(audio) / REALTIME_SAMPLE_RATE, 2)
        segments = [Segment(0.0, duration_sec, text, avg_logprob, no_speech_prob)]
        info = TranscribeInfo(language=language)
        return segments, info

    @staticmethod
    def _compute_avg_logprob(outputs) -> float:
        """생성된 각 토큰의 최고 로그확률 평균 → ctranslate2의 avg_logprob에 대응하는 근사치."""
        scores = getattr(outputs, "scores", None)
        if not scores:
            return 0.0
        log_probs = []
        for step_scores in scores:
            log_softmax = torch.log_softmax(step_scores[0].float(), dim=-1)
            log_probs.append(log_softmax.max().item())
        return float(np.mean(log_probs)) if log_probs else 0.0

    @staticmethod
    def _estimate_no_speech_prob(outputs) -> float:
        """
        ctranslate2처럼 전용 no_speech 토큰 확률을 직접 노출하는 공식 API가
        transformers엔 없어서, 첫 디코딩 스텝의 불확실성(최고 확률이 낮을수록
        '무슨 소리인지 모르겠다'에 가까움)으로 근사. VAD가 1차로 침묵을 걸러주므로
        이 값은 보조 신호로만 사용할 것.
        """
        scores = getattr(outputs, "scores", None)
        if not scores:
            return 0.0
        first_step_probs = torch.softmax(scores[0][0].float(), dim=-1)
        return float(1.0 - first_step_probs.max().item())
