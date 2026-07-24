"""post-meeting 파이프라인 2-2: 구조화 LLM 호출 (통합 — 1회)

요약/결정/할일을 별도 LLM 호출 3번으로 나누지 않고 하나의 구조화 출력으로 통합한다.
(설계 문서 2-2 참조 — 호출을 나누면 같은 텍스트를 여러 관점으로 읽으며 서로
미묘하게 어긋난 결과가 나올 수 있고, 비용·레이턴시도 불리함)

여기서는 실시간 파이프라인처럼 confidence 기반 escalation을 쓰지 않는다.
post-meeting은 회의 종료 후 비동기로 도는 작업이라 레이턴시 압박이 없으므로,
처음부터 Model2(무거운 모델)로 간다 — ollama_client의 OLLAMA_MODEL 설정을 그대로 사용.
"""

import json
import re

from backend.modules.llm.ollama_client import OLLAMA_MODEL_HEAVY, _call_ollama

EXTRACTION_PROMPT_TEMPLATE = """다음은 회의 전체 발화 기록이다. 이 내용을 분석해서 아래 JSON 스키마에
맞춰 정확히 출력하라. 다른 설명이나 텍스트 없이 JSON만 출력하라.

[중요 지침]
- topics는 이 회의에서 실제로 논의된 주제만 포함한다.
- status는 다음 세 값 중 하나만 쓴다:
  - "confirmed": 이 회의에서 명시적으로 합의/확정된 것
  - "reconfirmed": 기존 결정을 그대로 유지하기로 재확인한 것
  - "reopened_no_conclusion": 재논의했지만 결론이 나지 않고 보류된 것
- 아직 논의 중이거나 제안 단계에 머문 것, 결론이 나지 않은 것은 "reopened_no_conclusion"으로
  분류하고, 절대로 "confirmed"로 표시하지 않는다.
- action_items는 담당자 또는 기한이 명시적으로 언급된 항목만 포함한다.

[회의 전체 발화]
{transcript}

[출력 JSON 스키마]
{{
  "full_summary": "회의 전체를 상세히 요약한 텍스트",
  "short_summary": "한두 문장으로 요약한 텍스트",
  "discussion_points": ["논의 포인트1", "논의 포인트2"],
  "topics": [
    {{
      "title": "주제 제목",
      "decision_text": "확정된 내용 (reopened_no_conclusion이면 논의 중이던 내용)",
      "evidence": "근거가 된 발화 요약",
      "reason": "이렇게 결정/보류된 이유",
      "status": "confirmed | reconfirmed | reopened_no_conclusion"
    }}
  ],
  "action_items": [
    {{
      "title": "할 일 제목",
      "assignee": "담당자 이름 (없으면 null)",
      "due_date": "YYYY-MM-DD 형식 기한 (없으면 null)",
      "description": "상세 설명"
    }}
  ]
}}
"""


def _extract_json_block(text: str) -> str:
    """LLM 응답에서 ```json ... ``` 코드펜스가 있으면 벗겨내고, 없으면 그대로 반환."""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    # 코드펜스 없이 JSON만 온 경우, 첫 '{'부터 마지막 '}'까지 추출
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def extract(transcript: str) -> dict:
    """
    전체 회의 텍스트를 받아 구조화된 결과를 반환한다.

    Returns:
        {
          "full_summary": str, "short_summary": str, "discussion_points": list[str],
          "topics": list[dict], "action_items": list[dict]
        }
    실패 시 모든 값이 비어있는 안전한 기본값을 반환한다 (파이프라인 중단 방지).
    """
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(transcript=transcript)
    # 회의 전체 요약/결정 추출은 비동기 처리 - 처음부터 Model2(Qwen3-8B)로 감
    raw = _call_ollama(prompt, timeout=300.0, model=OLLAMA_MODEL_HEAVY)  # 긴 회의 전체를 읽어야 하니 타임아웃 넉넉히

    fallback = {
        "full_summary": "",
        "short_summary": "",
        "discussion_points": [],
        "topics": [],
        "action_items": [],
    }

    try:
        json_str = _extract_json_block(raw)
        parsed = json.loads(json_str)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[llm_extractor] JSON 파싱 실패, 빈 결과로 폴백: {e}\n원본 응답: {raw[:500]}")
        return fallback

    # 최소 형태 검증 - 키가 없으면 기본값으로 채움
    for key, default in fallback.items():
        parsed.setdefault(key, default)

    # status 값 검증 - 스키마에 없는 값이 오면 reopened_no_conclusion으로 안전하게 처리
    valid_statuses = {"confirmed", "reconfirmed", "reopened_no_conclusion"}
    for topic in parsed.get("topics", []):
        if topic.get("status") not in valid_statuses:
            topic["status"] = "reopened_no_conclusion"

    return parsed