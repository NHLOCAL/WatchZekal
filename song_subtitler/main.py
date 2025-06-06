import os
import json
import sys
import traceback
import argparse
import re
import urllib.parse
import glob
import shutil


from video_maker.subtitle_generator import SubtitleGenerator
from video_maker.video_creator import VideoCreator
from video_maker.json_to_srt import convert_json_to_srt as convert_json_content_to_srt_string

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


    data_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('data_rel', 'data')))
    songs_dir = os.path.join(data_dir, paths_cfg.get('songs_subdir', 'songs'))
    lyrics_dir = os.path.join(data_dir, paths_cfg.get('lyrics_subdir', 'lyrics'))
    json_files_dir = os.path.join(data_dir, paths_cfg.get('json_files_subdir', 'json_files'))


    output_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('output_rel', 'output')))
    output_frames_dir = os.path.join(output_dir, paths_cfg.get('output_frames_subdir', 'subtitle_frames'))
    srt_files_dir = os.path.abspath(os.path.join(base_dir, paths_cfg.get('srt_files_rel', 'srt_files')))

    resolved_config['paths'] = {
        'assets_dir': assets_dir,
        'fonts_dir': fonts_dir,
        'data_dir': data_dir,
        'songs_dir': songs_dir,
        'lyrics_dir': lyrics_dir,
        'json_files_dir': json_files_dir,
        'output_dir': output_dir,
        'output_frames_dir': output_frames_dir,
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
        print("אזהרה: הגדרות עיצוב 'artist_style' חסרות בקובץ הקונפיגורציה. שם הזמר לא יוצג (אלא אם כן נבחרה כותרת משנה בעברית).")
    sub_style = resolved_config.get('subtitle_style', {})
    if 'source' not in sub_style or 'target' not in sub_style:
        print("שגיאת קונפיגורציה קריטית: 'subtitle_style' חייב להכיל קטעי 'source' ו-'target'.")
        return None, None, None, None, None
    for role in ['source', 'target']:
        role_style = sub_style[role]
        missing_keys = [key for key in ['font_name', 'font_size', 'color'] if key not in role_style]
        if missing_keys:
            print(f"שגיאת קונפיגורציה קריטית: חלק '{role}' ב-'subtitle_style' חסר את המפתחות הבאים: {', '.join(missing_keys)}")
            return None, None, None, None, None

    return resolved_config, songs_dir, srt_files_dir, lyrics_dir, json_files_dir


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, CONFIG_DIR, CONFIG_FILE_NAME)
SONG_LIST_JSON_PATH = os.path.join(BASE_DIR, CONFIG_DIR, SONG_LIST_FILE_NAME)
SYSTEM_INSTRUCTIONS_FILE_NAME = 'system_instructions.yaml'
SYSTEM_INSTRUCTIONS_PATH = os.path.join(BASE_DIR, CONFIG_DIR, SYSTEM_INSTRUCTIONS_FILE_NAME)

raw_config = load_config(CONFIG_PATH)
if not raw_config:
    sys.exit(1)

resolved_config, SONGS_DIR, SRT_FILES_DIR, LYRICS_DIR, JSON_FILES_DIR = resolve_paths(raw_config, BASE_DIR)
if not resolved_config:
    print("יציאה עקב שגיאות בקונפיגורציה.")
    sys.exit(1)

ASSETS_DIR = resolved_config['paths']['assets_dir']
FONTS_DIR = resolved_config['paths']['fonts_dir']
OUTPUT_DIR = resolved_config['paths']['output_dir']
OUTPUT_FRAMES_DIR = resolved_config['paths']['output_frames_dir']

