# PinkyCare — YOLO 판별 파이프라인 작업 계획

간호사가 배송 도착 시 물품이 실제로 전달되었는지 판별하는 YOLO 파이프라인. 이 문서는 정수진 담당 파트의 진행 로드맵.

- **최종 수정일**: 2026-07-06
- **관련 문서**: [`api-spec.md`](./api-spec.md) (§7 YOLO 엔드포인트), [`../backend/README.md`](../backend/README.md)

---

## 0. 내일 30분 안에 시작하기

1. 이 문서 §3 "작업 단계" 훑기 → 현재 자기 위치 파악
2. §4 "미결정 사항" 확인 → 팀원과 정해야 할 게 있으면 슬랙 남기기
3. Phase 1이 아직이면 → 촬영 대상 물품 4종 확보하고 §3.1로
4. Phase 1 완료 상태면 → 라벨링 툴 세팅부터 (§3.1 후반)

---

## 1. 목적과 MVP 완성 조건

**목적**: 로봇이 목적지에 도착(`ARRIVED`)한 순간 카메라 프레임을 YOLO로 추론하여, 지정된 물품(약/주사/붕대/생리식염수 중 1)이 실제로 놓여 있는지 판별하고 배송 상태를 `SUCCESS`/`FAILED`로 확정.

**MVP 완성 조건**
- [ ] 4개 클래스 (약/주사/붕대/생리식염수) 학습된 YOLO 모델 파일 확보
- [ ] `verify(image_bytes, expected_item) → SUCCESS/FAILED+reason` 순수 함수 완성
- [ ] `ARRIVED` 상태 진입 시 백엔드가 자동으로 위 함수를 호출하고 SSE로 결과 브로드캐스트
- [ ] 카메라 프레임을 백엔드가 받을 방법 하나 확정 (실기기 or MVP 시뮬)
- [ ] pytest로 추론 모듈 회귀 방지 (이미지 fixture 몇 장 + expected 결과)

---

## 2. 오늘까지의 상태 (2026-07-06)

- 백엔드 v1 REST + SSE 구현 완료 (`backend/app/`)
- 프론트가 실백엔드에 SSE로 붙어 end-to-end 시나리오 확인됨
- 상태 전이는 지금 **외부에서 `PATCH /verification`을 curl로 쳐서** 시뮬레이션 중 → YOLO가 이 자리를 대체함
- 백엔드 pytest 16개 통과 (`backend/tests/`)
- ROS2 노드/카메라 하드웨어는 아직 없음

---

## 3. 작업 단계

각 단계 완료 시 이 문서의 체크박스를 갱신하세요.

### 3.1 데이터셋 준비 (선행 필수, 물리 시간 필요)

**클래스**: `약`, `주사`, `붕대`, `생리식염수` (`backend/app/models/delivery.py`의 `Item` enum과 일치)

- [ ] 각 물품 실제 물체 확보 (여러 브랜드/사이즈 있으면 다양성↑)
- [ ] 촬영 환경 세팅
  - 실제 배송 상황 재현: 병실 침대 사이드테이블 / 트레이 위 / 조명 조건 2~3가지
  - 배경 다양성: 흰 시트, 나무 테이블, 금속 트레이 등
- [ ] 클래스당 **150~300장** 촬영 (총 600~1200장 목표)
  - 각도: top-down, 45도, side
  - 오클루전: 다른 물건이 살짝 가린 경우 포함
- [ ] 라벨링 툴 세팅 → **Roboflow** 추천 (팀 협업 · export가 편함) / 대안: `labelImg`, `label-studio`
- [ ] YOLO 포맷으로 export (train/val 80/20 split)
- [ ] 데이터셋을 어디에 둘지 결정
  - 후보: `backend/datasets/pinky-care-v1/` (gitignore 처리), 또는 Roboflow에 원본만 두고 로컬은 캐시

**산출물**: `datasets/pinky-care-v1/{images,labels}/{train,val}/`, `data.yaml`

---

### 3.2 모델 학습

- [ ] Ultralytics 설치: `pip install ultralytics`
- [ ] 베이스 모델 선택: **YOLOv8n** 또는 **YOLO11n** (엣지 배포 대비 작은 모델)
- [ ] 학습 실행:
  ```bash
  yolo train model=yolov8n.pt data=datasets/pinky-care-v1/data.yaml \
    epochs=100 imgsz=640 batch=16
  ```
- [ ] 학습 로그 확인 (`runs/detect/train*/`) — 목표: **mAP@0.5 ≥ 0.85**
- [ ] 미달 시 데이터 늘리거나 augmentation 조정 후 재학습
- [ ] 최종 `best.pt`를 `backend/models/pinky_yolo_v1.pt`로 복사 (경로는 나중에 정리)

**산출물**: `backend/models/pinky_yolo_v1.pt` + 성능 리포트

---

### 3.3 추론 모듈 (백엔드 독립)

파일: `backend/app/services/yolo.py` (신규)

인터페이스:
```python
from enum import Enum
from app.models.delivery import Item, VerificationResult


class YoloOutcome(NamedTuple):
    result: VerificationResult
    reason: str | None  # FAILED일 때만 채움


def verify(image: bytes, expected_item: Item) -> YoloOutcome:
    """카메라 프레임 bytes를 받아 배송 성공/실패 판정."""
    ...
```

