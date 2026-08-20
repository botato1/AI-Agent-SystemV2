"""
화자 임베딩 모델을 한국어 회의 음성으로 파인튜닝한다 (AAM-softmax).

왜 하는가 (2026-08-18):
  화자 판정 개선 가설이 다섯 번 기각됐다 — 문턱 0.30/0.25/0.15, 점수 z정규화,
  회의 내 프로필 적응, 미상 구간을 경계로 인정하기. 전부 **판정이 끝난 뒤를 만졌다.**

  왜 다 실패했는지가 EER 측정으로 설명됐다:
    EER 지점의 문턱 0.340  vs  서버의 절대 하한 0.35 — 거의 같다.
  하한 0.35는 이미 이 모델의 EER 지점(두 오류가 균형을 이루는 곳)이었다. 거기서
  어느 쪽으로 움직여도 한쪽을 얻고 다른 쪽을 잃는다. **곡선 위를 오갔을 뿐 곡선을
  옮기지 못한 것이다.** 곡선을 옮기려면 모델 자체가 좋아져야 한다.

  그리고 옮길 여지가 있다: 같은 조건에서 잰 EER이 **9.68%**다. 영어(VoxCeleb)에서
  1% 안팎인 모델이 한국어 회의 음성에서 약 10배로 나빠진다. 다만 도메인 자체가 더
  어려우므로(회의실, 자유발화, 짧은 발화) 목표는 1%가 아니라 **5~7%대**로 잡는다.

무엇을 하는가:
  사전학습 가중치에서 **이어서** 학습한다(처음부터가 아니라). VoxCeleb 수십만 발화로
  배운 것을 버리고 20.7만 건으로 다시 하면 오히려 못 미친다.
  분류 머리(AAM-softmax)를 붙여 화자 2855명을 맞히게 학습시키고, 끝나면 머리는 버리고
  몸통(임베딩)만 쓴다 — 화자 임베딩 학습의 표준 방식이다.

⚠️ 가장 큰 위험은 **목소리 대신 녹음 환경을 외우는 것**이다.
   AI-Hub 화자는 세션 한정이라 한 사람이 한 회의에만 존재한다. 그래서 모델이
   "이 방에서 난 소리"를 단서로 화자를 맞혀도 학습 손실은 잘 줄어든다.

   두 겹으로 막는다:
     ① 증강 — 다른 회의의 소리를 잡음으로 섞고 이득을 흔들어 채널 단서를 흐린다
     ② **평가가 이 부정행위를 잡아낸다** — trials는 같은 회의 안에서만 만들어져
        같은 사람 쌍과 다른 사람 쌍이 방·마이크를 공유한다. 채널을 외운 모델은
        EER이 전혀 나아지지 않는다. 손실은 주는데 EER이 그대로면 그게 신호다.

⚠️ EER이 좋아져도 그것만으로 채택하지 않는다. 실제 목표는 회의록이므로 반드시
   우리 회의 cpCER을 함께 본다(sweep_speaker_floor.py). EER만 좋아지고 cpCER이
   그대로인 경우가 실제로 있다.

사용법:
  python train_speaker_embedding.py --manifest manifest_spk_train.jsonl --epochs 4
  # 끝나면
  python eval_speaker_eer.py --trials trials_aihub.tsv --checkpoint ckpt/best.pt
"""
import argparse
import io
import json
import math
import os
import random
import sys
import zipfile

import numpy as np
import soundfile as sf
import torch
import torch.nn as nn
import torch.nn.functional as F
from pyannote.audio import Model
from torch.utils.data import DataLoader, Dataset

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import HF_TOKEN, SPEAKER_EMBEDDING_MODEL  # noqa: E402

SAMPLE_RATE = 16000
_ZIPS: dict[str, zipfile.ZipFile] = {}      # 워커마다 따로 채워진다


def zip_handle(path: str) -> zipfile.ZipFile:
    """zip을 발화마다 새로 열면 매우 느려진다(전에 229배 느려진 적이 있다)."""
    if path not in _ZIPS:
        _ZIPS[path] = zipfile.ZipFile(path)
    return _ZIPS[path]


