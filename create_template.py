#!/usr/bin/env python3
"""Generate a Nnotes-compatible page template from a declarative spec.

    python create_template.py spec.json           # write templates/svg + templates/meta
    python create_template.py spec.json --check   # verify they are up to date
    python create_template.py --sample            # print a starter spec

The generated SVG follows templates/SPEC.md (role groups, one alpha per group,
honest repeat rows). The generated meta sidecar carries the layout block that makes
spacing editable. Overlaps and off-grid rows are hard errors, not warnings.

Run the normal toolchain afterwards:
    python compile_templates.py
    python generate_templates_json.py
"""

import argparse
import html
import json
import os
import re
import sys

SVG_DIR = "templates/svg"
META_DIR = "templates/meta"
VALID_CATEGORIES = {"Basic", "Academic", "Planners"}
VALID_KINDS = {"lines", "checklist", "timed"}
MIN_PITCH = 8.0
MIN_H_GAP = 16.0  # horizontal clearance between columns whose rows overlap

ROLE_ALPHA = {
    "structural": 0.8,
    "guide": 0.4,
    "label": 0.9,
    "label-muted": 0.75,
    "rule": 0.5,
}


class SpecError(Exception):
    pass


def num(value, default, name):
    if value is None:
        return float(default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpecError(f"{name} must be a number")
    return float(value)


def text(value, default="", name="value"):
    if value is None:
        return default
    if not isinstance(value, str):
        raise SpecError(f"{name} must be a string")
    return value


def ident(value, name):
    value = text(value, "", name)
    if not value:
        raise SpecError(f"{name} is required")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value):
        raise SpecError(f"{name} must be lowercase kebab-case: {value!r}")
    return value


def rnd(value):
    return round(float(value), 1)


def esc(value):
    return html.escape(str(value), quote=True)


# --- spec -> plan --------------------------------------------------------------

