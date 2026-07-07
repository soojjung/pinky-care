# PinkyCare — YOLO 판별 파이프라인 작업 계획

로봇이 배송 도착 후, **환자가 O/X 카드로 응답**하면 YOLO가 그 카드를 인식해 배송 성공/실패를 확정하는 파이프라인. 정수진 담당 파트의 진행 로드맵.

- **최종 수정일**: 2026-07-07
- **관련 문서**: [`api-spec.md`](./api-spec.md) (§7 YOLO 엔드포인트), [`../backend/README.md`](../backend/README.md), [`../yolo/README.md`](../yolo/README.md) (v1 실제 학습 결과)

> **v1 방식 확정 (2026-07-07)**: 초기 계획은 배송 물품 자체(약/기저귀/혈당측정키트/물티슈)를 인식하는 **4클래스 물품 판별** 방식이었으나, 데이터 수집·라벨링 단순화 및 성공/실패 분기라는 백엔드 요구에 직접 대응하기 위해 **2클래스 O/X 카드 판별** 방식으로 전환했다. 실제 학습된 v1 모델은 `yolo/README.md` 참고 (mAP@0.5 = 0.977). 물품 인식 방식은 후속 버전 과제로 보류.

---

## 0. 지금 위치

- **§3.1 데이터셋** ✅ v1 완료 (194장, `yolo/pinkycare.yolov8/`)
- **§3.2 모델 학습** ✅ v1 완료 (`yolo/runs/detect/delivery_train/weights/best.pt`, mAP@0.5=0.977)
- **§3.3 추론 모듈** 🔜 다음 작업 (`backend/app/services/yolo.py` 신규)
- **§3.4 백엔드 자동 트리거** 🔜 다음 작업
- **§3.5 프레임 소스** — 방식 A 확정 (§4 참고). ROS2 팀 구현 대기

내일 시작할 지점 = **§3.3부터**.

---

## 1. 목적과 MVP 완성 조건

**목적**: 로봇이 목적지에 도착(`ARRIVED`)한 뒤 30초 동안 카메라 프레임을 반복 추론. 노인 환자가 O 카드를 카메라에 보여주면 `SUCCESS`, X 카드면 `FAILED`, 그 안에 응답 없으면 `FAILED(무응답 타임아웃)`으로 배송 상태 확정.

**시나리오**
```
로봇 도착 (ARRIVED)
   ↓
로봇이 환자에게 응답 요청 (음성/화면 — 로봇팀 담당)
   ↓
백엔드: 30초간 초당 1프레임 폴링 (VERIFYING 상태)
   ↓
   ├─ "success" 카드 감지 → SUCCESS
   ├─ "failure" 카드 감지 → FAILED "환자가 실패 카드로 응답함"
   ├─ 두 카드 동시 감지 → FAILED "응답 모호 — 재확인 필요"
   └─ 30초 무응답        → FAILED "환자 무응답 (30초 타임아웃)"
```

**MVP 완성 조건**
- [x] 2클래스(`0: failure`, `1: success`) 학습된 YOLO 모델 확보 → `yolo/runs/detect/delivery_train/weights/best.pt`
- [ ] `wait_for_patient_response(frame_source, timeout=30) → YoloOutcome` 폴링 함수 완성
- [ ] `ARRIVED` 상태 진입 시 백엔드가 자동으로 위 함수를 호출하고 SSE로 결과 브로드캐스트
- [ ] 프레임 소스 확정 (방식 A: ROS2가 초당 1회 `POST /image` — §3.5)
- [ ] pytest로 폴링 로직 회귀 방지 (fixture 이미지 + fake frame source)

---

## 2. 오늘까지의 상태 (2026-07-07)

- 백엔드 v1 REST + SSE 구현 완료 (`backend/app/`)
- 프론트가 실백엔드에 SSE로 붙어 end-to-end 시나리오 확인됨
- 상태 전이는 지금 **외부에서 `PATCH /verification`을 curl로 쳐서** 시뮬레이션 중 → YOLO 폴링 루프가 이 자리를 대체함
- 백엔드 pytest 16개 통과 (`backend/tests/`)
- YOLO v1 학습 완료: 2클래스 O/X, val 42장, **mAP@0.5 = 0.977** (`yolo/README.md`)
- ROS2 노드/카메라 하드웨어는 아직 없음 → 방식 A로 확정, 팀원 구현 대기

---

## 3. 작업 단계

각 단계 완료 시 이 문서의 체크박스를 갱신하세요.

### 3.1 데이터셋 준비 ✅ v1 완료

