import base64
import os
import json # לעבודה עם JSON
from google import genai
from google.genai import types
import re
import urllib.parse
import moviepy.editor as mp
from moviepy.video.tools.subtitles import SubtitlesClip
# import pysrt <<< לא נדרש יותר!
import math # For ceiling function
import imageio # לשמירת תמונות
import numpy as np # MoviePy משתמש בזה, וגם אנחנו לקליפ תמונה
from PIL import Image, ImageDraw, ImageFont # ליצירת טקסט מתקדמת
import arabic_reshaper # לעיצוב תווים ערביים/עבריים
from bidi.algorithm import get_display # לסדר תצוגה מימין לשמאל (RTL)

# --- הגדרות נתיבים ותיקיות ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'data', 'levels')
ASSETS_DIR = os.path.join(BASE_DIR, '..', 'assets')
FONTS_DIR = os.path.join(ASSETS_DIR, 'fonts')
output_frames_dir = os.path.join(BASE_DIR, "subtitle_frames")
json_files_dir = os.path.join(BASE_DIR, "json_files") # תיקייה לקבצי JSON
output_dir = os.path.join(BASE_DIR, "output")

# --- יצירת תיקיות נדרשות ---
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)
os.makedirs(output_frames_dir, exist_ok=True)
os.makedirs(json_files_dir, exist_ok=True) # יצירת תיקיית JSON
os.makedirs(output_dir, exist_ok=True)

# --- הגדרות קלט ---
youtube_link = input("הזן קישור YouTube לשיר: ")
mp3_file = input(f"הכנס נתיב לקובץ שיר (ברירת מחדל: {os.path.join(BASE_DIR, 'so much closer.mp3')}) >>> ") or os.path.join(BASE_DIR, "so much closer.mp3")

# --- הגדרות כלליות ---
video_resolution = (1280, 720)
video_fps = 25

# --- נתיבי קבצים נוספים ---
background_image_path = os.path.join(ASSETS_DIR, 'backgrounds', 'levels', "word_background.png")
font_name = "Rubik-Regular.ttf"
font_path = os.path.join(FONTS_DIR, font_name)

# --- הגדרות עיצוב כתוביות מעודכנות ---
fontsize_en = 60
fontsize_he = 57
color_subs = 'black'
stroke_color_subs = 'white'
stroke_width_subs = 1.5
position_subs = ('center', 'center')
spacing_within_language = 10
spacing_between_languages = 35

# --- הגדרות עיצוב כותרת שיר ---
fontsize_title = 120
color_title = 'blue'
stroke_color_title = 'white'
stroke_width_title = 4.0
position_title = ('center', 'center')

# --- בדיקת קיום קבצים ---
if not os.path.exists(mp3_file): print(f"שגיאה: קובץ האודיו '{mp3_file}' לא נמצא."); exit()
if not os.path.exists(background_image_path): print(f"שגיאה: קובץ תמונת הרקע '{background_image_path}' לא נמצא."); exit()
if not os.path.exists(font_path): print(f"שגיאה: קובץ הפונט '{font_path}' לא נמצא."); exit()

def clean_json_text(raw_text):
    """Removes potential Markdown fences (```json ... ```) from the raw text."""
    # Pattern to find ```json ... ``` or ``` ... ```, capturing the content inside
    pattern = r"```(?:json)?\s*(.*?)\s*```"
    match = re.search(pattern, raw_text, re.DOTALL)
    if match:
        cleaned_content = match.group(1).strip()
        print("Info: Removed Markdown fences from JSON response.")
        return cleaned_content
    else:
        # If no fences found, return the original text stripped.
        return raw_text.strip()

def parse_json_response(json_text, language_name):
    """Parses JSON response, validates structure, and returns the list."""
    cleaned_text = clean_json_text(json_text) # <<< נקה לפני הפענוח
    if not cleaned_text:
        print(f"Error: JSON text for {language_name} is empty after cleaning.")
        return None
    try:
        data = json.loads(cleaned_text)
        if not isinstance(data, list):
            print(f"Warning: Expected JSON list for {language_name}, but got {type(data)}. Trying to proceed if it's a single dict in a list.")
            if isinstance(data, dict): data = [data]
            else: raise ValueError("JSON response is not a list.")

        if data:
            item = data[0]
            if not isinstance(item, dict):
                raise ValueError(f"Items in {language_name} JSON list are not dictionaries.")
            required_keys = {"start_time", "end_time", "text"} # ID is good but optional for processing
            if not required_keys.issubset(item.keys()):
                raise ValueError(f"Dictionary in {language_name} JSON is missing required keys ({required_keys}). Found: {item.keys()}")
            if not isinstance(item['start_time'], (int, float)) or not isinstance(item['end_time'], (int, float)):
                 print(f"Warning: Timestamps in first item of {language_name} JSON are not numbers (int/float). Found: start={type(item['start_time'])}, end={type(item['end_time'])}. Will attempt conversion later.")

        print(f"Successfully parsed JSON for {language_name}.")
        return data
    except json.JSONDecodeError as e:
        print(f"Error: Failed to decode JSON response for {language_name}. Error: {e}")
        print("--- Received Text (after potential cleaning) ---")
        print(cleaned_text[:500] + "..." if len(cleaned_text) > 500 else cleaned_text)
        print("--- End of Received Text ---")
        return None
    except ValueError as e:
        print(f"Error: Invalid JSON structure for {language_name}. Error: {e}")
        print("--- Received Data Structure ---")
        # Use print(data) only if 'data' was successfully assigned before the error
        try: print(data)
        except NameError: print("(Could not assign data before error)")
        print("--- End of Received Data Structure ---")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during JSON parsing for {language_name}: {e}")
        return None


