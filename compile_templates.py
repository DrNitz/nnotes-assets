#!/usr/bin/env python3
"""Compile layered template SVGs into the Nnotes template model.

Source layout (see templates/SPEC.md):

    <g id="structural">    structural rules, alpha from stroke-opacity
    <g id="rule-<name>">   ruling lines, may be a spacing-driven repeat group
    <g id="guide">         hairlines
    <g id="label">         text labels, outlined to vector paths
    <g id="decor">         decorative vector art (recolours with the ink)
    <g id="sticker-<id>">  extracted as an editable page item, not painted

Optional sidecar metadata (templates/meta/<name>.json):

    "layout": {
      "primary": "todo",
      "repeats": {
        "todo": {"group": "rule-todo", "anchor": 576, "base": 34}
      }
    }

Usage:
    python compile_templates.py [--font PATH] [--font-bold PATH] [--check]
"""

import argparse
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
SVG_DIR = "templates/svg"
META_DIR = "templates/meta"
OUT_DIR = "templates/model"
MODEL_VERSION = 1
ROLE_PREFIXES = ("structural", "rule", "guide", "label", "decor", "sticker")

DEFAULT_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
DEFAULT_BOLD_CANDIDATES = (
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


# --- tiny matrix helpers -------------------------------------------------------

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def mat_mul(m, n):
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a * a2 + c * b2,
        b * a2 + d * b2,
        a * c2 + c * d2,
        b * c2 + d * d2,
        a * e2 + c * f2 + e,
        b * e2 + d * f2 + f,
    )


def apply(m, x, y):
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def parse_transform(text):
    if not text:
        return IDENTITY
    total = IDENTITY
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text):
        vals = [float(v) for v in re.split(r"[\s,]+", args.strip()) if v]
        if name == "translate":
            m = (1, 0, 0, 1, vals[0], vals[1] if len(vals) > 1 else 0.0)
        elif name == "scale":
            sx = vals[0]
            sy = vals[1] if len(vals) > 1 else sx
            m = (sx, 0, 0, sy, 0, 0)
        elif name == "matrix":
            m = tuple(vals[:6])
        elif name == "rotate":
            ang = math.radians(vals[0])
            cx, cy = (vals[1], vals[2]) if len(vals) > 2 else (0.0, 0.0)
            cos_a, sin_a = math.cos(ang), math.sin(ang)
            m = mat_mul(
                (1, 0, 0, 1, cx, cy),
                mat_mul((cos_a, sin_a, -sin_a, cos_a, 0, 0), (1, 0, 0, 1, -cx, -cy)),
            )
        else:
            continue
        total = mat_mul(total, m)
    return total


def style_of(el, inherited):
    out = dict(inherited)
    for key in ("stroke", "stroke-width", "stroke-opacity", "fill", "fill-opacity",
                "font-size", "font-weight", "letter-spacing", "text-anchor", "font-family"):
        if el.get(key) is not None:
            out[key] = el.get(key)
    style = el.get("style")
    if style:
        for part in style.split(";"):
            if ":" in part:
                k, v = part.split(":", 1)
                out[k.strip()] = v.strip()
    return out


def fnum(value, fallback=0.0):
    if value is None:
        return fallback
    try:
        return float(re.sub(r"[a-z%]+$", "", str(value).strip()))
    except ValueError:
        return fallback


def alpha_of(style, key):
    base = fnum(style.get("stroke-opacity" if key == "stroke" else "fill-opacity"), 1.0)
    opacity = fnum(style.get("opacity"), 1.0)
    return max(0.0, min(1.0, base * opacity))


def is_none_color(value):
    return value is None or value.strip().lower() in ("none", "transparent")


# --- path parsing --------------------------------------------------------------

NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
CMD = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]")


def flatten_cubic(p0, p1, p2, p3, steps=8):
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt ** 3 * p0[0] + 3 * mt ** 2 * t * p1[0] + 3 * mt * t ** 2 * p2[0] + t ** 3 * p3[0]
        y = mt ** 3 * p0[1] + 3 * mt ** 2 * t * p1[1] + 3 * mt * t ** 2 * p2[1] + t ** 3 * p3[1]
        pts.append((x, y))
    return pts


