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

# הגדרת נתיב לתיקיית הלוגים
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)  # יצירת התיקייה אם היא לא קיימת

# יצירת שם קובץ לוג ייחודי על בסיס התאריך והשעה
log_filename = datetime.now().strftime("video_creation_%Y%m%d_%H%M%S.log")
log_filepath = os.path.join(LOGS_DIR, log_filename)

# הגדרת רמת הלוגינג ותבנית הלוגים
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# יצירת FileHandler לכתיבת הלוגים לקובץ ייחודי בתיקיית הלוגים
file_handler = logging.FileHandler(log_filepath, mode='w', encoding='utf-8')
file_handler.setLevel(logging.INFO)

# הגדרת פורמט ל-FileHandler
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# הוספת FileHandler ללוגר הראשי
logging.getLogger().addHandler(file_handler)

# עדכון שימוש ב-LANCZOS
RESAMPLING = Image.LANCZOS

# הגדרות בסיסיות
DATA_DIR = os.path.join(BASE_DIR, '..', 'data', 'shorts')  # שינוי לתיקיית "shorts"
ASSETS_DIR = os.path.join(BASE_DIR, '..', 'assets')
FONTS_DIR = os.path.join(ASSETS_DIR, 'fonts')
LOGOS_DIR = os.path.join(ASSETS_DIR, 'logos')
BACKGROUNDS_DIR = os.path.join(ASSETS_DIR, 'backgrounds')  # תיקיית רקעים
OUTPUT_DIR = os.path.join(BASE_DIR, '..', 'output', 'shorts')  # הוספת "shorts" לנתיב היציאה
THUMBNAILS_DIR = os.path.join(OUTPUT_DIR, 'thumbnails')

# נתיבים לקבצים
json_name = str(sys.argv[1])
JSON_FILE = os.path.join(DATA_DIR, f'{json_name}.json')
STYLES_JSON_FILE = os.path.join(ASSETS_DIR, 'styles_shorts.json')  # שינוי לקובץ העיצובים החדש
LOGO_PATH = os.path.join(LOGOS_DIR, 'logo_colored.png')

# הגדרות רווח בין שורות
LINE_SPACING_NORMAL = 60  # רווח רגיל בין השורות
LINE_SPACING_WITHIN_SENTENCE = 40  # רווח קטן בין שורות בתוך אותו משפט
LINE_SPACING_BETWEEN_SENTENCE_AND_TRANSLATION = 60  # רווח גדול בין משפט לתרגומו
# הסרתי את LINE_SPACING_INTRO_SUBTITLE כדי להשתמש ברווח רגיל לכל השורות

# נתיב למוזיקת רקע (אם יש)
BACKGROUND_MUSIC_PATH = os.path.join(ASSETS_DIR, 'background_music.mp3')  # ודא שהקובץ קיים

# הגדרות MoviePy
VIDEO_SIZE = (1080, 1920)  # שינוי לפורמט אנכי
WIDTH, HEIGHT = VIDEO_SIZE
FPS = 24
THREADS = 8

