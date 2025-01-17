import json
import sys
import os
import random
import re
import numpy as np
from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile
import logging
from functools import lru_cache
from audio_creator import AudioCreator

# הגדרת רמת הלוגינג
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# עדכון שימוש ב-LANCZOS
RESAMPLING = Image.LANCZOS

# הגדרות בסיסיות
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # נתיב לסקריפט הנוכחי
DATA_DIR = os.path.join(BASE_DIR, '..', 'data', 'levels')
ASSETS_DIR = os.path.join(BASE_DIR, '..', 'assets')
FONTS_DIR = os.path.join(ASSETS_DIR, 'fonts')
LOGOS_DIR = os.path.join(ASSETS_DIR, 'logos')
OUTPUT_DIR = os.path.join(BASE_DIR, '..', 'output')
THUMBNAILS_DIR = os.path.join(OUTPUT_DIR, 'thumbnails')
LANG_SETTINGS_FILE = os.path.join(DATA_DIR, 'lang_settings.json')  # נתיב לקובץ הגדרות שפה

# נתיב לתיקיית תמונות רקע
BACKGROUNDS_DIR = os.path.join(ASSETS_DIR, 'backgrounds')
os.makedirs(BACKGROUNDS_DIR, exist_ok=True)

# שמות קבצי תמונות רקע עבור כל סוג מקטע
BACKGROUND_IMAGES = {
    'subtopic': 'subtopic_background.png',
    'word': 'word_background.png',
    'sentence': 'sentence_background.png',
    'translation': 'sentence_background.png',
    'level': 'intro_outro_background.png',
    'outro': 'intro_outro_background.png',
    'outro_title': 'intro_outro_background.png'
}

# נתיבים לקבצים
json_name = str(sys.argv[1])
lang_code = str(sys.argv[2])  # קוד שפה (en, es, fr)
JSON_FILE = os.path.join(DATA_DIR, lang_code, f'words_level_{json_name}.json')
STYLES_JSON_FILE = os.path.join(ASSETS_DIR, 'styles-v2.json')  # שימוש בקובץ styles-v2.json
FONT_PATH = os.path.join(FONTS_DIR, 'Rubik-Regular.ttf')
LOGO_PATH = os.path.join(LOGOS_DIR, 'logo.png')

# הגדרות רווח בין שורות
LINE_SPACING_NORMAL = 60
LINE_SPACING_OUTRO_SUBTITLE = 80
LINE_SPACING_WITHIN_SENTENCE = 40
LINE_SPACING_BETWEEN_SENTENCE_AND_TRANSLATION = 60

# נתיב למוזיקת רקע
BACKGROUND_MUSIC_PATH = os.path.join(ASSETS_DIR, 'background_music.mp3')

# הגדרות MoviePy
VIDEO_SIZE = (1920, 1080)
FPS = 24
THREADS = 8

# זמן השהייה בין קטעי משפט ותרגום (בשניות)
SENTENCE_TRANSITION_DURATION = 1.0

def sanitize_filename(filename):
    """
    מסיר תווים בלתי חוקיים משם קובץ ומחליף אותם ב-underscore.
    """
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