def generate_subtitles_from_youtube(youtube_url):
    # --- חישוב שמות קבצים צפויים ---
    try:
        parsed_url = urllib.parse.urlparse(youtube_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        video_id = query_params.get('v')
        if video_id:
            base_filename = video_id[0]
        else:
            base_filename = re.sub(r'\W+', '_', os.path.splitext(os.path.basename(mp3_file))[0]) if 'mp3_file' in globals() and mp3_file else "default_song"
            print(f"אזהרה: לא זוהה Video ID מהקישור. משתמש בשם חלופי: {base_filename}")

        english_json_filename = os.path.join(json_files_dir, f"{base_filename}_en.json")
        hebrew_json_filename = os.path.join(json_files_dir, f"{base_filename}_he.json")
    except Exception as e:
        print(f"שגיאה בניתוח הקישור או הגדרת שמות קבצים: {e}")
        print("לא ניתן לבדוק קבצים קיימים. ממשיך לנסות ליצור כתוביות.")
        english_json_filename = None
        hebrew_json_filename = None

    # --- בדיקה אם קבצי JSON כבר קיימים ---
    if english_json_filename and hebrew_json_filename and \
       os.path.exists(english_json_filename) and os.path.exists(hebrew_json_filename):
        print(f"\nנמצאו קבצי JSON קיימים:\n  EN: {english_json_filename}\n  HE: {hebrew_json_filename}")
        print("מדלג על שלב יצירת הכתוביות מ-YouTube וטוען את הקבצים הקיימים.")
        try:
            with open(english_json_filename, "r", encoding="utf-8") as f_en:
                english_subs_data = json.load(f_en)
            with open(hebrew_json_filename, "r", encoding="utf-8") as f_he:
                hebrew_subs_data = json.load(f_he)

            if not isinstance(english_subs_data, list) or not isinstance(hebrew_subs_data, list):
                 print("אזהרה: אחד מקבצי ה-JSON הקיימים אינו רשימה. ממשיך ליצירה מחדש.")
            elif not english_subs_data and not hebrew_subs_data:
                 print("אזהרה: שני קבצי ה-JSON הקיימים ריקים (כרשימה ריקה). ממשיך ליצירה מחדש.")
            elif not english_subs_data or not hebrew_subs_data:
                 print("אזהרה: אחד מקבצי ה-JSON הקיימים ריק.")
                 print("תוכן הכתוביות (הקיים) נטען בהצלחה מהקבצים.")
                 return english_subs_data, hebrew_subs_data
            else:
                 print("תוכן הכתוביות נטען בהצלחה מהקבצים.")
                 return english_subs_data, hebrew_subs_data

        except json.JSONDecodeError as e:
            print(f"שגיאה בפענוח קובץ JSON קיים: {e}. ממשיך לנסות ליצור כתוביות מחדש.")
        except Exception as e:
            print(f"שגיאה בקריאת קבצי JSON קיימים: {e}. ממשיך לנסות ליצור כתוביות מחדש.")


    # --- אם הקבצים לא קיימים או היתה שגיאה בקריאה, המשך עם היצירה ---
    print("\nקבצי JSON לא נמצאו או היו שגויים. מתחיל תהליך יצירה מ-YouTube...")

    if not os.environ.get("GEMINI_API_KEY"):
        print("שגיאה: לא נמצא מפתח API של Gemini. אנא הגדר את משתנה הסביבה GEMINI_API_KEY.")
        return None, None

    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    model = "gemini-2.5-pro-exp-03-25" # "gemini-2.0-flash" #  # Or your preferred model

    system_instruction_content = """עליך ליצור כתוביות עבור הסרטון המצורף, תוך הקפדה על דיוק התמלול וניסוח טבעי שמתאים לשפה המדוברת בסרטון. הפלט חייב להיות **רשימת JSON (Array)** כפי שמוצג להלן.  

כל כתובית חייבת לכלול:  
- **`id`**: מספר סידורי המייצג את סדר הופעת הכתובית.  
- **`start_time`**: זמן התחלה בפורמט **שניות עשרוניות (float)**, לדוגמה `12.759`.  
- **`end_time`**: זמן סיום בפורמט **שניות עשרוניות (float)**, לדוגמה `18.859`.  
- **`text`**: טקסט הכתובית, שיכול להכיל שורות מרובות (מופרדות באמצעות `\n`).  

יש לשמור על דיוק בזמנים ובתוכן כדי להבטיח שהתוצאה תוכל להיות מומרת בקלות לקובץ SRT.

### **מבנה JSON לדוגמה:**
```json
[
  {
    "id": 1,
    "start_time": 12.759,
    "end_time": 18.859,
    "text": "I will never forget\nthe night I saw my father cry"
  },
  {
    "id": 2,
    "start_time": 21.359,
    "end_time": 28.729,
    "text": "I was frightened and alone\nand his tears were burning in my eyes, deep in my soul"
  }
]
```"""

    generate_content_config = types.GenerateContentConfig(
        # <<< דרישת JSON מה-API >>>
        response_mime_type="application/json",
        system_instruction=[
            types.Part.from_text(text=system_instruction_content),
        ],
    )

    transcription_prompt_text = """Transcribe the following song accurately.
Output the result as a JSON array following the specified format (id, start_time, end_time, text).
Use float seconds for times. Divide segments intelligently.
Output ONLY the JSON array."""

    contents_english = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_uri(
                    file_uri=youtube_url,
                    mime_type="video/*",
                ),
                types.Part.from_text(text=transcription_prompt_text),
            ],
        ),
    ]

    print("Generating English Subtitles (JSON)...")
    english_json_raw = ""
    try:
        # <<< חזרה לשימוש ב-stream כמו בקוד המקורי >>>
        stream_response = client.models.generate_content_stream(
            model=model,
            contents=contents_english,
            config=generate_content_config,
            # stream=True is implied by generate_content_stream
        )
        # <<< איסוף התוכן מה-stream >>>
        for chunk in stream_response:
            # Assuming chunk.text contains parts of the JSON string
            # Add safety check in case a chunk is empty or has no text
            if chunk.text:
                 english_json_raw += chunk.text
                 # Optional: print progress if needed, but can clutter output
                 # print(".", end="")

    except types.generation_types.BlockedPromptException as e:
         print(f"Error: Prompt was blocked for English generation. Reason: {e}")
         # You might want to inspect e.BlockReason or similar attributes if available
         return None, None
    except types.generation_types.StopCandidateException as e:
         print(f"Error: Generation stopped unexpectedly for English. Reason: {e}")
         # Inspect e.FinishReason
         return None, None
    except Exception as e:
        print(f"Error during Gemini API stream call for English: {e}")
        # Attempt to print response details if available in the exception context
        try:
             # Accessing response details might differ based on the exception type
             # This is a generic attempt
             if hasattr(e, 'response'):
                  print("Gemini response details (if available):", e.response)
             # Print safety feedback if the exception structure allows (might need adjustment)
             # The structure might be different for stream errors vs. direct call errors
             # print("Gemini safety feedback (if available):", stream_response.prompt_feedback)
        except Exception as report_err:
             print(f"(Could not report detailed error info: {report_err})")
        return None, None

    print("\nEnglish JSON stream finished.") # Added newline for clarity

    # <<< פענוח ה-JSON *לאחר* סיום ה-stream >>>
    english_subs_data = parse_json_response(english_json_raw, "English")

    if english_subs_data is None:
        print("Failed to get valid English JSON data.")
        return None, None

    # Ensure filenames exist
    if not english_json_filename:
        base_filename = "generated_fallback"
        english_json_filename = os.path.join(json_files_dir, f"{base_filename}_en.json")
        hebrew_json_filename = os.path.join(json_files_dir, f"{base_filename}_he.json")

    # --- שמירת קובץ JSON אנגלי ---
    try:
        with open(english_json_filename, "w", encoding="utf-8") as f:
            json.dump(english_subs_data, f, ensure_ascii=False, indent=2)
        print(f"English JSON saved to: {english_json_filename}")
    except Exception as e:
        print(f"\nError saving English JSON file '{english_json_filename}': {e}")
        return None, None

    # --- הכנת קלט לתרגום ---
    translation_prompt_text = f"""Translate the text in the following English JSON subtitles to Hebrew.
Maintain the exact same JSON structure, including 'id', 'start_time', and 'end_time' values. Only translate the 'text' field for each object.
Ensure the Hebrew text uses standard characters and line breaks (\\n) appropriately.
Output ONLY the translated JSON array.

Original English JSON:
{json.dumps(english_subs_data, ensure_ascii=False, indent=2)}"""

    contents_hebrew = [
        types.Content(
            role="user",
            parts=[
                 types.Part.from_text(text=translation_prompt_text),
            ],
        ),
    ]

    print("\nGenerating Hebrew Subtitles (JSON)...")
    hebrew_json_raw = ""
    try:
        # <<< שימוש ב-stream גם לתרגום >>>
        stream_response_he = client.models.generate_content_stream(
            model=model,
            contents=contents_hebrew,
            config=generate_content_config,
        )
        # <<< איסוף התוכן מה-stream >>>
        for chunk in stream_response_he:
            if chunk.text:
                hebrew_json_raw += chunk.text

    except types.generation_types.BlockedPromptException as e:
         print(f"Error: Prompt was blocked for Hebrew generation. Reason: {e}")
         return english_subs_data, None # Return English data
    except types.generation_types.StopCandidateException as e:
         print(f"Error: Generation stopped unexpectedly for Hebrew. Reason: {e}")
         return english_subs_data, None # Return English data
    except Exception as e:
        print(f"Error during Gemini API stream call for Hebrew: {e}")
        try:
            if hasattr(e, 'response'):
                 print("Gemini response details (if available):", e.response)
            # print("Gemini safety feedback (if available):", stream_response_he.prompt_feedback)
        except Exception as report_err:
            print(f"(Could not report detailed error info: {report_err})")
        return english_subs_data, None # Return English data

    print("\nHebrew JSON stream finished.")

    # <<< פענוח ה-JSON *לאחר* סיום ה-stream >>>
    hebrew_subs_data = parse_json_response(hebrew_json_raw, "Hebrew")

    if hebrew_subs_data is None:
        print("Failed to get valid Hebrew JSON data.")
        return english_subs_data, None

    # --- שמירת קובץ JSON עברי ---
    try:
        with open(hebrew_json_filename, "w", encoding="utf-8") as f:
            json.dump(hebrew_subs_data, f, ensure_ascii=False, indent=2)
        print(f"Hebrew JSON saved to: {hebrew_json_filename}")
    except Exception as e:
        print(f"\nError saving Hebrew JSON file '{hebrew_json_filename}': {e}")
        return english_subs_data, None

    # --- החזרת הנתונים המפוענחים ---
    return english_subs_data, hebrew_subs_data

