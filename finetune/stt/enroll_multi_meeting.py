"""
**여러 회의**의 발화를 섞어 목소리 프로필을 만든다 (하나 빼기 지원).

왜 필요한가 (2026-08-18):
  회의 한 건(36256894)에서 재등록했더니 결과가 회의마다 갈렸다:

      회의          기존 프로필 → 재등록
      ba8f38c4      28.82% → 11.10%   크게 개선
      ded1105f      22.22% → 14.62%   크게 개선
      8b5f84b7      54.23% → 64.71%   크게 악화

  **한 회의에서만 뽑으면 그 회의의 조건(방·마이크·거리)이 프로필에 박힌다.**
  등록에 쓴 회의와 조건이 비슷하면 크게 이기고, 다르면 오히려 해가 된다.
  평균이 35.09 → 30.14로 좋아 보이지만 그 평균은 이 갈림을 감춘다.

  악화의 기전도 확인됐다. 8b5f84b7에서 이승주의 등록 유사도가 0.156 → 0.391로
  **올랐는데**, 하한이 0.35라 전에는 미상으로 떨어지던 발언이 이제 하한을 넘는다.
  그런데 그의 순위는 여전히 틀려서(회의내 자기 0.391 < 타인 0.597) **이름이 붙되
  남의 이름이 붙는다.** 미상 17→14, 오배정 0→4가 정확히 그 결과다.
  전에는 프로필이 나쁜 것이 우연히 방패였던 셈이다.

  그래서 여러 조건을 섞어 한쪽에 박히지 않는 프로필을 만든다.

⚠️ 채점할 회의는 반드시 빼야 한다(--exclude).
   그 회의의 오디오로 만든 프로필로 그 회의를 채점하면 자기가 만든 데이터로 자기를
   채점하는 셈이라 실제보다 좋게 나온다. 예전에 36256894로 그 실수를 했다.

⚠️ 회의마다 발화 수가 다르므로 **회의 안에서 먼저 평균 내고, 그다음 회의들끼리 평균**낸다.
   그냥 전부 평균하면 발화가 많은 회의가 프로필을 지배해서, 조건을 섞으려는 목적이
   무너진다.

임베딩 추출은 서버 등록 경로와 동일하다(services/voice_ingest.py → extract_embedding).
따로 구현하면 서버가 만든 프로필과 미묘하게 다른 것이 나온다.

사용법:
  # ba8f38c4를 채점하려고, 나머지 회의들로 프로필을 만든다
  python enroll_multi_meeting.py \
      --meetings 36256894-...:scripts/demo_prep_meeting.txt \
                 ded1105f-...:scripts/launch_plan_meeting.txt \
                 8b5f84b7-...:scripts/retention_meeting.txt \
      --exclude ba8f38c4-... --dry-run
"""
import argparse
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np
import soundfile as sf

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

from stt.core.config import MEETINGS_DIR, VOICE_PROFILES_DIR  # noqa: E402
from stt.services.speaker_id_service import (  # noqa: E402
    LiveSpeakerIdentifier, load_speaker_embedding_inference,
)
from probe_score_norm import truth_spans  # noqa: E402

MIN_SPAN_SEC = 1.0


def unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n else v


