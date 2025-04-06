import os
import json
import sys

# Import the classes from the other files
from subtitle_generator import SubtitleGenerator
from video_creator import VideoCreator

# --- Configuration ---
# Adjust paths relative to this main.py file's location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, '..', 'assets') # Assumes assets is one level up
FONTS_DIR = os.path.join(ASSETS_DIR, 'fonts')
DEMO_SONGS_DIR = os.path.join(BASE_DIR, 'demo_songs') # Assumes demo_songs is in the same dir as main.py
JSON_FILES_DIR = os.path.join(BASE_DIR, "json_files")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_FRAMES_DIR = os.path.join(OUTPUT_DIR, "subtitle_frames") # Frames inside output dir
SONG_LIST_JSON_PATH = os.path.join(BASE_DIR, 'song_list.json')

# --- Function to select song --- (Moved from original script)
def select_song_from_list(json_path, songs_directory):
    """
    Loads a list of songs from a JSON file, prompts the user to select one,
    checks for the corresponding MP3 file, and returns details.
    """
    if not os.path.exists(json_path):
        print(f"שגיאה: קובץ רשימת השירים '{json_path}' לא נמצא.")
        print("אנא צור קובץ 'song_list.json' בפורמט:")
        print('[{"name": "שם השיר 1", "youtube_url": "קישור_יוטיוב_1"}, ...]')
        return None, None, None

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            songs = json.load(f)
    except json.JSONDecodeError:
        print(f"שגיאה: קובץ ה-JSON '{json_path}' אינו תקין.")
        return None, None, None
    except Exception as e:
        print(f"שגיאה בטעינת קובץ ה-JSON '{json_path}': {e}")
        return None, None, None

    if not isinstance(songs, list) or not songs:
        print(f"שגיאה: קובץ ה-JSON '{json_path}' ריק או שאינו מכיל רשימה תקינה.")
        return None, None, None

    valid_songs = []
    print("\n--- רשימת שירים זמינים ---")
    for i, song in enumerate(songs):
        if isinstance(song, dict) and 'name' in song and 'youtube_url' in song:
            print(f"{len(valid_songs) + 1}. {song['name']}")
            valid_songs.append(song)
        else:
            print(f"אזהרה: דילוג על רשומה לא תקינה באינדקס {i} בקובץ ה-JSON.")
    print("-------------------------")

    if not valid_songs:
         print("שגיאה: לא נמצאו שירים תקינים ברשימה.")
         return None, None, None

    while True:
        try:
            choice_str = input(f"הזן את מספר השיר שברצונך לעבד (1-{len(valid_songs)}), או 'q' ליציאה: ")
            if choice_str.lower() == 'q':
                 print("יציאה לפי בקשת המשתמש.")
                 return None, None, None
            choice = int(choice_str)
            if 1 <= choice <= len(valid_songs):
                selected_song = valid_songs[choice - 1]
                song_name = selected_song['name']
                youtube_url = selected_song['youtube_url']
                # Derive the expected MP3 filename based on the 'name' field
                expected_mp3_filename = f"{song_name}.mp3"
                expected_mp3_path = os.path.join(songs_directory, expected_mp3_filename)

                print(f"\nבחרת: {song_name}")
                print(f"קישור YouTube: {youtube_url}")
                print(f"נתיב MP3 צפוי: {expected_mp3_path}")

                # --- Critical Check: Verify MP3 file existence ---
                if not os.path.exists(expected_mp3_path):
                    print(f"\n!!! שגיאה קריטית !!!")
                    print(f"קובץ האודיו הצפוי '{expected_mp3_path}' עבור השיר '{song_name}' לא נמצא בתיקייה '{songs_directory}'.")
                    print(f"ודא שהקובץ קיים עם השם המדויק (כולל סיומת mp3) והנתיב הנכון.")
                    print("אנא בחר שיר אחר או תקן את שם הקובץ / מיקומו ונסה שנית.")
                    # Continue the loop to allow another selection
                    continue # Ask for input again
                else:
                    # MP3 file exists, return the details
                    return song_name, youtube_url, expected_mp3_path
            else:
                print(f"בחירה לא חוקית. אנא הזן מספר בין 1 ל-{len(valid_songs)} או 'q'.")
        except ValueError:
            print("קלט לא תקין. אנא הזן מספר בלבד או 'q'.")
        except KeyboardInterrupt:
             print("\nיציאה לפי בקשת המשתמש.")
             return None, None, None


