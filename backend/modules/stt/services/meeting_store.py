import json
import os
import shutil
import time
import wave
from datetime import datetime, timezone

import numpy as np

from ..core.config import logger, MEETINGS_DIR, REALTIME_SAMPLE_RATE

# transcript.json은 매 청크가 아니라 N청크마다 갱신 — 세그먼트가 쌓일수록 파일 전체를
# 다시 쓰는 비용이 커지고(누적 O(n²)), 저장소가 NAS(네트워크 마운트)라 더 느리기 때문.
# 서버가 도중에 죽으면 최대 N-1청크 분량의 JSON이 유실될 수 있지만, WAV에는 오디오가
# 남아있어 재분석으로 복구 가능하므로 허용 가능한 트레이드오프.
_JSON_SAVE_EVERY_N_CHUNKS = 5


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

    def __init__(self, session_id: str, speaker_mode: str, mixed_audio: bool = False):
        """
        mixed_audio=True: "각자 PC" 모드용 — 여러 참가자가 각자 보내는 오디오를
        "회의 시작 시각 기준 절대 위치"에 맞춰 메모리에서 합산(믹싱)하다가, 회의
        종료 시 한 번에 파일로 씀. 공용 마이크 모드(mixed_audio=False, 기본값)처럼
        스트림이 하나뿐이면 겹칠 일이 없어, 메모리 효율이 좋은 스트리밍 append 방식을
        그대로 씀(청크 도착 즉시 디스크에 씀 — 회의가 길어져도 메모리에 안 쌓임).
        """
        self.session_id = session_id
        self.mixed_audio = mixed_audio
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
            "speaker_mode": speaker_mode,  # enrolled(사전등록) | auto(자동감지) | group(각자 PC)
            "refined": False,              # C-4 정밀 재분석 완료 여부 (후속 작업에서 사용)
            "audio_file": "audio.wav",
            "segments": [],
        }

        # 참가자가 회의 시작 후 몇 초에 합류했는지 계산하는 기준 시각(단조 시계 —
        # 시스템 시각 변경/타임존 영향을 안 받아 오디오 위치 계산에 더 안전함)
        self.start_monotonic = time.monotonic()

        self._wav = None
        self._mix_buffer: np.ndarray | None = None
        if mixed_audio:
            self._mix_buffer = np.zeros(0, dtype=np.float32)
        else:
            self._wav = wave.open(os.path.join(self.dir, "audio.wav"), "wb")
            self._wav.setnchannels(1)
            self._wav.setsampwidth(2)
            self._wav.setframerate(REALTIME_SAMPLE_RATE)
        self._finalized = False
        self._chunks_since_json_save = 0
        self._save_json()
        logger.info(f"💾 회의 기록 시작: {self.meeting_id} (믹싱 모드={mixed_audio})")

    @property
    def has_content(self) -> bool:
        """발화가 하나라도 기록됐는지 — 빈 세션엔 재분석을 걸지 않기 위한 판단용."""
        return len(self._meta["segments"]) > 0

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

    def add_chunk(self, audio: np.ndarray, segments: list[dict], absolute_offset_sec: float | None = None) -> None:
        """
        확정된 청크 하나의 오디오와 세그먼트들을 저장. (블로킹 I/O — executor에서 호출할 것)
        absolute_offset_sec: 믹싱 모드에서 이 오디오를 회의 시작 기준 몇 초 지점에
        합산할지. 겹치는 구간은 파형을 더해서(mix) 동시 발화도 반영됨.
        """
        if self._finalized:
            return
        if self._mix_buffer is not None:
            start_sample = int((absolute_offset_sec or 0.0) * REALTIME_SAMPLE_RATE)
            end_sample = start_sample + len(audio)
            if end_sample > len(self._mix_buffer):
                self._mix_buffer = np.pad(self._mix_buffer, (0, end_sample - len(self._mix_buffer)))
            self._mix_buffer[start_sample:end_sample] += audio
        elif self._wav is not None:
            pcm16 = np.clip(audio * 32768.0, -32768, 32767).astype(np.int16)
            self._wav.writeframes(pcm16.tobytes())
        self._meta["segments"].extend(segments)
        self._meta["segments"].sort(key=lambda s: s.get("start", 0))
        self._chunks_since_json_save += 1
        if self._chunks_since_json_save >= _JSON_SAVE_EVERY_N_CHUNKS:
            self._save_json()
            self._chunks_since_json_save = 0

    def rename_speaker(self, old_name: str, new_name: str) -> bool:
        """
        회의 도중 화자 이름이 수정됐을 때, 이미 저장된 과거 세그먼트와
        C-4 재분석용 프로필 스냅샷(profiles.npz)까지 새 이름으로 갱신.
        이게 없으면 rename 이후의 자막만 새 이름이고, 회의록 앞부분과
        정밀 재분석 결과는 옛 이름으로 남아 한 회의 안에서 이름이 섞임.
        (블로킹 I/O — executor에서 호출할 것)
        """
        if self._finalized:
            return False
        changed = False

        for seg in self._meta["segments"]:
            if seg.get("speaker") == old_name:
                seg["speaker"] = new_name
                changed = True

        npz_path = os.path.join(self.dir, "profiles.npz")
        if os.path.isfile(npz_path):
            npz = np.load(npz_path)
            data = {name: npz[name] for name in npz.files}
            if old_name in data and new_name not in data:
                data[new_name] = data.pop(old_name)
                np.savez(npz_path, **data)
                changed = True

        if changed:
            self._save_json()
            logger.info(f"✏️ 회의록 화자 이름 갱신: {self.meeting_id}, {old_name} → {new_name}")
        return changed

    def finalize(self, status: str) -> None:
        """회의 종료 처리. 여러 번 불려도 첫 호출만 유효 (정상 종료 후 finally 중복 호출 대비)."""
        if self._finalized:
            return
        self._finalized = True
        if self._wav is not None:
            self._wav.close()
        elif self._mix_buffer is not None and len(self._mix_buffer) > 0:
            # 스트리밍 append 없이 메모리에 모아뒀던 믹싱 결과를 한 번에 파일로 씀
            with wave.open(os.path.join(self.dir, "audio.wav"), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(REALTIME_SAMPLE_RATE)
                pcm16 = np.clip(self._mix_buffer * 32768.0, -32768, 32767).astype(np.int16)
                wf.writeframes(pcm16.tobytes())

        if not self._meta["segments"]:
            # 접속만 하고 발화 없이 끝난 세션 — 빈 회의 폴더가 계속 쌓이지 않게 정리
            shutil.rmtree(self.dir, ignore_errors=True)
            logger.info(f"🧹 발화 없는 회의 기록 폐기: {self.meeting_id}")
            return

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
