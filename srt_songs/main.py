import os
import json
import sys
import traceback

from video_maker.subtitle_generator import SubtitleGenerator
from video_maker.video_creator import VideoCreator

CONFIG_DIR = 'config'
CONFIG_FILE_NAME = 'video_config.json'
SONG_LIST_FILE_NAME = 'song_list.json'

def load_config(config_path):
    if not os.path.exists(config_path):
        print(f"שגיאה: קובץ הקונפיגורציה '{config_path}' לא נמצא.")
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"קונפיגורציה נטענה בהצלחה מ: '{config_path}'")
        return config
    except json.JSONDecodeError:
        print(f"שגיאה: קובץ הקונפיגורציה '{config_path}' אינו קובץ JSON תקין.")
        return None
    except Exception as e:
        print(f"שגיאה בטעינת קובץ הקונפיגורציה '{config_path}': {e}")
        return None

def resolve_paths(config, base_dir):
    resolved_config = config.copy()
    paths_cfg = resolved_config.get('paths', {})

    assets_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('assets_rel', '../assets')))
    fonts_dir = os.path.join(assets_dir, paths_cfg.get('fonts_subdir', 'fonts'))
    output_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('output_rel', 'output')))
    output_frames_dir = os.path.join(output_dir, paths_cfg.get('output_frames_subdir', 'subtitle_frames'))
    demo_songs_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('demo_songs_rel', 'demo_songs')))
    srt_files_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('srt_files_rel', 'srt_files')))

    resolved_config['paths'] = {
        'assets_dir': assets_dir,
        'fonts_dir': fonts_dir,
        'output_dir': output_dir,
        'output_frames_dir': output_frames_dir,
        'demo_songs_dir': demo_songs_dir,
        'srt_files_dir': srt_files_dir
    }

    bg_config = resolved_config.get('background', {})
    if 'image_path_rel_assets' in bg_config:
        bg_rel_path = bg_config['image_path_rel_assets']
        bg_config['background_image_path'] = os.path.join(assets_dir, bg_rel_path)
    else:
         print("אזהרה: נתיב תמונת רקע ראשית לא הוגדר כראוי בקונפיגורציה.")

    if 'intro_image_path_rel_assets' in bg_config:
        intro_bg_rel_path = bg_config['intro_image_path_rel_assets']
        bg_config['intro_background_image_path'] = os.path.join(assets_dir, intro_bg_rel_path)
        print(f"נתיב רקע פתיח זוהה: {bg_config['intro_background_image_path']}")
    else:
        print("אזהרה: נתיב תמונת רקע לפתיח לא הוגדר בקונפיגורציה. ישתמש ברקע הראשי.")
        bg_config['intro_background_image_path'] = None

    resolved_config['background'] = bg_config

    if 'artist_style' not in resolved_config:
        print("אזהרה: הגדרות עיצוב 'artist_style' חסרות בקובץ הקונפיגורציה. שם הזמר לא יוצג.")

    # Validate new subtitle structure
    sub_style = resolved_config.get('subtitle_style', {})
    if 'source' not in sub_style or 'target' not in sub_style:
        print("שגיאת קונפיגורציה קריטית: 'subtitle_style' חייב להכיל קטעי 'source' ו-'target'.")
        return None, None, None # Indicate error
    for role in ['source', 'target']:
        role_style = sub_style[role]
        missing_keys = [key for key in ['font_name', 'font_size', 'color'] if key not in role_style]
        if missing_keys:
            print(f"שגיאת קונפיגורציה קריטית: חלק '{role}' ב-'subtitle_style' חסר את המפתחות הבאים: {', '.join(missing_keys)}")
            return None, None, None # Indicate error

    return resolved_config, demo_songs_dir, srt_files_dir


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, CONFIG_DIR, CONFIG_FILE_NAME)
SONG_LIST_JSON_PATH = os.path.join(BASE_DIR, CONFIG_DIR, SONG_LIST_FILE_NAME)

SYSTEM_INSTRUCTIONS_FILE_NAME = 'system_instructions.yaml'
SYSTEM_INSTRUCTIONS_PATH = os.path.join(BASE_DIR, CONFIG_DIR, SYSTEM_INSTRUCTIONS_FILE_NAME)


