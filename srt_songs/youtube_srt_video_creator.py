import base64
import os
from google import genai
from google.genai import types
import re
import urllib.parse
import moviepy.editor as mp
from moviepy.video.tools.subtitles import SubtitlesClip
import pysrt # To parse SRT files
import math # For ceiling function
import imageio # לשמירת תמונות
import numpy as np # MoviePy משתמש בזה, וגם אנחנו לקליפ תמונה
from PIL import Image, ImageDraw, ImageFont # ליצירת טקסט מתקדמת
import arabic_reshaper # <<< חדש: לעיצוב תווים ערביים/עבריים
from bidi.algorithm import get_display # <<< חדש: לסדר תצוגה מימין לשמאל (RTL)

# --- הגדרות נתיבים ותיקיות ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # נתיב לסקריפט הנוכחי
DATA_DIR = os.path.join(BASE_DIR, '..', 'data', 'levels')
ASSETS_DIR = os.path.join(BASE_DIR, '..', 'assets')
FONTS_DIR = os.path.join(ASSETS_DIR, 'fonts')
output_frames_dir = os.path.join(BASE_DIR, "subtitle_frames") # תיקייה לשמירת תמונות
srt_files_dir = os.path.join(BASE_DIR, "srt_files")  # תיקייה לשמירת קבצי SRT
output_dir = os.path.join(BASE_DIR, "output")  # תיקייה לשמירת קבצי וידאו

# --- יצירת תיקיות נדרשות ---
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)
os.makedirs(output_frames_dir, exist_ok=True)
os.makedirs(srt_files_dir, exist_ok=True)  # יצירת תיקיית SRT
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
spacing_within_language = 10 # <<< רווח קטן בין שורות באותה שפה
spacing_between_languages = 35 # <<< רווח גדול יותר בין אנגלית לעברית

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


def clean_srt_content(srt_text):
    """
    Extracts content within ```srt ... ``` or ``` ... ``` blocks,
    discarding any text outside the block.
    Falls back to returning the original text (stripped) if no block is found.
    """
    # Pattern to find ```srt ... ``` or ``` ... ```, capturing the content inside
    # re.DOTALL makes '.' match newlines as well
    # (?:srt)? makes 'srt' optional non-capturing group
    # (.*?) captures the content non-greedily
    pattern = r"```(?:srt)?\s*(.*?)\s*```"
    match = re.search(pattern, srt_text, re.DOTALL)

    if match:
        # Extract the captured group (the content inside the fences)
        # and strip leading/trailing whitespace from it
        cleaned_content = match.group(1).strip()
        # Optional: Add a check to ensure the cleaned content isn't empty
        # if not cleaned_content:
        #    print("Warning: Extracted SRT content is empty after cleaning.")
        return cleaned_content
    else:
        # If no fences found, assume the input might be the SRT content itself.
        # Return the original text stripped, as a fallback.
        # This handles cases where the API returns just the SRT without fences.
        print("Warning: Could not find SRT Markdown block (```srt...```). Returning original text stripped.")
        return srt_text.strip()


