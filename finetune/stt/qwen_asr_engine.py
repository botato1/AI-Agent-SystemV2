"""
Qwen3-ASR 평가용 엔진 어댑터.

기존 STT 파이프라인(faster-whisper / TransformersWhisperEngine)과 동일한
`.transcribe(...) -> (segments, info)` 형태를 흉내내서, evaluate_wer.py가
모델만 바꿔 끼우면 같은 평가셋으로 비교할 수 있게 한다.

⚠️ 아직 평가 전용이다. 서버(backend/modules/stt)에는 연결하지 않았다.
   Whisper와 달리 세그먼트 단위 타임스탬프를 주지 않기 때문에(별도
   Qwen3-ForcedAligner-0.6B 필요), 화자분리 병합이 걸린 실시간 경로에
   그대로 넣을 수 없다. 정확도가 먼저 검증되면 그때 통합 방식을 정한다.

Whisper 대비 핵심 차이:
  - `prompt` 인자로 도메인 용어/배경 텍스트를 넣는 컨텍스트 바이어싱이
    학습 단계에 포함돼 있다. Whisper의 initial_prompt처럼 "앞 문장 이어쓰기"로
    동작하지 않으므로, 짧은 청크에서 프롬프트를 그대로 받아적는 문제가
    구조적으로 발생하지 않아야 한다 — 이 가정을 검증하는 게 2단계 목표.

필요 버전: transformers >= 5.13
"""
from __future__ import annotations

import torch


class _Segment:
    """faster-whisper Segment와 최소 호환되는 결과 조각."""

    __slots__ = ("start", "end", "text", "avg_logprob", "no_speech_prob")

    def __init__(self, start, end, text, avg_logprob, no_speech_prob=0.0):
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = avg_logprob
        self.no_speech_prob = no_speech_prob


class _Info:
    __slots__ = ("language", "duration")

    def __init__(self, language, duration=0.0):
        self.language = language
        self.duration = duration


class Qwen3ASREngine:
    """
    Qwen3-ASR을 우리 transcribe 규약으로 감싼 어댑터.

    Whisper 엔진들과 달리 세그먼트를 나누지 않고 전체 전사를 세그먼트 1개로
    돌려준다. WER/CER 평가는 전체 텍스트만 쓰므로 평가 목적에는 충분하다.
    """

    def __init__(self, model_id: str, device: str = "cuda", max_new_tokens: int = 448,
                 itn: bool = True):
        """itn: 발음형 숫자를 아라비아 숫자로 되돌리는 후처리 적용 여부 (효과 측정용 스위치)."""
        from transformers import AutoProcessor, AutoModelForMultimodalLM

        self.model_id = model_id
        self.max_new_tokens = max_new_tokens
        self.itn = itn
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModelForMultimodalLM.from_pretrained(
            model_id,
            dtype=torch.bfloat16,
            device_map=device if device != "cuda" else "auto",
        )
        self.model.eval()

    def transcribe(
        self,
        audio,
        language: str | None = "ko",
        beam_size: int = 1,
        initial_prompt: str | None = None,
        **_ignored,          # vad_filter, condition_on_previous_text 등은 이 모델에 없음
    ):
        """
        audio: 파일 경로(str) 또는 16kHz float32 numpy 배열.
        initial_prompt: 컨텍스트 바이어싱 텍스트. Whisper의 initial_prompt와
                        이름만 같고 동작이 다르다(모델이 학습으로 배운 기능).

        processor.apply_transcription_request()는 시스템 메시지에 언어 힌트만
        넣고 컨텍스트를 받을 통로가 없다(transformers 5.13 기준 `prompt` 인자
        없음 — 넘기면 조용히 무시된다). 채팅 템플릿이 시스템 역할의 text 조각을
        전부 이어붙이므로, 언어와 컨텍스트를 같이 넣으려면 대화를 직접 만들어야
        한다.
        """
        inputs = self.processor.apply_chat_template(
            [self._build_conversation(audio, language, initial_prompt)],
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
        ).to(self.model.device, self.model.dtype)

        prompt_len = inputs["input_ids"].shape[1]
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                num_beams=beam_size,
                do_sample=False,
                return_dict_in_generate=True,
                output_scores=True,
            )

        generated_ids = outputs.sequences[:, prompt_len:]
        text = self.processor.decode(generated_ids, return_format="transcription_only")[0].strip()
        if self.itn:
            from stt.utils.korean_itn import to_digits
            text = to_digits(text)
        avg_logprob = self._avg_logprob(outputs, generated_ids, beam_size)

        return [_Segment(0.0, 0.0, text, avg_logprob)], _Info(language)

    @staticmethod
    def _build_conversation(audio, language: str | None, context: str | None) -> list[dict]:
        """
        시스템 메시지 = 언어 힌트 + 컨텍스트, 유저 메시지 = 오디오.

        언어는 "ko" 같은 코드로 줘도 resolve_language가 "Korean"으로 바꿔준다
        (모델이 학습 때 본 형태가 전체 이름이라 코드 그대로 넣으면 안 됨).
        """
        from transformers.models.qwen3_asr.processing_qwen3_asr import resolve_language

        parts = []
        if language:
            parts.append(resolve_language(language))
        if context:
            parts.append(context)

        system_content = [{"type": "text", "text": "\n".join(parts)}] if parts else []
        audio_content = (
            {"type": "audio", "path": audio} if isinstance(audio, str)
            else {"type": "audio", "audio": audio}
        )
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": [audio_content]},
        ]

    @staticmethod
    def _avg_logprob(outputs, generated_ids, beam_size: int) -> float:
        """
        confident 판정에 쓸 신뢰도 신호.

        Whisper 엔진과 같은 규칙을 따른다 — beam search면 generate가 계산해준
        정규화 점수(sequences_scores)를 쓰고, greedy면 매 스텝 선택된 토큰의
        로그확률을 평균낸다. 두 방식은 분포가 다르므로 임계값을 공유하면 안 된다
        (beam 10 -> 1 전환 때 실제로 게이트가 무력화됐던 적 있음).
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
