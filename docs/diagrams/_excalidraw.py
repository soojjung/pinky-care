"""Excalidraw 요소 생성 헬퍼.

docs/diagrams/_gen_*.py 가 공유한다. 저장소 루트에서 실행할 것:

    python3 docs/diagrams/_gen_architecture.py
"""
import json
import os

UPDATED = 1773161826574

_idx = [0]
_seed = [1000]


def nidx() -> str:
    _idx[0] += 1
    return f"a{_idx[0]:03d}"


def nseed() -> int:
    _seed[0] += 1
    return _seed[0]


def _base(id_, type_, x, y, w, h, stroke, bg, stroke_width, style):
    return {
        "id": id_, "type": type_,
        "x": x, "y": y, "width": w, "height": h,
        "angle": 0,
        "strokeColor": stroke, "backgroundColor": bg,
        "fillStyle": "solid", "strokeWidth": stroke_width, "strokeStyle": style,
        "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None,
        "index": nidx(),
        "seed": nseed(), "version": 1, "versionNonce": nseed(),
        "isDeleted": False,
        "boundElements": [],
        "updated": UPDATED, "link": None, "locked": False,
    }


def rect(id_, x, y, w, h, stroke, bg, stroke_width=2, bound_ids=None,
         roundness=True, style="solid"):
    el = _base(id_, "rectangle", x, y, w, h, stroke, bg, stroke_width, style)
    el["roundness"] = {"type": 3} if roundness else None
    el["boundElements"] = [{"type": "text", "id": t} for t in (bound_ids or [])]
    return el


def ellipse(id_, x, y, w, h, stroke, bg, stroke_width=2, bound_ids=None,
            style="solid"):
    el = _base(id_, "ellipse", x, y, w, h, stroke, bg, stroke_width, style)
    el["roundness"] = {"type": 2}
    el["boundElements"] = [{"type": "text", "id": t} for t in (bound_ids or [])]
    return el


def diamond(id_, x, y, w, h, stroke, bg, stroke_width=2, bound_ids=None,
            style="solid"):
    el = _base(id_, "diamond", x, y, w, h, stroke, bg, stroke_width, style)
    el["roundness"] = {"type": 2}
    el["boundElements"] = [{"type": "text", "id": t} for t in (bound_ids or [])]
    return el


def text(id_, x, y, w, h, txt, stroke, container=None, font=14,
         align="center", valign="middle", bg="transparent"):
    el = _base(id_, "text", x, y, w, h, stroke, bg, 2, "solid")
    el["roundness"] = None
    el.update({
        "text": txt, "fontSize": font, "fontFamily": 5,
        "textAlign": align, "verticalAlign": valign,
        "containerId": container,
        "originalText": txt, "autoResize": True, "lineHeight": 1.25,
    })
    return el


def line(id_, x, y, dx, dy, stroke, style="dashed", stroke_width=1.5):
    el = _base(id_, "line", x, y, abs(dx) or 1, abs(dy) or 1,
               stroke, "transparent", stroke_width, style)
    el["roughness"] = 0
    el["roundness"] = {"type": 2}
    el.update({
        "points": [[0, 0], [dx, dy]],
        "lastCommittedPoint": None,
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": None,
    })
    return el


def arrow(id_, x, y, points, stroke, stroke_width=1.75, style="solid",
          end_head="arrow"):
    """points: [(dx, dy), ...] — 시작점(0,0) 기준 상대 좌표."""
    pts = [[0, 0]] + [list(p) for p in points]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    el = _base(id_, "arrow", x, y,
               max(xs) - min(xs) or 1, max(ys) - min(ys) or 1,
               stroke, "transparent", stroke_width, style)
    el["roughness"] = 0
    el["roundness"] = {"type": 2}
    el.update({
        "points": pts,
        "lastCommittedPoint": None,
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": end_head,
        "elbowed": False,
    })
    return el


def save(elements, filename: str) -> None:
    out = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {"gridSize": 20, "viewBackgroundColor": "#ffffff"},
        "files": {},
    }
    os.makedirs("docs/diagrams", exist_ok=True)
    path = f"docs/diagrams/{filename}"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"wrote {path} · {len(elements)} elements")
