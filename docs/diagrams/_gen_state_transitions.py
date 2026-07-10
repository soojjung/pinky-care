"""Generate state-transitions.excalidraw — 배송 상태 전이.

기존 판본에는 AWAITING_NURSE 가 없었다 (VERIFYING → SUCCESS/FAILED 로 끝남).
실제 코드(backend/app/api/deliveries.py)의 전이:

    REQUESTED → MOVING → ARRIVED → VERIFYING ─┬─ SUCCESS
                                              └─ AWAITING_NURSE → FAILED

AWAITING_NURSE 에서 나가는 길은 FAILED 뿐이다. 간호사 응답이 없으면
5분(_AWAITING_NURSE_TIMEOUT_S = 300) 뒤 백엔드가 스스로 확정한다.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _excalidraw import ellipse, rect, text, arrow, save  # noqa: E402

elements = []

INK = "#1e1e1e"
GRAY = "#495057"
BLUE = "#1971c2"
ORANGE = "#e67700"
GREEN = "#2f9e44"
RED = "#c92a2a"

elements.append(text("title", 40, 20, 800, 32,
                     "< 배송 상태 전이 >", INK, font=24,
                     align="left", valign="top"))

# ── 상태 노드 ─────────────────────────────────────────────
# (id, x, y, label, stroke, bg)
W, H = 170, 62
NODES = [
    ("s_req", 60, 120, "REQUESTED", BLUE, "#d0ebff"),
    ("s_mov", 280, 120, "MOVING", BLUE, "#d0ebff"),
    ("s_arr", 500, 120, "ARRIVED", BLUE, "#d0ebff"),
    ("s_ver", 720, 120, "VERIFYING", ORANGE, "#fff3bf"),
    ("s_suc", 990, 40, "SUCCESS", GREEN, "#ebfbee"),
    ("s_awa", 960, 210, "AWAITING_NURSE", RED, "#fff5f5"),
    ("s_fai", 990, 330, "FAILED", RED, "#ffe3e3"),
]
for nid, nx, ny, label, stroke, bg in NODES:
    w = 210 if nid == "s_awa" else W
    elements.append(ellipse(nid, nx, ny, w, H, stroke, bg,
                            bound_ids=[f"{nid}_t"]))
    elements.append(text(f"{nid}_t", nx + 8, ny + 8, w - 16, H - 16,
                         label, stroke, container=nid, font=14))

# ── 전이 화살표 ───────────────────────────────────────────
def edge(eid, x, y, points, label, color, lx, ly, style="solid", lw=190):
    elements.append(arrow(eid, x, y, points, color, style=style))
    elements.append(text(f"{eid}_t", lx, ly, lw, 18, label, color,
                         font=12, align="center"))


edge("e1", 230, 151, [(50, 0)], "ROS2", GRAY, 230, 126, lw=50)
edge("e2", 450, 151, [(50, 0)], "ROS2", GRAY, 450, 126, lw=50)
edge("e3", 670, 151, [(50, 0)], "백엔드 자동", GRAY, 645, 126, lw=100)

# VERIFYING → SUCCESS (위로) — 라벨은 화살표 아래·SUCCESS 왼쪽 빈 공간에
edge("e4", 890, 138, [(100, -60)], "", GREEN, 0, 0)
elements.append(text("e4_t1", 830, 60, 160, 18, "성공 판정 (O 확정)",
                     GREEN, font=12, align="center"))
# VERIFYING → AWAITING_NURSE (아래로) — 라벨은 화살표 왼쪽에
edge("e5", 890, 165, [(70, 70)], "", RED, 0, 0)
elements.append(text("e5_t1", 770, 205, 110, 18, "실패 판정",
                     RED, font=12, align="center"))

# AWAITING_NURSE → FAILED
edge("e6", 1070, 272, [(0, 58)], "", RED, 0, 0)
elements.append(text("e6_t1", 1090, 280, 340, 46,
                     "간호사 결정 (바로 복귀 / 함께 복귀)\n"
                     "또는 5분 무응답 → 백엔드 자동 확정",
                     RED, font=12, align="left", valign="top"))

# ── 시작 화살표 ───────────────────────────────────────────
elements.append(arrow("e0", -80, 151, [(140, 0)], GRAY))
elements.append(text("e0_t", -90, 126, 160, 18, "POST /deliveries",
                     GRAY, font=12, align="center"))

# ── 주석 ──────────────────────────────────────────────────
elements.append(rect("note", 60, 300, 760, 110, GRAY, "#f8f9fa",
                     stroke_width=1.5, bound_ids=["note_t"], style="dashed"))
elements.append(text("note_t", 72, 312, 736, 86,
                     "※ terminal 상태는 SUCCESS · FAILED 둘 뿐이다. "
                     "두 경우 모두 로봇이 자동 복귀한다.\n"
                     "※ AWAITING_NURSE 는 terminal 이 아니므로 SSE 스트림이 닫히지 않는다.\n"
                     "※ AWAITING_NURSE 에서 나가는 길은 FAILED 뿐이다 — "
                     "간호사가 어떤 선택을 하든 배송은 실패로 기록된다.\n"
                     "※ 정의되지 않은 전이는 409 INVALID_TRANSITION 으로 거부된다.",
                     GRAY, container="note", font=12,
                     align="left", valign="top"))

save(elements, "state-transitions.excalidraw")