def flatten_quad(p0, p1, p2, steps=6):
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0]
        y = mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]
        pts.append((x, y))
    return pts


def arc_to_points(p0, rx, ry, phi_deg, large, sweep, p1, steps=16):
    """SVG endpoint arc to a polyline (W3C implementation notes)."""
    if rx == 0 or ry == 0 or p0 == p1:
        return [p1]
    phi = math.radians(phi_deg)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx2, dy2 = (p0[0] - p1[0]) / 2.0, (p0[1] - p1[1]) / 2.0
    x1p = cos_p * dx2 + sin_p * dy2
    y1p = -sin_p * dx2 + cos_p * dy2
    rx, ry = abs(rx), abs(ry)
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        scale = math.sqrt(lam)
        rx *= scale
        ry *= scale
    sign = -1.0 if large == sweep else 1.0
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = sign * math.sqrt(max(0.0, num / den)) if den else 0.0
    cxp = coef * rx * y1p / ry
    cyp = -coef * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (p0[0] + p1[0]) / 2.0
    cy = sin_p * cxp + cos_p * cyp + (p0[1] + p1[1]) / 2.0

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        norm = math.hypot(ux, uy) * math.hypot(vx, vy)
        a = math.acos(max(-1.0, min(1.0, dot / norm))) if norm else 0.0
        return -a if (ux * vy - uy * vx) < 0 else a

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2 * math.pi
    pts = []
    for i in range(1, steps + 1):
        t = theta1 + dtheta * i / steps
        x = cx + rx * math.cos(t) * cos_p - ry * math.sin(t) * sin_p
        y = cy + rx * math.cos(t) * sin_p + ry * math.sin(t) * cos_p
        pts.append((x, y))
    return pts


def parse_path(d):
    """Return a list of contours (each a list of points) plus a closed flag per contour."""
    tokens = re.findall(CMD.pattern + "|" + NUM.pattern, d.replace(",", " "))
    contours = []
    current = []
    start = (0.0, 0.0)
    pos = (0.0, 0.0)
    prev_ctrl = None
    prev_cmd = ""
    i = 0
    cmd = None

    def take(n):
        nonlocal i
        vals = [float(tokens[i + k]) for k in range(n)]
        i += n
        return vals

    while i < len(tokens):
        if CMD.fullmatch(tokens[i]):
            cmd = tokens[i]
            i += 1
        elif cmd is None:
            break
        rel = cmd.islower()
        c = cmd.upper()

        if c == "Z":
            if current:
                contours.append((current, True))
                current = []
            pos = start
            prev_ctrl = None
            prev_cmd = c
            continue

        if c == "M":
            x, y = take(2)
            if rel:
                x, y = x + pos[0], y + pos[1]
            if current:
                contours.append((current, False))
            current = [(x, y)]
            start = (x, y)
            pos = (x, y)
            prev_ctrl = None
            cmd = "l" if rel else "L"  # implicit lineto for following pairs
            prev_cmd = c
            continue

        if c == "L":
            x, y = take(2)
            if rel:
                x, y = x + pos[0], y + pos[1]
            current.append((x, y))
            pos = (x, y)
            prev_ctrl = None
        elif c == "H":
            x = take(1)[0]
            if rel:
                x += pos[0]
            current.append((x, pos[1]))
            pos = (x, pos[1])
            prev_ctrl = None
        elif c == "V":
            y = take(1)[0]
            if rel:
                y += pos[1]
            current.append((pos[0], y))
            pos = (pos[0], y)
            prev_ctrl = None
        elif c in ("C", "S"):
            if c == "C":
                x1, y1, x2, y2, x, y = take(6)
                if rel:
                    x1, y1, x2, y2, x, y = x1 + pos[0], y1 + pos[1], x2 + pos[0], y2 + pos[1], x + pos[0], y + pos[1]
            else:
                x2, y2, x, y = take(4)
                if rel:
                    x2, y2, x, y = x2 + pos[0], y2 + pos[1], x + pos[0], y + pos[1]
                if prev_ctrl is not None and prev_cmd in ("C", "S"):
                    x1 = 2 * pos[0] - prev_ctrl[0]
                    y1 = 2 * pos[1] - prev_ctrl[1]
                else:
                    x1, y1 = pos
            current.extend(flatten_cubic(pos, (x1, y1), (x2, y2), (x, y)))
            prev_ctrl = (x2, y2)
            pos = (x, y)
        elif c in ("Q", "T"):
            if c == "Q":
                x1, y1, x, y = take(4)
                if rel:
                    x1, y1, x, y = x1 + pos[0], y1 + pos[1], x + pos[0], y + pos[1]
            else:
                x, y = take(2)
                if rel:
                    x, y = x + pos[0], y + pos[1]
                if prev_ctrl is not None and prev_cmd in ("Q", "T"):
                    x1 = 2 * pos[0] - prev_ctrl[0]
                    y1 = 2 * pos[1] - prev_ctrl[1]
                else:
                    x1, y1 = pos
            current.extend(flatten_quad(pos, (x1, y1), (x, y)))
            prev_ctrl = (x1, y1)
            pos = (x, y)
        elif c == "A":
            rx, ry, phi, large, sweep, x, y = take(7)
            if rel:
                x, y = x + pos[0], y + pos[1]
            current.extend(arc_to_points(pos, rx, ry, phi, int(large), int(sweep), (x, y)))
            pos = (x, y)
            prev_ctrl = None
        else:
            prev_ctrl = None
        prev_cmd = c

    if current:
        contours.append((current, False))
    return contours


