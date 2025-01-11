import json
import re
import difflib

def remove_hebrew_punctuation(text):
    """Removes Hebrew punctuation from a string."""
    if not isinstance(text, str):
         return text
    return re.sub(r'[\u0591-\u05C7]', '', text)

def process_story(data):
    """Processes a story JSON object to remove Hebrew punctuation."""
    processed_data = data.copy()

    # Remove nikud from top-level fields
    if "video_title" in processed_data:
        processed_data["video_title"] = remove_hebrew_punctuation(processed_data["video_title"])
    if "language_level" in processed_data:
        processed_data["language_level"] = remove_hebrew_punctuation(processed_data["language_level"])
    if "story_type" in processed_data:
        processed_data["story_type"] = remove_hebrew_punctuation(processed_data["story_type"])


    if "story" in processed_data:
      if "title" in processed_data["story"]:
            processed_data["story"]["title"] = remove_hebrew_punctuation(processed_data["story"]["title"])
      
      if "text" in processed_data["story"]:
        for item in processed_data["story"]["text"]:
            if "hebrew" in item:
                item["hebrew"] = remove_hebrew_punctuation(item["hebrew"])

    if "vocabulary" in processed_data:
       for item in processed_data["vocabulary"]:
            if "translation" in item:
               item["translation"] = remove_hebrew_punctuation(item["translation"])

    if "comprehension_questions" in processed_data:
        for question in processed_data["comprehension_questions"]:
             if "question" in question:
                  question["question"]= remove_hebrew_punctuation(question["question"])
             if "options" in question:
                 for i in range(len(question["options"])):
                    question["options"][i] = remove_hebrew_punctuation(question["options"][i])

    if "call_to_action" in processed_data and "text" in processed_data["call_to_action"]:
        processed_data["call_to_action"]["text"] = remove_hebrew_punctuation(processed_data["call_to_action"]["text"])
                

    return processed_data

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

        processed_data = process_story(data)

        output_file_path = json_file_path.replace(".json", "_no_punctuation.json")
        with open(output_file_path, 'w', encoding='utf-8') as outfile:
            json.dump(processed_data, outfile, ensure_ascii=False, indent=2)
        print(f"Processed data saved to: {output_file_path}")
        
        if comparison_file_path:
            compare_json_files(output_file_path, comparison_file_path)

    except FileNotFoundError:
        print(f"Error: File not found at '{json_file_path}'.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON file at '{json_file_path}'.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    json_file_num = input("add num of file >>>")
    json_file_path = f"story{json_file_num}.json" 
    comparison_file_path = input("Enter path to comparison file (leave empty to skip comparison): ")
    if not comparison_file_path:
         comparison_file_path = None
    main(json_file_path, comparison_file_path)
