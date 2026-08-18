import os
import logging
import platform
import sys

# 기본 디렉토리 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

# 운영체제별 확장자 처리 (Windows는 .exe 포함)
EXE_EXT = ".exe" if platform.system() == "Windows" else ""

# AI 엔진 및 스크립트 경로
WHISPER_CLI = os.path.join(BASE_DIR, "whisper.cpp", "build", "bin", f"whisper-cli{EXE_EXT}")
WHISPER_MODEL = os.path.join(BASE_DIR, "whisper.cpp", "models", "ggml-large-v3-turbo.bin")
DIARIZE_SCRIPT = os.path.join(BASE_DIR, "diarize_engine.py")

# 현재 활성화된 파이썬(가상환경) 실행 경로를 자동으로 가져옴
PYTHON_EXEC = sys.executable

# uploads 폴더 자동 생성
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 로거 설정
logger = logging.getLogger("vigo_project")
logger.setLevel(logging.INFO)