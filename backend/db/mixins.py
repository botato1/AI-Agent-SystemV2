"""모델 전반에서 공통으로 쓰는 컬럼 헬퍼.

models/*.py 에서:
    from backend.db.mixins import uuid_pk, created_at_col, updated_at_col
"""

from sqlalchemy import Column, DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID


def uuid_pk() -> Column:
    """UUID PK 컬럼. pgcrypto의 gen_random_uuid() 사용."""
    return Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def created_at_col() -> Column:
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now())


def updated_at_col() -> Column:
    return Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
