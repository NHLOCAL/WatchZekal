import os
import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys # ודא שמיובא
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- הגדרות (כמו קודם) ---
VIDEO_FOLDER = r"C:\Users\me\Documents\GitHub\WatchZekal\up_ytb\videos"
JSON_METADATA_FILE = "metadata.json"
CHROME_USER_DATA_DIR = r"C:\Users\me\AppData\Local\Google\Chrome\User Data"
CHROME_PROFILE_DIRECTORY = "Profile 6"
YOUTUBE_STUDIO_URL = "https://studio.youtube.com"
UPLOAD_TIMEOUT_SECONDS = 3600
ELEMENT_WAIT_TIMEOUT_SECONDS = 45

# --- טעינת מידע מה-JSON (כמו קודם) ---
try:
    with open(JSON_METADATA_FILE, 'r', encoding='utf-8') as f:
        metadata_list = json.load(f)
    metadata_dict = {item['filename']: item for item in metadata_list}
    print(f"טעינת מטא-דאטה עבור {len(metadata_dict)} קבצים מ-JSON.")
except FileNotFoundError:
    print(f"שגיאה: קובץ המטא-דאטה לא נמצא בנתיב {JSON_METADATA_FILE}")
    exit()
except json.JSONDecodeError:
    print(f"שגיאה: לא ניתן לפענח את קובץ ה-JSON {JSON_METADATA_FILE}")
    exit()
except Exception as e:
    print(f"שגיאה לא צפויה בטעינת JSON: {e}")
    exit()

# --- קבלת רשימת קבצי וידאו מהתיקייה (כמו קודם) ---
try:
    all_files = os.listdir(VIDEO_FOLDER)
    video_files = [f for f in all_files if os.path.isfile(os.path.join(VIDEO_FOLDER, f)) and f.lower().endswith(('.mp4', '.mov', '.avi', '.wmv', '.flv'))] # הוסף סיומות לפי הצורך
    if not video_files:
         print(f"לא נמצאו קבצי וידאו בתיקייה {VIDEO_FOLDER}")
         exit()
    print(f"נמצאו {len(video_files)} קבצי וידאו בתיקייה.")
except FileNotFoundError:
    print(f"שגיאה: תיקיית הוידאו לא נמצאה בנתיב {VIDEO_FOLDER}")
    exit()
except Exception as e:
    print(f"שגיאה לא צפויה בקריאת תיקיית הוידאו: {e}")
    exit()

# --- הגדרת Selenium WebDriver (כמו קודם) ---
print("מגדיר את Selenium WebDriver...")
options = webdriver.ChromeOptions()
options.add_argument(f"user-data-dir={CHROME_USER_DATA_DIR}")
options.add_argument(f"profile-directory={CHROME_PROFILE_DIRECTORY}")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--start-maximized")
options.add_argument('--log-level=3')
options.add_experimental_option('excludeSwitches', ['enable-logging'])

try:
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT_SECONDS)
    print("WebDriver הוגדר בהצלחה.")
except Exception as e:
    print(f"שגיאה בהגדרת WebDriver: {e}")
    print("ודא ש-Chrome מותקן, שהנתיבים לפרופיל נכונים ושאין חסימות אבטחה.")
    exit()

# --- לולאת העלאת הסרטונים ---
uploaded_count = 0
skipped_count = 0