os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)
os.makedirs(SONGS_DIR, exist_ok=True)
os.makedirs(LYRICS_DIR, exist_ok=True)
os.makedirs(JSON_FILES_DIR, exist_ok=True)
os.makedirs(SRT_FILES_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_song_list(json_path):
    if not os.path.exists(json_path):
        print(f"מידע: קובץ רשימת השירים '{json_path}' לא נמצא. יוצר קובץ חדש.")
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            return [] # Return an empty list to continue
        except Exception as e:
            print(f"שגיאה: לא ניתן היה ליצור את קובץ רשימת השירים '{json_path}': {e}")
            return None # Fail if we can't create the file
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            # Handle empty file which is not valid JSON
            content = f.read()
            if not content.strip():
                print(f"אזהרה: קובץ רשימת השירים '{json_path}' קיים אך ריק. מתייחס אליו כרשימה ריקה.")
                return []
            songs = json.loads(content)

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
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(songs, f, ensure_ascii=False, indent=2)
        print(f"רשימת השירים עודכנה ונשמרה ב: '{json_path}'")
        return True
    except Exception as e:
        print(f"שגיאה בשמירת קובץ ה-JSON '{json_path}': {e}")
        return False

def get_youtube_video_id(url):
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
        pass
    return None

def find_song(songs, identifier):
    try:
        index = int(identifier)
        if 1 <= index <= len(songs):
            return songs[index - 1]
    except ValueError:
        pass

    identifier_lower = identifier.lower()
    matches_id = []
    for song in songs:

        if song.get('youtube_url'):
            video_id = get_youtube_video_id(song['youtube_url'])
            if video_id and video_id.lower() == identifier_lower:
                matches_id.append(song)
    if len(matches_id) == 1:
        return matches_id[0]
    elif len(matches_id) > 1:
        print(f"אזהרה: נמצאו מספר שירים עם אותו YouTube ID: '{identifier}'. לא ניתן לבחור באופן חד משמעי.")
        return None

    matches_name = []
    for song in songs:
        if 'name' in song and song['name'].lower() == identifier_lower:
            matches_name.append(song)
    if len(matches_name) == 1:
        return matches_name[0]
    elif len(matches_name) > 1:
        print(f"אזהרה: נמצאו מספר שירים עם אותו שם: '{identifier}'. נסה לציין זמר או להשתמש ב-ID/אינדקס.")
        return None
    return None

def select_song_interactive(songs):
    valid_songs = []
    print("\n--- רשימת שירים זמינים ---")
    for i, song in enumerate(songs):
        if isinstance(song, dict) and 'name' in song:
            artist_display = f" - {song.get('artist', 'לא ידוע')}" if song.get('artist') else ""
            lyrics_indicator = "[עם מילים]" if song.get('lyrics_file') else ""
            hebrew_indicator = "[שם עברי]" if song.get('hebrew_name') else ""
            lang_indicator = f"({song.get('language', 'en')})"
            url_indicator = "" if song.get('youtube_url') else " [ללא URL]"
            print(f"{len(valid_songs) + 1}. {song['name']}{artist_display} {lang_indicator} {hebrew_indicator}{lyrics_indicator}{url_indicator}")
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
                return valid_songs[choice - 1]
            else:
                print(f"בחירה לא חוקית. אנא הזן מספר בין 1 ל-{len(valid_songs)} או 'q'.")
        except ValueError:
            print("קלט לא תקין. אנא הזן מספר בלבד או 'q'.")
        except KeyboardInterrupt:
             print("\nיציאה לפי בקשת המשתמש.")
             return None

def validate_and_get_song_details(selected_song, songs_directory, lyrics_directory, cli_lyrics_path=None, cli_language=None):
    if not selected_song or not isinstance(selected_song, dict):
        print("שגיאה פנימית: נתוני השיר שנבחר אינם תקינים.")
        return None, None, None, None, None, None, None

    song_name = selected_song.get('name')
    youtube_url = selected_song.get('youtube_url')
    artist_name = selected_song.get('artist')
    hebrew_name = selected_song.get('hebrew_name')
    lyrics_rel_path_json = selected_song.get('lyrics_file')
    language_from_json = selected_song.get('language', 'en').lower()

    if not song_name:
        print(f"שגיאה: רשומת השיר אינה שלמה (חסר שם): {selected_song}")
        return None, None, None, None, None, None, None



    source_language = 'en'
    if cli_language and cli_language.lower() in ['en', 'yi']:
        source_language = cli_language.lower()
        print(f"  שפת מקור נקבעה מה-CLI: {'אנגלית' if source_language == 'en' else 'יידיש'}")
    elif language_from_json in ['en', 'yi']:
        source_language = language_from_json
        print(f"  שפת מקור נקבעה מה-JSON: {'אנגלית' if source_language == 'en' else 'יידיש'}")
    else:
        print(f"  שפת מקור נקבעה כברירת מחדל: {'אנגלית' if source_language == 'en' else 'יידיש'}")

    expected_mp3_filename = f"{song_name}.mp3"
    expected_mp3_path = os.path.join(songs_directory, expected_mp3_filename)

    print(f"\nפרטי השיר שנבחר:")
    print(f"  שם: {song_name}")
    if artist_name: print(f"  זמר: {artist_name}")
    if hebrew_name: print(f"  שם בעברית: {hebrew_name}")
    print(f"  קישור YouTube: {youtube_url if youtube_url else 'לא סופק (עיבוד מקבצים מקומיים אפשרי)'}")
    print(f"  שפת מקור מזוהה: {'אנגלית' if source_language == 'en' else 'יידיש'}")
    print(f"  נתיב MP3 צפוי: {expected_mp3_path}")

    if not os.path.exists(expected_mp3_path):
        print(f"\n!!! שגיאה קריטית !!!")
        print(f"קובץ האודיו הצפוי '{expected_mp3_filename}' עבור השיר '{song_name}' לא נמצא בתיקייה '{songs_directory}'.")
        print("ודא שהקובץ קיים עם השם המדויק (כולל סיומת mp3) והנתיב הנכון.")
        print("שם השיר בקובץ song_list.json חייב להיות זהה לשם קובץ ה-MP3 (ללא הסיומת).")
        return None, None, None, None, None, None, None

    lyrics_content = None
    lyrics_source_path = None
    if cli_lyrics_path:
        potential_paths = [cli_lyrics_path, os.path.join(lyrics_directory, cli_lyrics_path)]
        for path in potential_paths:
            if os.path.exists(path):
                lyrics_source_path = os.path.abspath(path)
                print(f"  מילים יטענו מהנתיב שהוגדר ב-CLI: {lyrics_source_path}")
                break
        if not lyrics_source_path:
            print(f"  אזהרה: קובץ המילים שצויין ב-CLI '{cli_lyrics_path}' לא נמצא.")
    elif lyrics_rel_path_json:
        potential_path = os.path.join(lyrics_directory, lyrics_rel_path_json)
        if os.path.exists(potential_path):
            lyrics_source_path = potential_path
            print(f"  מילים יטענו מהנתיב שהוגדר ב-JSON: {lyrics_source_path}")
        else:
            print(f"  אזהרה: קובץ המילים שהוגדר ב-JSON '{lyrics_rel_path_json}' לא נמצא בנתיב הצפוי '{potential_path}'.")
    else:
        potential_lyrics_filename = f"{song_name}.txt"
        potential_path = os.path.join(lyrics_directory, potential_lyrics_filename)
        if os.path.exists(potential_path):
            lyrics_source_path = potential_path
            print(f"  נמצא קובץ מילים אוטומטית התואם לשם השיר: {lyrics_source_path}")
        else:
             print("  לא הוגדר קובץ מילים (CLI/JSON) ולא נמצא קובץ אוטומטי תואם לשם השיר.")

    if lyrics_source_path:
        try:
            with open(lyrics_source_path, 'r', encoding='utf-8') as f:
                lyrics_content = f.read()
            print(f"  תוכן המילים נטען בהצלחה מ: '{lyrics_source_path}'")
        except Exception as e:
            print(f"  אזהרה: שגיאה בקריאת קובץ המילים '{lyrics_source_path}': {e}")
            lyrics_content = None
    return song_name, artist_name, hebrew_name, youtube_url, expected_mp3_path, lyrics_content, source_language

def process_standalone_json_to_srt(json_files_dir, srt_output_dir):
    print(f"\n--- בדיקת קבצי JSON עצמאיים להמרה ל-SRT בתיקייה: {json_files_dir} ---")
    json_files_found = glob.glob(os.path.join(json_files_dir, "*.json"))
    if not json_files_found:
        print("לא נמצאו קבצי JSON לעיבוד.")
        return
    converted_count = 0
    for json_file_path in json_files_found:
        json_filename = os.path.basename(json_file_path)
        srt_filename = os.path.splitext(json_filename)[0] + ".srt"
        srt_file_path = os.path.join(srt_output_dir, srt_filename)
        print(f"  מעבד את '{json_filename}'...")
        print(f"    נתיב קובץ SRT יעד: {srt_file_path}")
        srt_content = convert_json_content_to_srt_string(json_file_path)
        if srt_content:
            try:
                with open(srt_file_path, 'w', encoding='utf-8') as srt_f:
                    srt_f.write(srt_content)
                print(f"    המרת '{json_filename}' ל-SRT הושלמה ונשמרה ב: '{srt_file_path}'")
                converted_count += 1
            except IOError as e:
                print(f"    שגיאה בכתיבת קובץ ה-SRT '{srt_file_path}': {e}")
        else:
            print(f"    המרת '{json_filename}' נכשלה או שלא נוצר תוכן SRT (בדוק לוגים קודמים).")
    if converted_count > 0:
        print(f"סה\"כ {converted_count} קבצי JSON הומרו ל-SRT.")
    elif json_files_found:
        print("לא הומרו קבצי JSON (ייתכן שהמרות נכשלו או שלא נוצר תוכן).")
    print("--- סיום בדיקת קבצי JSON עצמאיים ---")

def copy_and_rename_file(source_path, target_dir, target_filename):

    if not os.path.exists(source_path):
        print(f"שגיאה: קובץ המקור '{source_path}' לא נמצא.")
        return None
    if not os.path.isdir(target_dir): # Should not happen if dirs are created
        print(f"שגיאה: תיקיית היעד '{target_dir}' אינה קיימת או אינה תיקייה.")
        return None

    target_full_path = os.path.join(target_dir, target_filename)
    try:
        os.makedirs(target_dir, exist_ok=True) # Ensure target_dir exists
        shutil.copy2(source_path, target_full_path) # copy2 preserves metadata
        print(f"הקובץ '{os.path.basename(source_path)}' הועתק בהצלחה אל '{target_full_path}'")
        return target_full_path
    except Exception as e:
        print(f"שגיאה בהעתקת הקובץ מ-'s{source_path}' אל '{target_full_path}': {e}")
        return None

def handle_external_subtitle_file(external_path, target_write_path_in_correct_dir, json_target_dir, srt_target_dir):
    # target_write_path_in_correct_dir is the full path where the file *should* end up,
    # e.g., .../srt_files/SongName_en.srt or .../json_files/SongName_en.json
    # This function determines the correct target_dir (json_target_dir or srt_target_dir)
    # and the final filename based on target_write_path_in_correct_dir.

    if not os.path.exists(external_path):
        print(f"אזהרה: קובץ הכתוביות החיצוני '{external_path}' לא נמצא. מדלג.")
        return False

    _, external_ext = os.path.splitext(external_path)
    external_ext = external_ext.lower()

    final_target_filename = os.path.basename(target_write_path_in_correct_dir)
    actual_target_dir = None

    if external_ext == ".json":
        actual_target_dir = json_target_dir
        # Ensure final_target_filename has .json extension if it's from an SRT path
        final_target_filename = os.path.splitext(final_target_filename)[0] + ".json"
    elif external_ext == ".srt":
        actual_target_dir = srt_target_dir

        final_target_filename = os.path.splitext(final_target_filename)[0] + ".srt"
    else:
        print(f"אזהרה: סיומת קובץ כתוביות חיצונית לא נתמכת: '{external_ext}' עבור '{external_path}'. נדרש .json או .srt. מדלג.")
        return False

    copied_path = copy_and_rename_file(external_path, actual_target_dir, final_target_filename)
    if copied_path:
        print(f"קובץ חיצוני '{os.path.basename(external_path)}' הועתק אל '{copied_path}'.")
        return True
    else:
        print(f"שגיאה בהעתקת קובץ חיצוני '{external_path}'.")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="יוצר סרטוני כתוביות YouTube עם תמלול ותרגום אוטומטיים (Gemini API).",
        formatter_class=argparse.RawTextHelpFormatter
    )
    group_select_add = parser.add_mutually_exclusive_group(required=False)
    group_select_add.add_argument(
        "-s", "--select",
        metavar="IDENTIFIER",
        help="בחר שיר ספציפי לעיבוד.\n"
             "   <IDENTIFIER> יכול להיות:\n"
             "     - מספר אינדקס (מהרשימה שתוצג).\n"
             "     - YouTube Video ID (אם השיר מכיל URL).\n"
             "     - שם השיר המדויק (case-insensitive)."
    )
    group_select_add.add_argument(
        "--add",
        action='store_true',
        help="הוסף שיר חדש לרשימה (song_list.json) ועבד אותו מיד.\n"
             "   דורש: --name (-n).\n"
             "   דורש: --url (-u) או (גם --source-subtitles-path (-ss) וגם --target-subtitles-path (-ts)).\n"
             "   אופציונלי: --artist (-ar), --hebrew-name (-hn), --language (-l), --lyrics-file (-lf),\n"
             "              --source-mp3-path (-sm)."
    )
    parser.add_argument(
        "-n", "--name",
        help="[נדרש עם --add] שם השיר להוספה (ישמש גם כשם קובץ MP3 צפוי)."
    )
    parser.add_argument(
        "-ar", "--artist",
        help="[אופציונלי עם --add] שם הזמר להוספה."
    )
    parser.add_argument(
        "-hn", "--hebrew-name",
        help="[אופציונלי עם --add] שם השיר בעברית (לשימוש בכותרת המשנה)."
    )
    parser.add_argument(
        "-u", "--url",
        help="[נדרש עם --add, אלא אם סופקו גם -ss וגם -ts] קישור YouTube מלא של השיר."
    )
    parser.add_argument(
        "-sm", "--source-mp3-path",
        metavar="PATH",
        help="[בשילוב עם --add] נתיב מלא לקובץ MP3 חיצוני.\n"
             "   הקובץ יועתק לתיקיית השירים ויקבל את השם שהוגדר עם --name."
    )
    parser.add_argument(
        "-ss", "--source-subtitles-path",
        metavar="PATH",
        help="נתיב מלא לקובץ כתוביות מקור חיצוני (JSON או SRT).\n"
             "   הקובץ יועתק וישונה שמו להתאמה לשיר הנבחר/נוסף.\n"
             "   אם מסופק יחד עם -ts, ה--url הופך לאופציונלי עבור --add."
    )
    parser.add_argument(
        "-ts", "--target-subtitles-path",
        metavar="PATH",
        help="נתיב מלא לקובץ כתוביות יעד חיצוני (עברית - JSON או SRT).\n"
             "   הקובץ יועתק וישונה שמו להתאמה לשיר הנבחר/נוסף.\n"
             "   אם מסופק יחד עם -ss, ה--url הופך לאופציונלי עבור --add."
    )
    parser.add_argument(
        "-lf", "--lyrics-file",
        metavar="PATH",
        help="נתיב לקובץ טקסט המכיל את מילות השיר.\n"
             "   - עוקף הגדרה ב-JSON וזיהוי אוטומטי.\n"
             "   - הנתיב יכול להיות אבסולוטי או יחסי."
    )
    parser.add_argument(
        "-f", "--force-regenerate",
        action="store_true",
        help="אלץ יצירה מחדש של קבצי הכתוביות (SRT) מה-API.\n"
             "   מתעלם מקבצי SRT קיימים. דורש YouTube URL עבור תמלול."
    )
    parser.add_argument(
        "-l", "--language",
        choices=['en', 'yi'],
        help="ציין במפורש את שפת המקור ('en' לאנגלית, 'yi' ליידיש).\n"
             "   - עוקף הגדרה ב-JSON.\n"
             "   - ברירת מחדל: מה-JSON, או 'en'."
    )
    parser.add_argument(
        "-is", "--intro-subtitle",
        choices=['artist', 'hebrew'],
        default='artist',
        help="קבע מה יוצג בכותרת המשנה בפתיח:\n"
             "   - 'artist': שם הזמר (ברירת מחדל).\n"
             "   - 'hebrew': שם השיר בעברית.\n"
             "   (דורש שהמידע יהיה קיים ב-JSON)"
    )
    args = parser.parse_args()
    print("--- יוצר וידאו כתוביות YouTube ---")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("שגיאה: משתנה הסביבה 'GEMINI_API_KEY' לא הוגדר.")
        print("אנא הגדר את המפתח והפעל את הסקריפט מחדש.")
        sys.exit(1)


    songs = load_song_list(SONG_LIST_JSON_PATH)
    if songs is None:
        sys.exit(1)

    selected_song_data = None
    cli_lyrics_path = args.lyrics_file
    cli_language_override = args.language

    if args.add:
        if not args.name:
            parser.error("--add דורש --name.")

        if not args.url and not (args.source_subtitles_path and args.target_subtitles_path):
            parser.error("--add דורש --url, או גם --source-subtitles-path וגם --target-subtitles-path אם אין URL זמין.")


        if args.source_mp3_path and not args.name:
             parser.error("--source-mp3-path דורש שימוש עם --name (-n) כאשר מוסיפים שיר חדש.")

        if args.source_mp3_path:
            print(f"מעבד קובץ MP3 חיצוני: {args.source_mp3_path}")
            target_mp3_filename = f"{args.name.strip()}.mp3"
            copied_mp3_path = copy_and_rename_file(args.source_mp3_path, SONGS_DIR, target_mp3_filename)
            if not copied_mp3_path:
                print(f"שגיאה קריטית בהעתקת קובץ MP3 חיצוני '{args.source_mp3_path}'. יוצא מהתוכנית.")
                sys.exit(1)
            print(f"קובץ MP3 חיצוני הועתק בהצלחה ל: {copied_mp3_path}")

        new_song = {"name": args.name.strip()}
        if args.url: new_song["youtube_url"] = args.url.strip()
        else: new_song["youtube_url"] = None

        if args.artist and args.artist.strip(): new_song["artist"] = args.artist.strip()
        if args.hebrew_name and args.hebrew_name.strip(): new_song["hebrew_name"] = args.hebrew_name.strip()
        new_song["language"] = cli_language_override if cli_language_override else 'en'

        if args.lyrics_file:
            user_lyrics_path = args.lyrics_file
            lyrics_dir_abs_path = LYRICS_DIR
            relative_path_in_lyrics_dir = None
            try:
                abs_user_path = os.path.abspath(user_lyrics_path)
                if abs_user_path.startswith(lyrics_dir_abs_path + os.sep) and os.path.exists(abs_user_path):
                    relative_path_in_lyrics_dir = os.path.relpath(abs_user_path, lyrics_dir_abs_path).replace(os.sep, '/')
            except: pass

            if not relative_path_in_lyrics_dir:
                 potential_path_in_lyrics = os.path.join(lyrics_dir_abs_path, user_lyrics_path)
                 if os.path.exists(potential_path_in_lyrics):
                     relative_path_in_lyrics_dir = user_lyrics_path.replace(os.sep, '/')

            if relative_path_in_lyrics_dir:
                 new_song['lyrics_file'] = relative_path_in_lyrics_dir
                 print(f"  נתיב קובץ המילים '{relative_path_in_lyrics_dir}' (יחסית לתיקיית המילים) ישמר ב-JSON.")
            elif os.path.exists(user_lyrics_path):
                 print(f"  אזהרה: קובץ המילים '{user_lyrics_path}' נמצא, אך אינו בתוך תיקיית המילים המוגדרת ('{lyrics_dir_abs_path}').")
                 print(f"           הקישור לא ישמר אוטומטית ב-song_list.json. אנא העבר את הקובץ לתיקייה המתאימה ועדכן ידנית אם צריך.")
            else:
                 print(f"  אזהרה: קובץ המילים שצויין '{user_lyrics_path}' לא נמצא. לא ניתן לקשר אותו ב-JSON.")

        existing_song = None
        if new_song.get("youtube_url"):
            existing_song = next((s for s in songs if s.get('youtube_url') == new_song['youtube_url']), None)

        if existing_song:
            print(f"אזהרה: שיר עם ה-URL '{new_song['youtube_url']}' כבר קיים ברשימה. משתמש בנתונים הקיימים ומעדכן אותם אם יש פרטים חדשים מה-CLI.")

            if "artist" in new_song: existing_song["artist"] = new_song["artist"]
            if "hebrew_name" in new_song: existing_song["hebrew_name"] = new_song["hebrew_name"]
            if "language" in new_song: existing_song["language"] = new_song["language"]
            if "lyrics_file" in new_song: existing_song["lyrics_file"] = new_song["lyrics_file"]
            selected_song_data = existing_song
            save_song_list(SONG_LIST_JSON_PATH, songs)
        else:
            existing_by_name = next((s for s in songs if s.get('name', '').lower() == new_song['name'].lower()), None)
            if existing_by_name and not new_song.get("youtube_url"):
                print(f"אזהרה: שיר עם השם '{new_song['name']}' (ללא URL) כבר קיים. מעדכן נתונים.")

                if "artist" in new_song: existing_by_name["artist"] = new_song["artist"]
                if "hebrew_name" in new_song: existing_by_name["hebrew_name"] = new_song["hebrew_name"]
                if "language" in new_song: existing_by_name["language"] = new_song["language"]
                if "lyrics_file" in new_song: existing_by_name["lyrics_file"] = new_song["lyrics_file"]
                selected_song_data = existing_by_name
                save_song_list(SONG_LIST_JSON_PATH, songs)
            else:
                print(f"מוסיף שיר חדש לרשימה: '{new_song['name']}'")
                songs.append(new_song)
                if save_song_list(SONG_LIST_JSON_PATH, songs):
                    selected_song_data = new_song
                else:
                    print("שגיאה בשמירת הרשימה המעודכנת, לא ניתן להמשיך.")
                    sys.exit(1)

    elif args.select:
        print(f"מחפש שיר לפי מזהה: '{args.select}'...")
        selected_song_data = find_song(songs, args.select)
        if selected_song_data is None:
             print(f"שגיאה: לא נמצא שיר התואם למזהה '{args.select}' או שהמזהה אינו חד משמעי.")
             sys.exit(1)
    else:
        selected_song_data = select_song_interactive(songs)
        if selected_song_data is None:
            print("לא נבחר שיר. יוצא מהתוכנית.")
            sys.exit(0)

    if selected_song_data is None:
         print("שגיאה: לא נבחרו נתוני שיר תקינים.")
         sys.exit(1)

    song_name_val, artist_name_val, hebrew_name_val, youtube_link_val, mp3_file_path_val, lyrics_content_val, source_language_val = validate_and_get_song_details(
        selected_song_data, SONGS_DIR, LYRICS_DIR, cli_lyrics_path, cli_language_override
    )
    if not all([song_name_val, mp3_file_path_val, source_language_val]):
        print("שגיאה באימות פרטי השיר או מציאת קבצים חיוניים. יוצא מהתוכנית.")
        sys.exit(1)

    try:
        gemini_model_name = resolved_config.get('gemini_settings', {}).get('model_name', 'gemini-2.5-pro-preview-06-05')
        print(f"משתמש במודל Gemini הבא: {gemini_model_name}")

        subtitle_generator = SubtitleGenerator(
            api_key=api_key,
            model_name=gemini_model_name,
            srt_output_dir=SRT_FILES_DIR,
            instructions_filepath=SYSTEM_INSTRUCTIONS_PATH
        )
    except Exception as e:
         print(f"שגיאה קריטית ביצירת SubtitleGenerator: {e}")
         sys.exit(1)


    (source_srt_write_path, _), \
    (hebrew_srt_write_path, _) = subtitle_generator._calculate_filenames(
        song_name_val, youtube_link_val, mp3_file_path_val, source_language_val
    )

    if args.source_subtitles_path:
        print(f"\n--- מעבד קובץ כתוביות מקור חיצוני: {os.path.basename(args.source_subtitles_path)} ---")
        handle_external_subtitle_file(
            external_path=args.source_subtitles_path,
            target_write_path_in_correct_dir=source_srt_write_path,
            json_target_dir=JSON_FILES_DIR,
            srt_target_dir=SRT_FILES_DIR
        )
    if args.target_subtitles_path:
        print(f"\n--- מעבד קובץ כתוביות יעד (עברית) חיצוני: {os.path.basename(args.target_subtitles_path)} ---")
        handle_external_subtitle_file(
            external_path=args.target_subtitles_path,
            target_write_path_in_correct_dir=hebrew_srt_write_path,
            json_target_dir=JSON_FILES_DIR,
            srt_target_dir=SRT_FILES_DIR
        )

    process_standalone_json_to_srt(JSON_FILES_DIR, SRT_FILES_DIR)


    source_language_name = "אנגלית" if source_language_val == 'en' else "יידיש"
    print(f"\n--- בדיקת קבצי כתוביות (SRT) קיימים לאחר טיפול בקבצים חיצוניים ---")
    print(f"  נתיב צפוי לכתיבת/קריאת קובץ מקור ({source_language_name}): {source_srt_write_path}")
    print(f"  נתיב צפוי לכתיבת/קריאת קובץ יעד (עברית): {hebrew_srt_write_path}")
    if not args.force_regenerate:
         if os.path.exists(source_srt_write_path): print(f"    -> קובץ מקור ({source_language_name}) נמצא בנתיב הראשי.")
         else: print(f"    -> קובץ מקור ({source_language_name}) לא נמצא בנתיב הראשי (ייתכן ויימצא בנתיב legacy).")
         if os.path.exists(hebrew_srt_write_path): print(f"    -> קובץ יעד (עברית) נמצא בנתיב הראשי.")
         else: print(f"    -> קובץ יעד (עברית) לא נמצא בנתיב הראשי (ייתכן ויימצא בנתיב legacy).")
         print(f"  (המערכת תנסה לטעון קבצים קיימים מנתיבים אפשריים. השתמש ב--force-regenerate ליצירה מחדש מה-API)")
    else:
        print("  שים לב: יצירה מחדש של הכתוביות מה-API נכפתה באמצעות '--force-regenerate'.")
        if not youtube_link_val:
            print("  אזהרה: '--force-regenerate' צויין, אך לא סופק YouTube URL. לא ניתן יהיה לייצר תמלול מה-API.")


    print("\n--- יצירה או טעינה של כתוביות ---")
    source_subs, target_subs = subtitle_generator.generate_or_load_subtitles(
        source_language=source_language_val,
        song_name=song_name_val,
        youtube_url=youtube_link_val,
        mp3_audio_path=mp3_file_path_val,
        lyrics_content=lyrics_content_val,
        force_regenerate=args.force_regenerate
    )

    if source_subs is None and target_subs is None:
        print("\nשגיאה קריטית: לא ניתן היה ליצור או לטעון כתוביות. יוצא מהתוכנית.")
        sys.exit(1)
    elif source_subs is None:
        print(f"\nאזהרה: לא הופקו/נטענו כתוביות מקור ({source_language_name}). ממשיך עם כתוביות יעד בלבד (אם קיימות).")
    elif target_subs is None:
        print("\nאזהרה: לא הופקו/נטענו כתוביות יעד (עברית). ממשיך עם כתוביות מקור בלבד (אם קיימות).")
    elif not source_subs and not target_subs:
         print("\nאזהרה: שתי רשימות הכתוביות (מקור ויעד) ריקות. הוידאו ייווצר ללא כתוביות טקסט.")
    else:
        print("\nנתוני הכתוביות הוכנו בהצלחה.")

    print("\n--- יצירת הוידאו ---")
    try:
        video_creator = VideoCreator(resolved_config)
        output_base_name = os.path.splitext(os.path.basename(mp3_file_path_val))[0]
        created_video_path = video_creator.create_video(
            mp3_path=mp3_file_path_val,
            song_title_text=song_name_val,
            artist_name_text=artist_name_val,
            hebrew_song_name_text=hebrew_name_val,
            intro_subtitle_mode=args.intro_subtitle,
            source_subtitle_data=source_subs,
            target_subtitle_data=target_subs,
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
        print("ודא שקובצי הפונטים ותמונות הרקע קיימים בנתיבים המוגדרים בקונפיגורציה.")
        sys.exit(1)
    except ValueError as e:
        print(f"\nשגיאה קריטית בהגדרות הקונפיגורציה או בנתונים: {e}")
        sys.exit(1)
    except KeyError as e:
         print(f"\nשגיאה קריטית: מפתח חסר בקובץ הקונפיגורציה - {e}")
         sys.exit(1)
    except Exception as e:
        print(f"\nשגיאה לא צפויה במהלך הגדרת או הרצת VideoCreator: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()