# פונקציה לסניטיזציה של שמות קבצים
def sanitize_filename(filename):
    """
    מסיר תווים בלתי חוקיים משם קובץ ומחליף אותם ב-underscore.
    """
    # הגדרת תווים בלתי חוקיים ב-Windows
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
        # הגדרת סגנונות שדורשים עיבוד רקע
        self.styles_require_bright_blur = {'word', 'sentence', 'sentence_bold', 'translation'}
        # הגדרת צבע ורמת שקיפות לשכבת ההדגשה
        self.overlay_color = (173, 216, 230, 150)  # תכלת בהיר עם שקיפות של 50%

    @lru_cache(maxsize=None)
    def get_font(self, font_path, font_size):
        try:
            font_full_path = os.path.join(FONTS_DIR, font_path)
            return ImageFont.truetype(font_full_path, font_size)
        except IOError:
            logging.error(f"לא ניתן למצוא את הגופן בנתיב: {font_path}")
            raise

    def create_gradient_background(self, width, height, start_color, end_color, direction='vertical'):
        base = Image.new('RGB', (width, height), start_color)
        top = Image.new('RGB', (width, height), end_color)
        mask = Image.new('L', (width, height))

        if direction == 'vertical':
            for y in range(height):
                mask.putpixel((0, y), int(255 * (y / height)))
        elif direction == 'horizontal':
            for x in range(width):
                mask.putpixel((x, 0), int(255 * (x / width)))
        # ניתן להוסיף כיוונים נוספים אם רוצים

        base.paste(top, (0, 0), mask)
        return base

    def split_text_into_lines(self, text, font, max_width, draw):
        """
        מפצל טקסט לשורות כך שכל שורה לא תעבור את הרוחב המקסימלי.
        """
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
        """
        מפרק טקסט לחלקים מודגשים ולא מודגשים.
        """
        parts = re.split(r'(\*\*[^*]+\*\*)', text)
        segments = []
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                segments.append((part[2:-2], True))  # חלק מודגש
            else:
                segments.append((part, False))       # חלק רגיל
        return segments

    def create_image(self, text_lines, style_definitions, line_styles=None, background_image_path=None):
        # שימוש בקאשינג למניעת יצירת תמונות חוזרות
        cache_key = tuple(text_lines) + tuple(line_styles or []) + (background_image_path,)
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
            if line_styles and 'intro_subtitle' in line_styles:
                # אם אין תמונה מתאימה, להשתמש בצבע רקע ברירת מחדל
                img = Image.new('RGB', (WIDTH, HEIGHT), color=(255, 255, 255))
            elif line_styles:
                # אם line_styles מוגדר, נשתמש בסגנון לכל שורה
                try:
                    first_style = style_definitions[line_styles[0]]
                except KeyError:
                    logging.error(f"סגנון '{line_styles[0]}' לא נמצא בקובץ העיצובים.")
                    raise

                if first_style.get('background_image'):
                    # כעת, לא נשתמש ב-background_image מהסגנון, אלא נקבע זאת על בסיס ה-title
                    img = Image.new('RGB', (WIDTH, HEIGHT), color=tuple(first_style['bg_color']))
                elif first_style.get('gradient'):
                    img = self.create_gradient_background(
                        WIDTH, HEIGHT, 
                        first_style['gradient'][0], 
                        first_style['gradient'][1], 
                        first_style['gradient_direction']
                    )
                else:
                    img = Image.new('RGB', (WIDTH, HEIGHT), color=tuple(first_style['bg_color']))
            else:
                # אחרת, נשתמש בסגנון הכללי
                try:
                    first_style = style_definitions['normal']
                except KeyError:
                    logging.error("סגנון 'normal' לא נמצא בקובץ העיצובים.")
                    raise

                img = Image.new('RGB', (WIDTH, HEIGHT), color=tuple(first_style['bg_color']))

        # אם הסגנון דורש עיבוד רקע (בהירות וטשטוש) והוספת שכבת הדגשה
        if line_styles:
            for style_name in line_styles:
                if style_name in self.styles_require_bright_blur:
                    # הגברת הבהירות
                    enhancer = ImageEnhance.Brightness(img)
                    img = enhancer.enhance(1.0)  # ערך 1.0 לפי בקשתך

                    # טשטוש קל
                    img = img.filter(ImageFilter.GaussianBlur(radius=5))  # רדיוס 5 לפי בקשתך

                    # הוספת שכבת הדגשה
                    overlay = Image.new('RGBA', img.size, self.overlay_color)
                    img = img.convert('RGBA')
                    img = Image.alpha_composite(img, overlay)

                    # המרת חזרה ל-RGB
                    img = img.convert('RGB')

                    logging.info(f"עיבוד רקע והוספת שכבת הדגשה עבור הסגנון: {style_name}")
                    break  # מספיק לעבד פעם אחת אם יש לפחות סגנון אחד שדורש עיבוד

        draw = ImageDraw.Draw(img)

        # הגדרת רוחב מקסימלי לטקסט (לדוגמה: רוחב התמונה פחות שוליים)
        MAX_TEXT_WIDTH = WIDTH - 100

        # חישוב גובה כולל
        total_height = 0
        processed_lines = []
        for i, line in enumerate(text_lines):
            if line_styles and i < len(line_styles):
                style_name = line_styles[i]
                try:
                    current_style = style_definitions[style_name]
                except KeyError:
                    logging.error(f"סגנון '{style_name}' לא נמצא בקובץ העיצובים.")
                    raise
            else:
                try:
                    current_style = style_definitions['normal']
                except KeyError:
                    logging.error("סגנון 'normal' לא נמצא בקובץ העיצובים.")
                    raise

            font = self.get_font(current_style['font_path'], current_style['font_size'])

            if is_hebrew(line):
                # פיצול שורות במידת הצורך לפני עיבוד
                split_lines = self.split_text_into_lines(line, font, MAX_TEXT_WIDTH, draw)
                for split_line in split_lines:
                    processed_line = process_hebrew_text(split_line)
                    segments = self.parse_bold(processed_line)
                    processed_style = current_style.copy()
                    processed_style['style_name'] = style_name if line_styles and i < len(line_styles) else 'normal'
                    
                    line_info = []
                    line_height = 0
                    for segment_text, is_bold in segments:
                        if is_bold:
                            try:
                                if processed_style['style_name'] == 'sentence':
                                    segment_style = style_definitions['sentence_bold']
                                elif processed_style['style_name'] == 'call_to_action':
                                    segment_style = style_definitions['call_to_action']
                                elif processed_style['style_name'] == 'intro_subtitle':
                                    segment_style = style_definitions['intro_subtitle']
                                else:
                                    segment_style = style_definitions['word']
                            except KeyError:
                                logging.error(f"סגנון 'sentence_bold', 'word', 'call_to_action' או 'intro_subtitle' לא נמצא בקובץ העיצובים.")
                                raise
                            segment_font = self.get_font(segment_style['font_path'], segment_style['font_size'])
                            segment_color = tuple(segment_style['text_color'])
                        else:
                            segment_style = current_style
                            segment_font = font
                            segment_color = tuple(segment_style['text_color'])
                        
                        bbox = draw.textbbox((0, 0), segment_text, font=segment_font)
                        width = bbox[2] - bbox[0]
                        height = bbox[3] - bbox[1]
                        line_info.append((segment_text, width, height, segment_font, segment_color, segment_style))
                        if height > line_height:
                            line_height = height
                    processed_lines.append((line_info, line_height, processed_style))
                    # הגדרת רווח בהתאם לסגנון
                    if processed_style['style_name'] in ['sentence', 'translation', 'intro_subtitle']:
                        spacing = LINE_SPACING_NORMAL  # רווח רגיל לכל הסגנונות
                    else:
                        spacing = LINE_SPACING_NORMAL
                    total_height += line_height + spacing  # רווח בין השורות
            else:
                # פיצול שורות במידת הצורך לפני עיבוד
                split_lines = self.split_text_into_lines(line, font, MAX_TEXT_WIDTH, draw)
                for split_line in split_lines:
                    processed_line = split_line
                    processed_style = current_style.copy()
                    processed_style['style_name'] = style_name if line_styles and i < len(line_styles) else 'normal'
                    segments = self.parse_bold(processed_line)
                    
                    line_info = []
                    line_height = 0
                    for segment_text, is_bold in segments:
                        if is_bold:
                            try:
                                if processed_style['style_name'] == 'sentence':
                                    segment_style = style_definitions['sentence_bold']
                                else:
                                    segment_style = style_definitions['word']
                            except KeyError:
                                logging.error(f"סגנון 'sentence_bold' או 'word' לא נמצא בקובץ העיצובים.")
                                raise
                            segment_font = self.get_font(segment_style['font_path'], segment_style['font_size'])
                            segment_color = tuple(segment_style['text_color'])
                        else:
                            segment_style = current_style
                            segment_font = font
                            segment_color = tuple(segment_style['text_color'])
                        
                        bbox = draw.textbbox((0, 0), segment_text, font=segment_font)
                        width = bbox[2] - bbox[0]
                        height = bbox[3] - bbox[1]
                        line_info.append((segment_text, width, height, segment_font, segment_color, segment_style))
                        if height > line_height:
                            line_height = height
                    processed_lines.append((line_info, line_height, processed_style))
                    # הגדרת רווח בהתאם לסגנון
                    if processed_style['style_name'] in ['sentence', 'translation']:
                        spacing = LINE_SPACING_NORMAL  # רווח רגיל לכל הסגנונות
                    else:
                        spacing = LINE_SPACING_NORMAL
                    total_height += line_height + spacing  # רווח בין השורות

        # הסרת הרווח הנוסף בסוף
        if processed_lines:
            total_height -= spacing

        # מיקום ההתחלה במרכז אנכי
        current_y = (HEIGHT - total_height) / 2

        # ציור הטקסט
        for line_info, line_height, processed_style in processed_lines:
            # חישוב רוחב השורה הכולל
            line_width = sum([segment[1] for segment in line_info])
            x_text = (WIDTH - line_width) / 2
            for segment_text, width, height, segment_font, segment_color, segment_style in line_info:
                # בדיקת סגנון לטקסט עם זוהר (לדוגמה: 'topic', 'video_number', 'call_to_action')
                if processed_style['style_name'] in ['topic', 'video_number', 'call_to_action']:
                    # הגדרת זוהר לבן עבה יותר
                    glow_color = (255, 255, 255)
                    # הגדרת היסטות רבות יותר כדי ליצור זוהר עבה
                    offsets = [
                        (-3, -3), (-3, 0), (-3, 3),
                        (0, -3), (0, 3),
                        (3, -3), (3, 0), (3, 3),
                        (-2, -2), (-2, 2), (2, -2), (2, 2),
                        (-4, 0), (4, 0), (0, -4), (0, 4)
                    ]
                    # ציור הזוהר מסביב לטקסט
                    for offset in offsets:
                        draw.text(
                            (x_text + offset[0], current_y + (line_height - height) / 2 + offset[1]), 
                            segment_text, font=segment_font, fill=glow_color
                        )
                # ציור הטקסט הרגיל במרכז הזוהר
                if 'outline_color' in segment_style and 'outline_width' in segment_style:
                    outline_color = tuple(segment_style['outline_color'])
                    outline_width = segment_style['outline_width']
                    # ציור מסגרת בטקסט על ידי ציור הטקסט עם הזזות
                    for dx in range(-outline_width, outline_width + 1):
                        for dy in range(-outline_width, outline_width + 1):
                            if dx != 0 or dy != 0:
                                draw.text((x_text + dx, current_y + dy + (line_height - height) / 2), segment_text, font=segment_font, fill=outline_color)
                draw.text((x_text, current_y + (line_height - height) / 2), segment_text, font=segment_font, fill=segment_color)
                x_text += width  # הזזת מיקום ה-X לחלק הבא

            # קביעת רווח בין השורות
            current_y += line_height + spacing  # רווח בין השורות

        # שמירת התמונה בזיכרון
        img = img.convert("RGB")  # המרת חזרה ל-RGB אם הוספנו אלפא
        self.cache[cache_key] = img
        return img


