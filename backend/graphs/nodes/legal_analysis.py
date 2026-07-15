import json
import re

from backend.schemas.agent_schema import AgentState
from backend.modules.llm.ollama_client import _call_ollama


def _parse_json_object(text: str) -> dict:
    if not text:
        return {}

    cleaned = re.sub(r"```json", "", text.strip())
    cleaned = re.sub(r"```", "", cleaned).strip()

    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}


def _build_analysis_source(state: AgentState) -> str:
    parts = []

    contract_clauses = state.get("contract_clauses") or []
    if contract_clauses:
        clause_lines = [
            f"{clause.get('clause', '')} {clause.get('clause_title', '')}\n{clause.get('content', '')}"
            for clause in contract_clauses
            if isinstance(clause, dict)
        ]
        parts.append("[계약 조항]\n" + "\n\n".join(clause_lines))

    case_summary = state.get("case_summary")
    if case_summary:
        parts.append(f"[상담 요약]\n{case_summary}")

    rag_context = state.get("rag_context") or ""
    if rag_context.strip():
        parts.append(f"[법령/판례 근거]\n{rag_context}")

    return "\n\n".join(parts).strip()


def legal_analysis_node(state: AgentState) -> dict:
    try:
        source = _build_analysis_source(state)

        if not source:
            return {
                "legal_issues": [],
                "risk_clauses": [],
                "missing_checks": [],
                "recommendations": [],
                "current_step": "legal_analysis_node",
                "error": "legal_analysis_source_empty",
            }

        prompt = f"""[INST]
아래는 계약 조항, 상담 요약, 법령/판례 근거 자료입니다.
이 내용을 바탕으로 법률 쟁점과 위험 요소를 분석해줘.

[규칙]
- 원본에 없는 내용은 추가하지 마라.
- 한국어로 작성해라.
- 반드시 아래 JSON 형식으로만 답해라. 다른 설명은 붙이지 마라.

자료:
{source[:8000]}

출력 형식:
{{
  "legal_issues": ["쟁점1", "쟁점2"],
  "risk_clauses": [
    {{"clause": "제3조", "issue": "...", "reason": "...", "risk_level": "high"}}
  ],
  "missing_checks": ["확인이 필요한 항목1"],
  "recommendations": ["권고사항1"]
}}
[/INST]"""

        response_text = _call_ollama(prompt)
        parsed = _parse_json_object(response_text)

        return {
            "legal_issues": parsed.get("legal_issues") or [],
            "risk_clauses": parsed.get("risk_clauses") or [],
            "missing_checks": parsed.get("missing_checks") or [],
            "recommendations": parsed.get("recommendations") or [],
            "current_step": "legal_analysis_node",
            "error": None,
        }

    except Exception as e:
        return {
            "legal_issues": state.get("legal_issues") or [],
            "risk_clauses": state.get("risk_clauses") or [],
            "missing_checks": state.get("missing_checks") or [],
            "recommendations": state.get("recommendations") or [],
            "current_step": "legal_analysis_node",
            "error": str(e),
        }
