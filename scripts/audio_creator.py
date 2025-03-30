from google.cloud import texttospeech
import tempfile
import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# הגדרת נתיב למפתח ה-API (ודאו שהקובץ JSON נמצא במיקום המתאים)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\me\OneDrive\וידאו\מפתחות גישה\youtube-channel-440320-fe17f0f0a940.json"

class AudioCreator:
    def __init__(self, temp_dir, lang_settings, threads):
        self.temp_dir = temp_dir
        self.lang_settings = lang_settings
        self.executor = ThreadPoolExecutor(max_workers=threads)
        self.client = texttospeech.TextToSpeechClient()

    def create_audio_task(self, text, lang, slow=False):
        try:
            voice_config = self.lang_settings.get(lang, self.lang_settings['en']).get('voice', None)
            if voice_config is None:
                logging.error(f"לא נמצאו הגדרות קול עבור שפה: {lang}")
                raise ValueError(f"לא נמצאו הגדרות קול עבור שפה: {lang}")

            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice_params = texttospeech.VoiceSelectionParams(
                language_code=voice_config['language_code'],
                name=voice_config['name']
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=0.70 if slow else 0.95
            )

            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=voice_params,
                audio_config=audio_config
            )

            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3', dir=self.temp_dir.name) as tmp_file:
                tmp_file.write(response.audio_content)
                return tmp_file.name

        except ValueError as e:
            logging.error(f"שגיאה ביצירת אודיו עבור הטקסט: '{text}' בשפה: '{lang}'. פרטים: {e}")
            raise

    def create_audios(self, tasks):
        futures = {}
        for task in tasks:
            if len(task) == 3:
                text, lang, slow = task
                future = self.executor.submit(self.create_audio_task, text, lang, slow)
            else:
                text, lang = task
                future = self.executor.submit(self.create_audio_task, text, lang, False)
            futures[future] = task

        results = {}
        for future in as_completed(futures):
            task = futures[future]
            try:
                audio_path = future.result()
                results[tuple(task)] = audio_path
                logging.info(
                    f"אודיו נוצר עבור: '{task[0]}' בשפה: '{task[1]}' עם slow={'True' if len(task) == 3 and task[2] else 'False'}"
                )
            except Exception as e:
                logging.error(f"שגיאה ביצירת אודיו עבור: '{task[0]}' בשפה: '{task[1]}'. פרטים: {e}")
        return results

    def shutdown(self):
        self.executor.shutdown(wait=True)