# --- text outlining ------------------------------------------------------------

class FlattenPen:
    """Collect glyph contours as flat polylines in font units."""

    def __init__(self):
        self.contours = []
        self._cur = []

    def moveTo(self, pt):
        if self._cur:
            self.contours.append(self._cur)
        self._cur = [pt]

    def lineTo(self, pt):
        self._cur.append(pt)

    def qCurveTo(self, *pts):
        if pts[-1] is None:
            pts = pts[:-1]
        p0 = self._cur[-1]
        for i in range(len(pts) - 1):
            p1 = pts[i]
            p2 = pts[i + 1] if i + 1 < len(pts) - 1 else pts[-1]
            self._cur.extend(flatten_quad(p0, p1, p2)[1:])
            p0 = p2

    def curveTo(self, *pts):
        p0 = self._cur[-1]
        for i in range(0, len(pts) - 2, 2):
            p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2]
            self._cur.extend(flatten_cubic(p0, p1, p2, p3)[1:])
            p0 = p3

    def closePath(self):
        if self._cur:
            self.contours.append(self._cur)
            self._cur = []

    def endPath(self):
        self.closePath()

    def addComponent(self, glyph_name, transform):
        pass

    def finish(self):
        self.closePath()
        return self.contours


class FontCache:
    def __init__(self, regular, bold):
        self.paths = {"regular": regular, "bold": bold}
        self.fonts = {}

    def get(self, weight):
        key = "bold" if weight and fnum(weight, 400) >= 600 else "regular"
        path = self.paths[key] or self.paths["regular"]
        if path not in self.fonts:
            from fontTools.ttLib import TTFont

            font = TTFont(path, lazy=True)
            self.fonts[path] = (font, font.getBestCmap(), font.getGlyphSet(), font["head"].unitsPerEm)
        return self.fonts[path]


def outline_text(text, style, matrix, fonts, origin=(0.0, 0.0)):
    from fontTools.pens.transformPen import TransformPen

    font, cmap, glyph_set, upm = fonts.get(style.get("font-weight"))
    size = fnum(style.get("font-size"), 16.0)
    scale = size / upm
    tracking = fnum(style.get("letter-spacing"), 0.0)
    anchor = (style.get("text-anchor") or "start").strip()
    ox, oy = origin

    advances = []
    total = 0.0
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            name = ".notdef"
        adv = glyph_set[name].width * scale
        advances.append((ch, name, adv))
        total += adv + tracking
    if advances:
        total -= tracking

    x = 0.0
    if anchor == "middle":
        x -= total / 2.0
    elif anchor == "end":
        x -= total

    contours = []
    for ch, name, adv in advances:
        if not ch.isspace():
            pen = FlattenPen()
            glyph = glyph_set[name]
            # font units are y-up; flip to y-down, scale into content px, and place at the
            # text element's x/y baseline (the advance cursor adds the per-glyph x offset).
            glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, ox + x, oy)))
            for contour in pen.finish():
                points = [apply(matrix, px, py) for px, py in contour]
                if len(points) >= 3:
                    contours.append(points)
        x += adv + tracking

    return contours


