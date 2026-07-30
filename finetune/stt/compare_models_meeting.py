"""
실제 회의 녹음으로 모델을 나란히 비교.

파일 벤치마크(AI-Hub, 낭독 녹음)는 두 모델이 서로 다른 데이터에서 이기는 상황을
정리해주지 못했다. 팀 용어·포트 번호·자연발화·발화 누락이 한꺼번에 들어있는
실제 회의 오디오로 직접 봐야 판단이 된다.

정답 텍스트가 없으므로 CER을 낼 수 없다 — 전사문을 사람이 읽고 비교하는 용도다.
회의 폴더의 transcript.json(실시간으로 만들어진 결과)도 같이 출력해서, 실시간
경로와 파일 경로의 차이도 눈에 보이게 한다.

사용법:
  python compare_models_meeting.py --meeting <회의폴더명> \
      --models openai/whisper-large-v3 Qwen/Qwen3-ASR-1.7B-hf \
      --context terms.txt
"""
import argparse
import json
import os
import sys
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import MEETINGS_DIR, WHISPER_LANGUAGE  # noqa: E402
from evaluate_wer import load_model  # noqa: E402


def audio_files(meeting_dir: str, tracks_only: bool) -> list[tuple[str, str]]:
    """(라벨, 경로) 목록. 참가자별 트랙이 있으면 그걸 우선한다."""
    names = sorted(os.listdir(meeting_dir))
    tracks = [n for n in names if n.startswith("track_") and n.endswith(".wav")]
    if tracks:
        picked = [(n[len("track_"):-len(".wav")], os.path.join(meeting_dir, n)) for n in tracks]
        if tracks_only:
            return picked
        return picked + [("전체", os.path.join(meeting_dir, "audio.wav"))]
    return [("전체", os.path.join(meeting_dir, "audio.wav"))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True, help="회의 폴더명 (meetings/ 아래)")
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--context", default=None, help="컨텍스트 바이어싱 텍스트 파일")
    parser.add_argument("--beam-size", type=int, default=1)
    parser.add_argument("--tracks-only", action="store_true", help="전체 오디오는 건너뛰고 참가자별 트랙만")
    args = parser.parse_args()

    meeting_dir = os.path.join(MEETINGS_DIR, args.meeting)
    if not os.path.isdir(meeting_dir):
        raise SystemExit(f"❌ 회의 폴더 없음: {meeting_dir}")

    context = None
    if args.context:
        with open(args.context, encoding="utf-8") as f:
            context = " ".join(ln.strip() for ln in f if ln.strip() and not ln.startswith("#"))

    targets = audio_files(meeting_dir, args.tracks_only)
    print(f"회의: {args.meeting}")
    print(f"대상 오디오: {', '.join(label for label, _ in targets)}")
    print(f"컨텍스트: {'있음 (' + str(len(context)) + '자)' if context else '없음'}")

    # 실시간 경로가 남긴 결과 — 파일 전사와 비교할 기준점
    tj = os.path.join(meeting_dir, "transcript.json")
    if os.path.exists(tj):
        with open(tj, encoding="utf-8") as f:
            live = json.load(f)
        segs = live.get("segments") or live.get("turns") or []
        print(f"\n{'='*70}\n[실시간 결과 (회의 중 생성)]\n{'='*70}")
        for s in segs:
            who = s.get("speaker") or "?"
            print(f"  {who}: {s.get('text', '').strip()}")

    for model_id in args.models:
        print(f"\n{'='*70}\n[{model_id}]{'  + 컨텍스트' if context else ''}\n{'='*70}")
        model = load_model(model_id)
        for label, path in targets:
            started = time.monotonic()
            segments, _info = model.transcribe(
                path,
                language=WHISPER_LANGUAGE,
                beam_size=args.beam_size,
                vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt=context,
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            print(f"  ── {label} ({time.monotonic() - started:.1f}초)")
            print(f"     {text}")
        del model  # 다음 모델 로드 전에 GPU 메모리 반납


if __name__ == "__main__":
    main()
