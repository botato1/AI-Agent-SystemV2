"""
지금 쓰는 화자 임베딩 모델이 **한국어 회의 음성에서** 몇 점인지 잰다 (EER).

왜 필요한가 (2026-08-18):
  임베딩 모델을 학습시킬지 말지 정하려면, 지금 모델이 실제로 나쁜지부터 알아야 한다.
  이미 충분히 좋다면 며칠 학습해도 안 오르고, 나쁘다면 그 폭이 곧 되찾을 수 있는 여지다.

  지금 모델은 pyannote의 wespeaker-voxceleb-resnet34-LM으로 **영어(VoxCeleb) 데이터로
  학습**됐다. 영어 기준으로는 EER 1% 안팎이 보고되는 모델이지만, 한국어 회의 음성에서
  얼마나 무너지는지는 우리가 잰 적이 없다.

  판단 기준 (측정 전에 미리 정해둔다 — 결과를 보고 기준을 만들면 자기합리화가 된다):
    EER > 5%    → 한국어에서 확실히 나쁨. 학습할 값이 있다
    EER 2~5%    → 애매. 학습하되 기대치를 낮게
    EER < 2%    → 이미 충분히 좋음. 학습 접고 판정 방식(순위+격차) 쪽으로

⚠️ 임베딩 추출은 **서버가 쓰는 것과 똑같은 경로**를 쓴다
   (load_speaker_embedding_inference + LiveSpeakerIdentifier.extract_embedding).
   따로 구현하면 "이 모델의 논문 성능"을 재게 되지 우리 시스템의 성능이 아니다.

⚠️ EER이 좋아져도 그것만으로 채택하지 않는다. 실제 목표는 회의록이므로 학습 후에는
   반드시 우리 회의 cpCER을 함께 봐야 한다(sweep_speaker_floor.py). EER만 좋아지고
   cpCER이 그대로인 경우가 실제로 있다.

사용법:
  python eval_speaker_eer.py --trials trials_aihub.tsv
"""
import argparse
import io
import os
import sys
import zipfile
from collections import defaultdict

import numpy as np
import soundfile as sf

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import (  # noqa: E402
    REALTIME_SAMPLE_RATE, HF_TOKEN, SPEAKER_EMBEDDING_MODEL, DEVICE,
)
from stt.services.speaker_id_service import (  # noqa: E402
    LiveSpeakerIdentifier, load_speaker_embedding_inference,
)


def load_inference(checkpoint: str | None):
    """기본은 서버와 똑같은 경로. --checkpoint를 주면 파인튜닝 가중치를 얹는다.

    학습 결과를 **같은 잣대로** 재기 위해 모델만 갈아끼우고 나머지(창 방식, 디바이스,
    임베딩 추출)는 서버와 동일하게 둔다.
    """
    if not checkpoint:
        return load_speaker_embedding_inference()

    import torch
    from pyannote.audio import Model, Inference
    model = Model.from_pretrained(SPEAKER_EMBEDDING_MODEL, use_auth_token=HF_TOKEN)
    state = torch.load(checkpoint, map_location="cpu")
    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing or unexpected:
        # 조용히 넘어가면 "학습이 안 먹었는데 좋아 보이는" 결과가 나온다
        print(f"⚠️ 가중치 불일치 — 없는 키 {len(missing)}개 / 남는 키 {len(unexpected)}개")
        if len(missing) > len(state) // 2:
            raise SystemExit("❌ 체크포인트가 이 모델 구조와 맞지 않는다")
    model.eval()
    inference = Inference(model, window="whole")
    if DEVICE == "cuda":
        inference.to(torch.device("cuda"))
    print(f"체크포인트 적용: {checkpoint}")
    return inference


def read_trials(path: str) -> list[tuple[int, tuple, tuple]]:
    out = []
    with open(path, encoding="utf-8") as f:
        next(f)                                   # 헤더
        for line in f:
            label, z1, m1, z2, m2 = line.rstrip("\n").split("\t")
            out.append((int(label), (z1, m1), (z2, m2)))
    return out


def embed_all(keys: set[tuple], identifier) -> dict[tuple, np.ndarray]:
    """필요한 발화의 임베딩을 한 번씩만 뽑는다. zip은 경로별로 한 번만 연다."""
    by_zip: dict[str, list[tuple]] = defaultdict(list)
    for zip_path, member in keys:
        by_zip[zip_path].append((zip_path, member))

    cache: dict[tuple, np.ndarray] = {}
    failed = 0
    for zip_path, items in by_zip.items():
        with zipfile.ZipFile(zip_path) as z:
            for i, key in enumerate(items, 1):
                try:
                    audio, sr = sf.read(io.BytesIO(z.read(key[1])), dtype="float32")
                    if audio.ndim > 1:
                        audio = audio.mean(axis=1)
                    if sr != REALTIME_SAMPLE_RATE:
                        # 서버는 16kHz로 들어온 오디오를 다룬다. 표본율이 다르면
                        # 임베딩이 달라지므로 맞춰준다.
                        idx = np.linspace(0, len(audio) - 1,
                                          int(len(audio) * REALTIME_SAMPLE_RATE / sr))
                        audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
                    cache[key] = identifier.extract_embedding(audio)
                except Exception:
                    failed += 1
                if i % 200 == 0:
                    print(f"    {i}/{len(items)}")
        print(f"  임베딩 완료: {zip_path.split('/')[-1]} ({len(items)}건)")
    if failed:
        print(f"  ⚠️ {failed}건은 못 읽어 제외")
    return cache


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


