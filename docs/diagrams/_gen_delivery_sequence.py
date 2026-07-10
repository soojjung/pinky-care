"""Generate delivery-sequence.excalidraw — 비개발자용 흐름도.

4개 액터: 간호사 · 화면 · 관제 시스템 · 로봇.
성공/실패 분기, 실패 시 간호사 선택(복귀/대기), 5분 타임아웃 포함.

주의 — 로봇 제어의 방향:
관제 시스템은 로봇에게 명령하지 않는다. 로봇이 새 배송 알림을 구독해
스스로 출발하고, 결과를 1초 간격으로 폴링해 스스로 복귀한다.
(기존 판본은 "이 방으로 이동해줘" / "복귀해줘" 처럼 관제가 지시하는 것으로
그려져 있었으나, 이는 이후 버린 설계다.)
"""
import json
import os

UPDATED = 1773161826574
elements = []
_idx = [0]
_seed = [1000]


def nidx():
    _idx[0] += 1
    return f"a{_idx[0]:03d}"


def nseed():
    _seed[0] += 1
    return _seed[0]


def rect(id_, x, y, w, h, stroke, bg, stroke_width=2, bound_ids=None,
         roundness=True, style="solid"):
    return {
        "id": id_, "type": "rectangle",
        "x": x, "y": y, "width": w, "height": h,
        "angle": 0,
        "strokeColor": stroke, "backgroundColor": bg,
        "fillStyle": "solid", "strokeWidth": stroke_width, "strokeStyle": style,
        "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None,
        "index": nidx(),
        "roundness": {"type": 3} if roundness else None,
        "seed": nseed(), "version": 1, "versionNonce": nseed(),
        "isDeleted": False,
        "boundElements": [{"type": "text", "id": t} for t in (bound_ids or [])],
        "updated": UPDATED, "link": None, "locked": False,
    }


def text(id_, x, y, w, h, txt, stroke, container=None, font=14,
         align="center", valign="middle", bg="transparent"):
    return {
        "id": id_, "type": "text",
        "x": x, "y": y, "width": w, "height": h,
        "angle": 0,
        "strokeColor": stroke, "backgroundColor": bg,
        "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None,
        "index": nidx(),
        "roundness": None,
        "seed": nseed(), "version": 1, "versionNonce": nseed(),
        "isDeleted": False,
        "boundElements": [],
        "updated": UPDATED, "link": None, "locked": False,
        "text": txt, "fontSize": font, "fontFamily": 5,
        "textAlign": align, "verticalAlign": valign,
        "containerId": container,
        "originalText": txt, "autoResize": True, "lineHeight": 1.25,
    }


def line(id_, x, y, dx, dy, stroke, style="dashed", stroke_width=1.5):
    return {
        "id": id_, "type": "line",
        "x": x, "y": y, "width": abs(dx) or 1, "height": abs(dy) or 1,
        "angle": 0,
        "strokeColor": stroke, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": stroke_width, "strokeStyle": style,
        "roughness": 0, "opacity": 100,
        "groupIds": [], "frameId": None,
        "index": nidx(),
        "roundness": {"type": 2},
        "seed": nseed(), "version": 1, "versionNonce": nseed(),
        "isDeleted": False,
        "boundElements": [],
        "updated": UPDATED, "link": None, "locked": False,
        "points": [[0, 0], [dx, dy]],
        "lastCommittedPoint": None,
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": None,
    }


def arrow(id_, x, y, dx, dy, stroke, stroke_width=1.75, style="solid",
          bound_ids=None, end_head="arrow"):
    return {
        "id": id_, "type": "arrow",
        "x": x, "y": y, "width": abs(dx) or 1, "height": abs(dy) or 1,
        "angle": 0,
        "strokeColor": stroke, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": stroke_width, "strokeStyle": style,
        "roughness": 0, "opacity": 100,
        "groupIds": [], "frameId": None,
        "index": nidx(),
        "roundness": {"type": 2},
        "seed": nseed(), "version": 1, "versionNonce": nseed(),
        "isDeleted": False,
        "boundElements": [{"type": "text", "id": t} for t in (bound_ids or [])],
        "updated": UPDATED, "link": None, "locked": False,
        "points": [[0, 0], [dx, dy]],
        "lastCommittedPoint": None,
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": end_head,
        "elbowed": False,
    }


