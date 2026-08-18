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

EXTRACTION_PROMPT_TEMPLATE = """다음은 회의 전체 발화 기록이다. 각 발화 앞에는 [번호] 형식의
발화 번호가 붙어있다. 이 내용을 분석해서 아래 JSON 스키마에 맞춰 정확히 출력하라.
다른 설명이나 텍스트 없이 JSON만 출력하라.

[중요 지침]
- topics는 이 회의에서 실제로 논의된 주제만 포함한다.
- status는 다음 세 값 중 하나만 쓴다:
  - "confirmed": 이 회의에서 명시적으로 합의/확정된 것
  - "reconfirmed": 기존 결정을 그대로 유지하기로 재확인한 것
  - "reopened_no_conclusion": 재논의했지만 결론이 나지 않고 보류된 것
- 아직 논의 중이거나 제안 단계에 머문 것, 결론이 나지 않은 것은 "reopened_no_conclusion"으로
  분류하고, 절대로 "confirmed"로 표시하지 않는다.
- action_items는 담당자 또는 기한이 명시적으로 언급된 항목만 포함한다.
- 인사말/날씨/안부 등 회의 주제와 무관한 잡담은 full_summary/discussion_points/topics
  어디에도 포함하지 마라. 대신 그런 발화의 번호를 chit_chat_segment_indexes에 전부 나열하라.
- title은 이 회의 내용을 대표하는 15자 내외의 짧은 제목이다.
- full_summary, meeting_purpose, next_steps, discussion_points, topics의 title/decision_text/
  evidence/reason, action_items의 description은 전부 회의록/보고서에 쓰는 개조식("~함", "~임",
  "~됨" 등으로 끝나는 명사형 종결)으로 작성한다. "~습니다", "~했어요" 같은 평서문/구어체로
  쓰지 않는다. (예: "출시일을 9월 15일로 확정함", "배포 인프라 변경 필요성 논의함")

[회의 전체 발화]
{transcript}

[출력 JSON 스키마]
{{
  "title": "회의 제목으로 쓸 15자 내외의 짧은 문구",
  "full_summary": "회의 전체를 상세히 요약한 텍스트",
  "short_summary": "한두 문장으로 요약한 텍스트",
  "meeting_purpose": "이 회의를 하는 목적/배경을 1~2문장으로 (예: 하반기 프로젝트 추진 현황을 공유하고 주요 이슈를 논의하기 위함)",
  "next_steps": "회의에서 논의된 내용을 바탕으로 이후 진행할 향후 계획을 1~2문장으로. 다음 회의 일정이 명시적으로 언급되지 않았으면 이 문장에도 다음 회의 날짜를 지어내지 마라. 향후 계획을 언급할 내용이 전혀 없으면 빈 문자열로 둔다.",
  "discussion_points": ["논의 포인트1", "논의 포인트2"],
  "chit_chat_segment_indexes": [1, 5, 12],
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
          "full_summary": str, "short_summary": str, "meeting_purpose": str,
          "next_steps": str, "discussion_points": list[str],
          "topics": list[dict], "action_items": list[dict]
        }
    실패 시 모든 값이 비어있는 안전한 기본값을 반환한다 (파이프라인 중단 방지).
    """
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(transcript=transcript)

    fallback = {
        "title": "",
        "full_summary": "",
        "short_summary": "",
        "meeting_purpose": "",
        "next_steps": "",
        "discussion_points": [],
        "chit_chat_segment_indexes": [],
        "topics": [],
        "action_items": [],
    }

    # [수정] LLM이 가끔 JSON 문법을 깨는 노이즈(엉뚱한 따옴표/구두점 등)를 내는 게
    # 실측으로 반복 확인됨 - 다시 호출하면 대부분 성공하므로, 사람이 스크립트를
    # 수동 재실행하던 걸 함수 내부 재시도로 자동화. post-meeting은 회의당 1회
    # 비동기로 도는 파이프라인이라 재시도 지연은 문제되지 않음.
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        # 회의 전체 요약/결정 추출은 비동기 처리 - 처음부터 Model2(Qwen3-8B)로 감
        raw = _call_ollama(prompt, timeout=300.0, model=OLLAMA_MODEL_HEAVY)  # 긴 회의 전체를 읽어야 하니 타임아웃 넉넉히
        try:
            json_str = _extract_json_block(raw)
            # strict=False: LLM이 문자열 값 안에 이스케이프 안 된 제어문자(줄바꿈 등)를
            # 넣는 경우가 있어, JSON 표준상 금지된 이런 문자도 관대하게 허용한다.
            parsed = json.loads(json_str, strict=False)
            break
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[llm_extractor] JSON 파싱 실패 ({attempt}/{max_attempts}), 재시도: {e}")
            if attempt == max_attempts:
                print(f"[llm_extractor] {max_attempts}회 모두 실패, 빈 결과로 폴백\n원본 응답: {raw[:500]}")
                return fallback

    # 최소 형태 검증 - 키가 없으면 기본값으로 채움
    for key, default in fallback.items():
        parsed.setdefault(key, default)

    # LLM이 배열 안에 dict가 아닌 값(문자열 등)을 섞어 보낼 수 있으므로, status
    # 검증 루프에서 .get()/할당을 시도하기 전에 걸러낸다 (지수 리뷰 반영 - 순서가
    # 바뀌면 아래 루프에서 AttributeError로 이 함수 전체가 죽어 요약/결정/할일이
    # 통째로 날아간다).
    parsed["topics"] = [t for t in parsed.get("topics", []) if isinstance(t, dict)]
    parsed["action_items"] = [t for t in parsed.get("action_items", []) if isinstance(t, dict)]
    parsed["chit_chat_segment_indexes"] = [
        i for i in parsed.get("chit_chat_segment_indexes", []) if isinstance(i, int)
    ]

    # status 값 검증 - 스키마에 없는 값이 오면 reopened_no_conclusion으로 안전하게 처리
    valid_statuses = {"confirmed", "reconfirmed", "reopened_no_conclusion"}
    for topic in parsed["topics"]:
        if topic.get("status") not in valid_statuses:
            topic["status"] = "reopened_no_conclusion"

    return parsed