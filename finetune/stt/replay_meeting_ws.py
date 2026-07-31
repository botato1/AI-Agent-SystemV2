"""
저장된 회의 오디오를 WebSocket으로 흘려보내 **실시간 경로 전체**를 재현한다.

왜 이게 필요한가:
  replay_speaker_split.py는 분할 로직만 따로 호출해봐서, 청크 경계가 실제와 달랐다
  (그 차이 때문에 화자 라벨이 다르게 나와 실제 결함으로 오인한 적이 있다).
  이 스크립트는 서버에 실제로 접속해 오디오를 스트리밍하므로 청크 분할·화자 판정·
  전사·저장·재분석·웹훅까지 **운영과 동일한 코드 경로**를 탄다.

  "코드가 있다"와 "실제로 돈다"는 다르다 — 오늘만 세 번 확인했다
  (프롬프트 유출, 잠정 전사 큐 포화, 화자 전환 임계값). 사람을 다시 모으지 않고도
  실시간 경로를 검증할 수 있는 수단이 필요하다.

기본은 실제 속도로 보낸다. 빨리 보내면 서버가 오디오 유입을 못 따라가 프레임을
버리게 되고(실측된 실패 모드), 그건 실사용과 다른 조건이 된다.

사용법 (GPU 서버, stt venv):
  python replay_meeting_ws.py --meeting test-session-1_20260730-073029 \
      --session-id test-session-1 --attendees 이준오 문지수 가동현 김나연 이승주
"""
import argparse
import asyncio
import json
import os
import sys
import urllib.parse

import numpy as np
import soundfile as sf

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import MEETINGS_DIR, REALTIME_SAMPLE_RATE  # noqa: E402

_FRAME_SEC = 0.1   # 프론트가 보내는 단위와 비슷하게 잘게 나눠 보낸다


def load_pcm16(path: str) -> bytes:
    audio, sample_rate = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sample_rate != REALTIME_SAMPLE_RATE:
        raise SystemExit(f"❌ 샘플레이트 {sample_rate}Hz — {REALTIME_SAMPLE_RATE}Hz 파일이어야 함")
    return (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True, help="재생할 회의 폴더명")
    parser.add_argument("--audio", default="audio.wav")
    parser.add_argument("--server", default="ws://127.0.0.1:8002")
    parser.add_argument("--session-id", default=None, help="미지정 시 회의 폴더명에서 유추")
    parser.add_argument("--attendees", nargs="*", default=None, help="닫힌 집합 참석자 이름")
    parser.add_argument("--participant-name", default=None, help="각자 PC 모드로 접속")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="1.0=실제 속도. 높이면 서버가 못 따라가 프레임을 버릴 수 있음")
    args = parser.parse_args()

    try:
        import websockets
    except ImportError:
        raise SystemExit("❌ websockets 미설치 — pip install websockets")

    path = os.path.join(MEETINGS_DIR, args.meeting, args.audio)
    if not os.path.isfile(path):
        raise SystemExit(f"❌ 오디오 없음: {path}")

    pcm = load_pcm16(path)
    duration = len(pcm) / 2 / REALTIME_SAMPLE_RATE
    session_id = args.session_id or args.meeting.rsplit("_", 1)[0]

    query = {}
    if args.participant_name:
        query["participant_name"] = args.participant_name
    elif args.attendees:
        query["attendees"] = ",".join(args.attendees)
    url = f"{args.server}/api/ws/stt/{urllib.parse.quote(session_id)}"
    if query:
        url += "?" + urllib.parse.urlencode(query, encoding="utf-8")

    print(f"오디오   : {args.meeting}/{args.audio} ({duration:.1f}초)")
    print(f"접속     : {url}")
    print(f"속도     : {args.speed}x\n")

    frame_bytes = int(_FRAME_SEC * REALTIME_SAMPLE_RATE) * 2
    finals: list[dict] = []
    partial_count = 0

    async with websockets.connect(url, max_size=None) as ws:
        async def receive():
            nonlocal partial_count
            try:
                async for raw in ws:
                    if isinstance(raw, bytes):
                        continue          # 통화 중계 오디오 — 여기선 관심 없음
                    msg = json.loads(raw)
                    kind = msg.get("type")
                    if kind == "partial":
                        partial_count += 1
                    elif kind == "final":
                        finals.append(msg)
                        for seg in msg["final"]["segments"]:
                            flag = "" if seg.get("confident", True) else "  [저신뢰]"
                            print(f"  [{seg['start']:6.1f}s] {seg.get('speaker') or '?':10s} "
                                  f"{seg['text']}{flag}")
                    elif kind == "session_end":
                        print(f"\n✅ 종료 — meeting_id={msg.get('meeting_id')}")
                        return
                    elif kind == "voice_ready":
                        print(f"  (통화 슬롯 {msg.get('slot')})")
            except websockets.ConnectionClosed:
                pass

        receiver = asyncio.create_task(receive())

        for offset in range(0, len(pcm), frame_bytes):
            await ws.send(pcm[offset:offset + frame_bytes])
            if args.speed > 0:
                await asyncio.sleep(_FRAME_SEC / args.speed)

        await ws.send("end")
        try:
            await asyncio.wait_for(receiver, timeout=180)
        except asyncio.TimeoutError:
            print("⚠️ session_end를 기다리다 시간 초과")

    speakers = {s.get("speaker") for m in finals for s in m["final"]["segments"]}
    print(f"\n{'=' * 56}")
    print(f"확정 청크 {len(finals)}개 / 잠정 메시지 {partial_count}개")
    print(f"등장 화자: {', '.join(sorted(x for x in speakers if x)) or '없음'}")
    print("\n서버 로그에서 함께 확인할 것:")
    print("  grep -cE '화자 전환 감지|받아적기 감지|큐 포화' /tmp/stt.log")


if __name__ == "__main__":
    asyncio.run(main())
