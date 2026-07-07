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

데이터·학습은 **두 위치로 나뉜다**: 리포에서 버전 관리되는 코드(A)와,
GPU 머신에만 있는 데이터셋·학습 산출물(B). 헷갈리지 않도록 분리해 표기.

**(A) 리포 안 — `pinky-care/` (커밋 대상)**

```
pinky-care/
├── yolo/
│   ├── notebooks/
│   │   ├── 01_capture.ipynb   # 촬영 (ipywidgets 방식, 출력 제거본)
│   │   └── 02_train.ipynb     # 학습/추론
│   ├── capture_webcam.py      # 촬영 CLI (--class/--cam/--n, --probe로 인덱스 확인)
│   ├── train_predict.py       # 학습/추론 CLI (train | predict)
│   ├── detect_ox.py           # 웹캠 실시간 O/X 판별 CLI (--cam/--conf/--post-to)
│   └── README.md              # (이 파일)
└── backend/
    ├── models/
    │   └── pinky_yolo_v1.pt   # 최종 가중치 (best.pt 사본, ≈5MB) ← 백엔드가 로드
    └── tests/fixtures/images/ # 회귀 테스트용 소량 이미지 (성공/실패)
```

> `yolo/` 자체엔 데이터셋·`runs/`·`yolo11n.pt`가 **없다**. 리포엔 코드·노트북과
> 최종 가중치 한 개만 들어간다. (`__pycache__/`는 gitignore)

**(B) GPU 머신 `~/yolo/` — 리포 밖 (커밋 X)**

```
~/yolo/
├── pinkycare.yolov8/          # Roboflow export 데이터셋
│   ├── yolo_images/{images,labels}/{train,val}/
│   ├── data.yaml              # Roboflow 원본 (클래스 순서 기준)
│   ├── finish.yaml            # 학습용 (path를 로컬 절대경로로 수정)
│   └── README.{dataset,roboflow}.txt
├── runs/detect/
│   ├── delivery_train/weights/best.pt   # 학습 결과 → 여기서 backend로 복사
│   └── val_predict/           # val 추론 결과
├── yolo1/{성공,실패,약}/       # 촬영 원본 (라벨링 전; 약은 구 4클래스 잔재)
├── yolo11n.pt                 # 사전학습 가중치
└── (기타 실험물: yolo26n.pt, capture.py, bus.jpg, datasets/coco8 …)
```

**학습 결과가 리포로 들어가는 경로** — `runs/`의 `best.pt`는 그 이름으로 커밋하지
않고, 백엔드가 로드하는 이름으로 복사한다:

