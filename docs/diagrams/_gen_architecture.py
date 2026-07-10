"""Generate architecture.excalidraw — 시스템 아키텍처 (발표자료 4페이지용).

세 구역이 물리적으로 다른 컴퓨터임을 드러내는 것이 이 그림의 목적이다.
배송 하나의 생애를 ①~⑧ 번호로 따라간다.

핵심 사실 (코드 검증됨):
- YOLO는 별도 서버가 아니라 FastAPI 백엔드 프로세스 안에서 인프로세스로 돈다
- 백엔드 → 로봇 방향의 "명령" 화살표는 존재하지 않는다.
  로봇이 SSE를 구독(②)하고, 결과를 폴링(⑦)한다
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _excalidraw import rect, text, arrow, save  # noqa: E402

elements = []

# ── 색상 ──────────────────────────────────────────────────
INK = "#1e1e1e"
GRAY = "#495057"
BLUE = "#1971c2"      # 간호사 · 브라우저
VIOLET = "#5f3dc4"    # 서버
GREEN = "#087f5b"     # 로봇
SSE = "#e67700"       # SSE 화살표 (점선)
REST = "#1e1e1e"      # REST 화살표 (실선)

# ── 제목 ──────────────────────────────────────────────────
elements.append(text("title", 40, 20, 900, 34,
                     "PinkyCare — 시스템 아키텍처",
                     INK, font=26, align="left", valign="top"))
elements.append(text("subtitle", 40, 58, 1000, 22,
                     "세 대의 서로 다른 컴퓨터가 REST와 SSE로 통신한다. "
                     "배송 하나의 생애를 ①~⑧ 순서로 따라가면 된다.",
                     GRAY, font=14, align="left", valign="top"))

# ── 구역 3개 ──────────────────────────────────────────────
ZONES = [
    ("zA", 40, 120, 300, 300, BLUE, "#f1f8ff", "🧑‍⚕️ 간호사 · 브라우저"),
    ("zB", 420, 120, 340, 400, VIOLET, "#f8f6ff", "🖥️ 서버 · 맥북"),
    ("zC", 840, 120, 380, 560, GREEN, "#f2fdf9", "🤖 로봇 · 라즈베리파이"),
]
for zid, zx, zy, zw, zh, color, bg, label in ZONES:
    elements.append(rect(zid, zx, zy, zw, zh, color, bg,
                         stroke_width=1.5, style="dashed"))
    elements.append(text(f"{zid}_t", zx + 14, zy + 12, zw - 28, 24,
                         label, color, font=15, align="left", valign="top"))

# ── 구역 A: 웹 UI ─────────────────────────────────────────
elements.append(rect("webui", 70, 200, 240, 90, BLUE, "#d0ebff",
                     bound_ids=["webui_t"]))
elements.append(text("webui_t", 80, 210, 220, 70,
                     "React + TS 웹 UI\n배송 요청 · 상태 확인",
                     BLUE, container="webui", font=14))

# ── 구역 B: FastAPI 백엔드 (YOLO 중첩) ────────────────────
elements.append(rect("backend", 450, 180, 280, 250, VIOLET, "#e5dbff"))
elements.append(text("backend_t", 464, 194, 260, 24,
                     "FastAPI 백엔드", VIOLET, font=15,
                     align="left", valign="top"))

elements.append(rect("yolo", 475, 240, 230, 70, VIOLET, "#ffffff",
                     stroke_width=1.5, bound_ids=["yolo_t"]))
elements.append(text("yolo_t", 485, 250, 210, 50,
                     "YOLOv8 판정\n(인프로세스 — 별도 서버 아님)",
                     VIOLET, container="yolo", font=12))

elements.append(rect("state", 475, 330, 230, 70, VIOLET, "#ffffff",
                     stroke_width=1.5, bound_ids=["state_t"]))
elements.append(text("state_t", 485, 340, 210, 50,
                     "배송 상태 관리\n(7단계 · 전이 검증)",
                     VIOLET, container="state", font=12))

# ── 구역 C: 로봇 3층 ──────────────────────────────────────
ROBOT = [
    ("disp", 180, "미션 디스패처\nSSE 상시 구독"),
    ("mission", 320, "junction_1.py 미션 노드\n도착 판정 · 업로드 · 복귀"),
    ("nav", 460, "ROS2 Nav2 · LCD · 카메라\n점-대-점 주행 · 표정 · 촬영"),
]
for rid, ry, label in ROBOT:
    elements.append(rect(rid, 870, ry, 320, 80, GREEN, "#c3fae8",
                         bound_ids=[f"{rid}_t"]))
    elements.append(text(f"{rid}_t", 880, ry + 10, 300, 60,
                         label, GREEN, container=rid, font=13))

# 로봇 내부 세로 화살표
elements.append(arrow("a_disp_mission", 1030, 260, [(0, 60)], GREEN))
elements.append(text("a_disp_mission_t", 1040, 275, 140, 18,
                     "② 자동 실행", GREEN, font=12, align="left"))
elements.append(arrow("a_mission_nav", 1030, 400, [(0, 60)], GREEN))

# ── 화살표: A ↔ B ────────────────────────────────────────
# ① 요청 (REST)
elements.append(arrow("a1", 310, 215, [(140, 0)], REST))
elements.append(text("a1_t", 330, 193, 100, 18, "① 배송 요청",
                     REST, font=12, align="center"))
# ⑥ 상태 브로드캐스트 (SSE)
elements.append(arrow("a6", 450, 275, [(-140, 0)], SSE, style="dashed"))
elements.append(text("a6_t", 330, 283, 100, 18, "⑥ 상태 알림",
                     SSE, font=12, align="center"))

# ── 화살표: B ↔ C ────────────────────────────────────────
# ② 새 배송 SSE (백엔드 → 디스패처)
elements.append(arrow("a2", 730, 200, [(140, 0)], SSE, style="dashed"))
elements.append(text("a2_t", 750, 178, 100, 18, "② 새 배송",
                     SSE, font=12, align="center"))
# ③ 이동 상태 보고 · ④ 카메라 프레임 · ⑦ 결과 폴링 — 모두 미션 노드에서 나간다
elements.append(arrow("a3", 870, 335, [(-140, 0)], REST))
elements.append(text("a3_t", 752, 315, 106, 18, "③ 상태 보고",
                     REST, font=12, align="center"))
elements.append(arrow("a4", 870, 372, [(-140, 0)], REST))
elements.append(text("a4_t", 752, 352, 106, 18, "④ 프레임",
                     REST, font=12, align="center"))
elements.append(arrow("a7", 870, 409, [(-140, 0)], REST))
elements.append(text("a7_t", 752, 389, 106, 18, "⑦ 결과 폴링",
                     REST, font=12, align="center"))

# ── ⑤ YOLO 판정 노트 (서버 구역 안) ──────────────────────
elements.append(rect("n5", 450, 442, 280, 66, VIOLET, "#f3f0ff",
                     stroke_width=1.5, bound_ids=["n5_t"], style="dashed"))
elements.append(text("n5_t", 458, 450, 264, 50,
                     "⑤ 30초 창 누적 판정\n"
                     "3프레임 이상 → SUCCESS / AWAITING_NURSE",
                     VIOLET, container="n5", font=11))

# ── ⑧ 복귀 노트 ──────────────────────────────────────────
elements.append(rect("n8", 870, 570, 320, 76, GREEN, "#e6fcf5",
                     stroke_width=1.5, bound_ids=["n8_t"], style="dashed"))
elements.append(text("n8_t", 880, 580, 300, 56,
                     "⑧ LCD 표정 표시 후\n간호실 자동 복귀",
                     GREEN, container="n8", font=12))

# ── 범례 ──────────────────────────────────────────────────
elements.append(rect("lg", 40, 450, 300, 230, GRAY, "#f8f9fa",
                     stroke_width=1.5, bound_ids=["lg_t"]))
elements.append(text("lg_t", 52, 462, 276, 206,
                     "범례\n\n"
                     "──▶  REST (요청 · 보고 · 폴링)\n"
                     "╌╌▶  SSE (서버가 밀어주는 알림)\n\n"
                     "① 배송 요청\n"
                     "② 새 배송 알림 → 주행 자동 실행\n"
                     "③ 이동 상태 보고 (MOVING · ARRIVED)\n"
                     "④ 카메라 프레임 (30초간 초당 1장)\n"
                     "⑤ YOLO 30초 창 누적 판정\n"
                     "⑥ 상태 실시간 브로드캐스트\n"
                     "⑦ 결과 1초 간격 폴링\n"
                     "⑧ LCD 표정 후 자동 복귀",
                     GRAY, container="lg", font=12,
                     align="left", valign="top"))

# ── 핵심 메시지 (전체 하단) ──────────────────────────────
elements.append(rect("key", 420, 710, 800, 58, "#c92a2a", "#fff5f5",
                     stroke_width=1.5, bound_ids=["key_t"]))
elements.append(text("key_t", 430, 718, 780, 42,
                     "⚠ 백엔드에서 로봇으로 가는 명령 화살표는 없다. "
                     "로봇이 스스로 구독(②)하고 스스로 폴링(⑦)한다.",
                     "#c92a2a", container="key", font=13))

save(elements, "architecture.excalidraw")
