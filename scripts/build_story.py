# build_story.py

import json
import sys
import os
import random
import re
import numpy as np
from gtts import gTTS
from moviepy.editor import *
from moviepy.audio.fx.audio_loop import audio_loop
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import arabic_reshaper
from bidi.algorithm import get_display
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile
import logging
from functools import lru_cache
from datetime import datetime
from collections import Counter
import colorsys
import unicodedata

# הגדרת נתיב לתיקיית הלוגים
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)  # יצירת התיקייה אם היא לא קיימת

# יצירת שם קובץ לוג ייחודי על בסיס התאריך והשעה
log_filename = datetime.now().strftime("video_creation_%Y%m%d_%H%M%S.log")
log_filepath = os.path.join(LOGS_DIR, log_filename)

# הגדרת רמת הלוגינג ותבנית הלוגים
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# יצירת FileHandler לכתיבת הלוגים לקובץ ייחודי בתיקיית הלוגים
file_handler = logging.FileHandler(log_filepath, mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

# הגדרת פורמט ל-FileHandler
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# הוספת FileHandler ללוגר הראשי
logging.getLogger().addHandler(file_handler)

# עדכון שימוש ב-LANCZOS
RESAMPLING = Image.LANCZOS

# הגדרות בסיסיות
DATA_DIR = os.path.join(BASE_DIR, '..', 'data', 'stories')
ASSETS_DIR = os.path.join(BASE_DIR, '..', 'assets')
FONTS_DIR = os.path.join(ASSETS_DIR, 'fonts')
LOGOS_DIR = os.path.join(ASSETS_DIR, 'logos')
BACKGROUNDS_DIR = os.path.join(ASSETS_DIR, 'backgrounds')
OUTPUT_DIR = os.path.join(BASE_DIR, '..', 'output', 'stories')
THUMBNAILS_DIR = os.path.join(OUTPUT_DIR, 'thumbnails')

# נתיבים לקבצים
json_name = str(sys.argv[1])
JSON_FILE = os.path.join(DATA_DIR, f'{json_name}.json')
STYLES_JSON_FILE = os.path.join(ASSETS_DIR, 'styles_stories.json')
LOGO_PATH = os.path.join(LOGOS_DIR, 'logo_colored.png')

# הגדרות רווח בין שורות
LINE_SPACING_NORMAL = 50
LINE_SPACING_WITHIN_SENTENCE = 30
LINE_SPACING_BETWEEN_SENTENCE_AND_TRANSLATION = 50

# נתיב למוזיקת רקע (אם יש)
BACKGROUND_MUSIC_PATH = os.path.join(ASSETS_DIR, 'background_music.mp3')

# הגדרות MoviePy
VIDEO_SIZE = (1920, 1080)  # פורמט HD רגיל
WIDTH, HEIGHT = VIDEO_SIZE
FPS = 24
THREADS = 8

# צבע חדש להדגשת תשובה נכונה
HIGHLIGHT_COLOR_CORRECT = (144, 238, 144, 180)  # ירוק בהיר עם שקיפות
GLOW_COLOR = (144, 238, 144)  # ירוק בהיר


def remove_niqqud(text):
    """
    מסיר ניקוד מטקסט עברי.
    """
    normalized_text = unicodedata.normalize('NFKD', text)
    without_niqqud = ''.join([c for c in normalized_text if not unicodedata.combining(c)])
    return without_niqqud


# פונקציה לסניטיזציה של שמות קבצים
def sanitize_filename(filename):
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


# פונקציה לבדוק אם הטקסט בעברית
def is_hebrew(text):
    for char in text:
        if '\u0590' <= char <= '\u05FF':
            return True
    return False


# פונקציה לעיבוד טקסט בעברית
def process_hebrew_text(text):
    reshaped_text = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)
    return bidi_text


# פונקציות חדשות לבחירת צבעים מנוגדים ומגוונים
def extract_main_colors(image_path, num_colors=2):
    """
    מחלץ את הצבעים העיקריים מתמונת הרקע.
    :param image_path: נתיב לתמונת הרקע
    :param num_colors: מספר הצבעים הראשיים לחילוץ
    :return: רשימה של צבעים (RGB)
    """
    with Image.open(image_path) as img:
        img = img.resize((100, 100))  # הפחתת גודל התמונה להאצת העיבוד
        img = img.convert('RGB')
        pixels = img.getcolors(100*100)
        if not pixels:
            pixels = img.getdata()
            pixels = list(pixels)
            pixels = Counter(pixels).most_common(num_colors)
        else:
            pixels = sorted(pixels, key=lambda x: x[0], reverse=True)
            pixels = pixels[:num_colors]
        main_colors = [color for count, color in pixels]
        return main_colors


def get_contrasting_color(rgb):
    """
    מחשב צבע מנוגד לצבע נתון על בסיס לומיננסיה.
    :param rgb: tuple של (R, G, B)
    :return: tuple של הצבע המנוגד (R, G, B)
    """
    # חשב את לומיננסיית הצבע
    r, g, b = rgb
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255

    # אם הלומיננסיה גבוהה, בחר צבע כהה, אחרת בחר צבע בהיר
    if luminance > 0.5:
        return (0, 0, 0)  # שחור
    else:
        return (255, 255, 255)  # לבן


