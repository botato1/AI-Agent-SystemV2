import os

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
    SPEAKER_EMBEDDING_CHECKPOINT,
    SPEECHBRAIN_CACHE_DIR,
    SPEAKER_SIMILARITY_THRESHOLD,
    SPEAKER_MIN_ASSIGN_SIMILARITY,
    SPEAKER_MIN_MARGIN,
    SPEAKER_ABSOLUTE_FLOOR,
    MAX_SPEAKERS,
)

# 화자 판정용 임베딩을 뽑을 때, 이보다 짧은 구간은 임베딩이 불안정해서 쓰지 않는다
# (너무 짧으면 목소리 특성보다 발음 내용에 휘둘림)
_MIN_EMBED_SEC = 1.0

# 미상끼리 같은 raw id로 묶을 최소 유사도(LiveSpeakerIdentifier.label_unassigned).
#
# 왜 이렇게 높은가 (2026-08-20 실측): 묶음 단위 판정 실험에서 같은 사람 유사도
# (0.29~0.53)와 다른 사람 유사도(김나연↔이승주 0.588~0.632)가 겹쳐서, 문턱
# 0.55로도 서로 다른 사람이 합쳐지는 참사가 났다(cpCER 평균 21.50%→65.68%).
# 여기서는 그 실패를 반복하지 않기 위해 알려진 다른 사람 최고값(0.632)보다
# 확실히 높게 잡는다 — 같은 사람을 여러 id로 쪼개는 게(안전, 프론트가 그냥
# "화자 C"를 하나 더 보는 정도) 서로 다른 사람을 합치는 것(위험, 남의 발언이
# 같은 사람으로 묶임)보다 낫다는 그날의 결론을 그대로 적용했다.
# ⚠️ 실측 없이 정한 초안값이다 — 실제 회의로 확인 전까지는 이 값을 낮추지 말 것.
_UNASSIGNED_MERGE_THRESHOLD = 0.75


class SpeechBrainEmbedding:
    """speechbrain 화자 인코더를 pyannote Inference처럼 쓰게 감싼다.

    왜 감싸는가: LiveSpeakerIdentifier는 `self._inference({"waveform": ..., "sample_rate": ...})`
    하나만 호출한다. 그 규약만 맞추면 호출부(실시간·재분석·등록 API 전부)를 안 건드리고
    백엔드를 갈아끼울 수 있다.

    왜 speechbrain이 필요한가 (2026-08-18):
      후보 네 개를 우리 회의 오디오로 비교한 결과(probe_embedding_models.py),
      speechbrain의 ResNet-TDNN이 **교차 회의 EER 17.32% → 12.47%**로 가장 좋았다.
      pyannote는 wespeaker 계열만 감싸므로 이 모델을 쓰려면 별도 로더가 필요하다.
    """

    def __init__(self, model_id: str):
        # 지연 임포트 — speechbrain을 안 쓰는 배포에서는 설치조차 필요 없어야 한다
        from speechbrain.inference.speaker import EncoderClassifier
        from speechbrain.utils.fetching import LocalStrategy
        savedir = os.path.join(SPEECHBRAIN_CACHE_DIR, model_id.replace("/", "_"))
        os.makedirs(savedir, exist_ok=True)
        # speechbrain 기본값(SYMLINK)은 HF 캐시 → savedir로 심볼릭 링크를 건다.
        # NAS 마운트가 심링크를 지원하지 않아 OSError(Errno 95)로 죽는다
        # (reference_nas_env_gotchas의 ④와 같은 부류지만, 이건 huggingface_hub가
        # 아니라 speechbrain 자체의 연결 로직이라 HF_HUB_DISABLE_SYMLINKS로는 안 잡힌다).
        # COPY로 바꾸면 실제로 파일을 복사해서 링크 자체를 안 만든다.
        self._enc = EncoderClassifier.from_hparams(
            source=model_id, savedir=savedir, run_opts={"device": DEVICE},
            local_strategy=LocalStrategy.COPY)

    def to(self, _device):
        """pyannote Inference와 호출 규약을 맞추기 위한 no-op. 디바이스는 생성 시 정한다."""
        return self

    def __call__(self, waveform: dict):
        # extract_embedding이 (1, samples) 텐서를 넘긴다 — speechbrain의 (batch, samples)와 같다
        with torch.no_grad():
            emb = self._enc.encode_batch(waveform["waveform"].to(DEVICE))
        return emb.detach().cpu().numpy().reshape(-1)


