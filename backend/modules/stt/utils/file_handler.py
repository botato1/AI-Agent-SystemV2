import os
import shutil
import subprocess
import uuid
from fastapi import UploadFile
from modules.stt.core.config import UPLOAD_DIR, logger

def save_upload_file(upload_file: UploadFile) -> str:
    """업로드된 파일을 임시 저장하고, Whisper용 16kHz WAV로 강제 변환합니다."""
    
    # 1. 원본 파일 임시 저장 (.m4a, .mp3 등)
    original_ext = os.path.splitext(upload_file.filename)[1]
    temp_filename = f"temp_{uuid.uuid4().hex}{original_ext}"
    temp_path = os.path.join(UPLOAD_DIR, temp_filename)
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
        
    # 2. 변환될 WAV 파일 경로 지정
    wav_filename = f"audio_{uuid.uuid4().hex}.wav"
    wav_path = os.path.join(UPLOAD_DIR, wav_filename)
    
    # 3. 파이썬 내장 subprocess로 FFmpeg 직접 호출 (충돌 0%)
    try:
        logger.info(f"🔄 FFmpeg 오디오 정규화 시작: {upload_file.filename} -> 16kHz WAV")
        cmd = [
                "ffmpeg", "-y", "-i", temp_path,
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav_path
]
        # 변환 실행
        subprocess.run(cmd, check=True)
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ FFmpeg 변환 실패: {e.stderr.decode()}")
        raise RuntimeError("오디오 파일을 WAV로 변환하는 데 실패했습니다. FFmpeg가 설치되어 있는지 확인하세요.")
    finally:
        # 변환이 끝났으니 원본 파일(.m4a 등)은 즉시 삭제
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    logger.info(f"✅ WAV 변환 완료: {wav_path}")
    
    # 변환된 완벽한 규격의 WAV 파일 경로를 반환 (이제 Whisper 엔진으로 들어감)
    return wav_path

def cleanup_files(*file_paths):
    """사용이 끝난 임시 파일들을 안전하게 삭제합니다."""
    for path in file_paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"🗑️ 임시 파일 삭제 완료: {path}")
            except Exception as e:
                logger.warning(f"⚠️ 파일 삭제 실패 ({path}): {e}")