def generate_srt_from_youtube(youtube_url):
    # --- חישוב שמות קבצים צפויים ---
    try:
        parsed_url = urllib.parse.urlparse(youtube_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        video_id = query_params.get('v')
        if video_id:
            base_filename = video_id[0]
        else:
            # Fallback (כמו בקוד המקורי שלך, תלוי ב-mp3_file הגלובלי)
            base_filename = re.sub(r'\W+', '_', os.path.splitext(os.path.basename(mp3_file))[0]) if 'mp3_file' in globals() and mp3_file else "default_song"
            print(f"אזהרה: לא זוהה Video ID מהקישור. משתמש בשם חלופי: {base_filename}")

        english_srt_filename = os.path.join(srt_files_dir, f"{base_filename}_en.srt")
        hebrew_srt_filename = os.path.join(srt_files_dir, f"{base_filename}_he.srt")
    except Exception as e:
        print(f"שגיאה בניתוח הקישור או הגדרת שמות קבצים: {e}")
        print("לא ניתן לבדוק קבצים קיימים. ממשיך לנסות ליצור כתוביות.")
        english_srt_filename = None # סמן כלא ידוע כדי למנוע שגיאות בהמשך הבדיקה
        hebrew_srt_filename = None

    # --- בדיקה אם קבצי SRT כבר קיימים ---
    if english_srt_filename and hebrew_srt_filename and \
       os.path.exists(english_srt_filename) and os.path.exists(hebrew_srt_filename):
        print(f"\nנמצאו קבצי SRT קיימים:\n  EN: {english_srt_filename}\n  HE: {hebrew_srt_filename}")
        print("מדלג על שלב יצירת הכתוביות מ-YouTube וטוען את הקבצים הקיימים.")
        try:
            with open(english_srt_filename, "r", encoding="utf-8") as f_en:
                english_srt_content = f_en.read()
            with open(hebrew_srt_filename, "r", encoding="utf-8") as f_he:
                hebrew_srt_content = f_he.read()

            if not english_srt_content.strip() or not hebrew_srt_content.strip():
                 print("אזהרה: אחד מקבצי ה-SRT הקיימים ריק. ממשיך ליצירה מחדש.")
            else:
                 print("תוכן הכתוביות נטען בהצלחה מהקבצים.")
                 return english_srt_content, hebrew_srt_content # <<< החזרה מוקדמת עם התוכן הקיים

        except Exception as e:
            print(f"שגיאה בקריאת קבצי SRT קיימים: {e}. ממשיך לנסות ליצור כתוביות מחדש.")
            # אם הקריאה נכשלה, נמשיך לשלב היצירה למטה

    # --- אם הקבצים לא קיימים או היתה שגיאה בקריאה, המשך עם היצירה ---
    print("\nקבצי SRT לא נמצאו או היו שגויים. מתחיל תהליך יצירה מ-YouTube...")

    if not os.environ.get("GEMINI_API_KEY"):
        print("שגיאה: לא נמצא מפתח API של Gemini. אנא הגדר את משתנה הסביבה GEMINI_API_KEY.")
        return None, None

    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    model = "gemini-2.0-flash-thinking-exp" # "gemini-2.5-pro-exp-03-25"  # or a suitable model

    system_instruction_content = """עליך לתמלל את השירים שאתה מקבל באופן מדויק בפורמט SRT, בצע חלוקה חכמה של הקטעים בהתאם לקטעי השיר"""

    generate_content_config = types.GenerateContentConfig(
        response_mime_type="text/plain",
        system_instruction=[
            types.Part.from_text(text=system_instruction_content),
        ],
    )

    contents_english = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_uri(
                    file_uri=youtube_url,
                    mime_type="video/*",
                ),
                types.Part.from_text(text="תתמלל את השיר הבא באופן מדויק בפורמט SRT, בצע חלוקה חכמה של הקטעים בהתאם לקטעי השיר"),
            ],
        ),
    ]

    print("Generating English SRT...")
    english_srt_content_raw = ""
    # ... (המשך הלולאה שלך לקבלת התוכן האנגלי) ...
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents_english,
        config=generate_content_config,
    ):
        # print(chunk.text, end="") # אפשר לכבות את ההדפסה הזו אם רוצים
        english_srt_content_raw += chunk.text
    print("English SRT generation complete.")


    english_srt_content = clean_srt_content(english_srt_content_raw)
    print("\n--- English SRT Cleaned ---")

    # ודא שיש לנו שמות קבצים גם אם החישוב הראשוני נכשל מסיבה כלשהי
    if not english_srt_filename:
        base_filename = "generated_fallback" # שם קובץ חלופי במקרה קיצון
        english_srt_filename = os.path.join(srt_files_dir, f"{base_filename}_en.srt")
        hebrew_srt_filename = os.path.join(srt_files_dir, f"{base_filename}_he.srt")


    # --- שמירת קובץ SRT אנגלי (התוכן הנקי) ---
    try:
        with open(english_srt_filename, "w", encoding="utf-8") as f:
            f.write(english_srt_content)
        print(f"\nEnglish SRT saved to: {english_srt_filename}")
    except Exception as e:
        print(f"\nError saving English SRT file '{english_srt_filename}': {e}")
        return None, None  # Stop if saving fails


    # --- הכנת קלט לתרגום (שימוש בתוכן הנקי) ---
    # ... (המשך הקוד שלך ליצירת התרגום העברי) ...
    contents_hebrew = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=f"""מצורף כאן תוכן קובץ SRT של שיר באנגלית. עליך לתרגם אותו לעברית בצורה מדויקת תוך שמירה על פורמט ה-SRT וחלוקת הקטעים המקורית. אל תכתוב שום דבר בתגובה למעט תוכן ה-SRT המתורגם!:

{english_srt_content}"""),
            ],
        ),
    ]

    print("\nGenerating Hebrew SRT...")
    hebrew_srt_content_raw = ""
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents_hebrew,
        config=generate_content_config,
    ):
        # print(chunk.text, end="") # אפשר לכבות
        hebrew_srt_content_raw += chunk.text
    print("Hebrew SRT generation complete.")

    hebrew_srt_content = clean_srt_content(hebrew_srt_content_raw)
    print("\n--- Hebrew SRT Cleaned ---")

    # --- שמירת קובץ SRT עברי (התוכן הנקי) ---
    try:
        with open(hebrew_srt_filename, "w", encoding="utf-8") as f:
            f.write(hebrew_srt_content)
        print(f"\nHebrew SRT saved to: {hebrew_srt_filename}")
    except Exception as e:
        print(f"\nError saving Hebrew SRT file '{hebrew_srt_filename}': {e}")
        return english_srt_content, None # החזר רק אנגלית אם שמירת עברית נכשלה


    # --- החזרת התוכן הנקי שנוצר ---
    return english_srt_content, hebrew_srt_content

