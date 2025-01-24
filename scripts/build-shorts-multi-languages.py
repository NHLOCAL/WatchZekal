import json
import sys
import os
import random
import re
import numpy as np
# הסרנו את gTTS
# from gtts import gTTS
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

# ייבוא ספריית Google Cloud Text-to-Speech
from google.cloud import texttospeech

# הגדרת נתיב למפתח ה-API (ודאו שהקובץ JSON נמצא במיקום מתאים)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\me\OneDrive\וידאו\מפתחות גישה\youtube-channel-440320-fe17f0f0a940.json"

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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'data', 'shorts')  # תיקיית "shorts" ראשית
ASSETS_DIR = os.path.join(BASE_DIR, '..', 'assets')
FONTS_DIR = os.path.join(ASSETS_DIR, 'fonts')
LOGOS_DIR = os.path.join(ASSETS_DIR, 'logos')
FLAGS_DIR = os.path.join(ASSETS_DIR, 'flags')
BACKGROUNDS_DIR = os.path.join(ASSETS_DIR, 'backgrounds')  # תיקיית רקעים
OUTPUT_DIR = os.path.join(BASE_DIR, '..', 'output', 'shorts')  # תיקיית "shorts" ראשית בנתיב היציאה
THUMBNAILS_DIR = os.path.join(OUTPUT_DIR, 'thumbnails')
LANG_SETTINGS_FILE = os.path.join(DATA_DIR, 'lang_settings.json')

# נתיבים לקבצים
json_name = str(sys.argv[1])
lang_code = str(sys.argv[2]) # קוד שפה
JSON_FILE = os.path.join(DATA_DIR, lang_code, f'shorts_{json_name}.json') # תיקיית שפה בתוך data/shorts
STYLES_JSON_FILE = os.path.join(ASSETS_DIR, 'styles_shorts.json')
LOGO_PATH = os.path.join(LOGOS_DIR, 'logo_colored.png')

# הגדרות רווח בין שורות
LINE_SPACING_NORMAL = 60
LINE_SPACING_WITHIN_SENTENCE = 40
LINE_SPACING_BETWEEN_SENTENCE_AND_TRANSLATION = 60

# נתיב למוזיקת רקע (אם יש)
BACKGROUND_MUSIC_PATH = os.path.join(ASSETS_DIR, 'background_music.mp3')

# הגדרות MoviePy
VIDEO_SIZE = (1080, 1920)
WIDTH, HEIGHT = VIDEO_SIZE
FPS = 24
THREADS = 8

def sanitize_filename(filename):
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

def is_hebrew(text):
    for char in text:
        if '\u0590' <= char <= '\u05FF':
            return True
    return False

def process_hebrew_text(text):
    reshaped_text = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)
    return bidi_text

def remove_nikud(text):
    nikud_chars = set(chr(i) for i in range(0x0591, 0x05C7 + 1))
    return ''.join(c for c in text if c not in nikud_chars)


