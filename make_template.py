#!/usr/bin/env python3
"""One-step template packer: AI-authored SVG -> everything the app needs.

    python make_template.py path/to/ai-template.svg

It validates the SVG against the Nnotes authoring contract, infers the meta sidecar
(repeat anchors, pitches, limits) from the rule groups, copies it into templates/svg/,
then runs compile_templates.py and generate_templates_json.py for you.

Output is the exact list of files to upload to GitHub.

Optional flags:
    --id NAME          override the template id (default: the SVG file's stem)
    --title TEXT       override the catalog title
    --category NAME    Basic | Academic | Planners (default: Basic)
    --primary NAME     repeat group that seeds the spacing slider (default: widest pitch)
    --tags a,b,c       comma separated tags
    --description TEXT catalog description
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SVG_DIR = ROOT / "templates" / "svg"
META_DIR = ROOT / "templates" / "meta"
ROLES = ("structural", "rule", "guide", "label", "label-muted", "decor", "sticker")
FORBIDDEN = ("<image", "<style", "<script", "href=", "url(", "@import", "xlink:")


class PackError(Exception):
    pass


def local(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def fnum(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def fnum_attr(el, name, default=0.0):
    return fnum(el.get(name), default)


def prettify(stem):
    parts = [p for p in re.split(r"[-_ ]+", stem) if p]
    return " ".join(p[:1].upper() + p[1:] for p in parts)


def check_source(source):
    raw = source.read_text(encoding="utf-8")
    lower = raw.lower()
    for token in FORBIDDEN:
        if token in lower:
            raise PackError(f"SVG uses forbidden external/CSS feature {token!r}")
    if "<svg" not in lower:
        raise PackError("file has no <svg> root")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise PackError(f"SVG is not well-formed XML: {exc}")
    if local(root.tag) != "svg":
        raise PackError("root element must be <svg>")
    return root


def check_canvas(root):
    view = (root.get("viewBox") or "").replace(",", " ").split()
    if len(view) != 4:
        raise PackError("root needs viewBox=\"0 0 1240 1754\"")
    w, h = fnum(view[2]), fnum(view[3])
    if abs(w - 1240.0) > 0.1 or abs(h - 1754.0) > 0.1:
        raise PackError(f"canvas must be 1240x1754 (A4 at 150 dpi), got {w:g}x{h:g}")
    return w, h


def role_of(group_id):
    if not group_id:
        return None
    head = group_id.split("-")[0]
    return head if head in ROLES else None


def collect_groups(root):
    groups = []
    for child in root:
        tag = local(child.tag)
        if tag in ("defs", "title", "desc", "metadata"):
            continue
        if tag != "g":
            raise PackError(
                f"element <{tag}> sits directly in <svg>; every visible element must be "
                "inside a role group (structural, rule-*, guide, label, decor, sticker-*)"
            )
        gid = child.get("id") or ""
        role = role_of(gid)
        if role is None:
            raise PackError(
                f"group id {gid!r} has no recognized role prefix; expected one of "
                "structural, rule-<name>, guide, label, decor, sticker-<id>"
            )
        groups.append((gid, role, child))
    if not groups:
        raise PackError("SVG has no role groups")
    return groups


def path_row_y(d):
    """Return y if this path is a horizontal row (M x y H x2), else None."""
    if not d:
        return None
    match = re.fullmatch(r"\s*M\s*(-?[\d.]+)[ ,]+(-?[\d.]+)\s+H\s*(-?[\d.]+)\s*Z?\s*", d, re.I)
    if match:
        return fnum(match.group(2))
    match = re.fullmatch(r"\s*M\s*(-?[\d.]+)[ ,]+(-?[\d.]+)\s+L\s*(-?[\d.]+)[ ,]+(-?[\d.]+)\s*", d, re.I)
    if match and abs(fnum(match.group(2)) - fnum(match.group(4))) < 0.5:
        return fnum(match.group(2))
    return None


def row_geometry(group):
    """Return (sorted row ys, x1, x2) for a rule group."""
    ys = []
    xs = []
    for el in group.iter():
        tag = local(el.tag)
        if tag == "path":
            y = path_row_y(el.get("d"))
            if y is not None:
                ys.append(y)
                nums = [fnum(v) for v in re.findall(r"-?[\d.]+", el.get("d") or "")]
                if len(nums) >= 3:
                    xs.extend((nums[0], nums[-1]))
        elif tag == "line":
            y1, y2 = fnum_attr(el, "y1"), fnum_attr(el, "y2")
            if abs(y1 - y2) < 0.5:
                ys.append(y1)
                xs.extend((fnum_attr(el, "x1"), fnum_attr(el, "x2")))
    return sorted(set(round(v, 1) for v in ys)), (min(xs) if xs else 0.0), (max(xs) if xs else 0.0)


def cluster(values, tol=1.0):
    result = []
    for value in values:
        if result and value - result[-1][-1] <= tol:
            result[-1].append(value)
        else:
            result.append([value])
    return [round(sum(c) / len(c), 1) for c in result]


def infer_repeats(groups, page_h):
    rule_groups = [(gid, el) for gid, role, el in groups if role == "rule"]
    if not rule_groups:
        raise PackError("no rule-* groups found; spacing needs at least one rule group")

    label_ys = []
    for gid, role, el in groups:
        if role in ("label", "label-muted"):
            for node in el.iter():
                if local(node.tag) == "text":
                    label_ys.append(fnum_attr(node, "y"))
        elif role == "structural":
            # A separator is just as hard a boundary as the next section's label.
            rows, _, _ = row_geometry(el)
            label_ys.extend(rows)
    label_ys.sort()

    repeats = {}
    bands = []
    for gid, el in rule_groups:
        name = gid[len("rule-"):] if gid.startswith("rule-") else gid
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise PackError(f"rule group {gid!r} needs a simple name after 'rule-'")
        rows, x1, x2 = row_geometry(el)
        rows = cluster(rows)
        if len(rows) < 2:
            raise PackError(
                f"rule group {gid!r} has fewer than 2 horizontal rows; "
                "author rows as <path d=\"M x y H x2\"/> so the pitch can be inferred"
            )
        diffs = [round(rows[i + 1] - rows[i], 1) for i in range(len(rows) - 1)]
        pitch = max(set(diffs), key=diffs.count)
        if pitch < 8.0:
            raise PackError(f"rule group {gid!r} inferred pitch {pitch:g} is below 8px")
        if any(abs(d - pitch) > 0.6 for d in diffs):
            raise PackError(
                f"rule group {gid!r} has uneven row spacing {diffs}; every row must use one pitch"
            )
        anchor = rows[0]
        last = rows[-1]
        later = [y for y in label_ys if y > last + 2.0]
        limit = round(min(later) - 8.0, 1) if later else page_h - 40.0
        if limit <= last:
            limit = round(last + pitch * 0.5, 1)
        repeats[name] = {
            "group": gid,
            "anchor": anchor,
            "base": pitch,
            "limit": limit,
        }
        bands.append((name, anchor, last, x1, x2))

    # Cross-group overlap: sharing y requires separated x bands.
    for i, a in enumerate(bands):
        for b in bands[i + 1:]:
            if a[2] < b[1] or b[2] < a[1]:
                continue
            if a[3] < b[4] + 16.0 and b[3] < a[4] + 16.0:
                raise PackError(
                    f"OVERLAP: repeats {a[0]!r} and {b[0]!r} share rows and their x bands "
                    "are closer than 16px"
                )
    return repeats


def check_alpha(groups):
    noisy = []
    for gid, role, el in groups:
        if role != "rule":
            continue
        alphas = set()
        for node in [el] + list(el.iter()):
            for key in ("stroke-opacity", "fill-opacity"):
                if node.get(key) is not None:
                    alphas.add(round(fnum(node.get(key), 1.0), 2))
        if len(alphas) > 1:
            noisy.append(f"{gid}: {sorted(alphas)}")
    return noisy


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("svg", help="SVG produced by the AI")
    parser.add_argument("--id", default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument("--category", default="Basic")
    parser.add_argument("--primary", default=None)
    parser.add_argument("--tags", default="")
    parser.add_argument("--description", default="")
    args = parser.parse_args()

    source = Path(args.svg).expanduser().resolve()
    if not source.is_file():
        print(f"error: no such file: {source}", file=sys.stderr)
        return 1
    if source.parent == SVG_DIR:
        print("error: give the original AI file, not the generated copy in templates/svg/", file=sys.stderr)
        return 1

    try:
        root = check_source(source)
        page_w, page_h = check_canvas(root)
        groups = collect_groups(root)
        repeats = infer_repeats(groups, page_h)
        template_id = re.sub(r"[^a-z0-9_-]+", "-", (args.id or source.stem).lower()).strip("-")
        if not template_id:
            raise PackError("template id is empty")
        if args.category not in ("Basic", "Academic", "Planners"):
            raise PackError("category must be Basic, Academic or Planners")
        if args.primary and args.primary not in repeats:
            raise PackError(f"--primary {args.primary!r} is not a repeat group: {list(repeats)}")
        primary = args.primary or max(repeats, key=lambda k: repeats[k]["base"])

        meta = {
            "title": args.title or prettify(template_id),
            "category": args.category,
            "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
            "description": args.description,
            "layout": {"primary": primary, "repeats": repeats},
        }

        target_svg = SVG_DIR / (template_id + ".svg")
        target_meta = META_DIR / (template_id + ".json")
        target_model = ROOT / "templates" / "model" / (template_id + ".json")
        target_registry = ROOT / "templates" / "templates_data.json"

        SVG_DIR.mkdir(parents=True, exist_ok=True)
        META_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target_svg)
        target_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        # Reuse the existing toolchain so the output is byte-identical to a manual run.
        for script in ("compile_templates.py", "generate_templates_json.py"):
            result = subprocess.run([sys.executable, script], cwd=ROOT, capture_output=True, text=True)
            if result.returncode != 0:
                raise PackError(f"{script} failed:\n{result.stdout}{result.stderr}")
        noisy = check_alpha(groups)
    except PackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Packed '{template_id}' ({len(repeats)} repeat groups, primary={primary}).")
    for warning in noisy:
        print(f"warning: {warning} uses more than one alpha -> extra paint layers")
    print("\nUpload these files to GitHub:")
    for path in (target_svg, target_meta, target_model, target_registry):
        print("  " + str(path.relative_to(ROOT)))
    print("\nThen open Page Styles > Online in the app; the card is fetched on open.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
