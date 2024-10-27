import json
import os
from gtts import gTTS
from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# הגדרות בסיסיות
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # נתיב לסקריפט הנוכחי
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')
ASSETS_DIR = os.path.join(BASE_DIR, '..', 'assets')
FONTS_DIR = os.path.join(ASSETS_DIR, 'fonts')
LOGOS_DIR = os.path.join(ASSETS_DIR, 'logos')
OUTPUT_DIR = os.path.join(BASE_DIR, '..', 'output', 'videos')
TEMP_DIR = os.path.join(OUTPUT_DIR, 'temp')

# נתיבים לקבצים
JSON_FILE = os.path.join(DATA_DIR, 'words.json')
FONT_PATH = os.path.join(FONTS_DIR, 'arial.ttf')  # ודא שהגופן תומך בעברית
SUBTOPIC_FONT_PATH = os.path.join(FONTS_DIR, 'arialbd.ttf')  # גופן מודגש עבור Subtopics
LOGO_PATH = os.path.join(LOGOS_DIR, 'logo.png')  # אם תרצה להשתמש בלוגו

# הגדרות עיצוב
FONT_SIZE = 80  # הגדלת גודל הגופן למילים ולמשפטים
SUBTOPIC_FONT_SIZE = 100  # גודל גופן שונה ל-Subtopics
LEVEL_FONT_SIZE = 120  # גודל גופן למסך פתיחת Level
BG_COLOR = (255, 255, 255)  # רקע לבן
SUBTOPIC_BG_COLOR = (200, 200, 255)  # רקע שונה ל-Subtopics
LEVEL_BG_COLOR = (255, 223, 186)  # רקע מיוחד למסך פתיחת Level
TEXT_COLOR = (0, 0, 0)  # טקסט שחור
SUBTOPIC_TEXT_COLOR = (0, 0, 128)  # צבע טקסט שונה ל-Subtopics
LEVEL_TEXT_COLOR = (255, 69, 0)  # צבע טקסט שונה למסך פתיחת Level
DURATION_PER_CLIP = 3  # משך כל קליפ בשניות
DELAY_BETWEEN_CLIPS = 1  # משך ההמתנה בין קליפים בשניות

# ודא שתיקיות היצוא זמינות
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

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