# --- (המשך הקוד נשאר זהה מנקודה זו) ---

# --- קריאה לפונקציה ---
print("בודק או יוצר כתוביות מיוטיוב (פורמט JSON)...")
english_subtitle_data, hebrew_subtitle_data = generate_subtitles_from_youtube(youtube_link)

# <<< בדיקה אם קיבלנו נתוני רשימה (list) >>>
if not isinstance(english_subtitle_data, list) and not isinstance(hebrew_subtitle_data, list):
    print("שגיאה קריטית: לא הופקו או נטענו נתוני כתוביות תקינים (לא בפורמט רשימה). יציאה.")
    exit()
elif not english_subtitle_data and not hebrew_subtitle_data:
     print("אזהרה: גם נתוני האנגלית וגם נתוני העברית ריקים. הוידאו ייווצר ללא כתוביות.")
elif not english_subtitle_data:
     print("אזהרה: לא הופקו/נטענו כתוביות באנגלית. ממשיך עם עברית בלבד.")
elif not hebrew_subtitle_data:
     print("אזהרה: לא הופקו/נטענו כתוביות בעברית. ממשיך עם אנגלית בלבד.")


# חישוב שמות הקבצים שוב לצורך וידוא
parsed_url = urllib.parse.urlparse(youtube_link)
query_params = urllib.parse.parse_qs(parsed_url.query)
video_id = query_params.get('v')
if video_id:
    base_filename = video_id[0]
