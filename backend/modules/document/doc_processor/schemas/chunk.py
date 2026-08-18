from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from doc_processor.schemas.metadata import ChunkMetadata

ChunkType = Literal["text", "table", "image", "chart"]


class ChunkSchema(BaseModel):
    """RAG 적재 단위 청크."""

    id: str
    content_type: ChunkType
    page_number: int
    content: str
    metadata: ChunkMetadata
