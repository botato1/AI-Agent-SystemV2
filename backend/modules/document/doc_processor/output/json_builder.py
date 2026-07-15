from __future__ import annotations

from pathlib import Path

from doc_processor.schemas.document import DocumentSchema


def save_json(schema: DocumentSchema, output_path: str) -> Path:
    path = Path(output_path)
    path.write_text(
        schema.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return path
