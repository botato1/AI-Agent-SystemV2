"""
화자 임베딩 모델 후보들을 **우리 회의 오디오로** 나란히 비교한다.

왜 필요한가 (2026-08-18):
  파인튜닝은 도메인 과적합으로 접었다. 남은 길은 **더 나은 기성 모델로 갈아끼우는 것**이고,
  문헌상 우리가 쓰는 wespeaker-resnet34-LM(VoxCeleb EER 1% 안팎)보다 확실히 나은 것들이 있다
  (WavLM-ECAPA-TDNN은 ESPnet-SPK 보고 기준 Vox1-O EER 0.39%).

  그런데 **VoxCeleb 점수는 우리 점수가 아니다.** 오늘 확인했듯 AI-Hub EER이 좋아진
  모델이 우리 회의에서는 나빠졌다. 그러니 후보를 우리 오디오로 직접 재야 한다.

무엇을 재나 — **교차 회의 EER**:
  같은 사람 쌍은 **서로 다른 회의**에서 뽑는다. 우리 실제 과제가 그것이기 때문이다 —
  등록은 지난 회의에서 하고 판정은 이번 회의에서 한다. 같은 회의 안에서만 재면
  녹음 환경이 같아 실제보다 쉬운 시험이 된다.

  함께 출력하는 프로필 유사도 표는 "누가 누구와 헷갈리는가"를 보여준다.
  우리 실패 지점은 김나연↔이승주(현재 0.606)다.

⚠️ 모델마다 로더가 다르다. pyannote는 wespeaker 계열만 감싸고, ECAPA는 speechbrain,
   WavLM은 transformers를 쓴다. 설치가 안 된 백엔드는 건너뛰고 이유를 알린다.

⚠️ 여기서 좋아 보여도 **cpCER로 확인하기 전에는 채택하지 않는다.**
   오늘 파인튜닝이 그 함정이었다(EER 9.68% → 7.63%인데 회의에서는 악화).

사용법:
  python probe_embedding_models.py --meetings <회의ID>:<대본> ...
"""
import argparse
import os
import sys
from collections import defaultdict

import numpy as np
import soundfile as sf

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

from stt.core.config import MEETINGS_DIR, HF_TOKEN, DEVICE  # noqa: E402
from probe_score_norm import truth_spans  # noqa: E402

SAMPLE_RATE = 16000
MIN_SPAN_SEC = 1.0

# (표시 이름, 백엔드, 모델 ID)
CANDIDATES = [
    ("wespeaker-resnet34-LM (현재)", "pyannote", "pyannote/wespeaker-voxceleb-resnet34-LM"),
    ("ECAPA-TDNN (speechbrain)", "speechbrain", "speechbrain/spkrec-ecapa-voxceleb"),
    ("ResNet-TDNN (speechbrain)", "speechbrain", "speechbrain/spkrec-resnet-voxceleb"),
    ("WavLM base+ SV", "transformers", "microsoft/wavlm-base-plus-sv"),
]


def unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n else v