def meeting_embeddings(meeting: str, script: str, identifier,
                       min_sec: float, chunk_sec: float = 0.0) -> dict[str, list[np.ndarray]]:
    """회의 하나에서 화자별 발화 임베딩을 모은다.

    chunk_sec > 0이면 긴 구간을 그 길이로 잘라 각각 임베딩을 뽑는다.

    왜 필요한가 (2026-08-18): 파인튜닝 모델이 우리 화자들을 오히려 뭉갠다
    (김나연↔이승주 0.606 → 0.834). 의심되는 원인은 **학습은 3초로 잘라서 했는데
    등록·판정은 10~30초를 통째로 넣는다**는 것이다. 모델이 3초 길이의 통계에
    적응했다면 긴 입력에서 임베딩이 무너질 수 있다.
    같은 길이로 잘라 재보면 그 가설이 맞는지 갈린다 — 유사도가 떨어지면 길이
    불일치가 원인이고, 그대로면 학습 자체가 공간을 뭉갠 것이다.
    """
    path = os.path.join(MEETINGS_DIR, meeting, "audio.wav")
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    out: dict[str, list[np.ndarray]] = defaultdict(list)
    for speaker, start, end in truth_spans(meeting, script):
        if end - start < min_sec:
            continue
        clip = audio[int(start * sr):int(end * sr)]
        if chunk_sec <= 0:
            out[speaker].append(unit(identifier.extract_embedding(clip)))
            continue
        step = int(chunk_sec * sr)
        for i in range(0, len(clip), step):
            piece = clip[i:i + step]
            if len(piece) < min_sec * sr:      # 자투리가 너무 짧으면 버린다
                continue
            out[speaker].append(unit(identifier.extract_embedding(piece)))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meetings", nargs="+", required=True, help="'회의ID:대본경로'")
    parser.add_argument("--exclude", default=None,
                        help="여기 준 회의는 등록에서 뺀다. 그 회의를 채점할 때 쓴다")
    parser.add_argument("--names", nargs="*", default=None,
                        help="등록할 이름. 안 주면 대본에 나오는 사람 전부")
    parser.add_argument("--min-sec", type=float, default=MIN_SPAN_SEC)
    parser.add_argument("--chunk-sec", type=float, default=0.0,
                        help="긴 구간을 이 길이로 잘라 각각 임베딩을 뽑는다(0이면 통째로). "
                             "학습 crop 길이와 맞춰 길이 불일치를 검증할 때 쓴다")
    parser.add_argument("--profiles-dir", default=VOICE_PROFILES_DIR)
    parser.add_argument("--dry-run", action="store_true",
                        help="저장하지 않고 어떤 프로필이 나올지만 보여준다")
    args = parser.parse_args()

    specs = []
    for spec in args.meetings:
        meeting, script = spec.split(":", 1)
        if args.exclude and meeting.startswith(args.exclude[:8]):
            print(f"제외: {meeting[:38]} (채점 대상)")
            continue
        specs.append((meeting, os.path.join(_HERE, script)))
    if not specs:
        raise SystemExit("❌ 등록에 쓸 회의가 없다")

    identifier = LiveSpeakerIdentifier(load_speaker_embedding_inference())

    # 회의 안에서 먼저 평균 → 회의들끼리 평균. 발화 많은 회의가 지배하지 않게.
    per_meeting: dict[str, dict[str, np.ndarray]] = {}
    counts: dict[str, dict[str, int]] = {}
    for meeting, script in specs:
        embs = meeting_embeddings(meeting, script, identifier, args.min_sec, args.chunk_sec)
        per_meeting[meeting] = {s: unit(np.mean(v, axis=0)) for s, v in embs.items()}
        counts[meeting] = {s: len(v) for s, v in embs.items()}
        print(f"  {meeting[:38]}: " +
              ", ".join(f"{s} {n}건" for s, n in sorted(counts[meeting].items())))

    names = args.names or sorted({s for m in per_meeting.values() for s in m})
    profiles: dict[str, np.ndarray] = {}
    for name in names:
        vecs = [m[name] for m in per_meeting.values() if name in m]
        if not vecs:
            print(f"⚠️ {name}: 발화를 못 찾음 — 건너뜀")
            continue
        profiles[name] = unit(np.mean(vecs, axis=0))
        used = sum(counts[mid].get(name, 0) for mid in per_meeting)
        print(f"  {name}: 회의 {len(vecs)}개 / 발화 {used}건")

    print()
    print("만들어진 프로필끼리의 유사도 (대각선 밖이 낮아야 잘 갈린다)")
    order = sorted(profiles)
    print("           " + "".join(f"{n:>9s}" for n in order))
    worst = (-1.0, "", "")
    for a in order:
        row = "".join(f"{float(np.dot(profiles[a], profiles[b])):9.3f}" for b in order)
        print(f"  {a:8s}{row}")
    for i, a in enumerate(order):
        for b in order[i + 1:]:
            sim = float(np.dot(profiles[a], profiles[b]))
            if sim > worst[0]:
                worst = (sim, a, b)
    if worst[1]:
        print(f"\n가장 헷갈리는 짝: {worst[1]} ↔ {worst[2]} = {worst[0]:.3f}")
        if worst[0] > 0.5:
            print("⚠️ 0.5를 넘으면 이 둘은 실제로 자주 뒤바뀐다 — 결과 해석에 감안할 것")

    if args.dry_run:
        print("\n(--dry-run: 저장하지 않음)")
        return

    os.makedirs(args.profiles_dir, exist_ok=True)
    backup = os.path.join(
        os.path.expanduser("~"), datetime.now().strftime("voice_profiles_%Y%m%d-%H%M%S"))
    os.makedirs(backup, exist_ok=True)
    for name, vec in profiles.items():
        path = os.path.join(args.profiles_dir, f"{name}.npy")
        if os.path.isfile(path):
            shutil.copyfile(path, os.path.join(backup, f"{name}.npy"))
        np.save(path, vec)
        print(f"  저장: {path}")
    print(f"\n✅ 프로필 {len(profiles)}개 저장 / 백업 {backup}")


if __name__ == "__main__":
    main()
