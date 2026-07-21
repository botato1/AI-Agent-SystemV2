# backend/services/meeting_service.py

import asyncio
import subprocess
import uuid

from backend.db.crud import meeting_crud
from backend.db.session import SessionLocal
from backend.graphs.contradiction_graph import run_contradiction_detection
from backend.graphs.meeting_postprocess_graph import run_meeting_postprocess
from backend.services.stt_stream_client import SttStreamClient


# 8002가 요구하는 PCM 포맷(PCM16LE, 16kHz, mono)에 맞춘 청크 크기
# 100ms 분량: 16000 samples/sec * 2 bytes/sample * 0.1 sec
PCM_CHUNK_BYTES = 3200

FFMPEG_TIMEOUT_SECONDS = 120

# 연결은 보통 수 초 내에 끝나므로 짧게 설정하고,
# 스트리밍(전송 + 수신)은 길게 별도로 설정한다.
STT_CONNECT_TIMEOUT_SECONDS = 20
STT_STREAM_TIMEOUT_SECONDS = 600


def _convert_to_pcm16(file_content: bytes) -> bytes:
    """업로드된 오디오를 PCM16LE, 16kHz, mono 형식으로 변환한다."""

    try:
        process = subprocess.run(
            [
                "ffmpeg",
                "-i",
                "pipe:0",
                "-f",
                "s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                "pipe:1",
            ],
            input=file_content,
            capture_output=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )

    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"ffmpeg 변환이 {FFMPEG_TIMEOUT_SECONDS}초 내에 끝나지 않았습니다."
        ) from exc

    if process.returncode != 0:
        error_message = process.stderr.decode(errors="ignore")[:500]

        raise RuntimeError(
            f"ffmpeg 변환 실패: {error_message}"
        )

    return process.stdout


async def _stream_and_receive_segments(
    stt_client: SttStreamClient,
    pcm_data: bytes,
) -> list[dict]:
    """
    PCM 송신과 STT 응답 수신을 동시에 처리한다.

    전체 오디오 전송이 끝날 때까지 수신을 미루면,
    STT 서버가 전송하는 partial/final 메시지가 쌓일 수 있으므로
    송신과 수신을 별도 Task로 동시에 실행한다.
    """

    async def _send_audio() -> None:
        for index in range(0, len(pcm_data), PCM_CHUNK_BYTES):
            chunk = pcm_data[index:index + PCM_CHUNK_BYTES]
            await stt_client.send_audio(chunk)

        await stt_client.send_end()

    async def _receive_segments() -> list[dict]:
        pending_segments: list[dict] = []

        async for data in stt_client.receive():
            message_type = data.get("type")

            if message_type == "final":
                final_data = data.get("final", {})
                segments = final_data.get("segments", [])

                for segment in segments:
                    try:
                        pending_segments.append(
                            {
                                "content": segment.get("text", ""),
                                "start_ms": int(segment["start"] * 1000),
                                "end_ms": int(segment["end"] * 1000),
                                "segment_index": len(pending_segments),
                                "speaker_label": segment.get("speaker"),
                            }
                        )

                    except (KeyError, TypeError, ValueError) as exc:
                        print(
                            "[meeting_service] "
                            f"세그먼트 파싱 실패, 건너뜀: {repr(exc)}"
                        )

            elif message_type == "session_end":
                break

        return pending_segments

    send_task = asyncio.create_task(_send_audio())
    receive_task = asyncio.create_task(_receive_segments())

    try:
        _, pending_segments = await asyncio.gather(
            send_task,
            receive_task,
        )

        return pending_segments

    finally:
        # wait_for() 타임아웃이나 한쪽 Task 예외 발생 시
        # 남아 있는 Task가 계속 실행되지 않도록 정리한다.
        for task in (send_task, receive_task):
            if not task.done():
                task.cancel()

        await asyncio.gather(
            send_task,
            receive_task,
            return_exceptions=True,
        )


def _save_segments_bulk(
    meeting_id: uuid.UUID,
    segments: list[dict],
) -> list[tuple[str, str]]:
    """
    worker thread 내부에서 전용 DB Session을 생성해 세그먼트를 저장한다.

    반환 시 ORM 객체를 그대로 넘기지 않고,
    세션 종료 후에도 사용할 수 있는 ID와 content만 반환한다.
    """

    db = SessionLocal()

    try:
        rows = meeting_crud.add_segments_bulk(
            db,
            meeting_id,
            segments,
        )

        return [
            (
                str(row.id),
                row.content or "",
            )
            for row in rows
        ]

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


async def _detect_uploaded_audio_contradictions(
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    saved_segments: list[tuple[str, str]],
) -> None:
    """
    업로드 음성에서 생성된 각 발화 세그먼트의 모순을 탐지한다.

    다수의 LLM 요청이 한꺼번에 실행되는 것을 막기 위해 순차 처리한다.
    개별 모순 감지 실패는 회의 요약 및 후처리 결과에 영향을 주지 않는다.
    """

    for segment_id, content in saved_segments:
        statement_text = content.strip()

        if not statement_text:
            continue

        try:
            await asyncio.to_thread(
                run_contradiction_detection,
                workspace_id=str(workspace_id),
                category_id=str(category_id),
                source_type="meeting_segment",
                statement_text=statement_text,
                meeting_segment_id=segment_id,
            )

        except Exception as exc:
            print(
                "[meeting_service] "
                f"모순 감지 실패: segment_id={segment_id}, "
                f"error={repr(exc)}"
            )


