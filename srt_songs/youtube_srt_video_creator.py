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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
output_frames_dir = os.path.join(BASE_DIR, "subtitle_frames") # תיקייה לשמירת תמונות

# --- יצירת תיקיות נדרשות ---
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)
os.makedirs(output_frames_dir, exist_ok=True)

# --- הגדרות קלט ---
youtube_link = input("הזן קישור YouTube לשיר: ")
mp3_file = input(f"הכנס נתיב לקובץ שיר (ברירת מחדל: {os.path.join(BASE_DIR, 'so much closer.mp3')}) >>> ") or os.path.join(BASE_DIR, "so much closer.mp3")

# --- הגדרות כלליות ---
video_resolution = (1280, 720)
video_fps = 25

# --- נתיבי קבצים נוספים ---
background_image_path = os.path.join(ASSETS_DIR, "word_background.png")
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
fontsize_title = 80
color_title = 'black'
stroke_color_title = 'white'
stroke_width_title = 2.0
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
    if not os.environ.get("GEMINI_API_KEY"):
        print("שגיאה: לא נמצא מפתח API של Gemini. אנא הגדר את משתנה הסביבה GEMINI_API_KEY.")
        return None, None

    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    model = "gemini-2.5-pro-exp-03-25"  # or a suitable model

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
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents_english,
        config=generate_content_config,
    ):
        print(chunk.text, end="")
        english_srt_content_raw += chunk.text

    # --- ניקוי תוכן SRT אנגלי ---
    english_srt_content = clean_srt_content(english_srt_content_raw)
    print("\n--- English SRT Cleaned ---")
    # print(english_srt_content) # Uncomment for debugging the cleaned content

    # Extract video ID from URL to create a valid filename
    parsed_url = urllib.parse.urlparse(youtube_url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    video_id = query_params.get('v')
    if video_id:
        base_filename = video_id[0]
    else:
        # Fallback if video ID extraction fails
        base_filename = re.sub(r'\W+', '_', os.path.splitext(os.path.basename(mp3_file))[0]) if 'mp3_file' in globals() and mp3_file else "default_song"


    # --- שמירת קובץ SRT אנגלי (התוכן הנקי) ---
    english_srt_filename = os.path.join(BASE_DIR, f"{base_filename}_en.srt") # Ensure saving in BASE_DIR
    try:
        with open(english_srt_filename, "w", encoding="utf-8") as f:
            f.write(english_srt_content)
        print(f"\nEnglish SRT saved to: {english_srt_filename}")
    except Exception as e:
        print(f"\nError saving English SRT file '{english_srt_filename}': {e}")
        return None, None # Stop if saving fails


    # --- הכנת קלט לתרגום (שימוש בתוכן הנקי) ---
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
        print(chunk.text, end="")
        hebrew_srt_content_raw += chunk.text

    # --- ניקוי תוכן SRT עברי ---
    hebrew_srt_content = clean_srt_content(hebrew_srt_content_raw)
    print("\n--- Hebrew SRT Cleaned ---")
    # print(hebrew_srt_content) # Uncomment for debugging the cleaned content

    # --- שמירת קובץ SRT עברי (התוכן הנקי) ---
    hebrew_srt_filename = os.path.join(BASE_DIR, f"{base_filename}_he.srt") # Ensure saving in BASE_DIR
    try:
        with open(hebrew_srt_filename, "w", encoding="utf-8") as f:
            f.write(hebrew_srt_content)
        print(f"\nHebrew SRT saved to: {hebrew_srt_filename}")
    except Exception as e:
        print(f"\nError saving Hebrew SRT file '{hebrew_srt_filename}': {e}")
        # Decide if you want to return the English one even if Hebrew fails
        return english_srt_content, None


    # --- החזרת התוכן הנקי ---
    return english_srt_content, hebrew_srt_content


# --- הפקת כתוביות מיוטיוב ---
print("מתחיל הפקת כתוביות מיוטיוב...")
english_srt_content, hebrew_srt_content = generate_srt_from_youtube(youtube_link)

if not english_srt_content or not hebrew_srt_content:
    print("שגיאה בהפקת כתוביות. יציאה.")
    exit()

# Extract video ID from URL to create a valid filename
parsed_url = urllib.parse.urlparse(youtube_link)
query_params = urllib.parse.parse_qs(parsed_url.query)
video_id = query_params.get('v')
if video_id:
    base_filename = video_id[0]
else:
    base_filename = "default_song"

# Save SRT content to temporary files (optional, can be in-memory as well)
srt_en_file = os.path.join(BASE_DIR, f"{base_filename}_en.srt")
srt_he_file = os.path.join(BASE_DIR, f"{base_filename}_he.srt")

with open(srt_en_file, "w", encoding="utf-8") as f:
    f.write(english_srt_content)
print(f"\nEnglish SRT saved to: {srt_en_file}")

with open(srt_he_file, "w", encoding="utf-8") as f:
    f.write(hebrew_srt_content)
print(f"Hebrew SRT saved to: {srt_he_file}")


# --- הגדרת שם קובץ פלט ושם השיר ---
output_video_base = os.path.splitext(os.path.basename(mp3_file))[0]
output_video_file = f"{output_video_base}_subtitled_v3.mp4" # עדכון שם קובץ פלט
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
    if subs_en_timing: first_subtitle_start_time = min(first_subtitle_start_time, subs_en_timing[0].start.ordinal / 1000.0)
except: pass
try:
    subs_he_timing = pysrt.open(srt_he_file, encoding='utf-8')
    if subs_he_timing: first_subtitle_start_time = min(first_subtitle_start_time, subs_he_timing[0].start.ordinal / 1000.0)
except: pass

if first_subtitle_start_time >= audio_duration:
    print("אזהרה: לא נמצאו כתוביות, כותרת שיר לא תוצג.")
    first_subtitle_start_time = 0
else:
     print(f"הכתובית הראשונה מתחילה ב: {first_subtitle_start_time:.2f} שניות")

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

# --- פונקציית עיבוד כתוביות מעודכנת - עם BiDi ורווחים משופרים ---
def create_styled_subtitle_clip_pil(srt_en_file_local, srt_he_file_local, font_path_local, font_size_en, font_size_he,
                                   text_color, stroke_color, stroke_width_local,
                                   spacing_intra, spacing_inter, # <<< רווחים נפרדים
                                   video_res, total_duration):
    subs_en = []
    subs_he = []
    combined_subs_format = []
    subtitle_id_counter = 0

    # --- 1. קריאת קבצי SRT (זהה לקודם) ---
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

    # --- 2. שילוב הכתוביות (זהה לקודם) ---
    max_len = max(len(subs_en), len(subs_he))
    for i in range(max_len):
        en_start, en_end, en_text = subs_en[i] if i < len(subs_en) else (0, 0, "")
        he_start, he_end, he_text = subs_he[i] if i < len(subs_he) else (0, 0, "")
        start_time = min(en_start, he_start) if en_text and he_text else (en_start if en_text else he_start)
        if i == 0 and not (en_text and he_text): start_time = max(en_start, he_start)
        end_time = max(en_end, he_end)
        combined_text = ""
        if en_text and he_text: combined_text = f"{en_text}\n{he_text}"
        elif en_text: combined_text = en_text
        elif he_text: combined_text = he_text
        if combined_text:
            sub_id = f"combined_sub_{subtitle_id_counter}"; combined_subs_format.append(((start_time, end_time), combined_text, sub_id)); subtitle_id_counter += 1

    if not combined_subs_format:
        print("אזהרה: לא נוצרו כתוביות משולבות."); return mp.ColorClip(size=(1,1), color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0), []

    # --- 3. הגדרת ה-Generator עבור SubtitlesClip (עם שינויים) ---
    def generator(txt):
        try:
            font_en = ImageFont.truetype(font_path_local, font_size_en)
            font_he = ImageFont.truetype(font_path_local, font_size_he)
        except Exception as e: print(f"שגיאה קריטית בטעינת פונט PIL '{font_path_local}': {e}"); return mp.ColorClip(size=(1,1), color=(0,0,0,0), ismask=True, duration=0.1).set_opacity(0)

        img = Image.new('RGBA', video_res, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        lines = txt.splitlines()
        if not lines: return mp.ColorClip(size=(1,1), color=(0,0,0,0), ismask=True, duration=0.1).set_opacity(0)

        # חישוב גובה כולל ופרטי שורות (כולל זיהוי שפה)
        total_text_height = 0
        line_details = []
        for i, line in enumerate(lines):
            is_line_hebrew = is_hebrew(line)
            font_for_line = font_he if is_line_hebrew else font_en
            try:
                bbox = draw.textbbox((0, 0), line, font=font_for_line)
                line_width = bbox[2] - bbox[0]
                line_height = bbox[3] - bbox[1]
            except Exception as e: print(f"אזהרה בחישוב גבולות: '{line}'. {e}"); line_width = 100; line_height = font_for_line.size
            line_details.append({'text': line, 'font': font_for_line, 'width': line_width, 'height': line_height, 'is_hebrew': is_line_hebrew})

            # חישוב רווח *אחרי* שורה זו
            current_spacing = 0
            if i < len(lines) - 1: # אם זו לא השורה האחרונה
                next_line_is_hebrew = is_hebrew(lines[i+1])
                # אם השפה משתנה (אנגלית -> עברית), השתמש ברווח הגדול
                if not is_line_hebrew and next_line_is_hebrew:
                    current_spacing = spacing_inter
                else: # אחרת, השתמש ברווח הקטן
                    current_spacing = spacing_intra
            line_details[-1]['spacing_after'] = current_spacing # שמירת הרווח
            total_text_height += line_height + current_spacing

        current_y = (video_res[1] - total_text_height) / 2

        # ציור הטקסט שורה אחר שורה (עם BiDi)
        for detail in line_details:
            x_text = (video_res[0] - detail['width']) / 2
            text_to_draw = detail['text']

            # <<< החלת BiDi על טקסט עברי >>>
            if detail['is_hebrew']:
                reshaped_text = arabic_reshaper.reshape(text_to_draw)
                text_to_draw = get_display(reshaped_text)

            draw_text_with_stroke(draw, (x_text, current_y), text_to_draw, detail['font'],
                                  text_color, stroke_color, stroke_width_local)
            current_y += detail['height'] + detail['spacing_after'] # קדם Y לפי הגובה + הרווח שחושב

        frame_array = np.array(img)
        return mp.ImageClip(frame_array, ismask=False).set_duration(0.1)

    # --- 4. יצירת ה-SubtitlesClip (זהה לקודם) ---
    subs_for_moviepy = [(item[0], item[1]) for item in combined_subs_format]
    if not subs_for_moviepy: print("אזהרה: אין כתוביות ל-MoviePy."); return mp.ColorClip(size=(1,1), color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0), []
    try:
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
print("משלב את הרקע, הכותרת, כתוביות משולבות ואודיו...")
clips_to_composite = [background_clip]
if title_clip: clips_to_composite.append(title_clip)
clips_to_composite.append(subtitles_clip)
final_clip = mp.CompositeVideoClip(clips_to_composite, size=video_resolution)
final_clip = final_clip.set_audio(audio_clip).set_duration(audio_duration).set_fps(video_fps)

# --- החלת פונקציית שמירת הפריימים (ללא שינוי) ---
print("מחבר את מנגנון שמירת הפריימים לקליפ...")
if combined_subs_list_for_frames:
     final_clip_with_saving = final_clip.fl(save_subtitle_frame_processor, apply_to='color')
else: print("אזהרה: אין כתוביות לשמירת פריימים."); final_clip_with_saving = final_clip

# --- יצירת קובץ הוידאו הסופי (ללא שינוי) ---
print(f"יוצר את קובץ הוידאו '{output_video_file}'...")
try:
    final_clip_with_saving.write_videofile(output_video_file, fps=video_fps, codec='libx264', audio_codec='aac',
                                           temp_audiofile=f'temp-audio-{output_video_base}.m4a', remove_temp=True,
                                           threads=os.cpu_count() or 4, preset='medium', logger='bar')
    print(f"\nיצירת הוידאו '{output_video_file}' הושלמה בהצלחה!")
    if combined_subs_list_for_frames: print(f"פריימים נשמרו בתיקייה: '{output_frames_dir}'")
except Exception as e: print(f"\nשגיאה במהלך יצירת הוידאו:\n{e}")
finally:
    # --- שחרור משאבים (ללא שינוי) ---
    print("משחרר משאבים...")
    for clip_var in ['audio_clip', 'final_clip', 'final_clip_with_saving', 'background_clip', 'title_clip', 'subtitles_clip']:
        clip_obj = locals().get(clip_var)
        if clip_obj and hasattr(clip_obj, 'close') and callable(getattr(clip_obj, 'close', None)):
            try: clip_obj.close()
            except Exception as e_close: print(f"Warning: Error closing {clip_var}: {e_close}")
    print("סיום.")