"""
학습된 LoRA 어댑터를 베이스 모델에 병합 (GGUF 변환 전 단계)

Unsloth의 save_pretrained_merged()를 안 쓰므로, peft 표준 방식으로 병합.

사용법:
    python merge_lora.py --lora_adapter ./model_output/lora_adapter --out ./model_output/merged_model
"""

import argparse

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base_model", type=str, default="Qwen/Qwen2.5-7B-Instruct",
        help="병합은 원본(비양자화) 모델로 해야 함 - 4bit 사전양자화 저장소는 "
             "config.json에 quantization 설정이 박혀있어 순수 16bit 로드가 안 됨",
    )
    parser.add_argument("--lora_adapter", type=str, required=True)
    parser.add_argument("--out", type=str, required=True)
    args = parser.parse_args()

    print(f"베이스 모델 로드 (16bit, 병합용): {args.base_model}")
    base_model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)

    print(f"LoRA 어댑터 적용: {args.lora_adapter}")
    model = PeftModel.from_pretrained(base_model, args.lora_adapter)

    print("병합 중...")
    model = model.merge_and_unload()

    print(f"저장: {args.out}")
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)

    print("병합 완료. GGUF 변환 단계로 진행 가능:")
    print(f"  python llama.cpp/convert_hf_to_gguf.py {args.out} --outfile decision-judge-v1.gguf")


if __name__ == "__main__":
    main()