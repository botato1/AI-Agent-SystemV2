# backend/core/main_loop.py

"""uvicorn 메인 이벤트 루프를 앱 시작 시 저장해두고, 다른 스레드(동기 라우트
핸들러, BackgroundTasks)에서 WebSocket으로 안전하게 push하기 위해 참조한다.

asyncio.run()으로 매번 새 루프를 만들면, WebSocket 연결이 묶여있는 메인 루프와
다른 루프에서 send를 호출하는 상황이 돼서 예외 위험이 있다 (리뷰 반영).
run_coroutine_threadsafe는 실제로 메인 루프 위에서 코루틴을 실행시키므로
이 문제가 없다.
"""

import asyncio
from typing import Optional

_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def get_main_loop() -> asyncio.AbstractEventLoop:
    if _main_loop is None:
        raise RuntimeError(
            "메인 이벤트 루프가 아직 저장되지 않았습니다 - "
            "FastAPI startup 이벤트가 실행되기 전에 호출된 것으로 보입니다."
        )
    return _main_loop
