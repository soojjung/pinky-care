# PinkyCare — ROS2 담당자와 조율할 항목

정수진(백엔드/프론트/YOLO)과 로봇 자율주행 담당자가 만나기 전에 훑어야 할 미결정 사항 5개.

- **최종 수정일**: 2026-07-06
- **관련 문서**: [`api-spec.md`](./api-spec.md), [`yolo-plan.md`](./yolo-plan.md), [`../README.md`](../README.md)

---

## 배경

현재 `docs/api-spec.md`가 정의한 계약은 **ROS2 → 백엔드 방향의 상태 보고 하나**뿐입니다 (`PATCH /deliveries/{id}/robot-status`). 그 반대 방향과 예외 상황은 정해져 있지 않아, 팀원과 합의해서 스펙에 반영해야 실제 통합이 가능합니다.

---

## 결정해야 할 5가지

각 항목: **질문 → 옵션 → 추천 → 결정 후 각자 할 일** 순.

### 1) 배송 미션을 로봇에 어떻게 전달할지 (가장 중요)

**질문**: 프론트가 `POST /deliveries`로 새 배송을 만들면, ROS2 노드는 이걸 어떻게 알고 Nav2 goal을 트리거하나?

**옵션**
- **A. ROS2가 백엔드 SSE 구독** — 백엔드에 "새 배송 알림" 전역 스트림 추가 (`GET /deliveries/events`). ROS2는 HTTP 클라이언트 하나로 해결.
- **B. 백엔드가 ROS2에 HTTP POST** — ROS2 노드가 HTTP 서버를 열고 `/mission` 같은 엔드포인트 노출.
- **C. 공유 메시지 브로커** (Redis/MQTT) — 오버킬.

**추천**: **A**. 이유: 백엔드가 이미 SSE 서버라서 스트림 하나 추가하는 게 가장 저비용. 실패 시 자동 재연결도 SSE가 처리.

**결정 후 각자 할 일**
- 정수진: `GET /deliveries/events` 전역 스트림 추가 (신규 배송 생성 시 스냅샷 push), `api-spec.md`에 스키마 명시
- 팀원: ROS2 노드에서 SSE 구독 후 `room` 값으로 Nav2 goal 전송

---

### 2) 병실 → Nav2 좌표 매핑

**질문**: `"101"`, `"102"`, `"103"`를 실제 `(x, y, yaw)`로 어디서 변환하나?

**옵션**
- **A. ROS2 노드가 자체 config에 매핑 테이블 보유** — 백엔드는 방 번호만 넘김 (지금 API 그대로).
- **B. 백엔드가 좌표까지 응답에 포함** — DB에 방 좌표 저장.

**추천**: **A**. 이유: 좌표는 SLAM 맵에 종속적이라 로봇/맵 바뀌면 변함. 방 번호만 계약으로 유지하고 좌표는 로봇 쪽 관심사로 캡슐화.

**결정 후 각자 할 일**
- 팀원: SLAM/맵 완성 후 `ros2_ws/config/room_map.yaml` 같은 매핑 파일 작성
- 정수진: 지금 API 그대로 유지 (변경 없음)

---

### 3) 카메라 프레임을 백엔드에 어떻게 넘길지 (YOLO 트리거와 직결)

**질문**: 로봇 도착 시 촬영한 이미지를 백엔드/YOLO가 어떻게 받나?

**옵션**
- **A. ROS2가 `ARRIVED` 시점의 프레임을 백엔드에 HTTP POST** — 새 엔드포인트: `POST /deliveries/{id}/image` (multipart/form-data). YOLO는 백엔드 안에서 실행.
- **B. 백엔드가 RTSP/WebRTC로 로봇 카메라 스트림 구독** — 상시 프레임 grab. 인프라 복잡.
- **C. YOLO가 로봇 쪽에서 실행** — ROS2 노드가 추론 후 `PATCH /verification` 직접 호출. 백엔드는 카메라 안 만짐.

**추천**: 하드웨어에 GPU 있으면 **C**, 없으면 **A**. `yolo-plan.md §3.4`는 A를 가정.

