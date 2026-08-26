"""일반 문서 분석 CRUD (정승현 파트 — 기본 템플릿)"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.modules.document import DocumentAnalysis, DocumentFigure


def create_document_analysis(db: Session, file_id: uuid.UUID, **fields) -> DocumentAnalysis:
    row = DocumentAnalysis(file_id=file_id, **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_document_analysis(db: Session, file_id: uuid.UUID) -> Optional[DocumentAnalysis]:
    return db.query(DocumentAnalysis).filter(DocumentAnalysis.file_id == file_id).first()


def ocr_success_rate(analysis: DocumentAnalysis) -> Optional[float]:
    """ocr_required_pages=0이면 OCR 미사용 -> None(N/A)."""
    if not analysis.ocr_required_pages:
        return None
    return round(analysis.ocr_success_pages / analysis.ocr_required_pages * 100, 2)

def update_document_analysis(db: Session, file_id: uuid.UUID, **fields) -> Optional[DocumentAnalysis]:
    row = get_document_analysis(db, file_id)
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
        db.commit()
        db.refresh(row)
    return row

def delete_figures_by_file(db: Session, file_id: uuid.UUID) -> None:
    db.query(DocumentFigure).filter(DocumentFigure.file_id == file_id).delete()
    db.commit()


def create_document_figures(db: Session, file_id: uuid.UUID, figures: list[dict]) -> list[DocumentFigure]:
    rows = [
        DocumentFigure(
            file_id=file_id,
            page_number=f["page_number"],
            figure_type=f["figure_type"],
            image_url=f["image_url"],
            display_order=i,
        )
        for i, f in enumerate(figures)
    ]
    db.add_all(rows)
    db.commit()
    for r in rows:
        db.refresh(r)
    return rows


def list_figures_by_file(db: Session, file_id: uuid.UUID) -> list[DocumentFigure]:
    return (
        db.query(DocumentFigure)
        .filter(DocumentFigure.file_id == file_id)
        .order_by(DocumentFigure.page_number, DocumentFigure.display_order)
        .all()
    )