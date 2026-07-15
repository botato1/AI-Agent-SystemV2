# backend/schemas/type_schema.py

"""
프로젝트 전역에서 사용하는 Literal 타입 정의.

현재 기존 v1/v2 그래프와 Re:Call 그래프가 함께 존재하므로,
기존 질문·문서 타입은 하위 호환을 위해 임시로 유지한다.

TODO:
- classifier.py를 Re:Call 기준으로 마이그레이션
- AgentState의 question_type, document_type 구조 마이그레이션
- common_schema.py, document_schema.py의 DocumentType 의존성 제거
- 기존 그래프 및 API 호환성 확인 후 legacy 타입 삭제
"""

from typing import Final, Literal


# =============================================================================
# Legacy: 기존 v1/v2 질문 타입
# =============================================================================

# v1 그래프에서 사용하던 질문 분류값
QuestionTypeV1 = Literal[
    "task_from_rag",
    "task_from_memory",
    "knowledge_search",
    "general_answer",
    "summary_from_rag",
]


# v2 법률 서비스에서 사용하던 질문 분류값
#
# 현재 backend/graphs/nodes/classifier.py에서 직접 참조하고 있으므로
# Re:Call용 classifier 마이그레이션 전까지 유지한다.
QuestionTypeV2 = Literal[
    "contract_risk_check",   # 계약서 위험 조항 검증
    "statute_search",        # 법조문 검색
    "precedent_search",      # 판례 검색
    "legal_search",          # 법조문 및 판례 통합 검색
    "general_answer",        # 일반 답변
    "consultation_summary",  # 상담 요약 및 사건 카드 생성
]


# v1/v2 혼용 기간 동안 허용하는 통합 질문 타입
QuestionType = QuestionTypeV1 | QuestionTypeV2


# 기존 그래프의 기본 질문 타입
DEFAULT_QUESTION_TYPE: Final[QuestionType] = "general_answer"


# =============================================================================
# Legacy: 기존 v1/v2 문서 타입
# =============================================================================

# v2 법률 서비스에서 사용하던 문서 타입
DocumentTypeV2 = Literal[
    "contract",
    "evidence",
    "consultation_audio",
    "consultation_note",
    "precedent_ref",
]


# v1에서 사용하던 문서 타입
LegacyDocumentType = Literal[
    "document",
    "meeting",
    "voice",
]


# 기존 문서 API 및 AgentState에서 사용하는 통합 문서 타입
#
# 현재 다음 파일에서 참조하고 있으므로 즉시 삭제할 수 없다.
# - backend/schemas/common_schema.py
# - backend/schemas/document_schema.py
# - backend/schemas/agent_schema.py
DocumentType = DocumentTypeV2 | LegacyDocumentType


# 기존 문서 API의 기본 문서 타입
DEFAULT_DOCUMENT_TYPE: Final[DocumentType] = "document"


# 인증 및 워크스페이스
AccountStatus = Literal[
    "active",
    "inactive",
    "locked",
]

WorkspaceRole = Literal[
    "owner",
    "member",
]


# 카테고리 및 채팅방
RoomMessageType = Literal[
    "text",
    "file",
    "ai_summary",
    "contradiction_alert",
    "meeting_notice",
    "system",
]


# 워크트리 및 통합 파일 관리
WorktreeStatus = Literal[
    "pending",
    "processing",
    "completed",
    "partially_completed",
    "failed",
]

FileKind = Literal[
    "document",
    "code",
    "config",
    "image",
    "audio",
]

FileOriginType = Literal[
    "worktree",
    "document_analysis",
    "room_upload",
    "meeting_upload",
    "live_recording",
]

FileAnalysisStatus = Literal[
    "pending",
    "processing",
    "completed",
    "failed",
    "excluded",
]


# 코드 및 설정 파일 분석
CodeFileRole = Literal[
    "production",
    "test",
    "example",
    "mock",
    "generated",
    "legacy",
    "unknown",
]

CodeSymbolType = Literal[
    "module",
    "class",
    "function",
    "method",
    "api_endpoint",
    "config",
    "constant",
    "variable",
]

CodeFactType = Literal[
    "server_port",
    "database_type",
    "api_endpoint",
    "token_expiry_minutes",
    "supported_extension",
    "external_service_url",
    "framework",
    "max_upload_size",
    "environment_variable",
    "symbol_exists",
]

FactEnvironment = Literal[
    "production",
    "development",
    "test",
    "unknown",
]


# 콘텐츠 청크
ContentChunkType = Literal[
    "document_text",
    "code_symbol",
    "config_text",
    "image_ocr",
    "meeting_segment",
    "meeting_summary",
]


# 음성 회의
MeetingInputType = Literal[
    "live_recording",
    "audio_upload",
]

MeetingStatus = Literal[
    "created",
    "recording",
    "processing",
    "completed",
    "failed",
    "cancelled",
]

GenerationStatus = Literal[
    "pending",
    "processing",
    "completed",
    "failed",
]

DecisionStatus = Literal[
    "active",
    "superseded",
    "cancelled",
]

ActionItemStatus = Literal[
    "open",
    "in_progress",
    "done",
    "cancelled",
]

ActionItemPriority = Literal[
    "low",
    "medium",
    "high",
]


# 모순 감지
ContradictionSourceType = Literal[
    "meeting_segment",
    "room_message",
]

ContradictionReferenceType = Literal[
    "content_chunk",
    "code_fact",
]

ContradictionSeverity = Literal[
    "low",
    "medium",
    "high",
]

ContradictionStatus = Literal[
    "unresolved",
    "resolved",
    "dismissed",
]

ContradictionResolutionType = Literal[
    "change_acknowledged",
    "keep_reference",
]

ChangeSummaryContextType = Literal[
    "meeting",
    "chat",
]

# AI Chat
AIChatRole = Literal[
    "user",
    "assistant",
    "system",
]

AIMessageSourceType = Literal[
    "content_chunk",
    "code_fact",
]


# 알림
NotificationType = Literal[
    "contradiction_detected",
    "contradiction_resolved",
    "meeting_summary_ready",
    "file_analysis_completed",
    "file_analysis_failed",
]