class FileManager:
    def __init__(self, output_dir, thumbnails_dir, lang_code):
        self.output_dir = os.path.join(output_dir, lang_code)  # תיקיית פלט לפי שפה
        self.thumbnails_dir = os.path.join(thumbnails_dir, lang_code)  # תיקיית תמונות ממוזערות לפי שפה
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

    def create_image(self, text_lines, style_definitions, line_styles=None):
        cache_key = tuple(text_lines) + tuple(line_styles or [])
        if cache_key in self.cache:
            logging.info("שימוש בתמונה מקאש")
            return self.cache[cache_key]

        if line_styles:
            first_style_name = line_styles[0]
        else:
            first_style_name = 'normal'

        background_image_name = BACKGROUND_IMAGES.get(first_style_name)
        if background_image_name:
            background_image_path = os.path.join(BACKGROUNDS_DIR, background_image_name)
            try:
                img = Image.open(background_image_path).convert("RGBA")
                img = img.resize(VIDEO_SIZE, Image.LANCZOS)
            except FileNotFoundError:
                logging.error(f"תמונת רקע לא נמצאה בנתיב: {background_image_path}")
                raise
        else:
            logging.error(f"לא הוגדרה תמונת רקע עבור סוג מקטע: {first_style_name}")
            raise ValueError(f"לא הוגדרה תמונת רקע עבור סוג מקטע: {first_style_name}")
        
        draw = ImageDraw.Draw(img)
        MAX_TEXT_WIDTH = 1720

        total_height = 0
        processed_lines = []
        for i, line in enumerate(text_lines):
            if line_styles and i < len(line_styles):
                current_style = style_definitions[line_styles[i]]
            else:
                current_style = style_definitions['normal']

            font = self.get_font(current_style['font_path'], current_style['font_size'])

            if is_hebrew(line):
                split_lines = self.split_text_into_lines(line, font, MAX_TEXT_WIDTH, draw)
                for split_line in split_lines:
                    processed_line = process_hebrew_text(split_line)
                    processed_style = current_style.copy()
                    processed_style['style_name'] = line_styles[i] if line_styles and i < len(line_styles) else 'normal'
                    bbox = draw.textbbox((0, 0), processed_line, font=font)
                    width = bbox[2] - bbox[0]
                    height = bbox[3] - bbox[1]
                    processed_lines.append((processed_line, width, height, processed_style, font))
                    if processed_style['style_name'] == 'sentence':
                        spacing = LINE_SPACING_WITHIN_SENTENCE
                    elif processed_style['style_name'] == 'translation':
                        spacing = LINE_SPACING_BETWEEN_SENTENCE_AND_TRANSLATION
                    else:
                        spacing = LINE_SPACING_NORMAL
                    if i == 1 and line_styles and line_styles[i] == 'outro_subtitle':
                        spacing = LINE_SPACING_OUTRO_SUBTITLE
                    total_height += height + spacing
            else:
                split_lines = self.split_text_into_lines(line, font, MAX_TEXT_WIDTH, draw)
                for split_line in split_lines:
                    processed_line = split_line
                    processed_style = current_style.copy()
                    processed_style['style_name'] = line_styles[i] if line_styles and i < len(line_styles) else 'normal'
                    bbox = draw.textbbox((0, 0), processed_line, font=font)
                    width = bbox[2] - bbox[0]
                    height = bbox[3] - bbox[1]
                    processed_lines.append((processed_line, width, height, processed_style, font))
                    if processed_style['style_name'] == 'sentence':
                        spacing = LINE_SPACING_WITHIN_SENTENCE
                    elif processed_style['style_name'] == 'translation':
                        spacing = LINE_SPACING_BETWEEN_SENTENCE_AND_TRANSLATION
                    else:
                        spacing = LINE_SPACING_NORMAL
                    if i == 1 and line_styles and line_styles[i] == 'outro_subtitle':
                        spacing = LINE_SPACING_OUTRO_SUBTITLE
                    total_height += height + spacing

        if processed_lines:
            total_height -= spacing

        current_y = (img.height - total_height) / 2

        for idx, (processed_line, width, height, current_style, font) in enumerate(processed_lines):
            style_name = current_style.get('style_name', 'normal')
            if style_name in ['sentence', 'translation']:
                x_text = (img.width - width) / 2
            else:
                x_text = (img.width - width) / 2

            draw.text((x_text, current_y), processed_line, font=font, fill=tuple(current_style['text_color']))

            if idx < len(processed_lines) - 1:
                next_style = processed_lines[idx + 1][3].get('style_name', 'normal')
                if style_name == 'sentence' and next_style == 'translation':
                    spacing = LINE_SPACING_BETWEEN_SENTENCE_AND_TRANSLATION
                elif style_name in ['sentence', 'translation']:
                    spacing = LINE_SPACING_WITHIN_SENTENCE
                else:
                    spacing = LINE_SPACING_NORMAL
            else:
                spacing = 0

            current_y += height + spacing

        img = img.convert("RGB")
        self.cache[cache_key] = img
        return img