# --- element conversion --------------------------------------------------------

def points_attr(value):
    nums = [float(v) for v in re.findall(NUM.pattern, value or "")]
    return list(zip(nums[0::2], nums[1::2]))


def rnd(value):
    return round(float(value), 1)


def primitives_from(el, style, matrix, fonts, role):
    tag = el.tag.split("}")[-1]
    items = []
    filled = not is_none_color(style.get("fill"))
    stroked = not is_none_color(style.get("stroke"))
    width = fnum(style.get("stroke-width"), 1.0)

    if tag == "line":
        p1 = apply(matrix, fnum(el.get("x1")), fnum(el.get("y1")))
        p2 = apply(matrix, fnum(el.get("x2")), fnum(el.get("y2")))
        if stroked:
            items.append({"op": "line", "a": [rnd(p1[0]), rnd(p1[1])], "b": [rnd(p2[0]), rnd(p2[1])],
                          "w": rnd(width * (abs(matrix[0]) + abs(matrix[3])) / 2.0)})
    elif tag == "rect":
        x, y = fnum(el.get("x")), fnum(el.get("y"))
        w, h = fnum(el.get("width")), fnum(el.get("height"))
        rx = fnum(el.get("rx"), fnum(el.get("ry")))
        corners = [apply(matrix, x, y), apply(matrix, x + w, y), apply(matrix, x + w, y + h), apply(matrix, x, y + h)]
        if filled:
            rounded = [apply(matrix, x + rx, y), apply(matrix, x + w - rx, y),
                       apply(matrix, x + w, y + rx), apply(matrix, x + w, y + h - rx),
                       apply(matrix, x + w - rx, y + h), apply(matrix, x + rx, y + h),
                       apply(matrix, x, y + h - rx), apply(matrix, x, y + rx)]
            items.append({"op": "fill", "contours": [[rnd(v) for p in rounded for v in p]]})
        if stroked:
            items.append({"op": "rect", "rect": [rnd(corners[0][0]), rnd(corners[0][1]),
                                                 rnd(corners[1][0] - corners[0][0]), rnd(corners[2][1] - corners[1][1])],
                          "rx": rnd(rx * (abs(matrix[0]) + abs(matrix[3])) / 2.0),
                          "w": rnd(width * (abs(matrix[0]) + abs(matrix[3])) / 2.0)})
    elif tag in ("circle", "ellipse"):
        cx, cy = fnum(el.get("cx")), fnum(el.get("cy"))
        rx = fnum(el.get("r"), fnum(el.get("rx")))
        ry = fnum(el.get("r"), fnum(el.get("ry")))
        c = apply(matrix, cx, cy)
        scale = (abs(matrix[0]) + abs(matrix[3])) / 2.0
        item = {"op": "circle", "c": [rnd(c[0]), rnd(c[1])],
                "rx": rnd(rx * scale), "ry": rnd(ry * scale)}
        if filled:
            items.append(dict(item, fill=True))
        if stroked:
            items.append(dict(item, w=rnd(width * scale)))
    elif tag in ("polygon", "polyline"):
        pts = [apply(matrix, x, y) for x, y in points_attr(el.get("points"))]
        closed = tag == "polygon"
        if filled and closed and len(pts) >= 3:
            items.append({"op": "fill", "contours": [[rnd(v) for p in pts for v in p]]})
        if stroked:
            items.append({"op": "poly", "pts": [rnd(v) for p in pts for v in p],
                          "closed": closed, "w": rnd(width * (abs(matrix[0]) + abs(matrix[3])) / 2.0)})
    elif tag == "path":
        d = el.get("d") or ""
        for contour, closed in parse_path(d):
            pts = [apply(matrix, x, y) for x, y in contour]
            if len(pts) < 2:
                continue
            if filled and closed and len(pts) >= 3:
                items.append({"op": "fill", "contours": [[rnd(v) for p in pts for v in p]]})
            if stroked:
                items.append({"op": "poly", "pts": [rnd(v) for p in pts for v in p],
                              "closed": closed, "w": rnd(width * (abs(matrix[0]) + abs(matrix[3])) / 2.0)})
    elif tag == "text":
        text = "".join(el.itertext())
        if not text.strip():
            return items
        pos = apply(matrix, fnum(el.get("x")), fnum(el.get("y")))
        if fonts is not None:
            contours = outline_text(text, style, matrix, fonts, (fnum(el.get("x")), fnum(el.get("y"))))
            if contours:
                items.append({"op": "fill", "evenOdd": True,
                              "contours": [[rnd(v) for p in contour for v in p] for contour in contours]})
                return items
        items.append({"op": "text", "at": [rnd(pos[0]), rnd(pos[1])], "text": text,
                      "size": rnd(fnum(style.get("font-size"), 16.0)),
                      "weight": int(fnum(style.get("font-weight"), 400)),
                      "anchor": (style.get("text-anchor") or "start").strip()})
    return items


