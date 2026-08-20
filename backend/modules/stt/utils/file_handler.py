import os
import shutil
import subprocess
import uuid
from fastapi import UploadFile
from ..core.config import UPLOAD_DIR, logger


def save_upload_file(upload_file: UploadFile) -> str:
    """업로드된 파일을 임시 저장하고, faster-whisper용 16kHz WAV로 강제 변환합니다."""

    original_ext = os.path.splitext(upload_file.filename)[1]
    temp_filename = f"temp_{uuid.uuid4().hex}{original_ext}"
    temp_path = os.path.join(UPLOAD_DIR, temp_filename)

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)

    wav_filename = f"audio_{uuid.uuid4().hex}.wav"
    wav_path = os.path.join(UPLOAD_DIR, wav_filename)

    try:
        logger.info(f"🔄 FFmpeg 오디오 정규화 시작: {upload_file.filename} -> 16kHz WAV")
        cmd = [
            "ffmpeg", "-y", "-i", temp_path,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav_path
        ]
        # 핵심 수정: stderr를 캡처해야 e.stderr가 None이 아니라 실제 에러 메시지를 담음
        subprocess.run(cmd, check=True, capture_output=True)

    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr.decode() if e.stderr else "알 수 없는 FFmpeg 에러"
        logger.error(f"❌ FFmpeg 변환 실패: {stderr_msg}")
        raise RuntimeError(f"오디오 파일을 WAV로 변환하는 데 실패했습니다: {stderr_msg}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    logger.info(f"✅ WAV 변환 완료: {wav_path}")
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