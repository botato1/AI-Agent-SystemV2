# Python 3.11 slim 베이스 이미지 사용
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 설치 (필요한 경우)
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl --version

# torch(+cu121)는 용량이 커서(약 780MB) requirements.txt와 분리한다.
# requirements.txt가 바뀌어도 이 레이어는 캐시되어 재다운로드하지 않는다.
RUN pip install --no-cache-dir torch==2.5.1+cu121 torchaudio==2.5.1+cu121 torchvision==0.20.1+cu121 --index-url https://download.pytorch.org/whl/cu121

# requirements.txt 먼저 복사 후 패키지 설치
# (코드 변경 시 캐시 활용을 위해 분리)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 전체 코드 복사
COPY . .

# storage 폴더 생성 (SQLite, 업로드 파일 저장용)
RUN mkdir -p storage/sqlite storage/uploads

# 포트 개방
EXPOSE 8000

# 서버 실행 (운영 환경용 워커 4개) @@@@@#예시# 서버 GPU환경 확인 필요@@@@@@@@@
CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4"]
