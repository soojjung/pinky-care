"""
train_predict.py — YOLO 학습 & 추론

주피터에서 돌리던 학습·추론 흐름을 CLI 스크립트로 정리한 것.

사용법:
    source ~/venv/yolo/bin/activate

    # 학습
    python train_predict.py train

    # val 폴더로 추론 (학습된 best.pt 사용)
    python train_predict.py predict

    # 특정 이미지/폴더로 추론
    python train_predict.py predict --source /path/to/images

주의:
    - DATA_YAML 의 path 는 이 머신의 실제 절대경로여야 한다.
      옛 경로(Downloads 등)가 남아있으면 'images not found'로 실패.
    - 클래스 순서는 Roboflow data.yaml 기준. 직접 만든 yaml 순서가
      어긋나면 클래스가 통째로 뒤바뀐다.
"""

import argparse
from pathlib import Path
from ultralytics import YOLO

# ─────────────────────────────────────────────
# 설정
BASE_MODEL = "yolo11n.pt"   # 사전학습 가중치 (학습 시작점)
DATA_YAML  = "/home/hospital/yolo/pinkycare.yolov8/finish.yaml"
RUN_NAME   = "delivery_train"

EPOCHS = 100
IMGSZ  = 640
BATCH  = 16                 # GPU 메모리 부족 시 8
DEVICE = 0                  # 로컬 GPU

# 추론 기본 소스 (val 이미지 폴더)
DEFAULT_SOURCE = "/home/hospital/yolo/pinkycare.yolov8/yolo_images/images/val"
# 학습 결과 가중치 경로
BEST_WEIGHTS = f"/home/hospital/yolo/runs/detect/{RUN_NAME}/weights/best.pt"
# ─────────────────────────────────────────────


def train():
    model = YOLO(BASE_MODEL)
    results = model.train(
        data=DATA_YAML,
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=BATCH,
        device=DEVICE,
        name=RUN_NAME,
    )
    print(f"\n학습 완료 → {BEST_WEIGHTS}")
    return results


def predict(source):
    weights = Path(BEST_WEIGHTS)
    if not weights.exists():
        raise FileNotFoundError(
            f"학습된 가중치가 없음: {weights}\n먼저 'python train_predict.py train' 실행."
        )

    model = YOLO(str(weights))
    results = model.predict(
        source,
        save=True,          # 박스 그려진 결과 이미지 저장
        imgsz=IMGSZ,
        conf=0.5,           # 안 잡히면 0.25로 낮추기
        save_conf=True,
        name="val_predict",
    )
    # 저장 위치 안내
    if results:
        print(f"\n추론 완료 → {results[0].save_dir}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["train", "predict"],
                        help="train: 학습 / predict: 추론")
    parser.add_argument("--source", default=DEFAULT_SOURCE,
                        help="추론 대상 이미지/폴더 경로 (predict 모드)")
    args = parser.parse_args()

    if args.mode == "train":
        train()
    else:
        predict(args.source)
