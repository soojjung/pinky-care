"""PinkyCare 미션 디스패처 — 백엔드의 새 배송을 감지해 로봇 주행을 자동 실행.

프론트에서 배송이 생성되면 백엔드 전역 SSE 스트림(`GET /deliveries/events`)으로
스냅샷이 흘러온다. 이 스크립트는 그걸 구독하다가 배송이 들어오면
``junction_1.py --room-number <room> --delivery-id <id>`` 를 실행한다.

로봇(라즈베리파이)에서 상시 실행해 두는 진입점:

    BACKEND_URL=http://192.168.4.19:8000 python3 mission_dispatcher.py

- BACKEND_URL 기본값은 시연자 노트북 IP. 매번 바뀌면 환경변수로 넘긴다.
- 한 번에 하나의 배송만 처리한다(주행 중이면 끝날 때까지 대기 후 다음 처리).
- SSE 연결이 끊기면 자동 재접속한다.
- 이미 처리한 delivery id 는 재실행하지 않는다(중복 방지).

의존성: requests (junction_1.py 와 동일). 별도 SSE 라이브러리 없이 직접 파싱.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time

import requests

BACKEND_URL = os.environ.get("BACKEND_URL", "http://192.168.4.19:8000")

# junction_1.py 는 기본적으로 이 파일과 같은 디렉터리에 있다.
# (테스트나 특수 배포 시 JUNCTION_SCRIPT 환경변수로 경로를 바꿀 수 있다.)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JUNCTION_SCRIPT = os.environ.get(
    "JUNCTION_SCRIPT", os.path.join(_SCRIPT_DIR, "junction_1.py")
)

# 처리 가능한 방 번호 (junction_1.py --room-number choices 와 일치)
VALID_ROOMS = {102, 103, 104}

RECONNECT_DELAY_SEC = 3.0  # SSE 끊길 때 재접속 간격


def _stream_new_deliveries(out_queue: "queue.Queue[dict]") -> None:
    """전역 SSE 스트림을 계속 읽어 새 배송 dict 를 큐에 넣는다 (백그라운드 스레드).

    SSE 포맷은 `event: delivery` + `data: {json}` 블록의 연속이다.
    라이브러리 없이 라인 단위로 파싱한다. 끊기면 재접속.
    """
    url = f"{BACKEND_URL}/deliveries/events"
    while True:
        try:
            print(f"[dispatcher] 스트림 접속: {url}", flush=True)
            with requests.get(url, stream=True, timeout=(5, None)) as resp:
                resp.raise_for_status()
                print("[dispatcher] 스트림 연결됨. 새 배송 대기 중...", flush=True)
                data_buf = []
                for raw in resp.iter_lines(decode_unicode=True):
                    # 빈 줄 = 이벤트 블록 종료 → 지금까지 모은 data 처리
                    if raw == "" or raw is None:
                        if data_buf:
                            _emit(out_queue, "\n".join(data_buf))
                            data_buf = []
                        continue
                    if raw.startswith(":"):
                        continue  # ping/comment
                    if raw.startswith("data:"):
                        data_buf.append(raw[len("data:"):].lstrip())
                    # event: 라인은 종류가 하나뿐이라 무시
        except requests.RequestException as e:
            print(f"[dispatcher] 스트림 끊김: {e} — {RECONNECT_DELAY_SEC}s 후 재접속", flush=True)
            time.sleep(RECONNECT_DELAY_SEC)


def _emit(out_queue: "queue.Queue[dict]", data_str: str) -> None:
    """data 문자열을 파싱해 유효하면 큐에 넣는다."""
    try:
        payload = json.loads(data_str)
    except json.JSONDecodeError:
        print(f"[dispatcher] JSON 파싱 실패, 무시: {data_str!r}", flush=True)
        return
    if isinstance(payload, dict) and payload.get("id"):
        out_queue.put(payload)


def _run_mission(delivery: dict) -> None:
    """junction_1.py 를 배송의 room·id 로 실행하고 끝날 때까지 대기(blocking)."""
    delivery_id = delivery["id"]
    room_raw = delivery.get("room")
    try:
        room = int(room_raw)
    except (TypeError, ValueError):
        print(f"[dispatcher] room 값 이상({room_raw!r}) — 스킵 (id={delivery_id})", flush=True)
        return
    if room not in VALID_ROOMS:
        print(f"[dispatcher] 미지원 방 {room} — 스킵 (id={delivery_id})", flush=True)
        return

    cmd = [
        sys.executable,
        JUNCTION_SCRIPT,
        "--room-number", str(room),
        "--delivery-id", delivery_id,
    ]
    print(f"[dispatcher] ▶ 미션 시작: {room}호 (id={delivery_id})", flush=True)
    print(f"[dispatcher]   $ {' '.join(cmd)}", flush=True)
    try:
        # BACKEND_URL 을 자식(junction_1.py)에도 그대로 물려준다.
        subprocess.run(cmd, env={**os.environ, "BACKEND_URL": BACKEND_URL}, check=False)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"[dispatcher] 미션 실행 오류(id={delivery_id}): {e}", flush=True)
    finally:
        print(f"[dispatcher] ■ 미션 종료: {room}호 (id={delivery_id})", flush=True)


def main() -> None:
    print(f"[dispatcher] BACKEND_URL = {BACKEND_URL}", flush=True)
    print(f"[dispatcher] junction 스크립트 = {JUNCTION_SCRIPT}", flush=True)
    if not os.path.exists(JUNCTION_SCRIPT):
        print(f"[dispatcher] 경고: junction_1.py 를 못 찾음 → {JUNCTION_SCRIPT}", flush=True)

    work_queue: "queue.Queue[dict]" = queue.Queue()
    reader = threading.Thread(
        target=_stream_new_deliveries, args=(work_queue,), daemon=True
    )
    reader.start()

    seen: set[str] = set()
    # 메인 스레드는 큐에서 하나씩 꺼내 순차 실행 → 한 번에 한 미션만 수행
    while True:
        delivery = work_queue.get()
        did = delivery.get("id")
        if did in seen:
            continue  # 재연결 스냅샷 등으로 중복 수신 시 무시
        seen.add(did)
        _run_mission(delivery)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[dispatcher] 종료.", flush=True)
