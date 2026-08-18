import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from unsloth import FastLanguageModel

CHECKPOINT_DIR = str(BASE_DIR / "models" / "qwen2.5-7b-finetuned" / "checkpoint-225")
OUTPUT_DIR = str(BASE_DIR / "models" / "qwen2.5-7b-finetuned")

print("체크포인트 로딩 중...")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=CHECKPOINT_DIR,
    max_seq_length=2048,
    load_in_4bit=True,
)

print("모델 저장 중...")
os.makedirs(OUTPUT_DIR, exist_ok=True)
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print(f"저장 완료: {OUTPUT_DIR}")