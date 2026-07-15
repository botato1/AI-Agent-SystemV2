# RAG 검색 관련 API 엔드포인트
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.schemas.rag_schema import RagSearchResponseSchema
from backend.services.rag_service import rag_service


class RagSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    relative_threshold: float = 0.5
    filter: Optional[dict] = None


router = APIRouter(
    prefix="/api/rag",
    tags=["RAG"]
)

# 사용자의 검색어를 받아 ChromaDB에서 관련 문서를 검색하는 API
@router.post("/search", response_model=RagSearchResponseSchema)
async def search_rag(request: RagSearchRequest):
    result = rag_service.retrieve_relevant_knowledge(
        query=request.query,
        top_k=request.top_k,
        relative_threshold=request.relative_threshold,
        filter=request.filter
    )

    return result