# --- קריאה לפונקציה ---
print("בודק או יוצר כתוביות מיוטיוב...")
# שאר הקוד לא משתנה - הוא יקבל את התוכן מהפונקציה, בין אם נוצר עכשיו או נטען מקובץ
english_srt_content, hebrew_srt_content = generate_srt_from_youtube(youtube_link)

if not english_srt_content or not hebrew_srt_content:
    print("שגיאה בהפקת או טעינת כתוביות. יציאה.")
    exit()

# חישוב שמות הקבצים שוב לצורך וידוא ושמירה (למקרה שהיו חסרים קודם)
parsed_url = urllib.parse.urlparse(youtube_link)
query_params = urllib.parse.parse_qs(parsed_url.query)
video_id = query_params.get('v')
if video_id:
    base_filename = video_id[0]
else:
    base_filename = re.sub(r'\W+', '_', os.path.splitext(os.path.basename(mp3_file))[0]) if 'mp3_file' in globals() and mp3_file else "default_song"

# Update paths for SRT files
srt_en_file = os.path.join(srt_files_dir, f"{base_filename}_en.srt")
srt_he_file = os.path.join(srt_files_dir, f"{base_filename}_he.srt")

with open(srt_en_file, "w", encoding="utf-8") as f:
    f.write(english_srt_content)
print(f"\nEnglish SRT saved to: {srt_en_file}")

with open(srt_he_file, "w", encoding="utf-8") as f:
    f.write(hebrew_srt_content)
print(f"Hebrew SRT saved to: {srt_he_file}")


# --- הגדרת שם קובץ פלט ושם השיר ---
output_video_base = os.path.splitext(os.path.basename(mp3_file))[0]
output_video_file = os.path.join(output_dir, f"{output_video_base}_subtitled.mp4")  # עדכון שם קובץ פלט
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
    background_clip = mp.ImageClip(background_image_path, duration=audio_duration)
    background_clip = background_clip.resize(height=video_resolution[1])
    background_clip = background_clip.crop(x_center=background_clip.w/2, width=video_resolution[0])
    background_clip = background_clip.resize(video_resolution)
    background_clip = background_clip.set_fps(video_fps)
except Exception as e:
    print(f"שגיאה בטעינת או עיבוד תמונת הרקע '{background_image_path}': {e}"); exit()

# --- מציאת זמן התחלה של הכתובית הראשונה ---
first_subtitle_start_time = audio_duration
try:
    subs_en_timing = pysrt.open(srt_en_file, encoding='utf-8')
    if subs_en_timing and subs_en_timing[0].start.ordinal >= 0: # Ensure non-negative start time
        first_subtitle_start_time = min(first_subtitle_start_time, subs_en_timing[0].start.ordinal / 1000.0)
except Exception as e:
    print(f"Warning: Could not parse English SRT for timing: {e}")
