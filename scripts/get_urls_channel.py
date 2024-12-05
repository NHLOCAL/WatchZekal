import os
import requests
import json
from dotenv import load_dotenv

# טעינת משתני הסביבה מקובץ .env
load_dotenv()

# מפתח ה-API וה-CHANNEL_ID
API_KEY = os.getenv("YOUTUBE_API_KEY")
if not API_KEY:
    raise ValueError("מפתח ה-API לא מוגדר במשתנה הסביבה YOUTUBE_API_KEY")

CHANNEL_ID = "UCpigWlQPv9SdmHjJ49JZTlg"

# URL בסיסי
BASE_URL = "https://www.googleapis.com/youtube/v3"

# פונקציה לשליפת נתונים מ-API עם טיפול ב-Token
def fetch_data(url):
    response = requests.get(url).json()
    if "error" in response:
        raise ValueError(f"API Error: {response['error']['message']}")
    return response

# פונקציה לקבלת URL של תמונת התצוגה באיכות הגבוהה ביותר הזמינה
def get_best_thumbnail(thumbnails):
    # ננסה קודם את התמונות ברזולוציה גבוהה יותר
    for quality in ["maxres", "standard", "high", "medium", "default"]:
        if quality in thumbnails:
            return thumbnails[quality]["url"]
    return None  # במקרה חריג מאוד

# שלב 1: קבלת ה-playlist ID של הסרטונים שהועלו לערוץ
playlist_url = f"{BASE_URL}/channels?part=contentDetails&id={CHANNEL_ID}&key={API_KEY}"
response = fetch_data(playlist_url)

# בדיקה אם items קיימים בתשובה
if "items" not in response or not response["items"]:
    raise ValueError("No items found in the response. Please check the CHANNEL_ID and API_KEY.")

uploads_playlist_id = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

# שלב 2: קבלת רשימת הסרטונים כולל כותרות, קישורים, תיאורים ותמונות תצוגה
videos = []
next_page_token = None

while True:
    playlist_items_url = f"{BASE_URL}/playlistItems?part=snippet&playlistId={uploads_playlist_id}&maxResults=50&pageToken={next_page_token or ''}&key={API_KEY}"
    response = fetch_data(playlist_items_url)

    for item in response.get('items', []):
        video_title = item['snippet']['title']
        video_id = item['snippet']['resourceId']['videoId']
        video_description = item['snippet'].get('description', 'No description available')
        video_thumbnail = get_best_thumbnail(item['snippet']['thumbnails'])
        videos.append({
            "title": video_title,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "description": video_description,
            "thumbnail": video_thumbnail
        })

    next_page_token = response.get('nextPageToken')
    if not next_page_token:
        break

# שלב 3: קבלת רשימת כל הפלייליסטים של הערוץ כולל תיאורים ותמונות תצוגה
playlists = []
next_page_token = None

while True:
    playlists_url = f"{BASE_URL}/playlists?part=snippet&channelId={CHANNEL_ID}&maxResults=50&pageToken={next_page_token or ''}&key={API_KEY}"
    response = fetch_data(playlists_url)

    for item in response.get('items', []):
        playlist_title = item['snippet']['title']
        playlist_id = item['id']
        playlist_description = item['snippet'].get('description', 'No description available')
        playlist_thumbnail = get_best_thumbnail(item['snippet']['thumbnails'])
        playlists.append({
            "title": playlist_title,
            "url": f"https://www.youtube.com/playlist?list={playlist_id}",
            "description": playlist_description,
            "thumbnail": playlist_thumbnail
        })

    next_page_token = response.get('nextPageToken')
    if not next_page_token:
        break

# שלב 4: שמירת התוצאות בקובץ JSON
output_data = {
    "videos": videos,
    "playlists": playlists
}

output_file = "channel_data.json"
with open(output_file, "w", encoding="utf-8") as file:
    json.dump(output_data, file, ensure_ascii=False, indent=4)

print(f"Saved channel data to {output_file}")
print(f"Found {len(videos)} videos and {len(playlists)} playlists.")
