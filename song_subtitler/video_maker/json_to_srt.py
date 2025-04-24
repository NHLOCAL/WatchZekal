import json
import os

def convert_json_to_srt(json_file_path):
    """
    ממיר קובץ JSON בפורמט כתוביות לפורמט SRT.

    Args:
        json_file_path (str): נתיב הקובץ JSON.

    Returns:
        str: תוכן קובץ SRT כטקסט, או None אם יש שגיאה.
    """
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"שגיאה: קובץ לא נמצא בנתיב: {json_file_path}")
        return None
    except json.JSONDecodeError:
        print(f"שגיאה: קובץ JSON לא תקין: {json_file_path}")
        return None

    srt_content = ""
    for subtitle in data:
        srt_content += str(subtitle['id']) + "\n"
        start_time_srt = format_time_srt(subtitle['start_time'])
        end_time_srt = format_time_srt(subtitle['end_time'])
        srt_content += f"{start_time_srt} --> {end_time_srt}\n"
        srt_content += subtitle['text'] + "\n\n"

    return srt_content

def format_time_srt(time_str):
    """
    ממיר פורמט זמן "MM:SS.milliseconds" לפורמט "HH:MM:SS,milliseconds" של SRT.

    Args:
        time_str (str): מחרוזת זמן בפורמט "MM:SS.milliseconds".

    Returns:
        str: מחרוזת זמן בפורמט "HH:MM:SS,milliseconds".
    """
    minutes, rest = time_str.split(":", 1)
    seconds, milliseconds = rest.split(".")
    return f"00:{minutes}:{seconds},{milliseconds}"

if __name__ == "__main__":
    json_path = input("אנא הכנס נתיב לקובץ JSON: ")

    if not os.path.exists(json_path):
        print("שגיאה: הנתיב שסופק אינו קיים.")
    elif not json_path.lower().endswith(".json"):
        print("שגיאה: הקובץ שסופק אינו קובץ JSON (.json).")
    else:
        srt_output = convert_json_to_srt(json_path)
        if srt_output:
            print("\nתוכן SRT:\n")
            print(srt_output)

            output_srt_file = os.path.splitext(json_path)[0] + ".srt"
            with open(output_srt_file, 'w', encoding='utf-8') as srt_file:
                srt_file.write(srt_output)
            print(f"\nקובץ SRT נשמר ב: {output_srt_file}")