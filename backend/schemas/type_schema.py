# backend/schemas/type_schema.py
from typing import Literal, Final

# question_type
# v1 - 현재 실제 라우팅에 쓰이는 값
QuestionTypeV1 = Literal[
    "task_from_rag",
    "task_from_memory",
    "knowledge_search",
    "general_answer",
    "summary_from_rag",
]

# v2 - 법률 서비스 기준 question_type
QuestionTypeV2 = Literal[
    "contract_risk_check",   # 계약서 위험조항 검증
    "statute_search",        # 법조문 검색
    "precedent_search",      # 판례 검색
    "legal_search",          # 법조문 + 판례 통합 검색
    "general_answer",        # 법률 무관 일반 답변
    "consultation_summary",  # 상담 요약/사건카드 생성
]

# v1/v2 혼용 기간 동안 함께 허용
QuestionType = QuestionTypeV1 | QuestionTypeV2

# question_type 기본값
DEFAULT_QUESTION_TYPE: Final[QuestionType] = "general_answer"


# document_type
# v2 법률 도메인 문서 타입
DocumentTypeV2 = Literal[
    "contract",
    "evidence",
    "consultation_audio",
    "consultation_note",
    "precedent_ref",
]

# v1 legacy 문서 타입
LegacyDocumentType = Literal[
    "document",
    "meeting",
    "voice",
]

# v1/v2 혼용 기간 동안 함께 허용하는 공통 문서 타입
DocumentType = DocumentTypeV2 | LegacyDocumentType

# 문서 타입 기본값
DEFAULT_DOCUMENT_TYPE: Final[DocumentType] = "document"