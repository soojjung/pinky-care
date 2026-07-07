# PinkyCare

병원 간호 로봇 **Pinky**의 배송 관리 시스템. 간호사가 웹에서 배송할 병실과 물품을 선택하면, 로봇이 자율주행으로 이동하고 도착지에서 YOLO가 배송 성공/실패를 판별합니다.

이 저장소는 **모노레포**로, 프론트엔드 · 백엔드 · ROS2 워크스페이스를 함께 관리합니다.

- **현재 단계**: 프론트엔드 MVP + FastAPI 백엔드(REST + SSE) 완료, 프론트가 실백엔드에 붙어 end-to-end 동작. ROS2/YOLO는 계약(API)만 준비된 상태.
- **역할 분담**
  - 프론트엔드 · YOLO 판별: 정수진
  - 로봇 자율주행 (Nav2, ROS2): 팀원 담당

---

## 1. 폴더 구조 (모노레포)

```
pinky-care/
├── frontend/              # React + TS + Vite (간호사용 웹 UI)
├── backend/               # FastAPI (배송 관리 + SSE + YOLO 판별)
├── yolo/                  # YOLO 촬영·학습 워크플로 (노트북/스크립트)
├── ros2_ws/               # ROS2 워크스페이스 (자율주행 노드)
├── docs/                  # 팀 공용 문서 (API 명세서 등)
│   └── api-spec.md
└── README.md              # (이 파일)
```

각 서브 프로젝트의 상세 설명은 하위 README 참고:

- [`frontend/README.md`](frontend/README.md)
- [`backend/README.md`](backend/README.md)
- [`ros2_ws/README.md`](ros2_ws/README.md)

---

## 2. 전체 시스템 아키텍처

### 2.1 컴포넌트 구성

```
┌─────────────────────────────────────────────────────────────────┐
│                        PinkyCare 시스템                          │
│                                                                 │
│  ┌──────────────┐        ┌──────────────┐                       │
│  │   간호사      │        │  ROS2 노드    │                       │
│  │   웹 UI      │        │  (Nav2)      │                       │
│  │  frontend/   │        │  ros2_ws/    │                       │
│  └──────┬───────┘        └──────┬───────┘                       │
│         │                        │                              │
│    REST │ SSE               REST │                              │
│         │                        │                              │
│         ▼                        ▼                              │
│  ┌──────────────────────────────────────┐                       │
│  │           FastAPI 백엔드              │                       │
│  │           backend/                    │                       │
│  │  · 배송 요청/조회                     │                       │
│  │  · 상태 전이 관리                     │                       │
│  │  · SSE 브로드캐스트                   │                       │
│  └──────┬───────────────────────┬───────┘                       │
│         │                       │                               │
│         │                  REST │                               │
│         │                       ▼                               │
│         │              ┌──────────────┐                         │
│         │              │  YOLO 판별    │                         │
│         │              │  파이프라인   │                         │
│         │              │ backend/ 내부 │                         │
│         │              └──────────────┘                         │
│         │                                                       │
│         ▼                                                       │
│    (배송 상태 실시간 표시)                                       │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 배송 시나리오 (End-to-End 흐름)

```
1. 간호사가 UI에서 병실(101호)과 물품(약)을 선택하고 "배송 시작" 클릭
       │
       ▼
2. UI → FastAPI:  POST /deliveries {room, item}
       │  ← 201  {id, status: "REQUESTED", ...}
       ▼
3. UI가 진행 화면으로 이동하고 SSE 스트림 연결
       UI → FastAPI:  GET /deliveries/{id}/events  (SSE 열림)
       │
       ▼
4. FastAPI가 ROS2에 배송 미션 전달 (구현 방식은 팀 협의)
       │
       ▼
5. ROS2 로봇이 이동 시작
       ROS2 → FastAPI:  PATCH /deliveries/{id}/robot-status  {"status":"MOVING"}
       │  → SSE로 UI에 전파 → 화면이 "로봇 이동 중"으로 갱신
       ▼