try:
    subs_he_timing = pysrt.open(srt_he_file, encoding='utf-8')
    if subs_he_timing and subs_he_timing[0].start.ordinal >= 0: # Ensure non-negative start time
        first_subtitle_start_time = min(first_subtitle_start_time, subs_he_timing[0].start.ordinal / 1000.0)
except Exception as e:
    print(f"Warning: Could not parse Hebrew SRT for timing: {e}")

# Define a minimum duration needed to display the title meaningfully
min_title_duration_threshold = 0.5 # <<< החלט כמה זמן מינימום הכותרת צריכה להופיע (למשל 0.5 שניות)

title_clip = None # Initialize title_clip to None

if first_subtitle_start_time < min_title_duration_threshold:
    print(f"אזהרה: הכתובית הראשונה מתחילה מוקדם מאוד ({first_subtitle_start_time:.2f}s). מדלג על הצגת כותרת השיר.")
    # Make sure first_subtitle_start_time isn't used incorrectly later if it was audio_duration
    if first_subtitle_start_time >= audio_duration:
         first_subtitle_start_time = 0 # Reset if no valid subtitles were found
else:
     # Only create title if there's enough time before the first subtitle
     print(f"הכתובית הראשונה מתחילה ב: {first_subtitle_start_time:.2f} שניות. יוצר קליפ כותרת.")
     try:
         title_max_width = video_resolution[0] * 0.9
         title_clip = mp.TextClip(song_title_text, font=font_path, fontsize=fontsize_title, color=color_title,
                                  stroke_color=stroke_color_title, stroke_width=stroke_width_title,
                                  method='caption', align='center', size=(title_max_width, None))
         # Set duration EXPLICITLY to the calculated start time
         title_clip = title_clip.set_position(position_title).set_duration(first_subtitle_start_time).set_start(0)
         print("קליפ כותרת נוצר.")
     except Exception as e:
         print(f"שגיאה ביצירת קליפ הכותרת: {e}")
         title_clip = None # Ensure title_clip is None if creation failed

# --- יצירת קליפ כותרת השיר (אם צריך) ---
title_clip = None
if first_subtitle_start_time > 0:
    print("יוצר קליפ לכותרת השיר...")
    try:
        title_max_width = video_resolution[0] * 0.9
        title_clip = mp.TextClip(song_title_text, font=font_path, fontsize=fontsize_title, color=color_title,
                                 stroke_color=stroke_color_title, stroke_width=stroke_width_title,
                                 method='caption', align='center', size=(title_max_width, None))
        title_clip = title_clip.set_position(position_title).set_duration(first_subtitle_start_time).set_start(0)
        print("קליפ כותרת נוצר.")
    except Exception as e:
        print(f"שגיאה ביצירת קליפ הכותרת: {e}"); title_clip = None

# --- פונקציית עזר לציור טקסט עם קו מתאר ---
def draw_text_with_stroke(draw, pos, text, font, fill_color, stroke_color, stroke_width_local):
    x, y = pos
    draw.text((x - stroke_width_local, y - stroke_width_local), text, font=font, fill=stroke_color)
    draw.text((x + stroke_width_local, y - stroke_width_local), text, font=font, fill=stroke_color)
    draw.text((x - stroke_width_local, y + stroke_width_local), text, font=font, fill=stroke_color)
    draw.text((x + stroke_width_local, y + stroke_width_local), text, font=font, fill=stroke_color)
    draw.text((x, y), text, font=font, fill=fill_color)

# --- פונקציית עזר לבדיקה אם שורה מכילה עברית ---
def is_hebrew(text_line):
    return any('\u0590' <= char <= '\u05FF' for char in text_line)