**v1 방식**: 2클래스 O/X 카드. `0: failure`, `1: success` (Roboflow `data.yaml` 순서 기준).

- 원본: `yolo/pinkycare.yolov8/yolo_images/{images,labels}/{train,val}/`
- 총 194장 (train 152 / val 42)
- 전처리: auto-orient, 512×512 stretch
- Augmentation 미적용 (기본 성능 확보 후 필요 시 추가)

**교훈 (다음 버전에 반영)** — 실환경 대응 여지 남아있음:

- 학습 데이터가 데스크 위 카드 자체 위주라, **환자가 카드를 실제로 드는 자세**(기울어짐·손 가림·측면 노출)는 커버 부족
- 조명 3종·상향 각도 촬영이 미포함 → 실제 로봇 카메라에서 성능 확인 필요
- v2 개선 시 조명·각도·손 가림 케이스 추가 촬영 권장

**참고**: 처음 계획했던 4클래스 물품 인식(약/기저귀/혈당측정키트/물티슈) 방식의 촬영 계획은 v1에선 채택하지 않음. 계획 자체는 물품 인식 방식으로 v2를 검토할 때 재활용 가능. 상세는 이 문서의 이전 커밋(2026-07-06 판) 참고.

---

### 3.2 모델 학습 ✅ v1 완료

- 베이스: `yolo11n.pt` (사전학습)
- 학습: `epochs=100, imgsz=640, batch=16, device=0` (RTX 5080 Laptop, 약 2.5분)
- **결과: mAP@0.5 = 0.977** (목표 0.85 대폭 초과)
- 최종 가중치: `yolo/runs/detect/delivery_train/weights/best.pt`

상세 성능 표 · 학습 명령 · 함정(클래스 순서, 카메라 인덱스, path 지정)은 `yolo/README.md` 참고.

**다음 단계에서 필요한 것**: 이 `best.pt`를 백엔드가 소비할 수 있게 `backend/models/pinky_yolo_v1.pt`로 복사 (아래 §3.4 마지막 단계에서 진행).

---

### 3.3 추론 모듈 (백엔드 독립)

파일: `backend/app/services/yolo.py` (신규)

**설계**: 프레임 하나에 대한 판정(`classify_frame`)과, 30초 폴링 루프(`wait_for_patient_response`)를 분리. 폴링 루프는 프레임을 어디서 가져올지 몰라야 하므로 `FrameSource` 프로토콜로 주입.

```python
from typing import NamedTuple, Protocol
import asyncio, time
from app.models.delivery import VerificationResult

CONF_THRESHOLD = 0.6
POLL_INTERVAL_SEC = 1.0
RESPONSE_TIMEOUT_SEC = 30       # 노인 병동 기준

class YoloOutcome(NamedTuple):
    result: VerificationResult
    reason: str | None          # FAILED일 때만 채움

class FrameSource(Protocol):
    async def grab(self) -> bytes | None:
        """최신 프레임 하나. 없으면 None."""

def classify_frame(image: bytes) -> YoloOutcome | None:
    """단일 프레임 판정. 카드 미감지면 None (계속 폴링 신호)."""
    detections = _model().predict(image, conf=CONF_THRESHOLD, verbose=False)
    labels = {d.name for d in detections if d.conf >= CONF_THRESHOLD}
    has_success = "success" in labels
    has_failure = "failure" in labels
    if has_success and has_failure:
        return YoloOutcome(VerificationResult.FAILED, "응답 모호 — 재확인 필요")
    if has_success:
        return YoloOutcome(VerificationResult.SUCCESS, None)
    if has_failure:
        return YoloOutcome(VerificationResult.FAILED, "환자가 실패 카드로 응답함")
    return None                 # 카드 아직 안 보임 → 폴링 지속

async def wait_for_patient_response(
    frame_source: FrameSource,
    timeout_sec: float = RESPONSE_TIMEOUT_SEC,
    poll_interval_sec: float = POLL_INTERVAL_SEC,
) -> YoloOutcome:
    """ARRIVED 이후 환자가 O/X 카드로 응답할 때까지 폴링."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        frame = await frame_source.grab()
        if frame is not None:
            outcome = classify_frame(frame)
            if outcome is not None:
                return outcome
        await asyncio.sleep(poll_interval_sec)
    return YoloOutcome(
        VerificationResult.FAILED,
        f"환자 무응답 ({int(timeout_sec)}초 타임아웃)",
    )
```