def load_speaker_embedding_inference():
    """
    화자 임베딩 모델은 로딩이 무겁기 때문에 앱 시작 시(lifespan) 딱 한 번만 로드하고,
    회의(세션)마다 이 객체를 공유해서 재사용한다.
    화자 프로필(_profiles)은 회의별로 달라야 하므로 LiveSpeakerIdentifier 쪽에서
    세션마다 새로 만든다 — 모델 따로, 상태 따로 분리한 이유.

    백엔드는 **모델 ID로 판별한다** — "speechbrain/"으로 시작하면 speechbrain,
    아니면 pyannote. 환경변수를 따로 두지 않는 이유는 ID에 이미 정보가 있고,
    둘을 따로 두면 어긋날 수 있기 때문이다.

    주의: pyannote.audio 버전에 따라 Inference/Model API가 조금씩 달라질 수 있어
    실제 GPU 서버(faster-whisper/pyannote 설치된 환경)에서 한 번 동작 검증이 필요함.
    """
    if SPEAKER_EMBEDDING_MODEL.startswith("speechbrain/"):
        if SPEAKER_EMBEDDING_CHECKPOINT:
            # 조용히 무시하면 "체크포인트를 줬는데 안 먹은" 상태를 아무도 모른다
            raise RuntimeError(
                "SPEAKER_EMBEDDING_CHECKPOINT는 pyannote 백엔드에서만 쓸 수 있다 "
                f"(현재 모델: {SPEAKER_EMBEDDING_MODEL})")
        logger.info(f"🧠 화자 임베딩 백엔드: speechbrain / {SPEAKER_EMBEDDING_MODEL}")
        return SpeechBrainEmbedding(SPEAKER_EMBEDDING_MODEL)

    model = Model.from_pretrained(SPEAKER_EMBEDDING_MODEL, use_auth_token=HF_TOKEN)

    # 파인튜닝 가중치가 지정돼 있으면 얹는다. config의 SPEAKER_EMBEDDING_CHECKPOINT 주석 참고 —
    # 특히 이 값을 켜면 기존 목소리 프로필을 다시 만들어야 한다.
    if SPEAKER_EMBEDDING_CHECKPOINT:
        if not os.path.isfile(SPEAKER_EMBEDDING_CHECKPOINT):
            raise FileNotFoundError(
                f"화자 임베딩 체크포인트를 못 찾음: {SPEAKER_EMBEDDING_CHECKPOINT}")
        state = torch.load(SPEAKER_EMBEDDING_CHECKPOINT, map_location="cpu")
        missing, unexpected = model.load_state_dict(state, strict=False)
        # 조용히 넘어가면 "가중치가 안 실렸는데 잘 도는 것처럼 보이는" 상태가 된다.
        # 화자 인식은 틀려도 예외가 안 나므로 여기서 막지 않으면 아무도 못 알아챈다.
        if len(missing) > len(state) // 2:
            raise RuntimeError(
                f"체크포인트가 모델 구조와 맞지 않음 (없는 키 {len(missing)}개)")
        if missing or unexpected:
            logger.warning(
                f"⚠️ 화자 임베딩 가중치 일부 불일치 — 없는 키 {len(missing)}개 / "
                f"남는 키 {len(unexpected)}개")
        logger.info(f"🎯 화자 임베딩 파인튜닝 가중치 적용: {SPEAKER_EMBEDDING_CHECKPOINT}")
        logger.warning("⚠️ 목소리 프로필이 이 가중치로 만들어진 것인지 확인할 것 — "
                       "옛 프로필과 섞으면 화자 인식이 망가진다")

    inference = Inference(model, window="whole")
    if DEVICE == "cuda":
        # torch는 모듈 최상단에서 이미 import 한다. 여기서 다시 import 하면 파이썬이
        # 이 함수 전체에서 torch를 지역 이름으로 보게 되어, 위쪽의 torch.load가
        # UnboundLocalError로 죽는다.
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
        max_speakers: int | None = None,
    ):
        """
        initial_profiles를 넘기면 "사전 등록(enrollment) 모드"로 동작함:
        - 회의 시작 전 각 참석자가 몇 초씩 말해서 미리 등록해둔 목소리 지문
        - 인원수가 고정되어 있으므로, 매칭 실패해도 새 화자를 만들지 않고
          가장 가까운 등록자에게 강제로 배정 (닫힌 집합 가정)
        - 이러면 "매 청크마다 새 화자로 등록되는" 문제가 원천적으로 사라짐

        initial_profiles가 없으면(사전 등록 안 하고 바로 시작한 경우) 기존처럼
        열린 집합 방식(유사도 낮으면 새 화자 생성)으로 폴백.

        max_speakers: 열린 집합에서 새 화자를 몇 명까지 만들지. 안 주면
        config.MAX_SPEAKERS(팀 인원 6명 기준값)로 폴백한다 — 등록 안 된 사람이
        여러 명 들어오는 회의(예: 한 계정으로 여러 명 참여)는 실제 인원이 다를 수
        있으므로 호출부(웹소켓 엔드포인트)가 회의별로 넘겨줄 수 있게 열어둔다.
        """
        self.similarity_threshold = similarity_threshold
        self._inference = inference
        self._profiles: dict[str, np.ndarray] = dict(initial_profiles) if initial_profiles else {}
        self._closed_set = bool(initial_profiles)
        self._max_speakers = max_speakers if max_speakers else MAX_SPEAKERS
        self._next_speaker_num = 1
        # 닫힌 집합에서 등록자 누구와도 안 닮은(미상) 임베딩끼리 구분용 raw id를
        # 매기는 보조 풀. 진짜 프로필(_profiles)과 완전히 분리 — label_unassigned() 참고.
        self._unassigned_profiles: dict[str, np.ndarray] = {}
        self._next_unassigned_num = 1

    @property
    def enrolled_names(self) -> list[str]:
        """이번 회의의 비교 대상 이름들. 경고 문구에 실제 이름을 넣어야
        사용자가 '아 참석자를 잘못 골랐구나'를 바로 안다."""
        return sorted(self._profiles) if self._closed_set else []

    @property
    def enrolled_count(self) -> int:
        """사전 등록된 화자 수. 닫힌 집합이 아니면 0 — 열린 집합에서는 '미상'이
        정상 동작이라, 호출부가 경고 여부를 가를 때 이 값으로 구분한다."""
        return len(self._profiles) if self._closed_set else 0

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

    def label_unassigned(self, embedding: np.ndarray, update_profile: bool = True) -> str:
        """
        등록자 누구와도 안 닮은(미상) 임베딩에 구분용 raw id("SPEAKER_미상N")를 붙인다.

        왜 (2026-08-21, 팀원 요청): 미상 세그먼트는 지금까지 전부 speaker=None으로
        나가서, 프론트가 "같은 미상 화자가 여러 번 말했는지"조차 구분할 수 없었다.
        진짜 프로필(_profiles)과 완전히 분리된 이 보조 풀에서만 구분자를 매긴다 —
        신원 판정 로직(identify/match_closed_set)에는 손대지 않는다. 그 로직들은
        turn 분할·병합처럼 이미 세밀하게 튜닝돼 있어(realtime_service.py 참고),
        None의 의미를 바꾸면 그 로직들까지 연쇄적으로 영향을 받아 회귀 위험이 크다.
        그래서 이 메서드는 **최종 세그먼트에 이름을 다 붙인 뒤, 후처리 단계에서만**
        호출해서 쓴다(refine_service._refine 참고).

        문턱(_UNASSIGNED_MERGE_THRESHOLD)을 높게 잡은 이유는 모듈 상단 주석 참고 —
        다른 사람을 합치는 것보다 같은 사람을 여러 id로 쪼개는 게 안전하다는
        2026-08-20 묶음 판정 실험의 결론을 그대로 적용했다.
        """
        if self._unassigned_profiles:
            best_label, best_score = max(
                ((label, self._cosine_similarity(embedding, profile))
                 for label, profile in self._unassigned_profiles.items()),
                key=lambda kv: kv[1],
            )
            if best_score >= _UNASSIGNED_MERGE_THRESHOLD:
                if update_profile:
                    self._unassigned_profiles[best_label] = (
                        0.9 * self._unassigned_profiles[best_label] + 0.1 * embedding
                    )
                return best_label
        if not update_profile:
            # 새 id를 확정하지 않는다(잠정 경로) — 다음 확정 호출이 실제로 만든다.
            return f"SPEAKER_미상{self._next_unassigned_num}"
        label = f"SPEAKER_미상{self._next_unassigned_num}"
        self._next_unassigned_num += 1
        self._unassigned_profiles[label] = embedding
        return label

    def rank_profiles(self, embedding: np.ndarray) -> list[tuple[float, str]]:
        """등록 프로필을 유사도 내림차순으로. 1등뿐 아니라 2등까지 봐야 margin을 잴 수 있다."""
        # identify()는 executor 스레드에서 돌고 rename_speaker()는 이벤트 루프에서 불릴 수
        # 있어서, 순회 중 dict 크기 변경 예외가 나지 않게 스냅샷을 순회
        return sorted(
            ((self._cosine_similarity(embedding, profile), label)
             for label, profile in list(self._profiles.items())),
            reverse=True,
        )

    def _find_best_match(self, embedding: np.ndarray) -> tuple[str | None, float]:
        ranked = self.rank_profiles(embedding)
        if not ranked:
            return None, -1.0
        return ranked[0][1], ranked[0][0]

    def match_closed_set(self, embedding: np.ndarray) -> tuple[str | None, str | None, float, float]:
        """
        참석자를 아는 회의의 판정: **절대 점수가 아니라 순위**로 정하고,
        1등과 2등의 차이(margin)로만 걸러낸다.

        (판정된 이름 또는 None, 최근접 이름, 유사도, margin)을 준다 — 미상일 때도
        누구와 제일 가까웠는지는 로그에 남겨야 원인을 좁힐 수 있다.

        왜 절대 문턱을 버렸나 (2026-08-04 실측, 정답 대본이 있는 5인 회의):
          평균 유사도가 이준오 0.360 / 이승주 0.302 / 김나연 0.286으로 하한(0.4)
          미만인데 1등은 87~94% 맞혔다. **순위는 처음부터 맞았고 문턱이 정답을
          걷어내고 있었다.** 절대 점수는 프로필 품질에 따라 0.29~0.53으로 흩어지므로
          모두에게 같은 문턱을 씌우는 것 자체가 성립하지 않는다.

          절대 문턱은 "누가 말할지 모를 때" 쓰는 기준이다(등록 안 된 사람이 말할 수
          있으니 '충분히 닮았나'를 물어야 한다). 참석자를 알면 물어야 할 것은
          "다섯 중 누가 제일 닮았나"다. 열린 집합 경로는 지금도 절대 문턱을 쓴다.

        margin이 필요한 이유: 순위 판정은 **무조건 누군가를 지목한다.** 잡음이나
        겹쳐 말한 구간에도 이름이 붙는다는 뜻이라, 그걸 막을 방어선이 하나는 있어야 한다.
        실측에서 오답 창의 margin은 0.028~0.078, 정답 창은 평균 0.086~0.244였다.
        """
        ranked = self.rank_profiles(embedding)
        if not ranked:
            return None, None, -1.0, 0.0
        best_score, best_label = ranked[0]

        if len(ranked) == 1:
            # 경쟁자가 없으면 margin을 잴 수 없다(항상 0이 되어 전부 미상이 된다).
            # 1인 회의에선 "누가 제일 닮았나"라는 질문 자체가 성립하지 않으므로,
            # 열린 집합과 같은 절대 문턱으로 판단한다.
            matched = best_label if best_score >= SPEAKER_MIN_ASSIGN_SIMILARITY else None
            return matched, best_label, best_score, 0.0

        margin = best_score - ranked[1][0]
        if best_score < SPEAKER_ABSOLUTE_FLOOR:
            # 명단 밖 목소리 차단 — 1등이라도 이 정도조차 안 닮았으면 참석자가 아니다.
            # margin은 이걸 못 잡는다(명단 안에서 갈리기만 하면 통과한다).
            return None, best_label, best_score, margin
        if margin < SPEAKER_MIN_MARGIN:
            return None, best_label, best_score, margin
        return best_label, best_label, best_score, margin

    def identify(self, audio: np.ndarray, update_profile: bool = True) -> str | None:
        """
        청크 오디오를 받아 화자 라벨(사전 등록 이름 또는 "SPEAKER_N")을 즉시 반환.
        내부적으로 프로필을 계속 갱신(이동 평균)해서 화자 목소리 변화에도 서서히 적응.

        update_profile=False면 판정만 하고 프로필/화자 목록을 전혀 건드리지 않는다.
        잠정(partial) 자막처럼 1초마다 호출되는 경로용 — 확정 경로보다 10배 이상 자주
        불리는데 매번 이동 평균을 돌리면 잘못 배정된 구간이 목소리 지문을 빠르게
        오염시킨다. 지문 갱신은 VAD로 끊긴 확정 청크에서만 한다.
        """
        # 청크 전체가 아니라 가장 긴 발화 구간으로 판정 — 화자 전환이 섞인 청크에서
        # 유령 화자가 만들어지는 걸 막기 위함 (_dominant_speech_region 참고).
        # 주의: extract_embedding 자체는 원본 그대로 두어야 한다 — speaker_timeline이
        # 이미 발화 구간 안에서 자른 짧은 창을 넘기는데, 거기서 또 "가장 긴 구간"을
        # 골라내면 창이 더 짧아져 임베딩이 흔들린다.
        embedding = self.extract_embedding(self._dominant_speech_region(audio))

        if not self._profiles:
            if not update_profile:
                # 아직 아는 화자가 없는데 등록도 못 하는 상황 — 판정 불가.
                # 호출부가 "화자 미정"으로 처리하도록 빈 문자열 대신 None을 준다.
                return None
            # 사전 등록도 없고 첫 화자도 없음 → 무조건 첫 화자로 등록
            new_label = f"SPEAKER_{self._next_speaker_num}"
            self._next_speaker_num += 1
            self._profiles[new_label] = embedding
            logger.info(f"🆕 새 화자 등록: {new_label} (첫 화자)")
            return new_label

        if self._closed_set:
            # 참석자를 아는 회의 — 절대 점수가 아니라 순위+margin으로 판정한다.
            # (근거는 match_closed_set 참고. 절대 문턱은 정답까지 걷어냈다.)
            name, nearest, best_score, margin = self.match_closed_set(embedding)
            # 로그는 확정 경로에서만 남긴다. 잠정 자막은 1초마다 이 함수를 부르므로
            # 여기서 로그를 찍으면 회의당 수백 줄이 쌓여 정작 필요한 기록이 묻힌다.
            if name is None:
                if update_profile:
                    reason = (
                        f"유사도 {best_score:.2f} < 바닥 {SPEAKER_ABSOLUTE_FLOOR} (명단 밖으로 판단)"
                        if best_score < SPEAKER_ABSOLUTE_FLOOR
                        else f"1·2등 차이 {margin:.3f} < 하한 {SPEAKER_MIN_MARGIN}"
                    )
                    logger.info(f"🤷 화자 미상 — {reason} (최근접: {nearest})")
                return None
            # 프로필 갱신(이동 평균)은 유사도가 충분히 높을 때만 — 겹쳐 말한 구간 등이
            # 잘못 배정됐을 때 엉뚱한 사람의 목소리 지문을 조금씩 오염시키는 걸 방지.
            # 여기는 절대 점수가 맞는 기준이다: "이 오디오를 지문에 섞어도 되나"를 묻는 것이라
            # 순위와 무관하게 충분히 닮았어야 한다.
            if update_profile:
                if best_score >= self.similarity_threshold:
                    self._profiles[name] = 0.9 * self._profiles[name] + 0.1 * embedding
                logger.info(
                    f"🗣️ 화자 매칭(사전등록): {name} "
                    f"(유사도 {best_score:.2f}, 2등과 {margin:.3f} 차이)"
                )
            return name

        best_label, best_score = self._find_best_match(embedding)

        if not update_profile:
            # 읽기 전용(열린 집합) — 새 화자를 만들지 않으므로 잠정 자막에 유령 화자가
            # 등장하지 않는다. 하한은 확정 경로와 동일하게 적용한다 — 잠정에서만 이름이
            # 뜨다가 확정에서 사라지면 화면이 더 혼란스럽다.
            if best_score < SPEAKER_MIN_ASSIGN_SIMILARITY:
                return None
            return best_label if best_score >= self.similarity_threshold else None

        if best_score >= self.similarity_threshold:
            self._profiles[best_label] = 0.9 * self._profiles[best_label] + 0.1 * embedding
            logger.info(f"🗣️ 화자 매칭: {best_label} (유사도 {best_score:.2f})")
            return best_label

        # 열린 집합이어도 화자 수는 무한정 늘 수 없다. 상한에 닿으면 새로 만들지 않고
        # 가장 가까운 기존 화자에 배정 — 상한이 없으면 판정이 한 번 흔들릴 때마다
        # 화자가 계속 늘어나 회의록이 유령 화자로 뒤덮인다(실측에서 SPEAKER_4까지 생김).
        # 이 경우 프로필은 갱신하지 않는다(확신이 없는 배정이라 지문을 오염시키면 안 됨).
        if len(self._profiles) >= self._max_speakers:
            logger.info(
                f"🗣️ 화자 매칭(상한 {self._max_speakers}명 도달, 최근접 배정): "
                f"{best_label} (유사도 {best_score:.2f})"
            )
            return best_label

        new_label = f"SPEAKER_{self._next_speaker_num}"
        self._next_speaker_num += 1
        self._profiles[new_label] = embedding
        logger.info(f"🆕 새 화자 등록: {new_label} (기존 최고 유사도 {best_score:.2f})")
        return new_label
