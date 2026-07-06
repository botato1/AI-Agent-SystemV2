from backend.schemas.agent_schema import AgentState
from backend.modules.llm.ollama_client import generate_voice_summary


CONSULTATION_DOCUMENT_TYPES = {
    "consultation_audio",
    "consultation_note",
    "voice",  # v1 legacy: STT 문서가 아직 이 타입으로 저장되는 경우 허용
}


def _extract_text_from_document_json(document_json: dict) -> str:
    content = document_json.get("content_markdown") or document_json.get("content") or ""
    if content.strip():
        return content

    chunks = document_json.get("chunks") or []
    chunk_texts = [
        chunk.get("content") or chunk.get("text") or ""
        for chunk in chunks
        if isinstance(chunk, dict)
    ]
    return "\n\n".join(text.strip() for text in chunk_texts if text.strip())


def fact_extractor_node(state: AgentState) -> dict:
    needs_case_summary = state.get("need_case_card") or state.get("need_legal_analysis")

    if state.get("document_type") not in CONSULTATION_DOCUMENT_TYPES or not needs_case_summary:
        return {
            "case_summary": state.get("case_summary"),
            "summary": state.get("summary"),
            "current_step": "fact_extractor_node",
            "error": None,
        }

    try:
        document_json = state.get("document_json") or {}
        text = _extract_text_from_document_json(document_json)

        if not text:
            return {
                "case_summary": state.get("case_summary"),
                "summary": state.get("summary"),
                "current_step": "fact_extractor_node",
                "error": "fact_source_empty",
            }

        case_summary = generate_voice_summary(text)

        return {
            "case_summary": case_summary,
            "summary": case_summary,
            "current_step": "fact_extractor_node",
            "error": None,
        }

    except Exception as e:
        return {
            "case_summary": state.get("case_summary"),
            "summary": state.get("summary"),
            "current_step": "fact_extractor_node",
            "error": str(e),
        }
