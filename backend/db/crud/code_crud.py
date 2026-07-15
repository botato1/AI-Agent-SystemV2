"""코드 분석 CRUD — 내 파트

tree-sitter로 뽑은 심볼/사실을 저장하고, 모순 감지 시 code_fact 조회에 쓴다.
"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.modules import CodeAnalysis, CodeFact, CodeSymbol


def create_code_analysis(db: Session, file_id: uuid.UUID, **fields) -> CodeAnalysis:
    row = CodeAnalysis(file_id=file_id, **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_code_analysis_by_file(db: Session, file_id: uuid.UUID) -> Optional[CodeAnalysis]:
    return db.query(CodeAnalysis).filter(CodeAnalysis.file_id == file_id).first()


def bulk_create_symbols(db: Session, symbols: list[dict]) -> list[CodeSymbol]:
    """tree-sitter 파싱 결과(dict 리스트)를 한 번에 저장."""
    rows = [CodeSymbol(**s) for s in symbols]
    db.add_all(rows)
    db.commit()
    for r in rows:
        db.refresh(r)
    return rows


def get_symbols_by_file(db: Session, file_id: uuid.UUID) -> list[CodeSymbol]:
    return db.query(CodeSymbol).filter(CodeSymbol.file_id == file_id).all()


def find_symbol_by_name(
    db: Session, workspace_id: uuid.UUID, symbol_name: str
) -> list[CodeSymbol]:
    """'search_documents 함수 어디서 쓰여?' 같은 질문의 1차 조회."""
    return (
        db.query(CodeSymbol)
        .filter(
            CodeSymbol.workspace_id == workspace_id,
            CodeSymbol.symbol_name == symbol_name,
        )
        .all()
    )


def bulk_create_facts(db: Session, facts: list[dict]) -> list[CodeFact]:
    rows = [CodeFact(**f) for f in facts]
    db.add_all(rows)
    db.commit()
    for r in rows:
        db.refresh(r)
    return rows


def find_facts_by_key(
    db: Session,
    workspace_id: uuid.UUID,
    fact_type: str,
    fact_key: str,
    environment: str = "production",
) -> list[CodeFact]:
    """
    모순 감지 파이프라인의 '규칙 기반 값 비교' 단계에서 사용.
    예: fact_type='server_port', fact_key='fastapi' -> 현재 설정된 포트값 조회
    """
    return (
        db.query(CodeFact)
        .filter(
            CodeFact.workspace_id == workspace_id,
            CodeFact.fact_type == fact_type,
            CodeFact.fact_key == fact_key,
            CodeFact.environment == environment,
        )
        .all()
    )