def eer(labels: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    """EER과 그때의 문턱. 같은 사람 점수가 높을수록 좋은 점수 체계를 가정한다."""
    order = np.argsort(-scores)                   # 점수 높은 순
    lab = labels[order]
    n_pos, n_neg = int(lab.sum()), int((1 - lab).sum())
    # 문턱을 위에서부터 내리며 누적 — i번째까지 수락했을 때의 오류율
    tp = np.cumsum(lab)
    fp = np.cumsum(1 - lab)
    far = fp / n_neg                              # 다른 사람인데 수락한 비율
    frr = 1 - tp / n_pos                          # 같은 사람인데 거절한 비율
    i = int(np.nanargmin(np.abs(far - frr)))
    return float((far[i] + frr[i]) / 2), float(scores[order][i])


def min_dcf(labels: np.ndarray, scores: np.ndarray,
            p_target: float = 0.01, c_miss: float = 1.0, c_fa: float = 1.0) -> float:
    """운영 지점을 반영한 지표. EER은 같은 사람/다른 사람이 반반이라고 가정하지만,
    실제 회의에서는 '명단 밖 사람'이 훨씬 드물어 그 불균형을 반영한 값도 함께 본다."""
    order = np.argsort(-scores)
    lab = labels[order]
    n_pos, n_neg = int(lab.sum()), int((1 - lab).sum())
    frr = 1 - np.cumsum(lab) / n_pos
    far = np.cumsum(1 - lab) / n_neg
    dcf = c_miss * frr * p_target + c_fa * far * (1 - p_target)
    return float(dcf.min() / min(c_miss * p_target, c_fa * (1 - p_target)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", default="trials_aihub.tsv")
    parser.add_argument("--checkpoint", default=None,
                        help="파인튜닝 가중치. 없으면 서버가 쓰는 사전학습 모델 그대로")
    args = parser.parse_args()

    trials = read_trials(args.trials)
    keys = {k for _, a, b in trials for k in (a, b)}
    print(f"시험 쌍 {len(trials)}개 / 서로 다른 발화 {len(keys)}건")

    identifier = LiveSpeakerIdentifier(load_inference(args.checkpoint))
    cache = embed_all(keys, identifier)

    labels, scores = [], []
    skipped = 0
    for label, a, b in trials:
        if a not in cache or b not in cache:
            skipped += 1
            continue
        labels.append(label)
        scores.append(cosine(cache[a], cache[b]))
    labels, scores = np.array(labels), np.array(scores, dtype=float)
    if skipped:
        print(f"⚠️ 임베딩이 없어 건너뛴 쌍 {skipped}개")

    value, threshold = eer(labels, scores)
    dcf = min_dcf(labels, scores)
    pos, neg = scores[labels == 1], scores[labels == 0]

    print()
    print("=" * 62)
    print(f"EER        {value * 100:.2f}%   (문턱 {threshold:.3f})")
    print(f"minDCF     {dcf:.4f}   (p_target=0.01)")
    print("-" * 62)
    print(f"같은 사람  평균 {pos.mean():.3f}  (쌍 {len(pos)}개)")
    print(f"다른 사람  평균 {neg.mean():.3f}  (쌍 {len(neg)}개)")
    print(f"격차       {pos.mean() - neg.mean():+.3f}")
    print("=" * 62)
    print()
    print("판단 기준 (측정 전에 정해둔 것)")
    print("  EER > 5%   → 한국어에서 확실히 나쁨. 임베딩 모델 학습에 값이 있다")
    print("  EER 2~5%   → 애매. 학습하되 기대치를 낮게")
    print("  EER < 2%   → 이미 충분히 좋음. 학습 접고 판정 방식(순위+격차) 쪽으로")
    print()
    print(f"참고: 서버의 절대 하한은 {os.getenv('SPEAKER_ABSOLUTE_FLOOR', '0.35')}이다.")
    print("      위 '문턱'과 크게 다르면, 하한이 이 모델의 점수 분포와 안 맞는다는 뜻이다.")


if __name__ == "__main__":
    main()
