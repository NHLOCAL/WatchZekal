import json
import os
import random
import re
import numpy as np
from gtts import gTTS
from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile
import logging
from functools import lru_cache

# הגדרת רמת הלוגינג
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# עדכון שימוש ב-LANCZOS
RESAMPLING = Image.LANCZOS

# הגדרות בסיסיות
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # נתיב לסקריפט הנוכחי
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')
ASSETS_DIR = os.path.join(BASE_DIR, '..', 'assets')
FONTS_DIR = os.path.join(ASSETS_DIR, 'fonts')
LOGOS_DIR = os.path.join(ASSETS_DIR, 'logos')
OUTPUT_DIR = os.path.join(BASE_DIR, '..', 'output', 'videos')
THUMBNAILS_DIR = os.path.join(OUTPUT_DIR, 'thumbnails')

# נתיבים לקבצים
json_name = input('add json name:\n>>>')
JSON_FILE = os.path.join(DATA_DIR, f'{json_name}.json')
FONT_PATH = os.path.join(FONTS_DIR, 'Rubik-Regular.ttf')  # ודא שהגופן תומך בעברית
SUBTOPIC_FONT_PATH = os.path.join(FONTS_DIR, 'Rubik-Bold.ttf')  # גופן מודגש עבור Subtopics
WORD_FONT_PATH = os.path.join(FONTS_DIR, 'Rubik-Bold.ttf')  # גופן מודגש עבור מילים
LOGO_PATH = os.path.join(LOGOS_DIR, 'logo.png')  # אם תרצה להשתמש בלוגו

# הגדרות עיצוב
FONT_SIZE = 80  # גודל גופן רגיל
SUBTOPIC_FONT_SIZE = 100  # גודל גופן ל-Subtopics
LEVEL_FONT_SIZE = 120  # גודל גופן למסך פתיחת Level
WORD_FONT_SIZE = 100  # גודל גופן גדול יותר למילים

# הגדרות רווח בין שורות
LINE_SPACING_NORMAL = 60  # רווח רגיל בין השורות
LINE_SPACING_OUTRO_SUBTITLE = 80  # רווח גדול יותר אחרי שורה מסוימת

BG_COLOR = (200, 210, 230)  # רקע מעט כהה יותר למילים ולמשפטים
SUBTOPIC_BG_COLOR = (200, 220, 255)  # רקע ל-Subtopics
LEVEL_BG_COLOR = (255, 223, 186)  # רקע למסך פתיחת Level
TEXT_COLOR = (0, 0, 0)  # טקסט רגיל
SUBTOPIC_TEXT_COLOR = (0, 0, 128)  # טקסט ל-Subtopics
LEVEL_TEXT_COLOR = (255, 69, 0)  # טקסט למסך פתיחת Level
WORD_TEXT_COLOR = (0, 0, 0)  # טקסט למילים
TRANSITION_DURATION = 1  # משך המעבר בשניות

# נתיב למוזיקת רקע (אם יש)
BACKGROUND_MUSIC_PATH = os.path.join(ASSETS_DIR, 'background_music.mp3')  # ודא שהקובץ קיים