def main():
    """Main execution function"""
    print("--- יוצר וידאו כתוביות YouTube ---")

    # --- Create necessary base directories ---
    # (Output directories will be created by VideoCreator)
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(FONTS_DIR, exist_ok=True)
    os.makedirs(DEMO_SONGS_DIR, exist_ok=True)
    os.makedirs(JSON_FILES_DIR, exist_ok=True) # SubtitleGenerator needs this
    os.makedirs(OUTPUT_DIR, exist_ok=True)     # VideoCreator needs this base

    # --- Get API Key ---
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("שגיאה: משתנה הסביבה 'GEMINI_API_KEY' לא הוגדר.")
        print("אנא הגדר את המפתח והפעל את הסקריפט מחדש.")
        sys.exit(1) # Exit if no API key

    # --- Select Song ---
    selected_song_name, youtube_link, mp3_file_path = select_song_from_list(SONG_LIST_JSON_PATH, DEMO_SONGS_DIR)

    if not selected_song_name:
        print("לא נבחר שיר. יוצא מהתוכנית.")
        sys.exit(0) # Clean exit

    # --- Step 1: Generate or Load Subtitles ---
    print("\n--- שלב 1: יצירה או טעינה של כתוביות ---")
    subtitle_generator = SubtitleGenerator(api_key=api_key, json_output_dir=JSON_FILES_DIR)
    english_subs, hebrew_subs = subtitle_generator.generate_or_load_subtitles(youtube_link, mp3_file_path)

    # Check results from subtitle generation/loading
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


    # --- Step 2: Create Video ---
    print("\n--- שלב 2: יצירת הוידאו ---")

    # Define configuration for VideoCreator
    video_creator_config = {
        'assets_dir': ASSETS_DIR,
        'fonts_dir': FONTS_DIR,
        'output_frames_dir': OUTPUT_FRAMES_DIR,
        'output_video_dir': OUTPUT_DIR,
        'background_image_name': os.path.join('levels', "word_background.png"), # Relative path within assets/backgrounds
        'font_name': "Rubik-Regular.ttf", # Relative path within fonts_dir
        'video_resolution': (1280, 720),
        'video_fps': 25,
        'fontsize_en': 60,
        'fontsize_he': 57,
        'color_subs': 'black',
        'stroke_color_subs': 'white',
        'stroke_width_subs': 1.5,
        'spacing_within_language': 10,
        'spacing_between_languages': 35,
        'fontsize_title': 120,
        'color_title': 'blue',
        'stroke_color_title': 'white',
        'stroke_width_title': 4.0,
        'position_title': ('center', 'center'),
    }

    try:
        video_creator = VideoCreator(config=video_creator_config)

        # Determine base filename for output video from the MP3 path
        output_base_name = os.path.splitext(os.path.basename(mp3_file_path))[0]

        # Call the creation method
        created_video_path = video_creator.create_video(
            mp3_path=mp3_file_path,
            song_title_text=selected_song_name,
            english_subtitle_data=english_subs, # Pass potentially None or empty lists
            hebrew_subtitle_data=hebrew_subs,   # Pass potentially None or empty lists
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
        print("ודא שקובץ הפונט ותמונת הרקע קיימים בנתיבים המוגדרים.")
        sys.exit(1)
    except Exception as e:
        print(f"\nשגיאה לא צפויה במהלך הגדרת או הרצת VideoCreator: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()