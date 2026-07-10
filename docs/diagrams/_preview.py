"""excalidraw 파일을 대략적인 PNG로 렌더해 레이아웃을 눈으로 확인한다.

excalidraw의 실제 렌더러가 아니라 배치 검증용 근사 렌더러다.
(손그림 질감·곡선 화살표 없음. 겹침·좌표 이탈만 잡는 용도.)

    python3 docs/diagrams/_preview.py docs/diagrams/architecture.excalidraw
"""
import json
import sys

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
SCALE = 1
PAD = 40


def _font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def render(src: str, dst: str) -> None:
    els = json.load(open(src))["elements"]
    vis = [e for e in els if not e.get("isDeleted")]

    xs = [e["x"] for e in vis] + [e["x"] + e["width"] for e in vis]
    ys = [e["y"] for e in vis] + [e["y"] + e["height"] for e in vis]
    minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
    w = int((maxx - minx) * SCALE) + PAD * 2
    h = int((maxy - miny) * SCALE) + PAD * 2

    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)

    def T(x, y):
        return ((x - minx) * SCALE + PAD, (y - miny) * SCALE + PAD)

    # 컨테이너에 바인딩된 텍스트는 컨테이너 중앙에 그린다
    by_id = {e["id"]: e for e in vis}

    for e in vis:
        t = e["type"]
        x0, y0 = T(e["x"], e["y"])
        x1, y1 = T(e["x"] + e["width"], e["y"] + e["height"])
        stroke = e.get("strokeColor", "#000")
        bg = e.get("backgroundColor", "transparent")
        fill = None if bg == "transparent" else bg
        dash = e.get("strokeStyle") == "dashed"

        if t == "rectangle":
            d.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=fill,
                                outline=stroke, width=2 if not dash else 1)
        elif t == "ellipse":
            d.ellipse([x0, y0, x1, y1], fill=fill, outline=stroke, width=2)
        elif t == "diamond":
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            d.polygon([(cx, y0), (x1, cy), (cx, y1), (x0, cy)],
                      fill=fill, outline=stroke)
        elif t in ("arrow", "line"):
            pts = [T(e["x"] + px, e["y"] + py) for px, py in e["points"]]
            d.line(pts, fill=stroke, width=2)
            if t == "arrow" and e.get("endArrowhead"):
                (ax, ay), (bx, by) = pts[-2], pts[-1]
                dx, dy = bx - ax, by - ay
                n = max((dx * dx + dy * dy) ** 0.5, 1e-6)
                ux, uy = dx / n, dy / n
                d.polygon([(bx, by),
                           (bx - 9 * ux + 5 * uy, by - 9 * uy - 5 * ux),
                           (bx - 9 * ux - 5 * uy, by - 9 * uy + 5 * ux)],
                          fill=stroke)

    for e in vis:
        if e["type"] != "text":
            continue
        f = _font(int(e.get("fontSize", 14) * SCALE))
        lines = e["text"].split("\n")
        cid = e.get("containerId")
        if cid and cid in by_id:
            c = by_id[cid]
            cx0, cy0 = T(c["x"], c["y"])
            cx1, cy1 = T(c["x"] + c["width"], c["y"] + c["height"])
            total = len(lines) * (f.size + 4)
            ty = (cy0 + cy1) / 2 - total / 2
            if e.get("verticalAlign") == "top":
                ty = cy0 + 8
            for ln in lines:
                tw = d.textlength(ln, font=f)
                tx = (cx0 + cx1) / 2 - tw / 2
                if e.get("textAlign") == "left":
                    tx = cx0 + 10
                d.text((tx, ty), ln, font=f, fill=e["strokeColor"])
                ty += f.size + 4
        else:
            tx, ty = T(e["x"], e["y"])
            for ln in lines:
                if e.get("textAlign") == "center":
                    tw = d.textlength(ln, font=f)
                    d.text((tx + e["width"] / 2 - tw / 2, ty), ln, font=f,
                           fill=e["strokeColor"])
                else:
                    d.text((tx, ty), ln, font=f, fill=e["strokeColor"])
                ty += f.size + 4

    img.save(dst)
    print(f"{dst}  ({w}x{h})")


if __name__ == "__main__":
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src.replace(".excalidraw", ".preview.png")
    render(src, dst)
