import json
import moviepy.editor as mp
from gtts import gTTS
from pydub import AudioSegment
import os
import re
from moviepy.config import change_settings

# עדכן את הנתיב בהתאם למיקום ההתקנה שלך
change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"})

def sanitize_filename(filename):
    """
    Removes invalid characters from a filename.
    """
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def create_video_from_json(json_file, output_folder="output"):
    """
    Creates a video from a JSON file with Hebrew and English narration.

    Args:
        json_file: Path to the JSON file.
        output_folder: The folder where the output videos will be saved.
    """

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stage_number = data["stage_number"]
    stage_name = data["stage_name_display_he"]

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for lesson in data["lessons"]:
        lesson_number = lesson["lesson_number"]
        lesson_title = lesson["lesson_title_display_he"]
        video_title = lesson["video_title_display_he"]
        video_duration = lesson["video_duration_minutes"]

        lesson_audio_segments = []  # List to store audio segments (hebrew, english, silence)
        lesson_clips = []

        # Intro Text Clip
        intro_text = f"{video_title}\n{lesson_title}"
        intro_clip = mp.TextClip(intro_text, fontsize=40, color='white', size=(1280, 720), method='caption', align='center', bg_color='blue').set_duration(3)
        lesson_clips.append(intro_clip)
        lesson_audio_segments.append(AudioSegment.silent(duration=3000))

        for section in lesson["sections"]:
            section_number = section["section_number"]
            section_title = section["section_title_display_he"]
            section_text = section["section_text_display_he"]
            narration_he = section["narration_he"]
            narration_en = section["narration_en"]

            # Section Title Clip
            section_title_clip = mp.TextClip(section_title, fontsize=50, color='white', size=(1280, 720), method='caption', align='center', bg_color='black').set_duration(2)
            lesson_clips.append(section_title_clip)
            lesson_audio_segments.append(AudioSegment.silent(duration=2000))

            # Hebrew Narration for Section Text (if no specific narration exists)
            if not narration_he and section_text:
                tts = gTTS(text=section_text, lang='iw')
                temp_file = f"temp_he_{lesson_number}_{section_number}_section_text.mp3"
                tts.save(temp_file)
                audio_segment = AudioSegment.from_mp3(temp_file)
                lesson_audio_segments.append(audio_segment)
                os.remove(temp_file)

                # Section Text Clip (displayed during Hebrew narration of section text)
                section_text_clip = mp.TextClip(section_text, fontsize=30, color='white', size=(1280, 720), method='caption', align='center').set_duration(audio_segment.duration_seconds)
                lesson_clips.append(section_text_clip)

            # Hebrew Narration
            for text in narration_he:
                tts = gTTS(text=text, lang='iw')
                temp_file = f"temp_he_{lesson_number}_{section_number}.mp3"
                tts.save(temp_file)
                audio_segment = AudioSegment.from_mp3(temp_file)
                lesson_audio_segments.append(audio_segment)
                os.remove(temp_file)

                # Section Text Clip (displayed during Hebrew narration)
                section_text_clip = mp.TextClip(section_text, fontsize=30, color='white', size=(1280, 720), method='caption', align='center').set_duration(audio_segment.duration_seconds)
                lesson_clips.append(section_text_clip)

                # Narration Text Clip (Hebrew)
                narration_clip = mp.TextClip(text, fontsize=35, color='yellow', size=(1280, 720), method='caption', align='center').set_duration(audio_segment.duration_seconds)
                lesson_clips.append(narration_clip)

            # English Narration
            for text in narration_en:
                tts = gTTS(text=text, lang='en')
                temp_file = f"temp_en_{lesson_number}_{section_number}.mp3"
                tts.save(temp_file)
                audio_segment = AudioSegment.from_mp3(temp_file)
                lesson_audio_segments.append(audio_segment)
                os.remove(temp_file)

                # Section Text Clip (displayed during English narration)
                section_text_clip = mp.TextClip(section_text, fontsize=30, color='white', size=(1280, 720), method='caption', align='center').set_duration(audio_segment.duration_seconds)
                lesson_clips.append(section_text_clip)

                # Narration Text Clip (English)
                narration_clip = mp.TextClip(text, fontsize=35, color='cyan', size=(1280, 720), method='caption', align='center').set_duration(audio_segment.duration_seconds)
                lesson_clips.append(narration_clip)

        for exercise in lesson["exercises"]:
            exercise_title = exercise["exercise_title_display_he"]
            exercise_instructions = exercise["exercise_instructions_display_he"]
            exercise_narration_he = exercise["exercise_narration_he"]
            exercise_narration_en = exercise["exercise_narration_en"]

            # Exercise title clip
            exercise_title_clip = mp.TextClip(exercise_title, fontsize=50, color='white', size=(1280, 720), method='caption', align='center', bg_color='purple').set_duration(2)
            lesson_clips.append(exercise_title_clip)
            lesson_audio_segments.append(AudioSegment.silent(duration=2000))

             # Hebrew Narration for Exercise Instructions (if no specific narration exists)
            if not exercise_narration_he and exercise_instructions:
                tts = gTTS(text=exercise_instructions, lang='iw')
                temp_file = f"temp_he_exercise_{lesson_number}_instructions.mp3"
                tts.save(temp_file)
                audio_segment = AudioSegment.from_mp3(temp_file)
                lesson_audio_segments.append(audio_segment)
                os.remove(temp_file)

                # Exercise Instructions Clip (displayed during Hebrew narration of instructions)
                exercise_instructions_clip = mp.TextClip(exercise_instructions, fontsize=30, color='white', size=(1280, 720), method='caption', align='center').set_duration(audio_segment.duration_seconds)
                lesson_clips.append(exercise_instructions_clip)

            # Hebrew Narration
            for text in exercise_narration_he:
                tts = gTTS(text=text, lang='iw')
                temp_file = f"temp_he_exercise_{lesson_number}.mp3"
                tts.save(temp_file)
                audio_segment = AudioSegment.from_mp3(temp_file)
                lesson_audio_segments.append(audio_segment)
                os.remove(temp_file)

                # Exercise Instructions Clip (displayed during Hebrew narration)
                exercise_instructions_clip = mp.TextClip(exercise_instructions, fontsize=30, color='white', size=(1280, 720), method='caption', align='center').set_duration(audio_segment.duration_seconds)
                lesson_clips.append(exercise_instructions_clip)

                # Narration Text Clip (Hebrew)
                narration_clip = mp.TextClip(text, fontsize=35, color='yellow', size=(1280, 720), method='caption', align='center').set_duration(audio_segment.duration_seconds)
                lesson_clips.append(narration_clip)

            # English Narration
            for text in exercise_narration_en:
                tts = gTTS(text=text, lang='en')
                temp_file = f"temp_en_exercise_{lesson_number}.mp3"
                tts.save(temp_file)
                audio_segment = AudioSegment.from_mp3(temp_file)
                lesson_audio_segments.append(audio_segment)
                os.remove(temp_file)

                 # Exercise Instructions Clip (displayed during English narration)
                exercise_instructions_clip = mp.TextClip(exercise_instructions, fontsize=30, color='white', size=(1280, 720), method='caption', align='center').set_duration(audio_segment.duration_seconds)
                lesson_clips.append(exercise_instructions_clip)

                # Narration Text Clip (English)
                narration_clip = mp.TextClip(text, fontsize=35, color='cyan', size=(1280, 720), method='caption', align='center').set_duration(audio_segment.duration_seconds)
                lesson_clips.append(narration_clip)

        # Concatenate audio segments sequentially
        lesson_audio = sum(lesson_audio_segments, AudioSegment.empty())

        lesson_audio_file = os.path.join(output_folder, f"lesson_{lesson_number}_audio.mp3")
        lesson_audio.export(lesson_audio_file, format="mp3")

        # Create the video
        video = mp.concatenate_videoclips(lesson_clips, method="compose")
        audio = mp.AudioFileClip(lesson_audio_file)

        # Ensure video duration matches audio duration
        if video.duration < audio.duration:
            # Extend the last clip to match the audio duration
            last_clip_extension = audio.duration - video.duration
            lesson_clips[-1] = lesson_clips[-1].set_duration(lesson_clips[-1].duration + last_clip_extension)
            video = mp.concatenate_videoclips(lesson_clips, method="compose")

        video = video.set_audio(audio)

        sanitized_video_title = sanitize_filename(video_title)
        output_file = os.path.join(output_folder, f"stage_{stage_number}_{sanitized_video_title}.mp4")
        video.write_videofile(output_file, fps=24)

        print(f"Video created: {output_file}")

# Example usage:
create_video_from_json("stage_data.json")