# הגדרות MoviePy
VIDEO_SIZE = (1920, 1080)
FPS = 24
THREADS = 4

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
    def __init__(self, fonts):
        self.fonts = fonts
        self.cache = {}

    @lru_cache(maxsize=None)
    def get_font(self, font_path, font_size):
        try:
            return ImageFont.truetype(font_path, font_size)
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

    def create_image(self, text_lines, style_definitions, line_styles=None):
        # שימוש בקאשינג למניעת יצירת תמונות חוזרות
        cache_key = tuple(text_lines) + tuple(line_styles or [])
        if cache_key in self.cache:
            logging.info("שימוש בתמונה מקאש")
            return self.cache[cache_key]

        # יצירת רקע
        if line_styles:
            # אם line_styles מוגדר, נשתמש בסגנון לכל שורה
            first_style = style_definitions[line_styles[0]]
        else:
            # אחרת, נשתמש בסגנון הכללי
            first_style = style_definitions['normal']

        if first_style['gradient']:
            img = self.create_gradient_background(1920, 1080, first_style['gradient'][0], first_style['gradient'][1], first_style['gradient_direction'])
        else:
            img = Image.new('RGB', (1920, 1080), color=first_style['bg_color'])

        draw = ImageDraw.Draw(img)

        # חישוב גובה כולל
        total_height = 0
        processed_lines = []
        for i, line in enumerate(text_lines):
            if line_styles and i < len(line_styles):
                current_style = style_definitions[line_styles[i]]
            else:
                current_style = style_definitions['normal']
            if is_hebrew(line):
                processed_line = process_hebrew_text(line)
            else:
                processed_line = line
            font = self.get_font(current_style['font_path'], current_style['font_size'])
            bbox = draw.textbbox((0, 0), processed_line, font=font)
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            processed_lines.append((processed_line, width, height, current_style, font))
            if i == 1 and line_styles and line_styles[i] == 'outro_subtitle':
                total_height += height + LINE_SPACING_OUTRO_SUBTITLE  # רווח גדול יותר אחרי השורה השנייה
            else:
                total_height += height + LINE_SPACING_NORMAL  # רווח רגיל

        # מיקום ההתחלה במרכז אנכי
        current_y = (img.height - total_height) / 2

        # ציור הטקסט
        for i, (processed_line, width, height, current_style, font) in enumerate(processed_lines):
            x_text = (img.width - width) / 2  # מרכז אופקי
            draw.text((x_text, current_y), processed_line, font=font, fill=current_style['text_color'])

            # קביעת רווח בין השורות
            if i == 1 and line_styles and line_styles[i] == 'outro_subtitle':  # אחרי השורה השנייה "לימוד אנגלית בקלי קלות"
                spacing = LINE_SPACING_OUTRO_SUBTITLE  # רווח גדול יותר
            else:
                spacing = LINE_SPACING_NORMAL  # רווח רגיל

            current_y += height + spacing  # רווח בין השורות

        # שמירת התמונה בזיכרון
        img = img.convert("RGB")  # המרת חזרה ל-RGB אם הוספנו אלפא
        self.cache[cache_key] = img
        return img

class AudioCreator:
    def __init__(self, temp_dir):
        self.temp_dir = temp_dir
        self.executor = ThreadPoolExecutor(max_workers=THREADS)

    def create_audio_task(self, text, lang):
        try:
            tts = gTTS(text=text, lang=lang)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3', dir=self.temp_dir.name) as tmp_file:
                tts.save(tmp_file.name)
                return tmp_file.name
        except ValueError as e:
            logging.error(f"שגיאה ביצירת אודיו עבור הטקסט: '{text}' בשפה: '{lang}'. פרטים: {e}")
            raise

    def create_audios(self, tasks):
        futures = {self.executor.submit(self.create_audio_task, text, lang): (text, lang) for text, lang in tasks}
        results = {}
        for future in as_completed(futures):
            text, lang = futures[future]
            try:
                audio_path = future.result()
                results[(text, lang)] = audio_path
                logging.info(f"אודיו נוצר עבור: '{text}' בשפה: '{lang}'")
            except Exception as e:
                logging.error(f"שגיאה ביצירת אודיו עבור: '{text}' בשפה: '{lang}'. פרטים: {e}")
        return results

    def shutdown(self):
        self.executor.shutdown(wait=True)