def build_plan(spec):
    if not isinstance(spec, dict):
        raise SpecError("spec root must be a JSON object")

    template_id = ident(spec.get("id"), "id")
    canvas = spec.get("canvas") or {}
    cw = num(canvas.get("w"), 1240, "canvas.w")
    ch = num(canvas.get("h"), 1754, "canvas.h")
    if cw <= 0 or ch <= 0:
        raise SpecError("canvas needs positive w and h")

    margin = spec.get("margin") or {}
    ml = num(margin.get("left"), 60, "margin.left")
    mr = num(margin.get("right"), 60, "margin.right")
    mt = num(margin.get("top"), 36, "margin.top")
    mb = num(margin.get("bottom"), 40, "margin.bottom")
    if ml < 0 or mr < 0 or mt < 0 or mb < 0 or ml + mr >= cw or mt + mb >= ch:
        raise SpecError("margins are invalid for this canvas")

    gap = num(spec.get("gap"), 30, "gap")
    label_h = num(spec.get("labelHeight"), 26, "labelHeight")
    label_to_row = num(spec.get("labelToRow"), 46, "labelToRow")
    row_tail = num(spec.get("rowTail"), 10, "rowTail")
    header_h = num(spec.get("headerHeight"), 180, "headerHeight")

    category = text(spec.get("category"), "Basic", "category") or "Basic"
    if category not in VALID_CATEGORIES:
        raise SpecError(f"category must be one of {sorted(VALID_CATEGORIES)}, got {category!r}")
    tags = spec.get("tags") or []
    if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
        raise SpecError("tags must be a list of strings")

    raw_sections = spec.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise SpecError("sections must be a non-empty list")
    sections = []
    used_ids = set()
    for index, src in enumerate(raw_sections):
        if not isinstance(src, dict):
            raise SpecError(f"sections[{index}] must be an object")
        sid = ident(src.get("id"), f"sections[{index}].id")
        if sid in used_ids:
            raise SpecError(f"duplicate section id {sid!r}")
        used_ids.add(sid)

        kind = text(src.get("kind"), "lines", f"sections[{sid}].kind")
        if kind not in VALID_KINDS:
            raise SpecError(f"section {sid}: kind must be one of {sorted(VALID_KINDS)}")
        rows = src.get("rows")
        if not isinstance(rows, int) or isinstance(rows, bool) or rows < 1 or rows > 80:
            raise SpecError(f"section {sid}: rows must be an integer 1..80")
        pitch = num(src.get("pitch"), 0, f"sections[{sid}].pitch")
        if pitch < MIN_PITCH:
            raise SpecError(f"section {sid}: pitch must be >= {MIN_PITCH}")

        x = num(src.get("x"), ml, f"sections[{sid}].x")
        width = num(src.get("width"), cw - ml - mr, f"sections[{sid}].width")
        if x < ml or x + width > cw - mr or width <= 0:
            raise SpecError(f"section {sid}: x/width escape the page margins")
        column = ident(src.get("column", "main"), f"sections[{sid}].column")
        gap_before = num(src.get("gapBefore"), gap, f"sections[{sid}].gapBefore")
        band = str(src.get("band", "auto:" + sid))

        sections.append({
            "id": sid,
            "kind": kind,
            "label": text(src.get("label"), sid.upper(), f"sections[{sid}].label"),
            "column": column,
            "band": band,
            "rows": rows,
            "pitch": pitch,
            "x": x,
            "width": width,
            "gapBefore": gap_before,
            "separator": bool(src.get("separator", False)),
            "checkbox": src.get("checkbox") or {},
            "lineInset": num(src.get("lineInset"), 40, f"sections[{sid}].lineInset"),
            "time": src.get("time") or {},
            "src": src,
        })

    # Bands stack vertically; sections inside one band share the same top cursor,
    # which is how side-by-side columns stay aligned without ever overlapping.
    cursor_top = mt + header_h + gap
    bands = {}
    for section in sections:
        bands.setdefault(section["band"], []).append(section)
    cursor = cursor_top
    for band, members in bands.items():
        starts = {
            rnd(num(m["src"].get("start"), 0, f"sections[{m['id']}].start"))
            for m in members if m["src"].get("start") is not None
        }
        if len(starts) > 1:
            raise SpecError(f"OVERLAP: band {band!r} has conflicting explicit starts {sorted(starts)}")
        band_top = cursor
        band_gap = max(m["gapBefore"] for m in members)
        band_bottom = band_top
        for section in members:
            explicit = section["src"].get("start")
            if explicit is not None:
                first_row = num(explicit, 0, f"sections[{section['id']}].start")
                label_y = first_row - label_to_row
                if label_y < band_top - 0.01:
                    raise SpecError(
                        f"OVERLAP: section {section['id']} label at y={rnd(label_y)} "
                        f"starts above its band top y={rnd(band_top)} ({band!r})"
                    )
            else:
                label_y = band_top + label_h
                first_row = label_y + label_to_row
            last_row = first_row + (section["rows"] - 1) * section["pitch"]
            bottom = last_row + row_tail
            if bottom > ch - mb + 0.01:
                raise SpecError(
                    f"OVERFLOW: section {section['id']} ends at y={rnd(bottom)}, "
                    f"page bottom margin is y={rnd(ch - mb)}"
                )
            section.update({
                "top": band_top,
                "labelY": label_y,
                "firstRow": first_row,
                "lastRow": last_row,
                "bottom": bottom,
            })
            band_bottom = max(band_bottom, bottom)
        cursor = band_bottom + band_gap

    # Two sections in the SAME band must not occupy overlapping x bands.
    for band, members in bands.items():
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                a_right = a["x"] + a["width"]
                b_right = b["x"] + b["width"]
                if a["x"] < b_right + MIN_H_GAP and b["x"] < a_right + MIN_H_GAP:
                    raise SpecError(
                        f"OVERLAP: band {band!r} sections {a['id']} and {b['id']} "
                        f"x bands are closer than {MIN_H_GAP:g}px"
                    )

    primary = text(spec.get("primary"), "", "primary")
    if primary and primary not in used_ids:
        raise SpecError(f"primary {primary!r} is not a section id")
    if not primary:
        primary = sections[0]["id"]

    header = spec.get("header") or {}
    weekdays = header.get("weekdays", False)
    if not isinstance(weekdays, bool):
        raise SpecError("header.weekdays must be true or false")
    weekday_x = cw - mr - 208.0
    if weekdays and not (mr <= weekday_x and weekday_x + 7 * 32 <= cw - mr + 32):
        raise SpecError("header.weekdays do not fit inside the right margin")

    stickers = spec.get("stickers") or []
    if not isinstance(stickers, list):
        raise SpecError("stickers must be a list")
    for sticker in stickers:
        if not isinstance(sticker, dict):
            raise SpecError("each sticker must be an object")
        sid = ident(sticker.get("id"), "sticker.id")
        pos = sticker.get("at")
        if not isinstance(pos, list) or len(pos) != 2:
            raise SpecError(f"sticker {sid}: at must be [x, y]")
        sx, sy = num(pos[0], -1, "sticker.x"), num(pos[1], -1, "sticker.y")
        if not (ml <= sx <= cw - mr and 0 <= sy <= ch - mb):
            raise SpecError(f"sticker {sid}: at {pos} is outside the page margins")
        shape = text(sticker.get("shape"), "star", "sticker.shape")
        if shape not in ("paperclip", "star", "tag") and "elements" not in sticker:
            raise SpecError(f"sticker {sid}: unknown shape {shape!r} and no custom elements")
        sticker["_id"] = sid

    return {
        "id": template_id,
        "title": text(spec.get("title"), template_id.replace("-", " ").title(), "title"),
        "category": category,
        "tags": tags,
        "description": text(spec.get("description"), "", "description"),
        "cw": cw, "ch": ch, "ml": ml, "mr": mr, "mt": mt, "mb": mb,
        "gap": gap, "label_h": label_h,
        "header": header, "weekday_x": weekday_x,
        "sections": sections, "primary": primary,
        "separators": spec.get("separators") or [],
        "dividers": spec.get("dividers") or [],
        "stickers": stickers,
    }


