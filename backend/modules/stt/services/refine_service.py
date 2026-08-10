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
    REFINE_LLM_ENABLED,
    SEPARATION_ENABLED,
    OVERLAP_SEGMENT_RATIO,
)
from .diarize_service import run_diarization
from .overlap_detect import (
    find_overlap_spans_from_audio, mark_overlapped_segments, overlap_ratio,
)
from .overlap_model import load_overlap_inference
from .refine_webhook import notify_refine_done
from .speaker_timeline import build_speaker_timeline, split_turns_by_timeline
from .speech_separation import active_channels, separate_sources
from .transcript_correction import correct_transcript

# 정밀 재분석은 전체 회의 오디오를 다시 돌리는 무거운 GPU 작업이라 동시에 하나만 수행
# (진행 중인 다른 회의의 실시간 처리와 executor 스레드를 나눠 쓰므로 과부하 방지)
_refine_lock = asyncio.Lock()

MIN_REFINE_AUDIO_SEC = 1.0   # 이보다 짧은 회의는 재분석 의미 없음
MAX_TURN_GAP_SEC = 1.0       # 같은 화자의 인접 발화를 한 턴으로 합치는 최대 침묵 간격
# "네", "네?" 같은 짧은 대꾸도 보통 0.3초 미만이라, 길이만으로 필터링하면 호흡/잡음뿐
# 아니라 실제 짧은 발화까지 통째로 사라짐 — 그래서 길이로 미리 거르지 않고, 아주
# 짧은(0.05초 미만, 배열 인덱싱만 방어) 것만 걸러내고 나머지는 실제로 전사를 시도해
# VAD/빈 텍스트 여부로 판단한다(잡음이면 전사 결과가 비어서 자연스럽게 걸러짐).
MIN_TURN_SEC = 0.05
# 겹침을 걷어내고 남은 조각이 이보다 짧으면 버린다. 잘려나간 끄트머리는 말이 안 되는
# 소리 조각이라 전사해봐야 헛것이 나온다(MIN_TURN_SEC은 "원래 짧은 발화"를 살리기 위한
# 값이라 다르다 — 그건 온전한 턴이고, 이건 잘리고 남은 부스러기다).
MIN_TRIMMED_TURN_SEC = 0.4
# 전사에 넘길 때만 턴 앞뒤로 더 들려주는 여유.
#
# 왜 필요한가 (2026-08-07 실측): 화자 경계는 발화 경계와 정확히 일치하지 않는다.
# 같은 오디오·같은 모델인데 어디서 자르느냐만 달라도 결과가 뒤집혔다 —
# 회의 ded1105f의 "온보딩까지 넣으면"이 화자 경계(24.0~28.6초)로 자르면
# "원본인까지 넘는"이 됐고, 앞뒤로 1초씩 넓혀 자르면 정확히 나왔다.
# 실시간 경로(자르지 않음)는 같은 구간을 맞혔다 — 즉 오디오 문제가 아니라
# **우리가 말머리를 잘라 넘긴 것**이었다.
#
# 저장되는 start/end는 원래 턴 경계 그대로다. 여유는 모델에게 문맥을 더 들려줄
# 뿐이고, 여유 구간에만 걸친 전사 조각은 아래에서 버린다(옆 사람 말이 섞이는 것 방지).
# 앞뒤를 다르게 두는 이유 (2026-08-07 실측): 앞쪽 여유는 말머리를 되살렸지만
# (원본인→온보딩), 뒤쪽 여유는 **다음 화자의 말을 끌어왔다**("...확정하겠습니다. 네.").
# 관찰된 고장은 말머리 잘림이지 말꼬리가 아니었다 — 근거 없는 쪽은 0으로 둔다.
# 뒤쪽이 필요하다는 증거가 나오면 그때 올릴 것.
TURN_PAD_SEC = 0.3
TURN_PAD_TAIL_SEC = 0.0
# 전사 조각을 살릴 기준 — 조각 길이의 이만큼이 턴 본체와 겹쳐야 이 턴의 말로 본다.
# 절반으로 둔 이유: 경계에 걸친 말은 어느 쪽 것인지 애매한데, 더 많이 겹치는 쪽에
# 주는 게 자연스럽다. 문턱을 높이면 경계 단어가 양쪽에서 다 사라진다.
TURN_PAD_KEEP_RATIO = 0.5



async def refine_meeting(meeting_id: str, app_state, force: bool = False) -> dict | None:
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
            meta = await _refine(meeting_id, app_state, force=force)
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


