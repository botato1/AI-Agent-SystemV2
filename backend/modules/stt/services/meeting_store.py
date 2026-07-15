import json
import os
import wave
from datetime import datetime, timezone

import numpy as np

from ..core.config import logger, MEETINGS_DIR, REALTIME_SAMPLE_RATE


class MeetingRecord:
    """
    실시간 회의 세션 하나의 오디오와 전사 결과를 디스크에 누적 저장.

    목적:
    - 회의가 끝나도 회의록이 서버에 남게 함 (이전까진 클라이언트로 스트리밍만 하고 소멸됐음)
    - C-4(회의 후 정밀 재분석)가 사용할 전체 오디오 원본 확보
    - 연결이 예기치 않게 끊겨도(터널 불안정 등) 그 직전까지의 기록은 보존

    저장 구조: {MEETINGS_DIR}/{meeting_id}/
      - audio.wav        회의 전체 오디오 (16kHz mono PCM16). 청크가 확정될 때마다 append.
      - transcript.json  전사 결과 + 메타데이터. 청크마다 갱신 저장 — 서버가 도중에
                         죽어도 직전 청크까지는 보존됨 (WAV 헤더는 finalize 시 확정되므로
                         비정상 종료 시 audio.wav 헤더가 깨질 수 있는 건 알려진 한계).
    """

    def __init__(self, session_id: str, speaker_mode: str):
        self.session_id = session_id
        started = datetime.now(timezone.utc)
        # 같은 session_id로 회의를 여러 번 열 수 있으므로 시작 시각을 붙여 회의를 구분
        self.meeting_id = f"{session_id}_{started.strftime('%Y%m%d-%H%M%S')}"
        self.dir = os.path.join(MEETINGS_DIR, self.meeting_id)
        os.makedirs(self.dir, exist_ok=True)

        self._meta = {
            "meeting_id": self.meeting_id,
            "session_id": session_id,
            "started_at": started.isoformat(),
            "ended_at": None,
            "status": "recording",        # recording | completed | disconnected
            "speaker_mode": speaker_mode,  # enrolled(사전등록) | auto(자동감지)
            "refined": False,              # C-4 정밀 재분석 완료 여부 (후속 작업에서 사용)
            "audio_file": "audio.wav",
            "segments": [],
        }

        self._wav = wave.open(os.path.join(self.dir, "audio.wav"), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(REALTIME_SAMPLE_RATE)
        self._finalized = False
        self._save_json()
        logger.info(f"💾 회의 기록 시작: {self.meeting_id}")

    def save_profiles(self, profiles: dict) -> None:
        """
        사전 등록된 화자 프로필(이름→임베딩)을 회의 폴더에 저장.
        회의 후 정밀 재분석(C-4)이 pyannote의 익명 라벨(SPEAKER_00 등)을
        실제 이름으로 매핑할 때 사용 — 회의가 끝나면 enrolled_profiles가
        메모리에서 정리되므로 디스크에 남겨둬야 함.
        """
        if not profiles:
            return
        np.savez(os.path.join(self.dir, "profiles.npz"), **profiles)

    def add_chunk(self, audio: np.ndarray, segments: list[dict]) -> None:
        """확정된 청크 하나의 오디오와 세그먼트들을 저장."""
        if self._finalized:
            return
        pcm16 = np.clip(audio * 32768.0, -32768, 32767).astype(np.int16)
        self._wav.writeframes(pcm16.tobytes())
        self._meta["segments"].extend(segments)
        self._save_json()

    def finalize(self, status: str) -> None:
        """회의 종료 처리. 여러 번 불려도 첫 호출만 유효 (정상 종료 후 finally 중복 호출 대비)."""
        if self._finalized:
            return
        self._finalized = True
        self._wav.close()
        self._meta["status"] = status
        self._meta["ended_at"] = datetime.now(timezone.utc).isoformat()
        self._save_json()
        logger.info(
            f"💾 회의록 저장 완료: {self.meeting_id} "
            f"(status={status}, segments={len(self._meta['segments'])})"
        )

    def _save_json(self) -> None:
        path = os.path.join(self.dir, "transcript.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._meta, f, ensure_ascii=False, indent=2)
