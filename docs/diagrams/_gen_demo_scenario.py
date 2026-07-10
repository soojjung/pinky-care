"""Generate demo-scenario.excalidraw — 데모 2회 주행.

기존 판본의 오류:
- 병실 번호가 101호 (101호는 간호실/복귀 지점이다. 배송 대상은 102/103/104)
- "방해물 대응 정책 미결정" 주석 (현재는 정책이 정해졌다 — 구분 없이 동일 취급)
- 실패 시 곧바로 FAILED 로 표기 (실제로는 AWAITING_NURSE 를 거친다)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _excalidraw import rect, text, arrow, save  # noqa: E402

elements = []

INK = "#1e1e1e"
GRAY = "#495057"
GREEN = "#2f9e44"
RED = "#c92a2a"

elements.append(text("title", 40, 20, 900, 32,
                     "< 데모 시나리오 (2회 주행) >", INK, font=24,
                     align="left", valign="top"))

STEP_W, STEP_H, GAP = 190, 84, 34


def run(prefix, y, banner, color, bg, steps):
    elements.append(rect(f"{prefix}_b", 40, y - 46, 1560, 36, color, bg,
                         stroke_width=1.5, bound_ids=[f"{prefix}_b_t"],
                         style="dashed"))
    elements.append(text(f"{prefix}_b_t", 52, y - 42, 1536, 28, banner, color,
                         container=f"{prefix}_b", font=15,
                         align="left", valign="middle"))
    x = 40
    for i, label in enumerate(steps):
        sid = f"{prefix}_{i}"
        elements.append(rect(sid, x, y, STEP_W, STEP_H, color, "#ffffff",
                             stroke_width=1.5, bound_ids=[f"{sid}_t"]))
        elements.append(text(f"{sid}_t", x + 8, y + 8, STEP_W - 16, STEP_H - 16,
                             label, color, container=sid, font=12))
        if i < len(steps) - 1:
            elements.append(arrow(f"{prefix}_a{i}", x + STEP_W, y + STEP_H / 2,
                                  [(GAP, 0)], GRAY, stroke_width=1.5))
        x += STEP_W + GAP


run("a", 120,
    "🅐 1회차 · 102호 배송 성공 (O 카드)", GREEN, "#ebfbee",
    [
        "1. 간호사 요청\n102호 · 물건",
        "2. 자동 출발\n디스패처가 SSE 수신",
        "3. MOVING\n장애물 회피 주행",
        "4. 102호 도착\nARRIVED",
        "5. YOLO 30초 창\nO 카드 3프레임 확정",
        "6. SUCCESS\n자동 판정",
        "7. LCD 웃는 얼굴\n→ 간호실 복귀",
    ])

run("b", 330,
    "🅑 2회차 · 103호 배송 실패 (X 카드) → 간호사 대기 시연", RED, "#fff5f5",
    [
        "1. 간호사 요청\n103호 · 물건",
        "2. 자동 출발\n디스패처가 SSE 수신",
        "3. MOVING\n장애물 회피 주행",
        "4. 103호 도착\nARRIVED",
        "5. YOLO 30초 창\nX 카드 3프레임 확정",
        "6. AWAITING_NURSE\nX_CARD_DETECTED\n+ 간호사 알림",
        "7. “대기해, 내가 갈게”\n→ 함께 복귀",
    ])

# ── 실패 경로 보조 설명 ───────────────────────────────────
elements.append(rect("wait", 1180, 440, 420, 96, RED, "#fff5f5",
                     stroke_width=1.5, bound_ids=["wait_t"], style="dashed"))
elements.append(text("wait_t", 1192, 452, 396, 72,
                     "🕐 병실 그 자리에서 대기 (상한 5분)\n"
                     "· 간호사 도착 → 슬픔 LCD → 함께 복귀\n"
                     "· 5분 무응답 → FAILED 자동 확정 → 혼자 복귀",
                     RED, container="wait", font=12,
                     align="left", valign="top"))

# ── 주석 ──────────────────────────────────────────────────
elements.append(rect("note", 40, 440, 1100, 96, GRAY, "#f8f9fa",
                     stroke_width=1.5, bound_ids=["note_t"], style="dashed"))
elements.append(text("note_t", 52, 452, 1076, 72,
                     "※ 간호실(원점)은 101호다. 배송 대상 병실은 102 · 103 · 104호.\n"
                     "※ 장애물 대응: 벽 · 정적 · 동적을 구분하지 않고 전부 동일한 장애물로 "
                     "취급한다 (Nav2 costmap 기반 회피).\n"
                     "※ 실패는 곧바로 FAILED 가 아니다. AWAITING_NURSE 를 거쳐 "
                     "간호사 결정 또는 5분 타임아웃으로 확정된다.",
                     GRAY, container="note", font=12,
                     align="left", valign="top"))

save(elements, "demo-scenario.excalidraw")
