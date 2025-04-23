# יוצר סרטוני כתוביות YouTube - מדריך שימוש

## תיאור

כלי זה יוצר סרטוני YouTube עבור שירים באופן אוטומטי. הוא משלב קובץ אודיו (MP3), תמונת רקע, כותרות (שם שיר ואמן), וכתוביות מסונכרנות בשפת המקור (אנגלית/יידיש) ובעברית. הכתוביות נוצרות באמצעות Google Gemini API.

## דרישות

*   **Python 3.10+**
*   **Pip** (מנהל החבילות של Python)
*   **ImageMagick:** **חובה להתקין ולהוסיף ל-PATH!** נדרש על ידי `moviepy` לעיבוד טקסט. [הוראות התקנה](https://imagemagick.org/script/download.php).
*   **מפתח API של Google Gemini:** נדרש ליצירת כתוביות. [השג מפתח כאן](https://aistudio.google.com/app/apikey).

## התקנה והגדרה

1.  **הורד את הקוד:** שכפל (clone) או הורד את קבצי הפרויקט.
2.  **התקן ספריות:** פתח טרמינל בתיקיית הפרויקט והרץ:
    ```bash
    pip install google-genai moviepy Pillow numpy arabic_reshaper python-bidi imageio imageio-ffmpeg PyYAML
    ```
3.  **התקן ImageMagick:** התקן לפי ההוראות וודא שהוא מוגדר ב-PATH של המערכת.
4.  **הגדר מפתח Gemini API:** הגדר את המפתח שקיבלת כ**משתנה סביבה** בשם `GEMINI_API_KEY` בטרמינל שממנו תריץ את הסקריפט:
    *   Linux/macOS: `export GEMINI_API_KEY="YOUR_API_KEY"`
    *   Windows (cmd): `set GEMINI_API_KEY=YOUR_API_KEY`
    *   Windows (PowerShell): `$env:GEMINI_API_KEY="YOUR_API_KEY"`
5.  **הכן קבצי קלט:**
    *   **`config/song_list.json`:** רשימת השירים לעיבוד. לכל שיר:
        *   `"name"` (חובה): שם השיר (חייב להיות **זהה** לשם קובץ ה-MP3).
        *   `"youtube_url"` (חובה): קישור YouTube לשיר.
        *   `"language"` (אופציונלי): `"en"` (אנגלית - ברירת מחדל) או `"yi"` (יידיש).
        *   `"artist"` (אופציונלי): שם האמן.
        *   `"lyrics_file"` (אופציונלי): נתיב לקובץ מילים ב-`data/lyrics/`.
    *   **MP3:** מקם קבצי MP3 בתיקייה `data/songs/`. **שם הקובץ (בלי .mp3) חייב להיות זהה לשדה `"name"` ב-JSON.**
    *   **מילים (אופציונלי):** קבצי טקסט ב-`data/lyrics/`.
    *   **Assets:** פונטים (`.ttf`/`.otf`) ב-`assets/fonts/`, תמונות רקע ב-`assets/backgrounds/songs/`.
6.  **בדוק תצורה:**
    *   **`config/video_config.json`:** ודא נתיבים, שמות פונטים, צבעים וגדלים נכונים.
    *   **`config/system_instructions.yaml`:** מכיל הנחיות ל-API (ערוך בזהירות).

## הרצת הסקריפט

פתח טרמינל בתיקיית הפרויקט, ודא ש-`GEMINI_API_KEY` מוגדר, והרץ `python main.py` עם האפשרויות הבאות:

*   **מצב אינטראקטיבי (בחירת שיר מרשימה):**
    ```bash
    python main.py
    ```

*   **בחירה ישירה של שיר:**
    ```bash
    python main.py --select <מזהה_שיר>
    ```
    `<מזהה_שיר>` יכול להיות מספר אינדקס, YouTube ID, או שם השיר המדויק מה-JSON.

*   **הוספה ועיבוד שיר חדש:**
    ```bash
    python main.py --add --name "שם השיר" --url "קישור_יוטיוב" [אפשרויות נוספות...]
    ```
    *   חובה לציין `--name` ו-`--url`.
    *   אפשר להוסיף: `--artist "שם"`, `--language yi`, `--lyrics-file "נתיב/קובץ"`.

*   **אפשרויות נוספות (ניתן לשלב):**
    *   `--lyrics-file <PATH>`: שימוש בקובץ מילים ספציפי (עוקף JSON).
    *   `--force-regenerate`: יצירה מחדש של כתוביות מה-API (מתעלם מקבצי SRT קיימים).
    *   `--language <en|yi>`: קביעת שפת המקור (עוקף JSON).

הסקריפט יבצע את התהליך ויציג התקדמות.

## פלט

*   **וידאו סופי (MP4):** נשמר בתיקיית `output/` (או לפי ההגדרה), בשם `<שם_השיר>_subtitled.mp4`.
*   **קבצי כתוביות (SRT):** נשמרים בתיקיית `srt_files/` (או לפי ההגדרה) עבור כל שפה (`_en.srt` / `_yi.srt` ו-`_he.srt`). משמשים לטעינה חוזרת מהירה.
*   **פריימים זמניים:** נוצרים ונמחקים אוטומטית מ-`output/subtitle_frames/` בסיום מוצלח.

## פתרון בעיות נפוצות

*   **`FileNotFoundError`:** בדוק נתיבים ב-`video_config.json`, ודא שקובצי MP3/פונטים/רקעים קיימים וששמות תואמים.
*   **שגיאת API Key / אימות:** ודא שמשתנה הסביבה `GEMINI_API_KEY` הוגדר נכון בטרמינל הנוכחי.
*   **שגיאות ImageMagick / טקסט:** ודא ש-ImageMagick מותקן ונמצא ב-PATH. הפעל מחדש טרמינל/מחשב.
*   **שגיאות טעינת SRT:** ודא שקובצי SRT קיימים תקינים (UTF-8). מחק קבצים פגומים או השתמש ב-`--force-regenerate`.
*   **`AttributeError: ... 'google.genai.types' ...`:** חוסר התאמה בגרסת SDK. ודא שהקוד תואם לגרסה המותקנת (`pip show google-genai`).

## רישיון

[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)