6. 로봇이 목적지 도착
       ROS2 → FastAPI:  PATCH /deliveries/{id}/robot-status  {"status":"ARRIVED"}
       │  → SSE로 UI에 전파 → 화면이 "목적지 도착"으로 갱신
       ▼
7. YOLO가 카메라 이미지로 배송 판별
       YOLO → FastAPI:  PATCH /deliveries/{id}/verification  {"result":"SUCCESS"}
       │  → FastAPI가 VERIFYING → SUCCESS/FAILED 순으로 SSE 이벤트 발송 후 스트림 종료
       ▼
8. UI가 terminal 상태 감지 → 결과 화면으로 자동 이동
       · 성공: ✓ 아이콘 + "배송 완료"
       · 실패: ✕ 아이콘 + 사유 + "다시 시도" 버튼
```

### 2.3 상태 전이

```
REQUESTED ──► MOVING ──► ARRIVED ──► VERIFYING ──┬─► SUCCESS  (terminal)
                                                 └─► FAILED   (terminal)
```

정의되지 않은 전이는 백엔드가 `409 Conflict`로 거부.

### 2.4 화면 흐름 (frontend)

```
┌───────────────┐  배송 시작  ┌───────────────────┐  terminal  ┌─────────────────┐
│   MainPage    │ ───────────► │ DeliveryProgress  │ ─────────► │ DeliveryResult  │
│  (병실/물품)   │              │      Page         │            │      Page       │
└───────────────┘              └───────────────────┘            └─────────────────┘
        ▲                                                                │
        │                                재시도(FAILED) / 홈으로          │
        └────────────────────────────────────────────────────────────────┘
```

---

## 3. 개발 (현재 시점)

```bash
# 백엔드 (터미널 1)
cd backend
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/uvicorn app.main:app --reload   # http://localhost:8000

# 프론트엔드 (터미널 2)
cd frontend
npm install
npm run dev        # http://localhost:5173

# ROS2 (팀원 담당)
cd ros2_ws
# 예정: colcon build && source install/setup.bash
```

로봇/YOLO 없이도 상태 진행을 시뮬레이션하려면 `curl`로 PATCH 두 개(`/robot-status`, `/verification`)를 순서대로 쳐주면 됩니다. 예시는 [`backend/README.md`](backend/README.md) 참고.

---

## 4. 관련 문서

- **API 명세서**: [`docs/api-spec.md`](docs/api-spec.md) — FastAPI 엔드포인트, 데이터 모델, SSE 스키마
- **YOLO 작업 계획**: [`docs/yolo-plan.md`](docs/yolo-plan.md) — 데이터셋 → 학습 → 백엔드 통합 로드맵
- **ROS2 팀원과 조율 항목**: [`docs/ros2-coordination.md`](docs/ros2-coordination.md) — 인터페이스/좌표/카메라/이상상황 결정
- **프론트 타입 정의(계약서)**: [`frontend/src/types/delivery.ts`](frontend/src/types/delivery.ts)

---

## 5. 로드맵

- [x] Vite + React + TS + Tailwind + Router 세팅
- [x] 타입/상수/서비스 인터페이스 정의
- [x] Mock 서비스 구현
- [x] 메인/진행/결과 3개 화면 구현
- [x] 배송 상태 실시간 반영 훅
- [x] 백엔드 API 명세서 작성
- [x] 모노레포 구조로 전환
- [x] FastAPI 백엔드 구현 (REST + SSE, 인메모리 저장)
- [x] `apiDeliveryService`로 프론트 스왑 (SSE + REST)
- [ ] YOLO 판별 파이프라인 연동
- [ ] ROS2 노드 ↔ 백엔드 연동 (팀원 담당)
- [ ] 저장소 영속화 (SQLite 등)
- [ ] 백엔드 pytest / 프론트 통합 테스트
- [ ] E2E 통합 테스트
