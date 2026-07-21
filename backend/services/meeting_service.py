# backend/services/meeting_service.py

import asyncio
import subprocess
import uuid

from backend.db.crud import meeting_crud
from backend.db.session import SessionLocal
from backend.graphs.meeting_postprocess_graph import run_meeting_postprocess
from backend.services.stt_stream_client import SttStreamClient

# 8002가 요구하는 PCM 포맷(PCM16LE, 16kHz, mono)에 맞춘 청크 크기: 100ms 분량
PCM_CHUNK_BYTES = 3200  # 16000 samples/sec * 2 bytes/sample * 0.1 sec

# STT 세션(전송+수신) 전체에 대한 제한 시간 — 8002가 응답을 멈춰도 회의가
# processing에 영구히 남지 않도록 함
STT_SESSION_TIMEOUT_SECONDS = 600


# 업로드된 오디오(mp3/wav/m4a/webm)를 8002가 요구하는 PCM16LE/16kHz/mono 원시 바이트로 변환
def _convert_to_pcm16(file_content: bytes) -> bytes:
    process = subprocess.run(
        ["ffmpeg", "-i", "pipe:0", "-f", "s16le", "-ar", "16000", "-ac", "1", "pipe:1"],
        input=file_content,
        capture_output=True,
    )
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg 변환 실패: {process.stderr.decode(errors='ignore')[:500]}")
    return process.stdout


async def _stream_and_receive_segments(
    stt_client: SttStreamClient, pcm_data: bytes, db, meeting_id: uuid.UUID,
) -> int:
    """PCM을 8002로 전송하고 세그먼트를 받아 저장한다. 저장된 세그먼트 개수를 반환."""
    next_index = 0
    for i in range(0, len(pcm_data), PCM_CHUNK_BYTES):
        await stt_client.send_audio(pcm_data[i:i + PCM_CHUNK_BYTES])
    await stt_client.send_end()

    async for data in stt_client.receive():
        msg_type = data.get("type")

        if msg_type == "final":
            for seg in data.get("final", {}).get("segments", []):
                try:
                    meeting_crud.add_segment(
                        db,
                        meeting_id=meeting_id,
                        content=seg.get("text", ""),
                        start_ms=int(seg["start"] * 1000),
                        end_ms=int(seg["end"] * 1000),
                        segment_index=next_index,
                        speaker_label=seg.get("speaker"),
                    )
                    next_index += 1
                except Exception as e:
                    db.rollback()
                    print(f"[meeting_service] 세그먼트 저장 실패: {repr(e)}")

        elif msg_type == "session_end":
            break

    return next_index


def _mark_failed(db, meeting_id: uuid.UUID) -> None:
    """실패 상태로 전환. 이 호출 자체가 실패하면(세션이 깨진 상태) rollback 후 한 번 더 시도."""
    try:
        meeting_crud.update_meeting_status(db, meeting_id, status="failed")
    except Exception:
        db.rollback()
        meeting_crud.update_meeting_status(db, meeting_id, status="failed")


# 업로드된 음성 파일을 8002로 스트리밍해 STT 처리하고, 끝나면 회의 후처리(요약 생성)까지 트리거
async def process_uploaded_audio_stt(
    meeting_id: uuid.UUID, workspace_id: uuid.UUID, category_id: uuid.UUID, file_content: bytes,
) -> None:
    db = SessionLocal()
    try:
        meeting_crud.update_meeting_status(db, meeting_id, status="processing")

        try:
            pcm_data = await asyncio.to_thread(_convert_to_pcm16, file_content)
        except Exception as e:
            meeting_crud.update_meeting_status(db, meeting_id, status="failed")
            print(f"[meeting_service] 오디오 변환 실패: {repr(e)}")
            return

        stt_client = SttStreamClient(session_id=str(meeting_id))
        try:
            await asyncio.wait_for(stt_client.connect(), timeout=STT_SESSION_TIMEOUT_SECONDS)
        except Exception as e:
            meeting_crud.update_meeting_status(db, meeting_id, status="failed")
            print(f"[meeting_service] STT 서버 연결 실패: {repr(e)}")
            return

        try:
            next_index = await asyncio.wait_for(
                _stream_and_receive_segments(stt_client, pcm_data, db, meeting_id),
                timeout=STT_SESSION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            meeting_crud.update_meeting_status(db, meeting_id, status="failed")
            print(f"[meeting_service] STT 응답 타임아웃: meeting_id={meeting_id}")
            return
        finally:
            await stt_client.close()

        if next_index == 0:
            meeting_crud.update_meeting_status(db, meeting_id, status="failed")
            print(f"[meeting_service] STT 결과에 세그먼트가 없습니다: meeting_id={meeting_id}")
            return

        await asyncio.to_thread(
            run_meeting_postprocess,
            meeting_id=str(meeting_id),
            workspace_id=str(workspace_id),
            category_id=str(category_id),
        )

    except Exception as e:
        _mark_failed(db, meeting_id)
        print(f"[meeting_service] 음성 파일 STT 처리 중 예외 발생: {repr(e)}")
    finally:
        db.close()