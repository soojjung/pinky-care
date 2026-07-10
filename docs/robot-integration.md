# PinkyCare — 로봇 통합 가이드

로봇 담당자가 시연 전까지 손봐야 할 항목을 한 문서에 정리한 것.
백엔드는 이번에 YOLO 자동 판정 파이프라인을 통합했고, 그 결과 로봇 측
`junction_1.py` 도 함께 바뀌어야 한다.

- **버전**: v1 (2026-07-08)
- **관련 문서**: [`delivery-scenario.md`](./delivery-scenario.md) · [`api-spec.md`](./api-spec.md)
- **시연 세팅**: 백엔드 = 시연자 맥북 / 로봇 = Pinky Pro (별개 머신, 같은 Wi-Fi)
- **Wi-Fi SSID**: `pinkycare`

---

## 1. 큰 그림 — 무엇이 바뀌었나

**이전(v1)** — 백엔드와 로봇이 같은 머신에 있다고 가정. 배송 검증 확정 시
백엔드가 `subprocess.Popen(python3 junction_1.py --state 복귀)` 로 복귀 프로세스를 직접 띄웠음.

**현재(v2)** — 백엔드가 맥북에 있고 로봇은 별개 라즈베리파이. 위의 subprocess 방식이
작동하지 않으므로 아래로 바뀐다:

```
[로봇: junction_1.py]                    [맥북: FastAPI + YOLO]
  Nav2로 병실 이동
  PATCH /robot-status {MOVING}      ─→
                                          MOVING 반영 · SSE push
  PATCH /robot-status {ARRIVED}     ─→
                                          ARRIVED 반영 + 30초 YOLO 창 자동 시작
  30초 동안 초당 1회 POST /image    ─→
                                          창 종료 → SUCCESS or AWAITING_NURSE 확정
  ★ 30초 후 shutdown 하지 말고
    GET /deliveries/{id} 폴링 시작  ─→
                                          최신 status 응답
  status 보고 LCD 표시 · 복귀 결정
  Nav2 goal (0,0) 복귀
```

**핵심 변화 3가지**
1. 백엔드가 subprocess 를 안 띄운다 → 로봇이 스스로 결과를 확인해야 함 (**폴링**)
2. 로봇은 30초 업로드 끝나도 프로세스를 종료하지 말고 폴링 루프로 진입
3. 새 상태 `AWAITING_NURSE` 가 추가됨 → 폴링 중 이 상태를 만나면 계속 대기

---

## 2. 로봇 측 변경 사항

### 2.1 `BACKEND_URL` 을 환경변수화

지금 `junction_1.py:23` 에 `BACKEND_URL = "http://localhost:8000"` 하드코딩. 로봇에서
`localhost`는 로봇 자신을 가리켜서 맥북 백엔드에 못 붙는다.

**변경**
```python
import os
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
```

**실행 시**
```bash
BACKEND_URL=http://<맥북-IP>:8000 python3 junction_1.py --room-number 102 --delivery-id <id>
```

맥북 IP 확인은 시연 당일 맥북에서 `ipconfig getifaddr en0` 로.
가능하면 공유기에서 맥북 MAC 주소에 IP 예약을 걸어두면 매번 안 바뀐다.

### 2.2 `junction_1.py` 폴링 리팩터

**지금(문제)**
```python
def camera_callback(self, msg):
    ...
    if current_time - self.yolo_start_time > self.yolo_duration:
        self.destroy_subscription(self.camera_sub)
        cv2.destroyAllWindows()
        rclpy.shutdown()     # ← 여기서 프로세스가 죽어버림
        return
```

30초 업로드 끝나면 `rclpy.shutdown()` 으로 죽고, 그 뒤 백엔드 subprocess 로 새
프로세스가 뜬다는 가정이었음. 이제 그 subprocess 가 없으니 대신 폴링으로 이어가야 한다.

