import os
import json
import sys
import traceback # Keep for potential errors

# Import the classes from the other files
from subtitle_generator import SubtitleGenerator
from video_creator import VideoCreator

# --- Configuration Loading ---
CONFIG_FILE_NAME = 'video_config.json'

def load_config(config_path):
    """Loads the JSON configuration file."""
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
    """Resolves relative paths in the config to absolute paths."""
    resolved_config = config.copy() # Don't modify original
    paths_cfg = resolved_config.get('paths', {})

    # Resolve main directories relative to base_dir
    assets_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('assets_rel', '../assets')))
    fonts_dir = os.path.join(assets_dir, paths_cfg.get('fonts_subdir', 'fonts'))
    output_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('output_rel', 'output')))
    output_frames_dir = os.path.join(output_dir, paths_cfg.get('output_frames_subdir', 'subtitle_frames'))
    demo_songs_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('demo_songs_rel', 'demo_songs')))
    json_files_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('json_files_rel', 'json_files')))

    resolved_config['paths'] = {
        'assets_dir': assets_dir,
        'fonts_dir': fonts_dir,
        'output_dir': output_dir,
        'output_frames_dir': output_frames_dir,
        'demo_songs_dir': demo_songs_dir,
        'json_files_dir': json_files_dir
    }

    # Resolve background image paths
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
        bg_config['intro_background_image_path'] = None # סמן כלא קיים

    resolved_config['background'] = bg_config # עדכון המילון בקונפיגורציה

    # --- הוספה: ולידציה לקיום artist_style (אופציונלי) ---
    if 'artist_style' not in resolved_config:
        print("אזהרה: הגדרות עיצוב 'artist_style' חסרות בקובץ הקונפיגורציה. שם הזמר לא יוצג.")
    # --- סוף הוספה ---

    return resolved_config, demo_songs_dir, json_files_dir

# --- Path Setup (Relative to this file) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, CONFIG_FILE_NAME)
SONG_LIST_JSON_PATH = os.path.join(BASE_DIR, 'song_list.json') # Keep this relative for now

# --- Load Configuration ---
raw_config = load_config(CONFIG_PATH)
if not raw_config:
    sys.exit(1)

# --- Resolve Paths ---
resolved_config, DEMO_SONGS_DIR, JSON_FILES_DIR = resolve_paths(raw_config, BASE_DIR)
# Extract other needed paths after resolution
ASSETS_DIR = resolved_config['paths']['assets_dir']
FONTS_DIR = resolved_config['paths']['fonts_dir']
OUTPUT_DIR = resolved_config['paths']['output_dir']
OUTPUT_FRAMES_DIR = resolved_config['paths']['output_frames_dir']

# --- Directory Creation ---
# Ensure all necessary directories exist based on resolved paths
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)
os.makedirs(DEMO_SONGS_DIR, exist_ok=True)
os.makedirs(JSON_FILES_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_FRAMES_DIR, exist_ok=True) # Ensure frame dir exists too

# --- Song Selection Function (Modified) ---
def select_song_from_list(json_path, songs_directory):
    """
    Loads a list of songs from a JSON file, prompts the user to select one,
    checks for the corresponding MP3 file, and returns details including the artist.
    Returns: tuple (song_name, artist_name, youtube_url, mp3_path) or (None, None, None, None)
    """
    if not os.path.exists(json_path):
        print(f"שגיאה: קובץ רשימת השירים '{json_path}' לא נמצא.")
        print("אנא צור קובץ 'song_list.json' בפורמט:")
        print('[{"name": "שם השיר 1", "artist": "שם הזמר 1", "youtube_url": "קישור_יוטיוב_1"}, ...]') # Updated example
        return None, None, None, None # <<< שינוי: החזרת 4 ערכים

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            songs = json.load(f)
    except json.JSONDecodeError:
        print(f"שגיאה: קובץ ה-JSON '{json_path}' אינו תקין.")
        return None, None, None, None # <<< שינוי
    except Exception as e:
        print(f"שגיאה בטעינת קובץ ה-JSON '{json_path}': {e}")
        return None, None, None, None # <<< שינוי

    if not isinstance(songs, list) or not songs:
        print(f"שגיאה: קובץ ה-JSON '{json_path}' ריק או שאינו מכיל רשימה תקינה.")
        return None, None, None, None # <<< שינוי

    valid_songs = []
    print("\n--- רשימת שירים זמינים ---")
    for i, song in enumerate(songs):
        # --- שינוי: בדיקה אם 'artist' קיים, אך לא חובה ---
        if isinstance(song, dict) and 'name' in song and 'youtube_url' in song:
            # נציג את שם הזמר אם קיים
            artist_display = f" - {song.get('artist', 'לא ידוע')}" if song.get('artist') else ""
            print(f"{len(valid_songs) + 1}. {song['name']}{artist_display}")
            valid_songs.append(song)
        else:
            print(f"אזהרה: דילוג על רשומה לא תקינה באינדקס {i} בקובץ ה-JSON.")
    print("-------------------------")

    if not valid_songs:
         print("שגיאה: לא נמצאו שירים תקינים ברשימה.")
         return None, None, None, None # <<< שינוי

    while True:
        try:
            choice_str = input(f"הזן את מספר השיר שברצונך לעבד (1-{len(valid_songs)}), או 'q' ליציאה: ")
            if choice_str.lower() == 'q':
                 print("יציאה לפי בקשת המשתמש.")
                 return None, None, None, None # <<< שינוי
            choice = int(choice_str)
            if 1 <= choice <= len(valid_songs):
                selected_song = valid_songs[choice - 1]
                song_name = selected_song['name']
                youtube_url = selected_song['youtube_url']
                # --- הוספה: קבלת שם הזמר, אם קיים ---
                artist_name = selected_song.get('artist') # יחזיר None אם לא קיים
                # --------------------------------------

                expected_mp3_filename = f"{song_name}.mp3"
                expected_mp3_path = os.path.join(songs_directory, expected_mp3_filename) # songs_directory is passed in

                print(f"\nבחרת: {song_name}")
                if artist_name:
                     print(f"זמר: {artist_name}") # הצגת הזמר אם יש
                print(f"קישור YouTube: {youtube_url}")
                print(f"נתיב MP3 צפוי: {expected_mp3_path}")

                if not os.path.exists(expected_mp3_path):
                    print(f"\n!!! שגיאה קריטית !!!")
                    print(f"קובץ האודיו הצפוי '{expected_mp3_path}' עבור השיר '{song_name}' לא נמצא בתיקייה '{songs_directory}'.")
                    print("ודא שהקובץ קיים עם השם המדויק (כולל סיומת mp3) והנתיב הנכון.")
                    print("אנא בחר שיר אחר או תקן את שם הקובץ / מיקומו ונסה שנית.")
                    continue # Go back to asking for input
                else:
                    # Found the MP3 file
                    return song_name, artist_name, youtube_url, expected_mp3_path # <<< שינוי: החזרת שם הזמר
            else:
                print(f"בחירה לא חוקית. אנא הזן מספר בין 1 ל-{len(valid_songs)} או 'q'.")
        except ValueError:
            print("קלט לא תקין. אנא הזן מספר בלבד או 'q'.")
        except KeyboardInterrupt:
             print("\nיציאה לפי בקשת המשתמש.")
             return None, None, None, None # <<< שינוי


