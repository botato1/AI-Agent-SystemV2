"""
Model1(decision_judgment) QLoRA 파인튜닝 스크립트 (순수 transformers + peft)

[수정 - 2026.07.16] Unsloth의 FastLanguageModel.from_pretrained()가 자체
"Fast downloading" 로직에서 서버 네트워크 환경과 맞지 않아 멈추는 문제 발견
(캐시에 모델이 이미 있어도 무시하고 멈춤). 순수 transformers.AutoModelForCausalLM
으로는 캐시에서 정상 로드되는 것을 확인했으므로, Unsloth 의존성을 제거하고
transformers + peft(LoRA) + bitsandbytes(4bit)로 재작성함.
Unsloth 없이도 QLoRA 학습 자체는 동일하게 가능하다 (속도 최적화만 빠짐).

사용법:
    python train.py --dataset dataset_tone.jsonl --out ./model_output
"""

import argparse
import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from trl import SFTConfig, SFTTrainer


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
    parser.add_argument(
        "--base_model", type=str,
        default="unsloth/Qwen2.5-7B-Instruct-unsloth-bnb-4bit",
        help="4bit 사전양자화 모델 권장 (다운로드/VRAM 절약)",
    )
    parser.add_argument("--out", type=str, default="./model_output")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch_size", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max_seq_length", type=int, default=1024)
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"베이스 모델 로드: {args.base_model}")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )

    print("LoRA 어댑터 부착")
    model = prepare_model_for_kbit_training(model)
    lora_config = LoraConfig(
        r=16,
        lora_alpha=16,
        lora_dropout=0.0,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    dataset = load_dataset(Path(args.dataset))
    dataset = dataset.map(lambda ex: format_prompt(ex, tokenizer))

    print(f"학습 시작 - epoch {args.epochs}, batch_size {args.batch_size}")
    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        args=SFTConfig(
            dataset_text_field="text",
            max_length=args.max_seq_length,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=4,
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            bf16=True,
            logging_steps=1,
            optim="paged_adamw_8bit",
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

    print("학습 완료.")
    print("다음 단계: LoRA 병합 후 GGUF 변환 + Ollama 등록 필요")
    print(f"  (병합 스크립트는 merge_lora.py 참고)")


if __name__ == "__main__":
    main()