raw_config = load_config(CONFIG_PATH)
if not raw_config:
    sys.exit(1)


resolved_config, DEMO_SONGS_DIR, SRT_FILES_DIR = resolve_paths(raw_config, BASE_DIR)
if not resolved_config:
    print("יציאה עקב שגיאות בקונפיגורציה.")
    sys.exit(1)


ASSETS_DIR = resolved_config['paths']['assets_dir']
FONTS_DIR = resolved_config['paths']['fonts_dir']
OUTPUT_DIR = resolved_config['paths']['output_dir']
OUTPUT_FRAMES_DIR = resolved_config['paths']['output_frames_dir']


os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)
os.makedirs(DEMO_SONGS_DIR, exist_ok=True)
os.makedirs(SRT_FILES_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
# Frame dir is created by VideoCreator if needed


def select_song_from_list(json_path, songs_directory):
    if not os.path.exists(json_path):
        print(f"שגיאה: קובץ רשימת השירים '{json_path}' לא נמצא.")
        print("אנא צור קובץ 'song_list.json' בפורמט:")
        print('[{"name": "שם השיר 1", "artist": "שם הזמר 1", "youtube_url": "קישור_יוטיוב_1"}, ...]')
        return None, None, None, None

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            songs = json.load(f)
    except json.JSONDecodeError:
        print(f"שגיאה: קובץ ה-JSON '{json_path}' אינו תקין.")
        return None, None, None, None
    except Exception as e:
        print(f"שגיאה בטעינת קובץ ה-JSON '{json_path}': {e}")
        return None, None, None, None

    if not isinstance(songs, list) or not songs:
        print(f"שגיאה: קובץ ה-JSON '{json_path}' ריק או שאינו מכיל רשימה תקינה.")
        return None, None, None, None

    valid_songs = []
    print("\n--- רשימת שירים זמינים ---")
    for i, song in enumerate(songs):
        if isinstance(song, dict) and 'name' in song and 'youtube_url' in song:
            artist_display = f" - {song.get('artist', 'לא ידוע')}" if song.get('artist') else ""
            print(f"{len(valid_songs) + 1}. {song['name']}{artist_display}")
            valid_songs.append(song)
        else:
            print(f"אזהרה: דילוג על רשומה לא תקינה באינדקס {i} בקובץ ה-JSON.")
    print("-------------------------")

    if not valid_songs:
         print("שגיאה: לא נמצאו שירים תקינים ברשימה.")
         return None, None, None, None

    while True:
        try:
            choice_str = input(f"הזן את מספר השיר שברצונך לעבד (1-{len(valid_songs)}), או 'q' ליציאה: ")
            if choice_str.lower() == 'q':
                 print("יציאה לפי בקשת המשתמש.")
                 return None, None, None, None
            choice = int(choice_str)
            if 1 <= choice <= len(valid_songs):
                selected_song = valid_songs[choice - 1]
                song_name = selected_song['name']
                youtube_url = selected_song['youtube_url']
                artist_name = selected_song.get('artist')

                expected_mp3_filename = f"{song_name}.mp3"
                expected_mp3_path = os.path.join(songs_directory, expected_mp3_filename)

                print(f"\nבחרת: {song_name}")
                if artist_name:
                     print(f"זמר: {artist_name}")
                print(f"קישור YouTube: {youtube_url}")
                print(f"נתיב MP3 צפוי: {expected_mp3_path}")

                if not os.path.exists(expected_mp3_path):
                    print(f"\n!!! שגיאה קריטית !!!")
                    print(f"קובץ האודיו הצפוי '{expected_mp3_path}' עבור השיר '{song_name}' לא נמצא בתיקייה '{songs_directory}'.")
                    print("ודא שהקובץ קיים עם השם המדויק (כולל סיומת mp3) והנתיב הנכון.")
                    print("אנא בחר שיר אחר או תקן את שם הקובץ / מיקומו ונסה שנית.")
                    continue
                else:
                    return song_name, artist_name, youtube_url, expected_mp3_path
            else:
                print(f"בחירה לא חוקית. אנא הזן מספר בין 1 ל-{len(valid_songs)} או 'q'.")
        except ValueError:
            print("קלט לא תקין. אנא הזן מספר בלבד או 'q'.")
        except KeyboardInterrupt:
             print("\nיציאה לפי בקשת המשתמש.")
             return None, None, None, None


def main():
    print("--- יוצר וידאו כתוביות YouTube (מוגדר מ-JSON) ---")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("שגיאה: משתנה הסביבה 'GEMINI_API_KEY' לא הוגדר.")
        print("אנא הגדר את המפתח והפעל את הסקריפט מחדש.")
        sys.exit(1)

    selected_song_name, selected_artist_name, youtube_link, mp3_file_path = select_song_from_list(SONG_LIST_JSON_PATH, DEMO_SONGS_DIR)
    if not selected_song_name:
        print("לא נבחר שיר. יוצא מהתוכנית.")
        sys.exit(0)

    print("\n--- יצירה או טעינה של כתוביות ---")
    subtitle_generator = SubtitleGenerator(
        api_key=api_key,
        srt_output_dir=SRT_FILES_DIR,
        instructions_filepath=SYSTEM_INSTRUCTIONS_PATH
    )
    # Assuming english_subs is source and hebrew_subs is target
    source_subs, target_subs = subtitle_generator.generate_or_load_subtitles(youtube_link, mp3_file_path)

    if source_subs is None and target_subs is None:
        print("\nשגיאה קריטית: לא ניתן היה ליצור או לטעון כתוביות.")
        print("יוצא מהתוכנית.")
        sys.exit(1)
    elif source_subs is None:
        print("\nאזהרה: לא הופקו/נטענו כתוביות מקור (לדוגמה: אנגלית). ממשיך עם כתוביות יעד בלבד (אם קיימות).")
    elif target_subs is None:
        print("\nאזהרה: לא הופקו/נטענו כתוביות יעד (לדוגמה: עברית). ממשיך עם כתוביות מקור בלבד (אם קיימות).")
    elif not source_subs and not target_subs:
         print("\nאזהרה: שתי רשימות הכתוביות (מקור ויעד) ריקות. הוידאו ייווצר ללא כתוביות טקסט.")
    else:
        print("\nנתוני הכתוביות הוכנו בהצלחה.")

    print("\n--- יצירת הוידאו ---")
    try:
        video_creator = VideoCreator(resolved_config)

        output_base_name = os.path.splitext(os.path.basename(mp3_file_path))[0]

        created_video_path = video_creator.create_video(
            mp3_path=mp3_file_path,
            song_title_text=selected_song_name, # Use selected name
            artist_name_text=selected_artist_name, # Use selected artist
            source_subtitle_data=source_subs,   # Pass source subs
            target_subtitle_data=target_subs,   # Pass target subs
            output_video_filename_base=output_base_name
        )

        if created_video_path:
            print(f"\n--- התהליך הושלם בהצלחה! ---")
            print(f"הוידאו נשמר ב: {created_video_path}")
        else:
            print(f"\n--- התהליך נכשל במהלך יצירת הוידאו. ---")
            sys.exit(1)

    except FileNotFoundError as e:
        print(f"\nשגיאה קריטית: קובץ חיוני לא נמצא - {e}")
        print("ודא שקובצי הפונטים (כותרת, אמן, כתוביות מקור ויעד) ותמונות הרקע קיימים בנתיבים המוגדרים בקובץ הקונפיגורציה video_config.json והם תקינים.")
        sys.exit(1)
    except ValueError as e:
        print(f"\nשגיאה קריטית בהגדרות הקונפיגורציה: {e}")
        print("אנא בדוק את קובץ video_config.json, במיוחד את החלקים 'subtitle_style.source' ו-'subtitle_style.target'.")
        sys.exit(1)
    except KeyError as e:
         print(f"\nשגיאה קריטית: מפתח חסר בקובץ הקונפיגורציה video_config.json - {e}")
         print("אנא ודא שכל המפתחות הנדרשים קיימים בקובץ, כולל בתוך 'source' ו-'target' תחת 'subtitle_style'.")
         sys.exit(1)
    except Exception as e:
        print(f"\nשגיאה לא צפויה במהלך הגדרת או הרצת VideoCreator: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()