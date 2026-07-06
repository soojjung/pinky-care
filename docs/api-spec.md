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
| `item` | enum | `"약"` \| `"주사"` \| `"붕대"` \| `"생리식염수"` |
| `status` | enum | 아래 상태 표 참고 |
| `createdAt` | string (ISO 8601) | 배송 생성 시각 |
| `failReason` | string \| null | `status="FAILED"`일 때만 채움. 그 외 `null` |

### 3.2 상태(`status`) 값

| 상태 | 의미 | 라벨(프론트 표시) |
|---|---|---|
| `REQUESTED` | 배송 요청 접수 | 배송 요청 완료 |
| `MOVING` | 로봇 이동 중 | 로봇 이동 중 |
| `ARRIVED` | 목적지 도착 | 목적지 도착 |
| `VERIFYING` | YOLO 판별 진행 중 | 배송 확인 중 |
| `SUCCESS` | 배송 성공 (terminal) | 배송 완료 |
| `FAILED` | 배송 실패 (terminal) | 배송 실패 |

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
                        │  YOLO: PATCH verification (요청 수신 시 자동 진입)
                        ▼
                  ┌──────────┐
                  │VERIFYING │
                  └──────────┘
                    │        │
        SUCCESS ────┘        └──── FAILED (+ failReason)
       (terminal)              (terminal)
```

정의되지 않은 전이는 `409 Conflict`로 거부.

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

## 7. YOLO 판별용 엔드포인트

### 7.1 배송 판별 결과 전송

```
PATCH /deliveries/{id}/verification
```

YOLO 추론 결과를 백엔드에 전달. terminal 상태로 전이됨.

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
- `409` — 현재 상태가 `ARRIVED`가 아님
- `422` — `result` 값 미허용, 또는 `FAILED`인데 `reason` 누락

**동작 규칙**
- 호출 시점의 상태는 `ARRIVED`여야 함
- 서버는 수신 즉시 `ARRIVED → VERIFYING` 이벤트 1건을 SSE에 발송한 후, 짧은 딜레이(또는 즉시) 뒤 `VERIFYING → 결과` 이벤트를 발송하여 프론트가 "배송 확인 중" 단계를 볼 수 있게 함

**curl**
```bash
curl -X PATCH http://localhost:8000/deliveries/{id}/verification \
  -H 'Content-Type: application/json' \
  -d '{"result":"FAILED","reason":"물품 인식 실패"}'
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
    MED = "약"; INJ = "주사"; BAND = "붕대"; SALINE = "생리식염수"

class Status(str, Enum):
    REQUESTED = "REQUESTED"
    MOVING    = "MOVING"
    ARRIVED   = "ARRIVED"
    VERIFYING = "VERIFYING"
    SUCCESS   = "SUCCESS"
    FAILED    = "FAILED"

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
