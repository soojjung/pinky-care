"""
capture_webcam.py — 웹캠으로 학습용 이미지 촬영

클래스별로 CLASS_NAME만 바꿔가며 실행한다.
실시간 미리보기 창을 보면서 c 키로 한 장씩 저장, q 키로 종료.

사용법:
    source ~/venv/yolo/bin/activate
    python capture_webcam.py

주의:
    - 카메라 인덱스는 환경마다 다르다. isOpened()가 True여도 프레임이
      안 읽힐 수 있으므로(UVC 메타데이터 노드), 아래 --probe로 실제
      프레임이 나오는 인덱스를 먼저 확인할 것.
        python capture_webcam.py --probe
    - macOS는 첫 실행 시 카메라 권한 팝업. Jupyter/터미널 앱에 허용.
"""

import argparse
import cv2
from pathlib import Path

# ─────────────────────────────────────────────
# 설정
CLASS_NAME = "성공"   # 촬영할 클래스 (성공 / 실패 / 약 / 기저귀 / 혈당측정키트 / 물티슈)
N_SHOTS    = 100      # 목표 장수
CAM_INDEX  = 4        # 실제 웹캠 인덱스 (--probe로 확인)
SAVE_ROOT  = "yolo1"  # 저장 루트. 최종 경로: {SAVE_ROOT}/{CLASS_NAME}/
# ─────────────────────────────────────────────


def probe_cameras(max_index=5):
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


def capture():
    save_dir = Path(f"{SAVE_ROOT}/{CLASS_NAME}")
    save_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        raise RuntimeError(
            f"웹캠 인덱스 {CAM_INDEX} 못 엶. "
            f"'python capture_webcam.py --probe'로 올바른 인덱스를 확인하세요."
        )

    # 워밍업 (초기 프레임은 노출 자동조정 중)
    for _ in range(10):
        cap.read()

    count = 0
    print(f"[{CLASS_NAME}] 촬영 시작 — 창을 클릭하고 c=촬영, q=종료")

    try:
        while count < N_SHOTS:
            ok, frame = cap.read()
            if not ok:
                print("프레임 못 읽음"); break

            # 미리보기에 안내 텍스트 (저장은 원본)
            view = frame.copy()
            cv2.putText(
                view, f"{CLASS_NAME}  {count}/{N_SHOTS}  (c=save, q=quit)",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
            )
            cv2.imshow("capture", view)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            if key == ord('c'):
                path = save_dir / f"{CLASS_NAME}_{count:03d}.jpg"
                cv2.imwrite(str(path), frame)   # 텍스트 없는 원본 저장
                count += 1
                print(f"✓ saved {path}")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print(f"총 {count}장 저장 → {save_dir.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true",
                        help="카메라 인덱스만 확인하고 종료")
    args = parser.parse_args()

    if args.probe:
        probe_cameras()
    else:
        capture()
