"""
화자 임베딩 모델을 바꿔가며 **여러 회의의 cpCER**로 비교한다 (하나 빼기 등록).

왜 필요한가 (2026-08-20):
  probe_embedding_models.py로 후보 4개를 교차 회의 EER로 비교했더니 ResNet-TDNN
  (speechbrain)이 가장 좋았다(17.32% → 12.47%). 그런데 EER만 보고 채택하면 안 된다
  — 파인튜닝 때 EER은 좋아졌는데 우리 회의 cpCER은 오히려 나빠진 전례가 있다
  (EXPERIMENTS.md 파인튜닝 절). 실제 회의록 품질(cpCER)로 재확인해야 채택할 수 있다.

  임베딩 모델을 바꾸면 기존 목소리 프로필(옛 모델 벡터)이 새 모델과 호환되지
  않으므로, 모델마다 전역 프로필을 다시 만들고(enroll_multi_meeting과 같은
  "회의 안에서 평균 → 회의들끼리 평균" 방식, 하나 빼기 포함) 그 프로필로 각
  회의를 다시 재분석(refine)한 뒤 채점한다.

이 스크립트가 하는 일 (모델마다):
  1. 서버를 SPEAKER_EMBEDDING_MODEL=<모델>로 재기동
  2. 채점 대상 회의마다: 그 회의를 뺀 나머지 회의들로 전역 프로필 재생성
     (enroll_multi_meeting.py와 동일 로직을 인라인으로 수행)
  3. prepare_refine_rerun.py --profiles-from-global 로 그 회의의 profiles.npz를
     방금 만든 전역 프로필로 교체
  4. refine을 force로 다시 돌리고 meeteval_score.py로 cpCER 채점

⚠️ 회의당 재분석은 무거운 GPU 작업이다 — 모델 수 × 회의 수만큼 반복되므로
   시간이 꽤 걸린다(회의당 몇 분 단위). 오래 걸리면 nohup으로 백그라운드 실행 권장.

⚠️ 끝나면 서버가 마지막 모델로 떠 있다. 채택한 모델로 다시 띄우고, 실제 배포용
   전역 프로필도 그 모델로 다시 등록해야 한다(--exclude 없이 전 회의로 — NEXT.md 참고).

사용법:
  python probe_embedding_swap.py \
      --meetings ded1105f-...:scripts/launch_plan_meeting.txt \
                 ba8f38c4-...:scripts/search_quality_meeting.txt \
                 8b5f84b7-...:scripts/retention_meeting.txt \
      --enroll-extra 36256894-...:scripts/demo_prep_meeting.txt \
      --models pyannote/wespeaker-voxceleb-resnet34-LM speechbrain/spkrec-resnet-voxceleb
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict

import numpy as np
import soundfile as sf

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

from stt.core.config import MEETINGS_DIR  # noqa: E402
from probe_score_norm import truth_spans  # noqa: E402

MIN_SPAN_SEC = 1.0


def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n else v


def restart(model: str) -> bool:
    """서버를 지정한 임베딩 모델로 다시 띄운다. 하한 등 다른 설정은 기존 기본값 그대로."""
    sh("kill $(pgrep -f 'uvicorn stt.main:app') 2>/dev/null")
    time.sleep(5)
    subprocess.Popen(
        f"cd {os.path.join(_REPO_ROOT, 'backend', 'modules')} && "
        f"SPEAKER_EMBEDDING_MODEL={model} nohup python -u -m uvicorn stt.main:app "
        f"--host 0.0.0.0 --port 8002 >> /tmp/stt.log 2>&1 &", shell=True,
    )
    for _ in range(40):
        time.sleep(5)
        if sh("curl -s -o /dev/null -w '%{http_code}' http://localhost:8002/docs") == "200":
            return True
    return False


def _load_inference_for(model: str):
    """
    지정한 모델 ID로 임베딩 추론 객체를 직접 만든다.

    ⚠️ load_speaker_embedding_inference()를 안 쓰는 이유(2026-08-20 버그로 발견):
    그 함수는 config.SPEAKER_EMBEDDING_MODEL(모듈 임포트 시점에 딱 한 번 env var를
    읽어 고정된 값)을 본다. restart()가 서버 subprocess에 환경변수를 넘겨도
    **이 스크립트 자신의 프로세스 환경은 안 바뀌므로** 그 함수를 쓰면 항상 기본값
    (pyannote)으로 프로필을 만들게 된다 — 실제로 이 버그 때문에 speechbrain 비교가
    화자대가 94~102%로 완전히 깨졌었다(전사만 멀쩡, DI-cpCER 정상 — 그게 단서였다).
    모델을 인자로 직접 받아 서버와 반드시 같은 모델을 쓰도록 강제한다.
    """
    if model.startswith("speechbrain/"):
        from stt.services.speaker_id_service import SpeechBrainEmbedding
        return SpeechBrainEmbedding(model)
    import torch
    from pyannote.audio import Model, Inference
    from stt.core.config import HF_TOKEN, DEVICE
    pt_model = Model.from_pretrained(model, use_auth_token=HF_TOKEN)
    inference = Inference(pt_model, window="whole")
    if DEVICE == "cuda":
        inference.to(torch.device("cuda"))
    return inference


def build_profiles(specs: list[tuple[str, str]], exclude: str, model: str) -> dict[str, np.ndarray]:
    """exclude를 뺀 나머지 회의들로 전역 프로필을 만든다 (enroll_multi_meeting과 같은 방식).

    model은 이번 반복에서 서버에 띄운 것과 반드시 같은 모델 ID여야 한다 —
    _load_inference_for() 문서 참고.
    """
    from stt.services.speaker_id_service import LiveSpeakerIdentifier
    identifier = LiveSpeakerIdentifier(_load_inference_for(model))

    per_meeting: dict[str, dict[str, np.ndarray]] = {}
    for meeting, script in specs:
        if meeting.startswith(exclude[:8]):
            continue
        audio, sr = sf.read(os.path.join(MEETINGS_DIR, meeting, "audio.wav"), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        embs: dict[str, list[np.ndarray]] = defaultdict(list)
        for speaker, start, end in truth_spans(meeting, script):
            if end - start < MIN_SPAN_SEC:
                continue
            clip = audio[int(start * sr):int(end * sr)]
            embs[speaker].append(unit(identifier.extract_embedding(clip)))
        per_meeting[meeting] = {s: unit(np.mean(v, axis=0)) for s, v in embs.items()}

    names = sorted({s for m in per_meeting.values() for s in m})
    profiles: dict[str, np.ndarray] = {}
    for name in names:
        vecs = [m[name] for m in per_meeting.values() if name in m]
        if vecs:
            profiles[name] = unit(np.mean(vecs, axis=0))
    return profiles


def refine_and_score(meeting: str, script: str, profiles: dict[str, np.ndarray]) -> dict:
    meeting_dir = os.path.join(MEETINGS_DIR, meeting)
    np.savez(os.path.join(meeting_dir, "profiles.npz"), **profiles)

    # profiles.npz는 위에서 이미 새 모델 벡터로 만들어뒀다 — --profiles-from-global을
    # 쓰면 그걸 덮어써버리므로 여기서는 refined 표시만 지우는 용도로 쓴다.
    sh(f"cd {_HERE} && python prepare_refine_rerun.py --meeting {meeting} 2>/dev/null")
    sh(f"curl -s -X POST 'http://localhost:8002/api/meetings/{meeting}/refine?force=1'")

    mt = sh(f"cd {_HERE} && python meeteval_score.py --meetings '{meeting}:{script}' 2>/dev/null")
    # meeteval_score.py 출력 열 순서: cpCER, DI-cpCER, ORC-CER, 화자대가, cpWER
    row = re.search(re.escape(meeting[:38]) + r"\s*([\d.]+)%\s*([\d.]+)%\s*([\d.]+)%\s*([\d.]+)%", mt)
    if not row:
        return {}
    return {"cpcer": float(row.group(1)), "di_cpcer": float(row.group(2)),
            "orc": float(row.group(3)), "speaker_cost": float(row.group(4))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meetings", nargs="+", required=True, help="채점 대상 '회의ID:대본'")
    parser.add_argument("--enroll-extra", nargs="*", default=[],
                         help="채점은 안 하지만 등록 재료로만 쓸 추가 회의 '회의ID:대본'")
    parser.add_argument("--models", nargs="+", required=True,
                         help="비교할 임베딩 모델 ID들 (pyannote/... 또는 speechbrain/...)")
    args = parser.parse_args()

    score_specs = [tuple(s.split(":", 1)) for s in args.meetings]
    all_specs = score_specs + [tuple(s.split(":", 1)) for s in args.enroll_extra]

    results: dict[str, dict[str, dict]] = {}
    for model in args.models:
        print(f"\n{'=' * 78}\n모델: {model}\n{'=' * 78}")
        if not restart(model):
            print("  ❌ 서버가 안 뜬다 — 중단"); break

        results[model] = {}
        for meeting, script in score_specs:
            print(f"\n  [{meeting[:38]}] 하나 빼기로 프로필 재생성...")
            profiles = build_profiles(all_specs, exclude=meeting, model=model)
            if not profiles:
                print("    ⚠️ 프로필 생성 실패 — 건너뜀"); continue
            print(f"    등록: {', '.join(sorted(profiles))}")
            r = refine_and_score(meeting, os.path.join(_HERE, script), profiles)
            if not r:
                print("    ⚠️ 채점 실패 — 건너뜀"); continue
            results[model][meeting] = r
            print(f"    cpCER {r['cpcer']:.2f}%  DI-cpCER {r['di_cpcer']:.2f}%  "
                  f"ORC-CER {r['orc']:.2f}%  화자대가 {r['speaker_cost']:.2f}%")

    print(f"\n{'=' * 78}\n요약 (cpCER, 글자 단위 — 낮을수록 좋음)\n{'=' * 78}")
    meetings = [m for m, _ in score_specs]
    header = "모델".ljust(38) + "".join(m[:8].rjust(10) for m in meetings) + "평균".rjust(10)
    print(header)
    for model, per_meeting in results.items():
        vals = [per_meeting.get(m, {}).get("cpcer") for m in meetings]
        cells = "".join(f"{v:9.2f}%" if v is not None else "     N/A" for v in vals)
        valid = [v for v in vals if v is not None]
        avg = f"{sum(valid) / len(valid):8.2f}%" if valid else "     N/A"
        print(model.ljust(38) + cells + avg)

    print()
    print("읽는 법")
    print("  회의별로 방향이 갈리면(한쪽만 좋아지면) 그 모델은 채택하지 말 것 — 특정")
    print("  회의 조건에 맞춘 것일 수 있다. 전 회의에서 일관되게 낮아야 채택 후보.")
    print()
    print("⚠️ 채택하기로 하면: 실제 배포용 전역 프로필도 이 모델로 다시 등록해야 한다")
    print("   (--exclude 없이 전 회의로, enroll_multi_meeting.py 사용 — NEXT.md 참고).")
    print("⚠️ 끝나면 서버가 마지막 모델로 떠 있다 — 채택 값으로 다시 띄울 것.")


if __name__ == "__main__":
    main()
