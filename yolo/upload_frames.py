"""upload_frames.py — 웹캠 프레임을 백엔드 /image 엔드포인트로 초당 1회 업로드.

로봇(ROS2 junction_1.py) 없이 시연자 노트북 웹캠만으로 새 YOLO 자동 파이프라인을
테스트할 때 사용. 실제 로봇의 카메라 프레임을 흉내낸다.

사용:
    # 처음 한 번 — 실제 웹캠 인덱스 확인
    python upload_frames.py --probe

    # 30초 동안 초당 1프레임 업로드 (백엔드가 자동으로 30초 창 판정)
    python upload_frames.py --delivery-id <id> --cam 0

    # 창 없이 콘솔에만 로그
    python upload_frames.py --delivery-id <id> --cam 0 --no-window

    # 무한 루프 (Ctrl+C 로 종료)
    python upload_frames.py --delivery-id <id> --cam 0 --duration 0

정상 사용 흐름:
    1. 백엔드 실행:  uvicorn app.main:app --reload  (backend/ 에서)
    2. 배송 생성 후 ARRIVED 까지 진행 (curl)
    3. 이 스크립트 실행 — 초당 1프레임을 /image 로 업로드
    4. 30초 안에 O/X 카드를 웹캠에 노출
    5. 백엔드가 자동으로 SUCCESS 또는 AWAITING_NURSE 로 전이
"""
import argparse
import sys
import time
from pathlib import Path

import cv2
import requests

CAM_INDEX = 0
FPS = 1.0              # 백엔드 폴링이 초당 1회이므로 맞춤
DURATION_SEC = 30      # 백엔드 창 길이와 동일. 0 이하면 무한 루프.
API_BASE = "http://localhost:8000"


def probe_cameras(max_index=6):
    """어떤 인덱스에 실제 웹캠이 잡히는지 확인해서 probe/ 폴더에 프레임 저장."""
    Path("probe").mkdir(exist_ok=True)
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if not cap.isOpened():
            cap.release()
            continue
        ok, frame = cap.read()
        if ok:
            path = f"probe/probe_{i}.jpg"
            cv2.imwrite(path, frame)
            print(f"[{i}] 프레임 저장 → {path}")
        else:
            print(f"[{i}] isOpened=True 지만 프레임 못 읽음")
        cap.release()
    print("probe/ 폴더의 이미지를 열어 실제 웹캠 화면이 나온 인덱스를 확인하세요.")


def upload_frame(api_base: str, delivery_id: str, jpg_bytes: bytes):
    url = f"{api_base.rstrip('/')}/deliveries/{delivery_id}/image"
    try:
        resp = requests.post(
            url,
            files={"image": ("frame.jpg", jpg_bytes, "image/jpeg")},
            timeout=2.0,
        )
        return resp.status_code
    except requests.RequestException as exc:
        print(f"→ 업로드 실패: {exc}")
        return None


def draw_overlay(frame, elapsed: float, duration: float, sent: int) -> None:
    remaining = "∞" if duration <= 0 else f"{max(0.0, duration - elapsed):.0f}s"
    text = f"{sent} sent · {remaining}"
    cv2.rectangle(frame, (10, 10), (280, 55), (0, 0, 0), -1)
    cv2.putText(frame, text, (20, 42), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (240, 240, 240), 2)


def run(delivery_id, cam_index, api_base, fps, duration, show_window):
    interval = 1.0 / max(fps, 0.001)
    cap = cv2.VideoCapture(cam_index)
    if not cap.isOpened():
        print(f"[에러] 카메라 index={cam_index} 열기 실패 — --probe 로 인덱스 확인")
        sys.exit(1)

    print(f"업로드 시작 → {api_base} / delivery={delivery_id} / cam={cam_index} / fps={fps}")
    print(f"지속 시간: {'무한 루프 (Ctrl+C)' if duration <= 0 else f'{duration:.0f}초'}")

    start = time.monotonic()
    last_send = 0.0
    sent = 0

    try:
        while True:
            elapsed = time.monotonic() - start
            if 0 < duration <= elapsed:
                print(f"[완료] {duration:.0f}초 경과 · 총 {sent}장 전송")
                break

            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue

            now = time.monotonic()
            if now - last_send >= interval:
                _, encoded = cv2.imencode(".jpg", frame)
                status = upload_frame(api_base, delivery_id, encoded.tobytes())
                if status is not None:
                    sent += 1
                    print(f"[{sent}] elapsed={elapsed:.1f}s → HTTP {status}")
                last_send = now

            if show_window:
                draw_overlay(frame, elapsed, duration, sent)
                cv2.imshow("upload_frames — press q to quit", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("[중단] q 키")
                    break
    except KeyboardInterrupt:
        print("[중단] Ctrl+C")
    finally:
        cap.release()
        if show_window:
            cv2.destroyAllWindows()


def parse_args():
    p = argparse.ArgumentParser(description="웹캠 → 백엔드 /image 업로드")
    p.add_argument("--delivery-id", help="POST /deliveries/{id}/image 의 배송 id")
    p.add_argument("--cam", type=int, default=CAM_INDEX,
                   help=f"웹캠 인덱스 (기본 {CAM_INDEX})")
    p.add_argument("--api", default=API_BASE,
                   help=f"백엔드 base URL (기본 {API_BASE})")
    p.add_argument("--fps", type=float, default=FPS,
                   help=f"초당 업로드 프레임 수 (기본 {FPS})")
    p.add_argument("--duration", type=float, default=DURATION_SEC,
                   help=f"실행 시간(초). 0 이하면 무한 루프. 기본 {DURATION_SEC}")
    p.add_argument("--no-window", action="store_true",
                   help="미리보기 창 없이 콘솔 로그만")
    p.add_argument("--probe", action="store_true",
                   help="카메라 인덱스만 확인하고 종료")
    return p.parse_args()


def main():
    args = parse_args()
    if args.probe:
        probe_cameras()
        return
    if not args.delivery_id:
        print("[에러] --delivery-id 가 필요합니다 (또는 --probe)")
        sys.exit(1)
    run(
        args.delivery_id, args.cam, args.api,
        args.fps, args.duration, not args.no_window,
    )


if __name__ == "__main__":
    main()
