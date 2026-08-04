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
    is_confident,
    MIN_SPEAKERS,
    build_context_hint,
)
from .diarize_service import run_diarization
from .refine_webhook import notify_refine_done
from .speaker_id_service import LiveSpeakerIdentifier

# 정밀 재분석은 전체 회의 오디오를 다시 돌리는 무거운 GPU 작업이라 동시에 하나만 수행
# (진행 중인 다른 회의의 실시간 처리와 executor 스레드를 나눠 쓰므로 과부하 방지)
_refine_lock = asyncio.Lock()

MIN_REFINE_AUDIO_SEC = 1.0   # 이보다 짧은 회의는 재분석 의미 없음
# (구 클러스터 단위 매핑에서 쓰던 값 — 턴별 판정으로 바꾸면서 제거.
#  지금은 config.SPEAKER_MIN_ASSIGN_SIMILARITY 하나로 실시간·재분석이 같은 기준을 쓴다)
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

    완료(또는 실패) 후 REFINE_WEBHOOK_URL이 설정돼 있으면 소비자에게 통지한다 —
    이 함수는 백그라운드 태스크로 던져지므로 호출부가 완료를 알 방법이 없기 때문.
    """
    async with _refine_lock:
        try:
            meta = await _refine(meeting_id, app_state)
        except Exception:
            logger.exception(f"❌ [{meeting_id}] 정밀 재분석 실패 — 실시간 회의록은 유지됨")
            # 실패도 통지한다. 성공만 알리면 소비자가 무한정 기다리게 된다.
            await notify_refine_done(
                meeting_id, _session_id_of(meeting_id),
                refined_at=None, segment_count=0, status="failed",
            )
            return None

        if meta is None:
            # 회의록 파일이 없는 경우 등 — 재분석할 대상 자체가 없었다.
            await notify_refine_done(
                meeting_id, _session_id_of(meeting_id),
                refined_at=None, segment_count=0, status="failed",
            )
            return None

        # 이미 재분석돼 있어 건너뛴 경우(refined_at이 이번 실행에서 갱신되지 않음)에는
        # 통지하지 않는다 — 새로 생긴 이벤트가 아니라 중복 알림이 된다.
        if meta.get("_refine_skipped"):
            meta.pop("_refine_skipped", None)
            return meta

        await notify_refine_done(
            meeting_id,
            meta.get("session_id"),
            refined_at=meta.get("refined_at"),
            segment_count=len(meta.get("segments") or []),
            status="refined",
        )
        return meta


def _session_id_of(meeting_id: str) -> str | None:
    """
    예외 경로에서 meta를 못 읽었을 때만 쓰는 폴백 — meeting_id는
    "{session_id}_{timestamp}" 형태라 마지막 밑줄 앞이 session_id다.
    정상 경로에서는 meta["session_id"]를 그대로 쓴다(포맷 파싱에 의존하지 않도록).
    """
    return meeting_id.rsplit("_", 1)[0] or None


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
            # 턴 하나가 여러 엔진 세그먼트로 쪼개질 수 있으므로, 하나라도 신뢰도가
            # 낮으면 턴 전체를 저신뢰로 본다(보수적 판정).
            "confident": all(
                is_confident(getattr(seg, "avg_logprob", None), getattr(seg, "no_speech_prob", None))
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
        # refined=True인데 refined_at이 없으면 완료 웹훅 계약이 어긋난다
        meta["refined_at"] = datetime.now(timezone.utc).isoformat()
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
        # refined=True인데 refined_at이 없으면 완료 웹훅 계약이 어긋난다
        meta["refined_at"] = datetime.now(timezone.utc).isoformat()
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta

    logger.info(f"🔬 [{meeting_id}] 각자 PC 모드 재전사 시작 (화자 {len(tracks)}명 / 턴 {len(turns)}개)")
    refined_segments = await _transcribe_turns(
        app_state, meeting_id, turns,
        audio_of=lambda t: tracks.get(t["speaker"], (None, REALTIME_SAMPLE_RATE)),
        initial_prompt=build_context_hint(list(tracks.keys()), session_id=meta.get("session_id")),
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
        # 호출부가 완료 웹훅을 중복 발송하지 않도록 표시 (응답에는 남지 않는 내부 플래그)
        meta["_refine_skipped"] = True
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
        initial_prompt=build_context_hint(enrolled_names, session_id=meta.get("session_id")),
    )

    # 3. 사전 등록 프로필이 있으면 익명 라벨(SPEAKER_00 등) → 실제 이름으로 교체
    if enrolled_count:
        refined_segments = await loop.run_in_executor(
            None, _identify_turn_speakers,
            refined_segments, audio, sample_rate, profiles_path,
            app_state.speaker_embedding_inference,
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


def _identify_turn_speakers(
    segments: list[dict], audio: np.ndarray, sample_rate: int, profiles_path: str, inference
) -> list[dict]:
    """
    화자분리가 만든 익명 라벨을 버리고, **턴마다 목소리를 직접 판정**해 이름을 붙인다.

    왜 클러스터 단위 매핑을 그만뒀나 (2026-08-03 실측):
      예전에는 익명 화자(SPEAKER_00 등) 하나에 등록 이름 하나를 1:1로 매핑했다.
      그 방식은 pyannote가 **두 사람을 한 클러스터로 묶으면 그 발언 전부가 한 사람
      이름을 받는다.** 정답 대본이 있는 5인 모의 회의에서 실제로 그렇게 됐다 —
      김나연·이승주·이준오의 발언이 문지수로 몰리고, 매핑 실패한 클러스터는
      SPEAKER_01로 남았다. 같은 회의에서 실시간 경로는 문지수·김나연·가동현을
      정확히 맞혔다. **더 정확한 결과를 덜 정확한 것으로 덮어쓰고 있었다.**

    지금은 실시간과 같은 방식이다: 턴 오디오로 임베딩을 뽑아 등록 프로필과 비교하고,
    충분히 닮지 않으면 이름을 붙이지 않는다(speaker=None). 화자분리의 **경계**는
    그대로 쓴다 — 경계 잡기는 pyannote가 잘하고, 누구인지 판정은 등록 프로필 대조가
    낫다는 게 실측 결론이다.

    턴이 두 사람에 걸쳐 있으면 임베딩이 섞여 유사도가 낮게 나오고 미상이 된다.
    틀린 이름이 붙는 것보다 낫다.
    """
    data = np.load(profiles_path)
    profiles = {name: data[name] for name in data.files}
    if not profiles:
        return segments

    # 닫힌 집합으로 만들어 실시간과 동일한 판정 규칙을 태운다
    # (유사도 하한 미달이면 None — SPEAKER_MIN_ASSIGN_SIMILARITY)
    identifier = LiveSpeakerIdentifier(inference, initial_profiles=profiles)

    # 화자분리가 붙인 익명 라벨을 보관해둔다 — 아래에서 짧은 턴을 메우는 데 쓴다
    clusters = [seg.get("speaker") for seg in segments]

    assigned: dict[str, int] = {}
    for seg in segments:
        clip = audio[int(seg["start"] * sample_rate): int(seg["end"] * sample_rate)]
        if len(clip) < sample_rate:      # 1초 미만은 임베딩이 불안정 — 판정 포기
            seg["speaker"] = None
            continue
        # 프로필은 갱신하지 않는다 — 재분석은 사후 판정이라 지문을 건드릴 이유가 없고,
        # 잘못 배정된 턴이 지문을 오염시키면 이후 회의까지 영향을 받는다.
        name = identifier.identify(clip, update_profile=False)
        seg["speaker"] = name
        if name:
            assigned[name] = assigned.get(name, 0) + 1

    filled = _fill_unknown_from_clusters(segments, clusters)

    unknown = sum(1 for seg in segments if not seg.get("speaker"))
    logger.info(
        "🔗 턴별 화자 판정: " + (", ".join(f"{k} {v}개" for k, v in sorted(assigned.items())) or "확정 없음")
        + (f", 클러스터로 보완 {filled}개" if filled else "")
        + (f", 미상 {unknown}개" if unknown else "")
    )
    return segments


def _fill_unknown_from_clusters(segments: list[dict], clusters: list) -> int:
    """
    판정 못 한 턴을, 같은 화자분리 클러스터의 확정된 이름으로 메운다.

    왜 필요한가: 화자분리가 한 사람의 발언을 여러 조각으로 쪼개면(겹쳐 말한 "네" 하나가
    끼는 것만으로도 그렇게 된다) 조각이 짧아 목소리 판정이 안 된다. 실측에서 이준오의
    한 발언이 41.3 / 41.8 / 46.4초 세 조각으로 갈렸고, 긴 조각만 이름을 얻고 나머지는
    미상이 됐다.

    클러스터를 **주 근거로 쓰지 않는 이유**는 따로 있다 — 클러스터 하나에 이름 하나를
    1:1로 매핑하던 예전 방식은 pyannote가 두 사람을 한 클러스터로 묶었을 때 그 발언
    전부를 오배정했다. 그래서 판정은 턴별로 하고, 클러스터는 **빈칸을 메우는 보조**로만 쓴다.

    한 클러스터에서 서로 다른 이름이 확정됐으면 그 클러스터는 믿을 수 없다는 뜻이므로
    아무것도 메우지 않는다 — 잘못 묶인 클러스터가 오배정을 퍼뜨리는 걸 막는다.
    """
    names_by_cluster: dict = {}
    for seg, cluster in zip(segments, clusters):
        if cluster is None or not seg.get("speaker"):
            continue
        names_by_cluster.setdefault(cluster, set()).add(seg["speaker"])

    filled = 0
    for seg, cluster in zip(segments, clusters):
        if seg.get("speaker") or cluster is None:
            continue
        names = names_by_cluster.get(cluster)
        if names and len(names) == 1:   # 이름이 하나로 일치할 때만
            seg["speaker"] = next(iter(names))
            filled += 1
    return filled