class FileManager:
    def __init__(self, output_dir, thumbnails_dir, lang_code):
        self.output_dir = os.path.join(output_dir, lang_code) # תיקיית פלט לפי שפה
        self.thumbnails_dir = os.path.join(thumbnails_dir, lang_code) # תיקיית תמונות ממוזערות לפי שפה
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
        self.styles_require_bright_blur = {'word', 'sentence', 'sentence_bold', 'translation'}
        self.overlay_color = (173, 216, 230, 150)

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

        base.paste(top, (0, 0), mask)
        return base

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

    def create_image(self, text_lines, style_definitions, line_styles=None, background_image_path=None):
        cache_key = tuple(text_lines) + tuple(line_styles or []) + (background_image_path,)
        if cache_key in self.cache:
            logging.info("שימוש בתמונה מקאש")
            return self.cache[cache_key]

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
                img = Image.new('RGB', (WIDTH, HEIGHT), color=(255, 255, 255))
            elif line_styles:
                try:
                    first_style = style_definitions[line_styles[0]]
                except KeyError:
                    logging.error(f"סגנון '{line_styles[0]}' לא נמצא בקובץ העיצובים.")
                    raise

                if first_style.get('background_image'):
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
                try:
                    first_style = style_definitions['normal']
                except KeyError:
                    logging.error("סגנון 'normal' לא נמצא בקובץ העיצובים.")
                    raise

                img = Image.new('RGB', (WIDTH, HEIGHT), color=tuple(first_style['bg_color']))

        if line_styles:
            for style_name in line_styles:
                if style_name in self.styles_require_bright_blur:
                    enhancer = ImageEnhance.Brightness(img)
                    img = enhancer.enhance(1.0)

                    img = img.filter(ImageFilter.GaussianBlur(radius=5))

                    overlay = Image.new('RGBA', img.size, self.overlay_color)
                    img = img.convert('RGBA')
                    img = Image.alpha_composite(img, overlay)
                    img = img.convert('RGB')

                    logging.info(f"עיבוד רקע והוספת שכבת הדגשה עבור הסגנון: {style_name}")
                    break

        draw = ImageDraw.Draw(img)

        MAX_TEXT_WIDTH = WIDTH - 100

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
            line_without_nikud = remove_nikud(line) if is_hebrew(line) else line

            if is_hebrew(line):
                split_lines = self.split_text_into_lines(line_without_nikud, font, MAX_TEXT_WIDTH, draw)
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
                                logging.error("סגנון חסר ('sentence_bold', 'word', 'call_to_action' או 'intro_subtitle').")
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
                    if processed_style['style_name'] in ['sentence', 'translation', 'intro_subtitle']:
                        spacing = LINE_SPACING_NORMAL
                    else:
                        spacing = LINE_SPACING_NORMAL
                    total_height += line_height + spacing
            else:
                split_lines = self.split_text_into_lines(line_without_nikud, font, MAX_TEXT_WIDTH, draw)
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
                                logging.error("סגנון חסר ('sentence_bold' או 'word').")
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
                    if processed_style['style_name'] in ['sentence', 'translation']:
                        spacing = LINE_SPACING_NORMAL
                    else:
                        spacing = LINE_SPACING_NORMAL
                    total_height += line_height + spacing

        if processed_lines:
            total_height -= spacing

        current_y = (HEIGHT - total_height) / 2

        for line_info, line_height, processed_style in processed_lines:
            line_width = sum([segment[1] for segment in line_info])
            x_text = (WIDTH - line_width) / 2
            for segment_text, width, height, segment_font, segment_color, segment_style in line_info:
                if processed_style['style_name'] in ['topic', 'video_number', 'call_to_action']:
                    glow_color = (255, 255, 255)
                    offsets = [
                        (-3, -3), (-3, 0), (-3, 3),
                        (0, -3), (0, 3),
                        (3, -3), (3, 0), (3, 3),
                        (-2, -2), (-2, 2), (2, -2), (2, 2),
                        (-4, 0), (4, 0), (0, -4), (0, 4)
                    ]
                    for offset in offsets:
                        draw.text(
                            (x_text + offset[0], current_y + (line_height - height) / 2 + offset[1]),
                            segment_text, font=segment_font, fill=glow_color
                        )

                if 'outline_color' in segment_style and 'outline_width' in segment_style:
                    outline_color = tuple(segment_style['outline_color'])
                    outline_width = segment_style['outline_width']
                    for dx in range(-outline_width, outline_width + 1):
                        for dy in range(-outline_width, outline_width + 1):
                            if dx != 0 or dy != 0:
                                draw.text((x_text + dx, current_y + dy + (line_height - height) / 2),
                                          segment_text, font=segment_font, fill=outline_color)

                draw.text((x_text, current_y + (line_height - height) / 2), segment_text, font=segment_font, fill=segment_color)
                x_text += width

            current_y += line_height + spacing

        img = img.convert("RGB")
        self.cache[cache_key] = img
        return img

def remove_asterisks(text):
    return text.replace("**", "")

