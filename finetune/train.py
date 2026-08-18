import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

MODEL_NAME = r"C:\Users\bit\Desktop\AI-Agent-System\models\qwen_base"
DATA_PATH = str(BASE_DIR / "data" / "finetune" / "train.jsonl")
OUTPUT_DIR = str(BASE_DIR / "models" / "qwen2.5-7b-finetuned")
MAX_SEQ_LENGTH = 2048
LOAD_IN_4BIT = True
LORA_R = 16
LORA_ALPHA = 32
BATCH_SIZE = 1
GRAD_ACCUMULATION = 4
EPOCHS = 3
LEARNING_RATE = 2e-4

def train():
    from unsloth import FastLanguageModel
    from datasets import load_dataset
    from trl import SFTTrainer
    from transformers import TrainingArguments

    print("모델 로딩 중...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=LOAD_IN_4BIT,
    )

    print("LoRA 설정 중...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing=True,
    )

    print("데이터 로딩 중...")
    dataset = load_dataset("json", data_files=DATA_PATH, split="train")

    def format_prompt(example):
        return {
            "text": f"""[INST] {example['instruction']}

입력: {example['input']} [/INST] {example['output']}"""
        }

    dataset = dataset.map(format_prompt)
    print(f"데이터 수: {len(dataset)}쌍")

    print("학습 시작...")
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        args=TrainingArguments(
            output_dir=OUTPUT_DIR,
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRAD_ACCUMULATION,
            num_train_epochs=EPOCHS,
            learning_rate=LEARNING_RATE,
            bf16=True,
            logging_steps=10,
            save_steps=999999,
            warmup_ratio=0.1,
            lr_scheduler_type="cosine",
            optim="adamw_8bit",
            report_to="none",
        ),
    )

    trainer.train()
    print("학습 완료!")

    print("모델 저장 중...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"저장 완료: {OUTPUT_DIR}")

if __name__ == "__main__":
    train()