# PinkyCare — Backend

FastAPI 기반 백엔드. 배송 요청 관리, 상태 전이, SSE 브로드캐스트, YOLO 판별 결과 수신.

## 상태

**v1 REST + SSE 구현 완료.** ROS2 노드 · YOLO 파이프라인 연동은 계약(API)만 준비됐고 실제 클라이언트 붙이는 건 별도 작업. 상세 계약은 [`../docs/api-spec.md`](../docs/api-spec.md).

구현된 엔드포인트:

| 메서드 | 경로 | 용도 |
|---|---|---|
| `POST` | `/deliveries` | 신규 배송 생성 (`REQUESTED`로 시작) |
| `GET` | `/deliveries/{id}` | 단건 조회 |
| `PATCH` | `/deliveries/{id}/robot-status` | ROS2 → 로봇 이동 상태 (`MOVING`/`ARRIVED`) |
| `PATCH` | `/deliveries/{id}/verification` | YOLO → 판별 결과 (`SUCCESS`/`FAILED`) |
| `GET` | `/deliveries/{id}/events` | SSE 스트림 (프론트용) |
| `GET` | `/health` | 헬스체크 |

- 상태 저장: 인메모리 dict (재시작 시 소실). DB는 아직 미도입.
- SSE: 연결 즉시 스냅샷 1건 발송, terminal 상태에서 스트림 자동 종료, 30초 keepalive.
- 정의되지 않은 상태 전이는 `409 INVALID_TRANSITION`으로 거부.
- 응답/에러 필드는 camelCase (`createdAt`, `failReason` 등).

## 스택

- Python 3.11+
- FastAPI · Pydantic v2
- `sse-starlette` (SSE)
- `uvicorn[standard]` (ASGI 서버)

## 폴더 구조

```
backend/
├── app/
│   ├── main.py                # FastAPI 앱, CORS, 공통 에러 봉투
│   ├── api/
│   │   └── deliveries.py      # POST/GET/PATCH/SSE 라우터
│   ├── models/
│   │   └── delivery.py        # Enum + Pydantic 모델 (camelCase alias)
│   └── services/
│       ├── store.py           # 인메모리 저장소
│       ├── transitions.py     # 허용 전이 매핑
│       └── broadcaster.py     # per-id asyncio.Queue 구독자
├── tests/                     # pytest (REST + SSE)
├── pyproject.toml
└── README.md
```

## 시작하기

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/uvicorn app.main:app --reload   # http://localhost:8000
```

- Swagger UI: `http://localhost:8000/docs`
- CORS: dev에서 `http://localhost:5173` 허용

## 테스트

```bash
.venv/bin/pip install -e ".[test]"   # 최초 1회
.venv/bin/pytest                     # REST + SSE 커버 (16 tests)
```

`tests/test_deliveries.py`가 REST 엔드포인트와 에러 봉투를, `tests/test_sse.py`가 SSE 이벤트 시퀀스(`VERIFYING` 노출 포함)와 터미널 재연결 종료를 검증합니다.

## 수동 시나리오 (curl)

```bash
# 1) 배송 생성
CREATE=$(curl -s -X POST http://localhost:8000/deliveries \
  -H 'Content-Type: application/json' -d '{"room":"101","item":"약"}')
ID=$(echo "$CREATE" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 2) SSE 구독 (별도 터미널)
curl -N http://localhost:8000/deliveries/$ID/events

# 3) 로봇 이동
curl -X PATCH http://localhost:8000/deliveries/$ID/robot-status \
  -H 'Content-Type: application/json' -d '{"status":"MOVING"}'
curl -X PATCH http://localhost:8000/deliveries/$ID/robot-status \
  -H 'Content-Type: application/json' -d '{"status":"ARRIVED"}'

# 4) YOLO 판별
curl -X PATCH http://localhost:8000/deliveries/$ID/verification \
  -H 'Content-Type: application/json' -d '{"result":"SUCCESS"}'
```

## 관련 문서

- API 명세서: [`../docs/api-spec.md`](../docs/api-spec.md)
- 시스템 아키텍처: [`../README.md`](../README.md)
