# 다이어그램

`.excalidraw` 파일은 **손으로 고치지 말고** 옆의 생성 스크립트를 고친 뒤 다시 돌린다.
그래야 코드가 바뀔 때 다이어그램도 같이 갱신할 수 있다.

| 다이어그램 | 생성 스크립트 | 쓰이는 곳 |
| --- | --- | --- |
| `architecture` | `_gen_architecture.py` | 발표자료 시스템 아키텍처, `api-spec.md` §1 |
| `state-transitions` | `_gen_state_transitions.py` | `api-spec.md` §4, README §2.3 |
| `yolo-failure-reasons` | `_gen_yolo_failure_reasons.py` | `yolo-plan.md`, `delivery-scenario.md` §4 |
| `demo-scenario` | `_gen_demo_scenario.py` | `delivery-scenario.md` §5 |
| `delivery-sequence` | `_gen_delivery_sequence.py` | `delivery-scenario.md` (비개발자용) |
| `scenario-unified-flow` | (생성 스크립트 없음) | `delivery-scenario.md` §1 |

## 생성

저장소 루트에서 실행한다.

```bash
python3 docs/diagrams/_gen_architecture.py
```

## 레이아웃 확인

`_preview.py` 가 근사 렌더러로 PNG를 뽑는다. 겹침·좌표 이탈을 잡는 용도이고,
excalidraw의 손그림 질감은 재현하지 않는다.

```bash
python3 docs/diagrams/_preview.py docs/diagrams/architecture.excalidraw /tmp/preview.png
```

## 발표자료·문서용 PNG 내보내기

이 저장소에는 excalidraw → PNG 변환기가 없다. 수동으로 한다.

1. <https://excalidraw.com> 접속
2. 좌상단 메뉴 → **Open** → `.excalidraw` 파일 선택
3. 메뉴 → **Export image** → PNG, 배경 있음, 2x scale
4. `docs/diagrams/<이름>.png` 로 저장

## 코드가 바뀌면 같이 고쳐야 하는 값

다이어그램에 박혀 있는 상수들이다. 코드와 어긋나면 발표에서 그대로 틀린다.

| 값 | 진실의 원천 | 현재 |
| --- | --- | --- |
| 배송 병실 | `backend/app/models/delivery.py` `Room` | 102 · 103 · 104 (101호 = 간호실) |
| 상태 7종 | 같은 파일 `Status` | `AWAITING_NURSE` 포함 |
| conf 임계값 | `backend/app/services/yolo.py` `CONF_THRESHOLD` | 0.35 |
| 확정 프레임 수 | 같은 파일 `MIN_CONFIRMATIONS` | 3 (연속 아님, 누적) |
| 판정 창 | 같은 파일 `WINDOW_SECONDS` | 30초 |
| 간호사 대기 상한 | `backend/app/api/deliveries.py` `_AWAITING_NURSE_TIMEOUT_S` | 300초 |
