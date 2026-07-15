from __future__ import annotations

import json
from pathlib import Path

from doc_processor.schemas.document import DocumentSchema


def save_rag(schema: DocumentSchema, output_path: str) -> Path:
    """DocumentSchema.chunks를 RAG 적재용 JSON으로 저장합니다."""
    chunks = [c.model_dump() for c in schema.chunks]
    path = Path(output_path)
    path.write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