작업:
- [ ] 순수 함수로 구현 (전역 모델 로드 캐시는 모듈 레벨에서 lazy)
- [ ] 실패 사유 카테고리 정의
  - `"물품 없음"` — 아무 것도 감지 안 됨
  - `"다른 물품 감지: {감지된-품목}"` — 지정 품목과 다른 게 잡힘
  - `"인식 신뢰도 부족"` — top-1 confidence < 임계값 (예: 0.6)
- [ ] pytest 추가 (`backend/tests/test_yolo.py`)
  - `tests/fixtures/images/약_success_01.jpg` 등 소량 이미지 fixture
  - `verify(bytes, Item.MED) == SUCCESS`, `verify(bytes, Item.INJ) == FAILED("다른 물품 감지: 약")` 등

**산출물**: `backend/app/services/yolo.py` + `backend/tests/test_yolo.py`

---

### 3.4 백엔드 자동 트리거 통합

지금은 외부에서 `PATCH /verification`을 쳐야 상태가 넘어감. YOLO 붙이면 `ARRIVED` 순간 백엔드가 알아서 판별.

**설계 안 A (권장)**: `robot-status` PATCH 핸들러 내부에서 자동 실행
- `PATCH /robot-status {ARRIVED}` 수신 → 상태 `ARRIVED` 반영/브로드캐스트 → 곧바로 백그라운드 태스크로 YOLO 실행 → 결과 나오면 기존 verification 로직 호출
- 장점: 외부 클라이언트 하나 줄어듦
- 단점: `robot-status` 엔드포인트가 YOLO 의존성을 가짐

**설계 안 B**: YOLO를 별도 워커로 두고 SSE 구독
- 별도 프로세스가 SSE로 `ARRIVED` 감지 → 카메라 프레임 grab → `POST /deliveries/{id}/verification` 콜
- 장점: 관심사 분리
- 단점: 두 프로세스 관리해야 함

일단 **안 A로 시작**하는 게 빠름. 나중에 필요하면 리팩터.

작업:
- [ ] `PATCH /robot-status`가 `ARRIVED` 도달 시 카메라 프레임 소스에서 이미지 획득 (§3.5)
- [ ] `yolo.verify(image, delivery.item)` 호출
- [ ] 결과에 따라 내부적으로 verification 로직 재사용 (핸들러 함수 분리 필요)
- [ ] 기존 pytest들이 계속 통과해야 함 — YOLO는 테스트에서 mock으로 대체 가능하게 DI

**산출물**: `backend/app/api/deliveries.py` 리팩터 + 관련 pytest

---

### 3.5 카메라 프레임 소스 (팀 결정 필요)

가장 미확정. §4로 넘김.

임시 MVP 안: `POST /deliveries/{id}/image` 엔드포인트를 하나 만들어서, 로컬 이미지 파일을 curl로 업로드하면 백엔드가 그걸 캐시했다가 `ARRIVED` 시 사용. 팀원의 하드웨어 세팅이 정해지기 전에도 데모 가능.

---

## 4. 미결정 사항 (팀 협의 필요)

내일 팀원과 만나면 이 리스트로 이야기 시작하세요.

- **[ ] 카메라 하드웨어**: 로봇에 어떤 카메라가 붙는가? (RGB 웹캠, RealSense, RPi Cam 등)
- **[ ] 프레임 전달 방식**: ROS2 이미지 토픽 → 어떻게 백엔드가 받나? 후보:
  1. ROS2 노드가 `ARRIVED` 프레임을 백엔드에 HTTP POST
  2. 백엔드가 RTSP/WebRTC로 스트림 받아 직접 grab
  3. 파일 시스템 공유 (같은 호스트)
- **[ ] 배송 미션 전달**: 백엔드 → ROS2 방향 트리거 (`REQUESTED` → Nav2 goal). SSE 구독안 유력
- **[ ] 병실 좌표 매핑**: `"101"/"102"/"103"` → Nav2 map coordinate. 팀원의 SLAM/map 결과 필요
- **[ ] 모델 배포 위치**: 백엔드 프로세스 안에 로드 vs. 별도 GPU 서버. GPU 유무에 따름
- **[ ] 실패 시 재시도 정책**: FAILED 후 `다시 시도` 눌렀을 때 로봇이 다시 나가야 하나, 아니면 현 위치에서 재판정만 하나?

---

## 5. 폴더/파일 참조

- 백엔드 코드: `backend/app/`
  - 상태 전이: `services/transitions.py`
  - 브로드캐스터: `services/broadcaster.py`
  - PATCH 핸들러: `api/deliveries.py`
  - 모델: `models/delivery.py`
- API 계약: `docs/api-spec.md` §7 (verification 엔드포인트)
- 프론트가 기대하는 결과 shape: `frontend/src/types/delivery.ts` (`failReason`)
- 테스트 예시: `backend/tests/test_deliveries.py`, `test_sse.py`

---

## 6. 진행 로그

새 단계 시작/종료할 때마다 한 줄씩 남기면 다음 날 픽업이 쉬움.

| 날짜 | 진행 |
|---|---|
| 2026-07-06 | 계획 문서 초안 작성. Phase 1 착수 예정. |