**변경 (개념)**
```python
def camera_callback(self, msg):
    ...
    if current_time - self.yolo_start_time > self.yolo_duration:
        self.destroy_subscription(self.camera_sub)
        cv2.destroyAllWindows()
        self._start_result_polling()    # ← shutdown 대신 폴링 진입
        return

def _start_result_polling(self):
    """30초 창 종료 후 백엔드 배송 상태를 확인해서 후속 조치."""
    import time
    POLL_INTERVAL = 1.0      # 초
    MAX_WAIT_SEC = 600       # 안전장치: 10분 넘어가면 실패 처리
    started = time.time()

    while True:
        try:
            res = requests.get(
                f"{BACKEND_URL}/deliveries/{self.delivery_id}", timeout=3
            ).json()
            status = res.get("status")
        except requests.RequestException as e:
            self.get_logger().warn(f"상태 조회 실패, 재시도: {e}")
            time.sleep(POLL_INTERVAL)
            continue

        if status == "SUCCESS":
            self.get_logger().info("배송 성공 확인 — 복귀 시작")
            self._show_emotion_and_return(_SUCCESS_STYLE)
            return

        if status == "FAILED":
            self.get_logger().info("배송 실패 확인 — 복귀 시작")
            self._show_emotion_and_return(_FAILURE_STYLE)
            return

        # AWAITING_NURSE 이면 간호사가 결정할 때까지 계속 대기
        if time.time() - started > MAX_WAIT_SEC:
            self.get_logger().error("대기 시간 초과 (10분) — 강제 복귀")
            self._show_emotion_and_return(_FAILURE_STYLE)
            return

        time.sleep(POLL_INTERVAL)

def _show_emotion_and_return(self, style):
    """LCD 표정 표시 후 간호실 복귀."""
    self.show_emotion_face_with_style(style)
    self._send_return_goal()   # Nav2 goal (0,0) 전송
```

기존 `show_emotion_face(self)` 는 `--state 복귀` 모드 진입 후에 배송 상태를
한 번 조회해서 표정을 정했다. 폴링 루프 안에서 상태를 이미 알고 있으니
스타일을 인자로 받는 형태로 리팩터하면 재사용 편함.

### 2.3 상태별 로봇 동작 요약

| 백엔드 status | 로봇이 할 일 |
|---|---|
| `MOVING` | Nav2 이동 중 (자체 처리) |
| `ARRIVED` | 카메라 30초 업로드 · 끝나면 폴링 진입 |
| `VERIFYING` | 폴링 응답으로 만날 수 있음 (0.3초 지연 상태) — 무시하고 계속 폴링 |
| `AWAITING_NURSE` | 병실 자리에 정지한 채 폴링 계속. LCD 옵션: clear or "확인 대기 중" 문구 |
| `SUCCESS` | 웃음 LCD → 자동 복귀 |
| `FAILED` | 슬픔 LCD → 자동 복귀 |

`AWAITING_NURSE` 에서는 간호사가 `POST /nurse-return-command` 를 누르면 백엔드가
`FAILED` 로 전이한다. 5분 안에 아무 응답이 없으면 백엔드가 스스로 `FAILED` 로
확정한다(무한 대기 방지). 로봇 입장에선 두 경우가 구분되지 않는다 — 폴링 결과가
`FAILED` 로 바뀌면 즉시 슬픔 표정 + 복귀만 실행하면 된다.

> 로봇 쪽 `MAX_POLL_SEC = 600`(10분)은 백엔드가 응답하지 않을 때만 걸리는 안전망이다.
> 정상 흐름에서는 백엔드의 5분 상한이 항상 먼저 걸린다.

### 2.4 정리 완료 — `--state 복귀` 경로 제거

v1 의 `_trigger_return_process()` (백엔드 → `subprocess.Popen(junction_1.py --state 복귀)`)
와 그 진입점을 양쪽에서 삭제했다. 근거:

