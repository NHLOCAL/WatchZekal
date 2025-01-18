import json
import re
import difflib

def is_hebrew(text):
    """Checks if the text contains Hebrew characters."""
    return bool(re.search('[\u0590-\u05FF]', text))

def remove_hebrew_punctuation(text):
    """Removes Hebrew punctuation from a string."""
    if not isinstance(text, str):
        return text
    return re.sub(r'[\u0591-\u05C7]', '', text)

def process_json(data):
    """Recursively processes a JSON object to remove Hebrew punctuation from Hebrew text."""
    if isinstance(data, dict):
        return {k: process_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [process_json(item) for item in data]
    elif isinstance(data, str):
        if is_hebrew(data):
            return remove_hebrew_punctuation(data)
        else:
            return data
    else:
        return data

def compare_json_files(file1_path, file2_path):
    """Compares two JSON files and prints the differences."""
    try:
        with open(file1_path, 'r', encoding='utf-8') as f1:
            data1 = json.load(f1)
        with open(file2_path, 'r', encoding='utf-8') as f2:
            data2 = json.load(f2)

        # Convert JSON objects to strings for line-by-line comparison
        str1 = json.dumps(data1, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
        str2 = json.dumps(data2, ensure_ascii=False, indent=2, sort_keys=True).splitlines()

        # Calculate differences
        diff = difflib.unified_diff(str1, str2, fromfile=file1_path, tofile=file2_path)

        diff_lines = list(diff)
        if diff_lines:
            print("Differences between files:")
            for line in diff_lines:
                print(line)
        else:
            print("Files are identical.")

    except FileNotFoundError:
        print("Error: One or both files not found.")
    except json.JSONDecodeError:
        print("Error: Could not decode one or both JSON files.")

def main(json_file_path, comparison_file_path):
    """Main function to process and compare the JSON files."""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        processed_data = process_json(data)

        # Directly overwrite the original file with processed data
        with open(json_file_path, 'w', encoding='utf-8') as outfile:
            json.dump(processed_data, outfile, ensure_ascii=False, indent=2)
        print(f"Processed data saved to: {json_file_path}")

        if comparison_file_path:
            compare_json_files(json_file_path, comparison_file_path)

    except FileNotFoundError:
        print(f"Error: File not found at '{json_file_path}'.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON file at '{json_file_path}'.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    json_file_path = input("Enter the full path to the JSON file: ")
    comparison_file_path = input("Enter the full path to the comparison file (leave empty to skip comparison): ")
    if not comparison_file_path:
        comparison_file_path = None
    main(json_file_path, comparison_file_path)