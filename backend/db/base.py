"""DB 연결의 최소 단위 — engine과 declarative Base만 정의한다."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://recall:recall@localhost:5432/recall"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base = declarative_base()


def init_db():
    """개발 초기 셋업용. 운영에서는 Alembic 마이그레이션 사용을 권장."""
    from backend.db import modules  # noqa: F401  (전체 모델 등록을 위해 필요)

    Base.metadata.create_all(bind=engine)
