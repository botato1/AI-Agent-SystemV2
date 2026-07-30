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
    CONF_AVG_LOGPROB_THRESHOLD,
    CONF_NO_SPEECH_THRESHOLD,
    MIN_SPEAKERS,
    build_context_hint,
)
from .diarize_service import run_diarization
from .speaker_id_service import LiveSpeakerIdentifier

# 정밀 재분석은 전체 회의 오디오를 다시 돌리는 무거운 GPU 작업이라 동시에 하나만 수행
# (진행 중인 다른 회의의 실시간 처리와 executor 스레드를 나눠 쓰므로 과부하 방지)
_refine_lock = asyncio.Lock()

MIN_REFINE_AUDIO_SEC = 1.0   # 이보다 짧은 회의는 재분석 의미 없음
MIN_MAP_SIMILARITY = 0.3     # 등록 이름 매핑 최소 유사도 (미달이면 익명 라벨 유지)
MAX_EMBED_SEC = 10           # 화자당 임베딩 추출에 쓸 최대 오디오 길이
MAX_TURN_GAP_SEC = 1.0       # 같은 화자의 인접 발화를 한 턴으로 합치는 최대 침묵 간격
# "네", "네?" 같은 짧은 대꾸도 보통 0.3초 미만이라, 길이만으로 필터링하면 호흡/잡음뿐
# 아니라 실제 짧은 발화까지 통째로 사라짐 — 그래서 길이로 미리 거르지 않고, 아주
# 짧은(0.05초 미만, 배열 인덱싱만 방어) 것만 걸러내고 나머지는 실제로 전사를 시도해
# VAD/빈 텍스트 여부로 판단한다(잡음이면 전사 결과가 비어서 자연스럽게 걸러짐).
MIN_TURN_SEC = 0.05


async def refine_meeting(meeting_id: str, app_state) -> dict | None:
    """
    회의 후 정밀 재분석 (C-4의 STT 파트).

    실시간 처리는 청크 단위라 화자 오배정/청크 경계 부정확이 생길 수 있는데,
    저장된 전체 오디오를 "화자 턴 단위"로 다시 분석해서 보정한다:
      1. 전체 오디오에 화자분리 → 누가 언제 말했는지 턴(turn) 목록 확보
      2. 각 턴의 오디오만 잘라 정밀 전사 → 화자 경계와 텍스트가 정확히 일치
    (전사 먼저 하고 화자를 나중에 겹침으로 배정하는 방식은, transformers 엔진처럼
     전사 세그먼트가 30초 창 단위로 나올 때 여러 화자가 한 덩어리로 뭉개지는 문제가 있어
     턴 단위 전사로 재설계함. 턴 수만큼 전사 호출이 늘어 느리지만 백그라운드 작업이라 허용.)

    결과 세그먼트 스키마는 실시간과 동일한 공통 계약을 따름:
      {start, end, text, speaker, confident, user_edited}
    transcript.json의 segments를 교체하고(실시간 결과는 realtime_segments로 보존),
    refined=true로 표시 — 모순 감지 배치 재검사(C-4의 Qwen 파트)는 이걸 입력으로 쓰면 됨.

    회의 종료 시 백그라운드로 자동 실행되며, 실패해도 실시간 회의록은 그대로 남는다.
    """
    async with _refine_lock:
        try:
            return await _refine(meeting_id, app_state)
        except Exception:
            logger.exception(f"❌ [{meeting_id}] 정밀 재분석 실패 — 실시간 회의록은 유지됨")
            return None


def _merge_adjacent_turns(tracks: list[dict]) -> list[dict]:
    """같은 화자의 인접 발화 구간(짧은 침묵 포함)을 하나의 턴으로 병합해 전사 호출 수를 줄임."""
    merged: list[dict] = []
    for track in sorted(tracks, key=lambda t: t["start"]):
        if (
            merged
            and merged[-1]["speaker"] == track["speaker"]
            and track["start"] - merged[-1]["end"] <= MAX_TURN_GAP_SEC
        ):
            merged[-1]["end"] = max(merged[-1]["end"], track["end"])
        else:
            merged.append(dict(track))
    return merged


