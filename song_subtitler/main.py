import os
import json
import sys
import traceback
import argparse
import re
import urllib.parse # Needed for YouTube ID extraction

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

    # --- נכסים (Assets) --- נשאר זהה, נטען מ-assets_rel חיצוני
    assets_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('assets_rel', '../assets')))
    fonts_dir = os.path.join(assets_dir, paths_cfg.get('fonts_subdir', 'fonts'))

    # --- נתונים (Data) --- חדש, נטען מ-data_rel פנימי
    data_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('data_rel', 'data'))) # נתיב לתיקיית data
    songs_dir = os.path.join(data_dir, paths_cfg.get('songs_subdir', 'songs')) # נתיב ל- data/songs
    lyrics_dir = os.path.join(data_dir, paths_cfg.get('lyrics_subdir', 'lyrics')) # נתיב ל- data/lyrics

    # --- פלט (Output) --- נשאר זהה
    output_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('output_rel', 'output')))
    output_frames_dir = os.path.join(output_dir, paths_cfg.get('output_frames_subdir', 'subtitle_frames'))
    srt_files_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('srt_files_rel', 'srt_files')))

    # שמירת הנתיבים המוחלטים בקונפיגורציה הפנימית
    resolved_config['paths'] = {
        'assets_dir': assets_dir,
        'fonts_dir': fonts_dir,
        'data_dir': data_dir,        # ***חדש***
        'songs_dir': songs_dir,      # ***חדש*** (מחליף demo_songs_dir)
        'lyrics_dir': lyrics_dir,    # ***נשאר***
        'output_dir': output_dir,
        'output_frames_dir': output_frames_dir,
        'srt_files_dir': srt_files_dir
    }

    # --- רקעים --- נשאר זהה, נטען מ-assets_dir
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

    # --- בדיקות נוספות --- נשאר זהה
    if 'artist_style' not in resolved_config:
        print("אזהרה: הגדרות עיצוב 'artist_style' חסרות בקובץ הקונפיגורציה. שם הזמר לא יוצג.")
    sub_style = resolved_config.get('subtitle_style', {})
    if 'source' not in sub_style or 'target' not in sub_style:
        print("שגיאת קונפיגורציה קריטית: 'subtitle_style' חייב להכיל קטעי 'source' ו-'target'.")
        return None, None, None # שינוי: החזרת None עבור הנתיבים החדשים
    for role in ['source', 'target']:
        role_style = sub_style[role]
        missing_keys = [key for key in ['font_name', 'font_size', 'color'] if key not in role_style]
        if missing_keys:
            print(f"שגיאת קונפיגורציה קריטית: חלק '{role}' ב-'subtitle_style' חסר את המפתחות הבאים: {', '.join(missing_keys)}")
            return None, None, None # שינוי: החזרת None עבור הנתיבים החדשים

    # החזרת הנתיבים הרלוונטיים
    return resolved_config, songs_dir, srt_files_dir, lyrics_dir # שינוי: החזרת songs_dir במקום demo_songs_dir


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, CONFIG_DIR, CONFIG_FILE_NAME)
SONG_LIST_JSON_PATH = os.path.join(BASE_DIR, CONFIG_DIR, SONG_LIST_FILE_NAME)

SYSTEM_INSTRUCTIONS_FILE_NAME = 'system_instructions.yaml'
SYSTEM_INSTRUCTIONS_PATH = os.path.join(BASE_DIR, CONFIG_DIR, SYSTEM_INSTRUCTIONS_FILE_NAME)


raw_config = load_config(CONFIG_PATH)
if not raw_config:
    sys.exit(1)

# שינוי: קבלת songs_dir במקום demo_songs_dir
resolved_config, SONGS_DIR, SRT_FILES_DIR, LYRICS_DIR = resolve_paths(raw_config, BASE_DIR)
if not resolved_config:
    print("יציאה עקב שגיאות בקונפיגורציה.")
    sys.exit(1)

