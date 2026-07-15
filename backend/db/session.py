"""세션 팩토리 및 FastAPI Depends용 get_db."""

from sqlalchemy.orm import sessionmaker

from backend.db.base import engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI Depends(get_db)로 사용."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