# פונקציה ליצירת תמונת רקע עם טקסט
def create_image(text_lines, image_path, style='normal'):
    # בחירת צבע רקע ועיצוב לפי הסגנון
    if style == 'subtopic':
        bg_color = SUBTOPIC_BG_COLOR
        text_color = SUBTOPIC_TEXT_COLOR
        font_size = SUBTOPIC_FONT_SIZE
        font_path = SUBTOPIC_FONT_PATH
    elif style == 'level':
        bg_color = LEVEL_BG_COLOR
        text_color = LEVEL_TEXT_COLOR
        font_size = LEVEL_FONT_SIZE
        font_path = SUBTOPIC_FONT_PATH  # שימוש בגופן מודגש
    else:
        bg_color = BG_COLOR
        text_color = TEXT_COLOR
        font_size = FONT_SIZE
        font_path = FONT_PATH

    # יצירת תמונה
    img = Image.new('RGB', (1920, 1080), color=bg_color)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        print(f"לא ניתן למצוא את הגופן בנתיב: {font_path}")
        raise

    # חישוב מיקום הטקסט במרכז האנכי והאופקי
    total_height = 0
    processed_lines = []
    for line in text_lines:
        if is_hebrew(line):
            processed_line = process_hebrew_text(line)
        else:
            processed_line = line
        bbox = draw.textbbox((0, 0), processed_line, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        processed_lines.append((processed_line, width, height))
        total_height += height + 40  # רווח גדול יותר בין השורות

    current_y = (img.height - total_height) / 2  # מרכז אנכי

    for processed_line, width, height in processed_lines:
        x_text = (img.width - width) / 2  # מרכז אופקי
        draw.text((x_text, current_y), processed_line, font=font, fill=text_color)
        current_y += height + 40  # רווח בין השורות

    # שמירת התמונה
    img.save(image_path)

# פונקציה ליצירת אודיו מהטקסט
def create_audio(text, lang, audio_path):
    try:
        tts = gTTS(text=text, lang=lang)
        tts.save(audio_path)
    except ValueError as e:
        print(f"שגיאה ביצירת אודיו עבור הטקסט: '{text}' בשפה: '{lang}'. פרטים: {e}")
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
    return clip_intro

# לולאה דרך כל הרמות
for level in data['levels']:
    level_num = level['level']
    level_name = level['name']
    print(f"מעבד Level {level_num}: {level_name}")

    # יצירת שם קובץ וידאו בטוח
    safe_level_name = "".join([c for c in level_name if c.isalnum() or c in (' ', '_')]).rstrip().replace(" ", "_")
    video_filename = f"Level_{level_num}_{safe_level_name}.mp4"
    video_path = os.path.join(OUTPUT_DIR, video_filename)

    # רשימה לאחסון הקליפים
    clips = []

    # יצירת קליפ פתיחה ל-Level
    clip_level_intro = create_level_intro(level_num, level_name)
    clips.append(clip_level_intro)

    # יצירת השהייה אחרי פתיחת Level
    blank_clip = ColorClip(size=(1920, 1080), color=BG_COLOR, duration=DELAY_BETWEEN_CLIPS)
    clips.append(blank_clip)

    for subtopic in level['subtopics']:
        subtopic_name = subtopic['name']
        print(f"  מעבד Subtopic: {subtopic_name}")

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
        clips.append(clip_subtopic)

        # יצירת השהייה אחרי Subtopic
        clips.append(blank_clip)

        for word in subtopic['words']:
            word_text = word['word']
            word_translation = word['translation']
            examples = word['examples']

            print(f"    מעבד מילה: {word_text} - {word_translation}")

            # יצירת תמונה ראשונה: המילה והתרגום
            safe_word_text = "".join([c for c in word_text if c.isalnum() or c in (' ', '_')]).rstrip().replace(" ", "_")
            image_word_path = os.path.join(TEMP_DIR, f"{safe_level_name}_word_{safe_word_text}.png")
            text_lines_word = [word_text, word_translation]
            create_image(text_lines_word, image_word_path)  # עיצוב רגיל

            # יצירת אודיו למילה ולתרגום
            audio_word_en = os.path.join(TEMP_DIR, f"{safe_level_name}_word_{safe_word_text}_en.mp3")
            audio_word_he = os.path.join(TEMP_DIR, f"{safe_level_name}_word_{safe_word_text}_he.mp3")
            create_audio(word_text, 'en', audio_word_en)
            create_audio(word_translation, 'iw', audio_word_he)  # שינוי 'he' ל-'iw'

            # יצירת קליפ מילה
            clip_word = create_clip(image_word_path, audio_word_en, audio_word_he)
            clips.append(clip_word)

            # יצירת השהייה אחרי מילה
            clips.append(blank_clip)

            for idx, example in enumerate(examples):
                sentence = example['sentence']
                translation = example['translation']

                print(f"      מעבד משפט: {sentence} - {translation}")

                # יצירת תמונה למשפט
                safe_sentence = "".join([c for c in sentence if c.isalnum() or c in (' ', '_')]).rstrip().replace(" ", "_")
                image_example_path = os.path.join(TEMP_DIR, f"{safe_level_name}_word_{safe_word_text}_example_{idx+1}.png")
                text_lines_example = [sentence, translation]
                create_image(text_lines_example, image_example_path)  # עיצוב רגיל

                # יצירת אודיו למשפט ולתרגום
                audio_example_en = os.path.join(TEMP_DIR, f"{safe_level_name}_word_{safe_word_text}_example_{idx+1}_en.mp3")
                audio_example_he = os.path.join(TEMP_DIR, f"{safe_level_name}_word_{safe_word_text}_example_{idx+1}_he.mp3")
                create_audio(sentence, 'en', audio_example_en)
                create_audio(translation, 'iw', audio_example_he)  # שינוי 'he' ל-'iw'

                # יצירת קליפ משפט
                clip_example = create_clip(image_example_path, audio_example_en, audio_example_he)
                clips.append(clip_example)

                # יצירת השהייה אחרי משפט
                clips.append(blank_clip)

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

    # איחוד כל הקליפים לסרטון אחד עבור ה-Level
    print(f"איחוד הקליפים לסרטון Level {level_num}: {level_name}")
    final_clip = concatenate_videoclips(clips, method="compose")

    # שמירת הוידאו
    print(f"שומר את הסרטון בנתיב: {video_path}")
    final_clip.write_videofile(video_path, fps=24, codec='libx264', audio_codec='aac')

    # ניקוי קבצים זמניים לאחר שמירת הוידאו
    for temp_file in os.listdir(TEMP_DIR):
        temp_file_path = os.path.join(TEMP_DIR, temp_file)
        if os.path.isfile(temp_file_path):
            os.remove(temp_file_path)

print("יצירת כל הסרטונים הסתיימה!")
