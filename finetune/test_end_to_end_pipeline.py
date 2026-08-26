"""end-to-end 판단 파이프라인 테스트 - decision_judgment.py의 judge()가 실제로 하는
체인(topic_match 게이트 -> 1단계 새값? -> 2단계 같은값? -> 3단계 근거명확?)을 그대로
재현해서, 발화 하나가 최종적으로 올바른 Case(0/1/2/3/none)까지 맞게 나오는지 본다.

지금까지의 4개 과제별 홀드아웃(test_tone_v1/test_value_match_v1/test_reason_clarity_v1/
test_topic_match_v2)은 각자 "그 단계까지 도달했다"는 전제를 깔고 만들어졌다
(예: same_as_existing 파일의 instruction 자체가 "이미 새로운 값을 제시하고 있다"를
전제함). 그래서 새로 만들 필요 없이 이 4개를 조합해서 end-to-end 정답을 도출한다:

  - presents_new_value=false  -> 정답 Case "0" (리마인더)
  - same_as_existing=true     -> 정답 Case "1" (무시/재확인 리마인더)
  - reason_is_clear=true      -> 정답 Case "2" (근거 명확한 변경)
  - reason_is_clear=false     -> 정답 Case "3" (근거 불명확한 변경)
  - same_topic=false          -> 정답 "none" (애초에 후보 매칭 자체가 안 됨)

주의: 이건 각 "단계"의 정답이지, 체인 전체가 맞는다는 보장은 아니다. 예를 들어
same_as_existing=true로 정답이 Case 1인 행이어도, 실제로 이 스크립트가 1단계
(presents_new_value)부터 다시 물어봐서 모델이 틀리면(예: false로 잘못 답하면)
Case 0으로 새 판단이 나온다 - 이런 단계 간 오류 전파까지 포함해서 재는 게
이 테스트의 목적이다(실제 judge()가 정확히 이렇게 동작하므로).

카테고리당 SAMPLE_SIZE_PER_CATEGORY개씩만 뽑아서 먼저 빠르게 돌린다 - 전체
(50/51/75/75/104)로 늘리려면 None으로 바꿀 것.

82서버에서: python3 finetune/test_end_to_end_pipeline.py
"""
import json
import random
import re

import httpx

OLLAMA_BASE_URL = "http://localhost:11434"
SAMPLE_SIZE_PER_CATEGORY = None  # None이면 전체 사용 (50/51/75/75/104 = 355개)
RANDOM_SEED = 42

MODELS = [
    "qwen2.5:7b",
    "re-call-model1-unified-v12",
]

# decision_judgment.py에서 그대로 복사 - 문구가 조금이라도 다르면 정확도가
# 크게 달라지므로 절대 따로 수정하지 말고 원본이 바뀌면 여기도 같이 맞출 것.
JUDGMENT_STEP_INSTRUCTIONS = {
    "presents_new_value": (
        "아래는 회의/채팅에서 방금 나온 발화이다. 이 발화가 새로운 값/입장을 제시하는지, "
        "아니면 단순히 과거 결정을 재언급/질문하는 것인지만 판단해서 JSON으로만 답하라."
    ),
    "same_as_existing": (
        "아래는 회의/채팅에서 방금 나온 발화이다. 이 발화는 이미 새로운 값/입장을 제시하고 있다. "
        "그 값이 기존 결정과 실질적으로 같은 내용인지 다른 내용인지만 판단해서 JSON으로만 답하라."
    ),
    "reason_is_clear": (
        "아래는 회의/채팅에서 방금 나온 발화이다. 이 발화는 이미 기존 결정과 다른 새 값을 제시하고 있다. "
        "왜 바뀌는지 근거/이유가 발화 안에 명확하게 드러나 있는지만 판단해서 JSON으로만 답하라."
    ),
}

JUDGMENT_INPUT_TEMPLATE = """[과거 결정]
{decision_text}
(결정 이유: {decision_reason})

[방금 발화]
{statement}"""

