# Python 3.12 slim 베이스 이미지 사용
# [수정] 서버가 ARM64(aarch64)라 cu121 인덱스에 이 조합의 wheel이 없어 빌드가
# 안 됐음 - 같은 서버에서 GPU까지 정상 동작 중인 jupyter-s202410771 컨테이너
# 기준으로 3.12 + torch(cu121 인덱스 없이 기본 PyPI)로 검증 완료.
FROM python:3.12-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 설치 (필요한 경우)
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl --version

# torch는 용량이 커서(약 780MB) requirements.txt와 분리한다.
# requirements.txt가 바뀌어도 이 레이어는 캐시되어 재다운로드하지 않는다.
# [수정] ARM64엔 cu121 인덱스에 wheel이 없어 --index-url 제거, 기본 PyPI에서 설치.
# torchaudio가 torch보다 낮은 버전(2.11.0)인 게 이상해 보일 수 있는데, 팀원이
# jupyter-s202410771 컨테이너에서 이 정확한 조합으로 GPU 동작까지 검증한 값을
# 그대로 사용함 (임의로 버전 맞추지 말 것).
RUN pip install --no-cache-dir torch==2.13.0 torchaudio==2.11.0 torchvision==0.28.0

# requirements.txt + backend_requirements.txt 먼저 복사 후 패키지 설치
# (코드 변경 시 캐시 활용을 위해 분리)
# [수정] backend_requirements.txt(sqlalchemy/psycopg2-binary/python-jose 등
# 핵심 런타임 의존성)가 설치 안 되고 있었음 - 지금까지 이 Dockerfile로 빌드한
# 이미지는 fastapi 기동 시 ModuleNotFoundError로 죽었을 것.
COPY requirements.txt backend/backend_requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r backend_requirements.txt

# 전체 코드 복사
COPY . .

# storage 폴더 생성 (SQLite, 업로드 파일 저장용)
RUN mkdir -p storage/sqlite storage/uploads

# 포트 개방
EXPOSE 8000

# [수정 - 지수 리포트] 워커 4개(멀티프로세스)에서는 meeting_ws_router.py의
# _VIEWER_CONNECTIONS/_MEETING_SPEAKER_MAPS가 프로세스 로컬 dict라 워커마다
# 따로 놀아서, 이벤트를 처리하는 워커와 WS 연결을 든 워커가 다르면 실시간
# push가 조용히 유실됨. Redis pub/sub 등 프로세스 간 공유로 가기 전까지
# 임시로 워커 1개로 낮춰 정합성을 우선한다 (동시처리량 저하 트레이드오프 있음).
CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]
