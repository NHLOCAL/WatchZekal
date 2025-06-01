# -*- coding: utf-8 -*-
import subprocess
import os
import sys
import threading # >>> נוסף עבור פלט בזמן אמת

# הגדרות צבעים (קודי ANSI)
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# --- הגדרות Bidi ---
try:
    from bidi.algorithm import get_display
    ENABLE_BIDI_FIX = True
except ImportError:
    ENABLE_BIDI_FIX = False
    def get_display(text): # פונקציית דמה
        return text
# --------------------

def prepare_display_text(text_to_display):
    if ENABLE_BIDI_FIX:
        return get_display(str(text_to_display))
    return str(text_to_display)

def print_color(text, color_code, end='\n'):
    processed_text = prepare_display_text(text)
    try:
        print(f"{color_code}{processed_text}{Colors.ENDC}", end=end, flush=True)
    except UnicodeEncodeError:
        fallback_text = str(text).encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8')
        print(fallback_text, end=end, flush=True)

def strip_all_enclosing_quotes(path_string):
    if path_string is None:
        return None
    s = str(path_string).strip()
    while len(s) >= 2:
        if (s.startswith('"') and s.endswith('"')) or \
           (s.startswith("'") and s.endswith("'")):
            s = s[1:-1].strip()
        else:
            break
    return s

def get_input(prompt_text, optional=False, default=None, allowed_values=None, to_lower=False, is_path=False):
    while True:
        displayed_prompt_main = prepare_display_text(prompt_text)
        full_prompt_parts = [f"{Colors.OKCYAN}{displayed_prompt_main}{Colors.ENDC}"]
        optional_suffix_parts = []
        if optional:
            optional_suffix_parts.append(prepare_display_text(" (אופציונלי, הקש Enter לדלג"))
            if default is not None:
                optional_suffix_parts.append(prepare_display_text(f", ברירת מחדל: {str(default)}"))
            optional_suffix_parts.append(prepare_display_text(")"))
        full_prompt_parts.append("".join(optional_suffix_parts))
        full_prompt_parts.append(prepare_display_text(": "))
        full_prompt_str = "".join(full_prompt_parts)
        user_input_raw = input(full_prompt_str)
        user_input_processed = user_input_raw.strip()
        if is_path:
            user_input_processed = strip_all_enclosing_quotes(user_input_processed)
        if to_lower:
            user_input_processed = user_input_processed.lower()
        if not user_input_raw.strip() and optional:
            return default if default is not None else None
        if not user_input_raw.strip() and not optional:
            print_color("שדה זה הוא חובה.", Colors.WARNING)
            continue
        if allowed_values:
            if user_input_processed not in allowed_values:
                displayed_allowed_values = ', '.join([prepare_display_text(str(v)) for v in allowed_values])
                error_message = f"ערך לא חוקי. אפשרויות מותרות: {displayed_allowed_values}"
                print_color(error_message, Colors.WARNING)
                continue
        return user_input_processed

def get_yes_no_input(prompt_text, default_yes=True):
    displayed_prompt = prepare_display_text(prompt_text)
    suffix = "[Y/n]" if default_yes else "[y/N]"
    while True:
        full_prompt_str = f"{Colors.OKCYAN}{displayed_prompt} {suffix}{Colors.ENDC} "
        response = input(full_prompt_str).strip().lower()
        if not response:
            return default_yes
        if response in ['y', 'yes', 'כן']:
            return True
        if response in ['n', 'no', 'לא']:
            return False
        print_color("אנא הזן 'y' (כן) או 'n' (לא).", Colors.WARNING)

# >>> פונקציית עזר לקריאה והדפסה של פלט מצינור (עבור תהליכונים)
def stream_output_reader(pipe, color_code_for_lines):
    """
    קוראת שורות מ-pipe ומדפיסה אותן עם הצבע הנתון.
    מיועדת לרוץ בתוך תהליכון.
    """
    try:
        # text=True ב-Popen אומר ש-pipe הוא אובייקט טקסטואלי (כמו קובץ פתוח במצב 'r')
        # readline() יחזיר מחרוזת ריקה כאשר הצינור נסגר (סוף הקלט).
        for line in iter(pipe.readline, ''):
            print_color(line.rstrip('\r\n'), color_code_for_lines) # הסרת תווי סוף שורה מיותרים
        pipe.close() # סגירת הצינור מצדנו לאחר סיום הקריאה
    except Exception as e:
        # במקרה של שגיאה בקריאה מהצינור (נדיר אם הצינור תקין)
        print_color(f"[שגיאת קריאת פלט]: {e}", Colors.FAIL)


