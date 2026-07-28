import numpy as np
import torch
from pyannote.audio import Model, Inference
from faster_whisper.vad import VadOptions, get_speech_timestamps

from ..core.config import (
    logger,
    HF_TOKEN,
    DEVICE,
    REALTIME_SAMPLE_RATE,
    SPEAKER_EMBEDDING_MODEL,
    SPEAKER_SIMILARITY_THRESHOLD,
    MAX_SPEAKERS,
)

# 화자 판정용 임베딩을 뽑을 때, 이보다 짧은 구간은 임베딩이 불안정해서 쓰지 않는다
# (너무 짧으면 목소리 특성보다 발음 내용에 휘둘림)
_MIN_EMBED_SEC = 1.0


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

    @staticmethod
    def _dominant_speech_region(audio: np.ndarray) -> np.ndarray:
        """
        청크에서 '가장 긴 연속 발화 구간'만 잘라서 반환 — 화자 판정 전용 전처리.

        왜 필요한가: 청크(최대 28초)가 화자 전환을 걸치면 두 사람 목소리가 한 청크에
        들어가는데, 이걸 통째로 임베딩하면 두 목소리가 섞인 벡터가 나와 기존 어느
        프로필과도 안 맞는다. 그러면 매번 새 화자가 만들어진다 — 실측(2026-07-27
        2인 회의)에서 유사도가 0.26~0.40으로 떨어지며 SPEAKER_1~4까지 유령 화자가
        생긴 원인이 이것.
        가장 긴 발화 구간은 한 사람이 이어 말한 부분일 가능성이 높아 훨씬 깨끗하다.

        발화 구간이 하나뿐이거나(=섞일 일 없음) 가장 긴 구간이 너무 짧으면
        원본을 그대로 돌려준다 — 잘라내서 얻을 게 없거나 오히려 손해이므로.
        """
        spans = get_speech_timestamps(
            audio, VadOptions(min_silence_duration_ms=300), sampling_rate=REALTIME_SAMPLE_RATE
        )
        if len(spans) < 2:
            return audio
        longest = max(spans, key=lambda s: s["end"] - s["start"])
        if (longest["end"] - longest["start"]) / REALTIME_SAMPLE_RATE < _MIN_EMBED_SEC:
            return audio
        return audio[longest["start"]:longest["end"]]

    def extract_embedding(self, audio: np.ndarray) -> np.ndarray:
        # pyannote Inference는 numpy 배열이 아니라 torch 텐서를 기대함 (내부에서 .to(device) 호출)
        waveform_tensor = torch.from_numpy(audio.reshape(1, -1).astype(np.float32))
        waveform = {"waveform": waveform_tensor, "sample_rate": REALTIME_SAMPLE_RATE}
        embedding = self._inference(waveform)
        return np.asarray(embedding).reshape(-1)

    def rename_speaker(self, old_name: str, new_name: str) -> bool:
        """
        진행 중인 세션의 화자 라벨 교체 — rename API가 저장소만 고치고 살아있는
        세션은 못 고쳐서 "회의 시작 후 이름을 수정하면 자막엔 옛 이름이 계속 나오는"
        문제를 해결하기 위한 전파 지점. 이후 청크부터 새 이름으로 라벨링됨.
        """
        if old_name not in self._profiles or new_name in self._profiles:
            return False
        self._profiles[new_name] = self._profiles.pop(old_name)
        logger.info(f"✏️ 세션 화자 라벨 교체: {old_name} → {new_name}")
        return True

    def _find_best_match(self, embedding: np.ndarray) -> tuple[str | None, float]:
        best_label = None
        best_score = -1.0
        # identify()는 executor 스레드에서 돌고 rename_speaker()는 이벤트 루프에서 불릴 수
        # 있어서, 순회 중 dict 크기 변경 예외가 나지 않게 스냅샷을 순회
        for label, profile in list(self._profiles.items()):
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
        # 청크 전체가 아니라 가장 긴 발화 구간으로 판정 — 화자 전환이 섞인 청크에서
        # 유령 화자가 만들어지는 걸 막기 위함 (_dominant_speech_region 참고).
        # 주의: extract_embedding 자체는 원본 그대로 두어야 한다 — refine_service가
        # "같은 화자의 여러 발화를 이어붙여" 임베딩할 때 재사용하는데, 거기서는
        # 오히려 오디오가 많을수록 정확하므로 잘라내면 안 됨.
        embedding = self.extract_embedding(self._dominant_speech_region(audio))

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

        # 열린 집합이어도 화자 수는 무한정 늘 수 없다. 상한에 닿으면 새로 만들지 않고
        # 가장 가까운 기존 화자에 배정 — 상한이 없으면 판정이 한 번 흔들릴 때마다
        # 화자가 계속 늘어나 회의록이 유령 화자로 뒤덮인다(실측에서 SPEAKER_4까지 생김).
        # 이 경우 프로필은 갱신하지 않는다(확신이 없는 배정이라 지문을 오염시키면 안 됨).
        if len(self._profiles) >= MAX_SPEAKERS:
            logger.info(
                f"🗣️ 화자 매칭(상한 {MAX_SPEAKERS}명 도달, 최근접 배정): "
                f"{best_label} (유사도 {best_score:.2f})"
            )
            return best_label

        new_label = f"SPEAKER_{self._next_speaker_num}"
        self._next_speaker_num += 1
        self._profiles[new_label] = embedding
        logger.info(f"🆕 새 화자 등록: {new_label} (기존 최고 유사도 {best_score:.2f})")
        return new_label
