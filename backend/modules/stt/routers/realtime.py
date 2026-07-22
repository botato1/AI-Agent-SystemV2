import asyncio
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.config import logger
from ..services.realtime_service import RealtimeSTTSession
from ..services.speaker_id_service import LiveSpeakerIdentifier
from ..services.meeting_store import MeetingRecord
from ..services.refine_service import refine_meeting

router = APIRouter()


def _leave_group(app_state, session_id: str, participant_name: str) -> bool:
    """
    "각자 PC" 모드에서 참가자 한 명을 그룹에서 제거.
    반환값이 True면 이 참가자가 마지막이었다는 뜻 — 공유 회의록을 확정(finalize)해야 함.
    (참조 카운트처럼 동작: 마지막 한 명이 나갈 때만 회의 전체가 끝남)
    """
    participants = app_state.active_group_participants.get(session_id)
    if participants is None:
        return True  # 이미 정리된 상태 — 방어적으로 종료 처리
    participants.discard(participant_name)
    if participants:
        return False
    app_state.active_group_participants.pop(session_id, None)
    app_state.active_group_meetings.pop(session_id, None)
    return True


async def _finalize_abnormal(
    session, recorder, app_state, session_id: str, cause: str, participant_name: str | None = None
) -> None:
    """
    비정상 종료(end 신호 없는 끊김/에러) 공통 처리.
    끊김이 감지되는 경로가 두 갈래(receive의 disconnect 메시지 / send 중 WebSocketDisconnect
    예외)라서, 어느 쪽이든 동일하게 잔여 버퍼 처리 → 회의록 확정 → 재분석 예약이 되게 묶음.
    각자 PC 모드(participant_name 있음)면, 남은 참가자가 있는 동안은 회의를 끝내지 않고
    이 참가자만 조용히 퇴장시킴.
    """
    try:
        # 클라이언트에 보낼 순 없지만, 회의록에는 마지막 발언까지 남긴다
        await session.flush_remaining()
    except Exception:
        logger.exception(f"⚠️ [{session_id}] 종료 시 잔여 버퍼 처리 실패 — 기존 기록까지만 저장됨")

    if participant_name is not None and not _leave_group(app_state, session_id, participant_name):
        logger.info(f"⚪ 참가자 퇴장({cause}): {session_id}/{participant_name} (다른 참가자가 있어 회의 계속)")
        return

    recorder.finalize("disconnected")
    if recorder.has_content:
        asyncio.create_task(refine_meeting(recorder.meeting_id, app_state))
    logger.info(f"⚪ 실시간 STT 세션 종료({cause}): {session_id}")


