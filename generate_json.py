import os
import json

REPO_URL = "https://raw.githubusercontent.com/DrNitz/nnotes-assets/main"

def generate_json_for_folder(folder_name, output_file, category_name):
    if not os.path.exists(folder_name):
        print(f"Folder '{folder_name}' does not exist. Skipping.")
        return

    images = []
    # Supported image extensions
    valid_extensions = ('.png', '.jpg', '.jpeg', '.svg', '.webp')

    for filename in sorted(os.listdir(folder_name)):
        if filename.lower().endswith(valid_extensions):
            # Generate ID, Title, and Tags based on the filename
            file_id = os.path.splitext(filename)[0]
            title = file_id.replace('-', ' ').replace('_', ' ').title()
            tags = [tag.lower() for tag in title.split()]

            images.append({
                "id": file_id,
                "title": title,
                "tags": tags,
                "url": f"{REPO_URL}/{folder_name}/{filename}"
            })

    data = {
        "categories": [
            {
                "name": category_name,
                "images": images
            }
        ]
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"Generated {output_file} with {len(images)} images.")

if __name__ == "__main__":
    # Generate for Stickers
    generate_json_for_folder("stickers", "stickers_data.json", "General Stickers")
    
    # Generate for Frames
    generate_json_for_folder("frames", "frames_data.json", "Basic Frames")
