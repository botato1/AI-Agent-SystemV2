# backend/core/contradiction_events.py

"""모순(contradiction) 생성/갱신 이벤트의 WS 브로드캐스트 채널.

[수정 - 리뷰 반영] graphs/judgment(비즈니스 로직 레이어)가 모순 생성 시 실시간
push를 하려면 원래 backend.routers.contradiction_ws_router를 직접 import했는데,
그러면 core/service 레이어가 routers 레이어를 거슬러 의존하게 된다(레이어 방향
역전). 채널을 여기(core)에 두고, contradiction_ws_router.py(WS 엔드포인트)와
graphs/judgment(이벤트 발행) 양쪽 다 여기서 가져다 쓰도록 해서 routers는
core만 바라보는 한 방향 의존을 유지한다."""

from backend.core.ws_broadcast import WorkspaceBroadcastChannel

contradiction_channel = WorkspaceBroadcastChannel("contradiction")
broadcast_contradiction_event = contradiction_channel.broadcast
broadcast_contradiction_event_sync = contradiction_channel.broadcast_sync