def item_ys(item):
    op = item["op"]
    if op == "line":
        return [item["a"][1], item["b"][1]]
    if op == "poly":
        return list(item["pts"][1::2])
    if op == "fill":
        return [v for contour in item["contours"] for v in contour[1::2]]
    if op == "rect":
        x, y, w, h = item["rect"]
        return [y, y + h]
    if op == "circle":
        cy = item["c"][1]
        return [cy - item["ry"], cy + item["ry"]]
    if op == "text":
        return [item["at"][1]]
    return []


def shift_y(item, delta):
    op = item["op"]
    if op == "line":
        item["a"][1] = rnd(item["a"][1] + delta)
        item["b"][1] = rnd(item["b"][1] + delta)
    elif op == "poly":
        item["pts"][1::2] = [rnd(v + delta) for v in item["pts"][1::2]]
    elif op == "fill":
        item["contours"] = [[rnd(v + delta) if i % 2 else v for i, v in enumerate(contour)]
                            for contour in item["contours"]]
    elif op == "rect":
        item["rect"][1] = rnd(item["rect"][1] + delta)
    elif op == "circle":
        item["c"][1] = rnd(item["c"][1] + delta)
    elif op == "text":
        item["at"][1] = rnd(item["at"][1] + delta)


def snap_to_row(item, anchor, base):
    """Bind an item to its repeat row, then store its geometry relative to that row."""
    ys = item_ys(item)
    if not ys:
        return None
    center = (min(ys) + max(ys)) / 2.0
    row = int(round((center - anchor) / base))
    baseline = anchor + row * base
    if abs(center - baseline) > base * 0.62:
        return None
    shift_y(item, -baseline)
    item["row"] = row
    return row


def walk(el, style, matrix, fonts, role, repeats, group_id, sink, sticker_sink=None):
    style = style_of(el, style)
    matrix = mat_mul(matrix, parse_transform(el.get("transform")))
    tag = el.tag.split("}")[-1]

    if tag == "g":
        gid = el.get("id") or group_id
        if gid and gid.startswith("sticker-"):
            # Bake the sticker artwork into the model as a preserveColor layer. It is painted with
            # the template, so switching templates can never leave old artwork on the page.
            for child in el:
                walk(child, style, matrix, fonts, "sticker", repeats, gid, sink, sticker_sink)
            return
        role = role_for(gid, role)
        for child in el:
            walk(child, style, matrix, fonts, role, repeats, gid, sink, sticker_sink)
        return

    if tag in ("defs", "title", "desc", "metadata", "clipPath", "mask"):
        return

    repeat = repeats.get(group_id)
    items = primitives_from(el, style, matrix, fonts, role)
    for item in items:
        if repeat is not None:
            name, anchor, base = repeat
            if snap_to_row(item, anchor, base) is None:
                print(f"warning: {group_id}: item near y={item_ys(item)} is off the {name} grid",
                      file=sys.stderr)
            else:
                item["rep"] = name
        item["role"] = role
        uses_fill = item["op"] == "fill" or item.get("fill") is True
        item["alpha"] = rnd(alpha_of(style, "fill" if uses_fill else "stroke"))
        if role == "sticker":
            item["ink"] = style.get("fill") if uses_fill else style.get("stroke")
        sink.append(item)


