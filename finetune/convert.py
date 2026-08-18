import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

BASE_MODEL = r"C:\Users\bit\Desktop\AI-Agent-System\models\qwen_base"
LORA_DIR = str(BASE_DIR / "models" / "qwen2.5-7b-finetuned")
MERGED_DIR = str(BASE_DIR / "models" / "qwen2.5-merged")
GGUF_DIR = str(BASE_DIR / "models" / "gguf")

def convert():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    import torch

    print("베이스 모델 로딩 중...")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float16,
        device_map="cpu"
    )
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

    print("LoRA 어댑터 병합 중...")
    model = PeftModel.from_pretrained(model, LORA_DIR)
    model = model.merge_and_unload()

    print("병합 모델 저장 중...")
    os.makedirs(MERGED_DIR, exist_ok=True)
    model.save_pretrained(MERGED_DIR)
    tokenizer.save_pretrained(MERGED_DIR)
    print(f"병합 완료: {MERGED_DIR}")

    print("\n이제 아래 명령어로 GGUF 변환하세요")
    llama_cpp = r"C:\Users\bit\.unsloth\llama.cpp"
    print(f"python {llama_cpp}\\convert_hf_to_gguf.py {MERGED_DIR} --outfile {GGUF_DIR}\\dev-assistant.gguf --outtype q4_k_m")

if __name__ == "__main__":
    convert()