TOPIC_MATCH_INSTRUCTION = (
    "아래는 과거 의사결정과 새 발화이다.\n\n"
    "목표:\n새 발화가 과거 의사결정에서 실제로 결정된 그 항목·속성을 다루는지 판단하라.\n\n"
    "같은 주제(true)인 경우\n"
    "- 과거 의사결정에서 선택한 항목을 다른 기술/서비스/제품으로 교체하자는 제안\n"
    "- 과거 의사결정에서 정한 그 설정값(수치, 기간, 비율, 개수 등)을 조정하자는 제안\n"
    "- 과거 의사결정과 동일한 선택지를 놓고 대안을 비교하거나 장단점을 논하는 경우\n"
    "- 과거 의사결정 내용 자체를 단순히 되묻거나 재확인하거나 다시 언급하는 경우, "
    "변경 의도가 없는 동의·긍정적 코멘트도 포함\n"
    "  (예: \"그거 A로 하기로 했었죠?\", \"왜 A로 정했었죠\", \"A 맞나요\", "
    "\"A로 그대로 가면 될 것 같아요\", \"A가 요즘 보니 괜찮더라고요\")\n\n"
    "다른 주제(false)인 경우\n"
    "- 같은 시스템/프로젝트/컴포넌트에 대한 이야기라도, 과거 의사결정이 실제로\n"
    "  다루지 않은 별개의 속성·정책·운영 이슈인 경우\n"
    "  (예: \"DB는 PostgreSQL을 쓴다\"는 \"어떤 DB 기술을 쓸지\"에 대한 결정이므로,\n"
    "  같은 DB에 대한 이야기여도 \"백업 주기\", \"마이그레이션 자동화\" 등은 별개 항목)\n"
    "- 비슷한 분야/카테고리라도 역할이 다른 경우 (예: 관계형DB vs 벡터DB, "
    "인증 vs 권한관리, 캐시 vs 메시지큐, 검색엔진 vs 그래프DB) — 배경지식으로 "
    "역할이 다름을 판단해야 하는 경우도 포함\n"
    "- 기존 결정과 독립적인 신규 기능 또는 신규 컴포넌트 제안\n"
    "- 완전히 무관한 화제\n\n"
    "판단의 핵심은 \"같은 시스템/키워드가 언급되었는가\"가 아니라\n"
    "\"과거에 실제로 결정된 바로 그 속성을 다루는가\"이다.\n\n"
    "다음 JSON만 출력한다.\n{\n  \"reason\": \"20자 이내\",\n  \"same_topic\": true | false\n}"
)

TOPIC_MATCH_INPUT_TEMPLATE = """[과거 의사결정]
{decision_text}
(결정 이유: {decision_reason})

[새 발화]
{statement}"""

# 4개 홀드아웃 파일의 input 필드 형식이 두 종류다 - [과거 결정]/[방금 발화]
# (tone/value_match/reason_clarity) vs [과거 의사결정]/[새 발화](topic_match).
# 내용 구조는 동일해서 정규식 하나로 둘 다 파싱한다.
INPUT_PATTERN = re.compile(
    r"\[.+?\]\n(?P<decision_text>.+?)\n\(결정 이유: (?P<decision_reason>.+?)\)\n\n\[.+?\]\n(?P<statement>.+)",
    re.DOTALL,
)


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def parse_input(input_text):
    m = INPUT_PATTERN.match(input_text)
    if not m:
        raise ValueError(f"input 파싱 실패: {input_text[:80]!r}...")
    return m.group("decision_text"), m.group("decision_reason"), m.group("statement")


def build_test_cases():
    """4개 홀드아웃 파일을 조합해서 (decision_text, decision_reason, statement, expected_case)
    리스트를 만든다. expected_case는 "0"/"1"/"2"/"3"/"none" 중 하나."""
    random.seed(RANDOM_SEED)
    cases = []

    def sample(rows, n):
        if n is None or n >= len(rows):
            return rows
        return random.sample(rows, n)

    tone_rows = load_jsonl("test_file/test_tone_v1.jsonl")
    case0_rows = [r for r in tone_rows if json.loads(r["output"])["presents_new_value"] is False]
    for r in sample(case0_rows, SAMPLE_SIZE_PER_CATEGORY):
        dt, dr, st = parse_input(r["input"])
        cases.append({"decision_text": dt, "decision_reason": dr, "statement": st, "expected_case": "0"})

    value_rows = load_jsonl("test_file/test_value_match_v1.jsonl")
    case1_rows = [r for r in value_rows if json.loads(r["output"])["same_as_existing"] is True]
    for r in sample(case1_rows, SAMPLE_SIZE_PER_CATEGORY):
        dt, dr, st = parse_input(r["input"])
        cases.append({"decision_text": dt, "decision_reason": dr, "statement": st, "expected_case": "1"})

    reason_rows = load_jsonl("test_file/test_reason_clarity_v1.jsonl")
    case2_rows = [r for r in reason_rows if json.loads(r["output"])["reason_is_clear"] is True]
    case3_rows = [r for r in reason_rows if json.loads(r["output"])["reason_is_clear"] is False]
    for r in sample(case2_rows, SAMPLE_SIZE_PER_CATEGORY):
        dt, dr, st = parse_input(r["input"])
        cases.append({"decision_text": dt, "decision_reason": dr, "statement": st, "expected_case": "2"})
    for r in sample(case3_rows, SAMPLE_SIZE_PER_CATEGORY):
        dt, dr, st = parse_input(r["input"])
        cases.append({"decision_text": dt, "decision_reason": dr, "statement": st, "expected_case": "3"})

    topic_rows = load_jsonl("test_file/test_topic_match_v2.jsonl")
    none_rows = [r for r in topic_rows if json.loads(r["output"])["same_topic"] is False]
    for r in sample(none_rows, SAMPLE_SIZE_PER_CATEGORY):
        dt, dr, st = parse_input(r["input"])
        cases.append({"decision_text": dt, "decision_reason": dr, "statement": st, "expected_case": "none"})

    return cases


