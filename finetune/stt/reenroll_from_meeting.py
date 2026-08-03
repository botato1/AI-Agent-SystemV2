"""
저장된 회의 오디오의 특정 구간으로 목소리 프로필을 다시 등록한다.

언제 쓰나:
  등록이 잘못돼 실시간 화자 매칭이 계속 실패할 때. 본인이 자리에 없어도 이미 녹음된
  회의에서 그 사람의 발화 구간을 잘라 재등록할 수 있다.

  실제 사례(2026-08-03): 이승주 프로필이 본인 발화와 0.31~0.33밖에 안 맞아
  (정상 매칭은 0.72) 발언이 계속 다른 사람으로 배정되거나 미상으로 떨어졌다.
  프로필 간 유사도도 이 사람만 유난히 낮았다 — 등록 당시 녹음이 짧았거나
  마이크 상태가 나빴을 가능성.

⚠️ 한계: 회의 오디오는 공용 마이크로 녹음돼 전용 등록 녹음보다 품질이 낮을 수 있다.
   본인이 자리에 있다면 테스트 페이지에서 직접 재녹음하는 쪽이 더 좋다.
   이 스크립트는 "사람을 못 구할 때"의 차선책이다.

⚠️ 같은 이름으로 등록하면 **덮어쓴다**. 기존 프로필은 실행 전에 자동 백업한다.

사용법:
  python reenroll_from_meeting.py --meeting <회의ID> --name 이승주 \
      --at 94.4-103.8 139.0-148.6 152.9-165.0 --dry-run
  (확인 후 --dry-run 빼고 실행)
"""
import argparse
import os
import shutil
import sys
import urllib.parse
import urllib.request
from datetime import datetime

import numpy as np
import soundfile as sf

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import (  # noqa: E402
    MEETINGS_DIR, VOICE_PROFILES_DIR, REALTIME_SAMPLE_RATE,
)
from stt.services.profile_store import GlobalProfileStore  # noqa: E402
from stt.services.speaker_id_service import (  # noqa: E402
    LiveSpeakerIdentifier, load_speaker_embedding_inference,
)


def cosine(a, b) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--name", required=True, help="등록할 이름 (기존과 같으면 덮어씀)")
    parser.add_argument("--at", nargs="+", required=True, help="구간 '시작-끝'(초)")
    parser.add_argument("--audio", default="audio.wav")
    parser.add_argument("--server", default="http://127.0.0.1:8002")
    parser.add_argument("--dry-run", action="store_true",
                        help="등록하지 않고 새 프로필이 얼마나 나아지는지만 확인")
    args = parser.parse_args()

    path = os.path.join(MEETINGS_DIR, args.meeting, args.audio)
    if not os.path.isfile(path):
        raise SystemExit(f"❌ 오디오 없음: {path}")

    audio, sample_rate = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sample_rate != REALTIME_SAMPLE_RATE:
        raise SystemExit(f"❌ 샘플레이트 {sample_rate}Hz — {REALTIME_SAMPLE_RATE}Hz 여야 함")

    # 여러 구간을 이어붙인다 — 오디오가 많을수록 지문이 안정적이다
    pieces = []
    for spec in args.at:
        start, end = (float(x) for x in spec.split("-"))
        clip = audio[int(start * sample_rate):int(end * sample_rate)]
        if len(clip) == 0:
            print(f"⚠️ 빈 구간 건너뜀: {spec}")
            continue
        pieces.append(clip)
        print(f"  구간 {start:.1f}s ~ {end:.1f}s  ({len(clip)/sample_rate:.1f}초)")
    if not pieces:
        raise SystemExit("❌ 쓸 수 있는 구간이 없음")

    merged = np.concatenate(pieces)
    print(f"\n합계 {len(merged)/sample_rate:.1f}초")

    # 새 프로필이 실제로 나아지는지 먼저 확인 — 나빠질 거면 등록하지 않는 게 낫다
    store = GlobalProfileStore()
    identifier = LiveSpeakerIdentifier(load_speaker_embedding_inference())
    new_embedding = identifier.extract_embedding(merged)

    existing = store.load(store.list_names())
    old = existing.get(args.name)

    print("\n새 프로필과 각 기존 프로필의 유사도:")
    for name, emb in sorted(existing.items(), key=lambda kv: -cosine(new_embedding, kv[1])):
        mark = "  ← 본인(기존)" if name == args.name else ""
        print(f"  {name:<10s} {cosine(new_embedding, emb):.3f}{mark}")

    if old is not None:
        same = cosine(new_embedding, old)
        print(f"\n기존 '{args.name}' 프로필과의 유사도: {same:.3f}")
        if same < 0.4:
            print("  → 기존 프로필과 많이 다르다. 기존 등록이 잘못됐거나, 이 구간이")
            print("     다른 사람일 수 있다. 구간이 정말 그 사람인지 확인할 것.")

    if args.dry_run:
        print("\n(--dry-run: 등록하지 않음)")
        return

    # 되돌릴 수 있게 백업 — 덮어쓰면 이전 지문은 복구할 방법이 없다
    src = os.path.join(VOICE_PROFILES_DIR, f"{args.name}.npy")
    if os.path.isfile(src):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dst = os.path.join(VOICE_PROFILES_DIR, f"{args.name}.{stamp}.npy.bak")
        shutil.copy2(src, dst)
        print(f"\n백업: {os.path.basename(dst)}")

    pcm16 = (np.clip(merged, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    url = f"{args.server}/api/profiles?" + urllib.parse.urlencode(
        {"speaker_name": args.name}, encoding="utf-8"
    )
    request = urllib.request.Request(
        url, data=pcm16, method="POST",
        headers={"Content-Type": "application/octet-stream"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        print(f"\n서버 응답 (HTTP {response.status}):")
        print(response.read().decode("utf-8", "replace"))

    print("\n확인: python diagnose_speaker_profiles.py --meeting <회의ID> --at <구간>")


if __name__ == "__main__":
    main()