for video_filename in video_files:
    video_path = os.path.join(VIDEO_FOLDER, video_filename)
    print(f"\n--- מתחיל עיבוד עבור: {video_filename} ---")

    if video_filename not in metadata_dict:
        print(f"  אזהרה: לא נמצא מטא-דאטה עבור {video_filename} בקובץ ה-JSON. מדלג.")
        skipped_count += 1
        continue

    metadata = metadata_dict[video_filename]
    title = metadata.get('title', f"Video Title - {video_filename}")
    description = metadata.get('description', "")
    tags = metadata.get('tags', []) # עדיין נקרא מה-JSON, אבל לא נשתמש בו בהמשך
    playlist_name = metadata.get('playlist')
    visibility = metadata.get('visibility', 'private').lower()

    try:
        # 1. ניווט ל-YouTube Studio והתחלת העלאה (כמו קודם)
        print("  מנווט ל-YouTube Studio...")
        driver.get(YOUTUBE_STUDIO_URL)
        time.sleep(5)

        print("  מחפש את כפתור 'צור'...")
        create_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "ytcp-button#create-icon")))
        create_button.click()
        print("  לחצתי על 'צור'.")
        time.sleep(1)

        print("  מחפש את אפשרות 'העלה סרטונים' באמצעות test-id...")
        upload_option_selector = "[test-id='upload-beta']"
        upload_option = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, upload_option_selector)))
        upload_option.click()
        print("  לחצתי על 'העלה סרטונים'.")
        time.sleep(2)

        # 2. בחירת קובץ הוידאו (כמו קודם)
        print(f"  בוחר קובץ וידאו: {video_path}")
        file_input = driver.find_element(By.XPATH, "//input[@type='file']")
        file_input.send_keys(video_path)
        print(f"  הקובץ {video_filename} נשלח להעלאה...")

        # 3. מילוי פרטים (כותרת, תיאור) - המתנה להופעת הדיאלוג
        print("  ממתין לטעינת דיאלוג הפרטים...")

        # --- כותרת (ניקוי עם מקשים והזנה) ---
        title_textbox_xpath = "//ytcp-social-suggestions-textbox[@id='title-textarea']//div[@id='textbox'] | //div[@id='title-textarea']//div[@id='textbox']"
        print("  מחפש את שדה הכותרת...")
        title_element = wait.until(EC.element_to_be_clickable((By.XPATH, title_textbox_xpath)))
        print("  מנקה כותרת באמצעות הדמיית מקשים (Ctrl+A, Delete)...")
        try:
            title_element.click()
            time.sleep(0.5)
            title_element.send_keys(Keys.CONTROL + "a")
            time.sleep(0.5)
            title_element.send_keys(Keys.DELETE)
            time.sleep(1)
            print("  ניקוי כותרת באמצעות מקשים הושלם.")
        except Exception as e: print(f"  אזהרה: שגיאה בניקוי כותרת באמצעות מקשים: {e}. ממשיך בכל זאת.")
        print(f"  מכניס כותרת: {title}")
        try:
            title_element.click()
            time.sleep(0.2)
            title_element.send_keys(title)
            time.sleep(1)
            print("  הכנסת כותרת חדשה הושלמה.")
        except Exception as e: print(f"  שגיאה בהכנסת הכותרת החדשה: {e}")

        # --- תיאור (ניקוי עם מקשים והזנה) ---
        desc_textbox_xpath = "//ytcp-social-suggestions-textbox[@id='description-textarea']//div[@id='textbox'] | //div[@id='description-textarea']//div[@id='textbox']"
        print("  מחפש את שדה התיאור...")
        description_element = wait.until(EC.element_to_be_clickable((By.XPATH, desc_textbox_xpath)))
        print("  מנקה תיאור באמצעות הדמיית מקשים (Ctrl+A, Delete)...")
        try:
            description_element.click()
            time.sleep(0.5)
            description_element.send_keys(Keys.CONTROL + "a")
            time.sleep(0.5)
            description_element.send_keys(Keys.DELETE)
            time.sleep(1)
            print("  ניקוי תיאור באמצעות מקשים הושלם.")
        except Exception as e: print(f"  אזהרה: שגיאה בניקוי תיאור באמצעות מקשים: {e}. ממשיך בכל זאת.")
        print("  מכניס תיאור...")
        try:
            description_element.click()
            time.sleep(0.2)
            description_lines = description.split('\n')
            for i, line in enumerate(description_lines):
                description_element.send_keys(line)
                if i < len(description_lines) - 1:
                    description_element.send_keys(Keys.RETURN)
                    time.sleep(0.1)
            time.sleep(1)
            print("  הכנסת תיאור חדש הושלם.")
        except Exception as e: print(f"  שגיאה בהכנסת התיאור החדש: {e}")

        # --- פלייליסט (אופציונלי) ---
        # אם אתה *לא* רוצה להשתמש בפלייליסטים מה-JSON, אתה יכול להעיר (comment out) את כל הבלוק הבא:
        if playlist_name:
             try:
                 print(f"  מחפש להוסיף לפלייליסט '{playlist_name}'...")
                 # Selector עשוי להשתנות! בדוק אם צריך לעדכן
                 playlist_dropdown_selector = "ytcp-video-metadata-playlists #playlist-dropdown"
                 playlist_dropdown = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, playlist_dropdown_selector)))
                 playlist_dropdown.click()
                 time.sleep(2)
                 # XPath לפלייליסט לפי שם - עשוי להשתנות! בדוק אם צריך לעדכן
                 playlist_xpath = f"//ytcp-ve[@data-list-item-name='{playlist_name}']//ytcp-checkbox-lit" # ניחוש ל-Selector חדש
                 # playlist_xpath_old = f"//span[@class='label style-scope ytcp-checkbox-group' and normalize-space(text())='{playlist_name}']" # Selector ישן
                 playlist_item = wait.until(EC.element_to_be_clickable((By.XPATH, playlist_xpath)))
                 playlist_item.click()
                 print(f"  הסרטון סומן להוספה לפלייליסט '{playlist_name}'.")
                 time.sleep(1)
                 # סגירת תפריט הפלייליסטים - Selector עשוי להשתנות! בדוק אם צריך לעדכן
                 done_button_playlist_selector = "ytcp-playlist-dialog #save-button" # ניחוש ל-Selector חדש
                 # done_button_playlist_old = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "ytcp-button.done-button[label='Done']"))) # Selector ישן
                 done_button_playlist = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, done_button_playlist_selector)))
                 done_button_playlist.click()
                 time.sleep(1)
             except Exception as pl_e:
                 print(f"  אזהרה: לא הצלחתי להוסיף לפלייליסט '{playlist_name}'. שגיאה: {pl_e}")
                 try: driver.find_element(By.CSS_SELECTOR, "body").click(); time.sleep(0.5) # נסה לסגור דיאלוג פתוח
                 except: pass

        # 4. מעבר בין שלבי האשף (כמו קודם, עם ההמתנה לבדיקות)
        next_button_id = "next-button" # ID לרוב יציב
        next_button_selector = (By.ID, next_button_id)

        print("  לוחץ 'הבא' (פרטים -> רכיבי וידאו)...")
        wait.until(EC.element_to_be_clickable(next_button_selector)).click()
        time.sleep(3)

        print("  לוחץ 'הבא' (רכיבי וידאו -> בדיקות)...")
        wait.until(EC.element_to_be_clickable(next_button_selector)).click()
        print("  נכנס למסך הבדיקות. ממתין לסיומן...")

        # --- המתנה חכמה לסיום הבדיקות (כמו בגרסה הקודמת) ---
        results_description_selector = (By.ID, "results-description")
        expected_success_text = "לא נמצאו בעיות"
        print(f"  מחכה שהטקסט '{expected_success_text}' יופיע באלמנט עם ID 'results-description'")
        try:
            WebDriverWait(driver, UPLOAD_TIMEOUT_SECONDS).until(
                EC.text_to_be_present_in_element(results_description_selector, expected_success_text)
            )
            print(f"  זוהה טקסט סיום בדיקות: '{expected_success_text}'")
            time.sleep(1)
            print(f"  ממתין שכפתור '{next_button_id}' יהפוך ללחיץ...")
            wait.until(EC.element_to_be_clickable(next_button_selector))
            print(f"  כפתור '{next_button_id}' מוכן.")
            time.sleep(1)
        except TimeoutException:
            print(f"  אזהרה: Timeout ({UPLOAD_TIMEOUT_SECONDS} שניות) בהמתנה לטקסט '{expected_success_text}' או להפעלת כפתור 'הבא'.")
            # ... (קוד טיפול ב-Timeout כמו קודם) ...
            raise TimeoutException(f"Timeout או שגיאה בשלב הבדיקות (לא נמצא הטקסט '{expected_success_text}')")
        except Exception as checks_err:
             print(f"  שגיאה בלתי צפויה בהמתנה לבדיקות: {checks_err}")
             raise checks_err

        # --- אם ההמתנה הצליחה, לחץ על כפתור "הבא" ---
        print("  הבדיקות הסתיימו והכפתור מוכן.")
        print("  לוחץ 'הבא' (בדיקות -> נראות)...")
        try:
            next_btn = wait.until(EC.element_to_be_clickable(next_button_selector))
            driver.execute_script("arguments[0].click();", next_btn)
            print("  המעבר לשלב 'נראות' בוצע.")
            time.sleep(5)
        except Exception as e:
             print(f"  שגיאה קריטית בלחיצה על 'הבא' לשלב נראות: {e}")
             # ... (קוד טיפול בשגיאה כמו קודם) ...
             raise e

        # 5. הגדרת נראות (כמו קודם)
        print(f"  מגדיר נראות ל: {visibility}")
        # Selector עשוי להשתנות! בדוק אם צריך לעדכן
        visibility_radio_xpath = f"//tp-yt-paper-radio-button[@name='{visibility.upper()}']//div[@id='radioContainer']" # ניסיון ללחוץ על div פנימי
        # visibility_radio_xpath_old = f"//tp-yt-paper-radio-button[@name='{visibility.upper()}']"
        try:
            wait.until(EC.element_to_be_clickable((By.XPATH, visibility_radio_xpath))).click()
            print(f"  נראות הוגדרה ל-{visibility}.")
        except Exception as vis_e:
            print(f"  אזהרה: לא נמצא/נלחץ כפתור רדיו לנראות '{visibility}'. ייתכן שברירת המחדל תישאר. שגיאה: {vis_e}")
        time.sleep(2)

        # 6. סיום ופרסום/שמירה (כמו קודם)
        done_button_id = "done-button" # ID לרוב יציב
        done_button_selector = (By.ID, done_button_id)
        print("  מחפש את כפתור 'סיום'/'פרסם'...")
        done_button = wait.until(EC.element_to_be_clickable(done_button_selector))
        print("  ממתין שכפתור 'סיום'/'פרסם' יהיה מאופשר...")
        # ודא שהכפתור אכן ניתן ללחיצה (לא מעובד עדיין או מושבת)
        WebDriverWait(driver, UPLOAD_TIMEOUT_SECONDS).until(
            EC.element_to_be_clickable(done_button_selector) # שינוי: מחכה שיהיה clickable במקום enabled
        )
        print("  לוחץ על 'סיום'/'פרסם'...")
        # נסה לחיצה עם JS ליתר ביטחון
        driver.execute_script("arguments[0].click();", done_button)
        # done_button.click() # אפשר לנסות גם לחיצה רגילה
        time.sleep(2) # המתנה קצרה אחרי הלחיצה

        # 7. המתנה לאישור סופי (הודעה שמופיעה או סגירת הדיאלוג)
        print("  ממתין לאישור סיום ההעלאה והעיבוד...")
        # נסה למצוא את כפתור הסגירה של דיאלוג האישור - Selector עשוי להשתנות!
        close_button_selector = "ytcp-button#close-button.ytcp-uploads-dialog" # ניחוש ל-Selector ספציפי יותר
        # close_button_selector_old = "ytcp-button#close-button"
        try:
            WebDriverWait(driver, UPLOAD_TIMEOUT_SECONDS).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, close_button_selector))
            )
            print(f"  אישור התקבל! סרטון '{video_filename}' הועלה בהצלחה.")
            uploaded_count += 1
            # אפשר ללחוץ סגירה אם רוצים
            # try:
            #     driver.find_element(By.CSS_SELECTOR, close_button_selector).click()
            #     time.sleep(5)
            # except Exception as close_e:
            #     print(f"  אזהרה: לא הצלחתי ללחוץ על כפתור הסגירה: {close_e}")

        except TimeoutException:
            print(f"  אזהרה: לא זוהה אישור סיום העלאה (כפתור סגירה '{close_button_selector}') עבור {video_filename} תוך הזמן שהוקצב.")
            print("  ייתכן שההעלאה עדיין מתבצעת ברקע או שנכשלה בשלב הסופי.")
            # אל תסמן כהצלחה במקרה זה, אבל אל תדלג אוטומטית אם יכול להיות שזה הצליח
        except Exception as final_e:
             print(f"  שגיאה לא צפויה בהמתנה לאישור סופי: {final_e}")

        # המתנה קצרה לפני הסרטון הבא
        time.sleep(10)

    except TimeoutException as e:
        print(f"  שגיאה: Timeout בהמתנה לאלמנט כלשהו עבור {video_filename}. ייתכן שהממשק השתנה או שהיה איטי מדי.")
        print(f"  פרטי השגיאה: {e}")
        # שקול לצלם מסך
        try: driver.save_screenshot(f"error_{video_filename}_timeout.png")
        except: pass
        skipped_count += 1
    except NoSuchElementException as e:
        print(f"  שגיאה: אלמנט לא נמצא עבור {video_filename}. כנראה שה-Selector (XPath/CSS) שגוי או שהמבנה השתנה.")
        print(f"  פרטי השגיאה: {e}")
        # שקול לצלם מסך
        try: driver.save_screenshot(f"error_{video_filename}_notfound.png")
        except: pass
        skipped_count += 1
    except Exception as e:
        print(f"  שגיאה כללית בעיבוד {video_filename}: {e}")
        import traceback
        traceback.print_exc()
        # שקול לצלם מסך
        try: driver.save_screenshot(f"error_{video_filename}_general.png")
        except: pass
        skipped_count += 1
    finally:
        # ודא שאנחנו לא תקועים בדיאלוג העלאה לפני הלולאה הבאה
        try:
            print("  חוזר לדף התוכן של סטודיו...")
            # שינוי: ניווט לדף התוכן במקום לדף הבית של סטודיו
            driver.get(YOUTUBE_STUDIO_URL + "/channel/UC/videos/upload?filter=%5B%5D&sort=%7B%22columnType%22%3A%22date%22%2C%22sortOrder%22%3A%22DESCENDING%22%7D")
            time.sleep(5) # המתנה לטעינת הדף
        except Exception as nav_e:
            print(f"  אזהרה: בעיה בניווט חזרה לדף התוכן: {nav_e}")


# --- סיום וניקוי ---
print("\n--- סיכום ---")
print(f"סרטונים שהועלו בהצלחה: {uploaded_count}")
print(f"סרטונים שדולגו (חסר מידע / שגיאה): {skipped_count}")
print("אוטומציה הסתיימה.")

if driver:
    driver.quit()