"""
detect_ox.py — 학습된 YOLO로 웹캠 실시간 O/X 판별

`backend/models/pinky_yolo_v1.pt`(성공/실패 O·X 카드 학습 가중치)를 로드해
웹캠 프레임마다 추론하고, 화면에 박스와 함께 O/X 판정을 크게 표시한다.

클래스 매핑 (data.yaml 기준, 절대 뒤집지 말 것):
    0: failure  → ✕ (실패)
    1: success  → ◯ (성공)

판정 안정화(debounce):
    한 프레임 튐으로 결과가 깜빡이지 않도록, 같은 라벨이 연속
    STABLE_FRAMES 프레임 이상 conf 임계값을 넘겨야 '확정'으로 본다.

사용법:
    source ~/venv/yolo/bin/activate

    # 기본 실행 (창 미리보기, q=종료 / s=스냅샷)
    python detect_ox.py

    # 카메라 인덱스가 다르면 먼저 확인 후 지정
    python detect_ox.py --probe
    python detect_ox.py --cam 0

    # 확정되면 백엔드 배송 판별 엔드포인트로 자동 보고
    # (기본 30초 창 종료 시 최종 판정 1회 보고. 창 안에서 O/X 모두 확정되면
    #  AMBIGUOUS, 아무것도 확정 안 되면 TIMEOUT_NO_CARD 로 보고)
    python detect_ox.py --post-to <deliveryId> --api http://localhost:8000

    # 무한 루프 모드 (개발/테스트용, 확정 즉시 보고)
    python detect_ox.py --post-to <id> --window-seconds 0

    # 디스플레이 없는 환경(SSH 등) — 창 없이 콘솔에만 판정 출력
    python detect_ox.py --no-window

주의:
    - 카메라 인덱스는 환경마다 다르다. isOpened()가 True여도 프레임이
      안 읽힐 수 있으므로(UVC 메타데이터 노드), --probe로 실제 프레임이
      나오는 인덱스를 먼저 확인할 것. (현재 머신 기준 실제 카메라 = index 4)
"""

import argparse
import urllib.error
import urllib.request
import json
from pathlib import Path

import cv2
from ultralytics import YOLO

# ─────────────────────────────────────────────
# 설정
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WEIGHTS = REPO_ROOT / "backend" / "models" / "pinky_yolo_v1.pt"

CAM_INDEX      = 4      # 실제 웹캠 인덱스 (--probe로 확인)
CONF           = 0.5    # 신뢰도 임계값 (안 잡히면 0.25로 낮추기)
IMGSZ          = 640
STABLE_FRAMES  = 5      # 같은 라벨이 이만큼 연속되면 '확정'
WINDOW_SECONDS = 30     # 판정 창 길이 (초). 0 이하이면 창 없이 무한 루프.

# 창 종료 시 사용되는 실패 사유 코드 (backend FailReason enum과 동일 문자열 유지)
FAIL_REASON_X_CARD    = "X_CARD_DETECTED"
FAIL_REASON_TIMEOUT   = "TIMEOUT_NO_CARD"
FAIL_REASON_AMBIGUOUS = "AMBIGUOUS_BOTH_CARDS"

# 라벨 → (표시 기호, 한글, 색 BGR)
VERDICT_STYLE = {
    "success": ("O", "성공", (0, 200, 0)),
    "failure": ("X", "실패", (0, 0, 255)),
}
# ─────────────────────────────────────────────


def probe_cameras(max_index=6):
    """각 인덱스에서 실제 프레임이 읽히는지 확인하고 테스트 이미지를 저장한다."""
    print("카메라 인덱스 확인 중... (probe_*.jpg 로 저장됨)")
    Path("probe").mkdir(exist_ok=True)
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if not cap.isOpened():
            print(f"[{i}] 안 열림")
            cap.release()
            continue
        for _ in range(5):        # 워밍업
            cap.read()
        ok, frame = cap.read()
        if ok and frame is not None:
            h, w = frame.shape[:2]
            out = f"probe/probe_{i}.jpg"
            cv2.imwrite(out, frame)
            print(f"[{i}] OK  {w}x{h}  → {out}")
        else:
            print(f"[{i}] 열리지만 프레임 못 읽음 (메타데이터 노드 가능성)")
        cap.release()
    print("probe/ 폴더의 이미지를 열어 실제 웹캠 화면이 나온 인덱스를 확인하세요.")