```
~/yolo/runs/detect/delivery_train/weights/best.pt   # 산출물 (리포 밖)
        │  cp
        ▼
pinky-care/backend/models/pinky_yolo_v1.pt          # 최종 가중치 (커밋 O, best.pt와 동일)
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

`capture_webcam.py` 실행. 성공/실패 클래스를 `--class` 플래그로 바꿔가며 촬영.

```bash
source ~/venv/yolo/bin/activate
python capture_webcam.py --probe                 # 처음 한 번 — 실제 카메라 인덱스 확인
python capture_webcam.py --class 성공            # 성공 촬영 (창 클릭 후 c=촬영, q=종료)
python capture_webcam.py --class 실패 --n 50     # 실패, 이번 세션 50장만
```

- 촬영 방식: `c` 키로 한 장씩 저장 (실시간 미리보기 창 확인하며)
- 저장 위치: `yolo1/{클래스}/` (예: `yolo1/성공/`, `yolo1/실패/`)
- **CLI 플래그** (상단 상수를 매번 고칠 필요 없음. 안 주면 상수 기본값 사용):
  | 플래그 | 의미 | 기본값 |
  | --- | --- | --- |
  | `--class` | 촬영할 클래스명 (저장 폴더명) | `성공` |
  | `--cam` | 웹캠 인덱스 | `4` |
  | `--n` | **이번 세션** 목표 장수 | `100` |
  | `--probe` | 카메라 인덱스만 확인하고 종료 | — |
- **이어찍기(덮어쓰기 방지)**: 재실행하면 해당 클래스 폴더의 마지막 번호
  다음부터 이어서 저장한다. 예) 기존 30장 → `{클래스}_030.jpg`부터.
  여러 세션에 나눠 찍어도 이전 사진이 덮어써지지 않음. 실행 시
  `기존 N장 감지 — N번부터 이어서 저장` 메시지로 확인 가능.
  (`--n`은 누적 총량이 아니라 **이번 세션에 추가로 찍을 장수**)
- **카메라 인덱스 주의**: 환경마다 다름. `--probe`가 `probe/probe_*.jpg`를
  저장하니 열어서 실제 웹캠 화면이 나온 인덱스를 확인하고 `--cam`으로 지정
  (또는 스크립트 상단 `CAM_INDEX` 기본값 수정). UVC 웹캠은 메타데이터 노드가
  함께 잡혀 `isOpened()`가 True여도 프레임이 안 읽힐 수 있음.
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

### 3-2. 실시간 웹캠 판별 (detect_ox.py)

학습된 가중치(`backend/models/pinky_yolo_v1.pt`)를 로드해 **웹캠 프레임마다
추론**하고, 화면에 박스와 함께 O(성공)/X(실패) 판정을 실시간 표시한다.
`train_predict.py predict`가 폴더 단위 배치 추론이라면, 이쪽은 라이브 스트림용.

```bash
source ~/venv/yolo/bin/activate

python detect_ox.py --probe          # 처음 한 번 — 실제 카메라 인덱스 확인
python detect_ox.py --cam 0          # 실시간 판별 (q=종료, s=스냅샷)

# 확정되면 백엔드 배송 판별 엔드포인트로 자동 보고
python detect_ox.py --cam 0 --post-to <deliveryId> --api http://localhost:8000

# 디스플레이 없는 환경(SSH 등) — 창 없이 콘솔로만 판정
python detect_ox.py --cam 0 --no-window
```

- **가중치 자동 탐색**: 리포 기준 `backend/models/pinky_yolo_v1.pt`를 기본 로드
  (`--weights`로 변경 가능). 별도 `.pt` 복사 불필요.
- **판정 안정화(debounce)**: 한 프레임 튐으로 O/X가 깜빡이지 않도록, 같은
  라벨이 연속 `--stable`(기본 5) 프레임 이상 `--conf`(기본 0.5)를 넘겨야
  **확정**으로 본다. 확정 순간에만 콘솔 출력 / 백엔드 보고가 발생.
- **백엔드 연동(`--post-to`)**: 확정 시 `PATCH /deliveries/{id}/verification`을
  호출. 성공→`{result: SUCCESS}`, 실패→`{result: FAILED, reason}`. 같은 배송에
  중복 보고하지 않는다(다른 라벨이 새로 확정될 때만 재보고). → [`4. 백엔드로 반영`](#4-백엔드로-반영)
- **CLI 플래그**:
  | 플래그 | 의미 | 기본값 |
  | --- | --- | --- |
  | `--cam` | 웹캠 인덱스 | `4` (머신마다 다름, `--probe`로 확인) |
  | `--conf` | 신뢰도 임계값 | `0.5` |
  | `--stable` | 확정에 필요한 연속 프레임 수 | `5` |
  | `--weights` | 가중치 경로 | `backend/models/pinky_yolo_v1.pt` |
  | `--post-to` | 확정 판정을 보고할 배송 id | 없음(로컬만) |
  | `--api` | 백엔드 base URL | `http://localhost:8000` |
  | `--no-window` | 미리보기 창 없이 콘솔 출력만 | — |
  | `--probe` | 카메라 인덱스만 확인하고 종료 | — |

> **카메라 인덱스**: `capture_webcam.py`와 동일하게 환경마다 다르다. GPU 머신은
> index 4였지만 다른 머신에선 0~3일 수 있으니 `--probe`로 실제 프레임이 나오는
> 인덱스를 먼저 확인할 것.

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
