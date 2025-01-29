import json
import os
import requests
import base64
from PIL import Image
from io import BytesIO
import re
import argparse  # ייבוא argparse לטיפול בארגומנטים משורת הפקודה

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("Error: GEMINI_API_KEY environment variable is not set.")
    exit()

SYSTEM_INST_TEMPLATE = """
אתה מודל שפה גדול שמקבל קבצי JSON המיועדים לבניית סרטונים ללימוד אנגלית.
על בסיס התוכן בקובץ, עליך ליצור קובץ JSON חדש וזהה לחלוטין שמלמד {target_language} במקום אנגלית.
עליך להחליף את המילים באנגלית למילים ב{target_language}, וכך גם את המשפטים לדוגמה.
הקפד לשמור על מבנה זהה של תוכן ושים לב ששמות השלבים, הקטעים והקריאה לפעולה ישארו בעברית!

הקובץ JSON המלא יסופק לך בהודעה הבאה.
עליך להחזיר קובץ JSON מתורגם מלא בתוך תגי קוד Markdown (```json ... ```).

הקפד על תרגום מדויק, ניסוח תקין ובאיכות גבוהה בשפה ה{target_language}.
"""

conversation = []
TEMPERATURE = 0.6 # הגדרת טמפרטורה גלובלית - ניתן לשנות כאן

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
        "generationConfig": { # הגדרת generationConfig בדומה ל-CURL
            "temperature": TEMPERATURE, # שימוש בטמפרטורה הגלובלית
            "topK": 64, # ערכים אופציונליים נוספים - ניתן להסיר אם לא נדרש
            "topP": 0.95, # ערכים אופציונליים נוספים
            "maxOutputTokens": 65536, # ערכים אופציונליים נוספים
            "responseMimeType": "text/plain" # ערכים אופציונליים נוספים
        }
    }

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-thinking-exp-01-21:generateContent" # שימוש במודל gemini-2.0-flash-thinking-exp-01-21
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
        return True  # ערכים פרימיטיביים - אין צורך לבדוק מבנה לעומק

def translate_json_file(file_path, target_language):
    """
    מתרגם קובץ JSON שלם משפה אחת לשפה אחרת באמצעות Gemini API.
    שולח את כל קובץ ה-JSON כהקשר ראשוני ומקבל קובץ JSON מתורגם מלא.
    מוודא שהמבנה של קובץ ה-JSON המתורגם זהה למקור.

    Args:
        file_path (str): נתיב לקובץ JSON.
        target_language (str): שפת היעד לתרגום (באנגלית, לדוגמה "English", "French", "Arabic").
    """
    global conversation, SYSTEM_INST, TEMPERATURE
    conversation = [] # איפוס השיחה בתחילת תרגום קובץ חדש

    # הגדרת הנחיית מערכת דינמית עם שפת היעד
    SYSTEM_INST = SYSTEM_INST_TEMPLATE.format(target_language=target_language)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: קובץ לא נמצא בנתיב '{file_path}'.")
        return None
    except json.JSONDecodeError:
        print(f"Error: שגיאה בפענוח קובץ JSON. ודא שהקובץ '{file_path}' הוא קובץ JSON תקין.")
        return None

    original_json_data = json_data.copy() # שמירת עותק של ה JSON המקורי לצורך השוואה

    json_string = json.dumps(json_data, indent=2, ensure_ascii=False)

    # שליחת קובץ JSON מלא כהודעה למשתמש
    add_user_text(f"```json\n{json_string}\n```")

    print("שולח בקשה לתרגום קובץ JSON מלא...")
    translated_text_md = send_and_receive() # מקבל תשובה בפורמט Markdown עם קוד JSON

    print("תגובה מהמודל התקבלה.")

    # חילוץ קוד JSON מתוך תגי Markdown
    json_match = re.search(r'```json\s*(.*?)\s*```', translated_text_md, re.DOTALL) # חילוץ JSON מתגי MD
    if json_match:
        translated_json_string = json_match.group(1).strip()
        try:
            translated_data = json.loads(translated_json_string) # טעינת JSON מהמחרוזת

            if validate_json_structure(original_json_data, translated_data): # וידוא מבנה JSON
                print("מבנה קובץ JSON תואם למקור - תקין.")
                output_file_path = file_path.replace(".json", f"_translated_צרפתית.json") if target_language == "French" else file_path.replace(".json", f"_translated_{target_language}.json")
                with open(output_file_path, 'w', encoding='utf-8') as outfile:
                    json.dump(translated_data, outfile, indent=2, ensure_ascii=False)
                print(f"קובץ JSON מתורגם נשמר ב: '{output_file_path}'")
            else:
                print("Error: מבנה קובץ JSON לא תואם את המבנה המקורי!")
                print("תרגום נכשל עקב אי התאמה במבנה.")

        except json.JSONDecodeError:
            print("Error: לא הצלחתי לפענח JSON מהתגובה של המודל.")
            print("תוכן התגובה המלא מהמודל:")
            print(translated_text_md)
    else:
        print("Error: לא נמצא קוד JSON בתגובה מהמודל (תגי ```json לא נמצאו).")
        print("תוכן התגובה המלא מהמודל:")
        print(translated_text_md)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="תרגום קובץ JSON לשפת יעד.") # הגדרת parser
    parser.add_argument("level_number", type=int, help="מספר רמת הקובץ (לדוגמה, 1 עבור words_level_1.json)") # הוספת ארגומנט לקבלת מס' רמה
    args = parser.parse_args() # קריאת ארגומנטים משורת הפקודה

    level_number = args.level_number # קבלת מס' רמה מהארגומנטים
    file_path = f"words_level_{level_number}.json" # בניית נתיב קובץ דינמי

    if not os.path.exists(file_path): # בדיקה אם הקובץ קיים
        print(f"Error: קובץ לא נמצא: '{file_path}'")
        exit()

    translate_json_file(file_path, target_language)