# --- Main Execution Logic (Modified) ---
def main():
    print("--- יוצר וידאו כתוביות YouTube (מוגדר מ-JSON) ---")

    # API Key Check
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("שגיאה: משתנה הסביבה 'GEMINI_API_KEY' לא הוגדר.")
        print("אנא הגדר את המפתח והפעל את הסקריפט מחדש.")
        sys.exit(1)

    # --- שינוי: קבלת שם הזמר מהפונקציה ---
    selected_song_name, selected_artist_name, youtube_link, mp3_file_path = select_song_from_list(SONG_LIST_JSON_PATH, DEMO_SONGS_DIR)
    if not selected_song_name:
        print("לא נבחר שיר. יוצא מהתוכנית.")
        sys.exit(0)
    # --- סוף שינוי ---

    # Subtitle Generation (Uses resolved JSON_FILES_DIR)
    print("\n--- יצירה או טעינה של כתוביות ---")
    subtitle_generator = SubtitleGenerator(api_key=api_key, json_output_dir=JSON_FILES_DIR)
    # אין שינוי בחלק הזה, subtitle_generator לא מושפע
    english_subs, hebrew_subs = subtitle_generator.generate_or_load_subtitles(youtube_link, mp3_file_path)

    # Check subtitle results (logic unchanged)
    if english_subs is None and hebrew_subs is None:
        print("\nשגיאה קריטית: לא ניתן היה ליצור או לטעון כתוביות.")
        print("יוצא מהתוכנית.")
        sys.exit(1)
    elif english_subs is None:
        print("\nאזהרה: לא הופקו/נטענו כתוביות באנגלית. ממשיך עם עברית בלבד (אם קיימות).")
    elif hebrew_subs is None:
        print("\nאזהרה: לא הופקו/נטענו כתוביות בעברית. ממשיך עם אנגלית בלבד (אם קיימות).")
    elif not english_subs and not hebrew_subs:
         print("\nאזהרה: שתי רשימות הכתוביות (אנגלית ועברית) ריקות. הוידאו ייווצר ללא כתוביות טקסט.")
    else:
        print("\nנתוני הכתוביות הוכנו בהצלחה.")

    # Video Creation
    print("\n--- יצירת הוידאו ---")
    try:
        # Instantiate VideoCreator with the *resolved* configuration
        video_creator = VideoCreator(resolved_config)

        output_base_name = os.path.splitext(os.path.basename(mp3_file_path))[0]
        # --- שינוי: העברת שם הזמר לפונקציה ---
        created_video_path = video_creator.create_video(
            mp3_path=mp3_file_path,
            song_title_text=selected_song_name,
            artist_name_text=selected_artist_name, # <-- פרמטר חדש
            english_subtitle_data=english_subs,
            hebrew_subtitle_data=hebrew_subs,
            output_video_filename_base=output_base_name
        )
        # --- סוף שינוי ---

        if created_video_path:
            print(f"\n--- התהליך הושלם בהצלחה! ---")
            print(f"הוידאו נשמר ב: {created_video_path}")
        else:
            print(f"\n--- התהליך נכשל במהלך יצירת הוידאו. ---")
            sys.exit(1)

    except FileNotFoundError as e:
        print(f"\nשגיאה קריטית: קובץ חיוני לא נמצא - {e}")
        print("ודא שקובץ הפונט (כולל פונט הזמר אם הוגדר) ותמונות הרקע קיימים בנתיבים המוגדרים בקובץ הקונפיגורציה video_config.json והם תקינים.") # עדכון הודעת שגיאה
        sys.exit(1)
    except KeyError as e:
         print(f"\nשגיאה קריטית: מפתח חסר בקובץ הקונפיגורציה video_config.json - {e}")
         print("אנא ודא שכל המפתחות הנדרשים קיימים בקובץ, כולל 'artist_style' אם בכוונתך להשתמש בו.") # עדכון הודעת שגיאה
         sys.exit(1)
    except Exception as e:
        print(f"\nשגיאה לא צפויה במהלך הגדרת או הרצת VideoCreator: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()