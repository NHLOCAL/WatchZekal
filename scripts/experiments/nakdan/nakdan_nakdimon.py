import json
from nakdimon_ort import Nakdimon
import sys

def nakdimon_text(text, model_path="nakdimon.onnx"):
    """
    Applies Nakdimon to a given text.

    Args:
        text (str): The input text to be processed.
        model_path (str): The path to the Nakdimon ONNX model file.

    Returns:
        str: The diacritized text.
    """
    nakdimon = Nakdimon(model_path)
    return nakdimon.compute(text)


def process_json_with_nakdimon(json_file_path):
    """
    Reads a JSON file, applies Nakdimon to Hebrew text fields, including translations,
    and writes the modified data back to a JSON file (with '_dotted' suffix).

    Args:
        json_file_path (str): Path to the input JSON file.
    """
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {json_file_path}")
        return
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in {json_file_path}")
        return


    if 'story' in data and 'text' in data['story']:
          for item in data['story']['text']:
                if 'hebrew' in item:
                     item['hebrew'] = nakdimon_text(item['hebrew'])

    if 'vocabulary' in data:
        for vocab_item in data['vocabulary']:
            if 'translation' in vocab_item:
                 vocab_item['translation'] = nakdimon_text(vocab_item['translation'])
    
    if 'comprehension_questions' in data:
        for question_data in data['comprehension_questions']:
           if 'question' in question_data:
               question_data['question'] = nakdimon_text(question_data['question'])
           if 'options' in question_data:
               for i, option in enumerate(question_data['options']):
                   question_data['options'][i] = nakdimon_text(option)

    if 'call_to_action' in data and 'text' in data['call_to_action']:
        data['call_to_action']['text'] = nakdimon_text(data['call_to_action']['text'])


    output_file_path = json_file_path.replace('.json', '_dotted.json')

    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Processed JSON with Nakdimon and saved to {output_file_path}")



if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <input_json_file>")
    else:
        input_json_file = sys.argv[1]
        process_json_with_nakdimon(input_json_file)