class VideoCreator:
    def __init__(self, file_manager, image_creator, audio_creator):
        self.file_manager = file_manager
        self.image_creator = image_creator
        self.audio_creator = audio_creator
        self.style_definitions = self.define_styles()

    def define_styles(self):
        return {
            'normal': {
                'bg_color': BG_COLOR,
                'gradient': None,
                'gradient_direction': 'vertical',
                'text_color': TEXT_COLOR,
                'font_size': FONT_SIZE,
                'font_path': FONT_PATH
            },
            'subtopic': {
                'bg_color': SUBTOPIC_BG_COLOR,
                'gradient': None,
                'gradient_direction': 'vertical',
                'text_color': SUBTOPIC_TEXT_COLOR,
                'font_size': SUBTOPIC_FONT_SIZE,
                'font_path': SUBTOPIC_FONT_PATH
            },
            'level': {
                'bg_color': LEVEL_BG_COLOR,
                'gradient': None,
                'gradient_direction': 'vertical',
                'text_color': LEVEL_TEXT_COLOR,
                'font_size': LEVEL_FONT_SIZE,
                'font_path': SUBTOPIC_FONT_PATH  # שימוש בגופן מודגש
            },
            'word': {
                'bg_color': BG_COLOR,
                'gradient': None,
                'gradient_direction': 'vertical',
                'text_color': WORD_TEXT_COLOR,
                'font_size': WORD_FONT_SIZE,
                'font_path': WORD_FONT_PATH  # גופן מודגש
            },
            'gradient_background': {
                'bg_color': None,
                'gradient': ((255, 255, 255), (200, 200, 255)),  # דוגמה ל-Start ו-End צבעים
                'gradient_direction': 'vertical',
                'text_color': TEXT_COLOR,
                'font_size': FONT_SIZE,
                'font_path': FONT_PATH
            },
            'outro': {  # סגנון ל-Outro
                'bg_color': (50, 150, 200),  # צבע רקע כחול נעים
                'gradient': None,
                'gradient_direction': 'vertical',
                'text_color': (255, 255, 255),  # טקסט לבן
                'font_size': 60,  # גודל גופן קטן יותר לטקסט רגיל
                'font_path': FONT_PATH
            },
            'outro_title': {  # סגנון לכותרת הראשית של Outro
                'bg_color': (50, 150, 200),  # אותו צבע רקע כחול נעים
                'gradient': None,
                'gradient_direction': 'vertical',
                'text_color': (255, 255, 255),  # טקסט לבן
                'font_size': 120,  # גודל גופן גדול יותר
                'font_path': SUBTOPIC_FONT_PATH  # שימוש בגופן מודגש
            },
            'outro_subtitle': {  # סגנון לתת-כותרת של Outro
                'bg_color': (50, 150, 200),  # אותו צבע רקע כחול נעים
                'gradient': None,
                'gradient_direction': 'vertical',
                'text_color': (255, 255, 255),  # טקסט לבן
                'font_size': 100,  # גודל גופן מעט קטן יותר מהכותרת
                'font_path': SUBTOPIC_FONT_PATH  # שימוש בגופן מודגש
            }
        }

    def create_image_clip(self, text_lines, style, line_styles=None):
        img = self.image_creator.create_image(text_lines, self.style_definitions, line_styles)
        # יצירת שם קובץ בטוח
        filename = f"{'_'.join(text_lines)}.png"
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

    def create_clip(self, image_clip, audio_en_path, audio_he_path, min_duration=0):
        audio_total = self.create_audio_clips([audio_en_path, audio_he_path])
        if audio_total:
            duration = max(audio_total.duration, min_duration)
            image_clip = image_clip.set_duration(duration)
            image_clip = image_clip.set_audio(audio_total)
        else:
            image_clip = image_clip.set_duration(min_duration)
        return image_clip

    def slide_transition(self, clip1, clip2, duration=TRANSITION_DURATION):
        # בחר כיוון אקראי
        direction = random.choice(['left', 'right', 'up', 'down'])

        # הגדר את תנועת הקליפים בהתאם לכיוון
        if direction == 'left':
            move_out = lambda t: (-VIDEO_SIZE[0] * t / duration, 'center')
            move_in = lambda t: (VIDEO_SIZE[0] - VIDEO_SIZE[0] * t / duration, 'center')
        elif direction == 'right':
            move_out = lambda t: (VIDEO_SIZE[0] * t / duration, 'center')
            move_in = lambda t: (-VIDEO_SIZE[0] + VIDEO_SIZE[0] * t / duration, 'center')
        elif direction == 'up':
            move_out = lambda t: ('center', -VIDEO_SIZE[1] * t / duration)
            move_in = lambda t: ('center', VIDEO_SIZE[1] - VIDEO_SIZE[1] * t / duration)
        elif direction == 'down':
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

    def add_logo_to_video(self, clip, logo_path, position='top-right', size=(180, 180), opacity=255, margin=(50, 50)):
        try:
            logo_image = Image.open(logo_path).convert("RGBA")
            logo_image = logo_image.resize(size, RESAMPLING)

            if opacity < 255:
                alpha = logo_image.split()[3]
                alpha = alpha.point(lambda p: p * (opacity / 255))
                logo_image.putalpha(alpha)

            logo_array = np.array(logo_image)
            logo = (ImageClip(logo_array)
                    .set_duration(clip.duration))

            x_margin, y_margin = margin
            if position == 'top-right':
                logo = logo.set_pos((clip.w - logo.w - x_margin, y_margin))
            elif position == 'top-left':
                logo = logo.set_pos((x_margin, y_margin))
            elif position == 'bottom-right':
                logo = logo.set_pos((clip.w - logo.w - x_margin, clip.h - logo.h - y_margin))
            elif position == 'bottom-left':
                logo = logo.set_pos((x_margin, clip.h - logo.h - y_margin))
            elif position == 'bottom-center':
                x_position = (clip.w - logo.w) / 2
                y_position = clip.h - logo.h - y_margin
                logo = logo.set_pos((x_position, y_position))
            else:
                raise ValueError("מיקום לא נתמך")

            return CompositeVideoClip([clip, logo])
        except Exception as e:
            logging.error(f"שגיאה בהוספת הלוגו: {e}")
            return clip

    def create_level_intro(self, level_num, level_name):
        text_lines_intro = [f"Level {level_num}", level_name]
        # הגדרת סגנון לכל שורה: 'level' לכל שורה
        line_styles_intro = ['level', 'level']
        clip_intro = self.create_image_clip(text_lines_intro, 'level', line_styles_intro)

        # יצירת אודיו לפתיחת Level
        audio_tasks = [
            (f"Level {level_num}", 'en'),
            (level_name, 'iw')
        ]
        audio_results = self.audio_creator.create_audios(audio_tasks)
        clip_intro = self.create_clip(
            clip_intro,
            audio_results.get((f"Level {level_num}", 'en'), ""),
            audio_results.get((level_name, 'iw'), ""),
            min_duration=5  # **הוספת מינימום משך 5 שניות**
        )
        return clip_intro

    def create_outro(self):
        text_lines_outro = [
            "זה קל!",
            "לימוד אנגלית בקלי קלות",
            "Thank you for watching!",
            "Don't forget to like and subscribe."
        ]
        line_styles_outro = ['outro_title', 'outro_subtitle', 'outro', 'outro']
        clip_outro = self.create_image_clip(text_lines_outro, 'outro', line_styles_outro)

        # יצירת אודיו לקליפ הסיום
        audio_tasks = [
            ("It's easy! Thank you for watching! Don't forget to like and subscribe.", 'en'),
            ("זה קל! תודה שצפיתם! אל תשכחו לעשות like ולהירשם.", 'iw')
        ]
        audio_results = self.audio_creator.create_audios(audio_tasks)
        clip_outro = self.create_clip(
            clip_outro,
            audio_results.get(("It's easy! Thank you for watching! Don't forget to like and subscribe.", 'en'), ""),
            audio_results.get(("זה קל! תודה שצפיתם! אל תשכחו לעשות like ולהירשם.", 'iw'), "")
        )
        return clip_outro

