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

    def create_image(self, text_lines, style_definitions, line_styles=None, background_image_path=None, process_background=True):
        cache_key = tuple(text_lines) + tuple(line_styles or []) + (background_image_path,) + (process_background,)
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

        for line_info, line_height in processed_lines:
            line_width = sum([segment[1] for segment in line_info])
            x_text = (WIDTH - line_width) / 2
            for segment_text, width, height, segment_font, segment_color in line_info:
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

    def create_image_clip(self, text_lines, style, line_styles=None, background_image_path=None, process_background=True):
        img = self.image_creator.create_image(text_lines, self.style_definitions, line_styles, background_image_path, process_background)
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

    def create_intro_clip(self, intro_subtitle, title, video_number, background_image_path):
        try:
            # סדר השורות: intro_subtitle מעל, אחריו title ומספר הסרטון
            text_lines_intro = [intro_subtitle, title, f"#{video_number}"]
            line_styles_intro = ['intro_subtitle', 'topic', 'video_number']

            clip_intro = self.create_image_clip(text_lines_intro, 'intro_subtitle', line_styles_intro, background_image_path, process_background=False)

            # יצירת אודיו רק לשם הנושא ומספר הסרטון, לא למשפט הנוסף
            audio_tasks = [
                (title, 'iw'),
                (f"מספר {video_number}", 'iw')
            ]
            audio_results = self.audio_creator.create_audios(audio_tasks)
            clip_intro = self.create_clip(
                clip_intro,
                [
                    audio_results.get((title, 'iw'), ""),
                    audio_results.get((f"מספר {video_number}", 'iw'), "")
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

class VideoAssembler:
    def __init__(self, file_manager, image_creator, audio_creator, style_definitions):
        self.video_creator = VideoCreator(file_manager, image_creator, audio_creator, style_definitions)

    def determine_background_image_path(self, title):
        background_image_filename = f"{sanitize_filename(title)}.png"
        background_image_path = os.path.join(BACKGROUNDS_DIR, background_image_filename)
        if not os.path.exists(background_image_path):
            logging.warning(f"תמונת הרקע '{background_image_filename}' לא נמצאה בתיקיית הרקעים. ישתמש ברקע לבן.")
            background_image_path = None
        return background_image_path

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
            language_level = video_data['language_level']
            story_type = video_data['story_type']
            story = video_data['story']
            vocabulary = video_data.get('vocabulary', [])
            grammar_points = video_data.get('grammar_points', [])
            comprehension_questions = video_data.get('comprehension_questions', [])
            call_to_action = video_data.get('call_to_action', {}).get('text', '')
            intro_subtitle_text = "למד מילים חדשות בשישים שניות"  # משפט הפתיחה הנוסף

            logging.info(f"מעבד סרטון: {video_title}")

            safe_title = sanitize_filename(video_title.replace(" ", "_"))
            video_filename = f"{safe_title}.mp4"
            video_path = os.path.join(output_dir, video_filename)

            background_image_path = self.determine_background_image_path(video_title)

            clips = []

            try:
                # קליפ פתיחה
                intro_clip = self.video_creator.create_intro_clip(intro_subtitle_text, video_title, 1, background_image_path)
                if intro_clip:
                    clips.append(intro_clip)

                # הצגת הסיפור
                for paragraph in story['text']:
                    english_text = paragraph['english']
                    hebrew_text = paragraph['hebrew']
                    text_lines = [english_text, hebrew_text]
                    line_styles = ['sentence', 'translation']
                    clip_story = self.video_creator.create_image_clip(text_lines, 'sentence', line_styles, background_image_path, process_background=True)

                    audio_tasks = [
                        (english_text, 'en', True),  # אנגלית באיטיות
                        (hebrew_text, 'iw')
                    ]
                    audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                    audio_paths = [
                        audio_results.get((english_text, 'en', True), ""),
                        audio_results.get((hebrew_text, 'iw'), "")
                    ]

                    clip_story = self.video_creator.create_clip(
                        clip_story,
                        audio_paths,
                        min_duration=5
                    )
                    if clips:
                        transition = self.video_creator.slide_transition(clips[-1], clip_story)
                        clips.append(transition)
                    clips.append(clip_story)

                # אוצר מילים
                if vocabulary:
                    vocab_title = "אוצר מילים"
                    text_lines = [vocab_title]
                    line_styles = ['subtopic']
                    clip_vocab_title = self.video_creator.create_image_clip(text_lines, 'subtopic', line_styles, background_image_path, process_background=True)
                    audio_tasks = [(vocab_title, 'iw')]
                    audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                    clip_vocab_title = self.video_creator.create_clip(
                        clip_vocab_title,
                        [audio_results.get((vocab_title, 'iw'), "")],
                        min_duration=3
                    )
                    transition = self.video_creator.slide_transition(clips[-1], clip_vocab_title)
                    clips.append(transition)
                    clips.append(clip_vocab_title)

                    for word_entry in vocabulary:
                        word = word_entry['word']
                        translation = word_entry['translation']
                        text_lines = [word, translation]
                        line_styles = ['word', 'translation']
                        clip_word = self.video_creator.create_image_clip(text_lines, 'word', line_styles, background_image_path, process_background=True)
                        audio_tasks = [
                            (word, 'en', True),  # קריאה באנגלית באיטיות
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
                            min_duration=4
                        )
                        transition = self.video_creator.slide_transition(clips[-1], clip_word)
                        clips.append(transition)
                        clips.append(clip_word)

                # נקודות דקדוק
                if grammar_points:
                    grammar_title = "נקודות דקדוק"
                    text_lines = [grammar_title]
                    line_styles = ['subtopic']
                    clip_grammar_title = self.video_creator.create_image_clip(text_lines, 'subtopic', line_styles, background_image_path, process_background=True)
                    audio_tasks = [(grammar_title, 'iw')]
                    audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                    clip_grammar_title = self.video_creator.create_clip(
                        clip_grammar_title,
                        [audio_results.get((grammar_title, 'iw'), "")],
                        min_duration=3
                    )
                    transition = self.video_creator.slide_transition(clips[-1], clip_grammar_title)
                    clips.append(transition)
                    clips.append(clip_grammar_title)

                    for point in grammar_points:
                        title = point['title']
                        explanation = point['explanation']
                        text_lines = [title, explanation]
                        line_styles = ['word', 'translation']
                        clip_point = self.video_creator.create_image_clip(text_lines, 'word', line_styles, background_image_path, process_background=True)
                        audio_tasks = [
                            (title, 'iw'),
                            (explanation, 'iw')
                        ]
                        audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                        audio_paths = [
                            audio_results.get((title, 'iw'), ""),
                            audio_results.get((explanation, 'iw'), "")
                        ]
                        clip_point = self.video_creator.create_clip(
                            clip_point,
                            audio_paths,
                            min_duration=5
                        )
                        transition = self.video_creator.slide_transition(clips[-1], clip_point)
                        clips.append(transition)
                        clips.append(clip_point)

                # שאלות הבנה
                if comprehension_questions:
                    questions_title = "שאלות הבנה"
                    text_lines = [questions_title]
                    line_styles = ['subtopic']
                    clip_questions_title = self.video_creator.create_image_clip(text_lines, 'subtopic', line_styles, background_image_path, process_background=True)
                    audio_tasks = [(questions_title, 'iw')]
                    audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                    clip_questions_title = self.video_creator.create_clip(
                        clip_questions_title,
                        [audio_results.get((questions_title, 'iw'), "")],
                        min_duration=3
                    )
                    transition = self.video_creator.slide_transition(clips[-1], clip_questions_title)
                    clips.append(transition)
                    clips.append(clip_questions_title)

                    for question_entry in comprehension_questions:
                        question = question_entry['question']
                        options = question_entry['options']
                        text_lines = [question] + options
                        line_styles = ['sentence'] + ['translation'] * len(options)
                        clip_question = self.video_creator.create_image_clip(text_lines, 'sentence', line_styles, background_image_path, process_background=True)
                        audio_tasks = [(question, 'iw')] + [(opt, 'iw') for opt in options]
                        audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                        audio_paths = [audio_results.get((text, 'iw'), "") for text in [question] + options]
                        clip_question = self.video_creator.create_clip(
                            clip_question,
                            audio_paths,
                            min_duration=6
                        )
                        transition = self.video_creator.slide_transition(clips[-1], clip_question)
                        clips.append(transition)
                        clips.append(clip_question)

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
            "title",
            "intro_subtitle",
            "video_number",
            "topic",
            "logo"
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