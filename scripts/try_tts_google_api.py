from google.cloud import texttospeech

# הגדרת נתיב למפתח ה-API (יש לוודא שהקובץ JSON נמצא במיקום זה)
import os
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\me\OneDrive\וידאו\מפתחות גישה\youtube-channel-440320-fe17f0f0a940.json"

# יצירת לקוח Text-to-Speech
client = texttospeech.TextToSpeechClient()

# הגדרת הטקסט לדיבור
text_to_speak = "שלום, אני מבצע בדיקה של שירות טקסט לדיבור."
synthesis_input = texttospeech.SynthesisInput(text=text_to_speak)

# הגדרת קול והגדרות אודיו
voice = texttospeech.VoiceSelectionParams(
    language_code="he-IL",  # עברית
    name="he-IL-Wavenet-C"  # קול ספציפי בעברית
)

audio_config = texttospeech.AudioConfig(
    audio_encoding=texttospeech.AudioEncoding.MP3  # פורמט MP3
)

# שליחת הבקשה ל-API
response = client.synthesize_speech(
    input=synthesis_input,
    voice=voice,
    audio_config=audio_config
)

# שמירת האודיו לקובץ
output_path = "output.mp3"
with open(output_path, "wb") as audio_file:
    audio_file.write(response.audio_content)
    print(f"אודיו נוצר בהצלחה ונשמר ב-{output_path}")
