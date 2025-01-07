import json
import re

def remove_hebrew_punctuation(text):
    """Removes Hebrew punctuation from a string.

    Args:
        text: The input string.

    Returns:
        The string with Hebrew punctuation removed.
    """
    if not isinstance(text, str):
         return text
    return re.sub(r'[\u0591-\u05C7]', '', text)

def process_story(data):
    """Processes a story JSON object to remove Hebrew punctuation.

    Args:
        data: A dictionary representing the story JSON object.

    Returns:
        A new dictionary with Hebrew punctuation removed.
    """
    processed_data = data.copy()

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

def main(json_file_path):
    """Loads a JSON file, processes the text, and saves the result.

    Args:
        json_file_path: Path to the JSON file to process.
    """
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        processed_data = process_story(data)

        output_file_path = json_file_path.replace(".json", "_no_punctuation.json")
        with open(output_file_path, 'w', encoding='utf-8') as outfile:
            json.dump(processed_data, outfile, ensure_ascii=False, indent=2)
        print(f"Processed data saved to: {output_file_path}")
    except FileNotFoundError:
        print(f"Error: File not found at '{json_file_path}'.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON file at '{json_file_path}'.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    json_file_num = input("add num of file >>>")
    json_file_path = f"story{json_file_num}.json" 
    main(json_file_path)