# --- SVG emission --------------------------------------------------------------

STICKER_SHAPES = {
    "paperclip": (
        '<path d="M-7 -24 V20 a7 7 0 0 0 14 0 V-26 a9 9 0 0 0 -18 0 V26" '
        'fill="none" stroke="#8a8a8a" stroke-width="3" stroke-linecap="round"/>'
    ),
    "star": (
        '<polygon points="0,-18 5,-5 18,0 5,5 0,18 -5,5 -18,0 -5,-5" fill="#b8b8b8"/>'
    ),
    "tag": (
        '<rect x="-20" y="-14" width="40" height="28" rx="6" fill="#d8d8d8" '
        'stroke="#9a9a9a" stroke-width="1.5"/>'
        '<circle cx="-10" cy="0" r="3" fill="#8a8a8a"/>'
    ),
}


def emit_svg(plan):
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{rnd(plan["cw"])}" '
        f'height="{rnd(plan["ch"])}" viewBox="0 0 {rnd(plan["cw"])} {rnd(plan["ch"])}">'
    ]
    alpha = ROLE_ALPHA["structural"]

    # structural: explicit separators plus any section boundary flagged for one
    structural = []
    explicit_y = []
    for item in plan["separators"]:
        if not isinstance(item, dict):
            raise SpecError("separators entries must be objects")
        y = num(item.get("y"), 0, "separator.y")
        explicit_y.append(y)
        x1 = num(item.get("x1"), plan["ml"], "separator.x1")
        x2 = num(item.get("x2"), plan["cw"] - plan["mr"], "separator.x2")
        w = num(item.get("w"), 2.0, "separator.w")
        structural.append((x1, y, x2, y, w))
    for section in plan["sections"]:
        if section["separator"]:
            y = section["top"] - plan["gap"] / 2.0
            if any(abs(y - other) < 12.0 for other in explicit_y):
                continue  # an explicit rule already sits at this boundary
            structural.append((section["x"], y, section["x"] + section["width"], y, 2.0))
    if structural:
        out.append(f'  <g id="structural" fill="none" stroke="#5d5d5d" stroke-opacity="{alpha}">')
        for x1, y1, x2, y2, w in structural:
            out.append(f'    <path d="M{rnd(x1)} {rnd(y1)} H{rnd(x2)}" stroke-width="{rnd(w)}"/>')
        out.append("  </g>")

    # guide: vertical dividers and the optional weekday underline
    guide = []  # (x1, y1, x2, y2, width)
    for item in plan["dividers"]:
        if not isinstance(item, dict):
            raise SpecError("dividers entries must be objects")
        x = num(item.get("x"), 0, "divider.x")
        top = num(item.get("top"), 0, "divider.top")
        bottom = num(item.get("bottom"), plan["ch"], "divider.bottom")
        w = num(item.get("w"), 0.9, "divider.w")
        guide.append((x, top, x, bottom, w))
    if plan["header"].get("weekdays"):
        y = plan["mt"] + 86.0
        guide.append((plan["weekday_x"] - 20.0, y, plan["weekday_x"] + 7 * 32, y, 0.9))
    if guide:
        out.append(f'  <g id="guide" fill="none" stroke="#9a9a9a" stroke-opacity="{ROLE_ALPHA["guide"]}">')
        for x1, y1, x2, y2, w in guide:
            if abs(y2 - y1) < 1e-6:
                out.append(f'    <path d="M{rnd(x1)} {rnd(y1)} H{rnd(x2)}" stroke-width="{rnd(w)}"/>')
            else:
                out.append(f'    <path d="M{rnd(x1)} {rnd(y1)} V{rnd(y2)}" stroke-width="{rnd(w)}"/>')
        out.append("  </g>")

    # labels: header title/date and section labels
    header = plan["header"]
    title = text(header.get("title"), plan["title"].upper(), "header.title")
    out.append(f'  <g id="label" fill="#6d6d6d" fill-opacity="{ROLE_ALPHA["label"]}" '
               'font-family="sans-serif">')
    out.append(
        f'    <text x="{rnd(plan["ml"])}" y="{rnd(plan["mt"] + 68)}" '
        f'font-size="{rnd(num(header.get("titleSize"), 27, "header.titleSize"))}" '
        f'font-weight="700" letter-spacing="2">{esc(title)}</text>'
    )
    date_label = header.get("dateLabel")
    if date_label:
        out.append(
            f'    <text x="{rnd(plan["ml"])}" y="{rnd(plan["mt"] + 114)}" '
            f'font-size="16" font-weight="500" letter-spacing="1">{esc(date_label)}</text>'
        )
    for section in plan["sections"]:
        out.append(
            f'    <text x="{rnd(section["x"])}" y="{rnd(section["labelY"])}" '
            f'font-size="19" font-weight="700" letter-spacing="1.5">{esc(section["label"])}</text>'
        )
    out.append("  </g>")

    if header.get("weekdays"):
        out.append(f'  <g id="label-muted" fill="#8a8a8a" fill-opacity="{ROLE_ALPHA["label-muted"]}" '
                   'font-family="sans-serif" font-size="17" text-anchor="middle">')
        for i, day in enumerate("SMTWTFS"):
            out.append(f'    <text x="{rnd(plan["weekday_x"] + i * 32)}" '
                       f'y="{rnd(plan["mt"] + 76)}">{day}</text>')
        out.append("  </g>")

    # rule groups: one per section, uniform alpha so the compiler makes one layer
    for section in plan["sections"]:
        sid = section["id"]
        out.append(f'  <g id="rule-{sid}" fill="none" stroke="#7c7c7c" '
                   f'stroke-width="1.2" stroke-opacity="{ROLE_ALPHA["rule"]}">')
        line_x = section["x"] + section["lineInset"]
        line_right = section["x"] + section["width"]
        for row in range(section["rows"]):
            y = section["firstRow"] + row * section["pitch"]
            out.append(f'    <path d="M{rnd(line_x)} {rnd(y)} H{rnd(line_right)}"/>')
            if section["kind"] == "checklist":
                box = section["checkbox"]
                bx = num(box.get("x"), section["x"], "checkbox.x")
                size = num(box.get("size"), 22, "checkbox.size")
                rx = num(box.get("rx"), 4, "checkbox.rx")
                out.append(
                    f'    <rect x="{rnd(bx)}" y="{rnd(y - size / 2.0)}" '
                    f'width="{rnd(size)}" height="{rnd(size)}" rx="{rnd(rx)}" stroke-width="1.1"/>'
                )
            elif section["kind"] == "timed":
                tm = section["time"]
                tx = num(tm.get("x"), plan["ml"], "time.x")
                first_hour = int(num(tm.get("firstHour"), 8, "time.firstHour"))
                size = num(tm.get("size"), 18, "time.size")
                hour = (first_hour + row) % 24
                out.append(
                    f'    <text x="{rnd(tx)}" y="{rnd(y - 8)}" fill="#8a8a8a" '
                    f'fill-opacity="{ROLE_ALPHA["rule"]}" font-family="sans-serif" '
                    f'font-size="{rnd(size)}">{hour:02d}:00</text>'
                )
        out.append("  </g>")

    # stickers: separate editable items, never part of a ruling group
    for sticker in plan["stickers"]:
        sx, sy = sticker["at"]
        inner = sticker.get("elements")
        if inner is None:
            inner = STICKER_SHAPES[text(sticker.get("shape"), "star", "sticker.shape")]
        elif not isinstance(inner, list) or any(not isinstance(e, str) for e in inner):
            raise SpecError(f"sticker {sticker['_id']}: elements must be a list of SVG strings")
        out.append(f'  <g id="sticker-{sticker["_id"]}" transform="translate({rnd(sx)} {rnd(sy)})">')
        out.extend("    " + element for element in (inner if isinstance(inner, list) else [inner]))
        out.append("  </g>")

    out.append("</svg>")
    return "\n".join(out) + "\n"