# ── 액터 4명 ───────────────────────────────────────────────
X = {"N1": 150, "N2": 460, "N3": 780, "N4": 1100}
actors = [
    ("N1", 50, 200, "🧑‍⚕️ 간호사", "#1971c2", "#d0ebff"),
    ("N2", 360, 200, "💻 화면 (웹 UI)", "#495057", "#e9ecef"),
    ("N3", 670, 220, "🧠 관제 시스템\n(요청 관리 + 카드 인식)", "#5f3dc4", "#e5dbff"),
    ("N4", 1000, 200, "🤖 로봇", "#087f5b", "#c3fae8"),
]
for key, rx, rw, label, stroke, bg in actors:
    rid, tid = f"r_{key}", f"t_{key}"
    elements.append(rect(rid, rx, 40, rw, 80, stroke, bg,
                         stroke_width=2, bound_ids=[tid]))
    elements.append(text(tid, rx + 10, 50, rw - 20, 60, label, stroke,
                         container=rid, font=15))

# ── Lifeline ───────────────────────────────────────────────
LIFELINE_TOP = 125
LIFELINE_BOT = 1720
for key, cx in X.items():
    elements.append(line(f"L_{key}", cx, LIFELINE_TOP, 0,
                         LIFELINE_BOT - LIFELINE_TOP, "#adb5bd", style="dashed"))

# ── 공통 메시지 (요청 → 도착 → 알림) ─────────────────────
common_messages = [
    (170, "N1", "N2", "방·물품 선택 후 “요청” 버튼", "solid"),
    (215, "N2", "N3", "배송 요청 전달", "solid"),
    (260, "N3", "N2", "“요청됨” 상태 표시", "dashed"),
    (325, "N3", "N4", "새 배송 알림 (로봇이 구독 중)", "dashed"),
    (370, "N4", "N3", "받았어요 — 이동 시작합니다", "solid"),
    (415, "N3", "N2", "“이동 중” 상태 표시", "dashed"),
    (475, "N4", "N3", "병실에 도착했어요", "solid"),
    (520, "N3", "N2", "“도착 · 확인 중” 상태 표시", "dashed"),
    (565, "N4", "N3", "카메라 영상 전송 (30초)", "solid"),
    # NOTE 605-715: 카드 확인 창
    (745, "N3", "N2", "결과 전달 (성공 or 실패 사유)", "dashed"),
    (790, "N2", "N1", "🔔 알림 팝업 (성공 or 실패)", "solid"),
]

# ── 성공 분기 ─────────────────────────────────────────────
success_messages = [
    (890, "N4", "N3", "결과 나왔나요? (1초마다 물어봄)", "solid"),
    (925, "N3", "N4", "성공으로 확정됐어요", "dashed"),
]

# ── 실패 분기: 알림 + 선택 + 대기 + 종료 ──────────────────
failure_messages = [
    (1145, "N1", "N2", "“바로 복귀” 또는 “대기해, 내가 갈게” 선택", "solid"),
    (1190, "N2", "N3", "간호사의 선택 전달", "solid"),
    (1235, "N4", "N3", "결과 나왔나요? (1초마다 물어봄)", "solid"),
    (1270, "N3", "N4", "아직 간호사 결정 대기 중이에요", "dashed"),
    # NOTE 1300-1390: 병실 그 자리에서 대기 (최대 5분)
    (1420, "N1", "N2", "간호사 도착 → “복귀 보내기” 버튼", "solid"),
    (1455, "N2", "N3", "복귀 지시 전달", "solid"),
    (1490, "N3", "N4", "실패로 확정됐어요 (또는 5분 초과 자동 확정)", "dashed"),
]

# ── 마지막 공통: 간호실 도착 ──────────────────────────────
final_messages = [
    (1660, "N4", "N3", "간호실 도착 · 다음 배송 대기", "solid"),
]