# --- פונקציית עיבוד כתוביות מעודכנת - עם BiDi, רווחים משופרים וגלישת שורות ---
def create_styled_subtitle_clip_pil(srt_en_file_local, srt_he_file_local, font_path_local, font_size_en, font_size_he,
                                   text_color, stroke_color, stroke_width_local,
                                   spacing_intra, spacing_inter, # <<< רווחים: spacing_intra לגלישה פנימית, spacing_inter בין קטעי זמן
                                   video_res, total_duration):
    subs_en = []
    subs_he = []
    combined_subs_format = []
    subtitle_id_counter = 0

    # --- 1. קריאת קבצי SRT ---
    try:
        subs_en_pysrt = pysrt.open(srt_en_file_local, encoding='utf-8')
        subs_en = [(sub.start.ordinal / 1000.0, sub.end.ordinal / 1000.0, sub.text_without_tags.strip().replace('\\N', '\n').replace('\\n', '\n')) for sub in subs_en_pysrt if sub.text_without_tags.strip()]
    except Exception as e: print(f"אזהרה: לא ניתן לקרוא קובץ אנגלית '{srt_en_file_local}': {e}")
    try:
        subs_he_pysrt = pysrt.open(srt_he_file_local, encoding='utf-8')
        subs_he = [(sub.start.ordinal / 1000.0, sub.end.ordinal / 1000.0, sub.text_without_tags.strip().replace('\\N', '\n').replace('\\n', '\n')) for sub in subs_he_pysrt if sub.text_without_tags.strip()]
    except Exception as e: print(f"אזהרה: לא ניתן לקרוא קובץ עברית '{srt_he_file_local}': {e}")

    if not subs_en and not subs_he:
        print("אזהרה: לא נמצאו כתוביות."); return mp.ColorClip(size=(1,1), color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0), []

    # --- 2. שילוב הכתוביות ---
    max_len = max(len(subs_en), len(subs_he))
    for i in range(max_len):
        en_start, en_end, en_text = subs_en[i] if i < len(subs_en) else (0, 0, "")
        he_start, he_end, he_text = subs_he[i] if i < len(subs_he) else (0, 0, "")
        start_time = min(en_start, he_start) if en_text and he_text else (en_start if en_text else he_start)
        # Handle case where one subtitle starts much later than the other in the first pair
        if i == 0 and en_text and he_text and abs(en_start - he_start) > 0.1: # Threshold can be adjusted
             start_time = max(en_start, he_start) # Start when both are ready if significantly different
        elif i == 0 and not (en_text and he_text):
             start_time = max(en_start, he_start) # If only one exists at start, use its time

        end_time = max(en_end, he_end)
        combined_text = ""
        if en_text and he_text: combined_text = f"{en_text}\n{he_text}"
        elif en_text: combined_text = en_text
        elif he_text: combined_text = he_text
        if combined_text:
            sub_id = f"combined_sub_{subtitle_id_counter}"; combined_subs_format.append(((start_time, end_time), combined_text.strip(), sub_id)); subtitle_id_counter += 1

    if not combined_subs_format:
        print("אזהרה: לא נוצרו כתוביות משולבות."); return mp.ColorClip(size=(1,1), color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0), []

    # --- 3. הגדרת ה-Generator עבור SubtitlesClip (עם גלישת שורות) ---
    def generator(txt):
        try:
            font_en = ImageFont.truetype(font_path_local, font_size_en)
            font_he = ImageFont.truetype(font_path_local, font_size_he)
        except Exception as e: print(f"שגיאה קריטית בטעינת פונט PIL '{font_path_local}': {e}"); return mp.ColorClip(size=(1,1), color=(0,0,0,0), ismask=True, duration=0.1).set_opacity(0)

        max_text_width = video_res[0] * 0.75

        # <<<--- התחלה: תיקון לטיפול בטקסט ריק ---<<<
        if not txt or not txt.strip(): # בדוק אם הטקסט ריק או מכיל רק רווחים
            # צור פריים שקוף ריק בגודל מלא ובפורמט RGBA
            # חשוב: MoviePy מצפה לסדר (גובה, רוחב, ערוצים) עבור NumPy
            empty_frame_array = np.zeros((video_res[1], video_res[0], 4), dtype=np.uint8) # H, W, 4 (RGBA)
            # החזר ImageClip עקבי עם פריימים אחרים
            return mp.ImageClip(empty_frame_array, ismask=False, transparent=True).set_duration(0.1)
        # <<<--- סוף: תיקון לטיפול בטקסט ריק ---<<<

        # המשך הקוד הקיים ליצירת תמונה עם טקסט
        img = Image.new('RGBA', video_res, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        original_lines = txt.splitlines()
        # if not original_lines: ... # כבר טופל למעלה, אבל אפשר להשאיר כבטחון אם רוצים

        # --- פונקציית עזר לגלישת שורות לפי מילים ---
        def wrap_text(line_text, font, max_width):
            words = line_text.split(' ')
            wrapped_lines = []
            current_line = ''
            for word in words:
                if not word: continue # Skip empty strings resulting from multiple spaces

                # בדוק רוחב של השורה הנוכחית + המילה הבאה
                test_line = f"{current_line} {word}".strip()
                try:
                    # Use textlength which might be slightly faster than bbox for width check
                    line_width = draw.textlength(test_line, font=font)
                except AttributeError: # Fallback for older PIL/Pillow or specific fonts
                     bbox = draw.textbbox((0, 0), test_line, font=font)
                     line_width = bbox[2] - bbox[0]


                if line_width <= max_width:
                    current_line = test_line
                else:
                    # אם הוספת המילה חורגת:
                    # 1. אם השורה הנוכחית לא ריקה, הוסף אותה לרשימה
                    if current_line:
                        wrapped_lines.append(current_line)
                    # 2. התחל שורה חדשה עם המילה הנוכחית
                    current_line = word
                    # 3. בדוק אם המילה הבודדת עצמה ארוכה מדי
                    try:
                         word_width = draw.textlength(current_line, font=font)
                    except AttributeError:
                         bbox_word = draw.textbbox((0, 0), current_line, font=font)
                         word_width = bbox_word[2] - bbox_word[0]

                    if word_width > max_width:
                         print(f"אזהרה: מילה בודדת '{word}' ארוכה מרוחב השורה המותר ({max_width:.0f}px). היא תוצג בשורה נפרדת אך עשויה לחרוג.")
                         # במקרה כזה, פשוט מוסיפים את המילה הארוכה כשורה בפני עצמה.
                         # אפשר לשקול חיתוך תווים כאן אם רוצים, אך זה מסבך.
                         if current_line: # Add the long word line
                             wrapped_lines.append(current_line)
                         current_line = "" # Reset for next word

            # הוסף את השורה האחרונה שנבנתה (אם ישנה)
            if current_line:
                wrapped_lines.append(current_line)

            # אם הקלט המקורי לא היה ריק אבל לא נוצרו שורות (נדיר)
            if not wrapped_lines and line_text.strip():
                 return [line_text.strip()]
            # אם הקלט היה ריק או רק רווחים
            elif not wrapped_lines:
                return []

            return wrapped_lines


        # --- חישוב גובה כולל ופרטי שורות (כולל זיהוי שפה וגלישה) ---
        total_text_height = 0
        processed_line_details = [] # רשימה לשמור את כל השורות הסופיות לאחר גלישה
        original_line_indices_map = {} # מעקב איזה שורות מקוריות יצרו כל שורה סופית
        original_line_is_hebrew = [] # שמירת השפה של כל שורה מקורית

        # שלב 1: גלישה ויצירת רשימת שורות שטוחה, תוך שמירת מידע מקור
        flat_line_counter = 0
        for i, line in enumerate(original_lines):
            is_heb = is_hebrew(line)
            original_line_is_hebrew.append(is_heb)
            font_for_line = font_he if is_heb else font_en
            # בצע גלישה על השורה הנוכחית
            wrapped_lines_for_current = wrap_text(line, font_for_line, max_text_width)

            for wrapped_line in wrapped_lines_for_current:
                processed_line_details.append({
                    'text': wrapped_line,
                    'font': font_for_line,
                    'is_hebrew': is_heb,
                    'original_index': i, # אינדקס השורה המקורית ממנה נוצרה זו
                    'flat_index': flat_line_counter # אינדקס רץ של כל השורות הסופיות
                })
                original_line_indices_map[flat_line_counter] = i
                flat_line_counter += 1

        # שלב 2: חישוב גיאומטריה ורווחים עבור כל שורה ברשימה השטוחה
        num_processed_lines = len(processed_line_details)
        for k, detail in enumerate(processed_line_details):
            try:
                # bbox נותן גובה מדויק יותר מ-size עבור פונטים מסוימים
                bbox = draw.textbbox((0, 0), detail['text'], font=detail['font'])
                detail['width'] = bbox[2] - bbox[0]
                detail['height'] = bbox[3] - bbox[1]
            except Exception as e:
                print(f"אזהרה בחישוב גבולות עבור: '{detail['text']}'. שגיאה: {e}. משתמש בגודל פונט.")
                detail['width'] = draw.textlength(detail['text'], font=detail['font']) if hasattr(draw, 'textlength') else 100
                detail['height'] = detail['font'].size # Fallback height

            # חישוב הרווח *אחרי* שורה זו
            current_spacing = 0
            is_last_line_overall = (k == num_processed_lines - 1)

            if not is_last_line_overall:
                next_detail = processed_line_details[k+1]
                # בדוק אם השורה הבאה שייכת לאותה שורה מקורית (כלומר, זו גלישה פנימית)
                if detail['original_index'] == next_detail['original_index']:
                    current_spacing = spacing_intra # רווח קטן בין שורות שנגלשו מאותה שורה מקורית
                else:
                    # אם השורה הבאה היא משורה מקורית אחרת = סוף קטע זמן נוכחי / התחלה של קטע הבא
                    current_spacing = spacing_inter # רווח גדול בין קטעי זמן שונים (בין שורות מקוריות שונות)
            # אם זו השורה האחרונה בסך הכל, אין רווח אחריה

            detail['spacing_after'] = current_spacing
            total_text_height += detail['height'] + current_spacing
            # אין צורך להסיר רווח אחרון כאן, כי החישוב מסתמך על הרווח *שאחרי* כל שורה,
            # והשורה האחרונה ממילא לא מוסיפה רווח אחריה לחישוב.

        # חישוב מיקום התחלתי אנכי (מרכוז)
        current_y = (video_res[1] - total_text_height) / 2

        # שלב 3: ציור הטקסט שורה אחר שורה (מהרשימה השטוחה)
        for detail in processed_line_details:
            x_text = (video_res[0] - detail['width']) / 2 # מרכוז אופקי של כל שורה
            text_to_draw = detail['text']

            # החלת עיצוב BiDi על טקסט עברי
            if detail['is_hebrew']:
                try:
                    reshaped_text = arabic_reshaper.reshape(text_to_draw)
                    text_to_draw = get_display(reshaped_text)
                except Exception as e:
                    print(f"שגיאה בעיבוד BiDi עבור: '{text_to_draw}'. שגיאה: {e}")
                    # המשך עם הטקסט המקורי במקרה של שגיאה

            # ציור הטקסט עם קו מתאר
            draw_text_with_stroke(draw, (x_text, current_y), text_to_draw, detail['font'],
                                  text_color, stroke_color, stroke_width_local)

            # קדם את Y לגובה השורה הבאה + הרווח שאחרי השורה הנוכחית
            current_y += detail['height'] + detail['spacing_after']

    # Inside the generator function, at the very end:

        frame_array = np.array(img)
        return mp.ImageClip(frame_array, ismask=False, transparent=True).set_duration(0.1)


    # --- 4. יצירת ה-SubtitlesClip (ללא שינוי מהקודם שלך, רק לוודא שה-generator מעודכן) ---
    subs_for_moviepy = [(item[0], item[1]) for item in combined_subs_format]
    if not subs_for_moviepy: print("אזהרה: אין כתוביות ל-MoviePy."); return mp.ColorClip(size=(1,1), color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0), []
    try:
        # שימוש ב-generator שכולל גלישת שורות והתיקון transparent=True
        subtitle_moviepy_clip = SubtitlesClip(subs_for_moviepy, generator)
        subtitle_moviepy_clip = subtitle_moviepy_clip.set_duration(total_duration).set_position('center')
    except Exception as e: print(f"שגיאה ביצירת SubtitlesClip: {e}"); return mp.ColorClip(size=(1,1), color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0), []

    return subtitle_moviepy_clip, combined_subs_format
    
# --- עיבוד כתוביות משולב ---
print("מעבד כתוביות משולבות (אנגלית ועברית) באמצעות PIL עם BiDi...")
subtitles_clip, combined_subs_list_for_frames = create_styled_subtitle_clip_pil(
    srt_en_file, srt_he_file, font_path, fontsize_en, fontsize_he, color_subs,
    stroke_color_subs, stroke_width_subs,
    spacing_within_language, spacing_between_languages, # <<< העברת הרווחים החדשים
    video_resolution, audio_duration
)

# בדיקה אם הקליפ נוצר בהצלחה
if not hasattr(subtitles_clip, 'duration') or subtitles_clip.duration == 0:
     print("יצירת הוידאו בוטלה עקב שגיאה קריטית ביצירת קליפ הכתוביות."); exit()

# --- פונקציה לניקוי שם קובץ (ללא שינוי) ---
def sanitize_filename(text, max_len=50):
    text = text.replace('\n', ' ').replace('\r', '')
    text = re.sub(r'[\\/*?:"<>|.]', "", text)
    if len(text) > max_len: text = text[:max_len].rstrip() + "..."
    text = re.sub(r'\s+', ' ', text); text = text.strip(' .'); return text or "subtitle"

# --- הכנת נתונים לשמירת פריימים (ללא שינוי) ---
saved_subtitle_ids = set()

# --- פונקציית עיבוד ושמירת פריימים (ללא שינוי) ---
print("מגדיר פונקציית שמירת פריימים...")
def save_subtitle_frame_processor(get_frame, t):
    frame = get_frame(t)
    for interval, text, sub_id in combined_subs_list_for_frames:
        start_time, end_time = interval
        if start_time <= t < end_time and sub_id not in saved_subtitle_ids:
            try:
                time_str = f"{int(t)}_{int((t - int(t)) * 1000):03d}"
                safe_text = sanitize_filename(text)
                filename = os.path.join(output_frames_dir, f"frame_{time_str}_{safe_text}.png")
                imageio.imwrite(filename, frame); saved_subtitle_ids.add(sub_id); break
            except Exception as e: print(f"שגיאה בשמירת פריים {t:.3f}s: {e}"); saved_subtitle_ids.add(sub_id); break
    return frame

# --- שילוב הקליפים (ללא שינוי) ---
print("משלב את הרקע, הכותרת (אם קיימת), כתוביות משולבות ואודיו...")
clips_to_composite = [background_clip]
if title_clip: # This check remains the same
    clips_to_composite.append(title_clip)
clips_to_composite.append(subtitles_clip)
final_clip = mp.CompositeVideoClip(clips_to_composite, size=video_resolution)

# --- החלת פונקציית שמירת הפריימים (ללא שינוי) ---
print("מחבר את מנגנון שמירת הפריימים לקליפ...")
if combined_subs_list_for_frames:
     final_clip_with_saving = final_clip.fl(save_subtitle_frame_processor, apply_to='color')
else:
    print("אזהרה: אין כתוביות לשמירת פריימים.")
    final_clip_with_saving = final_clip # הקצאה ישירה אם אין עיבוד נדרש

# <<<--- התיקון: הוסף את האודיו כאן ---<<<
print("מוסיף את האודיו לקליפ הסופי...")
final_clip_with_saving = final_clip_with_saving.set_audio(audio_clip)

# --- יצירת קובץ הוידאו הסופי ---
print(f"יוצר את קובץ הוידאו '{output_video_file}'...")
temp_audio_file = os.path.join(output_dir, f'temp-audio-{output_video_base}.m4a')  # עדכון נתיב קובץ temp audio
try:
    final_clip_with_saving.write_videofile(output_video_file, fps=video_fps, codec='libx264', audio_codec='aac',
                                           temp_audiofile=temp_audio_file, remove_temp=True,
                                           threads=os.cpu_count() or 4, preset='medium', logger='bar')
    print(f"\nיצירת הוידאו '{output_video_file}' הושלמה בהצלחה!")
    if combined_subs_list_for_frames:
        print(f"פריימים נשמרו בתיקייה: '{output_frames_dir}'")
except Exception as e:
    print(f"\nשגיאה במהלך יצירת הוידאו:\n{e}")
finally:
    # --- מחיקת קובץ temp audio אם קיים ---
    if os.path.exists(temp_audio_file):
        try:
            os.remove(temp_audio_file)
            print(f"קובץ temp audio נמחק: {temp_audio_file}")
        except Exception as e:
            print(f"אזהרה: לא ניתן למחוק את קובץ temp audio '{temp_audio_file}': {e}")

    # --- שחרור משאבים ---
    print("משחרר משאבים...")
    for clip_var in ['audio_clip', 'final_clip', 'final_clip_with_saving', 'background_clip', 'title_clip', 'subtitles_clip']:
        clip_obj = locals().get(clip_var)
        if clip_obj and hasattr(clip_obj, 'close') and callable(getattr(clip_obj, 'close', None)):
            try:
                clip_obj.close()
            except Exception as e_close:
                print(f"Warning: Error closing {clip_var}: {e_close}")
    print("סיום.")