- `_RETURN_SCRIPT` 는 `~/pinky_pro/...` 경로라 백엔드가 도는 머신(맥북)에 없다.
  `Popen` 은 `python3` 를 찾으니 **예외를 던지지 않고**, 자식이 종료코드 2로 조용히
  죽는다. 백엔드는 복귀를 트리거했다고 믿지만 아무 일도 일어나지 않았고,
  `wait()` 도 안 해서 좀비 프로세스만 쌓였다.
- 경로가 맞았더라도 `junction_1.py` 는 Nav2 액션 서버·LCD·카메라를 잡는 ROS2
  노드라 **로봇 위에서** 돌아야 한다. 백엔드 머신에서 띄우는 건 의미가 없다.
- 복귀는 이미 로봇이 스스로 한다 — `_poll_tick()` 이 terminal 상태를 보면
  `_begin_return()` 으로 표정 표시 + 간호실 Nav2 goal 을 실행한다.
- 로봇 쪽에서도 `--state 복귀` 를 부르는 곳이 없었다. `mission_dispatcher.py` 는
  `--room-number` / `--delivery-id` 만 넘긴다.

함께 삭제된 것: `junction_1.py` 의 `--state` 인자와, 그 진입점에서만 쓰이던
`show_emotion_face()`. 백엔드의 `import subprocess` · `_RETURN_SCRIPT` 상수.

---

## 2.5 미션 자동 트리거 — `mission_dispatcher.py` (신규)

프론트에서 배송이 생성되면 로봇이 자동으로 출발하도록, 백엔드에 전역 스트림을
추가하고 로봇 쪽에 디스패처를 두었다.

- **백엔드**: `GET /deliveries/events` — 새 배송이 생기면 `event: delivery` 로 스냅샷 push
- **로봇**: `mission_dispatcher.py` — 위 스트림을 구독하다가 배송이 들어오면
  `junction_1.py --room-number <room> --delivery-id <id>` 를 자동 실행

한 번에 하나의 미션만 순차 처리하고(주행 중이면 끝날 때까지 대기), SSE 가 끊기면
자동 재접속한다. 로봇에서 **상시 실행**해 두는 진입점:

```bash
# 로봇(라즈베리파이)에서, junction_1.py 와 같은 디렉터리에 함께 배포
BACKEND_URL=http://<노트북-IP>:8000 python3 mission_dispatcher.py
# 예: 로봇 AP(192.168.4.1) 에 노트북이 붙어 192.168.4.19 를 받은 경우
#     BACKEND_URL=http://192.168.4.19:8000 python3 mission_dispatcher.py
```

이제 시연 흐름은: **프론트에서 방·물품 선택 → 배송 생성 → 디스패처가 감지 →
`junction_1.py` 자동 실행** (수동으로 CLI 를 칠 필요 없음).

---

## 3. 백엔드 API 참조 (로봇이 부르는 것들)

전체 스펙: [`api-spec.md`](./api-spec.md)

| 시점 | 메서드 · 경로 | 페이로드 | 응답 |
|---|---|---|---|
| 새 배송 구독 (디스패처, 상시) | `GET /deliveries/events` | — | SSE `event: delivery` 스냅샷 스트림 |
| 이동 시작 | `PATCH /deliveries/{id}/robot-status` | `{"status":"MOVING"}` | 200 Delivery |
| 병실 도착 | `PATCH /deliveries/{id}/robot-status` | `{"status":"ARRIVED"}` | 200 Delivery |
| 카메라 프레임 (초당 1회, 30초) | `POST /deliveries/{id}/image` (multipart) | `image=<JPEG>` | 204 No Content |
| 결과 폴링 (1초 간격) | `GET /deliveries/{id}` | — | 200 Delivery (`status` 필드 확인) |

**중요** — `POST /image` 는 30초 창 안에만 의미 있음. 창이 끝난 뒤에도 백엔드가
받긴 하지만 판정에 안 쓰인다. 30초 지난 시점부터는 프레임 업로드 중단하고
결과 폴링으로 전환.

---