class AudioCreator:
    def __init__(self, temp_dir, lang_settings):
        self.temp_dir = temp_dir
        self.lang_settings = lang_settings
        self.executor = ThreadPoolExecutor(max_workers=THREADS)
        self.client = texttospeech.TextToSpeechClient()

    def create_audio_task(self, text, lang, slow=False):
        try:
            clean_text = remove_asterisks(text)
            voice_settings = self.lang_settings.get(lang, self.lang_settings['es']).get('voice') # ברירת מחדל לספרדית אם שפה לא נמצאה

            if not voice_settings:
                logging.error(f"הגדרות קול לא נמצאו עבור שפה: {lang}. שימוש בהגדרות ברירת מחדל.")
                voice_settings = self.lang_settings['es']['voice'] # גיבוי להגדרות ספרדית

            language_code = voice_settings['language_code']
            voice_name = voice_settings['name']

            synthesis_input = texttospeech.SynthesisInput(text=clean_text)
            voice_params = texttospeech.VoiceSelectionParams(
                language_code=language_code,
                name=voice_name
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=0.70 if slow else 0.95
            )

            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=voice_params,
                audio_config=audio_config
            )

            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3', dir=self.temp_dir.name) as tmp_file:
                tmp_file.write(response.audio_content)
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
    def __init__(self, file_manager, image_creator, audio_creator, style_definitions, lang_settings):
        self.file_manager = file_manager
        self.image_creator = image_creator
        self.audio_creator = audio_creator
        self.style_definitions = style_definitions
        self.lang_settings = lang_settings

    def create_image_clip(self, text_lines, style, line_styles=None, background_image_path=None):
        img = self.image_creator.create_image(text_lines, self.style_definitions, line_styles, background_image_path)
        filename = f"{'_'.join([sanitize_filename(line) for line in text_lines])}.png"
        temp_image_path = self.file_manager.get_temp_path(filename)
        img.save(temp_image_path)
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
        direction = random.choice(['left', 'right'])

        if direction == 'left':
            move_out = lambda t: (-VIDEO_SIZE[0] * t / duration, 'center')
            move_in = lambda t: (VIDEO_SIZE[0] - VIDEO_SIZE[0] * t / duration, 'center')
        else:
            move_out = lambda t: (VIDEO_SIZE[0] * t / duration, 'center')
            move_in = lambda t: (-VIDEO_SIZE[0] + VIDEO_SIZE[0] * t / duration, 'center')

        clip1_moving = clip1.set_position(move_out).set_duration(duration)
        clip2_moving = clip2.set_position(move_in).set_duration(duration)

        transition = CompositeVideoClip([clip1_moving, clip2_moving], size=VIDEO_SIZE).set_duration(duration)
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

            new_size = int(WIDTH * 0.7)
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

    def create_intro_clip(self, intro_subtitle, title, video_number, background_image_path, lang_code):
        try:
            text_lines_intro = [intro_subtitle, title, f"#{video_number}"]
            line_styles_intro = ['intro_subtitle', 'topic', 'video_number']

            clip_intro = self.create_image_clip(text_lines_intro, 'intro_subtitle', line_styles_intro, background_image_path)

            # יצירת אודיו לכותרת ומספר הסרטון - שניהם בעברית ('iw')
            audio_tasks = [
                (title, 'iw'), # כותרת תוקרא בעברית
                (f"מספר {video_number}", 'iw')
            ]
            audio_results = self.audio_creator.create_audios(audio_tasks)
            clip_intro = self.create_clip(
                clip_intro,
                [
                    audio_results.get((title, 'iw'), ""), # שימוש באודיו כותרת עברית
                    audio_results.get((f"מספר {video_number}", 'iw'), "")
                ],
                min_duration=3
            )
            return clip_intro
        except Exception as e:
            logging.error(f"שגיאה ביצירת קליפ הפתיחה: {e}")
            return None

    def create_outro(self, call_to_action, background_image_path): # הסרנו lang_code מכיוון שההקראה תמיד בעברית
        try:
            text_lines_outro = [call_to_action]
            line_styles_outro = ['call_to_action']

            clip_outro = self.create_image_clip(text_lines_outro, 'outro', line_styles_outro, background_image_path)
            return clip_outro # החזר רק את קליפ התמונה, בלי אודיו בשלב זה
        except Exception as e:
            logging.error(f"שגיאה ביצירת קליפ הסיום: {e}")
            return None


    def create_language_strip(self, width, height, lang_code, text_bottom_margin=None):
        try:
            strip_height = int(height * 0.08)

            strip_image = Image.new('RGBA', (width, strip_height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(strip_image)

            def create_gradient(image, color1, color2):
                gradient = Image.new('RGBA', image.size, color=color1)
                for x in range(image.width):
                    for y in range(image.height):
                        ratio = y / image.height
                        r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
                        g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
                        b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
                        a = int(color1[3] * (1 - ratio) + color2[3] * ratio)
                        gradient.putpixel((x, y), (r, g, b, a))
                return gradient

            start_color = (100, 100, 128, 100)
            end_color = (0, 0, 128, 150)

            gradient_background = create_gradient(strip_image, start_color, end_color)
            strip_image.paste(gradient_background, (0, 0))

            font_size = int(strip_height * 0.5)
            try:
                font = self.image_creator.get_font("Rubik-Bold.ttf", font_size)
            except IOError:
                logging.error("לא ניתן למצוא את הגופן Rubik-Bold.ttf. מוודא שהוא נמצא בתיקיית FONTS_DIR.")
                font = ImageFont.load_default()

            lang_settings = self.lang_settings
            hebrew_text = lang_settings['iw']['language_name_iw']
            current_lang_text = lang_settings[lang_code]['language_name_iw']

            hebrew_processed = process_hebrew_text(hebrew_text)
            current_lang_processed = process_hebrew_text(current_lang_text)

            hebrew_bbox = draw.textbbox((0, 0), hebrew_processed, font=font)
            hebrew_width = hebrew_bbox[2] - hebrew_bbox[0]
            hebrew_height = hebrew_bbox[3] - hebrew_bbox[1]

            current_lang_bbox = draw.textbbox((0, 0), current_lang_processed, font=font)
            current_lang_width = current_lang_bbox[2] - current_lang_bbox[0]
            current_lang_height = current_lang_bbox[3] - current_lang_bbox[1]

            text_spacing = int(width * 0.03)
            edge_spacing = int(width * 0.03)

            israel_flag_path = os.path.join(FLAGS_DIR, 'עברית.png')
            current_lang_flag_path = os.path.join(FLAGS_DIR, f'{current_lang_text}.png') # שימוש בשם השפה לקובץ הדגל
            arrows_path = os.path.join(ASSETS_DIR, 'arrows.png')

            flag_max_height = int(strip_height * 0.6)
            flag_aspect_ratio = 1.5

            hebrew_x = width
            current_lang_x = 0

            arrow_img = None

            if os.path.exists(israel_flag_path):
                israel_flag = Image.open(israel_flag_path).convert("RGB")
                flag_width = int(flag_max_height * flag_aspect_ratio)
                israel_flag = israel_flag.resize((flag_width, flag_max_height), RESAMPLING)
                flag_x_israel = width - flag_width - edge_spacing
                strip_image.paste(israel_flag, (flag_x_israel, (strip_height - flag_max_height) // 2))
                hebrew_x = flag_x_israel - hebrew_width - text_spacing
            else:
                logging.warning(f"קובץ דגל ישראל לא נמצא בנתיב: {israel_flag_path}")

            if os.path.exists(current_lang_flag_path):
                current_lang_flag = Image.open(current_lang_flag_path).convert("RGB")
                flag_width = int(flag_max_height * flag_aspect_ratio)
                current_lang_flag = current_lang_flag.resize((flag_width, flag_max_height), RESAMPLING)
                flag_x_current_lang = edge_spacing
                strip_image.paste(current_lang_flag, (flag_x_current_lang, (strip_height - flag_max_height) // 2))
                current_lang_x = flag_x_current_lang + flag_width + text_spacing
            else:
                logging.warning(f"קובץ דגל {current_lang_text} לא נמצא בנתיב: {current_lang_flag_path}")

            if os.path.exists(arrows_path):
                arrow_img = Image.open(arrows_path).convert("RGBA")
                arrow_height = int(strip_height * 0.4)
                arrow_aspect = arrow_img.width / arrow_img.height
                arrow_width = int(arrow_height * arrow_aspect)
                arrow_img = arrow_img.resize((arrow_width, arrow_height), RESAMPLING)
            else:
                 logging.warning(f"קובץ החץ לא נמצא בנתיב: {arrows_path}")

            arrow_x = (hebrew_x + current_lang_x + hebrew_width) // 2 - arrow_width // 2
            arrow_y = (strip_height - arrow_height) // 2

            if text_bottom_margin is None:
                text_bottom_margin = int(strip_height * 0.5)

            y = strip_height - max(hebrew_height, current_lang_height) - text_bottom_margin

            text_color = (0, 242, 232)
            draw.text((hebrew_x, y), hebrew_processed, font=font, fill=text_color)
            draw.text((current_lang_x, y), current_lang_processed, font=font, fill=text_color)

            if arrow_img:
                strip_image.paste(arrow_img, (arrow_x, arrow_y), mask=arrow_img)

            temp_image_path = self.file_manager.get_temp_path("language_strip.png")
            strip_image.save(temp_image_path, "PNG")

            return temp_image_path, strip_height
        except Exception as e:
            logging.error(f"שגיאה ביצירת רצועת השפות: {e}")
            return None, 0


class VideoAssemblerShorts:
    def __init__(self, file_manager, image_creator, audio_creator, style_definitions, lang_settings):
        self.video_creator = VideoCreator(file_manager, image_creator, audio_creator, style_definitions, lang_settings)
        self.lang_settings = lang_settings
        self.lang_code = None

    def determine_background_image_path(self, title):
        background_image_filename = f"{sanitize_filename(title)}.png"
        background_image_path = os.path.join(BACKGROUNDS_DIR, background_image_filename)
        if not os.path.exists(background_image_path):
            logging.warning(f"תמונת הרקע '{background_image_filename}' לא נמצאה בתיקיית הרקעים. ישתמש ברקע לבן.")
            background_image_path = None
        return background_image_path

    def assemble_shorts_videos(self, data, output_dir, thumbnails_dir, lang_code):
        self.lang_code = lang_code
        videos = data

        for video_data in videos:
            video_number = video_data['video_number']
            title = video_data['title']
            word = video_data['word']
            translation = video_data['translation']
            examples = video_data['examples']
            call_to_action = video_data.get('call_to_action', '')
            intro_subtitle_text = "למד מילים חדשות בשישים שניות" # כתובית פתיח בשפה הרצויה

            logging.info(f"מעבד סרטון מספר {video_number}: {title} בשפה: {lang_code}")

            safe_title = sanitize_filename("".join([c for c in title if c.isalnum() or c in (' ', '_')]).rstrip().replace(" ", "_"))
            video_filename = f"Short_{lang_code}_{video_number}_{safe_title}.mp4" # שם קובץ כולל קוד שפה
            video_path = os.path.join(output_dir, video_filename)

            background_image_path = self.determine_background_image_path(title)
            clips = []

            try:
                intro_clip = self.video_creator.create_intro_clip(intro_subtitle_text, title, video_number, background_image_path, lang_code)
                if intro_clip:
                    clips.append(intro_clip)

                text_lines_word = [word, translation]
                line_styles_word = ['word', 'translation']
                clip_word = self.video_creator.create_image_clip(text_lines_word, 'word', line_styles_word, background_image_path)

                audio_tasks = [
                    (word, lang_code, True), # שימוש בקוד שפה משתנה
                    (translation, 'iw'),
                ]
                audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)

                audio_paths_word = []
                english_audio = audio_results.get((word, lang_code, True), "") # שימוש בקוד שפה משתנה
                if english_audio:
                    audio_paths_word.append(english_audio)
                hebrew_audio_translation = audio_results.get((translation, 'iw'), "")
                if hebrew_audio_translation:
                    audio_paths_word.append(hebrew_audio_translation)
                if english_audio:
                    audio_paths_word.append(english_audio)

                clip_word = self.video_creator.create_clip(clip_word, audio_paths_word, min_duration=3)
                clips.append(clip_word)

                for example in examples:
                    sentence = example['sentence']
                    ex_translation = example['translation']

                    text_lines_example = [sentence, ex_translation]
                    line_styles_example = ['sentence', 'translation']
                    clip_example = self.video_creator.create_image_clip(text_lines_example, 'sentence', line_styles_example, background_image_path)

                    audio_tasks = [
                        (sentence, lang_code, True), # שימוש בקוד שפה משתנה
                        (ex_translation, 'iw'),
                    ]
                    audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)

                    audio_paths_example = []
                    english_audio_sentence = audio_results.get((sentence, lang_code, True), "") # שימוש בקוד שפה משתנה
                    if english_audio_sentence:
                        audio_paths_example.append(english_audio_sentence)
                    hebrew_audio_ex_translation = audio_results.get((ex_translation, 'iw'), "")
                    if hebrew_audio_ex_translation:
                        audio_paths_example.append(hebrew_audio_ex_translation)
                    if english_audio_sentence:
                        audio_paths_example.append(english_audio_sentence)

                    clip_example = self.video_creator.create_clip(clip_example, audio_paths_example, min_duration=4)

                    if clips:
                        previous_clip = clips[-1]
                        transition = self.video_creator.slide_transition(previous_clip, clip_example)
                        clips.append(transition)

                    clips.append(clip_example)

                # קריאה לפעולה
                if call_to_action:
                    clip_outro_image = self.video_creator.create_outro(call_to_action, background_image_path) # יצירת קליפ תמונה בלבד
                    if clip_outro_image:
                        # יצירת משימת אודיו לקריאה לפעולה בעברית
                        audio_tasks_outro = [(call_to_action, 'iw')]
                        audio_results_outro = self.video_creator.audio_creator.create_audios(audio_tasks_outro)
                        audio_path_outro = audio_results_outro.get((call_to_action, 'iw'), "")

                        # יצירת קליפ סיום סופי עם תמונה ואודיו
                        clip_outro = self.video_creator.create_clip(
                            clip_outro_image, # שימוש בקליפ התמונה שנוצר
                            [audio_path_outro], # הוספת נתיב האודיו לקריאה לפעולה
                            min_duration=4
                        )
                        transition = self.video_creator.slide_transition(clips[-1], clip_outro)
                        clips.append(transition)
                        clips.append(clip_outro)
                        clip_outro_image.close() # סגירת קליפ התמונה לאחר שימוש

                logo_clip = self.video_creator.add_logo_clip(duration=5, background_image_path=background_image_path)
                if logo_clip:
                    transition = self.video_creator.slide_transition(clips[-1], logo_clip)
                    clips.append(transition)
                    clips.append(logo_clip)

                logging.info(f"איחוד הקליפים לסרטון מספר {video_number}: {title}")
                final_clip = concatenate_videoclips(clips, method="compose")

                if os.path.exists(BACKGROUND_MUSIC_PATH):
                    background_music = AudioFileClip(BACKGROUND_MUSIC_PATH).volumex(0.01)
                    background_music = audio_loop(background_music, duration=final_clip.duration)
                    final_audio = CompositeAudioClip([final_clip.audio, background_music])
                    final_clip = final_clip.set_audio(final_audio)
                    background_music.close()
                    final_audio.close()

                self.create_and_save_final_video(video_path, final_clip, video_number, lang_code) # קוד שפה לשמירה

            except Exception as e:
                logging.error(f"שגיאה בתהליך הרכבת הווידאו לסרטון מספר {video_number}: {e}")
            finally:
                for clip in clips:
                    clip.close()
                if 'final_clip' in locals():
                    final_clip.close()


    def add_language_strip_to_clip(self, clip, language_strip, strip_height):
        try:
            logging.info("Attempting to add language strip to clip")
            strip_clip = ImageClip(np.array(language_strip)).set_duration(clip.duration)

            resized_clip = clip.resize(height=VIDEO_SIZE[1] - strip_height)

            strip_position = (0, VIDEO_SIZE[1] - strip_height)

            final_clip = CompositeVideoClip([resized_clip, strip_clip.set_position(strip_position)])

            if clip.audio:
                final_clip = final_clip.set_audio(clip.audio)

            logging.info("Language strip added to clip successfully.")
            return final_clip

        except Exception as e:
            logging.error(f"Error adding language strip to clip: {e}")
            return clip


    def create_and_save_final_video(self, video_path, final_clip, video_number, lang_code):
        try:
            language_strip_path, strip_height = self.video_creator.create_language_strip(WIDTH, HEIGHT, lang_code) # קוד שפה לרצועה

            if language_strip_path:
                strip_clip = ImageClip(language_strip_path).set_duration(final_clip.duration)
                strip_position = (0, VIDEO_SIZE[1] - strip_height)
                final_video_clip = CompositeVideoClip([final_clip, strip_clip.set_position(strip_position)])
            else:
                final_video_clip = final_clip

            logging.info(f"שומר את הסרטון בנתיב: {video_path}")
            # הסר את השורה הבעייתית:
            # final_video_clip = final_video_clip.fx(afx.speedx, 1.0) # שמירה על מהירות תקינה
            final_video_clip.write_videofile(video_path, fps=FPS, codec='libx264', audio_codec='aac', threads=THREADS)

            thumbnail_path = os.path.join(thumbnails_dir, f"Short_{video_number}_thumbnail.png")
            final_video_clip.save_frame(thumbnail_path, t=0)
            logging.info(f"שומר תמונת תצוגה מקדימה בנתיב: {thumbnail_path}")

        except Exception as e:
            logging.error(f"שגיאה ביצירת או שמירת הסרטון הסופי: {e}")
        finally:
            if 'final_video_clip' in locals():
                final_video_clip.close()

def main():
    file_manager = None
    video_assembler = None
    lang_code = str(sys.argv[2]) # קוד שפה מגיע כארגומנט שני

    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        with open(STYLES_JSON_FILE, 'r', encoding='utf-8') as f:
            style_definitions = json.load(f)

        with open(LANG_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            lang_settings = json.load(f)

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
            "intro_subtitle"
        }

        missing_styles = required_styles - set(style_definitions.keys())
        if missing_styles:
            logging.error(f"סגנונות חסרים בקובץ העיצובים: {', '.join(missing_styles)}. ודא שכל הסגנונות הדרושים מוגדרים.")
            sys.exit(1)

        file_manager = FileManager(OUTPUT_DIR, THUMBNAILS_DIR, lang_code) # קוד שפה ל file manager
        image_creator = ImageCreator(styles=style_definitions)
        audio_creator = AudioCreator(file_manager.temp_dir, lang_settings) # lang_settings לאודיו
        video_assembler = VideoAssemblerShorts(file_manager, image_creator, audio_creator, style_definitions, lang_settings) # lang_settings ל video assembler

        video_assembler.assemble_shorts_videos(data, file_manager.output_dir, file_manager.thumbnails_dir, lang_code) # קוד שפה להרכבה

        logging.info(f"יצירת כל הסרטונים הסתיימה עבור שפה: {lang_code}!") # לוג כולל שפה

    except FileNotFoundError as e:
        logging.error(f"לא ניתן למצוא קובץ: {e.filename}")
    except json.JSONDecodeError as e:
        logging.error(f"שגיאה בפענוח קובץ JSON: {e}")
    except Exception as e:
        logging.error(f"שגיאה כללית בתהליך יצירת הסרטונים: {e}")
    finally:
        if file_manager:
            file_manager.cleanup()
        if 'audio_creator' in locals() and audio_creator:
            audio_creator.shutdown()

if __name__ == "__main__":
    main()