def remove_asterisks(text):
    """
    מסירה את הכוכביות מטקסט המשמש להדגשה, כך שהמערכת לא תקריא אותן.
    """
    return text.replace("**", "")

class AudioCreator:
    def __init__(self, temp_dir):
        self.temp_dir = temp_dir
        self.executor = ThreadPoolExecutor(max_workers=THREADS)

    def create_audio_task(self, text, lang, slow=False):
        try:
            # הסרת הכוכביות מהטקסט לפני ההקראה
            clean_text = remove_asterisks(text)
            tts = gTTS(text=clean_text, lang=lang, slow=slow)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3', dir=self.temp_dir.name) as tmp_file:
                tts.save(tmp_file.name)
                return tmp_file.name
        except ValueError as e:
            logging.error(f"שגיאה ביצירת אודיו עבור הטקסט: '{text}' בשפה: '{lang}'. פרטים: {e}")
            raise

    def create_audios(self, tasks):
        """
        tasks: list of tuples, each tuple can be (text, lang) or (text, lang, slow)
        """
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

    def create_image_clip(self, text_lines, style, line_styles=None, background_image_path=None):
        img = self.image_creator.create_image(text_lines, self.style_definitions, line_styles, background_image_path)
        # יצירת שם קובץ בטוח
        filename = f"{'_'.join([sanitize_filename(line) for line in text_lines])}.png"
        temp_image_path = self.file_manager.get_temp_path(filename)
        img.save(temp_image_path)
        # יצירת קליפ ללא הגדרת משך, יוגדר לפי האודיו או min_duration
        image_clip = ImageClip(temp_image_path)
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

    def create_clip(self, image_clip, audio_paths, min_duration=0):
        audio_total = self.create_audio_clips(audio_paths)
        if audio_total:
            duration = max(audio_total.duration, min_duration)
            image_clip = image_clip.set_duration(duration)
            image_clip = image_clip.set_audio(audio_total)
        else:
            image_clip = image_clip.set_duration(min_duration)
        return image_clip

    def slide_transition(self, clip1, clip2, duration=1):
        # בחר כיוון משמאל לימין או מימין לשמאל בלבד
        direction = random.choice(['left', 'right'])

        # הגדר את תנועת הקליפים בהתאם לכיוון
        if direction == 'left':
            move_out = lambda t: (-VIDEO_SIZE[0] * t / duration, 'center')
            move_in = lambda t: (VIDEO_SIZE[0] - VIDEO_SIZE[0] * t / duration, 'center')
        elif direction == 'right':
            move_out = lambda t: (VIDEO_SIZE[0] * t / duration, 'center')
            move_in = lambda t: (-VIDEO_SIZE[0] + VIDEO_SIZE[0] * t / duration, 'center')

        # קטעים עם אנימציית מיקום
        clip1_moving = clip1.set_position(move_out).set_duration(duration)
        clip2_moving = clip2.set_position(move_in).set_duration(duration)

        # שכבת הקליפים
        transition = CompositeVideoClip([clip1_moving, clip2_moving], size=VIDEO_SIZE).set_duration(duration)

        # הגדרת אודיו ל-None כדי למנוע בעיות באודיו
        transition = transition.set_audio(None)

        return transition

    def add_logo_clip(self, duration=5, background_image_path=None):
        """
        יוצר קליפ לוגו עם מסגרת לבנה עגולה סביב הלוגו במרכז המסך.
        """
        try:
            # יצירת התמונה הבסיסית
            if background_image_path and os.path.exists(background_image_path):
                try:
                    background = Image.open(background_image_path).convert("RGB")
                    background = background.resize((WIDTH, HEIGHT), RESAMPLING)
                    logging.info(f"שימש רקע מהתמונה: {background_image_path} עבור הלוגו")
                except Exception as e:
                    logging.error(f"שגיאה בטעינת תמונת הרקע עבור הלוגו: {e}")
                    background = Image.new('RGB', (WIDTH, HEIGHT), color=(173, 216, 230))
            else:
                # אם אין תמונת רקע, השתמש ברקע צבעי
                logo_style = self.style_definitions.get('logo', None)
                if logo_style and 'bg_color' in logo_style:
                    bg_color = tuple(logo_style['bg_color'])
                else:
                    bg_color = (173, 216, 230)  # צבע ברירת מחדל
                background = Image.new('RGB', (WIDTH, HEIGHT), color=bg_color)

            # טעינת הלוגו
            logo_image = Image.open(LOGO_PATH).convert("RGBA")

            # יצירת מסכה מעגלית
            size = min(logo_image.size)
            mask = Image.new('L', (size, size), 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, size, size), fill=255)

            # חיתוך הלוגו לצורה מעגלית
            logo_image = logo_image.crop((0, 0, size, size))
            logo_image.putalpha(mask)

            # קריאת הגדרות המסגרת מקובץ ה-JSON
            logo_style = self.style_definitions.get('logo', {})
            border_color = tuple(logo_style.get('border_color', [255, 255, 255]))  # ברירת מחדל לבן
            border_width = logo_style.get('border_width', 10)  # ברירת מחדל לעובי 10

            # יצירת תמונה חדשה עם מסגרת עגולה
            bordered_size = (size + 2 * border_width, size + 2 * border_width)
            bordered_logo = Image.new('RGBA', bordered_size, (0, 0, 0, 0))
            bordered_logo_draw = ImageDraw.Draw(bordered_logo)

            # ציור מסגרת עגולה בצבע המסגרת
            bordered_logo_draw.ellipse((0, 0, bordered_size[0], bordered_size[1]), fill=border_color)

            # יצירת מסכה פנימית לשקיפות
            inner_mask = Image.new('L', (size, size), 0)
            inner_draw = ImageDraw.Draw(inner_mask)
            inner_draw.ellipse((0, 0, size, size), fill=255)

            # הדבקת הלוגו המעוגל על המסגרת
            bordered_logo.paste(logo_image, (border_width, border_width), logo_image)

            # שינוי גודל הלוגו עם המסגרת
            new_size = int(WIDTH * 0.7)  # 70% מרוחב המסך
            bordered_logo = bordered_logo.resize((new_size, new_size), RESAMPLING)

            # מיקום הלוגו במרכז
            logo_position = ((WIDTH - new_size) // 2, (HEIGHT - new_size) // 2)

            # הדבקת הלוגו עם המסגרת על הרקע
            background.paste(bordered_logo, logo_position, bordered_logo)

            # שמירת התמונה הזמנית
            temp_image_path = self.file_manager.get_temp_path("logo_outro.png")
            background.convert("RGB").save(temp_image_path)

            # יצירת קליפ הווידאו
            clip = ImageClip(temp_image_path).set_duration(duration)
            return clip
        except Exception as e:
            logging.error(f"שגיאה ביצירת קליפ הלוגו: {e}")
            return None

    def create_intro_clip(self, intro_subtitle, title, video_number, background_image_path):
        try:
            # סדר השורות: intro_subtitle מעל, אחריו title ומספר הסרטון
            text_lines_intro = [intro_subtitle, title, f"#{video_number}"]
            line_styles_intro = ['intro_subtitle', 'topic', 'video_number']

            clip_intro = self.create_image_clip(text_lines_intro, 'intro_subtitle', line_styles_intro, background_image_path)

            # יצירת אודיו רק לשם הנושא ומספר הסרטון, לא למשפט הנוסף
            audio_tasks = [
                (title, 'iw'),
                (f"מספר {video_number}", 'iw')
                # לא מוסיפים את המשפט "למד מילים חדשות בשישים שניות"
            ]
            audio_results = self.audio_creator.create_audios(audio_tasks)
            clip_intro = self.create_clip(
                clip_intro,
                [
                    audio_results.get((title, 'iw'), ""),
                    audio_results.get((f"מספר {video_number}", 'iw'), "")
                    # לא מוסיפים את הנתיב לאודיו של המשפט הנוסף
                ],
                min_duration=3  # משך מינימלי
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

            clip_outro = self.create_image_clip(text_lines_outro, 'outro', line_styles_outro, background_image_path)

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

class VideoAssemblerShorts:
    def __init__(self, file_manager, image_creator, audio_creator, style_definitions):
        self.video_creator = VideoCreator(file_manager, image_creator, audio_creator, style_definitions)

    def determine_background_image_path(self, title):
        """
        קובע את נתיב תמונת הרקע על בסיס ה-title.
        מחפש תמונה בפורמט PNG בתיקיית הרקעים עם שם תואם ל-title.
        """
        background_image_filename = f"{sanitize_filename(title)}.png"  # שימוש ב-PNG
        background_image_path = os.path.join(BACKGROUNDS_DIR, background_image_filename)
        if not os.path.exists(background_image_path):
            logging.warning(f"תמונת הרקע '{background_image_filename}' לא נמצאה בתיקיית הרקעים. ישתמש ברקע לבן.")
            background_image_path = None  # ייעשה שימוש ברקע ברירת מחדל
        return background_image_path

    def assemble_shorts_videos(self, data, output_dir, thumbnails_dir):
        videos = data  # הפורמט העדכני הוא רשימה

        for video_data in videos:
            video_number = video_data['video_number']
            title = video_data['title']
            word = video_data['word']
            translation = video_data['translation']
            examples = video_data['examples']
            call_to_action = video_data.get('call_to_action', '')
            intro_subtitle_text = "למד מילים חדשות בשישים שניות"  # המשפט הנוסף

            logging.info(f"מעבד סרטון מספר {video_number}: {title}")

            # יצירת שם קובץ וידאו בטוח
            safe_title = sanitize_filename("".join([c for c in title if c.isalnum() or c in (' ', '_')]).rstrip().replace(" ", "_"))
            video_filename = f"Short_{video_number}_{safe_title}.mp4"
            video_path = os.path.join(output_dir, video_filename)

            # קביעת נתיב תמונת הרקע על בסיס ה-title
            background_image_path = self.determine_background_image_path(title)

            # רשימה לאחסון הקליפים
            clips = []

            try:
                # יצירת קליפ פתיחה עם intro_subtitle, שם הנושא ומספר הסרטון
                intro_clip = self.video_creator.create_intro_clip(intro_subtitle_text, title, video_number, background_image_path)
                if intro_clip:
                    clips.append(intro_clip)

                # הצגת המילה והתרגום
                text_lines_word = [word, translation]
                line_styles_word = ['word', 'translation']
                clip_word = self.video_creator.create_image_clip(text_lines_word, 'word', line_styles_word, background_image_path)

                # יצירת אודיו למילה ולתרגום
                audio_tasks = [
                    (word, 'en', True),  # אנגלית באיטיות
                    (translation, 'iw'),
                ]
                audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)

                # יצירת רשימת נתיבי האודיו
                audio_paths_word = []
                # עבור 'word' - קריאה באנגלית
                english_audio = audio_results.get((word, 'en', True), "")
                if english_audio:
                    audio_paths_word.append(english_audio)  # קריאה אחת באנגלית
                # עבור 'translation' - קריאה בעברית
                hebrew_audio_translation = audio_results.get((translation, 'iw'), "")
                if hebrew_audio_translation:
                    audio_paths_word.append(hebrew_audio_translation)  # קריאה אחת בעברית
                # עבור 'word' - קריאה שוב באנגלית
                if english_audio:
                    audio_paths_word.append(english_audio)  # קריאה שנייה באנגלית

                clip_word = self.video_creator.create_clip(
                    clip_word,
                    audio_paths_word,
                    min_duration=3  # משך מינימלי
                )
                clips.append(clip_word)

                # משפטים לדוגמה
                for example in examples:
                    sentence = example['sentence']
                    ex_translation = example['translation']

                    text_lines_example = [sentence, ex_translation]
                    line_styles_example = ['sentence', 'translation']
                    clip_example = self.video_creator.create_image_clip(text_lines_example, 'sentence', line_styles_example, background_image_path)

                    # יצירת אודיו למשפט ולתרגום
                    audio_tasks = [
                        (sentence, 'en', True),
                        (ex_translation, 'iw'),
                    ]
                    audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)

                    # יצירת רשימת נתיבי האודיו
                    audio_paths_example = []
                    # עבור 'sentence' - קריאה באנגלית
                    english_audio_sentence = audio_results.get((sentence, 'en', True), "")
                    if english_audio_sentence:
                        audio_paths_example.append(english_audio_sentence)  # קריאה אחת באנגלית
                    # עבור 'translation' - קריאה בעברית
                    hebrew_audio_ex_translation = audio_results.get((ex_translation, 'iw'), "")
                    if hebrew_audio_ex_translation:
                        audio_paths_example.append(hebrew_audio_ex_translation)  # קריאה אחת בעברית
                    # עבור 'sentence' - קריאה שוב באנגלית
                    if english_audio_sentence:
                        audio_paths_example.append(english_audio_sentence)  # קריאה שנייה באנגלית

                    clip_example = self.video_creator.create_clip(
                        clip_example,
                        audio_paths_example,
                        min_duration=4  # משך מינימלי
                    )

                    # יצירת מעבר
                    if clips:
                        previous_clip = clips[-1]
                        transition = self.video_creator.slide_transition(previous_clip, clip_example)
                        clips.append(transition)

                    clips.append(clip_example)

                # קריאה לפעולה
                if call_to_action:
                    clip_outro = self.video_creator.create_outro(call_to_action, background_image_path)
                    if clip_outro:
                        transition = self.video_creator.slide_transition(clips[-1], clip_outro)
                        clips.append(transition)
                        clips.append(clip_outro)

                # הוספת קליפ הלוגו בסוף
                logo_clip = self.video_creator.add_logo_clip(duration=5, background_image_path=background_image_path)
                if logo_clip:
                    transition = self.video_creator.slide_transition(clips[-1], logo_clip)
                    clips.append(transition)
                    clips.append(logo_clip)

                # איחוד הקליפים לסרטון אחד
                logging.info(f"איחוד הקליפים לסרטון מספר {video_number}: {title}")
                final_clip = concatenate_videoclips(clips, method="compose")

                # הוספת מוזיקת רקע אם קיימת
                if os.path.exists(BACKGROUND_MUSIC_PATH):
                    background_music = AudioFileClip(BACKGROUND_MUSIC_PATH).volumex(0.1)
                    background_music = audio_loop(background_music, duration=final_clip.duration)
                    final_audio = CompositeAudioClip([final_clip.audio, background_music])
                    final_clip = final_clip.set_audio(final_audio)
                    # סגירת background_music ו-final_audio לאחר השימוש
                    background_music.close()
                    final_audio.close()

                # שמירת הוידאו
                logging.info(f"שומר את הסרטון בנתיב: {video_path}")
                final_clip.write_videofile(video_path, fps=FPS, codec='libx264', audio_codec='aac', threads=THREADS)

                # שמירת תמונת תצוגה מקדימה
                thumbnail_path = os.path.join(thumbnails_dir, f"Short_{video_number}_thumbnail.png")
                final_clip.save_frame(thumbnail_path, t=0)
                logging.info(f"שומר תמונת תצוגה מקדימה בנתיב: {thumbnail_path}")

            except Exception as e:
                logging.error(f"שגיאה בתהליך הרכבת הוידאו לסרטון מספר {video_number}: {e}")
            finally:
                # סגירת כל הקליפים
                for clip in clips:
                    clip.close()
                # סגירת final_clip אם לא כבר סגור
                if 'final_clip' in locals():
                    final_clip.close()