def get_diverse_contrasting_color(rgb):
    """
    מחשב צבע מנוגד מגוון לצבע נתון על בסיס לומיננסיה וחילוף גוונים.
    :param rgb: tuple של (R, G, B)
    :return: tuple של הצבע המנוגד והמעודן (R, G, B)
    """
    # חשב את לומיננסיית הצבע
    r, g, b = rgb
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255

    # המרה מ-RGB ל-HSL
    h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)

    # הוספת שינוי לגוון כדי ליצור גיוון בצבעים המנוגדים
    h_new = (h + 0.5) % 1.0  # הוספת 180 מעלות בגוון

    # הגברת הסאטורציה כדי לשמור על צבעוניות
    s_new = min(s * 1.2, 1.0)

    # התאמת הלומיננסיה
    if luminance > 0.5:
        l_new = 0.2  # צבע כהה
    else:
        l_new = 0.8  # צבע בהיר

    # המרה חזרה ל-RGB
    r_new, g_new, b_new = colorsys.hls_to_rgb(h_new, l_new, s_new)
    return (int(r_new * 255), int(g_new * 255), int(b_new * 255))


class FileManager:
    def __init__(self, output_dir, thumbnails_dir):
        self.output_dir = output_dir
        self.thumbnails_dir = thumbnails_dir
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.thumbnails_dir, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory()

    def get_temp_path(self, filename):
        sanitized_filename = sanitize_filename(filename)
        return os.path.join(self.temp_dir.name, sanitized_filename)

    def cleanup(self):
        self.temp_dir.cleanup()


class ImageCreator:
    def __init__(self, styles):
        self.styles = styles
        self.cache = {}
        self.overlay_color = (173, 216, 230, 150)  # תכלת עם שקיפות
        self.brightness_factor = 1.2  # הגברת בהירות
        self.blur_radius = 5  # רדיוס טשטוש

    @lru_cache(maxsize=None)
    def get_font(self, font_path, font_size):
        try:
            font_full_path = os.path.join(FONTS_DIR, font_path)
            return ImageFont.truetype(font_full_path, font_size)
        except IOError:
            logging.error(f"לא ניתן למצוא את הגופן בנתיב: {font_path}")
            raise

    def split_text_into_lines(self, text, font, max_width, draw):
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
            if width <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines

    def parse_bold(self, text):
        parts = re.split(r'(\*\*[^*]+\*\*)', text)
        segments = []
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                segments.append((part[2:-2], True))
            else:
                segments.append((part, False))
        return segments

    def create_image(self, text_lines, style_definitions, line_styles=None, background_image_path=None, process_background=True, highlight_option=None):
        # Convert highlight_option tuple if not None
        if highlight_option is not None:
            highlight_option = tuple(highlight_option)
        
        cache_key = tuple(text_lines) + tuple(line_styles or []) + (background_image_path,) + (process_background,) + (highlight_option,)
        if cache_key in self.cache:
            logging.info("שימוש בתמונה מקאש")
            return self.cache[cache_key]

        # יצירת רקע
        if background_image_path and os.path.exists(background_image_path):
            try:
                img = Image.open(background_image_path).convert("RGB")
                img = img.resize((WIDTH, HEIGHT), RESAMPLING)
                logging.info(f"שימש רקע מהתמונה: {background_image_path}")
            except Exception as e:
                logging.error(f"שגיאה בטעינת תמונת הרקע: {e}")
                img = Image.new('RGB', (WIDTH, HEIGHT), color=(255, 255, 255))
        else:
            img = Image.new('RGB', (WIDTH, HEIGHT), color=(255, 255, 255))

        if process_background:
            # הגברת בהירות
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(self.brightness_factor)

            # טשטוש
            img = img.filter(ImageFilter.GaussianBlur(radius=self.blur_radius))

            # הוספת שכבת צבע מעל
            overlay = Image.new('RGBA', img.size, self.overlay_color)
            img = img.convert('RGBA')
            img = Image.alpha_composite(img, overlay)
            img = img.convert('RGB')
            logging.info("עיבוד רקע: הגברת בהירות, טשטוש ושכבת צבע נוספו")

        draw = ImageDraw.Draw(img)

        MAX_TEXT_WIDTH = WIDTH - 200

        processed_lines = []
        total_height = 0
        for i, line in enumerate(text_lines):
            style_name = line_styles[i] if line_styles and i < len(line_styles) else 'normal'
            current_style = style_definitions.get(style_name, style_definitions['normal'])
            font = self.get_font(current_style['font_path'], current_style['font_size'])

            if is_hebrew(line):
                # כאן מוסיפים את הפונקציה להסרת ניקוד
                line = remove_niqqud(line)

                split_lines = self.split_text_into_lines(line, font, MAX_TEXT_WIDTH, draw)
                for split_line in split_lines:
                    processed_line = process_hebrew_text(split_line)
                    segments = self.parse_bold(processed_line)
                    line_info = []
                    line_height = 0
                    for segment_text, is_bold in segments:
                        segment_style = current_style.copy()
                        if is_bold:
                            segment_style = style_definitions.get('bold', current_style)
                            segment_font = self.get_font(segment_style['font_path'], segment_style['font_size'])
                        else:
                            segment_font = font
                        bbox = draw.textbbox((0, 0), segment_text, font=segment_font)
                        width = bbox[2] - bbox[0]
                        height = bbox[3] - bbox[1]
                        line_info.append((segment_text, width, height, segment_font, tuple(segment_style['text_color'])))
                        if height > line_height:
                            line_height = height
                    processed_lines.append((line_info, line_height))
                    total_height += line_height + LINE_SPACING_NORMAL
            else:
                split_lines = self.split_text_into_lines(line, font, MAX_TEXT_WIDTH, draw)
                for split_line in split_lines:
                    segments = self.parse_bold(split_line)
                    line_info = []
                    line_height = 0
                    for segment_text, is_bold in segments:
                        segment_style = current_style.copy()
                        if is_bold:
                            segment_style = style_definitions.get('bold', current_style)
                            segment_font = self.get_font(segment_style['font_path'], segment_style['font_size'])
                        else:
                            segment_font = font
                        bbox = draw.textbbox((0, 0), segment_text, font=segment_font)
                        width = bbox[2] - bbox[0]
                        height = bbox[3] - bbox[1]
                        line_info.append((segment_text, width, height, segment_font, tuple(segment_style['text_color'])))
                        if height > line_height:
                            line_height = height
                    processed_lines.append((line_info, line_height))
                    total_height += line_height + LINE_SPACING_NORMAL

        if processed_lines:
            total_height -= LINE_SPACING_NORMAL  # הסרת רווח נוסף בסוף
        current_y = (HEIGHT - total_height) / 2

        for line_idx, (line_info, line_height) in enumerate(processed_lines):
            line_width = sum([segment[1] for segment in line_info])
            x_text = (WIDTH - line_width) / 2
            for segment_idx, (segment_text, width, height, segment_font, segment_color) in enumerate(line_info):
                # ציור המסגרת אם קיים
                if 'outline_color' in current_style and 'outline_width' in current_style:
                    outline_color = tuple(current_style['outline_color'])
                    outline_width = current_style['outline_width']
                    # ציור מסגרת בטקסט על ידי ציור הטקסט עם הזזות
                    for dx in range(-outline_width, outline_width + 1):
                        for dy in range(-outline_width, outline_width + 1):
                            if dx != 0 or dy != 0:
                                draw.text((x_text + dx, current_y + dy + (line_height - height) / 2), segment_text, font=segment_font, fill=outline_color)
                # ציור הטקסט הרגיל
                if highlight_option is not None:
                    highlight_line, highlight_option_idx = highlight_option
                    if line_idx == highlight_line and segment_idx == highlight_option_idx:
                        # הוספת זוהר לטקסט
                        glow = Image.new('RGBA', img.size, (0,0,0,0))
                        glow_draw = ImageDraw.Draw(glow)
                        glow_draw.text((x_text, current_y + (line_height - height) / 2), segment_text, font=segment_font, fill=GLOW_COLOR)
                        glow = glow.filter(ImageFilter.GaussianBlur(radius=10))
                        img = Image.alpha_composite(img.convert('RGBA'), glow)
                        draw = ImageDraw.Draw(img)
                        
                        # החלפת רקע הצהוב בירוק בהיר
                        text_bbox = draw.textbbox((x_text, current_y + (line_height - height) / 2), segment_text, font=segment_font)
                        padding = 10
                        draw.rectangle(
                            [
                                (text_bbox[0] - padding, text_bbox[1] - padding),
                                (text_bbox[2] + padding, text_bbox[3] + padding)
                            ],
                            fill=HIGHLIGHT_COLOR_CORRECT
                        )
                draw.text((x_text, current_y + (line_height - height) / 2), segment_text, font=segment_font, fill=segment_color)
                x_text += width
            current_y += line_height + LINE_SPACING_NORMAL

        img = img.convert("RGB")
        self.cache[cache_key] = img
        return img