def add_messages(msg_list, override_color=None):
    for i, (y, fk, tk, lbl, style) in enumerate(msg_list):
        aid, tid = f"arr_{y}_{fk}_{tk}", f"arrt_{y}_{fk}_{tk}"
        sx, ex = X[fk], X[tk]
        dx = ex - sx
        if override_color:
            color = override_color
        else:
            color = "#5f3dc4" if style == "dashed" else "#1e1e1e"
        elements.append(arrow(aid, sx, y, dx, 0, color,
                              stroke_width=1.75, style=style, bound_ids=[tid]))
        approx_w = max(len(lbl) * 9, 100)
        mid_x = sx + dx / 2
        elements.append(text(tid, mid_x - approx_w / 2, y - 12, approx_w, 18,
                             lbl, color, container=aid, font=13,
                             align="center", valign="middle", bg="#ffffff"))


add_messages(common_messages)
add_messages(success_messages, override_color="#2f9e44")
add_messages(failure_messages, override_color="#c92a2a")
add_messages(final_messages)

# ── ② 로봇이 스스로 출발한다는 점을 명시 ─────────────────
disp_id, disp_tid = "disp_note", "disp_note_t"
elements.append(rect(disp_id, X["N4"] - 130, 395, 260, 56,
                     "#087f5b", "#e6fcf5",
                     stroke_width=1.5, bound_ids=[disp_tid]))
elements.append(text(disp_tid, X["N4"] - 120, 403, 240, 40,
                     "🤖 로봇의 미션 디스패처가\n주행을 자동 시작 (사람 개입 0)",
                     "#087f5b", container=disp_id, font=12))

# ── ③ 카드 확인 30초 창 (관제 시스템 lifeline 위) ─────────
note_id, note_tid = "card_note", "card_note_t"
elements.append(rect(note_id, 670, 605, 220, 110, "#5f3dc4", "#f3f0ff",
                     stroke_width=2, bound_ids=[note_tid]))
elements.append(text(note_tid, 680, 615, 200, 90,
                     "🎯 카드 확인 창 (30초)\n\n"
                     "매 프레임 O/X 자동 인식\n창 종료 시 결과 확정",
                     "#5f3dc4", container=note_id, font=13,
                     align="center", valign="middle"))

# ── 성공 배경 배너 ────────────────────────────────────────
success_banner_id, success_banner_t = "succ_banner", "succ_banner_t"
elements.append(rect(success_banner_id, 340, 850, 900, 130, "#2f9e44", "#ebfbee",
                     stroke_width=1.5, bound_ids=[success_banner_t], style="dashed"))
elements.append(text(success_banner_t, 350, 855, 880, 20,
                     "🟢 성공 시 — 자동 복귀", "#2f9e44",
                     container=success_banner_id, font=14,
                     align="left", valign="top"))

# 로봇 성공 self-notes
succ_self = [
    (960, "LCD “배송 성공!” 3초"),
    (992, "웃음 얼굴 → 스스로 복귀"),
]
for i, (y, txt_) in enumerate(succ_self):
    rid, tid = f"succ_self_{i}", f"succ_self_t_{i}"
    elements.append(rect(rid, X["N4"] - 100, y - 12, 200, 26,
                         "#2f9e44", "#ffffff",
                         stroke_width=1.25, bound_ids=[tid]))
    elements.append(text(tid, X["N4"] - 95, y - 10, 190, 22, txt_, "#2f9e44",
                         container=rid, font=12))

# ── 실패 배경 배너 ────────────────────────────────────────
fail_banner_id, fail_banner_t = "fail_banner", "fail_banner_t"
elements.append(rect(fail_banner_id, 340, 1040, 900, 570, "#c92a2a", "#fff5f5",
                     stroke_width=1.5, bound_ids=[fail_banner_t], style="dashed"))
elements.append(text(fail_banner_t, 350, 1045, 880, 20,
                     "🔴 실패 시 — 간호사가 결정 (자동 복귀 안 함)", "#c92a2a",
                     container=fail_banner_id, font=14,
                     align="left", valign="top"))

# 실패 - "로봇은 그 자리 대기" note (병실 그 자리에서 대기)
wait_id, wait_tid = "wait_note", "wait_note_t"
elements.append(rect(wait_id, X["N4"] - 130, 1300, 260, 90,
                     "#c92a2a", "#fff5f5",
                     stroke_width=1.75, bound_ids=[wait_tid]))
