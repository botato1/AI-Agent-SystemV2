import json
import os

from dotenv import load_dotenv


# .env 파일에 적힌 환경변수 값을 불러옴
load_dotenv()


# DATA_ENCRYPTION_MASTER_KEYS는 env에서 문자열로만 들어오므로
# JSON 형태({"v1": "base64...", "v2": "base64..."})로 파싱해 dict로 변환한다.
# 마스터 키 로테이션 시 이전 버전 키를 이 dict에 계속 남겨둔 채 새 버전을 추가해야
# 과거 데이터의 복호화가 계속 가능하다.
def _parse_master_keys(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            "DATA_ENCRYPTION_MASTER_KEYS는 JSON 객체 형식이어야 합니다. "
            '예: {"v1": "base64...", "v2": "base64..."}'
        ) from e

    if not isinstance(parsed, dict):
        raise ValueError("DATA_ENCRYPTION_MASTER_KEYS는 JSON 객체({...}) 형식이어야 합니다.")

    return parsed


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

    # 하위호환용 단일 마스터 키 (DATA_ENCRYPTION_MASTER_KEYS 미설정 시 fallback)
    DATA_ENCRYPTION_MASTER_KEY: str | None = os.getenv("DATA_ENCRYPTION_MASTER_KEY")

    # 버전별 마스터 키 목록. 로테이션 지원을 위해 여러 버전을 동시에 보관.
    # .env 예: DATA_ENCRYPTION_MASTER_KEYS={"v1": "base64...", "v2": "base64..."}
    DATA_ENCRYPTION_MASTER_KEYS: dict[str, str] = _parse_master_keys(
        os.getenv("DATA_ENCRYPTION_MASTER_KEYS")
    )

    # 현재 신규 암호화에 사용할 활성 마스터 키 버전
    DATA_ENCRYPTION_KEY_VERSION: str = os.getenv("DATA_ENCRYPTION_KEY_VERSION", "v1")

    # 파일 저장 경로 (NAS 연결 시 활성화)
    # STORAGE_PATH: str = os.getenv("STORAGE_PATH", "storage/uploads")

    # SMTP 서버 설정 (비밀번호 재설정 이메일 발송용)
    SMTP_HOST: str | None = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str | None = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "noreply@recall.app")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    # 비밀번호 재설정 토큰 만료 시간 (분)
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "30")
    )

    # 프론트엔드 비밀번호 재설정 페이지 URL (이메일 링크에 포함)
    FRONTEND_PASSWORD_RESET_URL: str = os.getenv(
        "FRONTEND_PASSWORD_RESET_URL",
        "http://localhost:5173/reset-password"
    )
    
    # 프론트엔드 회원가입 페이지 URL (워크스페이스 초대 메일 링크에 포함)
    FRONTEND_SIGNUP_URL: str = os.getenv(
        "FRONTEND_SIGNUP_URL",
        "http://localhost:5173/signup"
    )

# 다른 파일에서 settings.SQLITE_DB_PATH 이런 식으로 쓰기 위한 객체
settings = Settings()