def remove_asterisks(text):
    return text.replace("**", "")


class AudioCreator:
    def __init__(self, temp_dir):
        self.temp_dir = temp_dir
        self.executor = ThreadPoolExecutor(max_workers=THREADS)

    def create_audio_task(self, text, lang, slow=False):
        try:
            clean_text = remove_asterisks(text)
            tts = gTTS(text=clean_text, lang=lang, slow=slow)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3', dir=self.temp_dir.name) as tmp_file:
                tts.save(tmp_file.name)
                return tmp_file.name
        except ValueError as e:
            logging.error(f"שגיאה ביצירת אודיו עבור הטקסט: '{text}' בשפה: '{lang}'. פרטים: {e}")
            raise

    def create_audios(self, tasks):
        futures = {}
        for task in tasks:
            if len(task) == 3:
                text, lang, slow = task
                future = self.executor.submit(self.create_audio_task, text, lang, slow)
            else:
                text, lang = task
                future = self.executor.submit(self.create_audio_task, text, lang, False)
            futures[future] = task

        results = {}
        for future in as_completed(futures):
            task = futures[future]
            try:
                audio_path = future.result()
                results[tuple(task)] = audio_path
                logging.info(f"אודיו נוצר עבור: '{task[0]}' בשפה: '{task[1]}' עם slow={'True' if len(task) == 3 and task[2] else 'False'}")
            except Exception as e:
                logging.error(f"שגיאה ביצירת אודיו עבור: '{task[0]}' בשפה: '{task[1]}'. פרטים: {e}")
        return results

    def shutdown(self):
        self.executor.shutdown(wait=True)


