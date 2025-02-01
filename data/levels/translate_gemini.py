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
כמודל שפה גדול, תפקידך לבצע **תרגום ישיר והחלפה** של טקסטים בקבצי JSON מאנגלית ל{target_language_iw}.

אני אעביר לך קובץ JSON כקלט.  **עליך ליצור קובץ JSON חדש שהוא *עותק מדויק* של הקובץ המקורי, מלבד זאת שכל הטקסט בשפה האנגלית יוחלף בתרגום שלו לשפה ה{target_language_iw}.**

**הנחיות מפורטות:**

1. **זיהוי שדות טקסט באנגלית:** עליך לזהות את כל השדות בקובץ ה-JSON שמכילים טקסט בשפה האנגלית (לדוגמה, "word", "sentence", "title", "call_to_action" וכו').
2. **תרגום והחלפה:** עבור כל שדה טקסט באנגלית שזוהה:
    * **תרגם את התוכן של השדה לשפה ה{target_language_iw}.**
    * **החלף *ישירות* את הטקסט האנגלי המקורי בתרגום לשפה ה{target_language_iw} *בתוך אותו שדה*.**
    * **אל תיצור שדות חדשים!** התרגום צריך להחליף את הטקסט האנגלי בשדות הקיימים.
3. **שימור טקסט עברי:** **כל הטקסט בשפה העברית בקובץ ה-JSON *חייב להישאר ללא שינוי*.** אל תתרגם, תשנה או תיגע בטקסט העברי בשום צורה.
4. **שימור מבנה JSON:** **המבנה של קובץ ה-JSON המתורגם חייב להיות *זהה לחלוטין* למבנה של קובץ ה-JSON המקורי.**  אותם שדות, אותה היררכיה, רק התוכן בשדות הטקסט האנגלי יוחלף בתרגום.

**פלט:**

עליך להחזיר **קובץ JSON מתורגם *מלא***, המכיל את כל התוכן המתורגם והשמור, עטוף בתוך תגי קוד Markdown ```json ... ```.

**דגשים:**

* **תרגום מדויק ואיכותי:** הקפד על תרגום מדויק, טבעי ותקני לשפה ה{target_language_iw}.
* **החלפה ישירה:**  זכור, עליך *להחליף* את הטקסט האנגלי בתרגום *בשדות הקיימים*, ולא להוסיף שדות חדשים.
* **שמירה על עברית ומבנה:**  ודא שהטקסט העברי נשאר ללא שינוי, ושמבנה ה-JSON נשמר באופן מלא.

אני מצפה לקבל קובץ JSON מתורגם מלא, במבנה זהה למקור, עם החלפת הטקסט האנגלי בלבד לשפה ה{target_language_iw}.
"""

QUALITY_CHECK_INST_TEMPLATE = """
**תפקידך:** לבדוק קבצי JSON המכילים אוצר מילים ב{source_language_iw}, תרגומים לעברית ומשפטי דוגמה בשתי השפות.

**משימה:**  עליך לבצע בדיקה **יסודית** של התוכן כדי לוודא **דיוק ניסוח ותרגום** בשתי השפות - {source_language_iw} ועברית.

**הנחיות ספציפיות:**
* **פורמט פלט נדרש:** **החזר את התשובה שלך כטקסט פשוט בלבד.** **חשוב מאוד:** **אל תשתמש בפורמט JSON, רשימות ממוספרות, טבלאות או כל פורמט נתונים מובנה אחר.**  הפלט צריך להיות **טקסטואלי לחלוטין**.
* **מיקוד בדיקה:**  חפש משפטים שבהם יש **טעויות ניסוח ברורות**, **תרגום לא מדויק** או **שימוש בשפה שאינו תקני או מקובל** ב{source_language_iw} או בעברית.
* **סוגי טעויות:**  שים לב לטעויות דקדוקיות, תחביריות, סמנטיות וטעויות תרגום המשנות את המשמעות המקורית.
* **אי הכללה:**  **אין צורך** להציע שיפורים סגנוניים, גיוון ניסוח או שינויים שאינם נובעים **מטעות ברורה**. התמקד אך ורק בתיקון טעויות מהותיות.

**פורמט פלט - במקרה של שגיאות (דוגמה):**

---

- המשפט המקורי ({source_language_iw}): [הכנס משפט מקורי כאן]
  - המשפט המתורגם: [הכנס משפט מתורגם כאן]
  - סוג הבעיה: [הכנס הסבר ברור של סוג הבעיה]
  - משפט חלופי תקין ({source_language_iw}): [הכנס משפט חלופי תקין כאן]

- המשפט המקורי (עברית): [הכנס משפט מקורי בעברית כאן]
  - המשפט המתורגם: [הכנס משפט מתורגם כאן]
  - סוג הבעיה: [הכנס הסבר ברור של סוג הבעיה]
  - משפט חלופי תקין (עברית): [הכנס משפט חלופי תקין בעברית כאן]

---

**פורמט פלט - במקרה של תקינות (חובה להחזיר בדיוק):**

`NO_ERRORS_FOUND`

**דגש על מיקוד ופורמט פלט:**  התשובה שלך צריכה להיות **ממוקדת אך ורק** בהצגת משפטים הדורשים תיקון בשתי השפות, כולל משפט חלופי תקין, או החזרת המחרוזת `NO_ERRORS_FOUND` **בדיוק** אם אין טעויות. **הפלט חייב להיות טקסט פשוט** כפי שמוצג בדוגמאות, **ללא JSON או פורמט מובנה אחר.**
"""

conversation = []
TEMPERATURE = 0.6
TEMPERATURE_QUALITY_CHECK = 0.7

MODELS_CONFIG = {
    "thinking": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-thinking-exp-01-21:generateContent",
        "temperature": TEMPERATURE_QUALITY_CHECK
    },
    "1206": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-exp-1206:generateContent",
        "temperature": TEMPERATURE_QUALITY_CHECK
    }
}

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

def send_and_receive(model_name="thinking", quality_check=False) -> str:
    """
    שולח בקשה ל-Gemini API ומקבל תגובה.

    Args:
        model_name (str): שם המודל לשימוש ("thinking" או "1206").
        quality_check (bool): האם מדובר בבדיקת איכות.

    Returns:
        str: תגובת המודל.
    """
    model_config = MODELS_CONFIG.get(model_name)
    if not model_config:
        raise ValueError(f"Invalid model name: {model_name}")

    current_temperature = model_config["temperature"] if quality_check else TEMPERATURE

    payload = {
        "systemInstruction": {
            "role": "system",
            "parts": [
                {"text": SYSTEM_INST}
            ]
        },
        "contents": conversation,
        "generationConfig": {
            "temperature": current_temperature,
            "topK": 64,
            "topP": 0.95,
            "maxOutputTokens": 65536,
            "responseMimeType": "text/plain"
        }
    }

    url = model_config["url"]
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
                print(f"לא נמצא תוכן בתשובת המודל {model_name}.")
        else:
            print(f"לא התקבלה תשובה מהמודל {model_name}.")
    except requests.exceptions.RequestException as e:
        print(f"שגיאת בקשה ל-API ({model_name}): {e}")
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
    diff = DeepDiff(original_json, translated_json, exclude_regex_paths=[r"root\['levels'\]\[\d+\]\['subtopics'\]\[\d+\]\['words'\]\[\d+\]\['word'\]", r"root\['levels'\]\[\d+\]\[\'subtopics\'\]\[\d+\]\[\'words\'\]\[\d+\]\[\'examples\'\]\[\d+\]\[\'sentence\'\]"]) # corrected regex here

    if diff:
        print("נמצאו שינויים בשדות JSON שאינם 'word' או 'sentence':")
        print(diff.to_json(indent=2))
    else:
        print("לא נמצאו שינויים בשדות JSON שאינם 'word' או 'sentence'.")

def perform_quality_check(file_path, source_language_iw, target_language_iw, source_lang_code, target_lang_code):
    """
    מבצע בדיקת איכות כפולה לתוכן JSON מתורגם באמצעות Gemini API, פעם אחת עם מודל "thinking" ופעם נוספת עם מודל "1206".
    משלב את תוצאות שתי הבדיקות לדוח אחד.
    שומר את דוח הבדיקה לקובץ טקסט.

    Args:
        file_path (str): נתיב לקובץ JSON המתורגם.
        source_language_iw (str): שפת המקור בעברית (לדוגמה "אנגלית").
        target_language_iw (str): שפת היעד בעברית (לדוגמה "צרפתית").
        source_lang_code (str): קוד שפת המקור (לדוגמה "en").
        target_lang_code (str): קוד שפת היעד (לדוגמה "fr").
    """
    global conversation, SYSTEM_INST
    conversation = []

    QUALITY_CHECK_SYS_INST = QUALITY_CHECK_INST_TEMPLATE.format(source_language_iw=source_language_iw)
    SYSTEM_INST = QUALITY_CHECK_SYS_INST

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: קובץ לא נמצא בנתיב '{file_path}'.")
        return None
    except json.JSONDecodeError:
        print(f"Error: שגיאה בפענוח קובץ JSON. ודא שהקובץ '{file_path}' הוא קובץ JSON תקין.")
        return None

    json_string = json.dumps(json_data, indent=2, ensure_ascii=False)
    add_user_text(f"```json\n{json_string}\n```")

    print("שולח בקשה לביצוע בדיקת איכות תרגום...")

    # Perform quality check with "thinking" model
    quality_check_report_thinking = send_and_receive(model_name="thinking", quality_check=True)
    print(f"דוח בדיקת איכות התקבל מהמודל thinking.")

    # Reset conversation for the second quality check
    conversation = []
    add_user_text(f"```json\n{json_string}\n```")

    # Perform quality check with "1206" model
    quality_check_report_1206 = send_and_receive(model_name="1206", quality_check=True)
    print(f"דוח בדיקת איכות התקבל מהמודל 1206.")

    # Combine reports
    combined_report = ""
    if quality_check_report_thinking.strip() == "NO_ERRORS_FOUND" and quality_check_report_1206.strip() == "NO_ERRORS_FOUND":
        combined_report = "NO_ERRORS_FOUND"
        print("לא נמצאו שגיאות תרגום על ידי שני המודלים.")
    else:
        combined_report += "דוח בדיקת איכות - מודל thinking:\n"
        combined_report += quality_check_report_thinking + "\n\n"
        combined_report += "דוח בדיקת איכות - מודל 1206:\n"
        combined_report += quality_check_report_1206

    # Save combined report
    report_filename = f"quality_report_{os.path.basename(file_path).replace('.json', '')}_{target_lang_code}.txt"
    output_dir = target_lang_code
    report_file_path = os.path.join(output_dir, report_filename)

    with open(report_file_path, 'w', encoding='utf-8') as report_file:
        report_file.write(combined_report)
    print(f"דוח בדיקת איכות משולב נשמר ב: '{report_file_path}'")

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

            # Perform quality check after saving the translated JSON
            source_language_iw = "אנגלית"
            perform_quality_check(output_file_path, source_language_iw, target_language_iw, "en", target_lang_code)

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
    file_path = os.path.join("en", file_name)

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