elements.append(text(wait_tid, X["N4"] - 120, 1310, 240, 70,
                     "🕐 병실 그 자리에서 대기\n(최대 5분)\n\n"
                     "5분 초과 시 자동 복귀\n(로그: “간호사 미응답”)",
                     "#c92a2a", container=wait_id, font=12,
                     align="center", valign="middle"))

# 실패 - LCD 슬픔 self-notes (마지막)
fail_self = [
    (1540, "LCD “배송 실패!” 3초"),
    (1572, "슬픔 얼굴 → 스스로 복귀"),
]
for i, (y, txt_) in enumerate(fail_self):
    rid, tid = f"fail_self_{i}", f"fail_self_t_{i}"
    elements.append(rect(rid, X["N4"] - 100, y - 12, 200, 26,
                         "#c92a2a", "#ffffff",
                         stroke_width=1.25, bound_ids=[tid]))
    elements.append(text(tid, X["N4"] - 95, y - 10, 190, 22, txt_, "#c92a2a",
                         container=rid, font=12))

# 선택 다이아 힌트 - 화면(N2) lifeline 옆에 두 옵션 박스
choice_box_id, choice_box_t = "choice_box", "choice_box_t"
elements.append(rect(choice_box_id, X["N2"] - 130, 1085, 260, 44,
                     "#c92a2a", "#ffffff",
                     stroke_width=1.5, bound_ids=[choice_box_t]))
elements.append(text(choice_box_t, X["N2"] - 125, 1090, 250, 34,
                     "🔘 “바로 복귀”     🔘 “대기해, 내가 갈게”",
                     "#c92a2a", container=choice_box_id, font=12,
                     align="center", valign="middle"))

# ── Phase 라벨 (좌측) ─────────────────────────────────────
phases = [
    (170, "① 배송 요청", "#1971c2", "#d0ebff"),
    (325, "② 이동", "#e67700", "#fff3bf"),
    (475, "③ 도착 & 카드 확인", "#087f5b", "#c3fae8"),
    (745, "④⑤ 결과 & 알림", "#5f3dc4", "#e5dbff"),
    (900, "⑥ 성공 복귀", "#2f9e44", "#ebfbee"),
    (1145, "⑥ 실패: 간호사 결정", "#c92a2a", "#fff5f5"),
    (1660, "종료", "#495057", "#e9ecef"),
]
for i, (y, label, stroke, bg) in enumerate(phases):
    pid, pt = f"ph_{i}", f"ph_{i}_t"
    elements.append(rect(pid, -240, y - 15, 210, 32, stroke, bg,
                         stroke_width=1.5, bound_ids=[pt]))
    elements.append(text(pt, -235, y - 13, 200, 28, label, stroke,
                         container=pid, font=13))

# ── Title & Legend ────────────────────────────────────────
elements.append(text("title_t", -240, -20, 800, 40,
                     "PinkyCare — 배송 흐름 (성공/실패 분기 반영)",
                     "#1e1e1e", container=None, font=24,
                     align="left", valign="top"))

lg_id, lg_t = "lg", "lg_t"
elements.append(rect(lg_id, 1260, 40, 260, 230, "#495057", "#f8f9fa",
                     stroke_width=1.5, bound_ids=[lg_t]))
elements.append(text(lg_t, 1270, 50, 240, 210,
                     "범례\n\n"
                     "──▶  요청 · 보고 · 물어보기\n"
                     "╌╌▶  알림 · 결과 (밀어주기)\n"
                     "🟢 초록: 성공 자동 복귀\n"
                     "🔴 빨강: 실패 · 간호사 결정\n"
                     "▢    카드 확인 창 / 대기 상태\n\n"
                     "※ 관제 시스템은 로봇에게 명령하지\n"
                     "   않는다. 로봇이 알림을 구독해\n"
                     "   스스로 출발하고, 결과를 물어봐\n"
                     "   스스로 복귀한다.",
                     "#495057", container=lg_id, font=12,
                     align="left", valign="top"))

# ── Save ──────────────────────────────────────────────────
out = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": elements,
    "appState": {"gridSize": 20, "viewBackgroundColor": "#ffffff"},
    "files": {},
}

os.makedirs("docs/diagrams", exist_ok=True)
path = "docs/diagrams/delivery-sequence.excalidraw"
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"wrote {path} · {len(elements)} elements")
