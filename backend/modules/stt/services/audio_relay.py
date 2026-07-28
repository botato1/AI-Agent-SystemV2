"""
"각자 PC" 모드 참가자끼리 서로 목소리를 듣게 하는 오디오 릴레이 (통화 기능).

설계 배경:
  WebRTC는 시그널링 서버·STUN/TURN·미디어 협상이 필요해 STT 모듈 범위를 크게 벗어난다.
  그런데 각자 PC 모드에서는 이미 참가자마다 WebSocket으로 PCM16을 서버에 보내고 있으므로,
  "받은 프레임을 나머지 참가자에게 그대로 흘려보내기"만 하면 통화가 성립한다.
  인프라 추가 없이 기존 연결을 재사용하는 대신, TCP(WebSocket) 특성상 패킷 손실 시
  재전송을 기다리며 지연이 튀는 한계는 감수한다(같은 랩/보통 인터넷에선 대화 가능 수준).

STT 경로와의 분리:
  전사용 청킹은 발화가 끊길 때까지 2~28초를 모으기 때문에 통화에는 쓸 수 없다.
  릴레이는 프레임이 도착하는 즉시 팬아웃하는 완전히 별개의 경로다.

프레임 규약 (서버 → 클라이언트):
  텍스트 프레임 = 기존 JSON(partial/final/session_end) — 변경 없음
  바이너리 프레임 = [1바이트 발신자 인덱스][PCM16LE 오디오]
  발신자 인덱스가 필요한 이유: 3명 이상이면 여러 사람의 프레임이 섞여 도착하는데,
  구분 없이 한 버퍼에 이어붙이면 소리가 뭉개진다. 수신 측이 발신자별로 재생
  타임라인을 따로 관리해야 한다.

옵트인:
  기존 클라이언트는 바이너리 수신을 예상하지 않으므로(JSON.parse에서 깨짐),
  통화를 요청한 연결에만 오디오를 보낸다. join(voice=True)로 참여를 표시한다.
"""
import asyncio

from fastapi import WebSocket

from ..core.config import logger, MAX_SPEAKERS

# 한 세션에서 발신자 인덱스로 쓸 수 있는 최대 인원. 1바이트 헤더라 이론상 256명까지
# 가능하지만, 회의 인원 상한(MAX_SPEAKERS)과 맞춰두는 게 의미상 맞다.
_MAX_PARTICIPANTS = MAX_SPEAKERS


class VoiceRoom:
    """
    한 회의(session_id)의 통화 참가자들을 들고 있다가, 들어온 오디오를 나머지에게 전달한다.

    참가자마다 고유한 발신자 인덱스(0~N)를 부여하고, 나갈 때 반납한다.
    인덱스를 재사용하는 이유는 수신 측이 인덱스별로 재생 버퍼를 유지하기 때문에
    번호가 무한정 커지면 버퍼가 계속 쌓이기 때문.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        # 참가자키 → (WebSocket, 발신자 인덱스)
        self._members: dict[str, tuple[WebSocket, int]] = {}
        self._free_slots: list[int] = list(range(_MAX_PARTICIPANTS))

    @property
    def size(self) -> int:
        return len(self._members)

    def join(self, participant_key: str, websocket: WebSocket) -> int | None:
        """통화 참여. 부여된 발신자 인덱스를 반환하고, 자리가 없으면 None."""
        existing = self._members.get(participant_key)
        if existing is not None:
            # 재연결 — 소켓만 갈아끼우고 인덱스는 유지해서 수신 측 버퍼가 리셋되지 않게 함
            _, slot = existing
            self._members[participant_key] = (websocket, slot)
            return slot

        if not self._free_slots:
            logger.warning(f"⚠️ [{self.session_id}] 통화 인원 상한({_MAX_PARTICIPANTS}) 초과 — {participant_key} 음성 미참여")
            return None

        slot = self._free_slots.pop(0)
        self._members[participant_key] = (websocket, slot)
        logger.info(f"🔊 [{self.session_id}] 통화 참여: {participant_key} (슬롯 {slot}, 현재 {self.size}명)")
        return slot

    def leave(self, participant_key: str, websocket: WebSocket) -> None:
        """
        통화 퇴장. 같은 키로 이미 새 연결이 들어와 있으면(재연결) 건드리지 않는다 —
        늦게 도착한 옛 연결의 정리 작업이 새 연결을 끊어버리는 걸 막기 위함.
        """
        entry = self._members.get(participant_key)
        if entry is None or entry[0] is not websocket:
            return
        _, slot = self._members.pop(participant_key)
        self._free_slots.append(slot)
        self._free_slots.sort()
        logger.info(f"🔇 [{self.session_id}] 통화 퇴장: {participant_key} (슬롯 {slot} 반납, 남은 {self.size}명)")

    async def broadcast(self, sender_key: str, pcm: bytes) -> None:
        """
        발신자를 뺀 나머지 참가자에게 오디오를 전달.

        자기 목소리를 되돌려주면 하울링이 생기므로 발신자는 반드시 제외한다.
        전송 실패(이미 끊긴 소켓 등)는 무시한다 — 통화가 안 되는 것보다 전사가
        멈추는 게 더 큰 문제라, 릴레이 실패가 STT 루프를 깨뜨리면 안 된다.
        """
        entry = self._members.get(sender_key)
        if entry is None:
            return
        _, sender_slot = entry

        targets = [(key, ws) for key, (ws, _) in self._members.items() if key != sender_key]
        if not targets:
            return

        payload = bytes([sender_slot]) + pcm
        results = await asyncio.gather(
            *(ws.send_bytes(payload) for _, ws in targets), return_exceptions=True
        )
        for (key, _), result in zip(targets, results):
            if isinstance(result, Exception):
                logger.debug(f"🔇 [{self.session_id}] 음성 전달 실패({key}) — 무시하고 계속: {result!r}")


def get_room(app_state, session_id: str) -> VoiceRoom:
    """세션의 통화방을 가져오고, 없으면 만든다."""
    return app_state.voice_rooms.setdefault(session_id, VoiceRoom(session_id))


def drop_room_if_empty(app_state, session_id: str) -> None:
    """아무도 안 남았으면 통화방을 정리 — 회의가 끝나도 빈 방이 계속 쌓이지 않게."""
    room = app_state.voice_rooms.get(session_id)
    if room is not None and room.size == 0:
        app_state.voice_rooms.pop(session_id, None)