def post_verification(api_base, delivery_id, result, reason=None):
    """확정된 판정을 백엔드 verification 엔드포인트로 보고한다.

    - result: "SUCCESS" 또는 "FAILED"
    - reason: FAILED일 때 필수. FailReason enum 문자열(X_CARD_DETECTED /
      TIMEOUT_NO_CARD / AMBIGUOUS_BOTH_CARDS) 중 하나.
    """
    body = {"result": result}
    if result == "FAILED":
        body["reason"] = reason or FAIL_REASON_X_CARD

    url = f"{api_base.rstrip('/')}/deliveries/{delivery_id}/verification"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            suffix = f" reason={reason}" if reason else ""
            print(f"→ 백엔드 보고 완료: {result}{suffix} (HTTP {resp.status})")
            return True
    except urllib.error.HTTPError as e:
        print(f"→ 백엔드 보고 실패: HTTP {e.code} {e.read().decode(errors='replace')[:200]}")
    except urllib.error.URLError as e:
        print(f"→ 백엔드 연결 실패: {e.reason} ({url})")
    return False


def decide_window_verdict(confirmed_labels):
    """30초 창 안에 확정된 라벨 집합에서 최종 판정을 도출한다.

    - {"success"} only               → SUCCESS
    - {"failure"} only               → FAILED / X_CARD_DETECTED
    - {"success", "failure"} both    → FAILED / AMBIGUOUS_BOTH_CARDS
    - 비어 있음                       → FAILED / TIMEOUT_NO_CARD

    Returns:
        (result, reason) — result는 "SUCCESS"/"FAILED", reason은 FAILED일 때 사유 코드.
    """
    has_success = "success" in confirmed_labels
    has_failure = "failure" in confirmed_labels

    if has_success and has_failure:
        return "FAILED", FAIL_REASON_AMBIGUOUS
    if has_success:
        return "SUCCESS", None
    if has_failure:
        return "FAILED", FAIL_REASON_X_CARD
    return "FAILED", FAIL_REASON_TIMEOUT


def top_detection(result, names):
    """한 프레임 추론 결과에서 conf가 가장 높은 박스의 (label, conf)를 돌려준다.

    박스가 없으면 (None, 0.0).
    """
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return None, 0.0
    confs = boxes.conf.tolist()
    clss = boxes.cls.tolist()
    best = max(range(len(confs)), key=lambda i: confs[i])
    return names[int(clss[best])], confs[best]


