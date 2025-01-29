import json
import os
import requests
import base64
from PIL import Image
from io import BytesIO
import re
import argparse
from deepdiff import DeepDiff

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("Error: GEMINI_API_KEY environment variable is not set.")
    exit()

SYSTEM_INST_TEMPLATE = """
אתה מודל שפה גדול שמקבל קבצי JSON המיועדים לבניית סרטונים ללימוד אנגלית.
על בסיס התוכן בקובץ, עליך ליצור קובץ JSON חדש וזהה לחלוטין שמלמד {target_language_iw} במקום אנגלית.
עליך להחליף את המילים באנגלית למילים ב{target_language_iw}, וכך גם את המשפטים לדוגמה.
הקפד לשמור על מבנה זהה של תוכן ושים לב ששמות השלבים, הקטעים והקריאה לפעולה ישארו בעברית!

הקובץ JSON המלא יסופק לך בהודעה הבאה.
עליך להחזיר קובץ JSON מתורגם מלא בתוך תגי קוד Markdown (```json ... ```).

הקפד על תרגום מדויק, ניסוח תקין ובאיכות גבוהה בשפה ה{target_language_iw}.
"""

conversation = []
TEMPERATURE = 0.6

def encode_image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        encoded_bytes = base64.b64encode(image_file.read())
        encoded_str = encoded_bytes.decode("utf-8")
    return encoded_str

def add_user_text(message: str):
    conversation.append({
        "role": "user",
        "parts": [
            {"text": message}
        ]
    })

def add_user_image(image_path: str, mime_type: str = "image/jpeg"):
    encoded_str = encode_image_to_base64(image_path)
    conversation.append({
        "role": "user",
        "parts": [
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": encoded_str
                }
            }
        ]
    })

def send_and_receive() -> str:
    payload = {
        "systemInstruction": {
            "role": "system",
            "parts": [
                {"text": SYSTEM_INST}
            ]
        },
        "contents": conversation,
        "generationConfig": {
            "temperature": TEMPERATURE,
            "topK": 64,
            "topP": 0.95,
            "maxOutputTokens": 65536,
            "responseMimeType": "text/plain"
        }
    }

    # אפשרות חילופית: gemini-2.0-flash-thinking-exp-01-21
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-exp-1206:generateContent"
    params = {"key": API_KEY}
    headers = {"Content-Type": "application/json"}

    resp_text = "NO_ANSWER"

    try:
        response = requests.post(url, params=params, headers=headers, json=payload)
        response.raise_for_status()

        resp_json = response.json()
        candidates = resp_json.get("candidates", [])
        if candidates:
            model_content = candidates[0].get("content", {})
            model_parts = model_content.get("parts", [])
            if model_parts:
                model_text = model_parts[0].get("text", "").strip()
                conversation.append({
                    "role": "model",
                    "parts": [
                        {"text": model_text}
                    ]
                })
                resp_text = model_text
            else:
                print("לא נמצא תוכן בתשובת המודל.")
        else:
            print("לא התקבלה תשובה מהמודל.")
    except requests.exceptions.RequestException as e:
        print(f"שגיאת בקשה ל-API: {e}")
        if response is not None:
            print(f"סטטוס קוד: {response.status_code}")
            print("תוכן התגובה:")
            print(response.text)
        else:
            print("לא התקבלה תגובה מהשרת.")

    return resp_text

def validate_json_structure(original_json, translated_json):
    """
    פונקציה רקורסיבית לווידוא שמבנה ה-JSON זהה בין שני אובייקטים.
    """
    if type(original_json) != type(translated_json):
        return False

    if isinstance(original_json, dict):
        if set(original_json.keys()) != set(translated_json.keys()):
            return False
        for key in original_json:
            if not validate_json_structure(original_json[key], translated_json[key]):
                return False
        return True
    elif isinstance(original_json, list):
        if len(original_json) != len(translated_json):
            return False
        for i in range(len(original_json)):
            if not validate_json_structure(original_json[i], translated_json[i]):
                return False
        return True
    else:
        return True

def compare_json_content(original_json, translated_json):
    """
    השוואת תוכן JSON וזיהוי שינויים בשדות שאינם 'word' או 'sentence'.
    מציג את השינויים במסוף.
    """
    diff = DeepDiff(original_json, translated_json, exclude_regex_paths=[r"root\['levels'\]\[\d+\]\['subtopics'\]\[\d+\]\['words'\]\[\d+\]\['word'\]", r"root\['levels'\]\[\d+\]\['subtopics'\]\[\d+\]\['words'\]\[\d+\]\['examples'\]\[\d+\]\['sentence'\]"])

    if diff:
        print("נמצאו שינויים בשדות JSON שאינם 'word' או 'sentence':")
        print(diff.to_json(indent=2))
    else:
        print("לא נמצאו שינויים בשדות JSON שאינם 'word' או 'sentence'.")