else:
    base_filename = re.sub(r'\W+', '_', os.path.splitext(os.path.basename(mp3_file))[0]) if 'mp3_file' in globals() and mp3_file else "default_song"

json_en_file = os.path.join(json_files_dir, f"{base_filename}_en.json")
json_he_file = os.path.join(json_files_dir, f"{base_filename}_he.json")

# --- הגדרת שם קובץ פלט ושם השיר ---
output_video_base = os.path.splitext(os.path.basename(mp3_file))[0]
output_video_file = os.path.join(output_dir, f"{output_video_base}_subtitled.mp4")
song_title_text = output_video_base.replace('_', ' ').replace('-', ' ').title()
print(f"שם השיר שיוצג: {song_title_text}")
print(f"שם קובץ הפלט יהיה: {output_video_file}")
print(f"תמונות כתוביות יישמרו בתיקייה: {output_frames_dir}")

# --- טעינת אודיו ---
print("טוען אודיו...")
try:
    audio_clip = mp.AudioFileClip(mp3_file)
    audio_duration = audio_clip.duration
    print(f"משך האודיו: {audio_duration:.2f} שניות")
except Exception as e:
     print(f"שגיאה בטעינת קובץ האודיו '{mp3_file}': {e}"); exit()

# --- יצירת קליפ רקע מתמונה ---
print("טוען תמונת רקע...")
try:
    # Explicitly set duration to avoid issues if audio load fails partially
    bg_duration = audio_duration if audio_duration and audio_duration > 0 else 1.0
    background_clip = mp.ImageClip(background_image_path, duration=bg_duration)
    background_clip = background_clip.resize(height=video_resolution[1])
    # Ensure cropping happens only if image is wider than target
    if background_clip.w > video_resolution[0]:
        background_clip = background_clip.crop(x_center=background_clip.w/2, width=video_resolution[0])
    # Final resize to target resolution
    background_clip = background_clip.resize(video_resolution)
    background_clip = background_clip.set_fps(video_fps)
except Exception as e:
    print(f"שגיאה בטעינת או עיבוד תמונת הרקע '{background_image_path}': {e}")
    # Attempt to close audio if loaded before exiting
    try: audio_clip.close()
    except: pass
    exit()


# --- מציאת זמן התחלה של הכתובית הראשונה (מנתוני ה-JSON) ---
first_subtitle_start_time = audio_duration if audio_duration else float('inf')
try:
    if english_subtitle_data and isinstance(english_subtitle_data, list) and len(english_subtitle_data) > 0:
        start_en = float(english_subtitle_data[0].get('start_time', first_subtitle_start_time))
        if start_en >= 0: first_subtitle_start_time = min(first_subtitle_start_time, start_en)
    if hebrew_subtitle_data and isinstance(hebrew_subtitle_data, list) and len(hebrew_subtitle_data) > 0:
         start_he = float(hebrew_subtitle_data[0].get('start_time', first_subtitle_start_time))
         if start_he >= 0: first_subtitle_start_time = min(first_subtitle_start_time, start_he)
except (ValueError, TypeError, KeyError) as e:
     print(f"Warning: Could not reliably determine first subtitle start time from JSON data. Error: {e}")
     first_subtitle_start_time = 0 # Default to 0 if unsure

# Handle case where audio_duration was 0 or None
if first_subtitle_start_time == float('inf'):
    first_subtitle_start_time = 0

# Define a minimum duration needed to display the title meaningfully
min_title_duration_threshold = 0.5
title_clip = None # Initialize title_clip to None

# Ensure first_subtitle_start_time is not greater than audio duration
first_subtitle_start_time = min(first_subtitle_start_time, audio_duration if audio_duration else 0)


if first_subtitle_start_time < min_title_duration_threshold:
    print(f"אזהרה: הכתובית הראשונה מתחילה מוקדם מאוד ({first_subtitle_start_time:.2f}s) או שאין מספיק זמן. מדלג על הצגת כותרת השיר.")
