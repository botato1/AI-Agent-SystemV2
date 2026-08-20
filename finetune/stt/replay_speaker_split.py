"""
저장된 회의 오디오를 실시간 경로와 같은 방식으로 흘려보내, 청크 안 화자 전환 분할이
실제로 동작하는지 검증한다.

왜 필요한가:
  화자 전환 분할은 "한 청크에 두 사람 이상이 들어갔을 때"만 발동한다. 혼자 녹음한
  오디오로는 발동 조건 자체가 성립하지 않아 검증이 불가능하다. 사람을 다시 모으는
  대신, 이미 저장된 다인 회의 오디오를 재생해 같은 판정을 돌린다.

실시간 서버를 띄우지 않고 로직만 돌리므로 GPU 전사는 하지 않는다 —
확인 대상은 "어디서 화자가 바뀌었다고 판단하는가"이지 전사 텍스트가 아니다.

사용법 (GPU 서버, stt venv):
  python replay_speaker_split.py --meeting test-session-1_20260730-073029
  python replay_speaker_split.py --meeting <회의ID> --speakers 이준오 문지수 가동현
"""
import argparse
import os
import sys

import numpy as np
import soundfile as sf

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import (  # noqa: E402
    MEETINGS_DIR, REALTIME_SAMPLE_RATE, REALTIME_MIN_CHUNK_SEC,
    REALTIME_MAX_CHUNK_SEC, REALTIME_SILENCE_MS,
)
from stt.services.profile_store import GlobalProfileStore  # noqa: E402
from stt.services.speaker_id_service import (  # noqa: E402
    LiveSpeakerIdentifier, load_speaker_embedding_inference,
)
from stt.services.realtime_service import RealtimeSTTSession  # noqa: E402
from faster_whisper.vad import VadOptions, get_speech_timestamps  # noqa: E402


def chunk_like_realtime(audio: np.ndarray) -> list[tuple[int, int]]:
    """
    실시간 경로와 같은 규칙으로 오디오를 청크로 나눈다(발화가 끊긴 지점 기준,
    최소 2초 / 최대 28초). 실제 세션은 스트리밍이라 정확히 같지는 않지만,
    "한 청크에 여러 화자가 들어가는가"를 보기에는 충분히 동등하다.
    """
    spans = get_speech_timestamps(
        audio, VadOptions(min_silence_duration_ms=REALTIME_SILENCE_MS),
        sampling_rate=REALTIME_SAMPLE_RATE,
    )
    if not spans:
        return []

    min_s = int(REALTIME_MIN_CHUNK_SEC * REALTIME_SAMPLE_RATE)
    max_s = int(REALTIME_MAX_CHUNK_SEC * REALTIME_SAMPLE_RATE)
    chunks, start = [], 0
    for i, span in enumerate(spans):
        end = span["end"]
        is_last = i == len(spans) - 1
        long_enough = end - start >= min_s
        too_long = end - start >= max_s
        # 다음 발화까지의 침묵이 충분하면 여기서 끊는다 (실시간의 should_flush와 같은 판단)
        gap_ok = is_last or (spans[i + 1]["start"] - end) >= REALTIME_SILENCE_MS * REALTIME_SAMPLE_RATE // 1000
        if (long_enough and gap_ok) or too_long:
            chunks.append((start, end))
            start = end
    if start < len(audio):
        chunks.append((start, len(audio)))
    return chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True, help="회의 폴더명 (meetings/ 아래)")
    parser.add_argument("--speakers", nargs="*", default=None,
                        help="참석자 이름 (미지정 시 전역 프로필 전체를 닫힌 집합으로 사용)")
    parser.add_argument("--audio", default="audio.wav", help="재생할 파일 (기본: 믹스본)")
    args = parser.parse_args()

    path = os.path.join(MEETINGS_DIR, args.meeting, args.audio)
    if not os.path.isfile(path):
        raise SystemExit(f"❌ 오디오 없음: {path}")

    audio, sample_rate = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sample_rate != REALTIME_SAMPLE_RATE:
        raise SystemExit(f"❌ 샘플레이트 {sample_rate}Hz — {REALTIME_SAMPLE_RATE}Hz 파일이어야 함")

    store = GlobalProfileStore()
    names = args.speakers or store.list_names()
    profiles = store.load(names)
    if not profiles:
        raise SystemExit("❌ 등록된 목소리 프로필이 없음 — --speakers로 지정하거나 먼저 등록 필요")

    print(f"회의       : {args.meeting} ({len(audio)/REALTIME_SAMPLE_RATE:.1f}초)")
    print(f"참석자     : {', '.join(profiles)}")

    identifier = LiveSpeakerIdentifier(load_speaker_embedding_inference(), initial_profiles=profiles)
    session = object.__new__(RealtimeSTTSession)
    session.session_id = args.meeting
    session.speaker_identifier = identifier

    chunks = chunk_like_realtime(audio)
    print(f"청크 수    : {len(chunks)}\n")

    split_count = 0
    for i, (start, end) in enumerate(chunks, 1):
        piece = audio[start:end]
        turns = session._speaker_turns(piece)
        base = start / REALTIME_SAMPLE_RATE
        dur = (end - start) / REALTIME_SAMPLE_RATE

        if len(turns) < 2:
            who = turns[0][2] if turns else None
            print(f"[{i:3d}] {base:6.1f}s ({dur:5.1f}초)  단일 화자: {who}")
            continue

        split_count += 1
        print(f"[{i:3d}] {base:6.1f}s ({dur:5.1f}초)  🔀 화자 전환 {len(turns)}턴")
        for ts, te, spk in turns:
            print(f"          └ {base + ts/REALTIME_SAMPLE_RATE:6.1f}s ~ "
                  f"{base + te/REALTIME_SAMPLE_RATE:6.1f}s  {spk}")

    print(f"\n{'='*56}")
    print(f"화자 전환이 있던 청크: {split_count}/{len(chunks)}")
    if split_count:
        print("→ 이 청크들은 예전 방식이었다면 여러 사람 발언이 한 사람 이름으로 묶였을 구간입니다.")
    else:
        print("→ 전환 없음. 이 오디오에서는 청크가 이미 화자별로 갈려 있어 문제가 없던 상황입니다.")


if __name__ == "__main__":
    main()
