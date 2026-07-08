# PinkyCare — 배송 API 명세서

병원 간호 로봇(Pinky) 배송 시스템(**PinkyCare**)의 백엔드 API 명세서입니다. 프론트엔드 · ROS2(자율주행) · YOLO(배송 판별) 세 개의 클라이언트가 이 API를 통해 통신합니다.

- **버전**: v1
- **최종 수정일**: 2026-07-06
- **관련 저장소**: `pinky-care` (모노레포)
- **프론트 타입 정의(진실의 원천)**: `frontend/src/types/delivery.ts`

---

## 1. 시스템 개요

```
[간호사 웹 UI] ─── REST / SSE ───► [FastAPI 백엔드] ◄─── REST ─── [ROS2 노드 · YOLO 파이프라인]
```

- 프론트엔드는 배송을 요청하고 상태를 실시간으로 받아 표시함
- ROS2 노드는 로봇의 이동 상태를 백엔드에 알림
- YOLO 파이프라인은 도착 후 배송 성공/실패 판별 결과를 백엔드에 알림
- 백엔드는 상태 변경을 SSE로 프론트에 브로드캐스트함

---

## 2. 공통 규칙

| 항목 | 값 |
|---|---|
| Base URL (dev) | `http://localhost:8000` |
| Content-Type | `application/json` (SSE만 `text/event-stream`) |
| 필드 네이밍 | **camelCase** (프론트 타입과 일치) |
| 타임스탬프 | ISO 8601 UTC (예: `2026-07-06T14:23:00.123Z`) |
| ID 포맷 | UUIDv4 문자열, 서버에서 생성 |
| 인증 | 현 버전 미적용 |
| CORS | dev 단계에서 `http://localhost:5173` 허용 |

---

## 3. 데이터 모델

### 3.1 Delivery (응답 공통 모델)

```json
{
  "id": "a7f3e0c8-2b9a-4d4e-9c1f-3a5b8e2d7f10",
  "room": "101",
  "item": "약",
  "status": "MOVING",
  "createdAt": "2026-07-06T14:23:00.123Z",
  "failReason": null
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | string (UUID) | 배송 식별자 |
| `room` | enum | `"101"` \| `"102"` \| `"103"` |
| `item` | enum | `"약"` \| `"기저귀"` \| `"혈당측정키트"` \| `"물티슈"` |
| `status` | enum | 아래 상태 표 참고 |
| `createdAt` | string (ISO 8601) | 배송 생성 시각 |
| `failReason` | string \| null | `status="FAILED"`일 때만 채움. 그 외 `null` |

### 3.2 상태(`status`) 값

| 상태 | 의미 | 라벨(프론트 표시) |
|---|---|---|
| `REQUESTED` | 배송 요청 접수 | 배송 요청 완료 |
| `MOVING` | 로봇 이동 중 | 로봇 이동 중 |
| `ARRIVED` | 목적지 도착 | 목적지 도착 |
| `VERIFYING` | 판정 결과 반영 중 (0.3초 지연) | 배송 확인 중 |
| `AWAITING_NURSE` | YOLO가 실패 판정 후 간호사 결정 대기 (v3 추가) | 확인 필요 (실패 알림) |
| `SUCCESS` | 배송 성공 (terminal) | 배송 완료 |
| `FAILED` | 배송 실패 (terminal) | 배송 실패 |

### 3.3 실패 사유(`failReason`) 값 — YOLO 자동 판정

| 코드 | 조건 |
|---|---|
| `X_CARD_DETECTED` | 30초 창 안에 실패(X) 카드만 확정됨 |
| `TIMEOUT_NO_CARD` | 30초 창 안에 어떤 카드도 확정되지 않음 |
| `AMBIGUOUS_BOTH_CARDS` | O와 X 모두 확정됨(모호) |

간호사가 자유 텍스트로 `reason`을 덧붙이면 그 문자열이 우선 저장됨.

---

## 4. 상태 전이 다이어그램

```
                    (POST /deliveries)
                            │
                            ▼
                      ┌──────────┐
                      │ REQUESTED│
                      └──────────┘
                            │  ROS2: PATCH robot-status {MOVING}
                            ▼
                      ┌──────────┐
                      │  MOVING  │
                      └──────────┘
                            │  ROS2: PATCH robot-status {ARRIVED}
                            ▼
                      ┌──────────┐
                      │ ARRIVED  │
                      └──────────┘
                            │  ARRIVED 진입 즉시 백엔드가 30초 YOLO 창 자동 시작
                            ▼
                      ┌──────────┐
                      │VERIFYING │
                      └──────────┘
                       │           │
        SUCCESS  ──────┘           └──────  AWAITING_NURSE  (+ failReason)
       (terminal, 자동 복귀)                  │
                                              │  간호사: POST /nurse-return-command
                                              ▼
                                          ┌────────┐
                                          │ FAILED │  (terminal, + 복귀 스크립트 트리거)
                                          └────────┘
