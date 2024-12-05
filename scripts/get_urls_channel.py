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

# שלב 1: קבלת ה-playlist ID של הסרטונים שהועלו לערוץ
playlist_url = f"{BASE_URL}/channels?part=contentDetails&id={CHANNEL_ID}&key={API_KEY}"
response = requests.get(playlist_url).json()

# בדיקה אם items קיימים בתשובה
if "items" not in response or not response["items"]:
    raise ValueError("No items found in the response. Please check the CHANNEL_ID and API_KEY.")

uploads_playlist_id = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

# שלב 2: קבלת רשימת הסרטונים
videos = []
next_page_token = None

while True:
    playlist_items_url = f"{BASE_URL}/playlistItems?part=snippet&playlistId={uploads_playlist_id}&maxResults=50&pageToken={next_page_token or ''}&key={API_KEY}"
    response = requests.get(playlist_items_url).json()

    for item in response.get('items', []):
        video_title = item['snippet']['title']
        video_id = item['snippet']['resourceId']['videoId']
        videos.append({
            "title": video_title,
            "url": f"https://www.youtube.com/watch?v={video_id}"
        })

    next_page_token = response.get('nextPageToken')
    if not next_page_token:
        break

# שלב 3: שמירת הרשימה בקובץ JSON
output_file = "videos_list.json"
with open(output_file, "w", encoding="utf-8") as file:
    json.dump(videos, file, ensure_ascii=False, indent=4)

print(f"Saved {len(videos)} videos to {output_file}")
