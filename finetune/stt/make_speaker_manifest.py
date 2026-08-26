"""
AI-Hub 회의 음성에서 **진짜 화자 라벨**이 붙은 매니페스트를 만든다.

왜 필요한가 (2026-08-18):
  manifest_aihub.jsonl의 speaker 필드는 경로에서 추측한 값이다
  (make_manifest_aihub.py: "D20/G02/S000314/000016 → 화자=S000314").
  **이 추측은 틀렸다.** S000314는 화자가 아니라 **회의 세션**이고, 한 세션에는
  여러 사람이 들어 있다.

  실측으로 확인한 근거:
    ① 세션 S000290 안의 발화 60건을 서로 비교하니 유사도가 0.1~0.3에 큰 덩어리,
       0.5~0.8에 작은 꼬리로 갈렸다(평균 0.241). 한 사람이면 0.5~0.7에 봉우리가
       하나 서야 한다. 여러 사람이 섞여 있다는 뜻이다.
    ② 라벨 .json의 typeInfo.speakers에 참가자가 여럿 있다(S000314는 3명).
    ③ 이 잘못된 라벨로 EER을 쟀더니 37.08%가 나왔다 — 모델이 나쁜 게 아니라
       정답이 틀린 것이었다. 그 숫자는 폐기했다.

  진짜 화자는 세션 .json의 dialogs에 발화별로 있다:
    {"speaker": "1", "audioPath": "KconfSpeech/D20/G02/S000314/000000.wav", ...}

⚠️ 화자 id는 **세션 안에서만 유효한 자리 번호**다. 617세션에 id가 42개뿐이고
   그중 30개는 나이·성별이 세션마다 다르다. id "1"은 551개 세션에 등장한다.
   즉 "1번 참가자"라는 뜻이지 특정 인물이 아니다.
   그래서 전역 화자 id를 "<세션>_<번호>" 형식으로 만든다(S000314_1).

⚠️ 그 결과 **한 사람은 한 세션에만 존재한다.** 이 때문에 비교를 아무렇게나 만들면
   모델이 목소리 대신 녹음 환경을 외울 수 있다(같은 사람=같은 방, 다른 사람=다른 방).
   make_speaker_trials.py가 **같은 세션 안에서만** 쌍을 만드는 이유다.
   그리고 그것이 우리 제품이 실제로 하는 일이기도 하다 — 한 회의 안의 참석자 구분.

사용법:
  python make_speaker_manifest.py --output manifest_aihub_speaker.jsonl
"""
import argparse
import json
import os
import zipfile

AUDIO_PREFIX = "KconfSpeech/"


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="manifest_aihub.jsonl",
                        help="기존 매니페스트. audio_zip 대응과 전사 텍스트를 여기서 가져온다")
    parser.add_argument("--output", default="manifest_aihub_speaker.jsonl")
    args = parser.parse_args()

    base = load_jsonl(args.manifest)
    if not base:
        raise SystemExit(f"❌ {args.manifest}이 비어 있다")
    # audio_member → (zip, text). 라벨 zip을 다시 인덱싱하지 않으려고 재활용한다.
    index = {r["audio_member"]: (r["audio_zip"], r.get("text", "")) for r in base}
    print(f"기존 매니페스트 {len(base)}건 로드")

    data_dir = os.path.dirname(base[0]["audio_zip"])
    label_zips = [os.path.join(data_dir, f) for f in sorted(os.listdir(data_dir))
                  if "label" in f and f.endswith(".zip")]
    if not label_zips:
        raise SystemExit(f"❌ 라벨 zip을 못 찾음: {data_dir}")
    print(f"라벨 zip {len(label_zips)}개")

    rows, missing, sessions = [], 0, 0
    for zip_path in label_zips:
        with zipfile.ZipFile(zip_path) as z:
            for member in z.namelist():
                if not member.endswith(".json"):
                    continue
                sessions += 1
                # BOM이 붙어 있을 수 있어 utf-8-sig로 읽는다
                data = json.loads(z.read(member).decode("utf-8-sig"))["dataSet"]
                session = os.path.basename(member)[:-len(".json")]
                for d in data.get("dialogs", []):
                    path = d.get("audioPath", "")
                    if path.startswith(AUDIO_PREFIX):
                        path = path[len(AUDIO_PREFIX):]
                    found = index.get(path)
                    if found is None:
                        missing += 1
                        continue
                    audio_zip, text = found
                    rows.append({
                        "source": "aihub_speaker",
                        "audio_zip": audio_zip,
                        "audio_member": path,
                        "text": text,
                        "session": session,
                        "speaker_local": d["speaker"],
                        "speaker": f"{session}_{d['speaker']}",
                    })
        print(f"  읽음: {os.path.basename(zip_path)}")

    with open(args.output, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    speakers = {r["speaker"] for r in rows}
    per_session: dict[str, set] = {}
    for r in rows:
        per_session.setdefault(r["session"], set()).add(r["speaker"])
    sizes = sorted(len(v) for v in per_session.values())

    print()
    print(f"세션 {sessions}개 / 발화 {len(rows)}건 / 화자 {len(speakers)}명")
    if missing:
        print(f"⚠️ 오디오를 못 찾아 건너뛴 발화 {missing}건")
    print(f"세션당 화자 수: 최소 {sizes[0]} / 중앙값 {sizes[len(sizes) // 2]} / 최대 {sizes[-1]}")
    print(f"화자당 발화 수 평균 {len(rows) / max(len(speakers), 1):.1f}")
    print(f"✅ {args.output}")


if __name__ == "__main__":
    main()