```

- **`AWAITING_NURSE` 는 YOLO 자동 파이프라인에서만 나오는 상태.** 레거시
  `PATCH /verification {result:FAILED}` 는 이 상태를 건너뛰고 바로 `FAILED`로 감.
- 정의되지 않은 전이는 `409 Conflict`로 거부.

---

## 5. 프론트엔드용 엔드포인트

### 5.1 신규 배송 생성

```
POST /deliveries
```

**Request Body**
```json
{ "room": "101", "item": "약" }
```

**Response `201 Created`**
```json
{
  "id": "a7f3e0c8-...",
  "room": "101",
  "item": "약",
  "status": "REQUESTED",
  "createdAt": "2026-07-06T14:23:00.123Z",
  "failReason": null
}
```

**에러**
- `422` — `room`/`item`이 허용값이 아님

**curl**
```bash
curl -X POST http://localhost:8000/deliveries \
  -H 'Content-Type: application/json' \
  -d '{"room":"101","item":"약"}'
```

---

### 5.2 단건 조회

```
GET /deliveries/{id}
```

**Response `200 OK`** — `Delivery` 스키마

**에러**
- `404` — 존재하지 않는 id

**curl**
```bash
curl http://localhost:8000/deliveries/a7f3e0c8-...
```

---

### 5.3 상태 SSE 스트림

```
GET /deliveries/{id}/events
```

**Response Headers**
```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

**Event 형식**

이벤트 이름: `status`. `data`는 `Delivery` 스냅샷 전체(부분 업데이트 X).

```
event: status
data: {"id":"a7f3...","room":"101","item":"약","status":"MOVING","createdAt":"...","failReason":null}

event: status
data: {"id":"a7f3...","room":"101","item":"약","status":"ARRIVED","createdAt":"...","failReason":null}

event: status
data: {"id":"a7f3...","room":"101","item":"약","status":"SUCCESS","createdAt":"...","failReason":null}
```

**동작 규칙**
- 연결 즉시 현재 스냅샷 1건 발송 (프론트는 별도 `GET` 불필요)
- 매 이벤트 payload는 부분 업데이트가 아니라 Delivery 전체
- terminal 상태(`SUCCESS` / `FAILED`) 이벤트 발송 후 서버가 스트림 종료
- 이미 terminal인 id에 연결하면 현재 스냅샷 1건 보내고 즉시 종료
- 30초마다 `: keepalive\n\n` 코멘트 프레임 발송 (프록시 idle timeout 방지)

**에러**
- `404` — 존재하지 않는 id (스트림 시작 전 반환)

**클라이언트 예시 (JS)**
```js
const es = new EventSource(`/deliveries/${id}/events`);
es.addEventListener("status", (e) => {
  const delivery = JSON.parse(e.data);
  // 화면 업데이트
});
```

---

## 6. ROS2용 엔드포인트

### 6.1 로봇 상태 갱신

```
PATCH /deliveries/{id}/robot-status
```

로봇 이동 상태를 백엔드에 알림. `MOVING`, `ARRIVED` 두 값만 허용.

