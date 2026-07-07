# PinkyCare — YOLO 학습 워크플로

노인 병동 배송 로봇의 **배송 성공/실패 판별용** YOLO 모델을 학습·평가하는 코드가
모여 있는 폴더. 백엔드가 실제로 사용하는 추론 코드는
`backend/app/services/yolo.py`에 있고, 이 폴더는 **학습 사이클 전용**.

- **판별 방식**: 배송 완료 시점에 O(성공)/X(실패) 카드를 카메라에 노출 → YOLO가
  카드를 인식해 성공/실패 분기
- **2클래스**: `0: failure`(X 카드), `1: success`(O 카드)
- **상세 계획**: [`../docs/yolo-plan.md`](../docs/yolo-plan.md)

> **참고 — 접근 변경 이력**
> 초기 계획(§yolo-plan)은 배송 물품 자체를 인식하는 4클래스
> (`약`/`기저귀`/`혈당측정키트`/`물티슈`) 방식이었으나, v1에서는 **O/X 카드 판별
> 방식**으로 진행했다. 물품 인식보다 데이터 수집·라벨링이 단순하고, 성공/실패
> 분기라는 백엔드 요구에 직접 대응되기 때문. 물품 인식 방식은 후속 버전 과제로
> 보류.

---

## 폴더 구조 (실제)

```
yolo/
├── pinkycare.yolov8/          # Roboflow export 데이터셋
│   ├── yolo_images/
│   │   ├── images/train/images/val/
│   │   └── labels/train/labels/val/
│   ├── data.yaml              # Roboflow 원본 (클래스 순서 기준)
│   ├── finish.yaml            # 학습용 (path를 로컬 경로로 수정해 사용)
│   └── README.roboflow.txt
├── runs/detect/
│   ├── delivery_train/        # 학습 결과 + weights/best.pt
│   └── val_predict/           # val 추론 결과
├── capture_webcam.py          # 웹캠 촬영 스크립트 (CLI, c 키로 촬영, --probe로 인덱스 확인)
├── train_predict.py           # 학습/추론 CLI (train | predict 모드)
├── yolo11n.pt                 # 사전학습 가중치
└── README.md                  # (이 파일)
```

**저장소 밖(gitignore 권장)**:

- `runs/detect/*` — 학습 로그·중간 가중치
- 라벨링 전 촬영 원본

**저장소 안**:

- 이 폴더의 코드(`capture_webcam.py`, `train_predict.py`, 노트북)
- 최종 학습 가중치 → `backend/models/pinky_yolo_v1.pt` (yolo11n 기준 ≈ 5MB)
- pytest 회귀용 소량 이미지 → `backend/tests/fixtures/images/`

---

## 환경

- **머신**: 로컬 GPU 단일 머신 (NVIDIA RTX 5080 Laptop, 15.8GB)
- **소프트웨어**: Ultralytics 8.4.87, Python 3.12, torch 2.12 + CUDA 13.0
- **실행**: 로컬 주피터. 초기 계획의 Colab/Google Drive 흐름은 사용하지 않음
  (로컬 GPU로 충분해 드라이브 마운트 불필요)

가상환경은 `~/venv/yolo`에 있으며, 터미널 작업 시:

```bash
source ~/venv/yolo/bin/activate
```

---

## 전체 흐름 (재현 순서)

```
1. 촬영 (capture_webcam.py, 웹캠)
       │
       ▼
2. Roboflow 업로드 → O/X 바운딩 박스 라벨링 → YOLOv8 export
       │
       └──────► pinkycare.yolov8/  (로컬에 압축 해제)
                     │
                     ▼
                3. 학습 (02_train.ipynb / 주피터)
                     │
                     ▼
                runs/detect/delivery_train/weights/best.pt
                     │
                     ▼
                4. best.pt → backend/models/pinky_yolo_v1.pt 로 반영
                     │
                     ▼
                5. backend/app/services/yolo.py 가 로드해서 verify() 제공
                     │
                     ▼
                6. PATCH /robot-status {ARRIVED} 순간 백엔드가 자동 호출
```

---

## 단계별 상세

### 1. 촬영 (웹캠)

`capture_webcam.py` 실행. 성공/실패 각각 `CLASS_NAME`을 바꿔가며 촬영.

```bash
source ~/venv/yolo/bin/activate
python capture_webcam.py --probe    # 처음 한 번 — 실제 카메라 인덱스 확인
python capture_webcam.py            # capture 창 클릭 후 c=촬영, q=종료
```

- 촬영 방식: `c` 키로 한 장씩 저장 (실시간 미리보기 창 확인하며)
- 저장 위치: `yolo1/{성공|실패}/`
- **카메라 인덱스 주의**: 환경마다 다름. `--probe`가 `probe/probe_*.jpg`를
  저장하니 열어서 실제 웹캠 화면이 나온 인덱스를 확인하고 스크립트 상단
  `CAM_INDEX` 를 그 값으로 수정. UVC 웹캠은 메타데이터 노드가 함께 잡혀
  `isOpened()`가 True여도 프레임이 안 읽힐 수 있음.
  (현재 머신 기준 실제 카메라 = index 4)
- 촬영 중 각도·거리·조명·배경을 계속 바꿔 다양성 확보

### 2. 라벨링 (Roboflow)

