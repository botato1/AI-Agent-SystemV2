import asyncio
import json
import os
from datetime import datetime, timezone

import numpy as np
import soundfile as sf
import torch

from ..core.config import (
    logger,
    MEETINGS_DIR,
    WHISPER_LANGUAGE,
    PRECISE_BEAM_SIZE,
    REALTIME_SAMPLE_RATE,
)
from .diarize_service import run_diarization
from .pipeline import merge_transcript_with_diarization
from .speaker_id_service import LiveSpeakerIdentifier

# 정밀 재분석은 전체 회의 오디오를 다시 돌리는 무거운 GPU 작업이라 동시에 하나만 수행
# (진행 중인 다른 회의의 실시간 처리와 executor 스레드를 나눠 쓰므로 과부하 방지)
_refine_lock = asyncio.Lock()

MIN_REFINE_AUDIO_SEC = 1.0   # 이보다 짧은 회의는 재분석 의미 없음
MIN_MAP_SIMILARITY = 0.3     # 등록 이름 매핑 최소 유사도 (미달이면 익명 라벨 유지)
MAX_EMBED_SEC = 10           # 화자당 임베딩 추출에 쓸 최대 오디오 길이


async def refine_meeting(meeting_id: str, app_state) -> dict | None:
    """
    회의 후 정밀 재분석 (C-4의 STT 파트).
    실시간 처리는 청크 단위라 화자 오배정/청크 경계 부정확이 생길 수 있는데,
    저장된 전체 오디오를 정밀 전사 + 전체 화자분리로 다시 분석해서 보정한다.
    결과는 transcript.json의 segments를 교체하고(실시간 결과는 realtime_segments로 보존),
    refined=true로 표시 — 모순 감지 배치 재검사(C-4의 Qwen 파트)는 이걸 입력으로 쓰면 됨.

    회의 종료 시 백그라운드로 자동 실행되며, 실패해도 실시간 회의록은 그대로 남는다.
    """
    async with _refine_lock:
        try:
            return await _refine(meeting_id, app_state)
        except Exception:
            logger.exception(f"❌ [{meeting_id}] 정밀 재분석 실패 — 실시간 회의록은 유지됨")
            return None


async def _refine(meeting_id: str, app_state) -> dict | None:
    meeting_dir = os.path.join(MEETINGS_DIR, meeting_id)
    meta_path = os.path.join(meeting_dir, "transcript.json")
    if not os.path.isfile(meta_path):
        logger.warning(f"⚠️ [{meeting_id}] 재분석 대상 회의록 없음")
        return None

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("refined"):
        logger.info(f"↩️ [{meeting_id}] 이미 재분석 완료된 회의 — 건너뜀")
        return meta

    wav_path = os.path.join(meeting_dir, meta.get("audio_file", "audio.wav"))
    audio, sample_rate = sf.read(wav_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    duration_sec = len(audio) / sample_rate
    if duration_sec < MIN_REFINE_AUDIO_SEC:
        logger.info(f"↩️ [{meeting_id}] 오디오가 너무 짧아 재분석 생략 ({duration_sec:.1f}s)")
        return meta

    logger.info(f"🔬 [{meeting_id}] 정밀 재분석 시작 (오디오 {duration_sec:.0f}초)")
    loop = asyncio.get_event_loop()

    # 정밀 전사 (전체 오디오, 청크 경계 없음)
    def _transcribe() -> list[dict]:
        segments, _info = app_state.stt_model.transcribe(
            audio,
            language=WHISPER_LANGUAGE,
            beam_size=PRECISE_BEAM_SIZE,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return [
            {"start": round(seg.start, 2), "end": round(seg.end, 2), "text": seg.text.strip()}
            for seg in segments
        ]

    # 전체 화자분리 — 파일 경로 대신 메모리 오디오를 넘김 (서버 FFmpeg 부재로 파일 디코딩 불가)
    waveform = {"waveform": torch.from_numpy(audio.reshape(1, -1)), "sample_rate": sample_rate}

    whisper_segments, diarization_tracks = await asyncio.gather(
        loop.run_in_executor(None, _transcribe),
        run_diarization(app_state.diarize_pipeline, waveform),
    )

    refined_segments = merge_transcript_with_diarization(whisper_segments, diarization_tracks)

    # 사전 등록 프로필이 있으면 익명 라벨(SPEAKER_00 등) → 실제 이름으로 매핑
    profiles_path = os.path.join(meeting_dir, "profiles.npz")
    if os.path.isfile(profiles_path):
        refined_segments = await loop.run_in_executor(
            None, _map_speaker_names,
            refined_segments, audio, profiles_path, app_state.speaker_embedding_inference,
        )

    # 실시간 결과는 비교/디버깅용으로 보존하고 segments를 정밀본으로 교체
    meta["realtime_segments"] = meta.get("segments", [])
    meta["segments"] = refined_segments
    meta["refined"] = True
    meta["refined_at"] = datetime.now(timezone.utc).isoformat()
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    logger.info(f"✅ [{meeting_id}] 정밀 재분석 완료 (segments={len(refined_segments)})")
    return meta


def _map_speaker_names(segments: list[dict], audio: np.ndarray, profiles_path: str, inference) -> list[dict]:
    """
    화자분리의 익명 라벨을 사전 등록된 실제 이름으로 매핑.
    각 익명 화자의 발화 구간에서 임베딩을 뽑아 등록 프로필과 코사인 유사도를 재고,
    유사도 높은 순으로 1:1 매칭 (같은 이름이 두 화자에게 배정되지 않게).
    """
    data = np.load(profiles_path)
    profiles = {name: data[name] for name in data.files}
    if not profiles:
        return segments

    identifier = LiveSpeakerIdentifier(inference)  # 임베딩 추출 기능만 재사용

    # 익명 화자별로 발화 구간 오디오를 모아 임베딩 추출 (화자당 최대 MAX_EMBED_SEC초)
    spans_by_speaker: dict[str, list] = {}
    for seg in segments:
        spans_by_speaker.setdefault(seg["speaker"], []).append((seg["start"], seg["end"]))

    candidates = []  # (유사도, 익명라벨, 등록이름)
    for label, spans in spans_by_speaker.items():
        clips, total_sec = [], 0.0
        for start, end in spans:
            if total_sec >= MAX_EMBED_SEC:
                break
            clip = audio[int(start * REALTIME_SAMPLE_RATE): int(end * REALTIME_SAMPLE_RATE)]
            if len(clip) == 0:
                continue
            clips.append(clip)
            total_sec += end - start
        if not clips:
            continue
        embedding = identifier.extract_embedding(np.concatenate(clips))
        for name, profile in profiles.items():
            score = LiveSpeakerIdentifier._cosine_similarity(embedding, profile)
            candidates.append((score, label, name))

    # 유사도 높은 순 1:1 배정
    candidates.sort(key=lambda x: x[0], reverse=True)
    mapping: dict[str, str] = {}
    used_names: set[str] = set()
    for score, label, name in candidates:
        if label in mapping or name in used_names or score < MIN_MAP_SIMILARITY:
            continue
        mapping[label] = name
        used_names.add(name)
        logger.info(f"🔗 화자 매핑: {label} → {name} (유사도 {score:.2f})")

    for seg in segments:
        seg["speaker"] = mapping.get(seg["speaker"], seg["speaker"])
    return segments
