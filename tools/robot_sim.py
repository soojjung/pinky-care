"""로봇 시뮬레이터 — 실물 로봇 없이 프론트/백엔드 흐름을 테스트하는 mock.

실제 로봇(mission_dispatcher.py + junction_1.py)이 하는 HTTP 호출을 그대로 흉내 낸다.
백엔드 전역 스트림(GET /deliveries/events)을 구독하다가 배송이 생기면:

    REQUESTED → (PATCH MOVING) → 잠깐 → (PATCH ARRIVED) → 결과 확정

노트북에서 실행 (ROS2 불필요):

    python3 tools/robot_sim.py                 # 기본: SUCCESS 로 완료
    python3 tools/robot_sim.py --result awaiting  # 30초 무응답 → AWAITING_NURSE (간호사 모달 테스트)
    python3 tools/robot_sim.py --result fail       # FAILED 로 완료
    BACKEND_URL=http://localhost:8000 python3 tools/robot_sim.py

주의: 이 시뮬레이터와 실물 로봇 디스패처를 동시에 켜지 말 것 (둘 다 같은 배송을 몰게 됨).
"""
import argparse
import json
import os
import sys
import time

import requests

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
MOVE_SECONDS = 2.0  # MOVING 상태를 얼마나 보여줄지 (UI 확인용)


def _patch_status(delivery_id: str, status: str) -> None:
    url = f"{BACKEND_URL}/deliveries/{delivery_id}/robot-status"
    resp = requests.patch(url, json={"status": status}, timeout=5)
    print(f"[sim]   PATCH robot-status {status} → {resp.status_code}", flush=True)
    resp.raise_for_status()


def _force_result(delivery_id: str, result: str, reason: str | None) -> None:
    """레거시 /verification 오버라이드로 결과를 즉시 확정 (30초 대기 없이)."""
    url = f"{BACKEND_URL}/deliveries/{delivery_id}/verification"
    body: dict = {"result": result}
    if reason:
        body["reason"] = reason
    resp = requests.patch(url, json=body, timeout=5)
    print(f"[sim]   PATCH verification {result} → {resp.status_code}", flush=True)
    resp.raise_for_status()


def _run_one(delivery: dict, result_mode: str) -> None:
    did = delivery["id"]
    room = delivery.get("room")
    print(f"[sim] ▶ 배송 감지: {room}호 (id={did}) — mode={result_mode}", flush=True)

    _patch_status(did, "MOVING")
    time.sleep(MOVE_SECONDS)
    _patch_status(did, "ARRIVED")  # ARRIVED 순간 백엔드가 30초 YOLO 창 시작

    if result_mode == "success":
        _force_result(did, "SUCCESS", None)
    elif result_mode == "fail":
        _force_result(did, "FAILED", "시뮬레이터 강제 실패")
    elif result_mode == "awaiting":
        # 아무 프레임도 안 올리면 30초 뒤 YOLO 가 TIMEOUT_NO_CARD → AWAITING_NURSE
        print("[sim]   프레임 업로드 없이 대기 → 30초 후 AWAITING_NURSE 예상", flush=True)
    print(f"[sim] ■ 처리 완료: {room}호 (id={did})", flush=True)


def _stream(result_mode: str) -> None:
    url = f"{BACKEND_URL}/deliveries/events"
    seen: set[str] = set()
    while True:
        try:
            print(f"[sim] 스트림 접속: {url}", flush=True)
            with requests.get(url, stream=True, timeout=(5, None)) as resp:
                resp.raise_for_status()
                print("[sim] 연결됨. 새 배송 대기 중... (Ctrl+C 종료)", flush=True)
                buf = []
                for raw in resp.iter_lines(decode_unicode=True):
                    if not raw:
                        if buf:
                            _handle(" ".join(buf), seen, result_mode)
                            buf = []
                        continue
                    if raw.startswith("data:"):
                        buf.append(raw[len("data:"):].lstrip())
        except requests.RequestException as e:
            print(f"[sim] 스트림 끊김: {e} — 3초 후 재접속", flush=True)
            time.sleep(3)


def _handle(data_str: str, seen: set, result_mode: str) -> None:
    try:
        delivery = json.loads(data_str)
    except json.JSONDecodeError:
        return
    did = delivery.get("id")
    if not did or did in seen:
        return
    seen.add(did)
    try:
        _run_one(delivery, result_mode)
    except requests.RequestException as e:
        print(f"[sim] 처리 중 오류(id={did}): {e}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="PinkyCare 로봇 시뮬레이터")
    parser.add_argument(
        "--result",
        choices=["success", "fail", "awaiting"],
        default="success",
        help="배송 결과 (기본 success)",
    )
    args = parser.parse_args(sys.argv[1:])
    print(f"[sim] BACKEND_URL = {BACKEND_URL}  ·  result-mode = {args.result}", flush=True)
    _stream(args.result)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[sim] 종료.", flush=True)
