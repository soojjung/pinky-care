"""Generate yolo-failure-reasons.excalidraw — YOLO 판정 및 실패 사유 분기.

기존 판본은 "5프레임 연속 = 확정" 이라고 적혀 있었으나 둘 다 틀렸다.
실제 코드(backend/app/services/yolo.py):

    CONF_THRESHOLD   = 0.35   # 0.5 에서 실측 기반으로 완화
    POLL_INTERVAL_SEC = 1.0
    WINDOW_SECONDS   = 30.0
    MIN_CONFIRMATIONS = 3     # 연속이 아니라 창 안의 '누적' 감지 프레임 수

판정은 창이 끝나는 순간 decide_window_verdict() 가 한 번에 내린다.
실패 3종은 곧바로 FAILED 가 아니라 AWAITING_NURSE 로 간다.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _excalidraw import rect, diamond, text, arrow, save  # noqa: E402

elements = []

INK = "#1e1e1e"
GRAY = "#495057"
BLUE = "#1971c2"
ORANGE = "#e67700"
GREEN = "#2f9e44"
RED = "#c92a2a"

elements.append(text("title", 40, 20, 900, 32,
                     "< YOLO 판정 및 실패 사유 분기 >", INK, font=24,
                     align="left", valign="top"))

# ── 도착 ──────────────────────────────────────────────────
elements.append(rect("arrived", 40, 200, 160, 70, BLUE, "#d0ebff",
                     bound_ids=["arrived_t"]))
elements.append(text("arrived_t", 50, 210, 140, 50,
                     "도착\n(ARRIVED)", BLUE, container="arrived", font=14))

elements.append(arrow("e_a", 200, 235, [(60, 0)], GRAY))

# ── 30초 창 ───────────────────────────────────────────────
elements.append(rect("window", 260, 180, 260, 110, ORANGE, "#fff3bf",
                     bound_ids=["window_t"]))
elements.append(text("window_t", 270, 190, 240, 90,
                     "YOLO 30초 창\n"
                     "1fps · conf ≥ 0.35\n"
                     "라벨별 누적 3프레임 이상 = 확정",
                     ORANGE, container="window", font=12))

elements.append(arrow("e_b", 520, 235, [(60, 0)], GRAY))

# ── 판정 다이아 ───────────────────────────────────────────
elements.append(diamond("decide", 580, 175, 200, 120, ORANGE, "#ffec99",
                        bound_ids=["decide_t"]))
elements.append(text("decide_t", 600, 200, 160, 70,
                     "창 종료 시\n확정 라벨?", ORANGE,
                     container="decide", font=13))

# ── 결과 4갈래 ────────────────────────────────────────────
# (id, y, 조건, 결과 라벨, 색, bg)
# 조건은 별도 라벨로 두면 화살표와 겹치므로 결과 박스 안에 함께 적는다
OUTCOMES = [
    ("o_suc", 40, "{ success } 만 확정\nSUCCESS", GREEN, "#ebfbee"),
    ("o_x", 150, "{ failure } 만 확정\nAWAITING_NURSE · X_CARD_DETECTED", RED, "#fff5f5"),
    ("o_both", 270, "{ success · failure } 둘 다 확정\nAWAITING_NURSE · AMBIGUOUS_BOTH_CARDS", RED, "#fff5f5"),
    ("o_none", 390, "확정된 라벨 없음\nAWAITING_NURSE · TIMEOUT_NO_CARD", RED, "#fff5f5"),
]
for oid, oy, label, color, bg in OUTCOMES:
    elements.append(rect(oid, 900, oy, 300, 80, color, bg, bound_ids=[f"{oid}_t"]))
    elements.append(text(f"{oid}_t", 910, oy + 10, 280, 60,
                         label, color, container=oid, font=12))
    elements.append(arrow(f"e_{oid}", 780, 235, [(120, oy + 40 - 235)], color))

# ── SUCCESS 는 바로 종료, 실패 3종은 간호사 결정 대기 ────
elements.append(rect("succ_note", 1250, 40, 240, 80, GREEN, "#e6fcf5",
                     stroke_width=1.5, bound_ids=["succ_note_t"], style="dashed"))
elements.append(text("succ_note_t", 1260, 50, 220, 60,
                     "terminal → 즉시 자동 복귀",
                     GREEN, container="succ_note", font=12))

elements.append(rect("fail_note", 1250, 190, 240, 280, RED, "#fff5f5",
                     stroke_width=1.5, bound_ids=["fail_note_t"], style="dashed"))
elements.append(text("fail_note_t", 1262, 202, 216, 256,
                     "실패 3종은 곧바로 FAILED 가\n아니다.\n\n"
                     "AWAITING_NURSE 로 멈춰\n간호사 결정을 기다린다.\n\n"
                     "· 바로 복귀\n"
                     "· 대기해, 내가 갈게\n"
                     "· 5분 무응답 → 자동 확정\n\n"
                     "세 경우 모두 최종 FAILED.",
                     RED, container="fail_note", font=12,
                     align="left", valign="top"))

# ── 주석 ──────────────────────────────────────────────────
elements.append(rect("note", 40, 510, 1160, 92, GRAY, "#f8f9fa",
                     stroke_width=1.5, bound_ids=["note_t"], style="dashed"))
elements.append(text("note_t", 52, 522, 1136, 68,
                     "※ '확정'은 연속 프레임이 아니라 30초 창 안의 누적 감지 횟수 기준이다 "
                     "(MIN_CONFIRMATIONS = 3).\n"
                     "※ 판정은 프레임마다 내리지 않는다. 창이 끝나는 순간 "
                     "decide_window_verdict() 가 한 번에 결정한다.\n"
                     "※ conf 임계값 0.35 — 실측상 O카드 검출은 0.34~0.66, "
                     "카드 없을 때 배경 노이즈는 ≤0.27 이라 그 사이를 택했다.",
                     GRAY, container="note", font=12,
                     align="left", valign="top"))

save(elements, "yolo-failure-reasons.excalidraw")
