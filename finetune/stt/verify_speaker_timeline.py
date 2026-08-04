"""
화자 타임라인을 **회의 오디오 전체**에 돌려 실제 성능을 확인한다.

probe_window_speaker_id.py와 다른 점이 핵심이다:
  probe는 사람이 손으로 고른 **깨끗한 단독 발화 구간**만 쟀다. 거기엔 침묵도,
  화자 전환 경계도, 겹쳐 말한 구간도 없다. 그 조건에서 94%가 나왔다고 실제
  회의에서 94%라는 뜻은 아니다 — margin 문턱의 진짜 역할(잡음·겹침 차단)도
  그 표본에는 아예 나타나지 않았다.

  이 스크립트는 전체 오디오에 그대로 돌려서, 재분석이 실제로 만들 결과를 본다.
  (파일 단위 평가만으로 통과시키지 않는다는 원칙과 같은 이유다.)

정답이 있으면 --truth로 구간을 주면 정확도까지 나오고, 없으면 화자별 발화량과
미상 비율만 나온다 — 그것만으로도 "한 사람에게 몰리는" 오배정은 눈에 띈다.

사용법:
  python verify_speaker_timeline.py --meeting <회의ID>
  python verify_speaker_timeline.py --meeting <회의ID> --truth 이준오:41.3-50.5 ...
"""
import argparse
import os
import sys

import numpy as np
import soundfile as sf

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import (  # noqa: E402
    MEETINGS_DIR, SPEAKER_MIN_MARGIN, SPEAKER_WINDOW_SEC, SPEAKER_WINDOW_HOP_SEC,
    SPEAKER_SMOOTH_WIDTH,
)
from stt.services.speaker_id_service import load_speaker_embedding_inference  # noqa: E402
from stt.services.speaker_timeline import build_speaker_timeline  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--audio", default="audio.wav")
    parser.add_argument("--truth", nargs="*", default=[], help="정답 구간 '이름:시작-끝' (초)")
    args = parser.parse_args()

    meeting_dir = os.path.join(MEETINGS_DIR, args.meeting)
    audio, sr = sf.read(os.path.join(meeting_dir, args.audio), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    profiles_path = os.path.join(meeting_dir, "profiles.npz")
    if not os.path.isfile(profiles_path):
        raise SystemExit(f"❌ 등록 프로필 없음: {profiles_path} (공용 마이크 회의가 아님)")
    data = np.load(profiles_path)
    profiles = {name: data[name] for name in data.files}

    print(f"설정: 창 {SPEAKER_WINDOW_SEC}초 / 이동 {SPEAKER_WINDOW_HOP_SEC}초 / "
          f"margin 하한 {SPEAKER_MIN_MARGIN} / 평활화 {SPEAKER_SMOOTH_WIDTH}창")
    print(f"참석자 {len(profiles)}명: {', '.join(profiles)}")
    print(f"오디오 {len(audio) / sr:.0f}초\n")

    timeline = build_speaker_timeline(audio, profiles, load_speaker_embedding_inference(), sr)

    print("\n화자별 발화 시간")
    totals: dict = {}
    for start, end, name in timeline.slots:
        key = name or "미상"
        totals[key] = totals.get(key, 0.0) + (end - start)
    grand = sum(totals.values()) or 1.0
    for name, sec in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"  {name:8s}{sec:7.1f}초{sec / grand * 100:7.0f}%")

    if not args.truth:
        print("\n(--truth 없이 돌렸으므로 정확도는 못 잰다. 한 사람에게 몰려 있지 않은지,")
        print(" 미상 비율이 과하지 않은지만 확인할 것)")
        return

    print("\n정답 구간별 판정 (구간을 통째로 조회 — 재분석이 세그먼트에 붙이는 방식 그대로)")
    print(f"{'정답':8s}{'판정':10s}{'결과':>6s}")
    hit = 0
    for spec in args.truth:
        name, span = spec.split(":")
        start, end = (float(x) for x in span.split("-"))
        got = timeline.speaker_of(start, end)
        ok = got == name
        hit += ok
        print(f"{name:8s}{str(got or '미상'):10s}{'✅' if ok else '❌':>6s}")
    print(f"\n정답 구간 {hit}/{len(args.truth)} 일치")


if __name__ == "__main__":
    main()