class VideoAssembler:
    def __init__(self, file_manager, image_creator, audio_creator):
        self.video_creator = VideoCreator(file_manager, image_creator, audio_creator)

    def assemble_level_video(self, level, output_dir, thumbnails_dir):
        level_num = level['level']
        level_name = level['name']
        logging.info(f"מעבד Level {level_num}: {level_name}")

        # יצירת שם קובץ וידאו בטוח
        safe_level_name = sanitize_filename("".join([c for c in level_name if c.isalnum() or c in (' ', '_')]).rstrip().replace(" ", "_"))
        video_filename = f"Level_{level_num}_{safe_level_name}.mp4"
        video_path = os.path.join(output_dir, video_filename)

        # רשימה לאחסון הקליפים
        clips = []

        try:
            # יצירת קליפ פתיחה ל-Level
            clip_level_intro = self.video_creator.create_level_intro(level_num, level_name)
            clips.append(clip_level_intro)

            # שמירת התמונה כמקדימה (Thumbnail)
            thumbnail_path = os.path.join(thumbnails_dir, f"Level_{level_num}_thumbnail.png")
            clip_level_intro.save_frame(thumbnail_path, t=0)
            logging.info(f"שומר תמונת תצוגה מקדימה בנתיב: {thumbnail_path}")

            for subtopic in level['subtopics']:
                subtopic_name = subtopic['name']
                logging.info(f"  מעבד Subtopic: {subtopic_name}")

                # יצירת כותרת Subtopic עם עיצוב ייחודי
                text_lines_subtopic = [subtopic_name]
                line_styles_subtopic = ['subtopic']
                clip_subtopic = self.video_creator.create_image_clip(text_lines_subtopic, 'subtopic', line_styles_subtopic)

                # יצירת אודיו Subtopic
                audio_tasks = [
                    (subtopic_name, 'en'),
                    (subtopic_name, 'iw')
                ]
                audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                clip_subtopic = self.video_creator.create_clip(
                    clip_subtopic,
                    audio_results.get((subtopic_name, 'en'), ""),
                    audio_results.get((subtopic_name, 'iw'), ""),
                    min_duration=4.5  # **הוספת מינימום משך 4.5 שניות**
                )

                # יצירת מעבר בין הקליפ הקודם לחדש
                if clips:
                    previous_clip = clips[-1]
                    transition = self.video_creator.slide_transition(previous_clip, clip_subtopic)
                    clips.append(transition)

                clips.append(clip_subtopic)

                for word in subtopic['words']:
                    word_text = word['word']
                    word_translation = word['translation']
                    examples = word['examples']

                    logging.info(f"    מעבד מילה: {word_text} - {word_translation}")

                    # יצירת תמונה ראשונה: המילה והתרגום
                    text_lines_word = [word_text, word_translation]
                    line_styles_word = ['word', 'normal']
                    clip_word = self.video_creator.create_image_clip(text_lines_word, 'word', line_styles_word)

                    # יצירת אודיו למילה ולתרגום
                    audio_tasks = [
                        (word_text, 'en'),
                        (word_translation, 'iw')
                    ]
                    audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                    clip_word = self.video_creator.create_clip(
                        clip_word,
                        audio_results.get((word_text, 'en'), ""),
                        audio_results.get((word_translation, 'iw'), "")
                    )

                    # יצירת מעבר
                    if clips:
                        previous_clip = clips[-1]
                        transition = self.video_creator.slide_transition(previous_clip, clip_word)
                        clips.append(transition)

                    clips.append(clip_word)

                    for idx, example in enumerate(examples):
                        sentence = example['sentence']
                        translation = example['translation']

                        logging.info(f"      מעבד משפט: {sentence} - {translation}")

                        # יצירת תמונה למשפט
                        text_lines_example = [sentence, translation]
                        line_styles_example = ['normal', 'normal']
                        clip_example = self.video_creator.create_image_clip(text_lines_example, 'normal', line_styles_example)

                        # יצירת אודיו למשפט ולתרגום
                        audio_tasks = [
                            (sentence, 'en'),
                            (translation, 'iw')
                        ]
                        audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                        clip_example = self.video_creator.create_clip(
                            clip_example,
                            audio_results.get((sentence, 'en'), ""),
                            audio_results.get((translation, 'iw'), "")
                        )

                        # יצירת מעבר
                        if clips:
                            previous_clip = clips[-1]
                            transition = self.video_creator.slide_transition(previous_clip, clip_example)
                            clips.append(transition)

                        clips.append(clip_example)

            # יצירת קטע הסיום
            clip_outro = self.video_creator.create_outro()
            transition = self.video_creator.slide_transition(clips[-1], clip_outro)
            clips.append(transition)
            clips.append(clip_outro)

            # איחוד כל הקליפים לסרטון אחד עבור ה-Level
            logging.info(f"איחוד הקליפים לסרטון Level {level_num}: {level_name}")
            final_clip = concatenate_videoclips(clips, method="compose")

            # הוספת מוזיקת רקע אם קיימת
            if os.path.exists(BACKGROUND_MUSIC_PATH):
                background_music = AudioFileClip(BACKGROUND_MUSIC_PATH).volumex(0.1)
                background_music = afx.audio_loop(background_music, duration=final_clip.duration)
                final_audio = CompositeAudioClip([final_clip.audio, background_music])
                final_clip = final_clip.set_audio(final_audio)
                # סגירת background_music ו-final_audio לאחר השימוש
                background_music.close()
                final_audio.close()

            # הוספת הלוגו לסרטון
            final_clip = self.video_creator.add_logo_to_video(
                final_clip,
                LOGO_PATH,
                position='top-right',
                size=(150, 150),
                opacity=200,
                margin=(20, 20)
            )

            # שמירת הוידאו
            logging.info(f"שומר את הסרטון בנתיב: {video_path}")
            final_clip.write_videofile(video_path, fps=FPS, codec='libx264', audio_codec='aac', threads=THREADS)

        except Exception as e:
            logging.error(f"שגיאה בתהליך הרכבת הוידאו ל-Level {level_num}: {e}")
        finally:
            # סגירת כל הקליפים
            for clip in clips:
                clip.close()
            # סגירת final_clip אם לא כבר סגור
            if 'final_clip' in locals():
                final_clip.close()

    def shutdown(self):
        self.video_creator.audio_creator.shutdown()