def emit_meta(plan):
    repeats = {}
    for section in plan["sections"]:
        repeats[section["id"]] = {
            "group": "rule-" + section["id"],
            "anchor": rnd(section["firstRow"]),
            "base": rnd(section["pitch"]),
            "limit": rnd(section["bottom"]),
        }
    meta = {
        "title": plan["title"],
        "category": plan["category"],
        "tags": plan["tags"],
        "description": plan["description"],
        "layout": {"primary": plan["primary"], "repeats": repeats},
    }
    return json.dumps(meta, indent=2, ensure_ascii=False) + "\n"


SAMPLE = {
    "id": "focus-day",
    "title": "Focus Day",
    "category": "Planners",
    "tags": ["daily", "focus", "planner"],
    "description": "A4 daily page with priorities, an hourly schedule, a to-do column and notes.",
    "canvas": {"w": 1240, "h": 1754},
    "margin": {"left": 60, "right": 60, "top": 36, "bottom": 40},
    "gap": 30,
    "headerHeight": 180,
    "header": {"title": "FOCUS DAY", "dateLabel": "DATE", "weekdays": True},
    "primary": "schedule",
    "separators": [{"y": 228, "x1": 60, "x2": 1180, "w": 2.1}],
    "dividers": [{"x": 722, "top": 490, "bottom": 1694}],
    "sections": [
        {
            "id": "focus", "band": "a", "column": "main", "label": "TOP PRIORITIES", "kind": "checklist",
            "x": 60, "width": 1120, "rows": 3, "pitch": 38, "lineInset": 44,
            "checkbox": {"x": 60, "size": 22, "rx": 4}, "separator": True,
        },
        {
            "id": "schedule", "band": "b", "column": "left", "label": "SCHEDULE", "kind": "timed",
            "x": 150, "width": 550, "rows": 10, "pitch": 78, "lineInset": 0,
            "time": {"x": 60, "firstHour": 8, "size": 18},
        },
        {
            "id": "notes_left", "band": "c", "column": "left", "label": "NOTES", "kind": "lines",
            "x": 60, "width": 640, "rows": 6, "pitch": 35, "lineInset": 0,
        },
        {
            "id": "todo", "band": "b", "column": "right", "label": "TO-DO", "kind": "checklist",
            "x": 748, "width": 432, "rows": 15, "pitch": 34, "lineInset": 36,
            "checkbox": {"x": 748, "size": 20, "rx": 4},
        },
        {
            "id": "notes_right", "band": "c", "column": "right", "label": "NOTES", "kind": "lines",
            "x": 748, "width": 432, "rows": 11, "pitch": 36, "lineInset": 0,
        },
    ],
    "stickers": [
        {"id": "paperclip", "shape": "paperclip", "at": [1146, 62]},
        {"id": "spark", "shape": "star", "at": [300, 80]},
    ],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec", nargs="?", help="path to the template spec JSON")
    parser.add_argument("--check", action="store_true", help="verify generated files are current")
    parser.add_argument("--sample", action="store_true", help="print a starter spec and exit")
    parser.add_argument("--svg-dir", default=SVG_DIR)
    parser.add_argument("--meta-dir", default=META_DIR)
    args = parser.parse_args()

    if args.sample:
        print(json.dumps(SAMPLE, indent=2, ensure_ascii=False))
        return 0
    if not args.spec:
        parser.error("give a spec JSON path, or use --sample")

    try:
        with open(args.spec, encoding="utf-8") as handle:
            spec = json.load(handle)
        plan = build_plan(spec)
        svg = emit_svg(plan)
        meta = emit_meta(plan)
    except (OSError, ValueError, SpecError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    svg_path = os.path.join(args.svg_dir, plan["id"] + ".svg")
    meta_path = os.path.join(args.meta_dir, plan["id"] + ".json")
    if args.check:
        failed = False
        for path, content in ((svg_path, svg), (meta_path, meta)):
            current = open(path, encoding="utf-8").read() if os.path.exists(path) else None
            if current != content:
                print(f"{path} is out of date")
                failed = True
        if not failed:
            print(f"{plan['id']}: generated files are up to date")
        return 1 if failed else 0

    os.makedirs(args.svg_dir, exist_ok=True)
    os.makedirs(args.meta_dir, exist_ok=True)
    with open(svg_path, "w", encoding="utf-8") as handle:
        handle.write(svg)
    with open(meta_path, "w", encoding="utf-8") as handle:
        handle.write(meta)
    print(f"wrote {svg_path} and {meta_path}")
    print(f"  {len(plan['sections'])} repeat sections, {len(plan['stickers'])} stickers, "
          f"primary={plan['primary']}")
    print("next: python compile_templates.py && python generate_templates_json.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
