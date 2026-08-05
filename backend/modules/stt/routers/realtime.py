import asyncio
import contextlib
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.config import logger, build_context_hint
from ..services.realtime_service import RealtimeSTTSession
from ..services.speaker_id_service import LiveSpeakerIdentifier
from ..services.meeting_store import MeetingRecord
from ..services.refine_service import refine_meeting
from ..services import session_relay

router = APIRouter()

# 연결이 끊겨도 곧바로 회의를 끝내지 않고, 이 시간 안에 같은 session_id(+참가자면
# participant_name도 동일)로 재접속하면 기존 recorder를 그대로 이어감.
# 짧은 네트워크 끊김(터널 불안정, 와이파이 순단 등)에도 회의가 끊기지 않게 하기 위함 —
# 팀원(지수)이 실제 통합 테스트 중 지적한 리스크.
RECONNECT_GRACE_SEC = 20

# 한 대의 PC(공용 마이크) 모드는 참가자 개념이 없지만, "각자 PC" 모드의 참조 카운트
# 로직을 그대로 재사용하기 위해 참가자가 1명뿐인 그룹처럼 취급 — 그 1명의 고정 키.
_SOLO_KEY = "__solo__"


def _leave(app_state, session_id: str, participant_key: str) -> bool:
    """
    참가자 한 명을 정상적으로(즉시) 퇴장시킴. 반환값 True면 이 참가자가 마지막이었다는
    뜻 — 공유 recorder를 확정(finalize)해야 함. (한 대의 PC 모드에서도 동일하게 동작:
    참가자가 1명뿐이라 항상 True가 됨)
    """
    participants = app_state.active_participants.get(session_id)
    if participants is None:
        return True  # 이미 정리된 상태 — 방어적으로 종료 처리
    participants.pop(participant_key, None)
    if participants:
        return False
    app_state.active_participants.pop(session_id, None)
    return True


def _finalize_recorder(app_state, session_id: str, recorder, status: str) -> None:
    """recorder를 확정하고 필요하면 정밀 재분석을 예약. 레지스트리 정리까지 함께 처리."""
    current = app_state.active_recorders.get(session_id)
    if current is recorder:
        app_state.active_recorders.pop(session_id, None)
    recorder.finalize(status)
    if recorder.has_content:
        asyncio.create_task(refine_meeting(recorder.meeting_id, app_state))


async def _finalize_abnormal(
    session, recorder, app_state, session_id: str, cause: str, participant_key: str,
) -> None:
    """
    비정상 종료(end 신호 없는 끊김/에러) 공통 처리.
    끊김이 감지되는 경로가 두 갈래(receive의 disconnect 메시지 / send 중 WebSocketDisconnect
    예외)라서, 어느 쪽이든 동일하게 잔여 버퍼 처리 → 재연결 유예 등록까지 되게 묶음.

    바로 회의를 끝내지 않고 RECONNECT_GRACE_SEC 동안 재연결을 기다린다 — 그 안에
    같은 키로 재접속하면(realtime_stt_ws 시작부에서 active_recorders/active_participants
    확인) 이 recorder를 그대로 이어받아 회의가 끊기지 않은 것처럼 계속됨.
    "끊김 감지 자체가 GPU 작업 때문에 지연될 수 있어, 재접속이 끊김 감지보다 먼저
    일어날 수도 있음" — 이 경우도 recorder가 아직 active_recorders에 살아있는 것으로
    자연스럽게 처리되므로 별도 방어 로직 불필요.
    """
    try:
        # 클라이언트에 보낼 순 없지만, 회의록에는 마지막 발언까지 남긴다
        await session.flush_remaining()
    except Exception:
        logger.exception(f"⚠️ [{session_id}] 종료 시 잔여 버퍼 처리 실패 — 기존 기록까지만 저장됨")

    async def _delayed_finalize():
        await asyncio.sleep(RECONNECT_GRACE_SEC)
        participants = app_state.active_participants.get(session_id)
        # 이 태스크가 여전히 "현재 등록된" 것일 때만 진행 — 그 사이 재연결로 취소됐거나
        # 다른 태스크로 교체됐으면(참가자가 다시 끊겼다 등) 건너뜀
        if participants is None or participants.get(participant_key) is not asyncio.current_task():
            return
        participants.pop(participant_key, None)
        if participants:
            logger.info(f"⚪ 참가자 퇴장(재연결 유예 시간 초과): {session_id}/{participant_key} (다른 참가자가 있어 회의 계속)")
            return
        app_state.active_participants.pop(session_id, None)
        _finalize_recorder(app_state, session_id, recorder, "disconnected")
        logger.info(f"⚪ 실시간 STT 세션 종료(재연결 없음, {cause}): {session_id}")

    task = asyncio.create_task(_delayed_finalize())
    app_state.active_participants.setdefault(session_id, {})[participant_key] = task
    logger.info(f"⏸️ 연결 끊김({cause}): {session_id}/{participant_key} — {RECONNECT_GRACE_SEC}초 안에 재접속하면 회의가 이어짐")


