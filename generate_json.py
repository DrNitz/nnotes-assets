import os
import json

REPO_URL = "https://raw.githubusercontent.com/DrNitz/nnotes-assets/main"
VALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.svg', '.webp')


def make_entry(folder_name, filename):
    import re
    file_id = os.path.splitext(filename)[0]
    title = re.sub(r'[-_]', ' ', file_id)
    title = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', title).strip().title()
    sheet = os.path.basename(folder_name)
    return {
        "id": file_id,
        "title": title,
        "tags": [t.lower() for t in title.split()] + [sheet.replace('-', ' ').lower()],
        "url": f"{REPO_URL}/{folder_name}/{filename}"
    }


def generate_json_for_folder(folder_name, output_file, category_name):
    if not os.path.exists(folder_name):
        print(f"Folder '{folder_name}' does not exist. Skipping.")
        return

    images = []
    for filename in sorted(os.listdir(folder_name)):
        if filename.lower().startswith(("freesvg_", "svgrepo_")):
            continue  # sourced stickers live in their own catalogs
        if filename.lower().endswith(VALID_EXTENSIONS):
            file_id = os.path.splitext(filename)[0]
            title = file_id.replace('-', ' ').replace('_', ' ').title()
            tags = [tag.lower() for tag in title.split()]
            images.append({
                "id": file_id,
                "title": title,
                "tags": tags,
                "url": f"{REPO_URL}/{folder_name}/{filename}"
            })

    data = {"categories": [{"name": category_name, "images": images}]}
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"Generated {output_file} with {len(images)} images.")


def generate_json_for_sheet_folders(root, output_file):
    """One category per sheet folder inside root (e.g. stickers_individual/<sheet>/*.svg)."""
    if not os.path.isdir(root):
        print(f"Folder '{root}' does not exist. Skipping.")
        return
    categories = []
    for folder in sorted(os.listdir(root)):
        path = os.path.join(root, folder)
        if not os.path.isdir(path):
            continue
        images = [make_entry(f"{root}/{folder}", f) for f in sorted(os.listdir(path))
                  if f.lower().endswith(VALID_EXTENSIONS)]
        if images:
            cat_name = folder.replace('-', ' ').replace('_', ' ').title()
            categories.append({"name": cat_name, "images": images})
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({"categories": categories}, f, indent=2)
    print(f"Generated {output_file} with {len(categories)} categories / "
          f"{sum(len(c['images']) for c in categories)} images.")


def generate_freesvg_catalog(sources_file="freesvg_sources.json", output_file="freesvg_stickers_data.json"):
    """Sourced CC0/MIT stickers stay in their own catalog, separate from the original groups."""
    if not os.path.exists(sources_file):
        print(f"File '{sources_file}' not found. Skipping.")
        return
    with open(sources_file, encoding="utf-8") as f:
        sources = json.load(f)
    images = []
    for item in sources:
        images.append({
            "id": item["id"],
            "title": item["title"],
            "tags": item["tags"],
            "url": f"{REPO_URL}/stickers/{item['file']}",
            "source": "freesvg",
            "author": item["author"],
            "license": item["license"],
            "licenseUrl": item["licenseUrl"],
            "sourceUrl": item["sourceUrl"],
        })
    data = {"categories": [{"name": "FreeSVG Picks", "images": images}]}
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Generated {output_file} with {len(images)} sourced stickers.")


def generate_svgrepo_catalog(sources_file="svgrepo_sources.json", output_file="svgrepo_stickers_data.json"):
    """Well-organised CC0-style packs from SVGRepo, kept separate from original groups."""
    if not os.path.exists(sources_file):
        print(f"File '{sources_file}' not found. Skipping.")
        return
    with open(sources_file, encoding="utf-8") as f:
        sources = json.load(f)
    by_category = {}
    for item in sources:
        by_category.setdefault(item["category"], []).append({
            "id": item["id"],
            "title": item["title"],
            "tags": item["tags"],
            "url": f"{REPO_URL}/stickers/{item['file']}",
            "source": "svgrepo",
            "author": item["author"],
            "license": item["license"],
            "licenseUrl": item["licenseUrl"],
            "sourceUrl": item["sourceUrl"],
        })
    data = {"categories": [{"name": name, "images": images} for name, images in by_category.items()]}
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Generated {output_file} with {len(sources)} sourced stickers.")


if __name__ == "__main__":
    generate_json_for_folder("stickers", "stickers_data.json", "General Stickers")
    generate_json_for_folder("frames", "frames_data.json", "Basic Frames")
    generate_json_for_sheet_folders("stickers_individual", "stickers_individual_data.json")
    generate_freesvg_catalog()
    generate_svgrepo_catalog()