def read_audio(row: dict) -> np.ndarray:
    audio, sr = sf.read(io.BytesIO(zip_handle(row["audio_zip"]).read(row["audio_member"])),
                        dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio if sr == SAMPLE_RATE else audio      # AI-Hub는 전부 16kHz임을 확인함


class MeetingSpeakerSet(Dataset):
    def __init__(self, rows: list[dict], labels: dict[str, int],
                 crop_sec: float, augment: bool):
        self.rows = rows
        self.labels = labels
        self.crop = int(crop_sec * SAMPLE_RATE)
        self.augment = augment

    def __len__(self) -> int:
        return len(self.rows)

    def _crop(self, audio: np.ndarray) -> np.ndarray:
        if len(audio) <= self.crop:                   # 짧으면 뒤를 0으로 채운다
            return np.pad(audio, (0, self.crop - len(audio)))
        start = random.randint(0, len(audio) - self.crop)
        return audio[start:start + self.crop]

    def __getitem__(self, i: int):
        row = self.rows[i]
        try:
            audio = self._crop(read_audio(row))
        except Exception:
            audio = np.zeros(self.crop, dtype=np.float32)

        if self.augment:
            # 다른 회의의 소리를 잡음으로 섞는다 — 채널 단서를 흐리는 것이 목적이라
            # 잡음 데이터셋(MUSAN 등) 없이 가진 데이터만으로 한다.
            if random.random() < 0.5:
                try:
                    other = self._crop(read_audio(random.choice(self.rows)))
                    snr = random.uniform(5.0, 20.0)
                    p_s = float(np.mean(audio ** 2)) + 1e-10
                    p_n = float(np.mean(other ** 2)) + 1e-10
                    audio = audio + other * math.sqrt(p_s / (p_n * 10 ** (snr / 10)))
                except Exception:
                    pass
            audio = audio * random.uniform(0.5, 1.5)      # 이득 흔들기
            peak = float(np.max(np.abs(audio))) or 1.0
            if peak > 1.0:
                audio = audio / peak

        return torch.from_numpy(audio.astype(np.float32)), self.labels[row["speaker"]]


class AAMSoftmax(nn.Module):
    """각도 여백을 준 분류 머리. 같은 화자를 더 촘촘히 모아 임베딩을 쓸모 있게 만든다.

    보통의 softmax는 '맞히기만 하면' 되지만, 우리는 학습에 없던 사람도 코사인
    유사도로 구분해야 한다. 여백(margin)이 그 간격을 강제로 벌린다.
    """

    def __init__(self, dim: int, num_classes: int, scale: float = 30.0, margin: float = 0.2):
        super().__init__()
        self.weight = nn.Parameter(torch.empty(num_classes, dim))
        nn.init.xavier_normal_(self.weight)
        self.scale, self.margin = scale, margin

    def forward(self, emb: torch.Tensor, label: torch.Tensor) -> torch.Tensor:
        cos = F.linear(F.normalize(emb), F.normalize(self.weight)).clamp(-1 + 1e-7, 1 - 1e-7)
        theta = torch.acos(cos)
        target = torch.cos(theta + self.margin)
        one_hot = F.one_hot(label, self.weight.shape[0]).bool()
        return F.cross_entropy(self.scale * torch.where(one_hot, target, cos), label)


def embed(model: nn.Module, wav: torch.Tensor) -> torch.Tensor:
    out = model(wav.unsqueeze(1))                 # (batch, 1, samples)
    return out.reshape(out.shape[0], -1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="manifest_spk_train.jsonl")
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-4,
                        help="파인튜닝이라 낮게. 크게 주면 사전학습 지식이 지워진다")
    parser.add_argument("--crop-sec", type=float, default=3.0,
                        help="학습에 쓸 구간 길이. 회의 발화 길이와 맞춘다")
    parser.add_argument("--num-workers", type=int, default=8)
    parser.add_argument("--no-augment", action="store_true")
    parser.add_argument("--out-dir", default="ckpt_speaker")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    random.seed(args.seed)

    with open(args.manifest, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    speakers = sorted({r["speaker"] for r in rows})
    labels = {s: i for i, s in enumerate(speakers)}
    print(f"학습셋 {len(rows)}발화 / 화자 {len(speakers)}명")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = Model.from_pretrained(SPEAKER_EMBEDDING_MODEL, use_auth_token=HF_TOKEN).to(device)
    model.train()

    with torch.no_grad():                          # 임베딩 차원은 직접 재서 알아낸다
        dim = embed(model, torch.zeros(2, int(args.crop_sec * SAMPLE_RATE)).to(device)).shape[1]
    print(f"임베딩 차원 {dim} / 디바이스 {device}")

    head = AAMSoftmax(dim, len(speakers)).to(device)
    loader = DataLoader(
        MeetingSpeakerSet(rows, labels, args.crop_sec, not args.no_augment),
        batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers,
        pin_memory=True, drop_last=True, persistent_workers=args.num_workers > 0,
    )
    # 머리는 새로 만든 것이라 몸통보다 빠르게 배워야 한다
    optimizer = torch.optim.AdamW(
        [{"params": model.parameters(), "lr": args.lr},
         {"params": head.parameters(), "lr": args.lr * 10}], weight_decay=1e-5)
    total = args.epochs * len(loader)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=total)

    os.makedirs(args.out_dir, exist_ok=True)
    step, best = 0, float("inf")
    for epoch in range(1, args.epochs + 1):
        run_loss, run_acc, seen = 0.0, 0, 0
        for wav, label in loader:
            wav, label = wav.to(device, non_blocking=True), label.to(device, non_blocking=True)
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
                emb = embed(model, wav)
                loss = head(emb, label)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            scheduler.step()

            with torch.no_grad():
                pred = F.linear(F.normalize(emb.float()),
                                F.normalize(head.weight.float())).argmax(1)
                run_acc += int((pred == label).sum())
            run_loss += float(loss) * len(label)
            seen += len(label)
            step += 1
            if step % 100 == 0:
                print(f"  epoch {epoch} step {step}/{total} "
                      f"loss {run_loss / seen:.4f} acc {run_acc / seen:.3f} "
                      f"lr {scheduler.get_last_lr()[0]:.2e}", flush=True)

        avg = run_loss / max(seen, 1)
        print(f"[epoch {epoch}] loss {avg:.4f} / acc {run_acc / max(seen, 1):.3f}")
        torch.save(model.state_dict(), os.path.join(args.out_dir, f"epoch{epoch}.pt"))
        if avg < best:
            best = avg
            torch.save(model.state_dict(), os.path.join(args.out_dir, "best.pt"))
            print(f"  → best.pt 갱신 (loss {avg:.4f})")

    print()
    print(f"✅ 학습 완료 — {args.out_dir}/best.pt")
    print("다음: python eval_speaker_eer.py --trials trials_aihub.tsv "
          f"--checkpoint {args.out_dir}/best.pt")
    print("⚠️ 손실은 줄었는데 EER이 안 나아지면 목소리가 아니라 녹음 환경을 외운 것이다.")
    print("⚠️ EER이 나아져도 우리 회의 cpCER로 확인하기 전에는 채택하지 말 것.")


if __name__ == "__main__":
    main()
