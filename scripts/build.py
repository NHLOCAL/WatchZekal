import json
import os
import random
import numpy as np
from gtts import gTTS
from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont

import arabic_reshaper
from bidi.algorithm import get_display

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
TEMP_DIR = os.path.join(OUTPUT_DIR, 'temp')

# נתיבים לקבצים
JSON_FILE = os.path.join(DATA_DIR, 'words.json')
FONT_PATH = os.path.join(FONTS_DIR, 'Rubik-Regular.ttf')  # ודא שהגופן תומך בעברית
SUBTOPIC_FONT_PATH = os.path.join(FONTS_DIR, 'Rubik-Bold.ttf')  # גופן מודגש עבור Subtopics
WORD_FONT_PATH = os.path.join(FONTS_DIR, 'Rubik-Bold.ttf')  # גופן מודגש עבור מילים
LOGO_PATH = os.path.join(LOGOS_DIR, 'logo.png')  # אם תרצה להשתמש בלוגו

# הגדרות עיצוב
FONT_SIZE = 80  # גודל גופן רגיל
SUBTOPIC_FONT_SIZE = 100  # גודל גופן ל-Subtopics
LEVEL_FONT_SIZE = 120  # גודל גופן למסך פתיחת Level
WORD_FONT_SIZE = 100  # גודל גופן גדול יותר למילים
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

# ודא שתיקיות היצוא זמינות
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(THUMBNAILS_DIR, exist_ok=True)

