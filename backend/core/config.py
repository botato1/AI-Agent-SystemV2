import os
from dotenv import load_dotenv


# .env 파일에 적힌 환경변수 값을 불러옴
load_dotenv()


class Settings:
    # 프로젝트 기본 이름
    PROJECT_NAME: str = "AI-Agent-System"

    # SQLite DB 파일 경로
    SQLITE_DB_PATH: str = os.getenv(
        "SQLITE_DB_PATH",
        "storage/sqlite/chat.db"
    )

    # Ollama 서버 주소
    OLLAMA_BASE_URL: str = os.getenv(
        "OLLAMA_BASE_URL",
        "http://localhost:11434"
    )

    # Ollama에서 사용할 모델명
    OLLAMA_MODEL_NAME: str = os.getenv(
        "OLLAMA_MODEL_NAME",
        "qwen2.5"
    )

    # JWT 토큰 서명에 사용할 비밀키
    JWT_SECRET_KEY: str | None = os.getenv("JWT_SECRET_KEY")

    # JWT 알고리즘
    JWT_ALGORITHM: str = os.getenv(
        "JWT_ALGORITHM",
        "HS256"
    )

    # Access Token 만료 시간
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    )

    # Refresh Token 만료 시간
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(
        os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")
    )

    DATA_ENCRYPTION_MASTER_KEY: str | None = os.getenv("DATA_ENCRYPTION_MASTER_KEY")
    DATA_ENCRYPTION_KEY_VERSION: str = os.getenv("DATA_ENCRYPTION_KEY_VERSION", "v1")

    # 파일 저장 경로 (NAS 연결 시 활성화)
    # STORAGE_PATH: str = os.getenv("STORAGE_PATH", "storage/uploads")


# 다른 파일에서 settings.SQLITE_DB_PATH 이런 식으로 쓰기 위한 객체
settings = Settings()