# 수신 루프와 전사를 잇는 큐의 상한(프레임 수). 브라우저가 약 85ms 단위로 보내므로
# 512면 약 43초치 — 전사가 일시적으로 밀려도 흡수되고, 그 이상 밀리면 오래된 오디오를
# 붙잡고 있어봐야 회의 진행을 못 따라가므로 버린다.
_AUDIO_QUEUE_MAX = 512


async def _stt_worker(
    websocket: WebSocket, session, audio_q: asyncio.Queue,
    room=None, participant_key: str | None = None,
) -> None:
    """
    전사 전담 태스크 — 수신 루프에서 분리한 이유가 핵심이다.

    전사를 수신 루프 안에서 await하면, 청크 확정(process_chunk, 약 1.7초) 동안
    websocket.receive()를 못 불러서 그 참가자의 오디오를 읽지도 남에게 릴레이하지도
    못한다. 통화에서는 청크마다 목소리가 1.7초씩 통째로 끊기는 현상으로 나타난다.
    큐로 분리하면 전사가 아무리 오래 걸려도 수신·릴레이는 계속 돈다.

    None을 받으면 잔여 버퍼를 마지막 청크로 처리하고 종료한다(회의 종료 신호).
    이 태스크만 partial/final을 전송하므로, 한 소켓에 두 코루틴이 동시에 쓰는 상황은
    생기지 않는다(session_end는 이 태스크가 끝난 뒤 수신 루프가 보냄).

    room이 있으면(각자 PC 모드) 확정 전사를 같은 회의의 다른 참가자에게도 보낸다 —
    각 참가자는 자기 소켓에서 자기 목소리만 전사되므로, 이게 없으면 회의 중에 본인
    발언만 보인다. 잠정 전사는 공유하지 않는다(1초마다 갱신돼 트래픽이 인원수만큼
    곱해지고, 남의 화면에서 내 잠정 텍스트가 계속 바뀌면 산만함).
    """
    def share_final(result: dict) -> None:
        if room is None or participant_key is None:
            return
        # 받는 쪽이 "남의 발언"임을 구분할 수 있게 표시해서 보낸다
        room.broadcast_json_nowait(participant_key, {**result, "remote": True})

    while True:
        item = await audio_q.get()
        if item is None:
            result = await session.flush_remaining()
            if result:
                await websocket.send_json(result)
                share_final(result)
            return

        session.push_audio(item)

        # 청크가 끝나기 전에도 1초 주기로 잠정 텍스트를 흘려보냄 (Local Agreement)
        partial = await session.maybe_stream_partial()
        if partial:
            await websocket.send_json(partial)

        if session.should_flush():
            chunk, offset_sec = session.pop_chunk()
            result = await session.process_chunk(chunk, offset_sec)
            await websocket.send_json(result)
            share_final(result)

            # 오디오가 인식이 무너질 상태면 알린다. **회의 중에** 알려야 마이크를
            # 옮기거나 소음원을 줄일 수 있다 — 끝난 뒤 알려주면 녹음을 다시 해야 한다.
            # (중계하지 않는다. 각자 자기 마이크 상태만 알면 되고, 남의 경고까지
            #  뜨면 누구 문제인지 헷갈린다.)
            warning = session.pop_audio_quality_warning()
            if warning:
                await websocket.send_json(warning)