class VideoCreator:
    def __init__(self, file_manager, image_creator, audio_creator, style_definitions, lang_settings):
        self.file_manager = file_manager
        self.image_creator = image_creator
        self.audio_creator = audio_creator
        self.style_definitions = style_definitions
        self.lang_settings = lang_settings

    def create_image_clip(self, text_lines, style, line_styles=None):
        img = self.image_creator.create_image(text_lines, self.style_definitions, line_styles)
        filename = f"{'_'.join(text_lines)}.png"
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
        direction = random.choice(['left', 'right', 'up', 'down'])
        if direction == 'left':
            move_out = lambda t: (-VIDEO_SIZE[0] * t / duration, 'center')
            move_in = lambda t: (VIDEO_SIZE[0] - VIDEO_SIZE[0] * t / duration, 'center')
        elif direction == 'right':
            move_out = lambda t: (VIDEO_SIZE[0] * t / duration, 'center')
            move_in = lambda t: (-VIDEO_SIZE[0] + VIDEO_SIZE[0] * t / duration, 'center')
        elif direction == 'up':
            move_out = lambda t: ('center', -VIDEO_SIZE[1] * t / duration)
            move_in = lambda t: ('center', VIDEO_SIZE[1] - VIDEO_SIZE[1] * t / duration)
        else:  # direction == 'down'
            move_out = lambda t: ('center', VIDEO_SIZE[1] * t / duration)
            move_in = lambda t: ('center', -VIDEO_SIZE[1] + VIDEO_SIZE[1] * t / duration)

        clip1_moving = clip1.set_position(move_out).set_duration(duration)
        clip2_moving = clip2.set_position(move_in).set_duration(duration)

        transition = CompositeVideoClip([clip1_moving, clip2_moving], size=VIDEO_SIZE).set_duration(duration)
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

    def create_level_intro(self, level_num, level_name, lang_code):
        level_word = self.lang_settings.get(lang_code, self.lang_settings['en']).get('level_word', 'Level')
        text_lines_intro = [f"{level_word} {level_num}", level_name]
        line_styles_intro = ['level', 'level']
        clip_intro = self.create_image_clip(text_lines_intro, 'level', line_styles_intro)

        audio_tasks = [
            (f"{level_word} {level_num}", lang_code),
            (level_name, 'iw')
        ]
        audio_results = self.audio_creator.create_audios(audio_tasks)
        clip_intro = self.create_clip(
            clip_intro,
            [
                audio_results.get((f"{level_word} {level_num}", lang_code), ""),
                audio_results.get((level_name, 'iw'), "")
            ],
            min_duration=6
        )
        return clip_intro

    def create_outro(self, lang_code):
        outro_data = self.lang_settings.get(lang_code, self.lang_settings['en']).get('outro', None)
        if outro_data is None:
             logging.error(f"לא נמצאו הגדרות outro עבור שפה: {lang_code}")
             raise ValueError(f"לא נמצאו הגדרות outro עבור שפה: {lang_code}")

        text_lines_outro = outro_data['text_lines']
        line_styles_outro = outro_data['line_styles']
        outro_audio_tasks = outro_data['audio_tasks']

        clip_outro = self.create_image_clip(text_lines_outro, 'outro', line_styles_outro)
        audio_results = self.audio_creator.create_audios(outro_audio_tasks)
        audio_paths = [audio_results.get(tuple(task), "") for task in outro_audio_tasks]
        clip_outro = self.create_clip(clip_outro, audio_paths, min_duration=15)
        return clip_outro

