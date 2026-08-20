"""
"각자 PC" 모드에서 같은 회의에 접속한 참가자들끼리 오디오와 전사 결과를 주고받는 중계.

두 가지를 중계한다:

  1) 확정 전사(final) — 각자 PC 모드면 항상.
     각 참가자는 자기 WebSocket에서 자기 목소리만 전사되므로, 중계가 없으면 화면에
     본인 발언만 보인다(회의록에는 합쳐져 저장되지만 회의 '중'에는 안 보임).
     회의 중에 상대 발언이 보이는 게 이 기능의 핵심 가치라 기본 동작으로 둔다.
     잠정 전사(partial)는 중계하지 않는다 — 1초마다 갱신돼 참가자 수만큼 트래픽이
     곱해지고, 남의 화면에서 내 잠정 텍스트가 계속 바뀌면 오히려 산만하다.

  2) 오디오(통화) — ?voice=1로 요청한 참가자끼리만.
     WebRTC는 시그널링·STUN/TURN이 필요해 STT 모듈 범위를 벗어나는데, 이미 참가자마다
     PCM16을 서버로 보내고 있으므로 받은 프레임을 나머지에게 되돌리면 통화가 성립한다.
     대신 TCP(WebSocket) 특성상 손실 시 재전송을 기다리며 지연이 튀는 한계는 감수한다.
     기존 클라이언트는 바이너리 수신을 예상하지 않아(JSON.parse에서 깨짐) 옵트인이다.

오디오 프레임 규약(서버→클라): [1바이트 발신자 슬롯][PCM16LE]
슬롯이 필요한 이유는 3명 이상일 때 여러 발신자의 프레임이 섞여 도착하는데, 구분 없이
한 버퍼에 이어붙이면 소리가 뭉개지기 때문(수신 측이 발신자별 재생 타임라인을 유지).
"""
import asyncio

from fastapi import WebSocket

from ..core.config import logger, MAX_SPEAKERS

# 오디오 발신자 슬롯 상한. 1바이트 헤더라 이론상 256명까지 가능하지만
# 회의 인원 상한과 맞춰두는 게 의미상 맞다.
_MAX_VOICE_SLOTS = MAX_SPEAKERS


