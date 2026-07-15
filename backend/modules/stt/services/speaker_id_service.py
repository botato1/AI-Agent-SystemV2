import numpy as np
import torch
from pyannote.audio import Model, Inference

from ..core.config import (
    logger,
    HF_TOKEN,
    DEVICE,
    REALTIME_SAMPLE_RATE,
    SPEAKER_EMBEDDING_MODEL,
    SPEAKER_SIMILARITY_THRESHOLD,
)


def load_speaker_embedding_inference() -> Inference:
    """
    화자 임베딩 모델은 로딩이 무겁기 때문에 앱 시작 시(lifespan) 딱 한 번만 로드하고,
    회의(세션)마다 이 Inference 객체를 공유해서 재사용한다.
    화자 프로필(_profiles)은 회의별로 달라야 하므로 LiveSpeakerIdentifier 쪽에서
    세션마다 새로 만든다 — 모델 따로, 상태 따로 분리한 이유.

    주의: pyannote.audio 버전에 따라 Inference/Model API가 조금씩 달라질 수 있어
    실제 GPU 서버(faster-whisper/pyannote 설치된 환경)에서 한 번 동작 검증이 필요함.
    """
    model = Model.from_pretrained(SPEAKER_EMBEDDING_MODEL, use_auth_token=HF_TOKEN)
    inference = Inference(model, window="whole")
    if DEVICE == "cuda":
        import torch
        inference.to(torch.device("cuda"))
    return inference


class LiveSpeakerIdentifier:
    """
    실시간 청크마다 pyannote 전체 화자분리(클러스터링)를 다시 돌리면
    비용이 크고, 회의가 길어질수록 느려짐(누적 오디오 전체를 재분석하는 방식이라).

    대신 청크 오디오에서 화자 임베딩 벡터 하나만 뽑아, 이미 등록된 화자
    프로필들과 코사인 유사도를 비교해서 즉시 매칭하는 경량 방식.
    - 유사도가 임계값 이상인 기존 화자가 있으면 그 화자로 판단
    - 없으면 새 화자로 등록

    정밀한 최종 화자분리는 회의 종료 후 기존 배치 파이프라인(diarize_service)이
    한 번 더 수행해서 여기서 생긴 오차를 보정한다 (C-4 안전망과 동일한 설계 원칙).

    회의(세션)마다 새로 만들어야 함 — 화자 프로필은 회의별로 독립적이어야 하니까.
    """

    def __init__(
        self,
        inference: Inference,
        similarity_threshold: float = SPEAKER_SIMILARITY_THRESHOLD,
        initial_profiles: dict[str, np.ndarray] | None = None,
    ):
        """
        initial_profiles를 넘기면 "사전 등록(enrollment) 모드"로 동작함:
        - 회의 시작 전 각 참석자가 몇 초씩 말해서 미리 등록해둔 목소리 지문
        - 인원수가 고정되어 있으므로, 매칭 실패해도 새 화자를 만들지 않고
          가장 가까운 등록자에게 강제로 배정 (닫힌 집합 가정)
        - 이러면 "매 청크마다 새 화자로 등록되는" 문제가 원천적으로 사라짐

        initial_profiles가 없으면(사전 등록 안 하고 바로 시작한 경우) 기존처럼
        열린 집합 방식(유사도 낮으면 새 화자 생성)으로 폴백.
        """
        self.similarity_threshold = similarity_threshold
        self._inference = inference
        self._profiles: dict[str, np.ndarray] = dict(initial_profiles) if initial_profiles else {}
        self._closed_set = bool(initial_profiles)
        self._next_speaker_num = 1

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        denom = np.linalg.norm(a) * np.linalg.norm(b) + 1e-8
        return float(np.dot(a, b) / denom)

    def extract_embedding(self, audio: np.ndarray) -> np.ndarray:
        # pyannote Inference는 numpy 배열이 아니라 torch 텐서를 기대함 (내부에서 .to(device) 호출)
        waveform_tensor = torch.from_numpy(audio.reshape(1, -1).astype(np.float32))
        waveform = {"waveform": waveform_tensor, "sample_rate": REALTIME_SAMPLE_RATE}
        embedding = self._inference(waveform)
        return np.asarray(embedding).reshape(-1)

    def _find_best_match(self, embedding: np.ndarray) -> tuple[str | None, float]:
        best_label = None
        best_score = -1.0
        for label, profile in self._profiles.items():
            score = self._cosine_similarity(embedding, profile)
            if score > best_score:
                best_score = score
                best_label = label
        return best_label, best_score

    def identify(self, audio: np.ndarray) -> str:
        """
        청크 오디오를 받아 화자 라벨(사전 등록 이름 또는 "SPEAKER_N")을 즉시 반환.
        내부적으로 프로필을 계속 갱신(이동 평균)해서 화자 목소리 변화에도 서서히 적응.
        """
        embedding = self.extract_embedding(audio)

        if not self._profiles:
            # 사전 등록도 없고 첫 화자도 없음 → 무조건 첫 화자로 등록
            new_label = f"SPEAKER_{self._next_speaker_num}"
            self._next_speaker_num += 1
            self._profiles[new_label] = embedding
            logger.info(f"🆕 새 화자 등록: {new_label} (첫 화자)")
            return new_label

        best_label, best_score = self._find_best_match(embedding)

        if self._closed_set:
            # 인원수를 미리 알고 있으므로 새 화자를 만들지 않고 무조건 가장 가까운 등록자에게 배정.
            # 단, 프로필 갱신(이동 평균)은 유사도가 충분히 높을 때만 — 겹쳐 말한 구간 등이
            # 잘못 배정됐을 때 엉뚱한 사람의 목소리 지문을 조금씩 오염시키는 걸 방지
            if best_score >= self.similarity_threshold:
                self._profiles[best_label] = 0.9 * self._profiles[best_label] + 0.1 * embedding
            logger.info(f"🗣️ 화자 매칭(사전등록): {best_label} (유사도 {best_score:.2f})")
            return best_label

        if best_score >= self.similarity_threshold:
            self._profiles[best_label] = 0.9 * self._profiles[best_label] + 0.1 * embedding
            logger.info(f"🗣️ 화자 매칭: {best_label} (유사도 {best_score:.2f})")
            return best_label

        new_label = f"SPEAKER_{self._next_speaker_num}"
        self._next_speaker_num += 1
        self._profiles[new_label] = embedding
        logger.info(f"🆕 새 화자 등록: {new_label} (기존 최고 유사도 {best_score:.2f})")
        return new_label
