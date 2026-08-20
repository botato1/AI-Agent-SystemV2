"""
recording_script.txt(script_sentences.json)를 TTS로 음성 합성해 팀원 녹음을 보완한다.

TTS 음성은 실제 회의 음성보다 훨씬 깨끗해서 완전한 대체는 아니지만, AI Hub 데이터에
전혀 없는 개발 용어(레이턴시/임베딩/파인튜닝 등)의 발음을 모델에 노출시키는 용도로는
유효함 — 실제 녹음이 쌓이기 전까지의 보조 데이터.

여러 목소리로 뽑아 발음 다양성을 조금이라도 확보하고, 파일명 규칙({이름}_{번호}.wav)을
make_manifest.py와 동일하게 맞춰서 기존 매니페스트 스크립트를 그대로 재사용한다.

사용법:
  python generate_tts_recordings.py --output-dir ./tts_recordings
"""
import argparse
import asyncio
import json
import os
import subprocess

import edge_tts

VOICES = {
    "tts여성1": "ko-KR-SunHiNeural",
    "tts남성1": "ko-KR-InJoonNeural",
}


async def synthesize(text: str, voice: str, out_path: str):
    # edge-tts는 확장자와 무관하게 mp3 바이트를 그대로 반환하므로, 학습 파이프라인이
    # 기대하는 16kHz mono WAV로 ffmpeg를 거쳐 변환한다 (recording_script.txt 안내와 동일 규칙).
    tmp_mp3 = out_path + ".tmp.mp3"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(tmp_mp3)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp_mp3, "-ar", "16000", "-ac", "1", out_path],
        check=True,
    )
    os.remove(tmp_mp3)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="./tts_recordings")
    parser.add_argument(
        "--sentences",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "script_sentences.json"),
    )
    args = parser.parse_args()

    with open(args.sentences, encoding="utf-8") as f:
        sentences = json.load(f)

    os.makedirs(args.output_dir, exist_ok=True)

    total = len(sentences) * len(VOICES)
    done = 0
    for speaker_name, voice in VOICES.items():
        for number, text in sentences.items():
            out_path = os.path.join(args.output_dir, f"{speaker_name}_{number}.wav")
            await synthesize(text, voice, out_path)
            done += 1
            print(f"[{done}/{total}] {out_path}")

    print(f"완료: {args.output_dir}에 {total}개 파일 생성됨")
    print("다음 단계: python make_manifest.py --recordings", args.output_dir, "--output manifest_tts.jsonl")


if __name__ == "__main__":
    asyncio.run(main())