def model_exists(model: str) -> bool:
    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10.0)
        names = [m["name"] for m in resp.json().get("models", [])]
        return model in names or f"{model}:latest" in names
    except Exception:
        return False


def _call_ollama(prompt: str, model: str) -> str:
    resp = httpx.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0}},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def ask_topic_match(model, decision_text, decision_reason, statement) -> bool:
    input_text = TOPIC_MATCH_INPUT_TEMPLATE.format(
        decision_text=decision_text, decision_reason=decision_reason, statement=statement,
    )
    prompt = f"{TOPIC_MATCH_INSTRUCTION}\n\n{input_text}"
    try:
        raw = _call_ollama(prompt, model)
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return False
        return bool(json.loads(raw[start : end + 1]).get("same_topic", False))
    except Exception as e:
        print(f"  [에러] topic_match: {e}")
        return False


def ask_judgment_step(model, key, decision_text, decision_reason, statement) -> bool:
    input_text = JUDGMENT_INPUT_TEMPLATE.format(
        decision_text=decision_text, decision_reason=decision_reason, statement=statement,
    )
    prompt = (
        f"{JUDGMENT_STEP_INSTRUCTIONS[key]}\n\n{input_text}\n\n"
        f'반드시 다음 JSON 형식으로만 답하라 (다른 설명 금지):\n{{\n  "{key}": true/false\n}}'
    )
    try:
        raw = _call_ollama(prompt, model)
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return False
        return bool(json.loads(raw[start : end + 1]).get(key, False))
    except Exception as e:
        print(f"  [에러] {key}: {e}")
        return False


def run_pipeline(model, decision_text, decision_reason, statement) -> str:
    """judge()의 topic_match 게이트 + 3단계 체인을 그대로 재현. 반환값은
    "0"/"1"/"2"/"3"/"none" 중 하나."""
    if not ask_topic_match(model, decision_text, decision_reason, statement):
        return "none"

    if not ask_judgment_step(model, "presents_new_value", decision_text, decision_reason, statement):
        return "0"

    if ask_judgment_step(model, "same_as_existing", decision_text, decision_reason, statement):
        return "1"

    if ask_judgment_step(model, "reason_is_clear", decision_text, decision_reason, statement):
        return "2"
    return "3"


def main():
    cases = build_test_cases()

    available = [m for m in MODELS if model_exists(m)]
    missing = [m for m in MODELS if m not in available]
    if missing:
        print(f"[스킵] 등록 안 된 모델: {missing}")
    if not available:
        print("등록된 모델이 하나도 없음. `ollama list`로 실제 이름 확인 필요.")
        return

    # [출력량 조절] 진행 중엔 50개마다 한 줄만 - 터미널에 다 찍으면 스크롤백이
    # 길어져서 앞부분(요약)이 밀려 잘릴 수 있음. 핵심 숫자·틀린 목록은 전부
    # 맨 마지막에 한 번씩만 출력한다.
    all_preds = {}
    for model in available:
        preds = []
        for i, c in enumerate(cases):
            preds.append(run_pipeline(model, c["decision_text"], c["decision_reason"], c["statement"]))
            if (i + 1) % 50 == 0:
                print(f"[{model}] {i + 1}/{len(cases)}")
        all_preds[model] = preds

    categories = ["0", "1", "2", "3", "none"]
    expecteds = [c["expected_case"] for c in cases]

    print(f"\n=== 결과 (총 {len(cases)}개, base vs v12) ===")
    print(f"{'모델':<28}{'전체':>10}  " + "  ".join(f"case{c:>4}" for c in categories))
    for model in available:
        preds = all_preds[model]
        total = sum(p == e for p, e in zip(preds, expecteds))
        row = f"{model:<28}{total}/{len(cases)}={total/len(cases)*100:5.1f}%  "
        for cat in categories:
            idxs = [i for i, c in enumerate(cases) if c["expected_case"] == cat]
            correct = sum(preds[i] == cat for i in idxs)
            row += f"{correct}/{len(idxs)}={correct/len(idxs)*100:4.0f}%  "
        print(row)

    print(f"\n=== 틀린 것만 (expected != 예측) ===")
    header = "  ".join(f"{m.split('-')[-1]:>6}" for m in available)
    print(f"{'#':>3} {'expected':>8}  {header}   문장")
    for i, c in enumerate(cases):
        oks = [all_preds[m][i] == c["expected_case"] for m in available]
        if all(oks):
            continue
        preds_str = "  ".join(f"{all_preds[m][i]:>6}" for m in available)
        print(f"{i+1:>3} {c['expected_case']:>8}  {preds_str}   {c['statement'][:50]}")


if __name__ == "__main__":
    main()