작업:
- [ ] 모듈 레벨 `_model()` lazy 로더 (첫 호출 시 `backend/models/pinky_yolo_v1.pt` 로드, 이후 캐시)
- [ ] pytest 추가 (`backend/tests/test_yolo.py`)
  - fixture: 실제 O 카드 사진 1장 + X 카드 사진 1장 (`backend/tests/fixtures/images/`)
  - `FakeFrameSource` — 미리 지정한 프레임을 순서대로 반환 (실제 모델 로드 여부는 CI 여건에 따라 mock)
  - 검증 케이스: 즉시 O → SUCCESS / 즉시 X → FAILED / 타임아웃 → FAILED 무응답 / O+X 동시 → FAILED 모호

**참고**: `expected_item` 파라미터는 v1에서 제거됨. 배송 물품 종류는 UI 표시용 정보로만 남고 판별에는 관여하지 않음. 물품 자체를 확인하는 검증은 v2 과제.

**산출물**: `backend/app/services/yolo.py` + `backend/tests/test_yolo.py`

---

### 3.4 백엔드 자동 트리거 통합

지금은 외부에서 `PATCH /verification`을 쳐야 상태가 넘어감. YOLO 붙이면 **`ARRIVED` 순간 백엔드가 30초 폴링 태스크를 자동 시작**하고, 결과가 나오면 verification 로직을 재사용해 SSE로 브로드캐스트.

**아키텍처 (안 A 확정)**
```
PATCH /robot-status {ARRIVED}
   ↓
  상태 ARRIVED 반영 + SSE 브로드캐스트
   ↓
  asyncio 백그라운드 태스크 시작
   │  wait_for_patient_response(frame_source=CachedImageSource(delivery_id))
   ↓
  30초 안에 outcome 결정 → verification 로직 재사용 (VERIFYING → SUCCESS/FAILED)
```

작업:
- [ ] `PATCH /robot-status`가 `ARRIVED`로 전이하면 백그라운드 태스크로 `wait_for_patient_response()` 실행
- [ ] `FrameSource` 구현체 선정: **`CachedImageSource`** — ROS2가 초당 1회 `POST /image`로 업로드한 최신 프레임을 dict에 캐시했다가 반환 (§3.5 참고)
- [ ] 폴링 완료 시 기존 verification 상태 전이 로직 재사용 (`VERIFYING → SUCCESS/FAILED`, SSE 이벤트 발송, 스트림 종료). 이를 위해 현재 `PATCH /verification` 핸들러 안의 상태 전이 부분을 별도 함수로 분리.
- [ ] YOLO는 pytest에서 DI로 mock 가능하게 서비스 로케이터/파라미터로 주입
- [ ] 기존 pytest 16개 계속 통과해야 함
- [ ] 신규 pytest: `ARRIVED` 후 폴링 태스크가 시작되는지, mock frame source가 SUCCESS/FAILED/타임아웃 outcome을 뱉을 때 SSE에 올바른 이벤트가 나오는지 검증

**주의**
- 백그라운드 태스크 중 중복 `PATCH /verification` 외부 요청이 오면 `409 INVALID_TRANSITION` (이미 VERIFYING/터미널) — 현재 상태 전이 로직으로 자동 방어
- 서버 재시작 시 진행 중인 폴링 태스크는 소실. 인메모리 저장소 자체가 재시작에 취약하므로 v1 범위에선 허용.

**산출물**: `backend/app/api/deliveries.py` 리팩터 + `backend/app/services/frame_source.py` (신규) + 관련 pytest

---

### 3.5 카메라 프레임 소스 (방식 A 확정)

**방식**: ROS2 노드가 로봇 카메라 프레임을 **초당 1회** 백엔드에 HTTP POST. 백엔드는 `delivery_id` 별로 최신 프레임 1장만 캐시했다가 폴링 루프가 꺼내씀.

**엔드포인트 신규**
```
POST /deliveries/{id}/image
Content-Type: multipart/form-data
Body: image (JPEG or PNG)
Response: 204 No Content
```

- 백엔드는 이 요청을 받으면 `frame_cache[delivery_id] = image_bytes` 로 덮어쓰기 (최신 1장만 유지)
- 폴링 루프가 `frame_source.grab()` 호출 시 캐시에서 꺼내옴. 없으면 `None` 반환 (폴링은 다음 tick에서 재시도)
- 배송 terminal 상태 도달 시 캐시 항목 삭제 (메모리 누수 방지)