def close_clips(clips):
    for clip in clips:
        clip.close()

def main():
    # ניהול קבצים
    file_manager = FileManager(OUTPUT_DIR, THUMBNAILS_DIR)

    video_assembler = None  # אתחול מראש

    try:
        # קריאת קובץ JSON
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # יצירת אובייקטים
        image_creator = ImageCreator(fonts={
            'normal': FONT_PATH,
            'subtopic': SUBTOPIC_FONT_PATH,
            'level': SUBTOPIC_FONT_PATH,
            'word': WORD_FONT_PATH,
            'outro': FONT_PATH,
            'outro_title': SUBTOPIC_FONT_PATH,
            'outro_subtitle': SUBTOPIC_FONT_PATH
        })
        audio_creator = AudioCreator(file_manager.temp_dir)
        video_assembler = VideoAssembler(file_manager, image_creator, audio_creator)

        # לולאה דרך כל הרמות
        for level in data['levels']:
            video_assembler.assemble_level_video(level, OUTPUT_DIR, THUMBNAILS_DIR)

        logging.info("יצירת כל הסרטונים הסתיימה!")

    except Exception as e:
        logging.error(f"שגיאה כללית בתהליך יצירת הסרטונים: {e}")

    finally:
        # ניקוי קבצים זמניים וסגירת ThreadPoolExecutor
        if file_manager:
            file_manager.cleanup()
        if video_assembler:
            video_assembler.shutdown()

if __name__ == "__main__":
    main()