def _free_pieces(start: float, end: float, occupied: list) -> list:
    """[start, end)에서 이미 차지된 구간을 뺀 나머지 조각들."""
    pieces, cursor = [], start
    for taken_start, taken_end in occupied:
        if taken_end <= cursor:
            continue
        if taken_start >= end:
            break
        if taken_start > cursor:
            pieces.append((cursor, taken_start))
        cursor = max(cursor, taken_end)
        if cursor >= end:
            break
    if cursor < end:
        pieces.append((cursor, end))
    return pieces


def _resolve_overlapping_turns(turns: list[dict]) -> list[dict]:
    """
    시간이 겹치는 턴들을 **겹치지 않게** 정리한다. 긴 턴이 우선이다.

    왜 필요한가 (2026-08-04 실측):
      화자분리는 시간이 겹치는 턴을 내놓을 수 있다. 그런데 공용 마이크 회의는
      **오디오가 하나뿐이라, 겹치는 두 턴이 같은 소리를 두 번 전사한다.**
      회의록에 같은 말이 두 번 들어갔다:

        [27.3~34.9] 문지수  "좋아요. 그럼 로그인 버튼 색상을..."
        [27.3~27.9] 김나연  "좋아요."          ← 위 문장 앞부분의 중복
        [38.4~40.8] 문지수  "감사합니다. 오늘은 여기까지 할게요."
        [39.0~39.8] 김나연  "자 오늘은 여기까지."  ← 뒷부분의 중복

      중복은 회의록 품질을 떨어뜨리고, 모순 감지가 같은 발언을 두 사람이 한 것으로
      볼 수도 있다.

    긴 턴을 우선하는 이유: 짧은 턴은 대개 화자분리가 잘못 끼워 넣은 조각이고, 설령
    진짜 맞장구였더라도 **그 소리는 이미 긴 턴의 오디오 안에 들어 있어 거기서 전사된다.**
    즉 내용을 잃는 게 아니라 중복을 없애는 것이다(화자 귀속은 잃을 수 있다 —
    공용 마이크에서 겹친 소리를 갈라내지 못하는 한 피할 수 없는 대가다).
    """
    occupied: list = []
    kept: list = []
    # 긴 턴부터 자리를 차지한다
    for turn in sorted(turns, key=lambda t: -(t["end"] - t["start"])):
        pieces = _free_pieces(turn["start"], turn["end"], occupied)
        if not pieces:
            continue        # 통째로 다른 턴 안에 들어 있음 — 버린다
        start, end = max(pieces, key=lambda p: p[1] - p[0])
        if end - start < MIN_TRIMMED_TURN_SEC:
            continue
        kept.append({**turn, "start": round(start, 2), "end": round(end, 2)})
        occupied = sorted(occupied + [(start, end)])

    dropped = len(turns) - len(kept)
    if dropped:
        logger.info(f"✂️ 겹치는 화자 턴 정리: {len(turns)}개 → {len(kept)}개 (중복 전사 방지)")
    return sorted(kept, key=lambda t: t["start"])


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
        # 턴 경계보다 넓게 들려준다 — 말머리가 잘리면 단어를 통째로 놓친다(TURN_PAD_SEC).
        # 실제로 넓힌 양을 따로 재는 이유: 오디오 처음/끝에서는 요청한 만큼 못 넓히므로,
        # 아래에서 본체 위치를 계산할 때 요청값이 아니라 실제값을 써야 어긋나지 않는다.
        clip_start = max(0.0, start - TURN_PAD_SEC)
        clip_end = min(len(audio) / sample_rate, end + TURN_PAD_TAIL_SEC)
        clip = audio[int(clip_start * sample_rate): int(clip_end * sample_rate)]
        if len(clip) == 0:
            continue

        engine_segments = await loop.run_in_executor(None, _transcribe_clip, clip)
        # 여유 구간에만 걸친 조각은 옆 사람 말일 수 있으므로 버린다. 조각 시각은
        # clip 기준이라 본체는 [start-clip_start, end-clip_start] 구간이다.
        core_from, core_to = start - clip_start, end - clip_start
        engine_segments = [
            seg for seg in engine_segments
            if (min(seg.end, core_to) - max(seg.start, core_from))
            >= (seg.end - seg.start) * TURN_PAD_KEEP_RATIO
        ]
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


