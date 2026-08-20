"""
회의 전사를 **이 분야 표준 지표**(cpWER / ORC-WER)로 채점한다.

왜 필요한가 (2026-08-10, 문헌 검토에서 출발):
  우리는 CER(전사 정확도)과 화자 정확도를 따로 재왔다. 그런데 회의 전사 분야는
  **둘을 하나로 합친 지표**를 표준으로 쓴다(CHiME-6/7/8 공식 순위 지표).

    cpWER    화자별로 전사를 이어붙인 뒤, 화자 배정 순열 중 최소 WER.
             전사가 맞아도 화자를 틀리면 벌점이 간다 — "누가 무엇을 말했나"를 한 숫자로 잰다.
    DI-cpWER 화자 오류를 제외한 순수 전사 품질(diarization-invariant).
    ORC-WER  참조 발화를 가설 스트림에 최적 배정해서 채점.
             **세그먼트 경계를 어떻게 나눴든 점수가 안 흔들린다.**

⚠️ ORC/DI-cp는 **greedy 근사**를 쓴다. 정확한 ORC-WER은 화자 수와 발화 수에 따라
   탐색 공간이 폭발한다 — 실측으로 화자 5명 × 발화 28개에서 메모리를 다 쓰고
   프로세스가 죽었다(종료코드 137). 근사와 정확값의 차이는 위 실측에서 2%p 안쪽이었다.

  우리 자체 지표의 문제는 두 가지였다:
    ① 다른 시스템·논문과 비교가 불가능하다(우리가 만든 기준이라)
    ② 세그먼트 경계를 우리가 정한 대로 채점해서, 경계를 바꾸면 점수가 흔들린다
       (실제로 turn padding을 넣자 회의별 CER이 ±0.6%p 움직였다)
  ORC-WER은 ②를 없애려고 만들어진 지표다.

한국어에서의 주의 — 그래서 두 가지를 다 낸다:
  cpWER은 **단어 단위**인데, 한국어는 띄어쓰기가 흔들려서 단어 오류율이 부풀려진다
  (실측: 같은 전사에서 CER 5.43% / WER 13.73%). 그래서 글자 사이에 공백을 넣어
  **글자 단위**로도 계산한다(cpCER). 상용 한국어 STT 비교도 CER 기준이다.

⚠️ DER(화자 분리 오류율)은 여기서 못 낸다. 정답 대본에 **시각 정보가 없어서**다.
   DER을 재려면 대본 각 줄이 몇 초~몇 초인지 표시된 참조가 필요하다.

사용법:
  python meeteval_score.py --meetings <회의ID>:<대본> [<회의ID>:<대본> ...]
  python meeteval_score.py --meetings ... --realtime   # 실시간 결과로 채점
"""
import argparse
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

import json  # noqa: E402

from stt.core.config import MEETINGS_DIR  # noqa: E402
from evaluate_against_script import load_script  # noqa: E402

_PUNCT = re.compile(r"[^가-힣a-zA-Z0-9\s]")

# 화자를 못 찾은 세그먼트에 붙일 이름. **비워두면 안 된다** — meeteval은 화자별로
# 묶어서 순열을 맞추는데, 라벨이 없으면 그 발화가 통째로 빠져 점수가 좋아 보인다.
_UNKNOWN = "미상"


def words_of(text: str, char_level: bool) -> str:
    """채점용 정규화. 문장부호는 화자·용어 인식과 무관하므로 제거한다."""
    t = _PUNCT.sub(" ", text)
    t = " ".join(t.split())
    if not char_level:
        return t
    # 글자 사이에 공백을 넣어 '단어=글자'로 만든다 → 단어 단위 지표가 글자 단위로 동작
    return " ".join(t.replace(" ", ""))