**호출 시점 (ROS2 팀)**
- `ARRIVED` 도달 후부터 배송 terminal 상태 확인까지, **초당 1회 최신 프레임 업로드**
- 촬영 각도: 사이드 테이블 위 침대 방향. 환자가 손을 뻗어 카드를 카메라에 보여주는 자세를 캡처할 수 있는 위치

**개발용 시뮬레이션**
- ROS2 없이도 테스트 가능하도록 curl로 이미지 업로드 흐름을 스크립트화:
  ```bash
  # ARRIVED 상태 만들고 O 카드 사진을 초당 업로드
  while true; do
    curl -X POST http://localhost:8000/deliveries/$ID/image \
      -F "image=@backend/tests/fixtures/images/success_01.jpg"
    sleep 1
  done
  ```

**산출물**: `POST /deliveries/{id}/image` 엔드포인트 + `frame_source.py` (CachedImageSource + FrameSource Protocol)

---

## 4. 결정 사항 · 미결정 사항

### 확정됨 (2026-07-07)

- **판별 방식**: O/X 카드 2클래스 (v1 완료, `yolo/README.md`)
- **응답 타임아웃**: **30초**
- **무응답 시 처리**: `FAILED` + reason `"환자 무응답 (30초 타임아웃)"`
- **O/X 동시 감지 시**: `FAILED` + reason `"응답 모호 — 재확인 필요"` (안전 우선)
- **프레임 전달**: 방식 A — ROS2가 초당 1회 `POST /deliveries/{id}/image`
- **폴링 간격**: 백엔드 1초
- **confidence 임계값**: 0.6
- **verify 인터페이스**: `expected_item` 파라미터 없음. 배송 물품은 UI 표시용으로만 유지.

### 아직 미결정 (팀 협의)

- **[ ] 카메라 하드웨어 최종 스펙**: 로봇에 어떤 카메라가 붙는가? (RGB 웹캠, RealSense, RPi Cam) → 실제 사진 화질/시야각으로 v1 모델 성능 재검증 필요
- **[ ] 배송 미션 전달**: 백엔드 → ROS2 방향 트리거 (`REQUESTED` → Nav2 goal). SSE 구독안 유력 (`docs/ros2-coordination.md` §1)
- **[ ] 병실 좌표 매핑**: `"101"/"102"/"103"` → Nav2 map coordinate. 팀원의 SLAM/map 결과 필요
- **[ ] 실패 시 재시도 정책**: FAILED 후 "다시 시도" 눌렀을 때 로봇이 다시 나가야 하나, 아니면 현 위치에서 재판정만 하나? (특히 무응답 타임아웃일 때)
- **[ ] 프론트 안내 문구**: `VERIFYING` 상태 라벨을 "환자 응답 대기 중 (남은 시간: XX초)"로 개선할지, 지금 "배송 확인 중"으로 둘지
- **[ ] 카드 물리적 관리**: 침대별 O/X 카드 세트 배포·회수·분실 대응은 병동 운영 이슈로 별도 논의
- **[ ] 환자 무응답 후 흐름**: 간호사에게 별도 알림(푸시/음성 콜)이 필요한가? MVP에선 UI에 FAILED 표시만.

---

## 5. 폴더/파일 참조

- 백엔드 코드: `backend/app/`
  - 상태 전이: `services/transitions.py`
  - 브로드캐스터: `services/broadcaster.py`
  - PATCH 핸들러: `api/deliveries.py`
  - 모델: `models/delivery.py`
  - YOLO 서비스 (신규 예정): `services/yolo.py`, `services/frame_source.py`
- YOLO 학습 산출물: `yolo/README.md`, `yolo/runs/detect/delivery_train/weights/best.pt`
- API 계약: `docs/api-spec.md` §7 (verification 엔드포인트), 신규 `POST /image` 추가 예정
- 프론트가 기대하는 결과 shape: `frontend/src/types/delivery.ts` (`failReason`)
- 테스트 예시: `backend/tests/test_deliveries.py`, `test_sse.py`

---

## 6. 진행 로그

새 단계 시작/종료할 때마다 한 줄씩 남기면 다음 날 픽업이 쉬움.

| 날짜 | 진행 |
|---|---|
| 2026-07-06 | 계획 문서 초안 작성. Phase 1 착수 예정. |
| 2026-07-07 | 접근 방식을 4클래스 물품 인식 → 2클래스 O/X 카드로 전환. v1 학습 완료 (mAP@0.5=0.977). 정책 확정: 타임아웃 30초, 무응답=FAILED, O/X 동시=FAILED, 방식 A 프레임 전달. 다음: §3.3 추론 모듈 + §3.4 백엔드 통합. |
