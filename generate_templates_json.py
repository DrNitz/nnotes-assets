#!/usr/bin/env python3
"""Build templates/templates_data.json for the Nnotes app template catalog.

Scans templates/svg/*.svg, merges optional sidecar data from templates/meta/<name>.json,
and writes templates/templates_data.json. Values already present in the registry are
kept when a sidecar is absent, so hand edits survive a rebuild.

Usage:
    python generate_templates_json.py            # write the registry
    python generate_templates_json.py --check    # exit 1 if the registry is stale
"""

import argparse
import json
import os
import re
import sys

REPO_URL = "https://raw.githubusercontent.com/DrNitz/nnotes-assets/main"
SVG_DIR = "templates/svg"
META_DIR = "templates/meta"
OUT_FILE = "templates/templates_data.json"

APP_CATEGORIES = ["Basic", "Academic", "Planners"]


def prettify(stem):
    words = [w for w in re.split(r"[-_ ]+", stem) if w]
    return " ".join(w[:1].upper() + w[1:] for w in words)


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
        return None


def check_svg(filename):
    path = os.path.join(SVG_DIR, filename)
    try:
        with open(path, encoding="utf-8") as handle:
            head = handle.read(4096)
    except OSError as exc:
        print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
        return
    if "<svg" not in head:
        print(f"warning: {path} has no <svg> root", file=sys.stderr)
    if "viewBox" not in head:
        print(f"warning: {path} has no viewBox, the app may not size it", file=sys.stderr)


def build_entry(filename, previous):
    stem = os.path.splitext(filename)[0]
    meta = load_json(os.path.join(META_DIR, stem + ".json")) or {}
    prev = previous.get(stem, {})
    raw_url = f"{REPO_URL}/{SVG_DIR}/{filename}"

    def pick(key):
        if meta.get(key) not in (None, "", []):
            return meta[key]
        if prev.get(key) not in (None, "", []):
            return prev[key]
        return None

    title = pick("title") or prettify(stem)
    entry = {
        "id": stem,
        "title": title,
        "category": pick("category") or "Basic",
        "tags": pick("tags") or [w.lower() for w in title.split()],
    }
    description = pick("description")
    if description:
        entry["description"] = description
    entry["url"] = pick("url") or raw_url
    entry["previewUrl"] = pick("previewUrl") or pick("url") or raw_url
    pattern = pick("matchingPattern")
    if pattern:
        entry["matchingPattern"] = pattern
    return entry


def build_registry():
    previous = {}
    old = load_json(OUT_FILE) or {}
    for item in old.get("templates", []):
        if isinstance(item, dict) and item.get("id"):
            previous[item["id"]] = item

    entries = []
    if os.path.isdir(SVG_DIR):
        for name in sorted(os.listdir(SVG_DIR)):
            if not name.lower().endswith(".svg"):
                continue
            check_svg(name)
            entries.append(build_entry(name, previous))

    used = [entry["category"] for entry in entries]
    categories = list(APP_CATEGORIES)
    for name in used:
        if name not in categories:
            categories.append(name)

    return {"version": 1, "categories": categories, "templates": entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args()

    data = build_registry()
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        current = None
        if os.path.exists(OUT_FILE):
            with open(OUT_FILE, encoding="utf-8") as handle:
                current = handle.read()
        if current != text:
            print(f"{OUT_FILE} is out of date, run generate_templates_json.py")
            return 1
        print(f"{OUT_FILE} is up to date ({len(data['templates'])} templates)")
        return 0

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"Wrote {OUT_FILE} with {len(data['templates'])} templates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
