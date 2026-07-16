"""
Model1(decision_judgment) QLoRA 파인튜닝 스크립트

사용법:
    python train.py --dataset dataset_tone_train.jsonl --out ./model_output

베이스 모델: Qwen2.5-7B-Instruct
방식: Unsloth + QLoRA (4bit)
"""

import argparse
import json
from pathlib import Path

from datasets import Dataset
from unsloth import FastLanguageModel, is_bfloat16_supported
from trl import SFTTrainer
from transformers import TrainingArguments


def load_dataset(path: Path) -> Dataset:
    """instruction/input/output 형식 jsonl -> HF Dataset."""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
    print(f"데이터 {len(records)}개 로드: {path}")
    return Dataset.from_list(records)


def format_prompt(example: dict, tokenizer) -> dict:
    """instruction+input -> Qwen2.5 chat template로 변환, output을 정답으로 붙임."""
    messages = [
        {"role": "user", "content": f"{example['instruction']}\n\n{example['input']}"},
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    full_text = prompt + example["output"] + tokenizer.eos_token
    return {"text": full_text}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, required=True, help="학습 데이터 jsonl 경로")
    parser.add_argument("--base_model", type=str, default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--out", type=str, default="./model_output")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch_size", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max_seq_length", type=int, default=1024)
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"베이스 모델 로드: {args.base_model}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
    )

    print("LoRA 어댑터 부착")
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        lora_alpha=16,
        lora_dropout=0,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    dataset = load_dataset(Path(args.dataset))
    dataset = dataset.map(lambda ex: format_prompt(ex, tokenizer))

    print(f"학습 시작 - epoch {args.epochs}, batch_size {args.batch_size}")
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=args.max_seq_length,
        args=TrainingArguments(
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=4,
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            fp16=not is_bfloat16_supported(),
            bf16=is_bfloat16_supported(),
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=42,
            output_dir=str(out_dir / "checkpoints"),
            save_strategy="epoch",
        ),
    )

    trainer.train()

    print(f"LoRA 어댑터 저장: {out_dir / 'lora_adapter'}")
    model.save_pretrained(str(out_dir / "lora_adapter"))
    tokenizer.save_pretrained(str(out_dir / "lora_adapter"))

    print(f"병합 모델(16bit) 저장: {out_dir / 'merged_model'}")
    model.save_pretrained_merged(
        str(out_dir / "merged_model"), tokenizer, save_method="merged_16bit"
    )

    print("학습 완료. 다음 단계: GGUF 변환 + Ollama 등록")
    print(f"  python llama.cpp/convert_hf_to_gguf.py {out_dir / 'merged_model'} --outfile {out_dir / 'model.gguf'}")


if __name__ == "__main__":
    main()