class VideoAssembler:
    def __init__(self, file_manager, image_creator, audio_creator, style_definitions, lang_settings):
        self.video_creator = VideoCreator(file_manager, image_creator, audio_creator, style_definitions, lang_settings)
        self.lang_code = None
        self.lang_settings = lang_settings

    def assemble_level_video(self, level, output_dir, thumbnails_dir, lang_code):
        self.lang_code = lang_code
        level_num = level['level']
        level_name = level['name']
        logging.info(f"מעבד Level {level_num}: {level_name}")

        safe_level_name = sanitize_filename("".join([c for c in level_name if c.isalnum() or c in (' ', '_')]).rstrip().replace(" ", "_"))
        video_filename = f"Level_{level_num}_{safe_level_name}.mp4"
        video_path = os.path.join(output_dir, video_filename)

        clips = []

        try:
            clip_level_intro = self.video_creator.create_level_intro(level_num, level_name, self.lang_code)
            clips.append(clip_level_intro)

            thumbnail_path = os.path.join(thumbnails_dir, f"Level_{level_num}_thumbnail.png")
            clip_level_intro.save_frame(thumbnail_path, t=0)
            logging.info(f"שומר תמונת תצוגה מקדימה בנתיב: {thumbnail_path}")

            for subtopic in level['subtopics']:
                subtopic_name = subtopic['name']
                logging.info(f"  מעבד Subtopic: {subtopic_name}")

                text_lines_subtopic = [subtopic_name]
                line_styles_subtopic = ['subtopic']
                clip_subtopic = self.video_creator.create_image_clip(text_lines_subtopic, 'subtopic', line_styles_subtopic)

                audio_tasks = [
                    (subtopic_name, self.lang_code),
                    (subtopic_name, 'iw')
                ]
                audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                clip_subtopic = self.video_creator.create_clip(
                    clip_subtopic,
                    [
                        audio_results.get((subtopic_name, self.lang_code), ""),
                        audio_results.get((subtopic_name, 'iw'), "")
                    ],
                    min_duration=4.5
                )

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

                    text_lines_word = [word_text, word_translation]
                    line_styles_word = ['word', 'normal']
                    clip_word = self.video_creator.create_image_clip(text_lines_word, 'word', line_styles_word)

                    audio_tasks = [
                        (word_text, self.lang_code, True),
                        (word_translation, 'iw'),
                        (word_text, self.lang_code, True)
                    ]
                    audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                    clip_word = self.video_creator.create_clip(
                        clip_word,
                        [
                            audio_results.get((word_text, self.lang_code, True), ""),
                            audio_results.get((word_translation, 'iw'), ""),
                            audio_results.get((word_text, self.lang_code, True), "")
                        ]
                    )

                    if clips:
                        previous_clip = clips[-1]
                        transition = self.video_creator.slide_transition(previous_clip, clip_word)
                        clips.append(transition)

                    clips.append(clip_word)

                    for idx, example in enumerate(examples):
                        sentence = example['sentence']
                        translation = example['translation']

                        logging.info(f"      מעבד משפט: {sentence} - {translation}")

                        text_lines_example = [sentence, translation]
                        line_styles_example = ['sentence', 'translation']
                        clip_example = self.video_creator.create_image_clip(text_lines_example, 'normal', line_styles_example)

                        audio_tasks = [
                            (sentence, self.lang_code, True),
                            (translation, 'iw'),
                            (sentence, self.lang_code, True)
                        ]
                        audio_results = self.video_creator.audio_creator.create_audios(audio_tasks)
                        clip_example = self.video_creator.create_clip(
                            clip_example,
                            [
                                audio_results.get((sentence, self.lang_code, True), ""),
                                audio_results.get((translation, 'iw'), ""),
                                audio_results.get((sentence, self.lang_code, True), "")
                            ]
                        )
                        
                        # הוספת השהייה בין קטעי משפט ותרגום
                        if clips:
                            previous_clip = clips[-1]
                            if previous_clip.duration < SENTENCE_TRANSITION_DURATION:
                                previous_clip = previous_clip.set_duration(SENTENCE_TRANSITION_DURATION)
                            # לא מוסיפים מעבר בין קטעי משפט ותרגום
                            if previous_clip != clip_example:
                                clips.append(clip_example)
                            else:
                                clips.append(clip_example)
                        else:
                            clips.append(clip_example)

            clip_outro = self.video_creator.create_outro(self.lang_code)
            transition = self.video_creator.slide_transition(clips[-1], clip_outro)
            clips.append(transition)
            clips.append(clip_outro)

            logging.info(f"איחוד הקליפים לסרטון Level {level_num}: {level_name}")
            final_clip = concatenate_videoclips(clips, method="compose")

            if os.path.exists(BACKGROUND_MUSIC_PATH):
                background_music = AudioFileClip(BACKGROUND_MUSIC_PATH).volumex(0.1)
                background_music = afx.audio_loop(background_music, duration=final_clip.duration)
                final_audio = CompositeAudioClip([final_clip.audio, background_music])
                final_clip = final_clip.set_audio(final_audio)
                background_music.close()
                final_audio.close()

            final_clip = self.video_creator.add_logo_to_video(
                final_clip,
                LOGO_PATH,
                position='top-right',
                size=(150, 150),
                opacity=200,
                margin=(20, 20)
            )

            logging.info(f"שומר את הסרטון בנתיב: {video_path}")
            final_clip.write_videofile(video_path, fps=FPS, codec='libx264', audio_codec='aac', threads=THREADS)

        except Exception as e:
            logging.error(f"שגיאה בתהליך הרכבת הוידאו ל-Level {level_num}: {e}")
        finally:
            for clip in clips:
                if clip:
                  clip.close()
            if 'final_clip' in locals():
                final_clip.close()

    def shutdown(self):
        self.video_creator.audio_creator.shutdown()

def close_clips(clips):
    for clip in clips:
        clip.close()

def main():
    lang_code = sys.argv[2]  # קבלת קוד השפה כארגומנט
    file_manager = FileManager(OUTPUT_DIR, THUMBNAILS_DIR, lang_code)
    video_assembler = None

    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        with open(STYLES_JSON_FILE, 'r', encoding='utf-8') as f:
            style_definitions = json.load(f)

        with open(LANG_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            lang_settings = json.load(f)

        image_creator = ImageCreator(styles=style_definitions)
        audio_creator = AudioCreator(file_manager.temp_dir, lang_settings, THREADS)
        video_assembler = VideoAssembler(file_manager, image_creator, audio_creator, style_definitions, lang_settings)

        for level in data['levels']:
            video_assembler.assemble_level_video(level, file_manager.output_dir, file_manager.thumbnails_dir, lang_code)

        logging.info("יצירת כל הסרטונים הסתיימה!")

    except Exception as e:
        logging.error(f"שגיאה כללית בתהליך יצירת הסרטונים: {e}")

    finally:
        if file_manager:
            file_manager.cleanup()
        if video_assembler:
            video_assembler.shutdown()

if __name__ == "__main__":
    main()