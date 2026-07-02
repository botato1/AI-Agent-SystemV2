# 법률 분석 결과 구조
from typing import Optional, Literal
from pydantic import BaseModel, Field

LegalRefType = Literal["law", "precedent", "contract", "evidence"]      # 법률 근거의 종류를 제한(법률, 판례, 계약서 조항, 증거자료)
RiskLevel = Literal["low", "medium", "high", "urgent"]                  # 위험도를 나타내는 타입(낮음, 보통, 높음, 긴급)


# 법률 근거 구조
class LegalRefSchema(BaseModel):
    ref_type: LegalRefType          # 근거 종류
    title: str                      # 근거 제목
    article: Optional[str] = None   # 법 조항
    case_no: Optional[str] = None   # 판례 번호
    source_document_id: Optional[str] = None    # 내부 문서 ID
    source_chunk_id: Optional[str] = None       # 내부 chunk ID
    content: Optional[str] = None               # 근거 내용
    is_verified: bool = False                   # 사람이 검증했는지 여부

# 위험 조항/요소 구조
class RiskClauseSchema(BaseModel):
    clause: Optional[str] = None                # 문제되는 조항명
    issue: str                                  # 어떤 문제가 있는지
    reason: str                                 # 문제의 이유
    risk_level: RiskLevel = "medium"            # 위험도
    source_document_id: Optional[str] = None    # 이 조항이 나오느 문서 ID
    source_clause: Optional[str] = None         # 원문 조항 번호 또는 조항명
    related_legal_refs: list[LegalRefSchema] = Field(default_factory=list)   # 위험 판단과 관련된 법령/판례 근거 목록

# 법률 분석 전체 결과를 담는 구조
class LegalAnalysisResultSchema(BaseModel):
    legal_issues: list[str] = Field(default_factory=list)                   # 발견된 법률 쟁점 목록
    risk_clauses: list[RiskClauseSchema] = Field(default_factory=list)      # 위험 조항 목록
    missing_checks: list[str] = Field(default_factory=list)                 # 추가로 확인해야하는 사항
    recommendations: list[str] = Field(default_factory=list)                # 추천 조치 또는 개선 방향