def draw_overlay(frame, label, conf, confirmed, fps):
    """미리보기 프레임 위에 현재 판정·확정 여부·FPS를 그린다."""
    h, w = frame.shape[:2]

    if label in VERDICT_STYLE:
        symbol, korean, color = VERDICT_STYLE[label]
        text = f"{symbol}  {korean}  {conf:.2f}"
    else:
        symbol, color = "?", (160, 160, 160)
        text = "판정 대기 (카드 없음)"

    # 상단 반투명 배너
    banner = frame.copy()
    cv2.rectangle(banner, (0, 0), (w, 70), (0, 0, 0), -1)
    cv2.addWeighted(banner, 0.45, frame, 0.55, 0, frame)

    cv2.putText(frame, text, (16, 48),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, color, 3)

    # 큰 기호를 우상단에
    cv2.putText(frame, symbol, (w - 90, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 2.2, color, 5)

    # 확정 표시
    if confirmed and label in VERDICT_STYLE:
        cv2.rectangle(frame, (2, 2), (w - 2, h - 2), color, 6)
        cv2.putText(frame, "CONFIRMED", (16, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    cv2.putText(frame, f"{fps:4.1f} FPS  (q=quit, s=snapshot)",
                (16, h - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 1)
    return frame


def run(weights, cam_index, conf, stable_frames, show_window,
        post_to, api_base, window_seconds):
    weights = Path(weights)
    if not weights.exists():
        raise FileNotFoundError(
            f"가중치 없음: {weights}\n"
            f"backend/models/pinky_yolo_v1.pt 가 있는지 확인하거나 --weights로 지정하세요."
        )

    print(f"모델 로드: {weights}")
    model = YOLO(str(weights))
    names = model.names   # {0: 'failure', 1: 'success'}

    cap = cv2.VideoCapture(cam_index)
    if not cap.isOpened():
        raise RuntimeError(
            f"웹캠 인덱스 {cam_index} 못 엶. "
            f"'python detect_ox.py --probe'로 올바른 인덱스를 확인하세요."
        )
    for _ in range(10):   # 워밍업 (초기 프레임은 노출 자동조정 중)
        cap.read()

    windowed = window_seconds > 0
    mode_desc = f"창 {window_seconds}s 창 판정" if windowed else "무한 루프"
    print(f"실시간 판별 시작 (cam={cam_index}, conf={conf}, "
          f"확정={stable_frames}프레임 연속, 모드={mode_desc})")
    if not show_window:
        print("창 없음(--no-window): 판정이 바뀔 때만 콘솔에 출력합니다. Ctrl+C로 종료.")

    run_label = None          # 현재 연속되고 있는 라벨
    run_count = 0             # 그 라벨의 연속 프레임 수
    confirmed_label = None    # 최근 확정된 라벨 (콘솔 중복 출력 방지)
    window_confirmed = set()  # 창 안에서 한 번이라도 확정된 라벨 집합
    window_start = cv2.getTickCount()
    tick_prev = window_start

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("프레임 못 읽음"); break

            # 추론 (verbose 끄고 단일 프레임)
            result = model.predict(frame, imgsz=IMGSZ, conf=conf, verbose=False)[0]
            label, det_conf = top_detection(result, names)

            # 연속 카운트 갱신 (박스 없으면 초기화)
            if label is None:
                run_label, run_count = None, 0
            elif label == run_label:
                run_count += 1
            else:
                run_label, run_count = label, 1

            confirmed = run_count >= stable_frames

            # 확정 순간 한 번만 콘솔에 출력. 창 판정 모드에서는 즉시 보고하지 않고,
            # 창 안에 등장한 라벨을 window_confirmed에 누적한 뒤 창 종료 시 최종 결정.
            if confirmed and run_label != confirmed_label:
                confirmed_label = run_label
                symbol, korean, _ = VERDICT_STYLE[run_label]
                print(f"확정: {symbol} {korean} (conf={det_conf:.2f})")
                window_confirmed.add(run_label)
                if not windowed and post_to:
                    # 무한 루프 모드: 즉시 보고 (기존 동작 유지)
                    if run_label == "success":
                        post_verification(api_base, post_to, "SUCCESS")
                    else:
                        post_verification(api_base, post_to, "FAILED", FAIL_REASON_X_CARD)

            # 창 종료 검사
            if windowed:
                elapsed = (cv2.getTickCount() - window_start) / cv2.getTickFrequency()
                if elapsed >= window_seconds:
                    result, reason = decide_window_verdict(window_confirmed)
                    print(f"[창 종료] {elapsed:.1f}s 경과 · 확정 라벨={sorted(window_confirmed) or '없음'} "
                          f"→ {result}" + (f" ({reason})" if reason else ""))
                    if post_to:
                        post_verification(api_base, post_to, result, reason)
                    break

            # FPS
            tick_now = cv2.getTickCount()
            fps = cv2.getTickFrequency() / max(1, (tick_now - tick_prev))
            tick_prev = tick_now

            if show_window:
                # 박스가 그려진 프레임 위에 판정 오버레이
                annotated = result.plot()
                annotated = draw_overlay(annotated, label, det_conf, confirmed, fps)
                cv2.imshow("O/X detect", annotated)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                if key == ord('s'):
                    snap = Path("snapshots"); snap.mkdir(exist_ok=True)
                    n = len(list(snap.glob("ox_*.jpg")))
                    out = snap / f"ox_{n:03d}.jpg"
                    cv2.imwrite(str(out), annotated)
                    print(f"✓ 스냅샷 저장 {out}")
            # 헤드리스(--no-window)에선 위의 '확정:' 콘솔 출력만으로 판정을 전달한다.
    except KeyboardInterrupt:
        print("\n중단됨")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("종료")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="웹캠 실시간 O/X 판별")
    parser.add_argument("--probe", action="store_true",
                        help="카메라 인덱스만 확인하고 종료")
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS),
                        help=f"가중치 경로 (기본: {DEFAULT_WEIGHTS})")
    parser.add_argument("--cam", type=int, default=CAM_INDEX,
                        help=f"웹캠 인덱스 (기본: {CAM_INDEX}, --probe로 확인)")
    parser.add_argument("--conf", type=float, default=CONF,
                        help=f"신뢰도 임계값 (기본: {CONF})")
    parser.add_argument("--stable", type=int, default=STABLE_FRAMES,
                        help=f"확정에 필요한 연속 프레임 수 (기본: {STABLE_FRAMES})")
    parser.add_argument("--no-window", dest="window", action="store_false",
                        help="미리보기 창 없이 콘솔 출력만 (디스플레이 없는 환경)")
    parser.add_argument("--post-to", default=None,
                        help="확정 시 판정을 보고할 배송 id (백엔드 verification)")
    parser.add_argument("--api", default="http://localhost:8000",
                        help="백엔드 base URL (기본: http://localhost:8000)")
    parser.add_argument("--window-seconds", type=int, default=WINDOW_SECONDS,
                        help=f"판정 창 길이(초). 0 이하이면 무한 루프 (기본: {WINDOW_SECONDS})")
    args = parser.parse_args()

    if args.probe:
        probe_cameras()
    else:
        run(args.weights, args.cam, args.conf, args.stable,
            args.window, args.post_to, args.api, args.window_seconds)