async def _run_session(
    websocket: WebSocket, session, recorder, session_id: str,
    participant_key: str, active_key: str, mode: str,
    group: bool = False, voice: bool = False,
) -> None:
    """
    연결 하나의 수신 루프 본체 — 새로 만든 세션이든, 재연결로 이어받은 세션이든
    동일하게 처리 (재연결 시에는 recorder를 새로 안 만들고 그대로 넘겨받되, session은
    매번 새로 만듦 — 이전 연결의 세션 객체를 여러 코루틴이 동시에 건드리는 걸 피하기 위함.
    타임스탬프 연속성은 base_offset_sec으로 보정됨).
    """
    # rename API가 진행 중인 회의에도 이름 수정을 전파할 수 있게 레지스트리에 등록.
    websocket.app.state.active_sessions[active_key] = session

    # 각자 PC 모드면 중계방에 참여한다 — 통화를 안 켜도 확정 전사는 서로 공유해야 하므로
    # (각 참가자는 자기 소켓에서 자기 목소리만 전사되어, 중계가 없으면 회의 중에 본인
    #  발언만 보인다). 통화(오디오)는 voice=1일 때만 슬롯을 받아 추가로 참여.
    room = session_relay.get_room(websocket.app.state, session_id) if group else None
    voice_slot = room.join(participant_key, websocket, voice) if room is not None else None

    # 수신 루프는 "읽기 → 중계 → 큐 적재"만 하고, 전사는 워커가 큐를 소비하며 담당한다
    # (전사를 수신 루프에서 await하면 그동안 통화 오디오가 끊긴다 — _stt_worker 참고)
    audio_q: asyncio.Queue = asyncio.Queue(maxsize=_AUDIO_QUEUE_MAX)
    worker = asyncio.create_task(_stt_worker(websocket, session, audio_q, room, participant_key))

    logger.info(f"🔴 실시간 STT 세션 시작: {session_id} (화자식별 모드: {mode}, 회의ID: {recorder.meeting_id})")

    try:
        if voice_slot is not None:
            await websocket.send_json({
                "session_id": session_id,
                "type": "voice_ready",
                "slot": voice_slot,
                "participants": room.voice_size,
            })

        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                await _finalize_abnormal(session, recorder, websocket.app.state, session_id, "연결 끊김", participant_key)
                return

            if message.get("text") is not None:
                if message["text"] == "end":
                    # 워커에게 종료를 알리고 잔여 버퍼 처리가 끝날 때까지 기다린다.
                    # 여기서 기다려야 아래 session_end가 마지막 final보다 먼저 나가지 않는다.
                    await audio_q.put(None)
                    await worker

                    is_meeting_over = _leave(websocket.app.state, session_id, participant_key)

                    await websocket.send_json({
                        "session_id": session_id,
                        "type": "session_end",
                        "meeting_id": recorder.meeting_id,
                    })

                    if is_meeting_over:
                        _finalize_recorder(websocket.app.state, session_id, recorder, "completed")
                        # 회의가 정상 종료됐으므로 이 세션의 사전 등록 정보도 정리
                        websocket.app.state.enrolled_profiles.pop(session_id, None)
                        logger.info(f"⚪ 실시간 STT 세션 정상 종료(end): {session_id}")
                    else:
                        logger.info(f"⚪ 참가자 퇴장(정상): {session_id}/{participant_key} (다른 참가자가 있어 회의 계속)")
                    break
                continue  # end 외의 텍스트 프레임은 무시

            data = message.get("bytes")
            if not data:
                continue

            # 통화 중계는 전사보다 먼저, 도착 즉시. 기다리지 않으므로(nowait)
            # 느린 수신자가 있어도 이 루프는 안 멈춘다.
            if voice_slot is not None:
                room.broadcast_audio_nowait(participant_key, data)

            try:
                audio_q.put_nowait(data)
            except asyncio.QueueFull:
                # 전사가 크게 밀린 상황. 오래된 오디오를 붙잡고 있어봐야 회의를 못 따라가므로
                # 버린다 — 통화(릴레이)는 위에서 이미 처리됐으니 대화 자체는 계속된다.
                logger.warning(f"⚠️ [{session_id}/{participant_key}] 전사 큐 포화 — 오디오 프레임 버림")

    except WebSocketDisconnect:
        # 결과 전송(send) 도중 클라이언트가 끊긴 경우 — receive 경로와 동일하게 처리
        await _finalize_abnormal(session, recorder, websocket.app.state, session_id, "전송 중 끊김", participant_key)
        return
    except Exception:
        logger.exception(f"❌ 실시간 STT 세션 에러 [{session_id}]")
        await _finalize_abnormal(session, recorder, websocket.app.state, session_id, "에러", participant_key)
    finally:
        # 정상 종료(end)면 이미 끝나 있고, 끊김/에러면 여기서 정리해야 태스크가 안 남는다.
        if not worker.done():
            worker.cancel()
        # 워커 안에서 난 예외가 조용히 묻히지 않게 회수 (취소는 정상 경로라 무시)
        with contextlib.suppress(asyncio.CancelledError):
            try:
                await worker
            except Exception:
                logger.exception(f"❌ 전사 워커 비정상 종료 [{session_id}/{participant_key}]")

        # 어떤 경로로 끝나든(정상/끊김/에러) 레지스트리에서 제거.
        # 같은 키로 새 연결이 이미 등록됐을 수 있으므로 내 세션일 때만 제거.
        if websocket.app.state.active_sessions.get(active_key) is session:
            websocket.app.state.active_sessions.pop(active_key, None)
        if room is not None:
            # leave()는 같은 키로 새 연결이 들어와 있으면 알아서 건너뛴다
            # (늦게 끝난 옛 연결이 새 연결을 중계방에서 쫓아내지 않도록)
            room.leave(participant_key, websocket)
            session_relay.drop_room_if_empty(websocket.app.state, session_id)

    try:
        await websocket.close()
    except Exception:
        pass  # 이미 닫힌 소켓이면 무시