def role_for(group_id, current):
    if not group_id:
        return current
    head = group_id.split("-")[0]
    if head in ROLE_PREFIXES and head != "sticker":
        return head
    return current


def bbox_of(items):
    xs, ys = [], []
    for item in items:
        op = item.get("op")
        if op == "line":
            xs += [item["a"][0], item["b"][0]]
            ys += [item["a"][1], item["b"][1]]
        elif op == "poly":
            xs += item["pts"][0::2]
            ys += item["pts"][1::2]
        elif op == "fill":
            for contour in item["contours"]:
                xs += contour[0::2]
                ys += contour[1::2]
        elif op in ("rect", "circle"):
            if op == "rect":
                x, y, w, h = item["rect"]
                xs += [x, x + w]
                ys += [y, y + h]
            else:
                cx, cy = item["c"]
                xs += [cx - item["rx"], cx + item["rx"]]
                ys += [cy - item["ry"], cy + item["ry"]]
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def items_to_svg(items, box):
    x, y, w, h = box
    pad_w = max(w, 1.0)
    pad_h = max(h, 1.0)
    parts = []
    for item in items:
        op = item["op"]
        ink = item.get("ink") or "#000"
        if op == "line":
            (x1, y1), (x2, y2) = item["a"], item["b"]
            parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{ink}" '
                         f'stroke-width="{item.get("w", 1)}"/>')
        elif op == "rect":
            rx, ry, rw, rh = item["rect"]
            radius = item.get("rx", 0)
            parts.append(f'<rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" rx="{radius}" '
                         f'fill="none" stroke="{ink}" stroke-width="{item.get("w", 1)}"/>')
        elif op == "circle":
            cx, cy = item["c"]
            if item.get("fill"):
                parts.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{item["rx"]}" ry="{item["ry"]}" fill="{ink}"/>')
            else:
                parts.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{item["rx"]}" ry="{item["ry"]}" '
                             f'fill="none" stroke="{ink}" stroke-width="{item.get("w", 1)}"/>')
        elif op == "poly":
            pts = " ".join(f"{item['pts'][i]},{item['pts'][i + 1]}" for i in range(0, len(item["pts"]), 2))
            tag = "polygon" if item.get("closed") else "polyline"
            parts.append(f'<{tag} points="{pts}" fill="none" stroke="{ink}" stroke-width="{item.get("w", 1)}"/>')
        elif op == "fill":
            for contour in item["contours"]:
                pts = " ".join(f"{contour[i]},{contour[i + 1]}" for i in range(0, len(contour), 2))
                parts.append(f'<polygon points="{pts}" fill="{ink}"/>')
    return (f'<svg xmlns="{SVG_NS}" width="{rnd(pad_w)}" height="{rnd(pad_h)}" '
            f'viewBox="{rnd(x)} {rnd(y)} {rnd(pad_w)} {rnd(pad_h)}">' + "".join(parts) + "</svg>")