async def _refine(meeting_id: str, app_state, force: bool = False) -> dict | None:
    meeting_dir = os.path.join(MEETINGS_DIR, meeting_id)
    meta_path = os.path.join(meeting_dir, "transcript.json")
    if not os.path.isfile(meta_path):
        logger.warning(f"⚠️ [{meeting_id}] 재분석 대상 회의록 없음")
        return None

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    # force는 **코드를 고치고 같은 회의로 결과를 다시 재는** 검증 경로를 위한 것이다.
    # 이게 없으면 transcript.json의 refined 플래그를 손으로 내려야 했고, 실제로 그러다
    # "고쳤는데 결과가 그대로"라는 잘못된 결론을 낼 뻔했다(건너뛴 걸 모르고 옛 코드
    # 탓으로 봤다). 운영 경로는 기본값(False)이라 중복 재분석이 일어나지 않는다.
    if meta.get("refined") and not force:
        logger.info(f"↩️ [{meeting_id}] 이미 재분석 완료된 회의 — 건너뜀 (다시 돌리려면 force=1)")
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
    # 같은 화자의 인접 턴을 합치고 → 서로 겹치는 턴을 걷어낸다.
    # 겹침을 안 걷어내면 공용 마이크(오디오 하나)에서 같은 소리를 두 번 전사해
    # 회의록에 같은 말이 두 번 들어간다 (_resolve_overlapping_turns 참고).
    turns = _resolve_overlapping_turns(_merge_adjacent_turns(diarization_tracks))

    # 2. 등록 프로필이 있으면 **전사하기 전에** 화자 타임라인을 만들어 턴을 다시 나눈다.
    #
    #    화자분리 턴 하나에 두 사람이 들어 있으면 전사한 뒤에는 손쓸 수 없다 —
    #    "더 오래 말한 쪽"으로 통째로 귀속시킬 수밖에 없고 앞뒤 절반이 남의 이름을 단다.
    #    타임라인은 0.5초 해상도라 화자분리보다 경계를 세밀하게 알므로, 그걸로 먼저
    #    나누면 전사 자체가 화자별로 분리돼 나온다.
    #    같은 타임라인을 아래 이름 배정에도 재사용한다(두 번 만들면 비용도 두 배고,
    #    두 결과가 어긋나면 "나눈 경계"와 "붙인 이름"이 안 맞는다).
    timeline = None
    if enrolled_count:
        profile_data = np.load(profiles_path)
        profiles = {name: profile_data[name] for name in profile_data.files}
        if profiles:
            timeline = await loop.run_in_executor(
                None, build_speaker_timeline,
                audio, profiles, app_state.speaker_embedding_inference, sample_rate,
            )
            turns = split_turns_by_timeline(turns, timeline)

    logger.info(f"🔬 [{meeting_id}] 화자 턴 {len(diarization_tracks)}개 → 정리 후 {len(turns)}개, 턴별 전사 시작")

    # 3. 턴별 정밀 전사 (각자 PC 모드와 같은 헬퍼를 씀 — 차이는 오디오 출처뿐)
    # 최종 회의록이 되는 경로라 인식 힌트를 여기에도 적용한다. 등록 프로필이 있으면
    # 그 이름들이 곧 참석자이므로 힌트에 넣고, 없으면 용어만 들어간다.
    enrolled_names = list(np.load(profiles_path).files) if enrolled_count else []
    refined_segments = await _transcribe_turns(
        app_state, meeting_id, turns,
        audio_of=lambda _turn: (audio, sample_rate),  # 공용 마이크는 회의 오디오 하나뿐
        initial_prompt=build_context_hint(enrolled_names, session_id=meta.get("session_id")),
    )

    # 4. 익명 라벨(SPEAKER_00 등) → 실제 이름. 위에서 만든 타임라인을 그대로 쓴다.
    if timeline is not None:
        _assign_speakers_from_timeline(refined_segments, timeline)

    # 5. 겹쳐 말한 구간 처리.
    #    모델에 직접 묻는다. 화자분리 결과에서 역산하던 방식은 오탐이 많아 폐기했다 —
    #    그 방식이 겹침이라고 한 11개 구간이 실제로는 하나도 겹침이 아니었고,
    #    멀쩡한 발언까지 "겹쳤다"고 표시하고 있었다(overlap_detect 상단 참고).
    # load_overlap_inference()를 인자 자리에서 부르면 **이벤트 루프에서** 모델을 로드한다
    # (인자가 먼저 평가되므로). 첫 회의에서 수 초간 서버 전체가 멈추므로 실행기 안에서 부른다.
    overlap_spans = await loop.run_in_executor(
        None, lambda: find_overlap_spans_from_audio(audio, load_overlap_inference(), sample_rate),
    )
    if overlap_spans:
        # 5-a. 분리가 켜져 있으면 겹친 구간을 화자별로 갈라 각각 전사 — 포기하지 않고 살린다
        refined_segments = await _split_overlaps(
            app_state, meeting_id, refined_segments, overlap_spans,
            audio, sample_rate, profiles_path, enrolled_names, meta,
        )
        # 5-b. **아직 안 풀린** 겹침에만 표시를 단다(이름은 그대로). 지울 근거가 실측에서
        #      안 나왔다 — overlap_detect.mark_overlapped_segments의 설명 참고.
        #      분리로 이미 갈라낸 세그먼트는 대상이 아니다 — 해결해놓고 "안 풀렸다"고
        #      표시하면 소비자가 그 발언을 불필요하게 걸러낸다.
        mark_overlapped_segments(
            [seg for seg in refined_segments if not seg.get("separated")], overlap_spans,
        )

    # 6. LLM이 문맥으로 읽고 오인식 단어를 고친다.
    #    용어 목록은 "사람이 미리 겪은 단어"만 커버한다. 여기서는 문장의 뜻으로 유추한다.
    #    실패해도 원문이 그대로 남으므로 회의록을 잃지 않는다.
    if REFINE_LLM_ENABLED:
        await loop.run_in_executor(
            None, correct_transcript, refined_segments,
            build_context_hint(enrolled_names, session_id=meta.get("session_id")),
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


async def _split_overlaps(
    app_state, meeting_id: str, segments: list[dict], spans: list[tuple[float, float]],
    audio, sample_rate: int, profiles_path: str, enrolled_names: list[str], meta: dict,
) -> list[dict]:
    """
    겹친 구간을 화자별 음원으로 분리해 각각 전사한 세그먼트로 교체한다.

    overlap_detect가 "누구인지 정하지 않겠다"고 포기하는 것과 달리, 여기서는 겹친
    소리를 실제로 갈라서 **두 발언을 모두 살린다.** 분리가 꺼져 있거나 모델을 못 쓰면
    원래 세그먼트를 그대로 돌려주고, 그러면 4-b가 '여러 명'으로 표시한다.

    분리 음성은 인공적인 왜곡이 남아 원본보다 전사가 나쁠 수 있으므로 **겹친 구간에만**
    쓴다. 안 겹친 구간은 원본 오디오로 이미 전사돼 있고 그쪽이 더 정확하다.
    """
    if not SEPARATION_ENABLED:
        return segments

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, separate_sources, audio, sample_rate)
    if result is None:
        return segments
    channels, _tracks = result

    # 어느 (겹침 구간 × 채널)을 전사할지 목록화. 그 사람이 말하지 않은 채널은
    # 잔향만 남아 있어 전사하면 헛것이 나오므로 세기로 걸러낸다.
    turns = []
    for start, end in spans:
        for label in active_channels(channels, start, end, sample_rate):
            turns.append({"start": start, "end": end, "speaker": None, "_channel": label})
    if not turns:
        return segments

    logger.info(f"🔀 [{meeting_id}] 겹침 {len(spans)}구간 → 분리 전사 {len(turns)}건")
    separated = await _transcribe_turns(
        app_state, meeting_id, turns,
        audio_of=lambda turn: (channels[turn["_channel"]], sample_rate),
        initial_prompt=build_context_hint(enrolled_names, session_id=meta.get("session_id")),
    )
    if not separated:
        return segments

    # 분리된 채널에도 이름을 붙인다 — 분리 모델의 라벨은 익명(SPEAKER_00)이라
    # 등록 프로필과 대조해야 실제 이름이 된다.
    if enrolled_names:
        await loop.run_in_executor(
            None, _name_separated_segments,
            separated, turns, channels, sample_rate, profiles_path,
            app_state.speaker_embedding_inference,
        )

    # 겹침 구간에 대부분 걸쳐 있던 원래 세그먼트를 분리본으로 교체
    kept = [
        seg for seg in segments
        if overlap_ratio(seg["start"], seg["end"], spans) < OVERLAP_SEGMENT_RATIO
    ]
    merged = sorted(kept + separated, key=lambda seg: (seg["start"], seg["end"]))
    logger.info(
        f"🔀 [{meeting_id}] 겹침 세그먼트 {len(segments) - len(kept)}개 → 분리본 {len(separated)}개로 교체"
    )
    return merged