else:
     # Calculate title duration, ensuring it's not negative
     title_duration = max(0, first_subtitle_start_time)
     print(f"הכתובית הראשונה מתחילה ב: {first_subtitle_start_time:.2f} שניות. יוצר קליפ כותרת במשך {title_duration:.2f} שניות.")
     if title_duration > 0:
         try:
             title_max_width = video_resolution[0] * 0.9
             # Use method='label' for single line title for potentially better centering
             title_clip = mp.TextClip(song_title_text, font=font_path, fontsize=fontsize_title, color=color_title,
                                      stroke_color=stroke_color_title, stroke_width=stroke_width_title,
                                      method='label') # Changed to label
             # Resize if too wide after rendering as label
             if title_clip.w > title_max_width:
                  title_clip = title_clip.resize(width=title_max_width)

             title_clip = title_clip.set_position(position_title).set_duration(title_duration).set_start(0)
             print("קליפ כותרת נוצר.")
         except Exception as e:
             print(f"שגיאה ביצירת קליפ הכותרת: {e}")
             title_clip = None
     else:
          print("משך הכותרת המחושב הוא 0, מדלג על יצירת קליפ כותרת.")


# --- פונקציית עזר לציור טקסט עם קו מתאר (ללא שינוי) ---
def draw_text_with_stroke(draw, pos, text, font, fill_color, stroke_color, stroke_width_local):
    x, y = pos
    offset = stroke_width_local
    draw.text((x - offset, y), text, font=font, fill=stroke_color)
    draw.text((x + offset, y), text, font=font, fill=stroke_color)
    draw.text((x, y - offset), text, font=font, fill=stroke_color)
    draw.text((x, y + offset), text, font=font, fill=stroke_color)
    draw.text((x, y), text, font=font, fill=fill_color)


# --- פונקציית עזר לבדיקה אם שורה מכילה עברית (ללא שינוי) ---
def is_hebrew(text_line):
    return any('\u0590' <= char <= '\u05FF' for char in text_line)