def build(meeting: str, script_path: str, realtime: bool, char_level: bool):
    ref, hyp = [], []
    for line in load_script(os.path.expanduser(script_path)):
        w = words_of(line["text"], char_level)
        if w:
            ref.append({"session_id": meeting, "speaker": line["speaker"], "words": w})

    path = os.path.join(MEETINGS_DIR, meeting, "transcript.json")
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    segs = meta.get("realtime_segments" if realtime else "segments") or []
    if not segs:
        raise SystemExit(f"❌ {meeting}: 세그먼트가 없다")
    for s in segs:
        w = words_of(s.get("text") or "", char_level)
        if w:
            hyp.append({"session_id": meeting, "speaker": s.get("speaker") or _UNKNOWN, "words": w})
    return ref, hyp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meetings", nargs="+", required=True, help="'회의ID:대본경로'")
    parser.add_argument("--realtime", action="store_true", help="재분석본 대신 실시간 결과를 채점")
    args = parser.parse_args()

    try:
        import meeteval
    except ImportError:
        raise SystemExit("❌ meeteval이 없다 — pip install meeteval")

    rows = []
    for spec in args.meetings:
        meeting, script = spec.split(":", 1)
        row = {"meeting": meeting}
        for char_level, key in ((False, "word"), (True, "char")):
            ref, hyp = build(meeting, script, args.realtime, char_level)
            combine = meeteval.wer.combine_error_rates
            cp = combine(meeteval.wer.cpwer(ref, hyp))
            # 정확한 orcwer는 화자·발화가 늘면 메모리를 다 쓰고 죽는다 → greedy 근사
            orc = combine(meeteval.wer.greedy_orcwer(ref, hyp))
            dicp = combine(meeteval.wer.greedy_dicpwer(ref, hyp))
            row[f"cp_{key}"] = cp.error_rate
            row[f"orc_{key}"] = orc.error_rate
            row[f"dicp_{key}"] = dicp.error_rate
            if key == "char":
                # 화자를 틀려서 생긴 벌점 = cpWER − DI-cpWER.
                # DI-cp는 정의상 화자 오류를 뺀 값이라, 그 차이가 곧 화자 오류의 대가다.
                row["speaker_cost"] = cp.error_rate - dicp.error_rate
        rows.append(row)

    print("=" * 92)
    print(f"대상: {'실시간 결과' if args.realtime else '재분석본'}")
    print("=" * 92)
    print(f"{'회의':38s}{'cpCER':>9s}{'DI-cpCER':>10s}{'ORC-CER':>9s}{'화자대가':>9s}{'cpWER':>9s}")
    print("-" * 92)
    for r in rows:
        print(f"{r['meeting'][:38]:38s}{r['cp_char']*100:8.2f}%{r['dicp_char']*100:9.2f}%"
              f"{r['orc_char']*100:8.2f}%{r['speaker_cost']*100:8.2f}%{r['cp_word']*100:8.2f}%")
    if len(rows) > 1:
        print("-" * 92)
        n = len(rows)
        print(f"{'평균':38s}"
              f"{sum(r['cp_char'] for r in rows)/n*100:8.2f}%"
              f"{sum(r['dicp_char'] for r in rows)/n*100:9.2f}%"
              f"{sum(r['orc_char'] for r in rows)/n*100:8.2f}%"
              f"{sum(r['speaker_cost'] for r in rows)/n*100:8.2f}%"
              f"{sum(r['cp_word'] for r in rows)/n*100:8.2f}%")

    print()
    print("읽는 법")
    print("  cpCER     전사 + 화자 배정을 합친 점수. **제품이 실제로 내놓는 결과의 품질**")
    print("  DI-cpCER  화자 오류를 뺀 순수 전사 품질")
    print("  ORC-CER   세그먼트를 어떻게 나눴든 안 흔들리는 전사 품질")
    print("  화자대가   cpCER − DI-cpCER = 화자를 틀려서 잃은 몫")
    print("           이 값이 크면 전사는 되는데 누가 말했는지를 못 맞히고 있다는 뜻이다")
    print()
    print("  ⚠️ 표본이 회의 몇 건뿐이면 이 숫자도 흔들린다. 논문 수치와 나란히 놓을 때는")
    print("     세션 수를 함께 밝힐 것 (CHiME/NOTSOFAR는 수십 세션 규모다).")


if __name__ == "__main__":
    main()