def _name_separated_segments(
    separated: list[dict], turns: list[dict], channels: dict, sample_rate: int,
    profiles_path: str, inference,
) -> None:
    """분리된 각 채널 구간의 목소리를 등록 프로필과 대조해 이름을 붙인다."""
    from .speaker_id_service import LiveSpeakerIdentifier

    data = np.load(profiles_path)
    profiles = {name: data[name] for name in data.files}
    if not profiles:
        return
    identifier = LiveSpeakerIdentifier(inference, initial_profiles=profiles)

    # _transcribe_turns는 텍스트가 빈 턴을 버리므로 turns와 개수가 다를 수 있다.
    # 시간·채널로 되짚어 찾는데, **반올림을 맞춰야 한다** — _transcribe_turns가
    # start/end를 소수 둘째 자리로 반올림해서 담기 때문에, 원본 float(예: 27.700000000000003)를
    # 키로 쓰면 조회가 전부 빗나가 이름이 하나도 안 붙는다.
    by_span = {}
    for turn in turns:
        key = (round(turn["start"], 2), round(turn["end"], 2))
        by_span.setdefault(key, []).append(turn["_channel"])

    for seg in separated:
        labels = by_span.get((seg["start"], seg["end"]), [])
        best_name, best_score = None, -1.0
        for label in labels:
            clip = channels[label][int(seg["start"] * sample_rate): int(seg["end"] * sample_rate)]
            if len(clip) < sample_rate:
                continue
            name, _nearest, score, _margin = identifier.match_closed_set(
                identifier.extract_embedding(clip)
            )
            if name and score > best_score:
                best_name, best_score = name, score
        seg["speaker"] = best_name
        seg["separated"] = True