@router.websocket("/ws/stt/{session_id}")
async def realtime_stt_ws(
    websocket: WebSocket, session_id: str, attendees: str = None,
    participant_name: str = None, voice: int = 0,
):
    """
    실시간 회의용 STT 엔드포인트.
    - 프론트는 PCM16LE(16kHz, mono) 오디오를 바이너리 프레임으로 스트리밍
    - 서버는 VAD로 발화가 끊길 때마다 partial(잠정)/final(확정) 결과를 push
    - 확정 결과는 서버에도 저장됨 (오디오 원본 + transcript.json → /api/meetings로 조회)
    - 회의를 끝낼 땐 텍스트 프레임 "end"를 보내면, 잔여 버퍼를 마지막 청크로
      처리한 결과와 "session_end" 메시지를 받은 뒤 정상 종료된다
    - 연결이 예기치 않게 끊겨도 RECONNECT_GRACE_SEC(20초) 안에 같은 session_id
      (+participant_name)로 재접속하면 회의가 끊기지 않고 그대로 이어짐

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
    바로 그 이름으로 라벨링됨. 여러 스트림의 오디오는 회의 시작 기준 절대 시각으로
    믹싱되어 하나의 오디오 파일로 저장되지만(겹치는 구간은 파형을 합산), 이미 화자가
    확정돼 있어 C-4 정밀 재분석(익명 라벨 매핑)은 의미가 없으므로 생략됨.
    마지막 참가자가 나갈 때(또는 끊길 때)만 회의 전체가 종료 처리됨.

    ⚠️ 두 모드는 같은 회의 안에서 섞어 쓸 수 없음 — 회의 하나는 처음부터 끝까지
    하나의 모드로 통일해야 함 (참가자마다 다르게 접속하면 서로 다른 회의록이 생김).

    voice=1 (각자 PC 모드 전용): 참가자끼리 서로 목소리를 듣는 통화 기능을 켠다.
    서버가 받은 오디오 프레임을 나머지 참가자에게 즉시 되돌려보내며, 이때부터
    이 연결은 바이너리 프레임(= [1바이트 발신자 슬롯][PCM16LE])도 받게 된다.
    기존 클라이언트가 예상 못 한 바이너리를 받고 깨지지 않도록 옵트인으로 두었다.
    공용 마이크 모드는 한 공간에 모여 있어 통화가 무의미하므로 무시된다.
    """
    await websocket.accept()

    active_key = f"{session_id}:{participant_name}" if participant_name else session_id
    participant_key = participant_name or _SOLO_KEY

    # 재연결 확인 — 참가자를 "연결됨" 상태로 표시. 직전에 끊겨서 유예 대기 중이던
    # 태스크가 있으면 취소(재연결 성공). recorder가 아직 살아있으면(끊김이 늦게
    # 감지됐어도, active_recorders에서 안 지워졌으면) 그걸 그대로 이어받음 —
    # "끊김 감지 시점"이 아니라 "recorder 생존 여부"로 판단하므로, 서버가 GPU 작업으로
    # 바빠서 끊김 감지가 늦어져도 재연결이 먼저 도착하는 레이스에도 안전함.
    participants = websocket.app.state.active_participants.setdefault(session_id, {})
    pending_task = participants.get(participant_key)
    if pending_task is not None:
        pending_task.cancel()
    participants[participant_key] = None

    recorder = websocket.app.state.active_recorders.get(session_id)
    is_reconnect = recorder is not None and not recorder.finalized

    fast_model = websocket.app.state.stt_model_fast
    precise_model = websocket.app.state.stt_model

    if participant_name:
        # ② 각자 PC 모드
        if not is_reconnect:
            recorder = MeetingRecord(session_id, "group", mixed_audio=True)
            websocket.app.state.active_recorders[session_id] = recorder
        # 믹싱 모드는 여러 스트림을 실제 시각 기준으로 합산하므로 벽시계 경과 시간 사용
        join_offset_sec = time.monotonic() - recorder.start_monotonic
        session = RealtimeSTTSession(
            session_id, fast_model, precise_model,
            fixed_speaker=participant_name, recorder=recorder, base_offset_sec=join_offset_sec,
            # 각자 PC 모드는 이 연결로 들어오는 목소리가 본인 하나뿐이므로 본인 이름만 힌트로
            # session_id를 함께 넘겨 같은 회의 시리즈의 지난 회의록에서 용어를 보탠다
            initial_prompt=build_context_hint([participant_name], session_id=session_id),
        )
        prefix = "재연결 — " if is_reconnect else ""
        mode = f"{prefix}각자 PC 모드 (참가자: {participant_name}, +{join_offset_sec:.1f}s)"
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

        if not is_reconnect:
            recorder = MeetingRecord(session_id, "enrolled" if initial_profiles else "auto")
            websocket.app.state.active_recorders[session_id] = recorder
            if initial_profiles:
                # 회의 후 정밀 재분석(C-4)이 익명 화자 라벨을 실제 이름으로 매핑할 때 필요
                recorder.save_profiles(initial_profiles)

        speaker_identifier = LiveSpeakerIdentifier(
            websocket.app.state.speaker_embedding_inference,
            initial_profiles=initial_profiles,
        )
        # 스트리밍(비믹싱) 모드는 끊긴 동안의 공백이 오디오 자체엔 없으므로, 벽시계
        # 시간이 아니라 "지금까지 실제로 기록된 오디오 길이"를 기준으로 이어붙임
        base_offset_sec = recorder.written_audio_sec
        session = RealtimeSTTSession(
            session_id, fast_model, precise_model, speaker_identifier, recorder,
            base_offset_sec=base_offset_sec,
            # 등록된 참석자 이름을 힌트로 (자동감지 모드면 이름이 없어 용어만 들어감)
            initial_prompt=build_context_hint(list(merged_profiles.keys()), session_id=session_id),
        )
        mode_desc = (
            f"닫힌 집합 {len(initial_profiles)}명 (전역 {global_count} + 세션 {session_count})"
            if initial_profiles else "자동감지(열린 집합)"
        )
        mode = ("재연결 — " if is_reconnect else "") + mode_desc

    # 중계(전사 공유·통화)는 각자 PC 모드에서만 의미가 있다 — 공용 마이크 모드는 한
    # 소켓이 회의 전체를 담당하므로 공유할 상대가 없고, 통화는 같은 공간이라 하울링만 생긴다.
    await _run_session(
        websocket, session, recorder, session_id, participant_key, active_key, mode,
        group=bool(participant_name), voice=bool(voice),
    )