# קבלת הנתיבים מהקונפיגורציה המעודכנת
ASSETS_DIR = resolved_config['paths']['assets_dir']
FONTS_DIR = resolved_config['paths']['fonts_dir']
OUTPUT_DIR = resolved_config['paths']['output_dir']
OUTPUT_FRAMES_DIR = resolved_config['paths']['output_frames_dir']
# DATA_DIR = resolved_config['paths']['data_dir'] # אפשר להשתמש אם צריך גישה לכל תיקיית data

# יצירת תיקיות (אם לא קיימות)
os.makedirs(ASSETS_DIR, exist_ok=True) # עדיין יוצר את תיקיית assets אם היא לא קיימת, למרות שהיא חיצונית
os.makedirs(FONTS_DIR, exist_ok=True) # יחסי ל-assets
os.makedirs(SONGS_DIR, exist_ok=True)   # ***חדש***: יוצר את data/songs
os.makedirs(LYRICS_DIR, exist_ok=True)  # ***נשאר***: יוצר את data/lyrics
os.makedirs(SRT_FILES_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_song_list(json_path):
    """Loads the song list from the JSON file."""
    if not os.path.exists(json_path):
        print(f"שגיאה: קובץ רשימת השירים '{json_path}' לא נמצא.")
        print("אנא צור קובץ 'song_list.json' בפורמט:")
        print('[{"name": "שם השיר 1", "artist": "שם הזמר 1", "youtube_url": "קישור_יוטיוב_1", "lyrics_file": "optional/path/lyrics.txt"}, ...]')
        return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            songs = json.load(f)
        if not isinstance(songs, list):
            print(f"שגיאה: קובץ ה-JSON '{json_path}' אינו מכיל רשימה תקינה.")
            return None
        return songs
    except json.JSONDecodeError:
        print(f"שגיאה: קובץ ה-JSON '{json_path}' אינו תקין.")
        return None
    except Exception as e:
        print(f"שגיאה בטעינת קובץ ה-JSON '{json_path}': {e}")
        return None

def save_song_list(json_path, songs):
    """Saves the song list back to the JSON file."""
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(songs, f, ensure_ascii=False, indent=2)
        print(f"רשימת השירים עודכנה ונשמרה ב: '{json_path}'")
        return True
    except Exception as e:
        print(f"שגיאה בשמירת קובץ ה-JSON '{json_path}': {e}")
        return False

def get_youtube_video_id(url):
    """Extracts YouTube video ID from URL."""
    if not url:
        return None
    try:
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.hostname in ('youtu.be',):
            return parsed_url.path[1:]
        if parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
            if parsed_url.path == '/watch':
                query_params = urllib.parse.parse_qs(parsed_url.query)
                return query_params.get('v', [None])[0]
            if parsed_url.path.startswith('/embed/'):
                return parsed_url.path.split('/')[2]
            if parsed_url.path.startswith('/v/'):
                return parsed_url.path.split('/')[2]
    except Exception:
        pass # Ignore parsing errors, return None
    return None

def find_song(songs, identifier):
    """Finds a song by index, YouTube ID, or name."""
    # Try by index (1-based)
    try:
        index = int(identifier)
        if 1 <= index <= len(songs):
            return songs[index - 1]
    except ValueError:
        pass # Not an integer index

    # Try by YouTube Video ID
    identifier_lower = identifier.lower()
    matches_id = []
    for song in songs:
        if 'youtube_url' in song:
            video_id = get_youtube_video_id(song['youtube_url'])
            if video_id and video_id.lower() == identifier_lower:
                matches_id.append(song)
    if len(matches_id) == 1:
        return matches_id[0]
    elif len(matches_id) > 1:
        print(f"אזהרה: נמצאו מספר שירים עם אותו YouTube ID: '{identifier}'. לא ניתן לבחור באופן חד משמעי.")
        return None # Ambiguous

    # Try by Name (case-insensitive)
    matches_name = []
    for song in songs:
        if 'name' in song and song['name'].lower() == identifier_lower:
            matches_name.append(song)
    if len(matches_name) == 1:
        return matches_name[0]
    elif len(matches_name) > 1:
        print(f"אזהרה: נמצאו מספר שירים עם אותו שם: '{identifier}'. נסה לציין זמר או להשתמש ב-ID/אינדקס.")
        return None # Ambiguous

    return None # Not found

def select_song_interactive(songs):
    """Handles interactive song selection from the list."""
    valid_songs = []
    print("\n--- רשימת שירים זמינים ---")
    for i, song in enumerate(songs):
        if isinstance(song, dict) and 'name' in song and 'youtube_url' in song:
            artist_display = f" - {song.get('artist', 'לא ידוע')}" if song.get('artist') else ""
            lyrics_indicator = "[עם מילים]" if song.get('lyrics_file') else ""
            print(f"{len(valid_songs) + 1}. {song['name']}{artist_display} {lyrics_indicator}")
            valid_songs.append(song)
        else:
            print(f"אזהרה: דילוג על רשומה לא תקינה באינדקס {i} בקובץ ה-JSON.")
    print("-------------------------")

    if not valid_songs:
         print("שגיאה: לא נמצאו שירים תקינים ברשימה.")
         return None

    while True:
        try:
            choice_str = input(f"הזן את מספר השיר שברצונך לעבד (1-{len(valid_songs)}), או 'q' ליציאה: ")
            if choice_str.lower() == 'q':
                 print("יציאה לפי בקשת המשתמש.")
                 return None
            choice = int(choice_str)
            if 1 <= choice <= len(valid_songs):
                selected_song = valid_songs[choice - 1]
                return selected_song
            else:
                print(f"בחירה לא חוקית. אנא הזן מספר בין 1 ל-{len(valid_songs)} או 'q'.")
        except ValueError:
            print("קלט לא תקין. אנא הזן מספר בלבד או 'q'.")
        except KeyboardInterrupt:
             print("\nיציאה לפי בקשת המשתמש.")
             return None

def validate_and_get_song_details(selected_song, songs_directory, lyrics_directory, cli_lyrics_path=None, cli_language=None):
    """Validates selected song, checks MP3, prepares details."""
    if not selected_song or not isinstance(selected_song, dict):
        print("שגיאה פנימית: נתוני השיר שנבחר אינם תקינים.")
        return None, None, None, None, None, None # Added None for language

    song_name = selected_song.get('name')
    youtube_url = selected_song.get('youtube_url')
    artist_name = selected_song.get('artist')
    lyrics_rel_path = selected_song.get('lyrics_file') # From JSON
    language_from_json = selected_song.get('language', 'en').lower() # Default to 'en' if missing

    if not song_name or not youtube_url:
        print(f"שגיאה: רשומת השיר אינה שלמה (חסר שם או קישור YouTube): {selected_song}")
        return None, None, None, None, None, None # Added None for language

    # Determine source language: CLI override > JSON value > Default 'en'
    source_language = 'en' # Default
    if cli_language and cli_language.lower() in ['en', 'yi']:
        source_language = cli_language.lower()
        print(f"  שפת מקור נקבעה מה-CLI: {'אנגלית' if source_language == 'en' else 'יידיש'}")
    elif language_from_json in ['en', 'yi']:
        source_language = language_from_json
        print(f"  שפת מקור נקבעה מה-JSON: {'אנגלית' if source_language == 'en' else 'יידיש'}")
    else:
        print(f"  שפת מקור נקבעה כברירת מחדל: {'אנגלית' if source_language == 'en' else 'יידיש'}")


    # --- MP3 Path ---
    expected_mp3_filename = f"{song_name}.mp3"
    expected_mp3_path = os.path.join(songs_directory, expected_mp3_filename)

    print(f"\nפרטי השיר שנבחר:")
    print(f"  שם: {song_name}")
    if artist_name:
         print(f"  זמר: {artist_name}")
    print(f"  קישור YouTube: {youtube_url}")
    print(f"  שפת מקור מזוהה: {'אנגלית' if source_language == 'en' else 'יידיש'}") # Display identified language
    print(f"  נתיב MP3 צפוי: {expected_mp3_path}")

    if not os.path.exists(expected_mp3_path):
        print(f"\n!!! שגיאה קריטית !!!")
        print(f"קובץ האודיו הצפוי '{expected_mp3_path}' עבור השיר '{song_name}' לא נמצא בתיקייה '{songs_directory}'.")
        print("ודא שהקובץ קיים עם השם המדויק (כולל סיומת mp3) והנתיב הנכון.")
        return None, None, None, None, None, None # Added None for language

    # --- Lyrics Path & Content ---
    lyrics_content = None
    lyrics_source_path = None

    # Priority: CLI argument
    if cli_lyrics_path:
        if os.path.isabs(cli_lyrics_path):
            lyrics_source_path = cli_lyrics_path
        else:
            # Assume relative to script execution OR potentially assets/lyrics?
            # Let's try relative to execution first, then assets/lyrics
            if os.path.exists(cli_lyrics_path):
                 lyrics_source_path = os.path.abspath(cli_lyrics_path)
            else:
                 potential_path = os.path.join(lyrics_directory, cli_lyrics_path)
                 if os.path.exists(potential_path):
                     lyrics_source_path = potential_path
                 else:
                      print(f"אזהרה: קובץ המילים שצויין ב-CLI '{cli_lyrics_path}' לא נמצא (לא בנתיב יחסי ולא בתיקיית המילים).")
        print(f"  מנסה לטעון מילים מקובץ שהוגדר ב-CLI: {lyrics_source_path}")
    # Fallback: JSON definition
    elif lyrics_rel_path:
        # Assume relative to lyrics_directory (which is relative to assets)
        lyrics_source_path = os.path.join(lyrics_directory, lyrics_rel_path)
        print(f"  מנסה לטעון מילים מקובץ שהוגדר ב-JSON: {lyrics_source_path}")
    else:
        print("  לא הוגדר קובץ מילים עבור שיר זה (לא ב-CLI ולא ב-JSON).")

    if lyrics_source_path:
        if os.path.exists(lyrics_source_path):
            try:
                with open(lyrics_source_path, 'r', encoding='utf-8') as f:
                    lyrics_content = f.read()
                print(f"  תוכן המילים נטען בהצלחה מ: '{lyrics_source_path}'")
            except Exception as e:
                print(f"  אזהרה: שגיאה בקריאת קובץ המילים '{lyrics_source_path}': {e}")
        else:
            print(f"  אזהרה: קובץ המילים '{lyrics_source_path}' לא נמצא.")

    return song_name, artist_name, youtube_url, expected_mp3_path, lyrics_content, source_language # Return language


def main():
    parser = argparse.ArgumentParser(description="יוצר סרטוני כתוביות YouTube עם Gemini API.")

    # Group for selecting/adding songs
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-s", "--select", metavar="IDENTIFIER",
                       help="בחר שיר לעיבוד לפי מספר אינדקס (מהרשימה שתוצג), YouTube Video ID, או שם השיר המדויק (case-insensitive).")
    group.add_argument("--add", action='store_true',
                       help="הוסף שיר חדש לרשימה ועבד אותו. דורש שימוש ב--name ו--url (ו--artist אופציונלי).")

    # Arguments for adding a new song (used only if --add is specified)
    parser.add_argument("--name", help="שם השיר להוספה (חובה עם --add).")
    parser.add_argument("--artist", help="שם הזמר להוספה (אופציונלי עם --add).")
    parser.add_argument("--url", help="קישור YouTube של השיר להוספה (חובה עם --add).")

    # General options
    parser.add_argument("--lyrics-file", metavar="PATH",
                        help="נתיב לקובץ טקסט המכיל את מילות השיר (עוקף הגדרה ב-JSON אם קיימת).")
    parser.add_argument("-f", "--force-regenerate", action="store_true",
                        help="אלץ יצירה מחדש של קבצי הכתוביות (SRT), גם אם הם קיימים.")
    parser.add_argument("-l", "--language", choices=['en', 'yi'],
                        help="ציין במפורש את שפת המקור של השיר ('en' לאנגלית, 'yi' ליידיש). עוקף הגדרה ב-JSON.")


    args = parser.parse_args()

    print("--- יוצר וידאו כתוביות YouTube ---")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("שגיאה: משתנה הסביבה 'GEMINI_API_KEY' לא הוגדר.")
        print("אנא הגדר את המפתח והפעל את הסקריפט מחדש.")
        sys.exit(1)

    songs = load_song_list(SONG_LIST_JSON_PATH)
    if songs is None:
        sys.exit(1) # Error message already printed by load_song_list

    selected_song_data = None
    cli_lyrics_path = args.lyrics_file # Get lyrics path from CLI args
    cli_language_override = args.language # Get language override from CLI

    # --- Handle Song Selection/Addition ---
    if args.add:
        # Add and process a new song
        if not args.name or not args.url:
            parser.error("--add דורש ציון של --name ו--url.")

        new_song = {
            "name": args.name.strip(),
            "artist": args.artist.strip() if args.artist else None,
            "youtube_url": args.url.strip(),
            "language": cli_language_override if cli_language_override else 'en' # Set language if provided via CLI, else default to 'en'
        }

        # --- הוספת נתיב מילים ל-JSON אם סופק ב-CLI ---
        if args.lyrics_file:
            user_lyrics_path = args.lyrics_file  # הנתיב שהמשתמש הזין
            lyrics_dir_abs_path = LYRICS_DIR     # הנתיב האבסולוטי לתיקיית המילים

            # נבנה את הנתיב המלא הצפוי, בהנחה שהקלט יחסי לתיקיית המילים
            expected_abs_path_in_lyrics_dir = os.path.join(lyrics_dir_abs_path, user_lyrics_path)

            # בדיקה 1: האם הקובץ קיים בנתיב הצפוי *בתוך* תיקיית המילים?
            if os.path.exists(expected_abs_path_in_lyrics_dir):
                # כן, נמצא במיקום הנכון (בין אם הקלט היה יחסי או אבסולוטי בתוך התיקייה)
                # נשמור את הנתיב המקורי שהמשתמש נתן (יחסי לתיקיית המילים)
                relative_path_to_save = user_lyrics_path.replace(os.sep, '/') # נוודא שימוש ב- /
                new_song['lyrics_file'] = relative_path_to_save
                print(f"  נתיב קובץ המילים '{relative_path_to_save}' (יחסית לתיקיית המילים) ישמר ב-JSON.")

            # בדיקה 2: אם לא נמצא בתיקיית המילים, האם הוא קיים במקום אחר (כנתיב אבסולוטי או יחסי ל-CWD)?
            elif os.path.exists(user_lyrics_path):
                # כן, אבל לא במיקום המנוהל
                print(f"  אזהרה: קובץ המילים '{user_lyrics_path}' נמצא, אך אינו בתוך תיקיית המילים המוגדרת ('{lyrics_dir_abs_path}').")
                print(f"           הקישור לא ישמר אוטומטית ב-song_list.json. ניתן להשתמש ב--lyrics-file בכל הרצה או לעדכן ידנית.")

            # ברירת מחדל: הקובץ לא נמצא באף אחד מהמיקומים הרלוונטיים
            else:
                 print(f"  אזהרה: קובץ המילים שצויין '{user_lyrics_path}' לא נמצא (לא בתיקיית המילים ולא בנתיב שצוין). לא ניתן לקשר אותו ב-JSON.")

        # Check if song already exists (by URL is usually more unique)
        existing_song = None
        for song in songs:
            if song.get('youtube_url') == new_song['youtube_url']:
                existing_song = song
                break
        if existing_song:
             print(f"אזהרה: שיר עם ה-URL '{new_song['youtube_url']}' כבר קיים ברשימה. משתמש בנתונים הקיימים.")
             selected_song_data = existing_song
        else:
            print(f"מוסיף שיר חדש לרשימה: '{new_song['name']}'")
            songs.append(new_song)
            if save_song_list(SONG_LIST_JSON_PATH, songs):
                selected_song_data = new_song
            else:
                print("שגיאה בשמירת הרשימה המעודכנת, לא ניתן להמשיך.")
                sys.exit(1)

    elif args.select:
        # Select song using identifier from CLI
        print(f"מחפש שיר לפי מזהה: '{args.select}'...")
        selected_song_data = find_song(songs, args.select)
        if selected_song_data is None:
             print(f"שגיאה: לא נמצא שיר התואם למזהה '{args.select}' או שהמזהה אינו חד משמעי.")
             sys.exit(1)

    else:
        # Interactive selection
        selected_song_data = select_song_interactive(songs)
        if selected_song_data is None:
            print("לא נבחר שיר. יוצא מהתוכנית.")
            sys.exit(0)

    # --- Validate selected song and get details ---
    if selected_song_data is None:
         print("שגיאה: לא נבחרו נתוני שיר תקינים.")
         sys.exit(1)

    song_name, artist_name, youtube_link, mp3_file_path, lyrics_content, source_language = validate_and_get_song_details(
        selected_song_data, SONGS_DIR, LYRICS_DIR, cli_lyrics_path, cli_language_override # Pass CLI language override
    )


    if not all([song_name, youtube_link, mp3_file_path]):
        print("שגיאה באימות פרטי השיר או מציאת קובץ MP3. יוצא מהתוכנית.")
        sys.exit(1)

    # --- Subtitle Generation/Loading ---
    print("\n--- יצירה או טעינה של כתוביות ---")
    if args.force_regenerate:
        print("שים לב: יצירה מחדש של הכתוביות נכפתה באמצעות '--force-regenerate'.")

    subtitle_generator = SubtitleGenerator(
        api_key=api_key,
        srt_output_dir=SRT_FILES_DIR,
        instructions_filepath=SYSTEM_INSTRUCTIONS_PATH
    )

    source_subs, target_subs = subtitle_generator.generate_or_load_subtitles(
        source_language=source_language, # Pass the determined source language
        song_name=song_name, # Pass song name for filename
        youtube_url=youtube_link,
        mp3_audio_path=mp3_file_path,
        lyrics_content=lyrics_content, # Pass lyrics content if loaded
        force_regenerate=args.force_regenerate # Pass force flag
    )

    if source_subs is None and target_subs is None:
        print("\nשגיאה קריטית: לא ניתן היה ליצור או לטעון כתוביות.")
        print("יוצא מהתוכנית.")
        sys.exit(1)
    elif source_subs is None:
        print(f"\nאזהרה: לא הופקו/נטענו כתוביות מקור ({'אנגלית' if source_language == 'en' else 'יידיש'}). ממשיך עם כתוביות יעד בלבד (אם קיימות).")
    elif target_subs is None:
        print("\nאזהרה: לא הופקו/נטענו כתוביות יעד (עברית). ממשיך עם כתוביות מקור בלבד (אם קיימות).")
    elif not source_subs and not target_subs:
         print("\nאזהרה: שתי רשימות הכתוביות (מקור ויעד) ריקות. הוידאו ייווצר ללא כתוביות טקסט.")
    else:
        print("\nנתוני הכתוביות הוכנו בהצלחה.")

    # --- Video Creation ---
    print("\n--- יצירת הוידאו ---")
    try:
        video_creator = VideoCreator(resolved_config)

        output_base_name = os.path.splitext(os.path.basename(mp3_file_path))[0]

        created_video_path = video_creator.create_video(
            mp3_path=mp3_file_path,
            song_title_text=song_name, # Use selected name
            artist_name_text=artist_name, # Use selected artist
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