def compile_svg(path, meta, fonts):
    tree = ET.parse(path)
    root = tree.getroot()
    view = root.get("viewBox")
    if view:
        _, _, cw, ch = [float(v) for v in re.split(r"[\s,]+", view.strip())]
    else:
        cw, ch = fnum(root.get("width"), 1240.0), fnum(root.get("height"), 1754.0)

    layout = (meta or {}).get("layout") or {}
    repeats_meta = layout.get("repeats") or {}
    group_repeats = {}  # svg group id -> (repeat name, anchor, base)
    repeat_specs = {}   # repeat name -> model descriptor
    for key, spec in repeats_meta.items():
        group = spec.get("group") or key
        anchor = fnum(spec.get("anchor"), 0.0)
        base = fnum(spec.get("base"), 20.0)
        group_repeats[group] = (key, anchor, base)
        repeat_specs[key] = {
            "anchor": rnd(anchor),
            "base": rnd(base),
            "limit": rnd(spec.get("limit", ch - 40.0)),
            "rows": 0,
        }

    items = []
    stickers = []
    for child in root:
        walk(child, {}, IDENTITY, fonts, "decor", group_repeats, None, items, stickers)

    for item in items:
        spec = repeat_specs.get(item.get("rep"))
        if spec is not None:
            spec["rows"] = max(spec["rows"], item["row"] + 1)

    # group consecutive items with the same role+alpha into paint layers
    layers = []
    for item in items:
        role = item.get("role", "decor")
        if layers and layers[-1]["alpha"] == item["alpha"] and layers[-1]["role"] == role:
            target = layers[-1]
        else:
            target = {"role": role, "alpha": item["alpha"], "items": []}
            if role == "sticker":
                target["preserveColor"] = True
            layers.append(target)
        target["items"].append(strip(item))

    spacing = None
    if repeat_specs:
        primary = layout.get("primary") or next(iter(repeat_specs))
        if primary in repeat_specs:
            spacing = {"primary": primary, "base": repeat_specs[primary]["base"]}

    compiled_stickers = []
    for sticker in stickers:
        box = bbox_of(sticker["items"])
        if box is None:
            continue
        compiled_stickers.append({
            "id": sticker["id"],
            "rect": [rnd(v) for v in box],
            "svg": items_to_svg(sticker["items"], box),
        })

    model = {
        "format": "nnotes-template",
        "version": MODEL_VERSION,
        "id": os.path.splitext(os.path.basename(path))[0],
        "canvas": {"w": rnd(cw), "h": rnd(ch)},
        "spacing": spacing,
        "repeat": repeat_specs,
        "layers": layers,
        "stickers": compiled_stickers,
    }
    return model


def strip(item):
    out = {k: v for k, v in item.items() if k not in ("role", "alpha", "_role")}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", default=None)
    parser.add_argument("--font-bold", default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    regular = args.font or next((p for p in DEFAULT_FONT_CANDIDATES if os.path.exists(p)), None)
    bold = args.font_bold or next((p for p in DEFAULT_BOLD_CANDIDATES if os.path.exists(p)), None)
    try:
        fonts = FontCache(regular, bold)
        import fontTools  # noqa: F401
    except ImportError:
        fonts = None
        print("warning: fonttools missing, text stays as a screen-only text op", file=sys.stderr)
    if fonts and not regular:
        print("warning: no font found, text stays as a screen-only text op", file=sys.stderr)
        fonts = None

    os.makedirs(OUT_DIR, exist_ok=True)
    failures = 0
    for name in sorted(os.listdir(SVG_DIR)):
        if not name.lower().endswith(".svg"):
            continue
        stem = os.path.splitext(name)[0]
        meta_path = os.path.join(META_DIR, stem + ".json")
        meta = {}
        if os.path.exists(meta_path):
            with open(meta_path, encoding="utf-8") as handle:
                meta = json.load(handle)
        try:
            model = compile_svg(os.path.join(SVG_DIR, name), meta, fonts)
        except Exception as exc:  # keep one bad file from blocking the rest
            print(f"error: {name}: {exc}", file=sys.stderr)
            failures += 1
            continue
        out_path = os.path.join(OUT_DIR, stem + ".json")
        text = json.dumps(model, indent=2, ensure_ascii=False) + "\n"
        if args.check:
            current = open(out_path, encoding="utf-8").read() if os.path.exists(out_path) else None
            if current != text:
                print(f"{out_path} is out of date")
                failures += 1
            continue
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"compiled {name} -> {out_path} ({len(model['layers'])} layers, "
              f"{len(model['stickers'])} stickers)")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