class SessionRoom:
    """
    한 회의(session_id)에 접속 중인 참가자들을 들고 있다가 전사/오디오를 중계한다.

    참가자는 전사 중계에는 항상 참여하고, 오디오 중계는 통화를 요청한 경우에만
    슬롯을 받아 참여한다.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        # 참가자키 → {"ws": WebSocket, "slot": int | None}  (slot이 None이면 통화 미참여)
        self._members: dict[str, dict] = {}
        self._free_slots: list[int] = list(range(_MAX_VOICE_SLOTS))
        # 참가자키 → 진행 중인 오디오 전송 태스크. 실시간 오디오는 밀린 프레임을 쌓아봐야
        # 지연만 누적되므로, 직전 전송이 안 끝났으면 이번 프레임을 버리는 데 쓴다.
        self._inflight_audio: dict[str, asyncio.Task] = {}

    @property
    def size(self) -> int:
        return len(self._members)

    @property
    def voice_size(self) -> int:
        return sum(1 for m in self._members.values() if m["slot"] is not None)

    def join(self, participant_key: str, websocket: WebSocket, voice: bool) -> int | None:
        """참가. 통화를 요청했으면 발신자 슬롯을, 아니면 None을 반환한다."""
        existing = self._members.get(participant_key)
        if existing is not None:
            # 같은 이름으로 이미 들어와 있음(브라우저 탭 두 개 등) — 소켓만 최신 것으로
            # 갈아끼우고 슬롯은 유지한다. 수신 측이 슬롯별로 재생 버퍼를 들고 있어서
            # 번호가 바뀌면 버퍼가 새로 잡히기 때문.
            # (끊김 후 재연결은 이 경로가 아니다 — 연결 종료 시 leave()가 이미 멤버를
            #  지우므로, 재접속은 아래의 새 참가자 경로를 타고 새 슬롯을 받는다)
            existing["ws"] = websocket
            return existing["slot"]

        slot = None
        if voice:
            if self._free_slots:
                slot = self._free_slots.pop(0)
            else:
                logger.warning(
                    f"⚠️ [{self.session_id}] 통화 인원 상한({_MAX_VOICE_SLOTS}) 초과 — "
                    f"{participant_key}는 전사 중계만 참여"
                )

        self._members[participant_key] = {"ws": websocket, "slot": slot}
        logger.info(
            f"🔗 [{self.session_id}] 참가: {participant_key} "
            f"(통화슬롯={slot}, 접속 {self.size}명 / 통화 {self.voice_size}명)"
        )
        return slot

    def leave(self, participant_key: str, websocket: WebSocket) -> None:
        """
        퇴장. 같은 키로 이미 새 연결이 들어와 있으면(탭 중복 등) 건드리지 않는다 —
        늦게 끝난 옛 연결의 정리가 새 연결을 쫓아내는 걸 막기 위함.
        """
        member = self._members.get(participant_key)
        if member is None or member["ws"] is not websocket:
            return
        self._members.pop(participant_key)
        if member["slot"] is not None:
            self._free_slots.append(member["slot"])
            self._free_slots.sort()
        # 아직 안 끝난 전송이 있으면 취소 — 이미 나간 사람에게 매달릴 이유가 없다
        pending = self._inflight_audio.pop(participant_key, None)
        if pending is not None and not pending.done():
            pending.cancel()
        logger.info(f"🔗 [{self.session_id}] 퇴장: {participant_key} (남은 {self.size}명)")

    async def _send_audio(self, key: str, websocket: WebSocket, payload: bytes) -> None:
        """전송 실패(이미 끊긴 소켓 등)는 삼킨다 — 중계 실패가 호출부를 깨뜨리면 안 된다."""
        try:
            await websocket.send_bytes(payload)
        except Exception as exc:
            logger.debug(f"🔇 [{self.session_id}] 음성 전달 실패({key}) — 무시하고 계속: {exc!r}")

    async def _send_json(self, key: str, websocket: WebSocket, payload: dict) -> None:
        try:
            await websocket.send_json(payload)
        except Exception as exc:
            logger.debug(f"📄 [{self.session_id}] 전사 전달 실패({key}) — 무시하고 계속: {exc!r}")

    def broadcast_audio_nowait(self, sender_key: str, pcm: bytes) -> None:
        """
        통화 참여자 중 발신자를 뺀 나머지에게 오디오를 전달. **기다리지 않는다.**

        await로 전송을 기다리면 수신자 한 명이 느릴 때(소켓 버퍼가 참) 그 사람이
        드레인될 때까지 발신자의 수신 루프까지 멈춘다 — 느린 참가자 하나가 방 전체를
        막는 구조가 된다. 실시간 오디오는 밀린 프레임을 쌓아봐야 지연만 누적되므로,
        직전 전송이 아직 안 끝난 상대에게는 이번 프레임을 그냥 버린다(큐잉 대신 드롭).

        자기 목소리를 되돌려주면 하울링이 생기므로 발신자는 반드시 제외한다.
        """
        sender = self._members.get(sender_key)
        if sender is None or sender["slot"] is None:
            return

        payload = bytes([sender["slot"]]) + pcm
        for key, member in self._members.items():
            if key == sender_key or member["slot"] is None:
                continue  # 자기 자신, 그리고 통화 미참여자는 제외
            prev = self._inflight_audio.get(key)
            if prev is not None and not prev.done():
                continue  # 아직 밀려 있음 — 이 프레임은 버린다
            self._inflight_audio[key] = asyncio.create_task(
                self._send_audio(key, member["ws"], payload)
            )

    def broadcast_json_nowait(self, sender_key: str, payload: dict) -> None:
        """
        확정 전사를 발신자를 뺀 나머지 참가자에게 전달. 기다리지 않는다.

        오디오와 달리 드롭하지 않는다 — 확정 전사는 유실되면 상대 화면에서 그 발언이
        영영 사라진다. 대신 final은 몇 초에 한 번 수준이라 쌓여도 부담이 적다.
        """
        for key, member in self._members.items():
            if key == sender_key:
                continue
            asyncio.create_task(self._send_json(key, member["ws"], payload))


def get_room(app_state, session_id: str) -> SessionRoom:
    """세션의 중계방을 가져오고, 없으면 만든다."""
    return app_state.session_rooms.setdefault(session_id, SessionRoom(session_id))


def drop_room_if_empty(app_state, session_id: str) -> None:
    """아무도 안 남았으면 정리 — 회의가 끝나도 빈 방이 계속 쌓이지 않게."""
    room = app_state.session_rooms.get(session_id)
    if room is not None and room.size == 0:
        app_state.session_rooms.pop(session_id, None)
