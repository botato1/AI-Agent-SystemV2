"""
Whisper(large-v3) LoRA 파인튜닝.

여러 매니페스트(jsonl)를 합쳐서 학습한다:
- 팀원 낭독 녹음 매니페스트 (make_manifest.py 결과) — {"audio": 절대경로, "text": ..., ...}
- AI Hub 매니페스트 (make_manifest_aihub.py 결과) — {"audio_zip": ..., "audio_member": ..., "text": ...}
둘 다 로더에서 자동 구분해서 읽는다 (AI Hub는 33GB급 zip을 재압축 해제하지 않고 zip에서 직접 읽음).

베이스라인(evaluate_wer.py)에 쓴 테스트셋은 절대 이 학습 매니페스트에 섞으면 안 됨 —
README.md의 규칙대로 팀원 녹음 중 20%는 따로 빼서 테스트 전용으로 보관할 것.

사용법:
  python train_lora.py \
    --manifests manifest.jsonl manifest_aihub.jsonl \
    --output-dir ./lora_checkpoints \
    --epochs 3 --batch-size 4
"""
import argparse
import json
import os
import random
import zipfile

import numpy as np
import soundfile as sf
import torch
import torchaudio
from peft import LoraConfig, get_peft_model
from transformers import (
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
    WhisperForConditionalGeneration,
    WhisperProcessor,
)

TARGET_SR = 16000
MODEL_ID = "openai/whisper-large-v3"


def load_entries(manifest_paths):
    entries = []
    for path in manifest_paths:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    return entries


def _load_audio(entry) -> np.ndarray:
    """entry 종류(로컬 파일 vs AI Hub zip 내부)에 따라 오디오를 읽어 16kHz mono float32로 반환."""
    if "audio_zip" in entry:
        with zipfile.ZipFile(entry["audio_zip"]) as z:
            with z.open(entry["audio_member"]) as f:
                audio, sr = sf.read(f, dtype="float32")
    else:
        audio, sr = sf.read(entry["audio"], dtype="float32")

    if audio.ndim > 1:  # 스테레오 → 모노
        audio = audio.mean(axis=1)
    if sr != TARGET_SR:
        audio_t = torch.from_numpy(audio).unsqueeze(0)
        audio_t = torchaudio.functional.resample(audio_t, sr, TARGET_SR)
        audio = audio_t.squeeze(0).numpy()
    return audio


class WhisperFinetuneDataset(torch.utils.data.Dataset):
    def __init__(self, entries, processor):
        self.entries = entries
        self.processor = processor

    def __len__(self):
        return len(self.entries)

    def __getitem__(self, idx):
        entry = self.entries[idx]
        audio = _load_audio(entry)
        input_features = self.processor.feature_extractor(
            audio, sampling_rate=TARGET_SR
        ).input_features[0]
        labels = self.processor.tokenizer(entry["text"]).input_ids
        return {"input_features": input_features, "labels": labels}


class DataCollatorSpeechSeq2SeqWithPadding:
    def __init__(self, processor):
        self.processor = processor
        # 주의: Whisper 라벨의 실제 시작 토큰은 tokenizer.bos_token_id(50257)가 아니라
        # <|startoftranscript|>(50258)임 — 이 둘을 착각하면 아래 중복 토큰 제거 조건이
        # 항상 False가 되어 절대 실행되지 않고, 학습 내내 디코더 입력에 시작 토큰이
        # 중복으로 들어가는 상태가 유지됨 (epoch이 늘수록 이 잘못된 패턴이 강화되어
        # 생성이 붕괴함 — 실측: 3epoch 경미한 성능 저하, 5epoch 완전 붕괴로 확인됨).
        self._start_token_id = processor.tokenizer.convert_tokens_to_ids("<|startoftranscript|>")

    def __call__(self, features):
        input_features = [{"input_features": f["input_features"]} for f in features]
        batch = self.processor.feature_extractor.pad(input_features, return_tensors="pt")

        label_features = [{"input_ids": f["labels"]} for f in features]
        labels_batch = self.processor.tokenizer.pad(label_features, return_tensors="pt")
        labels = labels_batch["input_ids"].masked_fill(labels_batch.attention_mask.ne(1), -100)

        # 시작 토큰이 라벨 맨 앞에 이미 붙어있으면(항상 그럼), 모델이 forward 시 자동으로
        # 한 번 더 붙이는 것과 중복되므로 여기서 제거
        if (labels[:, 0] == self._start_token_id).all().cpu().item():
            labels = labels[:, 1:]

        batch["labels"] = labels
        return batch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifests", nargs="+", required=True, help="학습에 쓸 manifest.jsonl 경로들")
    parser.add_argument("--output-dir", default="./lora_checkpoints")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--val-ratio", type=float, default=0.05, help="학습 중 모니터링용 내부 검증 비율")
    parser.add_argument("--lora-r", type=int, default=32)
    parser.add_argument("--lora-alpha", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    entries = load_entries(args.manifests)
    if not entries:
        raise SystemExit("매니페스트에서 항목을 하나도 못 읽음 — 경로 확인 필요")
    print(f"전체 학습 항목: {len(entries)}개 (출처: {set(e.get('source', 'recording') for e in entries)})")

    random.seed(args.seed)
    random.shuffle(entries)
    n_val = max(1, int(len(entries) * args.val_ratio))
    val_entries = entries[:n_val]
    train_entries = entries[n_val:]
    print(f"학습 {len(train_entries)}개 / 내부 검증(모니터링용) {len(val_entries)}개")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = WhisperProcessor.from_pretrained(MODEL_ID, language="korean", task="transcribe")

    model = WhisperForConditionalGeneration.from_pretrained(
        MODEL_ID, torch_dtype=torch.float16 if device == "cuda" else torch.float32
    )
    model.generation_config.language = "korean"
    model.generation_config.task = "transcribe"
    model.generation_config.forced_decoder_ids = None

    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.05,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    train_dataset = WhisperFinetuneDataset(train_entries, processor)
    val_dataset = WhisperFinetuneDataset(val_entries, processor)
    data_collator = DataCollatorSpeechSeq2SeqWithPadding(processor)

    training_args = Seq2SeqTrainingArguments(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate,
        num_train_epochs=args.epochs,
        fp16=(device == "cuda"),
        eval_strategy="steps",
        eval_steps=200,
        save_strategy="steps",
        save_steps=200,
        save_total_limit=3,
        logging_steps=25,
        predict_with_generate=True,
        generation_max_length=225,
        report_to=[],
        remove_unused_columns=False,
        label_names=["labels"],
    )

    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=data_collator,
    )

    trainer.train()

    model.save_pretrained(os.path.join(args.output_dir, "final_adapter"))
    processor.save_pretrained(os.path.join(args.output_dir, "final_adapter"))
    print(f"✅ LoRA 어댑터 저장 완료: {os.path.join(args.output_dir, 'final_adapter')}")


if __name__ == "__main__":
    main()