# --- פונקציית עיבוד כתוביות מעודכנת - מקבלת נתוני JSON ---
def create_styled_subtitle_clip_pil(subs_data_en, subs_data_he, font_path_local, font_size_en, font_size_he,
                                   text_color, stroke_color, stroke_width_local,
                                   spacing_intra, spacing_inter,
                                   video_res, total_duration, video_fps_local): # Pass fps

    subs_en = subs_data_en if isinstance(subs_data_en, list) else []
    subs_he = subs_data_he if isinstance(subs_data_he, list) else []
    combined_subs_format = []
    subtitle_id_counter = 0

    if not subs_en and not subs_he:
        print("אזהרה: לא סופקו נתוני כתוביות (אנגלית או עברית).")
        return mp.ColorClip(size=video_res, color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0), []

    # --- שילוב הכתוביות מה-JSON ---
    subs_en_map = {str(sub.get('id', f'en_{i}')): sub for i, sub in enumerate(subs_en)}
    subs_he_map = {str(sub.get('id', f'he_{i}')): sub for i, sub in enumerate(subs_he)}
    all_ids = sorted(list(set(subs_en_map.keys()) | set(subs_he_map.keys())))

    print(f"DEBUG: Starting merge. Found {len(subs_en_map)} EN keys, {len(subs_he_map)} HE keys. Total unique IDs: {len(all_ids)}") # DEBUG

    for idx in all_ids:
        sub_en = subs_en_map.get(idx)
        sub_he = subs_he_map.get(idx)
        en_start, en_end, en_text = (0, 0, "")
        he_start, he_end, he_text = (0, 0, "")
        valid_en, valid_he = False, False

        # --- Validate English ---
        try:
            if sub_en and 'start_time' in sub_en and 'end_time' in sub_en and 'text' in sub_en:
                 en_start = max(0, float(sub_en['start_time']))
                 en_end = max(en_start, float(sub_en['end_time'])) # Ensure end >= start
                 # Treat empty string text as invalid for combination purposes
                 en_text_raw = sub_en.get('text', None)
                 if en_text_raw is not None: # Allow empty string only if explicitly present
                      en_text = str(en_text_raw).strip().replace('\\n', '\n')
                      # Check duration and non-empty text (allowing whitespace-only text for now)
                      if en_end > en_start: # Removed the non-empty check here, handle later
                          valid_en = True
        except (ValueError, TypeError) as e: print(f"Warning: Invalid data in English sub ID {idx}: {e}")

        # --- Validate Hebrew ---
        try:
            if sub_he and 'start_time' in sub_he and 'end_time' in sub_he and 'text' in sub_he:
                 he_start = max(0, float(sub_he['start_time']))
                 he_end = max(he_start, float(sub_he['end_time']))
                 he_text_raw = sub_he.get('text', None)
                 if he_text_raw is not None:
                      he_text = str(he_text_raw).strip().replace('\\n', '\n')
                      if he_end > he_start: # Removed non-empty check
                          valid_he = True
        except (ValueError, TypeError) as e: print(f"Warning: Invalid data in Hebrew sub ID {idx}: {e}")

        # --- Combine Text and Times (More Flexible) ---
        combined_text_parts = []
        start_time = float('inf')
        end_time = 0

        if valid_en and en_text: # Add English if valid and has non-empty text after stripping
            combined_text_parts.append(en_text)
            start_time = min(start_time, en_start)
            end_time = max(end_time, en_end)

        if valid_he and he_text: # Add Hebrew if valid and has non-empty text after stripping
            combined_text_parts.append(he_text)
            start_time = min(start_time, he_start)
            end_time = max(end_time, he_end)

        # Only proceed if we have at least one valid text part
        if combined_text_parts:
            # Join with double newline only if both parts exist
            combined_text = "\n\n".join(combined_text_parts)
            sub_id = f"combined_sub_{idx}_{subtitle_id_counter}"

            # Ensure duration is at least one frame
            min_duration = 1.0 / video_fps_local
            if end_time - start_time < min_duration:
                end_time = start_time + min_duration

            # Clip times to total duration
            end_time = min(end_time, total_duration)
            start_time = min(start_time, total_duration) # Clip start time too

            if end_time > start_time: # Final check
                combined_subs_format.append(((start_time, end_time), combined_text.strip(), sub_id))
                subtitle_id_counter += 1

    if not combined_subs_format:
        print("אזהרה: לא נוצרו כתוביות משולבות תקינות."); return mp.ColorClip(size=video_res, color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0), []

    combined_subs_format.sort(key=lambda item: item[0][0])
    print(f"DEBUG: Finished merge. Combined {len(combined_subs_format)} subtitle entries.")
    # --- Generator function (same as before) ---
    def generator(txt):
        try:
            font_en = ImageFont.truetype(font_path_local, font_size_en)
            font_he = ImageFont.truetype(font_path_local, font_size_he)
        except Exception as e: print(f"שגיאה קריטית בטעינת פונט PIL '{font_path_local}': {e}"); return mp.ColorClip(size=(1,1), color=(0,0,0,0), ismask=True, duration=0.1).set_opacity(0)

        max_text_width = video_res[0] * 0.8 # Allow slightly wider text

        # Handle potential empty text passed by SubtitlesClip
        if not txt or not txt.strip():
            empty_frame_array = np.zeros((video_res[1], video_res[0], 4), dtype=np.uint8) # H, W, 4 (RGBA)
            # Return an ImageClip with minimal duration
            return mp.ImageClip(empty_frame_array, ismask=False, transparent=True).set_duration(1.0/video_fps_local)


        img = Image.new('RGBA', video_res, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Split text into lines, handling potential double line breaks from merging
        original_lines = [line for line in txt.splitlines() if line.strip()] # Filter out empty lines


        def wrap_text(line_text, font, max_width):
            words = line_text.split(' ')
            wrapped_lines = []
            current_line = ''
            for word in words:
                if not word: continue

                test_line = f"{current_line} {word}".strip()
                try:
                    # Use textbbox for potentially more accurate width
                    bbox = draw.textbbox((0, 0), test_line, font=font)
                    line_width = bbox[2] - bbox[0]
                except Exception: # Fallback if textbbox fails
                     try: line_width = draw.textlength(test_line, font=font)
                     except AttributeError: line_width = len(test_line) * font.size * 0.6 # Rough estimate


                if line_width <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        wrapped_lines.append(current_line)
                    current_line = word
                    try: # Check width of the single word
                         bbox_word = draw.textbbox((0, 0), current_line, font=font)
                         word_width = bbox_word[2] - bbox_word[0]
                    except Exception:
                         try: word_width = draw.textlength(current_line, font=font)
                         except AttributeError: word_width = len(current_line) * font.size * 0.6

                    if word_width > max_width:
                         # print(f"אזהרה: מילה בודדת '{word}' ארוכה מרוחב השורה המותר ({max_width:.0f}px).")
                         # Just add the long word as its own line, even if it overflows
                         if current_line:
                             wrapped_lines.append(current_line)
                         current_line = "" # Reset for next word

            if current_line:
                wrapped_lines.append(current_line)

            return wrapped_lines or ([line_text.strip()] if line_text.strip() else [])


        total_text_height = 0
        processed_line_details = []
        original_line_is_hebrew = []

        flat_line_counter = 0
        last_original_index = -1
        for i, line in enumerate(original_lines):
            is_heb = is_hebrew(line)
            original_line_is_hebrew.append(is_heb)
            font_for_line = font_he if is_heb else font_en
            # --- Wrapping ---
            wrapped_lines_for_current = wrap_text(line, font_for_line, max_text_width)

            for k, wrapped_line in enumerate(wrapped_lines_for_current):
                processed_line_details.append({
                    'text': wrapped_line,
                    'font': font_for_line,
                    'is_hebrew': is_heb,
                    'original_index': i, # Index within the *filtered* original_lines list
                    'is_first_wrapped': k == 0, # Is this the first line from a wrap?
                    'flat_index': flat_line_counter
                })
                flat_line_counter += 1
            last_original_index = i


        # --- Calculate Geometry & Spacing ---
        num_processed_lines = len(processed_line_details)
        for k, detail in enumerate(processed_line_details):
            try:
                bbox = draw.textbbox((0, 0), detail['text'], font=detail['font'], anchor='lt') # Use left-top anchor
                detail['width'] = bbox[2] - bbox[0]
                detail['height'] = bbox[3] - bbox[1]
                detail['y_offset'] = bbox[1] # Vertical offset from baseline
            except Exception as e:
                print(f"Warning calculating bbox for '{detail['text']}': {e}. Using fallback.")
                detail['width'] = draw.textlength(detail['text'], font=detail['font']) if hasattr(draw, 'textlength') else 100
                detail['height'] = detail['font'].size * 1.2 # Add some padding for height fallback
                detail['y_offset'] = 0

            # --- Determine spacing AFTER this line ---
            current_spacing = 0
            is_last_line_overall = (k == num_processed_lines - 1)

            if not is_last_line_overall:
                next_detail = processed_line_details[k+1]
                # Check if next line belongs to the same original line (wrap)
                if detail['original_index'] == next_detail['original_index']:
                    current_spacing = spacing_intra # Small space for wrapped lines
                else:
                    # Next line is from a different original subtitle line (language change or next block)
                     current_spacing = spacing_inter # Larger space between language blocks

            detail['spacing_after'] = current_spacing
            total_text_height += detail['height'] + current_spacing

        # Adjust total height (remove last spacing which isn't needed)
        if processed_line_details:
             total_text_height -= processed_line_details[-1]['spacing_after']


        # --- Drawing ---
        current_y = (video_res[1] - total_text_height) / 2

        for detail in processed_line_details:
            x_text = (video_res[0] - detail['width']) / 2
            text_to_draw = detail['text']

            if detail['is_hebrew']:
                try:
                    reshaped_text = arabic_reshaper.reshape(text_to_draw)
                    text_to_draw = get_display(reshaped_text)
                except Exception as e:
                    print(f"שגיאה בעיבוד BiDi עבור: '{text_to_draw}'. שגיאה: {e}")

            # Adjust Y pos by bbox offset for more accurate vertical placement
            draw_y = current_y #- detail['y_offset'] # Experiment with/without y_offset correction
            draw_text_with_stroke(draw, (x_text, draw_y), text_to_draw, detail['font'],
                                  text_color, stroke_color, stroke_width_local)

            current_y += detail['height'] + detail['spacing_after']


        frame_array = np.array(img)
        # Return an ImageClip with minimal duration, SubtitlesClip handles the actual timing
        return mp.ImageClip(frame_array, ismask=False, transparent=True).set_duration(1.0/video_fps_local)
    # --- End of Generator ---

    # --- Create SubtitlesClip ---
    subs_for_moviepy = [(item[0], item[1]) for item in combined_subs_format]

    if not subs_for_moviepy:
        print("אזהרה: אין כתוביות תקינות להזנה ל-MoviePy.")
        return mp.ColorClip(size=video_res, color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0), []

    try:
        # Increase SubtitlesClip verbosity for debugging if needed
        subtitle_moviepy_clip = SubtitlesClip(subs_for_moviepy, generator)#, verbose=True)
        subtitle_moviepy_clip = subtitle_moviepy_clip.set_duration(total_duration).set_position('center')
        print(f"SubtitlesClip created with duration: {subtitle_moviepy_clip.duration:.2f}s")
    except Exception as e:
        print(f"שגיאה קריטית ביצירת SubtitlesClip: {e}")
        import traceback
        traceback.print_exc()
        return mp.ColorClip(size=video_res, color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0), []

    return subtitle_moviepy_clip, combined_subs_format


# --- עיבוד כתוביות משולב ---
print("מעבד כתוביות משולבות (אנגלית ועברית) מנתוני JSON באמצעות PIL עם BiDi...")
subtitles_clip, combined_subs_list_for_frames = create_styled_subtitle_clip_pil(
    english_subtitle_data, hebrew_subtitle_data,
    font_path, fontsize_en, fontsize_he, color_subs,
    stroke_color_subs, stroke_width_subs,
    spacing_within_language, spacing_between_languages,
    video_resolution, audio_duration, video_fps # Pass video_fps
)

# בדיקה אם הקליפ נוצר בהצלחה
if not hasattr(subtitles_clip, 'duration') or subtitles_clip.duration <= 0:
     print("יצירת הוידאו בוטלה עקב שגיאה קריטית ביצירת קליפ הכתוביות או קליפ ריק.")
     try: audio_clip.close()
     except: pass
     try: background_clip.close()
     except: pass
     exit()
elif subtitles_clip.duration > audio_duration + 1:
    print(f"Warning: Subtitles clip duration ({subtitles_clip.duration:.2f}s) exceeds audio duration ({audio_duration:.2f}s). Trimming.")
    subtitles_clip = subtitles_clip.set_duration(audio_duration)


# --- פונקציה לניקוי שם קובץ (משופרת) ---
def sanitize_filename(text, max_len=50):
    text = text.replace('\n', ' ').replace('\r', '')
    # Remove specific problematic characters for filenames
    text = re.sub(r'[\\/*?:"<>|.!@#$%^&+=~`{}\[\];\'’,]', "", text)
    text = text.strip()
    text = re.sub(r'\s+', ' ', text) # Consolidate whitespace
    if not text: return "subtitle" # Handle empty string case

    # Truncate if too long
    if len(text) > max_len:
        # Try cutting at last space before max_len
        cut_point = text.rfind(' ', 0, max_len)
        # Ensure cut_point isn't too early (e.g., first word is very long)
        if cut_point != -1 and cut_point > max_len // 2 :
             text = text[:cut_point].rstrip() + "..."
        else:
             # Otherwise, just hard cut
             text = text[:max_len].rstrip() + "..."
    return text

# --- הכנת נתונים לשמירת פריימים ---
saved_subtitle_ids = set() # Re-initialize here to ensure it's fresh for each run

# --- פונקציית עיבוד ושמירת פריימים ---
print("מגדיר פונקציית שמירת פריימים...")
def save_subtitle_frame_processor(get_frame, t):
    # Get the frame for the current time
    try:
        frame = get_frame(t)
    except Exception as e:
        # This can happen near the very end of the clip sometimes
        # print(f"Warning: Could not get frame at t={t:.4f}. Error: {e}")
        # Return a black frame or the last good frame if possible? For now, just return None or re-raise
        # Returning a dummy frame to avoid crashing write_videofile
        return np.zeros((video_resolution[1], video_resolution[0], 3), dtype=np.uint8) # Return black frame

    # Check if time 't' falls within any subtitle interval
    active_sub_found = None
    for interval, text, sub_id in combined_subs_list_for_frames:
        start_time, end_time = interval
        # Use a small epsilon for float comparison robustness
        epsilon = 1 / (video_fps * 2) # Half frame duration tolerance
        if (start_time - epsilon) <= t < (end_time - epsilon):
            active_sub_found = (text, sub_id)
            break # Found the active subtitle for this time 't'

    if active_sub_found:
        text, sub_id = active_sub_found
        if sub_id not in saved_subtitle_ids:
            try:
                # Format time for filename (e.g., 0065_123 for 65.123 seconds)
                time_sec = int(t)
                time_ms = int((t - time_sec) * 1000)
                time_str = f"{time_sec:04d}_{time_ms:03d}"
                safe_text = sanitize_filename(text)
                # Limit filename length further if needed
                max_fname_len = 150
                filename_base = f"frame_{time_str}_{safe_text}"
                filename = os.path.join(output_frames_dir, f"{filename_base[:max_fname_len]}.png")

                # Prevent overwriting if file exists (e.g., from rounding issues)
                if not os.path.exists(filename):
                    imageio.imwrite(filename, frame)
                saved_subtitle_ids.add(sub_id)
                # print(f"DEBUG: Processed frame for sub {sub_id} at t={t:.3f}") # Optional debug

            except Exception as e:
                print(f"שגיאה בשמירת פריים {t:.3f}s (sub_id: {sub_id}): {e}")
                saved_subtitle_ids.add(sub_id) # Mark as processed even if save failed

    # Always return the original frame
    return frame


# --- שילוב הקליפים ---
print("משלב את הרקע, הכותרת (אם קיימת), כתוביות משולבות ואודיו...")
clips_to_composite = [background_clip]
if title_clip and title_clip.duration > 0:
    clips_to_composite.append(title_clip)
if subtitles_clip and subtitles_clip.duration > 0:
    clips_to_composite.append(subtitles_clip)
else:
    print("אזהרה: קליפ הכתוביות אינו תקין או שמשכו 0, הוא לא ישולב בוידאו.")

if not clips_to_composite:
     print("Error: No valid clips to composite. Exiting.")
     exit()

# Ensure the composite respects the intended video size
final_clip = mp.CompositeVideoClip(clips_to_composite, size=video_resolution)
# Set duration explicitly from audio AFTER composition
final_clip = final_clip.set_duration(audio_duration)


# --- החלת פונקציית שמירת הפריימים ---
print("מחבר את מנגנון שמירת הפריימים לקליפ...")
# Check if there are subtitles AND the clip is valid
if combined_subs_list_for_frames and final_clip and final_clip.duration > 0:
     final_clip_with_saving = final_clip.fl(save_subtitle_frame_processor, apply_to=['color'])
     # Propagate duration just in case fl changes it (it shouldn't)
     final_clip_with_saving = final_clip_with_saving.set_duration(final_clip.duration)
else:
    print("אזהרה: אין כתוביות לשמירת פריימים או שהקליפ אינו תקין.")
    final_clip_with_saving = final_clip # Use the clip without the frame processor


# --- הוספת אודיו ---
print("מוסיף את האודיו לקליפ הסופי...")
if audio_clip:
    final_clip_with_saving = final_clip_with_saving.set_audio(audio_clip)
    # Final duration check after adding audio
    final_clip_with_saving = final_clip_with_saving.set_duration(audio_duration)
else:
    print("Warning: No valid audio clip to attach.")


# --- יצירת קובץ הוידאו הסופי ---
print(f"יוצר את קובץ הוידאו '{output_video_file}'...")
temp_audio_file = os.path.join(output_dir, f'temp-audio-{output_video_base}.m4a')
try:
    # Ensure the final clip object is valid before writing
    if not final_clip_with_saving or final_clip_with_saving.duration <= 0:
         raise ValueError("Final video clip is invalid or has zero duration.")

    final_clip_with_saving.write_videofile(
        output_video_file,
        fps=video_fps,
        codec='libx264',
        audio_codec='aac',
        temp_audiofile=temp_audio_file,
        remove_temp=True,
        threads=max(1, (os.cpu_count() or 2) // 2), # Conservative thread usage
        preset='medium',
        logger='bar',
        # ffmpeg_params=["-loglevel", "error"] # Reduce ffmpeg console noise
    )
    print(f"\nיצירת הוידאו '{output_video_file}' הושלמה בהצלחה!")
    if combined_subs_list_for_frames:
        print(f"פריימים נשמרו בתיקייה: '{output_frames_dir}'")
except Exception as e:
    print(f"\nשגיאה במהלך יצירת הוידאו:\n{e}")
    import traceback
    traceback.print_exc()
finally:
    # --- מחיקת קובץ temp audio ---
    if os.path.exists(temp_audio_file):
        try: os.remove(temp_audio_file); print(f"קובץ temp audio נמחק: {temp_audio_file}")
        except Exception as e: print(f"אזהרה: לא ניתן למחוק את קובץ temp audio '{temp_audio_file}': {e}")

    # --- שחרור משאבים ---
    print("משחרר משאבים...")
    for clip_var_name in ['audio_clip', 'background_clip', 'title_clip', 'subtitles_clip', 'final_clip', 'final_clip_with_saving']:
        clip_obj = locals().get(clip_var_name)
        if clip_obj and hasattr(clip_obj, 'close') and callable(getattr(clip_obj, 'close', None)):
            try:
                clip_obj.close()
            except Exception as e_close:
                print(f"Warning: Error closing {clip_var_name}: {e_close}")

    print("סיום.")