def build_and_run_command(args_list):
    script_path = "main.py"
    command = [sys.executable, script_path] + args_list

    print_color("\nהפקודה שתופעל:", Colors.HEADER)
    display_command_parts = []
    for part in command:
        display_command_parts.append(f'"{str(part)}"')
    print_color(' '.join(display_command_parts), Colors.OKBLUE)

    try:
        print_color("\nמריץ את הכלי (הפלט יוצג בזמן אמת)...", Colors.OKGREEN)

        process = subprocess.Popen(command,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   text=True, # חשוב לקריאה כשורות טקסט
                                   encoding='utf-8', # קידוד הפלט הצפוי מהכלי
                                   errors='replace', # טיפול בשגיאות קידוד
                                   bufsize=1) # מעבר למצב line-buffered (עשוי לעזור לפלט להגיע מהר יותר)

        # יצירה והרצה של תהליכונים לקריאת stdout ו-stderr
        stdout_thread = None
        stderr_thread = None

        if process.stdout:
            # הפלט הרגיל (stdout) יודפס ללא צבע מיוחד נוסף (ישתמש בצבע הטרמינל הרגיל)
            # אך יעבור דרך print_color לטיפול Bidi
            stdout_thread = threading.Thread(target=stream_output_reader, args=(process.stdout, Colors.ENDC))
            stdout_thread.daemon = True # מאפשר לתוכנית הראשית להסתיים גם אם התהליכון עדיין רץ (אם כי נעשה join)
            stdout_thread.start()
        
        if process.stderr:
            # פלט שגיאות (stderr) יודפס בצבע אדום
            stderr_thread = threading.Thread(target=stream_output_reader, args=(process.stderr, Colors.FAIL))
            stderr_thread.daemon = True
            stderr_thread.start()

        # המתנה לסיום התהליך החיצוני
        return_code = process.wait()

        # המתנה לסיום תהליכוני הקריאה (כדי לוודא שכל הפלט הודפס)
        if stdout_thread:
            stdout_thread.join()
        if stderr_thread:
            stderr_thread.join()
        
        # סגירת הצינורות על ידי התהליך החיצוני אמורה לגרום ל-readline להחזיר ''
        # והלולאות ב-stream_output_reader יסתיימו. סגירה נוספת כאן ליתר ביטחון אם הם עדיין פתוחים.
        if process.stdout and not process.stdout.closed:
             process.stdout.close()
        if process.stderr and not process.stderr.closed:
             process.stderr.close()

        if return_code == 0:
            print_color("\nהכלי סיים בהצלחה!", Colors.OKGREEN)
        else:
            print_color(f"\nהכלי נכשל עם קוד שגיאה: {return_code}", Colors.FAIL)

    except FileNotFoundError:
        print_color(f"שגיאה: הקובץ '{script_path}' (או '{sys.executable}') לא נמצא. ודא שהם נגישים.", Colors.FAIL)
    except Exception as e:
        print_color(f"אירעה שגיאה בלתי צפויה בעת הרצת הכלי: {e}", Colors.FAIL)


def configure_select_song():
    args = []
    print_color("\n--- בחירת שיר קיים ---", Colors.HEADER)
    identifier = get_input("הזן מזהה שיר (מספר אינדקס, YouTube Video ID, או שם שיר מדויק)")
    args.extend(["-s", identifier])
    print_color("\nהגדרות אופציונליות עבור בחירת שיר:", Colors.OKCYAN)
    source_subtitles_path = get_input("נתיב לקובץ כתוביות מקור חיצוני (JSON או SRT)", optional=True, is_path=True)
    if source_subtitles_path: args.extend(["-ss", source_subtitles_path])
    target_subtitles_path = get_input("נתיב לקובץ כתוביות יעד חיצוני (עברית - JSON או SRT)", optional=True, is_path=True)
    if target_subtitles_path: args.extend(["-ts", target_subtitles_path])
    lyrics_file_path = get_input("נתיב לקובץ טקסט המכיל את מילות השיר", optional=True, is_path=True)
    if lyrics_file_path: args.extend(["-lf", lyrics_file_path])
    if get_yes_no_input("האם לאלץ יצירה מחדש של קבצי כתוביות (SRT) מה-API?", default_yes=False): args.append("-f")
    language = get_input("ציין שפת מקור ('en' לאנגלית, 'yi' ליידיש)", optional=True, allowed_values=['en', 'yi', None, ''])
    if language: args.extend(["-l", language])
    intro_subtitle = get_input("מה יוצג בכותרת המשנה בפתיח ('artist' לשם הזמר, 'hebrew' לשם השיר בעברית)", optional=True, allowed_values=['artist', 'hebrew', None, ''])
    if intro_subtitle: args.extend(["-is", intro_subtitle])
    return args