@router.websocket("/ws/stt/{session_id}")
async def realtime_stt_ws(
    websocket: WebSocket, session_id: str, attendees: str = None, participant_name: str = None
):
    """
    실시간 회의용 STT 엔드포인트.
    - 프론트는 PCM16LE(16kHz, mono) 오디오를 바이너리 프레임으로 스트리밍
    - 서버는 VAD로 발화가 끊길 때마다 partial(잠정)/final(확정) 결과를 push
    - 확정 결과는 서버에도 저장됨 (오디오 원본 + transcript.json → /api/meetings로 조회)
    - 회의를 끝낼 땐 텍스트 프레임 "end"를 보내면, 잔여 버퍼를 마지막 청크로
      처리한 결과와 "session_end" 메시지를 받은 뒤 정상 종료된다

    두 가지 회의 방식을 지원한다 (session_id는 같은 회의면 항상 동일해야 함):

    ① 한 대의 PC(공용 마이크) — participant_name 없이 접속. 화자 프로필 구성은
    두 소스를 병합해 "이번 회의의 전체 참석 인원"을 만든다:
    - 전역 프로필 (attendees 쿼리 파라미터 — "이준오,가동현"처럼 콤마 구분.
      최초 1회 등록해둔 목소리를 매 회의 재등록 없이 재사용)
    - 세션 등록 (/api/enroll — 전역 프로필이 없는 게스트용, 이번 회의 한정)
    둘 다 있으면 합쳐서 닫힌 집합을 구성 (같은 이름 충돌 시 세션 등록이 우선).
    둘 다 없으면 자동감지(열린 집합) 폴백.

    ② 각자 PC — participant_name 쿼리 파라미터로 자기 이름을 넣어 접속.
    같은 session_id로 여러 명이 각자 접속하면 하나의 공유 회의록으로 병합됨.
    이미 본인이 누군지 알고 접속하므로 화자 식별(임베딩 매칭) 자체가 불필요해서
    바로 그 이름으로 라벨링됨. 단, 여러 스트림의 오디오를 하나로 믹싱하는 건
    지원하지 않아 오디오 저장/C-4 정밀 재분석은 생략되고 실시간 전사가 최종본이 됨.
    마지막 참가자가 나갈 때(또는 끊길 때)만 회의 전체가 종료 처리됨.
    """
    await websocket.accept()

    fast_model = websocket.app.state.stt_model_fast
    precise_model = websocket.app.state.stt_model

    if participant_name:
        # ② 각자 PC 모드
        recorder = websocket.app.state.active_group_meetings.get(session_id)
        if recorder is None:
            recorder = MeetingRecord(session_id, "group", mixed_audio=True)
            websocket.app.state.active_group_meetings[session_id] = recorder
        websocket.app.state.active_group_participants.setdefault(session_id, set()).add(participant_name)
        # 이 참가자가 회의 시작 후 몇 초 뒤에 합류했는지 — 세그먼트 시각/오디오 믹싱
        # 위치를 "회의 전체 기준 절대 시각"으로 맞추는 데 필요 (먼저 합류한 사람 기준
        # 0초가 아니라 항상 recorder 생성 시각 기준으로 통일)
        join_offset_sec = time.monotonic() - recorder.start_monotonic
        session = RealtimeSTTSession(
            session_id, fast_model, precise_model,
            fixed_speaker=participant_name, recorder=recorder, base_offset_sec=join_offset_sec,
        )
        mode = f"각자 PC 모드 (참가자: {participant_name}, 합류 시각: +{join_offset_sec:.1f}s)"
    else:
        # ① 한 대의 PC(공용 마이크) 모드
        merged_profiles: dict = {}
        global_count = session_count = 0

        if attendees:
            names = [n.strip() for n in attendees.split(",") if n.strip()]
            global_profiles = websocket.app.state.voice_profiles.load(names)
            missing = set(names) - set(global_profiles.keys())
            if missing:
                logger.warning(f"⚠️ [{session_id}] 전역 프로필 미등록 참석자 무시됨: {', '.join(missing)}")
            merged_profiles.update(global_profiles)
            global_count = len(global_profiles)

        # pop이 아니라 get인 이유: 네트워크 문제로 연결이 끊겨 같은 session_id로
        # 재접속할 때 등록 정보가 사라져 있으면 조용히 자동감지 모드로 떨어져버림.
        # 등록 정보 삭제는 명시적 종료(end) 시점 또는 DELETE /api/enroll에서만 수행.
        session_profiles = websocket.app.state.enrolled_profiles.get(session_id)
        if session_profiles:
            merged_profiles.update(session_profiles)
            session_count = len(session_profiles)

        initial_profiles = merged_profiles or None
        if initial_profiles:
            mode = f"닫힌 집합 {len(initial_profiles)}명 (전역 {global_count} + 세션 {session_count})"
        else:
            mode = "자동감지(열린 집합)"

        speaker_identifier = LiveSpeakerIdentifier(
            websocket.app.state.speaker_embedding_inference,
            initial_profiles=initial_profiles,
        )
        recorder = MeetingRecord(session_id, "enrolled" if initial_profiles else "auto")
        if initial_profiles:
            # 회의 후 정밀 재분석(C-4)이 익명 화자 라벨을 실제 이름으로 매핑할 때 필요
            recorder.save_profiles(initial_profiles)
        session = RealtimeSTTSession(session_id, fast_model, precise_model, speaker_identifier, recorder)

    # rename API가 진행 중인 회의에도 이름 수정을 전파할 수 있게 레지스트리에 등록.
    # 각자 PC 모드는 같은 session_id로 여러 연결이 동시에 있을 수 있어 참가자별로 키를 분리.
    active_key = f"{session_id}:{participant_name}" if participant_name else session_id
    websocket.app.state.active_sessions[active_key] = session

    logger.info(f"🔴 실시간 STT 세션 시작: {session_id} (화자식별 모드: {mode}, 회의ID: {recorder.meeting_id})")

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                await _finalize_abnormal(session, recorder, websocket.app.state, session_id, "연결 끊김", participant_name)
                return

            if message.get("text") is not None:
                if message["text"] == "end":
                    result = await session.flush_remaining()
                    if result:
                        await websocket.send_json(result)

                    is_meeting_over = True
                    if participant_name:
                        is_meeting_over = _leave_group(websocket.app.state, session_id, participant_name)

                    await websocket.send_json({
                        "session_id": session_id,
                        "type": "session_end",
                        "meeting_id": recorder.meeting_id,
                    })

                    if is_meeting_over:
                        recorder.finalize("completed")
                        # 회의가 정상 종료됐으므로 이 세션의 사전 등록 정보도 정리
                        websocket.app.state.enrolled_profiles.pop(session_id, None)
                        # 회의 후 정밀 재분석(C-4) 백그라운드 실행 — 화자 오배정/청크 경계 오류 보정
                        # (각자 PC 모드는 오디오가 없어 refine_meeting이 내부적으로 자동 생략함)
                        if recorder.has_content:
                            asyncio.create_task(refine_meeting(recorder.meeting_id, websocket.app.state))
                        logger.info(f"⚪ 실시간 STT 세션 정상 종료(end): {session_id}")
                    else:
                        logger.info(f"⚪ 참가자 퇴장(정상): {session_id}/{participant_name} (다른 참가자가 있어 회의 계속)")
                    break
                continue  # end 외의 텍스트 프레임은 무시

            data = message.get("bytes")
            if not data:
                continue
            session.push_audio(data)

            # 청크가 끝나기 전에도 1초 주기로 잠정 텍스트를 흘려보냄 (Local Agreement)
            partial = await session.maybe_stream_partial()
            if partial:
                await websocket.send_json(partial)

            if session.should_flush():
                chunk, offset_sec = session.pop_chunk()
                result = await session.process_chunk(chunk, offset_sec)
                await websocket.send_json(result)

    except WebSocketDisconnect:
        # 결과 전송(send) 도중 클라이언트가 끊긴 경우 — receive 경로와 동일하게 처리
        await _finalize_abnormal(session, recorder, websocket.app.state, session_id, "전송 중 끊김", participant_name)
        return
    except Exception:
        logger.exception(f"❌ 실시간 STT 세션 에러 [{session_id}]")
        await _finalize_abnormal(session, recorder, websocket.app.state, session_id, "에러", participant_name)
    finally:
        # 어떤 경로로 끝나든(정상/끊김/에러) 레지스트리에서 제거.
        # 같은 키로 새 연결이 이미 등록됐을 수 있으므로 내 세션일 때만 제거.
        if websocket.app.state.active_sessions.get(active_key) is session:
            websocket.app.state.active_sessions.pop(active_key, None)

    try:
        await websocket.close()
    except Exception:
        pass  # 이미 닫힌 소켓이면 무시
