import json
import os
import requests
import base64
from PIL import Image
from io import BytesIO

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("Error: GEMINI_API_KEY environment variable is not set.")
    exit()

SYSTEM_INST_TEMPLATE = """
אתה מודל שפה גדול שמבצע תרגום מקצועי של טקסטים בעברית ל{target_language}.
המשימה שלך היא לתרגם טקסטים מקובץ JSON לשפת ה{target_language}, תוך התמקדות בשדות ספציפיים בלבד: 'sentence' ו- 'word'.
עליך לשמור על מבנה ה-JSON המקורי ולתרגם רק את הערכים של השדות האלה.
הקובץ JSON המלא יסופק לך בהודעה הראשונה כהקשר.
לאחר מכן, תקבל משפט אחד בכל פעם משדות הטקסט הרלוונטיים מתוך ה-JSON, ותגובתך צריכה להיות תרגום של המשפט הזה ל{target_language} בלבד.
אל תתרגם שדות אחרים או מילים מחוץ לשדות 'sentence' ו- 'word'.
השתמש בתרגום מקצועי וטבעי, המתאים ללימוד שפה.
הטמפרטורה שלך מוגדרת ל-{temperature}, השתמש בה כדי לשלוט ברנדומליות התגובות שלך.
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

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent" # שימוש במודל gemini-2.0-flash-exp
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

def translate_text(text_to_translate, target_language):
    global conversation
    add_user_text(text_to_translate)
    translated_text = send_and_receive()
    return translated_text

def translate_json_file(file_path, target_language):
    """
    מתרגם טקסט בעברית בקובץ JSON לשפה הרצויה, רק בשדות 'sentence' ו- 'word'.
    שולח את כל קובץ ה-JSON כהקשר ראשוני.

    Args:
        file_path (str): נתיב לקובץ JSON.
        target_language (str): שפת היעד לתרגום (באנגלית, לדוגמה "English", "French", "Arabic").
    """
    global conversation, SYSTEM_INST, TEMPERATURE
    conversation = [] # איפוס השיחה בתחילת תרגום קובץ חדש

    # הגדרת הנחיית מערכת דינמית עם שפת היעד והטמפרטורה
    SYSTEM_INST = SYSTEM_INST_TEMPLATE.format(target_language=target_language, temperature=TEMPERATURE)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: קובץ לא נמצא בנתיב '{file_path}'.")
        return None
    except json.JSONDecodeError:
        print(f"Error: שגיאה בפענוח קובץ JSON. ודא שהקובץ '{file_path}' הוא קובץ JSON תקין.")
        return None

    # שליחת קובץ JSON מלא כהקשר ראשוני
    add_user_text(f"הקובץ JSON הבא מספק הקשר לתרגום: \n\n ```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```\n\n עכשיו אתחיל לשלוח לך משפטים בודדים לתרגום.")

    def translate_recursive(json_object):
        if isinstance(json_object, dict):
            for key, value in json_object.items():
                if isinstance(value, str) and key in ["sentence", "word"]: # תרגום רק בשדות 'sentence' ו- 'word'
                    print(f"מתרגם שדה '{key}': '{value}'")
                    translated_text = translate_text(value, target_language)
                    print(f"-> תרגום: '{translated_text}'")
                    json_object[key] = translated_text
                elif isinstance(value, (dict, list)):
                    translate_recursive(value)
        elif isinstance(json_object, list):
            for item in json_object:
                translate_recursive(item)

    translate_recursive(data)

    output_file_path = file_path.replace(".json", f"_translated_{target_language}.json")
    try:
        with open(output_file_path, 'w', encoding='utf-8') as outfile:
            json.dump(data, outfile, indent=2, ensure_ascii=False)
        print(f"קובץ JSON מתורגם נשמר ב: '{output_file_path}'")
    except Exception as e:
        print(f"Error: שגיאה בשמירת קובץ JSON מתורגם: {e}")

if __name__ == "__main__":
    file_path = "words_level_0.json"
    target_language = "French" # שנה כאן את שפת היעד הרצויה

    translate_json_file(file_path, target_language)