**Request Body**
```json
{ "status": "MOVING" }
```
또는
```json
{ "status": "ARRIVED" }
```

**Response `200 OK`** — 갱신된 `Delivery`. SSE 구독자에게 브로드캐스트됨.

**에러**
- `404` — 존재하지 않는 id
- `409` — 유효하지 않은 상태 전이 (예: `SUCCESS` 이후 `MOVING`)
- `422` — `status` 값 미허용

**호출 시점 가이드**
- `REQUESTED` → `MOVING`: Nav2 목표 지점으로 이동 시작 직후
- `MOVING` → `ARRIVED`: Nav2 goal reached 콜백 발생 시

**curl**
```bash
curl -X PATCH http://localhost:8000/deliveries/{id}/robot-status \
  -H 'Content-Type: application/json' \
  -d '{"status":"ARRIVED"}'
```

---

## 7. YOLO · 카메라 · 간호사 응답 엔드포인트

### 7.1 카메라 프레임 업로드 (ROS2 → 백엔드)

```
POST /deliveries/{id}/image
Content-Type: multipart/form-data
Body: image=<JPEG or PNG>
```

로봇이 `ARRIVED` 도달 후 30초 동안 초당 1회 카메라 프레임을 올리는 엔드포인트.
백엔드는 배송별로 **최신 1장**만 캐시하고, 백그라운드 폴링 루프가 여기서 프레임을
꺼내 YOLO에 넘긴다.

**Response** — `204 No Content`

**에러**
- `404` — 존재하지 않는 배송 id
- `422` — 이미지 body 가 비어 있음

**동작 규칙**
- 배송 상태와 무관하게 수락 (ARRIVED 이전/이후 프레임은 그냥 캐시에 덮어씀)
- 배송이 terminal 상태로 도달하면 캐시 자동 삭제
- ROS2 팀 참고: 카메라 콜백에서 `cv2.imencode('.jpg', frame)` 후 requests로 POST

**curl**
```bash
curl -X POST http://localhost:8000/deliveries/{id}/image \
  -F "image=@frame.jpg"
```

### 7.2 자동 판정 파이프라인 (내부 동작)

`ARRIVED` 상태로 전이하는 순간 백엔드가 백그라운드 태스크로 30초 폴링을 시작.

1. 매 초 캐시된 최신 프레임을 꺼내 YOLO 모델에 넘김
2. `conf ≥ 0.5` 인 라벨을 창(30초) 안에 누적
3. `MIN_CONFIRMATIONS(=3)` 이상 감지된 라벨만 "확정" 처리
4. 30초 창 종료 시 규칙에 따라 최종 outcome 결정:
   - `success` 확정만 → **SUCCESS**
   - `failure` 확정만 → **FAILED / X_CARD_DETECTED**
   - 둘 다 확정 → **FAILED / AMBIGUOUS_BOTH_CARDS**
   - 아무것도 확정 안 됨 → **FAILED / TIMEOUT_NO_CARD**

성공: 즉시 `SUCCESS`로 전이하고 자동 복귀 트리거.
실패: `AWAITING_NURSE`로 전이 후 §7.4 명령을 기다림 (자동 복귀 안 함).

### 7.3 배송 판별 결과 전송 (레거시 · 수동 override)

```
PATCH /deliveries/{id}/verification
```

YOLO 자동 파이프라인 이전에 쓰던 수동 경로. 지금은 데모용 override 나 시연 리허설
용도로만 사용. `ARRIVED` 상태에서만 허용되며, 실패도 곧바로 `FAILED`로 전이한다
(자동 파이프라인과 달리 `AWAITING_NURSE`를 건너뜀).

**Request Body**

성공:
```json
{ "result": "SUCCESS" }
```

실패:
```json
{ "result": "FAILED", "reason": "물품 인식 실패" }
```

**Response `200 OK`** — 갱신된 `Delivery`. SSE 스트림에 이벤트 발송 후 종료.