- Roboflow 프로젝트 → 원본 업로드 → O/X 카드에 바운딩 박스
- 클래스: `failure`(X), `success`(O)
- Split: train/val 80/20 (v1 결과: train 152 / val 42, 총 194장)
- 전처리: auto-orient, 512×512 stretch
- Export: YOLOv8 포맷

> **클래스 순서 함정**: Roboflow가 생성한 `data.yaml`의 `names` 순서가
> **정답 기준**. 라벨 `.txt`의 숫자가 이 순서로 저장됨.
> v1에서는 `0: failure, 1: success`. 별도로 만든 `finish.yaml`의 순서가
> 이와 어긋나 있어 성공/실패가 뒤바뀔 뻔했음 → **항상 data.yaml에 맞출 것.**

### 3. 학습 (로컬 GPU)

학습 전 준비:

1. `finish.yaml`의 `path`를 이 머신 절대경로로 수정 (예: `/home/hospital/yolo/pinkycare.yolov8/yolo_images`)
2. `train_predict.py` 상단 상수(`DATA_YAML`, `BEST_WEIGHTS`, `DEFAULT_SOURCE`)의 경로도 함께 맞춤

`finish.yaml` (v1 실제 사용):

```yaml
path: /home/hospital/yolo/pinkycare.yolov8/yolo_images
train: images/train
val: images/val
names:
  0: failure
  1: success
```

실행:

```bash
source ~/venv/yolo/bin/activate
python train_predict.py train
```

파라미터(`EPOCHS=100`, `IMGSZ=640`, `BATCH=16`, `DEVICE=0`)는 스크립트 상단에서 조정.

- 결과: `runs/detect/delivery_train/weights/best.pt`
- 학습 시간: 100 epochs / 약 2.5분 (RTX 5080)
- 목표: mAP@0.5 ≥ 0.85 → **달성 (0.977)**

### 3-1. 검증 추론 (val)

학습에 쓰지 않은 val 이미지로 sanity check:

```bash
# 기본: val 폴더 전체
python train_predict.py predict

# 특정 이미지/폴더 지정
python train_predict.py predict --source /path/to/images
```

- 임계값 `conf=0.5` (스크립트 상단). 안 잡히면 0.25로 낮춰서 재실행
- 결과 이미지: `runs/detect/val_predict/`

### 4. 백엔드로 반영

```bash
cp runs/detect/delivery_train/weights/best.pt \
   backend/models/pinky_yolo_v1.pt
git add backend/models/pinky_yolo_v1.pt
git commit -m "chore(yolo): v1 weights (mAP@0.5=0.977)"
```

`backend/app/services/yolo.py`가 모듈 로드 시점에
`backend/models/pinky_yolo_v1.pt`를 lazy load.

### 5. 회귀 방지

성공/실패 각각 1~2장을 골라:

```
backend/tests/fixtures/images/success_01.jpg
backend/tests/fixtures/images/failure_01.jpg
```

`backend/tests/test_yolo.py`가 이 이미지로 `verify()`의 SUCCESS/FAILED 분기 검증.

---

## v1 성능 (val 42장)

| Class   | Precision | Recall | mAP50 | mAP50-95 |
| ------- | --------- | ------ | ----- | -------- |
| all     | 0.970     | 0.977  | 0.977 | 0.623    |
| failure | 0.945     | 1.000  | 0.995 | 0.595    |
| success | 0.996     | 0.955  | 0.959 | 0.650    |

- mAP@0.5 = 0.977 로 목표(0.85) 크게 상회. O/X 구분이 시각적으로 명확해 높게 나옴.
- mAP@0.5:0.95 = 0.623 은 박스 위치 정밀도 지표. 성공/실패 분기 목적에는 영향 적음
  (카드 유무·클래스만 맞으면 됨).
- **한계**: 194장 / augmentation 미적용. 실제 로봇 카메라의 조명·각도 변화
  대응은 추가 촬영 또는 augmentation으로 보강 여지.

---

## 자주 하는 실수 (기록해두기)

| 실수                                       | 결과                             | 예방                                           |
| ------------------------------------------ | -------------------------------- | ---------------------------------------------- |
| data.yaml과 다른 클래스 순서로 학습        | 성공/실패가 통째로 뒤바뀜        | **Roboflow data.yaml의 names 순서를 정답으로** |
| finish.yaml의 path가 옛 경로(Downloads 등) | `images not found` 로 학습 실패  | path를 현재 데이터셋 절대경로로 수정           |
| 카메라 인덱스를 isOpened()만으로 판단      | 메타데이터 노드라 프레임 안 읽힘 | 실제 프레임이 읽히는 인덱스로 확정             |
| Roboflow에서 random split                  | val 성능 뻥튀기                  | 세션 단위 split 권장                           |
| 좌우반전 augmentation ON                   | O/X·글자 뒤집혀 학습 오염        | flip 옵션 OFF                                  |
| .pt를 datasets/ 안에 둠                    | gitignore에 걸려 트래킹 누락     | 최종 가중치는 `backend/models/`에              |

---

## 관련 문서

- 전체 계획: [`../docs/yolo-plan.md`](../docs/yolo-plan.md)
- API 계약: [`../docs/api-spec.md`](../docs/api-spec.md) §7 (verification 엔드포인트)
- 백엔드 통합: [`../backend/README.md`](../backend/README.md)