# קריאת קובץ JSON
with open(JSON_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

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

# פונקציה ליצירת גרדיאנט
def create_gradient_background(width, height, start_color, end_color, direction='vertical'):
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

# פונקציה ליצירת תמונת רקע עם טקסט ותמיכה בסגנונות שונים לכל שורה
def create_image(text_lines, image_path, style='normal', line_styles=None):
    # הגדרת סגנונות
    style_definitions = {
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
    
    # אם line_styles לא מוגדר, השתמש בסגנון הכללי לכל השורות
    if line_styles is None:
        line_styles = [style] * len(text_lines)
    elif isinstance(line_styles, str):
        line_styles = [line_styles] * len(text_lines)
    elif isinstance(line_styles, list):
        if len(line_styles) != len(text_lines):
            raise ValueError("אורך רשימת הסגנונות חייב להתאים לאורך רשימת הטקסטים")
    else:
        raise TypeError("הפרמטר line_styles חייב להיות מחרוזת או רשימה של מחרוזות")
    
    # קבלת צבע הרקע או יצירת גרדיאנט
    first_style = style_definitions[line_styles[0]]
    if first_style['gradient']:
        img = create_gradient_background(1920, 1080, first_style['gradient'][0], first_style['gradient'][1], first_style['gradient_direction'])
    else:
        img = Image.new('RGB', (1920, 1080), color=first_style['bg_color'])
    
    draw = ImageDraw.Draw(img)
    
    # חישוב גובה כולל
    total_height = 0
    processed_lines = []
    fonts = []
    for i, line in enumerate(text_lines):
        current_style = style_definitions[line_styles[i]]
        if is_hebrew(line):
            processed_line = process_hebrew_text(line)
        else:
            processed_line = line
        try:
            font = ImageFont.truetype(current_style['font_path'], current_style['font_size'])
        except IOError:
            print(f"לא ניתן למצוא את הגופן בנתיב: {current_style['font_path']}", flush=True)
            raise
        bbox = draw.textbbox((0, 0), processed_line, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        processed_lines.append((processed_line, width, height, current_style, font))
        # הוספת רווח נוסף אחרי השורה השנייה אם זה Outro_subtitle
        if i == 1 and line_styles[i] == 'outro_subtitle':
            total_height += height + 60  # רווח גדול יותר אחרי השורה השנייה
        else:
            total_height += height + 40  # רווח רגיל
    
    # מיקום ההתחלה במרכז אנכי
    current_y = (img.height - total_height) / 2
    
    # ציור הטקסט
    for i, (processed_line, width, height, current_style, font) in enumerate(processed_lines):
        x_text = (img.width - width) / 2  # מרכז אופקי
        draw.text((x_text, current_y), processed_line, font=font, fill=current_style['text_color'])
        
        # קביעת רווח בין השורות
        if i == 1 and line_styles[i] == 'outro_subtitle':  # אחרי השורה השנייה "לימוד אנגלית בקלי קלות"
            spacing = 60  # רווח גדול יותר
        else:
            spacing = 40  # רווח רגיל
        
        current_y += height + spacing  # רווח בין השורות
    
    # שמירת התמונה
    img = img.convert("RGB")  # המרת חזרה ל-RGB אם הוספנו אלפא
    img.save(image_path)

# פונקציה ליצירת אודיו מהטקסט
def create_audio(text, lang, audio_path):
    try:
        tts = gTTS(text=text, lang=lang)
        tts.save(audio_path)
    except ValueError as e:
        print(f"שגיאה ביצירת אודיו עבור הטקסט: '{text}' בשפה: '{lang}'. פרטים: {e}", flush=True)
        raise

# פונקציה ליצירת קליפ עם תמונה ואודיו
def create_clip(image_path, audio_en_path, audio_he_path):
    audio_en = AudioFileClip(audio_en_path)
    audio_he = AudioFileClip(audio_he_path)
    # חיבור האודיו באנגלית והעברית אחד אחרי השני
    audio_total = concatenate_audioclips([audio_en, audio_he])
    # יצירת קליפ תמונה עם משך בהתאם לאודיו
    img_clip = ImageClip(image_path).set_duration(audio_total.duration)
    img_clip = img_clip.set_audio(audio_total)
    return img_clip

# פונקציה להוספת מוזיקת רקע
def add_background_music(clip, music_path, volume=0.1):
    background_music = AudioFileClip(music_path).volumex(volume)
    # לולאה למוזיקה כדי שתתאים לאורך הקליפ
    background_music = afx.audio_loop(background_music, duration=clip.duration)
    # שילוב המוזיקה עם האודיו של הקליפ
    final_audio = CompositeAudioClip([clip.audio, background_music])
    return clip.set_audio(final_audio)

# פונקציה ליצירת מסך פתיחה לכל Level
def create_level_intro(level_num, level_name):
    intro_image_path = os.path.join(TEMP_DIR, f"level_{level_num}_intro.png")
    text_lines_intro = [f"Level {level_num}", level_name]
    create_image(text_lines_intro, intro_image_path, style='level')
    
    # יצירת אודיו לפתיחת Level
    audio_intro_en = os.path.join(TEMP_DIR, f"level_{level_num}_intro_en.mp3")
    audio_intro_he = os.path.join(TEMP_DIR, f"level_{level_num}_intro_he.mp3")
    create_audio(f"Level {level_num}", 'en', audio_intro_en)
    create_audio(level_name, 'iw', audio_intro_he)
    
    # יצירת קליפ פתיחה
    clip_intro = create_clip(intro_image_path, audio_intro_en, audio_intro_he)
    return clip_intro, intro_image_path

# פונקציה ליצירת מעבר החלקה בין שני קליפים
def slide_transition(clip1, clip2, duration=TRANSITION_DURATION):
    # בחר כיוון אקראי
    direction = random.choice(['left', 'right', 'up', 'down'])
    
    # הגדר את תנועת הקליפים בהתאם לכיוון
    if direction == 'left':
        move_out = lambda t: (-1920 * t / duration, 'center')
        move_in = lambda t: (1920 - 1920 * t / duration, 'center')
    elif direction == 'right':
        move_out = lambda t: (1920 * t / duration, 'center')
        move_in = lambda t: (-1920 + 1920 * t / duration, 'center')
    elif direction == 'up':
        move_out = lambda t: ('center', -1080 * t / duration)
        move_in = lambda t: ('center', 1080 - 1080 * t / duration)
    elif direction == 'down':
        move_out = lambda t: ('center', 1080 * t / duration)
        move_in = lambda t: ('center', -1080 + 1080 * t / duration)
    
    # קטעים עם אנימציית מיקום
    clip1_moving = clip1.set_position(move_out).set_duration(duration)
    clip2_moving = clip2.set_position(move_in).set_duration(duration)
    
    # שכבת הקליפים
    transition = CompositeVideoClip([clip1_moving, clip2_moving], size=(1920, 1080)).set_duration(duration)
    
    # הגדרת אודיו ל-None כדי למנוע בעיות באודיו
    transition = transition.set_audio(None)
    
    return transition

# פונקציה להוספת לוגו לסרטון
def add_logo_to_video(clip, logo_path, position='top-right', size=(180, 180), opacity=255, margin=(50, 50)):
    # פתיחת תמונת הלוגו באמצעות PIL
    logo_image = Image.open(logo_path).convert("RGBA")
    
    # שינוי גודל הלוגו עם LANCZOS
    logo_image = logo_image.resize(size, Image.LANCZOS)
    
    # התאמת שקיפות הלוגו
    if opacity < 255:
        alpha = logo_image.split()[3]
        alpha = alpha.point(lambda p: p * (opacity / 255))
        logo_image.putalpha(alpha)
    
    # המרת תמונת PIL למערך numpy
    logo_array = np.array(logo_image)
    
    # יצירת ImageClip מהמערך
    logo = (ImageClip(logo_array)
            .set_duration(clip.duration))
    
    # הגדרת מיקום עם מרווח מהשוליים
    x_margin, y_margin = margin
    if position == 'top-right':
        logo = logo.set_pos((clip.w - logo.w - x_margin, y_margin))
    elif position == 'top-left':
        logo = logo.set_pos((x_margin, y_margin))
    elif position == 'bottom-right':
        logo = logo.set_pos((clip.w - logo.w - x_margin, clip.h - logo.h - y_margin))
    elif position == 'bottom-left':
        logo = logo.set_pos((x_margin, clip.h - logo.h - y_margin))
    elif position == 'bottom-center':  # הוספת תמיכה ב-bottom-center
        x_position = (clip.w - logo.w) / 2
        y_position = clip.h - logo.h - y_margin
        logo = logo.set_pos((x_position, y_position))
    else:
        raise ValueError("מיקום לא נתמך")
    
    # שילוב הלוגו עם הסרטון
    return CompositeVideoClip([clip, logo])

# פונקציה ליצירת קטע סיום (Outro)
def create_outro():
    outro_image_path = os.path.join(TEMP_DIR, "outro.png")
    
    # טקסטים חדשים עם שם הערוץ
    # הכותרת תהיה גדולה ומודגשת, השורה השנייה מעט קטנה יותר
    text_lines_outro = [
        "זה קל!",
        "לימוד אנגלית בקלי קלות",
        "Thank you for watching!",
        "Don't forget to like and subscribe."
    ]
    
    # הגדרת סגנונות לכל שורה: הכותרת הראשונה 'outro_title', השנייה 'outro_subtitle', והיתר 'outro'
    line_styles_outro = ['outro_title', 'outro_subtitle', 'outro', 'outro']
    
    # יצירת תמונת ה-Outro עם הסגנונות החדשים
    create_image(text_lines_outro, outro_image_path, style='outro', line_styles=line_styles_outro)
    
    # יצירת אודיו לקליפ הסיום
    # האודיו יהיה באנגלית ובעברית
    # ניצור שני קבצי אודיו נפרדים ונשלב אותם יחד
    audio_outro_en = os.path.join(TEMP_DIR, "outro_en.mp3")
    audio_outro_he = os.path.join(TEMP_DIR, "outro_he.mp3")
    create_audio("It's easy! Thank you for watching! Don't forget to like and subscribe.", 'en', audio_outro_en)
    create_audio("זה קל! תודה שצפיתם! אל תשכחו לעשות like ולהירשם.", 'iw', audio_outro_he)
    
    # יצירת קליפ הסיום
    clip_outro = create_clip(outro_image_path, audio_outro_en, audio_outro_he)
    
    return clip_outro

# לולאה דרך כל הרמות
for level in data['levels']:
    level_num = level['level']
    level_name = level['name']
    print(f"מעבד Level {level_num}: {level_name}", flush=True)

    # יצירת שם קובץ וידאו בטוח
    safe_level_name = "".join([c for c in level_name if c.isalnum() or c in (' ', '_')]).rstrip().replace(" ", "_")
    video_filename = f"Level_{level_num}_{safe_level_name}.mp4"
    video_path = os.path.join(OUTPUT_DIR, video_filename)

    # רשימה לאחסון הקליפים
    clips = []

    # יצירת קליפ פתיחה ל-Level
    clip_level_intro, intro_image_path = create_level_intro(level_num, level_name)
    clips.append(clip_level_intro)

    # שמירת התמונה כמקדימה (Thumbnail)
    thumbnail_path = os.path.join(THUMBNAILS_DIR, f"Level_{level_num}_thumbnail.png")
    os.makedirs(THUMBNAILS_DIR, exist_ok=True)
    # העתקת התמונה במקום להעביר אותה, כדי לשמור אותה גם לקליפ
    from shutil import copyfile
    copyfile(intro_image_path, thumbnail_path)
    print(f"שומר תמונת תצוגה מקדימה בנתיב: {thumbnail_path}", flush=True)

    for subtopic in level['subtopics']:
        subtopic_name = subtopic['name']
        print(f"  מעבד Subtopic: {subtopic_name}", flush=True)

        # יצירת כותרת Subtopic עם עיצוב ייחודי
        safe_subtopic_name = "".join([c for c in subtopic_name if c.isalnum() or c in (' ', '_')]).rstrip().replace(" ", "_")
        image_subtopic_path = os.path.join(TEMP_DIR, f"{safe_level_name}_subtopic_{safe_subtopic_name}.png")
        text_lines_subtopic = [subtopic_name]
        create_image(text_lines_subtopic, image_subtopic_path, style='subtopic')

        # יצירת אודיו Subtopic
        audio_subtopic_en = os.path.join(TEMP_DIR, f"{safe_level_name}_subtopic_{safe_subtopic_name}_en.mp3")
        audio_subtopic_he = os.path.join(TEMP_DIR, f"{safe_level_name}_subtopic_{safe_subtopic_name}_he.mp3")
        create_audio(subtopic_name, 'en', audio_subtopic_en)
        create_audio(subtopic_name, 'iw', audio_subtopic_he)  # שינוי 'he' ל-'iw'

        # יצירת קליפ Subtopic
        clip_subtopic = create_clip(image_subtopic_path, audio_subtopic_en, audio_subtopic_he)
        
        # אם יש כבר קליפ קודם, ניצור מעבר בין הקליפ הקודם לחדש
        if clips:
            previous_clip = clips[-1]
            transition = slide_transition(previous_clip, clip_subtopic)
            clips.append(transition)
        
        clips.append(clip_subtopic)

        for word in subtopic['words']:
            word_text = word['word']
            word_translation = word['translation']
            examples = word['examples']

            print(f"    מעבד מילה: {word_text} - {word_translation}", flush=True)

            # יצירת תמונה ראשונה: המילה והתרגום
            safe_word_text = "".join([c for c in word_text if c.isalnum() or c in (' ', '_')]).rstrip().replace(" ", "_")
            image_word_path = os.path.join(TEMP_DIR, f"{safe_level_name}_word_{safe_word_text}.png")
            text_lines_word = [word_text, word_translation]
            
            # הגדרת סגנונות לכל שורה: 'word' לשורה הראשונה, 'normal' לשורה השנייה
            line_styles_word = ['word', 'normal']
            
            create_image(text_lines_word, image_word_path, style='normal', line_styles=line_styles_word)

            # יצירת אודיו למילה ולתרגום
            audio_word_en = os.path.join(TEMP_DIR, f"{safe_level_name}_word_{safe_word_text}_en.mp3")
            audio_word_he = os.path.join(TEMP_DIR, f"{safe_level_name}_word_{safe_word_text}_he.mp3")
            create_audio(word_text, 'en', audio_word_en)
            create_audio(word_translation, 'iw', audio_word_he)  # שינוי 'he' ל-'iw'

            # יצירת קליפ מילה
            clip_word = create_clip(image_word_path, audio_word_en, audio_word_he)
            
            # יצירת מעבר
            if clips:
                previous_clip = clips[-1]
                transition = slide_transition(previous_clip, clip_word)
                clips.append(transition)
            
            clips.append(clip_word)

            for idx, example in enumerate(examples):
                sentence = example['sentence']
                translation = example['translation']

                print(f"      מעבד משפט: {sentence} - {translation}", flush=True)

                # יצירת תמונה למשפט
                safe_sentence = "".join([c for c in sentence if c.isalnum() or c in (' ', '_')]).rstrip().replace(" ", "_")
                image_example_path = os.path.join(TEMP_DIR, f"{safe_level_name}_word_{safe_word_text}_example_{idx+1}.png")
                text_lines_example = [sentence, translation]
                create_image(text_lines_example, image_example_path, style='normal')

                # יצירת אודיו למשפט ולתרגום
                audio_example_en = os.path.join(TEMP_DIR, f"{safe_level_name}_word_{safe_word_text}_example_{idx+1}_en.mp3")
                audio_example_he = os.path.join(TEMP_DIR, f"{safe_level_name}_word_{safe_word_text}_example_{idx+1}_he.mp3")
                create_audio(sentence, 'en', audio_example_en)
                create_audio(translation, 'iw', audio_example_he)  # שינוי 'he' ל-'iw'

                # יצירת קליפ משפט
                clip_example = create_clip(image_example_path, audio_example_en, audio_example_he)
                
                # יצירת מעבר
                if clips:
                    previous_clip = clips[-1]
                    transition = slide_transition(previous_clip, clip_example)
                    clips.append(transition)
                
                clips.append(clip_example)

                # ניקוי קבצים זמניים למשפט
                os.remove(image_example_path)
                os.remove(audio_example_en)
                os.remove(audio_example_he)

            # ניקוי קבצים זמניים למילה
            os.remove(image_word_path)
            os.remove(audio_word_en)
            os.remove(audio_word_he)

        # ניקוי קבצים זמניים ל-Subtopic
        os.remove(image_subtopic_path)
        os.remove(audio_subtopic_en)
        os.remove(audio_subtopic_he)

    # הוספת קטע הסיום
    clip_outro = create_outro()
    transition = slide_transition(clips[-1], clip_outro)
    clips.append(transition)
    clips.append(clip_outro)

    # איחוד כל הקליפים לסרטון אחד עבור ה-Level
    print(f"איחוד הקליפים לסרטון Level {level_num}: {level_name}", flush=True)
    final_clip = concatenate_videoclips(clips, method="compose")

    # הוספת מוזיקת רקע אם קיימת
    if os.path.exists(BACKGROUND_MUSIC_PATH):
        final_clip = add_background_music(final_clip, BACKGROUND_MUSIC_PATH, volume=0.1)

    # הוספת הלוגו לסרטון
    final_clip = add_logo_to_video(final_clip, LOGO_PATH, position='top-right', size=(150, 150), opacity=200, margin=(20, 20))

    # שמירת הוידאו
    print(f"שומר את הסרטון בנתיב: {video_path}", flush=True)
    final_clip.write_videofile(video_path, fps=24, codec='libx264', audio_codec='aac')

    # ניקוי קבצים זמניים לאחר שמירת הוידאו
    for temp_file in os.listdir(TEMP_DIR):
        temp_file_path = os.path.join(TEMP_DIR, temp_file)
        if os.path.isfile(temp_file_path):
            os.remove(temp_file_path)

print("יצירת כל הסרטונים הסתיימה!", flush=True)