async def _transcribe_turns(
    app_state, meeting_id: str, turns: list[dict],
    audio_of: "callable", initial_prompt: str | None,
) -> list[dict]:
    """
    화자 턴 목록을 받아 각 턴의 오디오만 잘라 정밀 전사한다.

    audio_of(turn) -> (오디오 배열, 샘플레이트): 턴이 어느 오디오에서 나왔는지는
    호출부가 결정한다(공용 마이크는 회의 오디오 하나, 각자 PC는 화자별 트랙).
    """
    loop = asyncio.get_event_loop()

    def _transcribe_clip(clip: np.ndarray) -> list:
        segments, _info = app_state.stt_model.transcribe(
            clip,
            language=WHISPER_LANGUAGE,
            beam_size=PRECISE_BEAM_SIZE,
            vad_filter=True,
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,
        )
        return list(segments)

    refined: list[dict] = []
    for i, turn in enumerate(turns, 1):
        start, end = turn["start"], turn["end"]
        if end - start < MIN_TURN_SEC:
            continue
        audio, sample_rate = audio_of(turn)
        if audio is None:
            continue
        clip = audio[int(start * sample_rate): int(end * sample_rate)]
        if len(clip) == 0:
            continue

        engine_segments = await loop.run_in_executor(None, _transcribe_clip, clip)
        text = " ".join(seg.text.strip() for seg in engine_segments).strip()
        if not text:
            continue

        refined.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "text": text,
            "speaker": turn["speaker"],
            "confident": all(
                seg.avg_logprob >= CONF_AVG_LOGPROB_THRESHOLD
                and seg.no_speech_prob <= CONF_NO_SPEECH_THRESHOLD
                for seg in engine_segments
            ),
            "user_edited": False,
        })
        if i % 20 == 0:
            logger.info(f"🔬 [{meeting_id}] 턴 전사 진행 {i}/{len(turns)}")
    return refined