class VideoCreator:
    def __init__(self, file_manager, image_creator, audio_creator, style_definitions):
        self.file_manager = file_manager
        self.image_creator = image_creator
        self.audio_creator = audio_creator
        self.style_definitions = style_definitions

    def create_image_clip(self, text_lines, style, line_styles=None, background_image_path=None, process_background=True, highlight_option=None):
        img = self.image_creator.create_image(text_lines, self.style_definitions, line_styles, background_image_path, process_background, highlight_option)
        filename = f"{'_'.join([sanitize_filename(line) for line in text_lines])}.png"
        temp_image_path = self.file_manager.get_temp_path(filename)
        img.save(temp_image_path)
        image_clip = ImageClip(temp_image_path).set_duration(5 if highlight_option is None else 1)
        return image_clip

    def create_audio_clips(self, audio_paths):
        audio_clips = []
        for path in audio_paths:
            if os.path.exists(path):
                audio_clip = AudioFileClip(path)
                audio_clips.append(audio_clip)
            else:
                logging.warning(f"אודיו לא נמצא בנתיב: {path}")
        if audio_clips:
            return concatenate_audioclips(audio_clips)
        else:
            return None

    def create_clip(self, image_clip, audio_paths, min_duration=0, repeat_english=False):
        audio_clips = []
        if repeat_english:
            # אם צריך לחזור על האנגלית, נוסיף אותה קודם, אחר כך עברית, ואז אנגלית שוב
            english_path = audio_paths[0]  # נתיב לקובץ האודיו באנגלית
            hebrew_path = audio_paths[1]  # נתיב לקובץ האודיו בעברית

            if os.path.exists(english_path):
                audio_clips.append(AudioFileClip(english_path))
            else:
                logging.warning(f"אודיו באנגלית לא נמצא בנתיב: {english_path}")

            if os.path.exists(hebrew_path):
                audio_clips.append(AudioFileClip(hebrew_path))
            else:
                logging.warning(f"אודיו בעברית לא נמצא בנתיב: {hebrew_path}")

            if os.path.exists(english_path): # מוסיף שוב את המילה באנגלית
                audio_clips.append(AudioFileClip(english_path))
            else:
                logging.warning(f"אודיו באנגלית לא נמצא בנתיב: {english_path}")

        else:
            # אם לא צריך לחזור על האנגלית, נוסיף את הקליפים כרגיל
            for path in audio_paths:
                if os.path.exists(path):
                    audio_clips.append(AudioFileClip(path))
                else:
                    logging.warning(f"אודיו לא נמצא בנתיב: {path}")

        if audio_clips:
            audio_total = concatenate_audioclips(audio_clips)
            duration = max(audio_total.duration, min_duration)
            image_clip = image_clip.set_duration(duration)
            image_clip = image_clip.set_audio(audio_total)
        else:
            image_clip = image_clip.set_duration(min_duration)

        return image_clip

    def slide_transition(self, clip1, clip2, duration=1):
        # בחר כיוון מלמעלה למטה או מתחת למעלה בלבד
        direction = random.choice(['down', 'up'])

        # הגדר את תנועת הקליפים בהתאם לכיוון
        if direction == 'down':
            move_out = lambda t: ('center', -VIDEO_SIZE[1] * t / duration)
            move_in = lambda t: ('center', VIDEO_SIZE[1] - VIDEO_SIZE[1] * t / duration)
        elif direction == 'up':
            move_out = lambda t: ('center', VIDEO_SIZE[1] * t / duration)
            move_in = lambda t: ('center', -VIDEO_SIZE[1] + VIDEO_SIZE[1] * t / duration)

        # קטעים עם אנימציית מיקום
        clip1_moving = clip1.set_position(move_out).set_duration(duration)
        clip2_moving = clip2.set_position(move_in).set_duration(duration)

        # שכבת הקליפים
        transition = CompositeVideoClip([clip1_moving, clip2_moving], size=VIDEO_SIZE).set_duration(duration)

        # הגדרת אודיו ל-None כדי למנוע בעיות באודיו
        transition = transition.set_audio(None)

        return transition

    def add_logo_clip(self, duration=5, background_image_path=None):
        try:
            if background_image_path and os.path.exists(background_image_path):
                try:
                    background = Image.open(background_image_path).convert("RGB")
                    background = background.resize((WIDTH, HEIGHT), RESAMPLING)
                    logging.info(f"שימש רקע מהתמונה: {background_image_path} עבור הלוגו")
                except Exception as e:
                    logging.error(f"שגיאה בטעינת תמונת הרקע עבור הלוגו: {e}")
                    background = Image.new('RGB', (WIDTH, HEIGHT), color=(173, 216, 230))
            else:
                logo_style = self.style_definitions.get('logo', None)
                if logo_style and 'bg_color' in logo_style:
                    bg_color = tuple(logo_style['bg_color'])
                else:
                    bg_color = (173, 216, 230)
                background = Image.new('RGB', (WIDTH, HEIGHT), color=bg_color)

            logo_image = Image.open(LOGO_PATH).convert("RGBA")

            size = min(logo_image.size)
            mask = Image.new('L', (size, size), 0)
            draw = ImageDraw.Draw(mask)

            draw.ellipse((0, 0, size, size), fill=255)

            logo_image = logo_image.crop((0, 0, size, size))
            logo_image.putalpha(mask)

            logo_style = self.style_definitions.get('logo', {})
            border_color = tuple(logo_style.get('border_color', [255, 255, 255]))
            border_width = logo_style.get('border_width', 10)

            bordered_size = (size + 2 * border_width, size + 2 * border_width)
            bordered_logo = Image.new('RGBA', bordered_size, (0, 0, 0, 0))
            bordered_logo_draw = ImageDraw.Draw(bordered_logo)

            bordered_logo_draw.ellipse((0, 0, bordered_size[0], bordered_size[1]), fill=border_color)

            bordered_logo.paste(logo_image, (border_width, border_width), logo_image)

            new_size = int(HEIGHT * 0.3)  # 30% מגובה המסך
            bordered_logo = bordered_logo.resize((new_size, new_size), RESAMPLING)

            logo_position = ((WIDTH - new_size) // 2, (HEIGHT - new_size) // 2)

            background.paste(bordered_logo, logo_position, bordered_logo)

            temp_image_path = self.file_manager.get_temp_path("logo_outro.png")
            background.convert("RGB").save(temp_image_path)

            clip = ImageClip(temp_image_path).set_duration(duration)
            return clip
        except Exception as e:
            logging.error(f"שגיאה ביצירת קליפ הלוגו: {e}")
            return None

    def create_intro_clip(self, title, language_level, story_type, background_image_path):
        try:
            # סדר השורות: כותרת, רמת שפה וסוג הסיפור בשורה אחת
            intro_details = f"{language_level} | {story_type}"
            text_lines_intro = [title, intro_details]
            line_styles_intro = ['intro_title', 'intro_details']

            clip_intro = self.create_image_clip(text_lines_intro, 'intro_title', line_styles_intro, background_image_path, process_background=False)

            # יצירת אודיו לכותרת ורמת שפה וסוג הסיפור
            audio_tasks = [
                (title, 'iw'),
                (intro_details, 'iw')
            ]
            audio_results = self.audio_creator.create_audios(audio_tasks)
            clip_intro = self.create_clip(
                clip_intro,
                [
                    audio_results.get((title, 'iw'), ""),
                    audio_results.get((intro_details, 'iw'), "")
                ],
                min_duration=5  # משך מינימלי
            )
            return clip_intro
        except Exception as e:
            logging.error(f"שגיאה ביצירת קליפ הפתיחה: {e}")
            return None

    def create_outro(self, call_to_action, background_image_path):
        try:
            text_lines_outro = [
                call_to_action
            ]
            line_styles_outro = ['call_to_action']

            clip_outro = self.create_image_clip(text_lines_outro, 'call_to_action', line_styles_outro, background_image_path, process_background=False)

            # יצירת אודיו לקריאה לפעולה
            audio_tasks = [
                (call_to_action, 'iw')
            ]
            audio_results = self.audio_creator.create_audios(audio_tasks)
            clip_outro = self.create_clip(
                clip_outro,
                [
                    audio_results.get((call_to_action, 'iw'), "")
                ],
                min_duration=4  # משך מינימלי
            )
            return clip_outro
        except Exception as e:
            logging.error(f"שגיאה ביצירת קליפ הסיום: {e}")
            return None

    def create_story_segment(self, text, style_name, background_image_path, duration=3):
        """
        יוצר קליפ עבור קטע "הסיפור" או "הסוף".
        :param text: הטקסט להצגה
        :param style_name: שם הסגנון ('story_start' או 'story_end')
        :param background_image_path: נתיב לתמונת הרקע
        :param duration: משך הקליפ בשניות
        :return: ImageClip
        """
        text_lines = [text]
        line_styles = [style_name]
        clip = self.create_image_clip(text_lines, style_name, line_styles, background_image_path, process_background=True)
        audio_tasks = [
            (text, 'iw')  # הנחה שהטקסט בעברית
        ]
        audio_results = self.audio_creator.create_audios(audio_tasks)
        clip = self.create_clip(
            clip,
            [
                audio_results.get((text, 'iw'), "")
            ],
            min_duration=duration
        )
        return clip

    def calculate_pause_duration(self, text, seconds_per_word=0.6):
        """
        מחשבת את משך ההשהייה על פי מספר המילים בטקסט.
        :param text: הטקסט באנגלית
        :param seconds_per_word: מספר שניות להשהייה לכל מילה
        :return: משך ההשהייה בשניות
        """
        word_count = len(text.split())
        duration = word_count * seconds_per_word
        return duration

    def assemble_video_with_pause(self, text, hebrew_text, background_image_path):
        """
        יוצר את הקליפ באנגלית, מרחיב את משך ההשהייה בהתאם לטקסט, ומוסיף את הקליפ בעברית.
        :param text: הטקסט באנגלית
        :param hebrew_text: הטקסט בעברית
        :param background_image_path: נתיב לתמונת הרקע
        :return: רשימת הקליפים
        """
        clips = []

        # קליפ באנגלית
        text_lines_en = [text]
        line_styles_en = ['sentence']
        clip_story_en = self.create_image_clip(text_lines_en, 'sentence', line_styles_en, background_image_path, process_background=True)
        audio_tasks_en = [
            (text, 'en', True)  # אנגלית באיטיות
        ]
        audio_results_en = self.audio_creator.create_audios(audio_tasks_en)
        clip_story_en = self.create_clip(
            clip_story_en,
            [
                audio_results_en.get((text, 'en', True), "")
            ],
            min_duration=5
        )
        clips.append(clip_story_en)

        # חישוב משך ההשהייה
        pause_duration = self.calculate_pause_duration(text)
        # הרחבת משך הקליפ הנוכחי על ידי הגדרת משך זמן נוסף
        extended_duration = clip_story_en.duration + pause_duration
        clip_story_en = clip_story_en.set_duration(extended_duration)
        clips[-1] = clip_story_en  # עדכון הקליפ ברשימה

        # קליפ בעברית
        text_lines_he = [hebrew_text]
        line_styles_he = ['translation']
        clip_story_he = self.create_image_clip(text_lines_he, 'translation', line_styles_he, background_image_path, process_background=True)
        audio_tasks_he = [
            (hebrew_text, 'iw')
        ]
        audio_results_he = self.audio_creator.create_audios(audio_tasks_he)
        clip_story_he = self.create_clip(
            clip_story_he,
            [
                audio_results_he.get((hebrew_text, 'iw'), "")
            ],
            min_duration=5
        )
        clips.append(clip_story_he)

        return clips


class VideoAssembler:
    def __init__(self, file_manager, image_creator, audio_creator, style_definitions):
        self.video_creator = VideoCreator(file_manager, image_creator, audio_creator, style_definitions)
        self.style_definitions = style_definitions  # שמירת ההגדרות לשימוש עתידי

    def determine_background_image_path(self, title):
        background_image_filename = f"{sanitize_filename(title)}.png"
        background_image_path = os.path.join(BACKGROUNDS_DIR, background_image_filename)
        if not os.path.exists(background_image_path):
            logging.warning(f"תמונת הרקע '{background_image_filename}' לא נמצאה בתיקיית הרקעים. ישתמש ברקע לבן.")
            background_image_path = None
        return background_image_path

    def update_style_definitions_with_contrasting_colors(self, background_image_path):
        """
        מעדכן את style_definitions עם הצבעים המנוגדים שנמצאו מתמונת הרקע.
        :param background_image_path: נתיב לתמונת הרקע
        """
        if not background_image_path or not os.path.exists(background_image_path):
            logging.info("לא נמצאה תמונת רקע. לא מעדכנים צבעים מנוגדים.")
            return

        main_colors = extract_main_colors(background_image_path, num_colors=2)
        if not main_colors:
            logging.warning("לא נמצאו צבעים בתמונת הרקע. לא מעדכנים צבעים מנוגדים.")
            return

        # בחירת הצבע העיקרי והצבע המנוגד שלו
        dominant_color = main_colors[0]
        contrasting_color = get_diverse_contrasting_color(dominant_color)
        logging.info(f"צבע עיקרי: {dominant_color}, צבע מנוגד מגוון: {contrasting_color}")

        # עדכון סגנון 'intro_title' עם צבע מנוגד מגוון
        if 'intro_title' in self.style_definitions:
            self.style_definitions['intro_title']['text_color'] = list(contrasting_color)
            # נבחר צבע מסגרת מנוגד גם כן
            outline_color_intro = get_contrasting_color(contrasting_color)
            self.style_definitions['intro_title']['outline_color'] = list(outline_color_intro)
            logging.debug(f"עדכון סגנון 'intro_title' עם צבע טקסט: {contrasting_color} וצבע מסגרת: {outline_color_intro}")

        # בחירת צבע מנוגד נוסף עבור 'call_to_action'
        if len(main_colors) > 1:
            secondary_color = main_colors[1]
            contrasting_color2 = get_diverse_contrasting_color(secondary_color)
            logging.info(f"צבע שני: {secondary_color}, צבע מנוגד מגוון שני: {contrasting_color2}")
        else:
            # אם אין צבע שני, נשתמש בצבע מנוגד העיקרי
            contrasting_color2 = contrasting_color

        if 'call_to_action' in self.style_definitions:
            # הגדרת צבע טקסט וצבע מסגרת להפוכים
            self.style_definitions['call_to_action']['text_color'] = list(get_contrasting_color(contrasting_color2))
            self.style_definitions['call_to_action']['outline_color'] = list(contrasting_color2)
            logging.debug(f"עדכון סגנון 'call_to_action' עם צבע טקסט: {get_contrasting_color(contrasting_color2)} וצבע מסגרת: {contrasting_color2}")

    def assemble_videos(self, data, output_dir, thumbnails_dir):
        if isinstance(data, dict):
            videos = [data]  # עטיפת המילון ברשימה
        elif isinstance(data, list):
            videos = data
        else:
            logging.error("מבנה הנתונים אינו תואם. צפה למילון או רשימה של מילונים.")
            return

        for video_data in videos:
            video_title = video_data['video_title']
            # הסרת ניקוד מכותרת הסרטון
            video_title = remove_niqqud(video_title)

            language_level = video_data['language_level']
            story_type = video_data['story_type']
            story = video_data['story']
            vocabulary = video_data.get('vocabulary', [])
            comprehension_questions = video_data.get('comprehension_questions', [])
            call_to_action = video_data.get('call_to_action', {}).get('text', '')

            logging.info(f"מעבד סרטון: {video_title}")

            safe_title = sanitize_filename(video_title.replace(" ", "_"))
            video_filename = f"{safe_title}.mp4"
            video_path = os.path.join(output_dir, video_filename)

            background_image_path = self.determine_background_image_path(video_title)

            # עדכון צבעים מנוגדים עבור 'intro_title' ו-'call_to_action'
            self.update_style_definitions_with_contrasting_colors(background_image_path)

            clips = []

            try:
                # קליפ פתיחה
                intro_clip = self.video_creator.create_intro_clip(video_title, language_level, story_type, background_image_path)
                if intro_clip:
                    clips.append(intro_clip)

                # מעבר לקטע הסיפור
                if story['text']:
                    story_intro = "כְּדֵי לְהָפִיק אֶת הַמֵּיטָב מֵהַסִּרְטוֹן: הַאֲזִינוּ לְהַקְרָאַת הַמִּשְׁפָּט בְּאַנְגְּלִית, נַסּוּ לִקְרוֹא אוֹתוֹ בְּעַצְמְכֶם וּלְהָבִין אֶת הַמַּשְׁמָעוּת, וּלְאַחַר מִכֵּן צְפוּ בַּתַרְגּוּם לְעִבְרִית כְּדֵי לִבְדּוֹק אֶת עַצְמְכֶם!"
                    text_lines_intro_story = [story_intro]
                    line_styles_intro_story = ['story_intro']
                    clip_story_intro = self.video_creator.create_image_clip(text_lines_intro_story, 'story_intro', line_styles_intro_story, background_image_path, process_background=True)
                    audio_tasks = [(story_intro, 'iw')]
                    audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                    clip_story_intro = self.video_creator.create_clip(
                        clip_story_intro,
                        [audio_results.get((story_intro, 'iw'), "")],
                        min_duration=3
                    )
                    # מעבר לקטע הסיפור
                    transition = self.video_creator.slide_transition(clips[-1], clip_story_intro)
                    clips.append(transition)
                    
                    # הוספת השהייה של 2 שניות על ידי הארכת משך התצוגה
                    clip_story_intro = clip_story_intro.set_duration(clip_story_intro.duration + 2)
                    
                    clips.append(clip_story_intro)

                    # הוספת קטע "הסיפור" בתחילת הסיפור
                    story_start_text = "הסיפור"
                    clip_story_start = self.video_creator.create_story_segment(story_start_text, 'story_start', background_image_path, duration=3)
                    transition = self.video_creator.slide_transition(clips[-1], clip_story_start)
                    clips.append(transition)
                    clips.append(clip_story_start)

                    # הצגת הסיפור
                    for paragraph in story['text']:
                        english_text = paragraph['english']
                        hebrew_text = paragraph['hebrew']

                        # יצירת קליפ עם השהייה לאחר הקטע באנגלית
                        story_clips = self.video_creator.assemble_video_with_pause(english_text, hebrew_text, background_image_path)
                        clips.extend(story_clips)

                    # הוספת קטע "הסוף" בסיום הסיפור
                    story_end_text = "הסוף"
                    clip_story_end = self.video_creator.create_story_segment(story_end_text, 'story_end', background_image_path, duration=3)
                    transition = self.video_creator.slide_transition(clips[-1], clip_story_end)
                    clips.append(transition)
                    clips.append(clip_story_end)

                # מעבר לקטע אוצר מילים
                if vocabulary:
                    vocab_intro = "מילים חדשות שלמדנו"
                    text_lines_vocab_intro = [vocab_intro]
                    line_styles_vocab_intro = ['subtopic']
                    clip_vocab_intro = self.video_creator.create_image_clip(text_lines_vocab_intro, 'subtopic', line_styles_vocab_intro, background_image_path, process_background=True)
                    audio_tasks = [(vocab_intro, 'iw')]
                    audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                    clip_vocab_intro = self.video_creator.create_clip(
                        clip_vocab_intro,
                        [audio_results.get((vocab_intro, 'iw'), "")],
                        min_duration=3
                    )
                    # מעבר לקטע אוצר מילים
                    transition = self.video_creator.slide_transition(clips[-1], clip_vocab_intro)
                    clips.append(transition)
                    clips.append(clip_vocab_intro)

                    for word_entry in vocabulary:
                        word = word_entry['word']
                        translation = word_entry['translation']
                        text_lines = [word, translation]
                        line_styles = ['word', 'translation']
                        clip_word = self.video_creator.create_image_clip(text_lines, 'word', line_styles, background_image_path, process_background=True)
                        audio_tasks = [
                            (word, 'en', True),
                            (translation, 'iw')
                        ]
                        audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                        audio_paths = [
                            audio_results.get((word, 'en', True), ""),
                            audio_results.get((translation, 'iw'), "")
                        ]

                        clip_word = self.video_creator.create_clip(
                            clip_word,
                            audio_paths,
                            min_duration=4,
                            repeat_english=True # מוסיף את המילה באנגלית שוב
                        )

                        # הרחבת משך התצוגה בשנייה
                        clip_word = clip_word.set_duration(clip_word.duration + 1)                        

                        clips.append(clip_word)

                # מעבר לקטע שאלות הבנה
                if comprehension_questions:
                    questions_intro = "בחנו את עצמכם"
                    text_lines_questions_intro = [questions_intro]
                    line_styles_questions_intro = ['subtopic']
                    clip_questions_intro = self.video_creator.create_image_clip(text_lines_questions_intro, 'subtopic', line_styles_questions_intro, background_image_path, process_background=True)
                    audio_tasks = [(questions_intro, 'iw')]
                    audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                    clip_questions_intro = self.video_creator.create_clip(
                        clip_questions_intro,
                        [audio_results.get((questions_intro, 'iw'), "")],
                        min_duration=3
                    )
                    # מעבר לקטע שאלות הבנה
                    transition = self.video_creator.slide_transition(clips[-1], clip_questions_intro)
                    clips.append(transition)
                    clips.append(clip_questions_intro)

                    for question_entry in comprehension_questions:
                        question = question_entry['question']
                        options = question_entry['options']
                        correct_answer = question_entry['answer']  # 0-based index בין 0-2

                        # קליפ השאלה עם כל התשובות
                        text_lines = [question] + options
                        line_styles = ['sentence'] + ['translation'] * len(options)
                        clip_question = self.video_creator.create_image_clip(text_lines, 'sentence', line_styles, background_image_path, process_background=True)
                        audio_tasks = [(question, 'iw')] + [(opt, 'iw') for opt in options]
                        audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                        audio_paths = [audio_results.get((text, 'iw'), "") for text in [question] + options]
                        clip_question = self.video_creator.create_clip(
                            clip_question,
                            audio_paths,
                            min_duration=5
                        )
                        clips.append(clip_question)

                        # הרחבת משך הקליפ ב-3 שניות
                        clip_question = clip_question.set_duration(clip_question.duration + 3)
                        clips[-1] = clip_question  # עדכון הקליפ ברשימה

                        # קליפ עם התשובה הנכונה מודגשת
                        correct_answer_text = options[correct_answer]
                        highlight_option = (1 + correct_answer, 0)  # line_idx = 1 + correct_answer, segment_idx = 0
                        clip_answer = self.video_creator.create_image_clip(text_lines, 'sentence', line_styles, background_image_path, process_background=True, highlight_option=highlight_option)

                        # יצירת אודיו עבור "התשובה הנכונה היא..." והאופציה הנכונה
                        narration_text = "התשובה הנכונה היא"
                        audio_tasks = [
                            (narration_text, 'iw'),
                            (correct_answer_text, 'iw')
                        ]
                        audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                        audio_paths = [
                            audio_results.get((narration_text, 'iw'), ""),
                            audio_results.get((correct_answer_text, 'iw'), "")
                        ]
                        clip_answer = self.video_creator.create_clip(
                            clip_answer,
                            audio_paths,
                            min_duration=3
                        )
                        clips.append(clip_answer)

                # מעבר לקטע קריאה לפעולה
                if call_to_action:
                    clip_outro = self.video_creator.create_outro(call_to_action, background_image_path)
                    if clip_outro:
                        transition = self.video_creator.slide_transition(clips[-1], clip_outro)
                        clips.append(transition)
                        clips.append(clip_outro)

                # מעבר לקטע הלוגו
                logo_intro = "תודה שצפיתם!"
                text_lines_logo_intro = [logo_intro]
                line_styles_logo_intro = ['subtopic']
                clip_logo_intro = self.video_creator.create_image_clip(text_lines_logo_intro, 'subtopic', line_styles_logo_intro, background_image_path, process_background=True)
                audio_tasks = [(logo_intro, 'iw')]
                audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                clip_logo_intro = self.video_creator.create_clip(
                    clip_logo_intro,
                    [audio_results.get((logo_intro, 'iw'), "")],
                    min_duration=3
                )
                # מעבר לקטע הלוגו
                transition = self.video_creator.slide_transition(clips[-1], clip_logo_intro)
                clips.append(transition)
                clips.append(clip_logo_intro)

                # הוספת קליפ הלוגו בסוף
                logo_clip = self.video_creator.add_logo_clip(duration=5, background_image_path=background_image_path)
                if logo_clip:
                    transition = self.video_creator.slide_transition(clips[-1], logo_clip)
                    clips.append(transition)
                    clips.append(logo_clip)

                # איחוד הקליפים לסרטון אחד
                logging.info(f"איחוד הקליפים לסרטון: {video_title}")
                final_clip = concatenate_videoclips(clips, method="compose")

                # הוספת מוזיקת רקע אם קיימת
                if os.path.exists(BACKGROUND_MUSIC_PATH):
                    background_music = AudioFileClip(BACKGROUND_MUSIC_PATH).volumex(0.1)
                    background_music = audio_loop(background_music, duration=final_clip.duration)
                    final_audio = CompositeAudioClip([final_clip.audio, background_music])
                    final_clip = final_clip.set_audio(final_audio)
                    background_music.close()
                    final_audio.close()

                # שמירת הוידאו
                logging.info(f"שומר את הסרטון בנתיב: {video_path}")
                final_clip.write_videofile(video_path, fps=FPS, codec='libx264', audio_codec='aac', threads=THREADS)

                # שמירת תמונת תצוגה מקדימה
                thumbnail_path = os.path.join(thumbnails_dir, f"{safe_title}_thumbnail.png")
                final_clip.save_frame(thumbnail_path, t=0)
                logging.info(f"שומר תמונת תצוגה מקדימה בנתיב: {thumbnail_path}")

            except Exception as e:
                logging.error(f"שגיאה בתהליך הרכבת הוידאו לסרטון: {e}")
            finally:
                for clip in clips:
                    clip.close()
                if 'final_clip' in locals():
                    final_clip.close()


def main():
    file_manager = FileManager(OUTPUT_DIR, THUMBNAILS_DIR)

    video_assembler = None

    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        with open(STYLES_JSON_FILE, 'r', encoding='utf-8') as f:
            style_definitions = json.load(f)

        required_styles = {
            "normal",
            "subtopic",
            "level",
            "word",
            "translation",
            "sentence",
            "bold",
            "call_to_action",
            "intro_title",
            "intro_details",
            "intro_subtitle",
            "video_number",
            "topic",
            "logo",
            "story_start",
            "story_end",
            "story_intro"  # הוספת הסגנון החדש
        }

        missing_styles = required_styles - set(style_definitions.keys())
        if missing_styles:
            logging.error(f"סגנונות חסרים בקובץ העיצובים: {', '.join(missing_styles)}. ודא שכל הסגנונות הדרושים מוגדרים.")
            sys.exit(1)

        image_creator = ImageCreator(styles=style_definitions)
        audio_creator = AudioCreator(file_manager.temp_dir)
        video_assembler = VideoAssembler(file_manager, image_creator, audio_creator, style_definitions)

        video_assembler.assemble_videos(data, OUTPUT_DIR, THUMBNAILS_DIR)

        logging.info("יצירת כל הסרטונים הסתיימה!")

    except FileNotFoundError as e:
        logging.error(f"לא ניתן למצוא קובץ: {e.filename}")
    except json.JSONDecodeError as e:
        logging.error(f"שגיאה בפענוח קובץ JSON: {e}")
    except Exception as e:
        logging.error(f"שגיאה כללית בתהליך יצירת הסרטונים: {e}")

    finally:
        if file_manager:
            file_manager.cleanup()
        if audio_creator:
            audio_creator.shutdown()


if __name__ == "__main__":
    main()