**에러**
- `404` — 존재하지 않는 id
- `409` — 현재 상태가 `ARRIVED`가 아님 (자동 파이프라인이 이미 넘어간 후 등)
- `422` — `result` 값 미허용, 또는 `FAILED`인데 `reason` 누락

### 7.4 간호사 복귀 명령 (실패 후 결정)

```
POST /deliveries/{id}/nurse-return-command
```

실패 알림을 본 간호사가 "바로 복귀" 또는 "대기해, 내가 갈게" → 도착 후
"복귀 보내기"를 누를 때 호출. 상태를 `AWAITING_NURSE → FAILED`로 전이하고
복귀 스크립트를 트리거한다.

**Request Body**
```json
{ "choice": "IMMEDIATE" | "AFTER_ARRIVAL", "reason": "환자 부재" }
```

- `choice` (선택, 기본 `IMMEDIATE`) — 감사 로그용
  - `IMMEDIATE`: "바로 복귀" 버튼 → 간호사가 병실에 안 감
  - `AFTER_ARRIVAL`: "대기해, 내가 갈게" 후 도착해서 "복귀 보내기" 누름
- `reason` (선택) — YOLO 사유 위에 간호사 자유 텍스트를 덧씀

**Response `200 OK`** — 갱신된 `Delivery` (status=FAILED)

**에러**
- `404` — 존재하지 않는 id
- `409` — 현재 상태가 `AWAITING_NURSE` 가 아님
- `422` — `choice` 값 미허용

**curl**
```bash
curl -X POST http://localhost:8000/deliveries/{id}/nurse-return-command \
  -H 'Content-Type: application/json' \
  -d '{"choice":"AFTER_ARRIVAL","reason":"환자 부재"}'
```

---

## 8. 에러 응답 형식

전 엔드포인트 공통.

```json
{
  "error": {
    "code": "INVALID_TRANSITION",
    "message": "Cannot transition from SUCCESS to MOVING"
  }
}
```

| HTTP | code 예시 | 상황 |
|---|---|---|
| `404` | `NOT_FOUND` | 존재하지 않는 배송 id |
| `409` | `INVALID_TRANSITION` | 허용되지 않은 상태 전이 |
| `422` | `VALIDATION_ERROR` | 요청 body 검증 실패 |
| `500` | `INTERNAL_ERROR` | 서버 내부 오류 |

---

## 9. 부록 — Pydantic 스키마 힌트

응답을 자동으로 camelCase 로 만들려면 Pydantic v2에서 아래처럼:

```python
from enum import Enum
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

class Base(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

class Room(str, Enum):
    R101 = "101"; R102 = "102"; R103 = "103"

class Item(str, Enum):
    MED = "약"; DIAPER = "기저귀"; GLUCOSE = "혈당측정키트"; WIPE = "물티슈"

class Status(str, Enum):
    REQUESTED       = "REQUESTED"
    MOVING          = "MOVING"
    ARRIVED         = "ARRIVED"
    VERIFYING       = "VERIFYING"
    AWAITING_NURSE  = "AWAITING_NURSE"   # v3
    SUCCESS         = "SUCCESS"
    FAILED          = "FAILED"

class DeliveryOut(Base):
    id: str
    room: Room
    item: Item
    status: Status
    created_at: str            # 응답에선 createdAt
    fail_reason: str | None = None  # 응답에선 failReason
```

SSE 구현은 `sse-starlette`의 `EventSourceResponse` 사용을 권장.

---

## 10. 변경 이력

| 날짜 | 버전 | 내용 |
|---|---|---|
| 2026-07-06 | v1 | 초안 작성 |
| 2026-07-08 | v2 | YOLO 자동 파이프라인 통합: `POST /image`, ARRIVED 자동 트리거, `AWAITING_NURSE` 상태, `POST /nurse-return-command`, `failReason` enum 3종 (X_CARD_DETECTED · TIMEOUT_NO_CARD · AMBIGUOUS_BOTH_CARDS). 레거시 `PATCH /verification` 은 유지. |
