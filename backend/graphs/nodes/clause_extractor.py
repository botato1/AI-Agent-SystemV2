import re

from backend.schemas.agent_schema import AgentState
from backend.db.crud import get_document_by_id


CLAUSE_PATTERN = re.compile(r"(제\s*\d+\s*조(?:의\s*\d+)?)(?:\s*[\(\[]([^\)\]]+)[\)\]])?")


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


def _split_clauses(text: str) -> list[dict]:
    matches = list(CLAUSE_PATTERN.finditer(text))

    if not matches:
        return []

    clauses = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)

        clause_number = match.group(1).strip()
        clause_title = (match.group(2) or "").strip()
        content = text[start:end].strip()

        clauses.append({
            "clause": clause_number,
            "clause_title": clause_title,
            "content": content,
        })

    return clauses


def clause_extractor_node(state: AgentState) -> dict:
    if state.get("document_type") != "contract":
        return {
            "contract_clauses": [],
            "current_step": "clause_extractor_node",
            "error": None,
        }

    try:
        document_ids = state.get("document_ids") or []
        contract_clauses = []

        for document_id in document_ids:
            document = get_document_by_id(document_id)
            if not document or document.get("type") != "contract":
                continue

            document_json = state.get("document_json") or {}
            text = _extract_text_from_document_json(document_json)

            if not text:
                continue

            clauses = _split_clauses(text)
            for clause in clauses:
                clause["source_document_id"] = document_id
                clause["page_number"] = None

            contract_clauses.extend(clauses)

        return {
            "contract_clauses": contract_clauses,
            "current_step": "clause_extractor_node",
            "error": None,
        }

    except Exception as e:
        return {
            "contract_clauses": [],
            "current_step": "clause_extractor_node",
            "error": str(e),
        }