def configure_add_song():
    args = ["--add"]
    print_color("\n--- הוספת שיר חדש ---", Colors.HEADER)
    name = get_input("שם השיר (ישמש גם כשם קובץ MP3 צפוי)")
    if not name: print_color("שם השיר הוא חובה.", Colors.WARNING); return None
    args.extend(["-n", name])
    use_url_provided = False
    print_color("\nהכלי דורש קישור YouTube או קבצי כתוביות מקור ויעד.", Colors.OKCYAN)
    if get_yes_no_input("האם ברצונך לספק קבצי כתוביות מקור ויעד במקום/בנוסף לקישור YouTube?", default_yes=False):
        ss_path = get_input("נתיב מלא לקובץ כתוביות מקור חיצוני (JSON או SRT)", is_path=True)
        if not ss_path: print_color("נתיב כתוביות מקור חובה במצב זה.", Colors.WARNING); return None
        ts_path = get_input("נתיב מלא לקובץ כתוביות יעד חיצוני (עברית - JSON או SRT)", is_path=True)
        if not ts_path: print_color("נתיב כתוביות יעד חובה במצב זה.", Colors.WARNING); return None
        args.extend(["-ss", ss_path, "-ts", ts_path])
        if get_yes_no_input("האם ברצונך לספק גם קישור YouTube (אופציונלי כעת)?", default_yes=False):
            url_val = get_input("קישור YouTube מלא של השיר")
            if url_val: args.extend(["-u", url_val]); use_url_provided = True
    else:
        url_val = get_input("קישור YouTube מלא של השיר (חובה אם לא סופקו קבצי כתוביות)")
        if not url_val: print_color("קישור YouTube חובה אם לא סופקו קבצי כתוביות.", Colors.WARNING); return None
        args.extend(["-u", url_val]); use_url_provided = True
    print_color("\nהגדרות אופציונליות עבור הוספת שיר:", Colors.OKCYAN)
    artist = get_input("שם הזמר", optional=True)
    if artist: args.extend(["-ar", artist])
    hebrew_name = get_input("שם השיר בעברית (לשימוש בכותרת המשנה)", optional=True)
    if hebrew_name: args.extend(["-hn", hebrew_name])
    source_mp3_path = get_input("נתיב מלא לקובץ MP3 חיצוני (יועתק וישונה שמו)", optional=True, is_path=True)
    if source_mp3_path: args.extend(["-sm", source_mp3_path])
    lyrics_file_path = get_input("נתיב לקובץ טקסט המכיל את מילות השיר", optional=True, is_path=True)
    if lyrics_file_path: args.extend(["-lf", lyrics_file_path])
    language = get_input("ציין שפת מקור ('en' לאנגלית, 'yi' ליידיש)", optional=True, allowed_values=['en', 'yi', None, ''], default='en')
    if language: args.extend(["-l", language])
    if use_url_provided and get_yes_no_input("האם לאלץ יצירה מחדש של קבצי כתוביות (SRT) מה-API (דורש YouTube URL)?", default_yes=False):
        args.append("-f")
    intro_subtitle = get_input("מה יוצג בכותרת המשנה בפתיח ('artist' לשם הזמר, 'hebrew' לשם השיר בעברית)", optional=True, allowed_values=['artist', 'hebrew', None, ''])
    if intro_subtitle: args.extend(["-is", intro_subtitle])
    return args

def main_menu():
    if os.name == 'nt':
        try: os.system("chcp 65001 > nul")
        except Exception: pass
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError: pass
    except Exception as e: print(f"[Warning] Could not reconfigure stdout/stderr encoding: {e}")
    if os.name == 'nt':
        try:
            import colorama
            colorama.init()
        except ImportError: print_color("[אזהרה] מומלץ להתקין 'colorama' לתמיכה בצבעים בחלונות CMD ישנים.", Colors.WARNING)
    if ENABLE_BIDI_FIX: print_color("[מידע] תיקון Bidi לעברית פעיל.", Colors.OKCYAN)
    else:
        print_color("[אזהרה] חבילת python-bidi אינה מותקנת. תצוגת עברית עלולה להיות הפוכה.", Colors.WARNING)
        print_color("ניתן להתקין עם: pip install python-bidi", Colors.WARNING)
    while True:
        print_color("\nברוך הבא לממשק הגדרות הכלי ליצירת סרטוני כתוביות!", Colors.HEADER)
        print_color("=====================================================", Colors.HEADER)
        print_color("הודעות סטטוס לדוגמה (כמו מהכלי המקורי):", Colors.OKCYAN)
        print_color("קונפיגורציה נטענה בהצלחה מ: 'C:\\Users\\me\\Documents\\GitHub\\WatchZekal\\song_subtitler\\config\\video_config.json'", Colors.OKBLUE)
        print_color("נתיב רקע פתיח זוהה: C:\\Users\\me\\Documents\\GitHub\\WatchZekal\\assets\\backgrounds/songs/intro.jpg", Colors.OKBLUE)
        print_color("-----------------------------------------------------", Colors.OKCYAN)
        print_color("\nאנא בחר פעולה:", Colors.BOLD)
        print_color("1. בחירת שיר קיים לעיבוד", Colors.OKGREEN)
        print_color("2. הוספת שיר חדש ועיבודו", Colors.OKGREEN)
        print_color("3. יציאה", Colors.WARNING)
        choice = get_input("הכנס את בחירתך (1-3)")
        final_args = None
        if choice == '1': final_args = configure_select_song()
        elif choice == '2': final_args = configure_add_song()
        elif choice == '3': print_color("יוצא מהתוכנית...", Colors.OKBLUE); break
        else: print_color("בחירה לא חוקית, אנא נסה שוב.", Colors.FAIL); continue
        if final_args is not None:
            build_and_run_command(final_args)
        input_prompt = prepare_display_text('הקש Enter כדי לחזור לתפריט הראשי...')
        input(f"\n{Colors.OKCYAN}{input_prompt}{Colors.ENDC}")

if __name__ == "__main__":
    main_menu()