def translate_json_file(file_path, target_language_iw, target_language_en, target_lang_code):
    """
    מתרגם קובץ JSON שלם משפה אחת לשפה אחרת באמצעות Gemini API.
    שולח את כל קובץ ה-JSON כהקשר ראשוני ומקבל קובץ JSON מתורגם מלא.
    מוודא שהמבנה של קובץ ה-JSON המתורגם זהה למקור ובודק שינויים בתוכן.

    Args:
        file_path (str): נתיב לקובץ JSON.
        target_language_iw (str): שפת היעד לתרגום בעברית (לדוגמה "צרפתית", "ספרדית", "ערבית").
        target_language_en (str): שפת היעד לתרגום באנגלית (לדוגמה "French", "Spanish", "Arabic").
        target_lang_code (str): קיצור שפת היעד (לדוגמה "fr", "es", "ar").
    """
    global conversation, SYSTEM_INST, TEMPERATURE
    conversation = []

    SYSTEM_INST = SYSTEM_INST_TEMPLATE.format(target_language_iw=target_language_iw)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: קובץ לא נמצא בנתיב '{file_path}'.")
        return None
    except json.JSONDecodeError:
        print(f"Error: שגיאה בפענוח קובץ JSON. ודא שהקובץ '{file_path}' הוא קובץ JSON תקין.")
        return None

    original_json_data = json_data.copy()

    json_string = json.dumps(json_data, indent=2, ensure_ascii=False)

    add_user_text(f"```json\n{json_string}\n```")

    print("שולח בקשה לתרגום קובץ JSON מלא...")
    translated_text_md = send_and_receive()

    print("תגובה מהמודל התקבלה.")

    json_match = re.search(r'```json\s*(.*?)\s*```', translated_text_md, re.DOTALL)
    if json_match:
        translated_json_string = json_match.group(1).strip()
        try:
            translated_data = json.loads(translated_json_string)

            if validate_json_structure(original_json_data, translated_data):
                print("מבנה קובץ JSON תואם למקור - תקין.")
            else:
                print("Error: מבנה קובץ JSON לא תואם את המבנה המקורי!")
                print("תרגום עלול להיות לא תקין עקב אי התאמה במבנה.")

            compare_json_content(original_json_data, translated_data)

            output_dir = target_lang_code
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            output_file_path = os.path.join(output_dir, os.path.basename(file_path))

            with open(output_file_path, 'w', encoding='utf-8') as outfile:
                json.dump(translated_data, outfile, indent=2, ensure_ascii=False)
            print(f"קובץ JSON מתורגם נשמר ב: '{output_file_path}'")

        except json.JSONDecodeError:
            print("Error: לא הצלחתי לפענח JSON מהתגובה של המודל.")
            print("תוכן התגובה המלא מהמודל:")
            print(translated_text_md)
    else:
        print("Error: לא נמצא קוד JSON בתגובה מהמודל (תגי ```json לא נמצאו).")
        print("תוכן התגובה המלא מהמודל:")
        print(translated_text_md)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="תרגום קובץ JSON לשפת יעד.")
    parser.add_argument("level_number", type=int, help="מספר רמת הקובץ (לדוגמה, 1 עבור words_level_1.json)")
    parser.add_argument("target_lang_code", type=str, help="קוד שפה לתרגום (en, es, fr, iw)")
    args = parser.parse_args()

    target_lang_code = args.target_lang_code
    level_number = args.level_number
    file_name = f"words_level_{level_number}.json"
    file_path = os.path.join("en", file_name) # Assume original English files are in 'en' subfolder

    if not os.path.exists(file_path):
        print(f"Error: קובץ לא נמצא: '{file_path}'")
        exit()

    try:
        with open("lang_settings.json", 'r', encoding='utf-8') as f:
            lang_settings = json.load(f)
    except FileNotFoundError:
        print("Error: lang_settings.json לא נמצא.")
        exit()
    except json.JSONDecodeError:
        print("Error: שגיאה בפענוח lang_settings.json.")
        exit()

    if target_lang_code not in lang_settings:
        print(f"Error: קוד שפה '{target_lang_code}' לא נתמך ב-lang_settings.json.")
        exit()

    target_language_iw = lang_settings[target_lang_code]["language_name_iw"]
    target_language_en = lang_settings[target_lang_code]["language_name_en"]

    translate_json_file(file_path, target_language_iw, target_language_en, target_lang_code)