def _assign_speakers_from_timeline(segments: list[dict], timeline) -> list[dict]:
    """
    각 세그먼트에 **미리 만들어둔 화자 타임라인**에서 읽은 이름을 붙인다.

    타임라인은 전사 전에 만들어 턴을 나누는 데 이미 쓰였다(split_turns_by_timeline).
    같은 것을 재사용한다 — 두 번 만들면 비용만 두 배고, 두 결과가 미세하게 달라지면
    "나눈 경계"와 "붙인 이름"이 어긋난다.

    왜 화자분리 결과에 이름을 붙이지 않나 (2026-08-03~04 실측, 정답 대본이 있는
    5인 공용 마이크 회의에서 다섯 번 고쳐가며 측정):

      ① 클러스터 1:1 매핑 — pyannote가 두 사람을 한 클러스터로 묶으면 그 발언
         전부가 한 사람 이름을 받는다. 김나연·이승주·이준오의 발언이 문지수로 몰렸다.
      ② 턴별 판정 — 틀린 이름은 사라졌지만, 조각난 턴이 짧아 미상 19개가 남았다.
      ③ 클러스터 보완/재판정 — 이준오·이승주가 묶인 클러스터는 15.9초를 다 모아도
         최고 유사도 0.37(엉뚱한 사람)이었다. 클러스터가 틀리면 무엇을 해도 안 된다.

      ①~③이 공통으로 깔고 있던 전제가 문제였다. 화자분리는 **참석자가 누구인지
      모른다는 전제**로 도는데, 우리는 이미 알고 있다. 그 정보를 안 쓰고 클러스터링
      결과를 받아 이름만 붙이니 클러스터링이 실패하면 같이 실패했다.
      같은 회의에서 창 단위 직접 판정의 1등 정확도는 94%(평활화 후 97%)였다.

    화자분리는 **전사 경계의 출발점**으로만 쓴다. 그 경계가 두 사람에 걸쳐 있으면
    전사 전에 타임라인으로 다시 나눈다.

    (speaker_timeline.build_speaker_timeline에 판정 규칙의 근거가 정리돼 있다)
    """
    assigned: dict[str, int] = {}
    for seg in segments:
        name = timeline.speaker_of(seg["start"], seg["end"])
        seg["speaker"] = name
        if name:
            assigned[name] = assigned.get(name, 0) + 1

    unknown = sum(1 for seg in segments if not seg.get("speaker"))
    logger.info(
        "🔗 세그먼트 화자 배정: "
        + (", ".join(f"{k} {v}개" for k, v in sorted(assigned.items())) or "확정 없음")
        + (f", 미상 {unknown}개" if unknown else "")
    )
    return segments