## 4. 시연 전 통신 확인 (5분)

로봇에서 아래 순서로 통신 확인:

```bash
# 1. Wi-Fi 접속 (pinkycare)
# 2. 맥북 IP 확인 (맥북에서: ipconfig getifaddr en0)
# 3. 로봇에서 ping
ping <맥북-IP>          # 응답 오면 OK

# 4. 백엔드 헬스체크 (dummy id로 404 나오면 통신 OK)
curl http://<맥북-IP>:8000/deliveries/dummy
# → 404 NOT_FOUND (엔드포인트 정상, 배송이 없어서 404)

# 5. 실 배송 하나 만들어 흐름 검증
BACKEND=http://<맥북-IP>:8000
ID=$(curl -s -X POST $BACKEND/deliveries \
  -H 'Content-Type: application/json' \
  -d '{"room":"102","item":"약"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')

curl -X PATCH $BACKEND/deliveries/$ID/robot-status \
  -H 'Content-Type: application/json' -d '{"status":"MOVING"}'
curl -X PATCH $BACKEND/deliveries/$ID/robot-status \
  -H 'Content-Type: application/json' -d '{"status":"ARRIVED"}'

# 6. 30초 뒤 상태 확인 (카메라 프레임 안 올렸으니 TIMEOUT_NO_CARD)
sleep 32
curl $BACKEND/deliveries/$ID
# → status: "AWAITING_NURSE", failReason: "TIMEOUT_NO_CARD"
```

여기까지 통신되면 데모 전체 흐름 문제 없음.

---

## 5. 아직 정해야 할 것

로봇 담당자와 결정할 사항:

1. **`AWAITING_NURSE` 동안 LCD 표시** — clear 유지? 문구 표시? 슬픈 얼굴 미리?
2. **"함께 복귀" 실질 방식** — 지금은 Nav2 goal (0,0) 자율주행. 간호사는 옆에서
   걸음 맞추기? 팔로우 모드? (시연 최소안: 자율주행 그대로)
3. **폴링 상한(안전장치)** — 위 예시는 10분. 이 시간 넘어가면 어떻게? (강제 복귀? 알림만?)
4. **카메라 토픽 이름** — 지금 `/image_raw` 로 구독. 실 로봇에서 이 이름 맞는지
5. **카메라 프레임 해상도** — 너무 크면 Wi-Fi 업로드 지연 → JPEG 압축 품질 조정 여지
6. **LCD GIF 파일 실제 경로** — 지금 `/home/user/images/{happy,sad}_face.gif`
   하드코딩. 실제 배포 경로 확정
7. **장애물 대응 정책** — 이동 중 사람·물건 만났을 때 (`delivery-scenario.md §6` 미결정)

---

## 6. 체크리스트 (요약)

- [x] 미션 자동 트리거: 백엔드 `GET /deliveries/events` + 로봇 `mission_dispatcher.py`
- [ ] 로봇에서 `mission_dispatcher.py` 상시 실행 (BACKEND_URL 지정)
- [ ] `BACKEND_URL` 환경변수화 (`os.environ.get`)
- [ ] `camera_callback` 30초 종료 시 `rclpy.shutdown()` 제거 → 폴링 진입
- [ ] `_start_result_polling()` 함수 신설 (SUCCESS / FAILED / AWAITING_NURSE 분기)
- [ ] `_show_emotion_and_return()` 로 LCD + Nav2 goal (0,0) 통합
- [ ] 폴링 안전장치 (10분 상한 등)
- [ ] Wi-Fi `pinkycare` 접속 + 맥북 IP 확인 스크립트 작성
- [ ] 시연 전 §4 통신 확인 완료

---

## 7. 문의

- 백엔드 스펙: [`api-spec.md`](./api-spec.md)
- 전체 시나리오: [`delivery-scenario.md`](./delivery-scenario.md)
- 코드 위치: `ros2_ws/src/pinky_pro/pinky_navigation/scripts/junction_1.py`