def make_extractor(backend: str, model_id: str):
    """모델 ID를 받아 (numpy 오디오 → 임베딩) 함수를 돌려준다.

    백엔드마다 API가 달라서 여기서 흡수한다. 설치 안 된 것은 예외를 그대로 올린다.
    """
    import torch

    if backend == "pyannote":
        from pyannote.audio import Model, Inference
        model = Model.from_pretrained(model_id, use_auth_token=HF_TOKEN)
        inference = Inference(model, window="whole")
        if DEVICE == "cuda":
            inference.to(torch.device("cuda"))

        def run(audio: np.ndarray) -> np.ndarray:
            wav = torch.from_numpy(audio.reshape(1, -1).astype(np.float32))
            return np.asarray(inference({"waveform": wav, "sample_rate": SAMPLE_RATE})).reshape(-1)

    elif backend == "speechbrain":
        from speechbrain.inference.speaker import EncoderClassifier
        enc = EncoderClassifier.from_hparams(
            source=model_id, savedir=os.path.join("/tmp", model_id.replace("/", "_")),
            run_opts={"device": DEVICE})

        def run(audio: np.ndarray) -> np.ndarray:
            wav = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
            return enc.encode_batch(wav).detach().cpu().numpy().reshape(-1)

    elif backend == "transformers":
        from transformers import AutoFeatureExtractor, WavLMForXVector
        fe = AutoFeatureExtractor.from_pretrained(model_id)
        model = WavLMForXVector.from_pretrained(model_id).to(DEVICE).eval()

        def run(audio: np.ndarray) -> np.ndarray:
            inputs = fe(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt")
            inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
            with torch.no_grad():
                return model(**inputs).embeddings.cpu().numpy().reshape(-1)

    else:
        raise ValueError(f"모르는 백엔드: {backend}")

    return run


def collect(specs, extract) -> dict[tuple[str, str], list[np.ndarray]]:
    """(화자, 회의) → 임베딩 목록."""
    out: dict[tuple[str, str], list[np.ndarray]] = defaultdict(list)
    for meeting, script in specs:
        audio, sr = sf.read(os.path.join(MEETINGS_DIR, meeting, "audio.wav"), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        for speaker, start, end in truth_spans(meeting, script):
            if end - start < MIN_SPAN_SEC:
                continue
            clip = audio[int(start * sr):int(end * sr)]
            out[(speaker, meeting)].append(unit(extract(clip)))
    return out


def eer_from(labels: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    order = np.argsort(-scores)
    lab = labels[order]
    n_pos, n_neg = int(lab.sum()), int((1 - lab).sum())
    if not n_pos or not n_neg:
        return float("nan"), float("nan")
    far = np.cumsum(1 - lab) / n_neg
    frr = 1 - np.cumsum(lab) / n_pos
    i = int(np.nanargmin(np.abs(far - frr)))
    return float((far[i] + frr[i]) / 2), float(scores[order][i])


def evaluate(embs: dict[tuple[str, str], list[np.ndarray]]):
    """교차 회의 EER과 프로필 유사도 표."""
    # 같은 사람 쌍은 **다른 회의**에서만 만든다 — 등록과 판정이 다른 회의인 실제 상황
    labels, scores = [], []
    keys = sorted(embs)
    for i, (s1, m1) in enumerate(keys):
        for (s2, m2) in keys[i:]:
            if m1 == m2:
                continue
            for a in embs[(s1, m1)]:
                for b in embs[(s2, m2)]:
                    labels.append(1 if s1 == s2 else 0)
                    scores.append(float(np.dot(a, b)))
    labels, scores = np.array(labels), np.array(scores, dtype=float)
    value, threshold = eer_from(labels, scores)

    # 프로필: 회의 안에서 평균 → 회의들끼리 평균 (enroll_multi_meeting과 같은 방식)
    per_speaker: dict[str, list[np.ndarray]] = defaultdict(list)
    for (spk, _), vecs in embs.items():
        per_speaker[spk].append(unit(np.mean(vecs, axis=0)))
    profiles = {s: unit(np.mean(v, axis=0)) for s, v in per_speaker.items()}
    return value, threshold, labels, scores, profiles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meetings", nargs="+", required=True, help="'회의ID:대본경로'")
    parser.add_argument("--only", nargs="*", default=None,
                        help="이 이름이 들어간 후보만 시험 (부분 일치)")
    args = parser.parse_args()

    specs = []
    for spec in args.meetings:
        meeting, script = spec.split(":", 1)
        specs.append((meeting, os.path.join(_HERE, script)))

    rows = []
    for name, backend, model_id in CANDIDATES:
        if args.only and not any(o in name for o in args.only):
            continue
        print(f"\n{'=' * 70}\n{name}  [{backend}] {model_id}\n{'=' * 70}")
        try:
            extract = make_extractor(backend, model_id)
        except Exception as e:
            print(f"  ⏭️ 건너뜀 — {type(e).__name__}: {str(e)[:160]}")
            if backend == "speechbrain":
                print("     (speechbrain 미설치라면: pip install speechbrain)")
            continue

        try:
            embs = collect(specs, extract)
        except Exception as e:
            print(f"  ❌ 임베딩 추출 실패 — {type(e).__name__}: {str(e)[:160]}")
            continue

        value, threshold, labels, scores, profiles = evaluate(embs)
        pos, neg = scores[labels == 1], scores[labels == 0]

        order = sorted(profiles)
        worst = (-1.0, "", "")
        for i, a in enumerate(order):
            for b in order[i + 1:]:
                sim = float(np.dot(profiles[a], profiles[b]))
                if sim > worst[0]:
                    worst = (sim, a, b)

        print(f"  교차 회의 EER  {value * 100:.2f}%   (문턱 {threshold:.3f})")
        print(f"  같은 사람 평균 {pos.mean():.3f} / 다른 사람 평균 {neg.mean():.3f} "
              f"/ 격차 {pos.mean() - neg.mean():+.3f}")
        print(f"  가장 헷갈리는 짝: {worst[1]} ↔ {worst[2]} = {worst[0]:.3f}")
        rows.append((name, value, worst[0], f"{worst[1]}↔{worst[2]}"))

    if not rows:
        raise SystemExit("\n시험한 모델이 없다")

    print(f"\n{'=' * 78}")
    print(f"{'모델':34s}{'교차회의 EER':>14s}{'최악 짝 유사도':>16s}  짝")
    print("-" * 78)
    for name, value, worst_sim, pair in sorted(rows, key=lambda r: r[1]):
        print(f"{name:34s}{value * 100:13.2f}%{worst_sim:16.3f}  {pair}")
    print()
    print("읽는 법")
    print("  EER이 낮고 최악 짝 유사도가 낮은 모델이 좋다. 둘이 어긋나면 짝 유사도를 우선한다")
    print("  — 우리 실패는 '평균적으로 못한다'가 아니라 '특정 두 사람을 못 가른다'이기 때문.")
    print()
    print("⚠️ 여기서 좋아 보여도 cpCER로 확인하기 전에는 채택하지 말 것.")
    print("   오늘 파인튜닝이 그 함정이었다 — AI-Hub EER은 좋아졌는데 우리 회의는 나빠졌다.")


if __name__ == "__main__":
    main()
