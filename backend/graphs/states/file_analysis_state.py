# backend/graphs/states/file_analysis_state.py

# 워크트리 업로드 후 파일 하나를 분석하는 그래프 상태.
# workspace_files 한 건당 한 번 실행한다.

from typing import Any, NotRequired, Required

from backend.graphs.states.common_state import CommonState
from backend.schemas.type_schema import (
    CodeFileRole,
    FileAnalysisStatus,
    FileKind,
)


class FileAnalysisState(CommonState, total=False):
    # 대상 파일
    file_id: Required[str]
    worktree_id: NotRequired[str]
    file_kind: NotRequired[FileKind]

    # 문서·이미지 분석 결과
    extracted_text: NotRequired[str]
    document_summary: NotRequired[str]
    page_count: NotRequired[int]
    ocr_avg_confidence: NotRequired[float]
    ocr_required_pages: NotRequired[int]
    ocr_success_pages: NotRequired[int]
    table_count: NotRequired[int]
    graph_count: NotRequired[int]
    diagram_count: NotRequired[int]
    document_model_name: NotRequired[str]
    document_analysis_id: NotRequired[str]

    # 코드·설정 분석 결과
    language: NotRequired[str]
    parser_name: NotRequired[str]
    file_role: NotRequired[CodeFileRole]
    code_summary: NotRequired[str]
    code_symbols: NotRequired[list[dict[str, Any]]]
    code_facts: NotRequired[list[dict[str, Any]]]
    code_analysis_id: NotRequired[str]

    # 공통 분석 정보
    processing_duration_ms: NotRequired[int]

    # 콘텐츠 청크 및 ChromaDB 저장 결과
    content_chunks: NotRequired[list[dict[str, Any]]]
    chroma_ids: NotRequired[list[str]]

    # 최종 처리 상태
    analysis_status: NotRequired[FileAnalysisStatus]
    processing_error: NotRequired[str]