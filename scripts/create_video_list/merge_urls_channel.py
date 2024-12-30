import json

def load_json(file_path):
    """Load a JSON file and return its data."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"Error: File not found - {file_path}")
        exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in file - {file_path}")
        exit(1)

def save_json(file_path, data):
    """Save data to a JSON file."""
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def merge_json(original_data, new_data):
    """Merge new data into original data, avoiding duplicates by title and number of videos."""
    if isinstance(original_data, list) and isinstance(new_data, list):
        # Merge lists with unique playlists based on title and video count
        for new_item in new_data:
            if not any(
                existing_item['title'] == new_item['title'] and
                len(existing_item.get('videos', [])) == len(new_item.get('videos', []))
                for existing_item in original_data
            ):
                original_data.append(new_item)
        return original_data

    elif isinstance(original_data, dict) and isinstance(new_data, dict):
        # Merge dictionaries recursively
        for key, value in new_data.items():
            if key not in original_data:
                original_data[key] = value
            else:
                original_data[key] = merge_json(original_data[key], value)
        return original_data

    # If types do not match or data is primitive, prefer the original
    return original_data

def sort_playlists(playlists):
    """Sort playlists by specific criteria."""
    def sort_key(playlist):
        title = playlist['title']
        if title == "אנגלית זה קל - כל השלבים":
            return (0, title)
        elif "סיפורים באנגלית" in title:
            return (1, title)
        else:
            return (2, title)

    return sorted(playlists, key=sort_key)

def main():
    original_file = "videos.json"
    new_file = "channel_playlists_data.json"
    output_file = "videos2.json"

    original_data = load_json(original_file)
    new_data = load_json(new_file)

    merged_data = merge_json(original_data, new_data)

    # Sort playlists
    if 'playlists' in merged_data:
        merged_data['playlists'] = sort_playlists(merged_data['playlists'])

    save_json(output_file, merged_data)

    print(f"Merged and sorted data saved to {output_file}")

if __name__ == "__main__":
    main()