def _mark_failed(db, meeting_id: uuid.UUID) -> None:
    """
    processing 상태인 회의만 failed로 변경한다.

    DB 세션이 오류 상태라면 rollback 후 한 번 더 시도한다.
    상태 변경 실패가 원래 처리 예외를 가리지 않도록 최종 실패는 로그만 남긴다.
    """

    try:
        transitioned = meeting_crud.try_transition_meeting_status(
            db,
            meeting_id,
            from_status="processing",
            to_status="failed",
        )

    except Exception as first_exc:
        db.rollback()

        try:
            transitioned = meeting_crud.try_transition_meeting_status(
                db,
                meeting_id,
                from_status="processing",
                to_status="failed",
            )

        except Exception as retry_exc:
            print(
                "[meeting_service] "
                f"meeting_id={meeting_id}를 failed로 변경하지 못했습니다. "
                f"first_error={repr(first_exc)}, "
                f"retry_error={repr(retry_exc)}"
            )
            return

    if transitioned is None:
        print(
            "[meeting_service] "
            f"meeting_id={meeting_id}는 processing 상태가 아니므로 "
            "failed로 변경하지 않습니다."
        )


async def process_uploaded_audio_stt(
    meeting_id: uuid.UUID,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    file_content: bytes,
) -> None:
    """
    업로드된 음성 파일을 8002 STT 서버로 전송한다.

    처리 순서:
    1. created -> processing 상태 전이
    2. ffmpeg를 이용한 PCM 변환
    3. STT 송신 및 수신
    4. 발화 세그먼트 일괄 저장
    5. 회의 요약, 결정사항, 할 일 생성
    6. 발화별 모순 감지
    """

    db = SessionLocal()

    try:
        # created -> processing 원자적 전이
        # 이미 다른 작업에서 상태가 변경된 경우 중복 처리를 시작하지 않는다.
        transitioned = meeting_crud.try_transition_meeting_status(
            db,
            meeting_id,
            from_status="created",
            to_status="processing",
        )

        if transitioned is None:
            print(
                "[meeting_service] "
                f"meeting_id={meeting_id}가 created 상태가 아니어서 "
                "STT 처리를 시작하지 않습니다."
            )
            return

        try:
            pcm_data = await asyncio.to_thread(
                _convert_to_pcm16,
                file_content,
            )

        except Exception as exc:
            meeting_crud.update_meeting_status(
                db,
                meeting_id,
                status="failed",
            )

            print(
                "[meeting_service] "
                f"오디오 변환 실패: {repr(exc)}"
            )
            return

        stt_client = SttStreamClient(
            session_id=str(meeting_id)
        )

        try:
            await asyncio.wait_for(
                stt_client.connect(),
                timeout=STT_CONNECT_TIMEOUT_SECONDS,
            )

        except Exception as exc:
            meeting_crud.update_meeting_status(
                db,
                meeting_id,
                status="failed",
            )

            print(
                "[meeting_service] "
                f"STT 서버 연결 실패: {repr(exc)}"
            )
            return

        try:
            pending_segments = await asyncio.wait_for(
                _stream_and_receive_segments(
                    stt_client,
                    pcm_data,
                ),
                timeout=STT_STREAM_TIMEOUT_SECONDS,
            )

        except asyncio.TimeoutError:
            meeting_crud.update_meeting_status(
                db,
                meeting_id,
                status="failed",
            )

            print(
                "[meeting_service] "
                f"STT 스트리밍 타임아웃: meeting_id={meeting_id}"
            )
            return

        finally:
            await stt_client.close()

        if not pending_segments:
            meeting_crud.update_meeting_status(
                db,
                meeting_id,
                status="failed",
            )

            print(
                "[meeting_service] "
                f"STT 결과에 세그먼트가 없습니다: meeting_id={meeting_id}"
            )
            return

        # DB 저장 작업을 worker thread에서 실행하며,
        # 해당 thread 안에서 별도 Session을 생성한다.
        saved_segments = await asyncio.to_thread(
            _save_segments_bulk,
            meeting_id,
            pending_segments,
        )

        if not saved_segments:
            meeting_crud.update_meeting_status(
                db,
                meeting_id,
                status="failed",
            )

            print(
                "[meeting_service] "
                f"저장된 세그먼트가 없습니다: meeting_id={meeting_id}"
            )
            return

        # 세그먼트 청킹·임베딩과 회의 요약,
        # 결정사항 및 할 일 생성을 먼저 완료한다.
        await asyncio.to_thread(
            run_meeting_postprocess,
            meeting_id=str(meeting_id),
            workspace_id=str(workspace_id),
            category_id=str(category_id),
        )

        # 후처리 과정에서 세그먼트가 ChromaDB에 등록된 뒤
        # 각 발화에 대한 모순 탐지를 수행한다.
        await _detect_uploaded_audio_contradictions(
            workspace_id,
            category_id,
            saved_segments,
        )

    except Exception as exc:
        _mark_failed(
            db,
            meeting_id,
        )

        print(
            "[meeting_service] "
            f"음성 파일 STT 처리 중 예외 발생: {repr(exc)}"
        )

    finally:
        db.close()