async def _refine_group(meeting_id, meeting_dir, meta, meta_path, app_state) -> dict:
    """
    "각자 PC" 모드 재분석 — 화자분리 없이 전사만 다시 돌린다.

    화자는 이미 확정돼 있으므로, 실시간 세그먼트의 시간·화자 정보를 턴으로 재사용하고
    **참가자별 트랙**에서 오디오를 잘라 정밀 모델로 다시 전사한다.
    믹스본(audio.wav)을 쓰면 안 되는 이유: 여러 목소리가 겹쳐 있어서, 각자의 깨끗한
    스트림으로 뽑은 실시간 결과보다 오히려 나빠질 수 있다.

    트랙이 없는 회의(이 기능 이전에 녹음된 것)는 재전사를 건너뛴다.
    """
    tracks_meta = meta.get("speaker_tracks") or {}
    if not tracks_meta:
        logger.info(f"↩️ [{meeting_id}] 각자 PC 모드 — 참가자별 트랙이 없어 재전사 생략(옛 회의)")
        meta["refined"] = True
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta

    # 화자별 트랙을 미리 한 번씩만 읽어둔다 (턴마다 파일을 여는 건 낭비)
    tracks: dict[str, tuple] = {}
    for speaker, filename in tracks_meta.items():
        path = os.path.join(meeting_dir, filename)
        if not os.path.isfile(path):
            logger.warning(f"⚠️ [{meeting_id}] 트랙 파일 없음: {filename} — 이 화자는 실시간 결과 유지")
            continue
        audio, sample_rate = sf.read(path, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        tracks[speaker] = (audio, sample_rate)

    realtime_segments = meta.get("segments", [])
    turns = _merge_adjacent_turns([
        {"start": s["start"], "end": s["end"], "speaker": s.get("speaker")}
        for s in realtime_segments if s.get("speaker") in tracks
    ])
    if not turns:
        logger.info(f"↩️ [{meeting_id}] 각자 PC 모드 — 재전사할 턴이 없음")
        meta["refined"] = True
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta

    logger.info(f"🔬 [{meeting_id}] 각자 PC 모드 재전사 시작 (화자 {len(tracks)}명 / 턴 {len(turns)}개)")
    refined_segments = await _transcribe_turns(
        app_state, meeting_id, turns,
        audio_of=lambda t: tracks.get(t["speaker"], (None, REALTIME_SAMPLE_RATE)),
        initial_prompt=build_context_hint(list(tracks.keys())),
    )
    refined_segments.sort(key=lambda s: s["start"])

    meta["realtime_segments"] = realtime_segments
    meta["segments"] = refined_segments
    meta["refined"] = True
    meta["refined_at"] = datetime.now(timezone.utc).isoformat()
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    logger.info(f"✅ [{meeting_id}] 각자 PC 모드 재전사 완료 (segments={len(refined_segments)})")
    return meta


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
    if meta.get("speaker_mode") == "group":
        # "각자 PC" 모드 — 참가자가 이미 자기 이름으로 접속해 화자가 확정돼 있으므로
        # pyannote 화자분리는 돌리지 않는다(익명 라벨로 덮어쓰면 정확한 정보가 퇴화).
        # 대신 참가자별 트랙으로 전사만 다시 돌려 텍스트 품질을 끌어올린다 —
        # 실시간은 빠른 모델(turbo)로 뽑은 잠정본이기 때문.
        return await _refine_group(meeting_id, meeting_dir, meta, meta_path, app_state)

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

    # 1. 전체 화자분리 — 파일 경로 대신 메모리 오디오를 넘김 (서버 FFmpeg 부재로 파일 디코딩 불가)
    #
    # 사전 등록 프로필이 있으면 등록 인원이 곧 회의 참석자(닫힌 집합)이므로 화자 수 상한을
    # 그 인원으로 좁혀준다 — 범위가 좁을수록 클러스터링이 흔들릴 여지가 줄어든다.
    # 하한(MIN_SPEAKERS)까지 인원수로 올리지는 않는다: 등록만 하고 한 마디도 안 한 참석자가
    # 있으면 없는 화자를 억지로 만들어내게 되기 때문.
    profiles_path = os.path.join(meeting_dir, "profiles.npz")
    enrolled_count = len(np.load(profiles_path).files) if os.path.isfile(profiles_path) else 0
    waveform = {"waveform": torch.from_numpy(audio.reshape(1, -1)), "sample_rate": sample_rate}
    diarization_tracks = await run_diarization(
        app_state.diarize_pipeline,
        waveform,
        max_speakers=enrolled_count if enrolled_count >= MIN_SPEAKERS else None,
    )
    turns = _merge_adjacent_turns(diarization_tracks)
    logger.info(f"🔬 [{meeting_id}] 화자 턴 {len(diarization_tracks)}개 → 병합 후 {len(turns)}개, 턴별 전사 시작")

    # 2. 턴별 정밀 전사 (각자 PC 모드와 같은 헬퍼를 씀 — 차이는 오디오 출처뿐)
    # 최종 회의록이 되는 경로라 인식 힌트를 여기에도 적용한다. 등록 프로필이 있으면
    # 그 이름들이 곧 참석자이므로 힌트에 넣고, 없으면 용어만 들어간다.
    enrolled_names = list(np.load(profiles_path).files) if enrolled_count else []
    refined_segments = await _transcribe_turns(
        app_state, meeting_id, turns,
        audio_of=lambda _turn: (audio, sample_rate),  # 공용 마이크는 회의 오디오 하나뿐
        initial_prompt=build_context_hint(enrolled_names),
    )

    # 3. 사전 등록 프로필이 있으면 익명 라벨(SPEAKER_00 등) → 실제 이름으로 매핑
    if enrolled_count:
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