def main():
    # ניהול קבצים
    file_manager = FileManager(OUTPUT_DIR, THUMBNAILS_DIR)

    video_assembler = None  # אתחול מראש

    try:
        # קריאת קובץ JSON
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # קריאת קובץ העיצובים
        with open(STYLES_JSON_FILE, 'r', encoding='utf-8') as f:
            style_definitions = json.load(f)

        # בדיקה שכל הסגנונות הנדרשים קיימים בקובץ העיצובים
        required_styles = {
            "normal",
            "subtopic",
            "level",
            "word",
            "gradient_background",
            "outro",
            "outro_title",
            "outro_subtitle",
            "sentence",
            "sentence_bold",
            "translation",
            "call_to_action",
            "topic",
            "video_number",
            "logo",
            "intro_subtitle"  # סגנון חדש עבור משפט הפתיחה הנוסף
        }

        missing_styles = required_styles - set(style_definitions.keys())
        if missing_styles:
            logging.error(f"סגנונות חסרים בקובץ העיצובים: {', '.join(missing_styles)}. ודא שכל הסגנונות הדרושים מוגדרים.")
            sys.exit(1)  # יציאה מהסקריפט עם קוד שגיאה

        # יצירת אובייקטים
        image_creator = ImageCreator(styles=style_definitions)
        audio_creator = AudioCreator(file_manager.temp_dir)
        video_assembler = VideoAssemblerShorts(file_manager, image_creator, audio_creator, style_definitions)

        # הרכבת סרטוני ה-Shorts
        video_assembler.assemble_shorts_videos(data, OUTPUT_DIR, THUMBNAILS_DIR)

        logging.info("יצירת כל הסרטונים הסתיימה!")

    except FileNotFoundError as e:
        logging.error(f"לא ניתן למצוא קובץ: {e.filename}")
    except json.JSONDecodeError as e:
        logging.error(f"שגיאה בפענוח קובץ JSON: {e}")
    except Exception as e:
        logging.error(f"שגיאה כללית בתהליך יצירת הסרטונים: {e}")

    finally:
        # ניקוי קבצים זמניים וסגירת ThreadPoolExecutor
        if file_manager:
            file_manager.cleanup()
        # סגירת אובייקט האודיו בלבד
        if audio_creator:
            audio_creator.shutdown()

if __name__ == "__main__":
    main()