**결정 후 각자 할 일**
- **A 선택 시**
  - 정수진: `POST /deliveries/{id}/image` 엔드포인트 추가, `robot-status ARRIVED` 시 캐시된 이미지로 YOLO 실행
  - 팀원: `ARRIVED` 순간 카메라 프레임을 백엔드에 업로드
- **C 선택 시**
  - 정수진: YOLO 모델/추론 코드를 Python 함수 형태로 팀원에게 제공
  - 팀원: ROS2 노드가 추론 + `PATCH /verification` 콜

---

### 4) 로봇 이상 상황 보고 (현재 API에 없음)

**질문**: Nav2 실패, 장애물, 타임아웃이 나면 어떻게 알리나? 지금 API는 `MOVING`/`ARRIVED`만 있음.

**옵션**
- **A. `robot-status`에 `FAILED` 값 추가** — `PATCH /robot-status {"status":"FAILED","reason":"경로 계획 실패"}`. 백엔드가 delivery FAILED로 전이.
- **B. 별도 엔드포인트** — `PATCH /deliveries/{id}/abort`.

**추천**: **A**. 이유: 인터페이스 하나로 통합, 재사용성↑.

**결정 후 각자 할 일**
- 정수진:
  - `RobotStatus` enum에 `FAILED` 추가
  - 상태 전이 로직 갱신 (`REQUESTED`/`MOVING` 어디서든 `FAILED`로 갈 수 있게)
  - `docs/api-spec.md` 갱신, 관련 pytest 추가
- 팀원: Nav2 goal 실패 콜백에서 이 PATCH 호출, `reason` 문자열 확정

---

### 5) 통합 테스트 환경 (실기 없이도 개발/데모 가능해야)

**질문**: 로봇 하드웨어 없는 상태에서 어떻게 붙여서 테스트하나?

**옵션**
- **A. Gazebo 시뮬레이션** — 팀원이 Gazebo world + Nav2 스택 세팅. 정수진은 백엔드만 로컬에서 띄우면 됨.
- **B. ROS2 노드 mock** — 팀원이 진짜 Nav2 없이 "3초 후 ARRIVED PATCH" 정도만 하는 최소 노드 먼저 제공.

**추천**: 초반엔 **B**, Nav2 붙으면 **A**로 확장.

**결정 후 각자 할 일**
- 팀원: 최소 ROS2 노드 하나 만들어서 슬랙에 실행법 공유
- 정수진: 백엔드 실행법 (`.venv/bin/uvicorn ...`) 공유 (이미 `backend/README.md`에 있음)

---

## 미팅 어젠다 (30분 목표)

1. 위 5개 질문에 각각 옵션 하나씩 픽 — **10분**
2. 카메라 하드웨어 뭐 쓸지, GPU 있는지 확인 (§3 결정과 연결) — **5분**
3. 다음 만남까지 각자 뭐 만들지 명확히 — **5분**
4. 이 문서 하단 "결정 로그" 갱신, `docs/api-spec.md` v2 반영 항목 리스트 — **10분**

---

## 담당 매트릭스 (참고)

결정 후 어느 쪽이 뭘 만드는지 한눈에.

| 항목 | 정수진 (백엔드/YOLO) | 팀원 (ROS2) |
|---|---|---|
| 새 배송 알림 | 전역 SSE 스트림 추가 | SSE 구독 클라이언트 |
| 방→좌표 매핑 | 변경 없음 | `room_map.yaml` 관리 |
| 카메라 프레임 (A안) | `POST /image` 엔드포인트 + 캐시 | ARRIVED 시 프레임 업로드 |
| 카메라 프레임 (C안) | YOLO 함수 제공 | 로봇쪽 추론 + `PATCH /verification` |
| 로봇 이상 상황 | `robot-status FAILED` 지원 | Nav2 실패 콜백에서 PATCH |
| 통합 테스트 | 백엔드 실행법 공유 | mock ROS2 노드 → Gazebo |

---

## 결정 로그

미팅 후 여기에 결정 사항 기록. 코드/스펙 반영은 별도 커밋으로.

| 날짜 | 항목 | 결정 | 스펙 반영 여부 |
|---|---|---|---|
| _(비어있음)_ | | | |
