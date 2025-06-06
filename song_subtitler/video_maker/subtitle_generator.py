import os
import json
import re
import urllib.parse
import yaml
from google import genai
from google.genai import types
import datetime

class SubtitleGenerator:

    def __init__(self, api_key, model_name, srt_output_dir, instructions_filepath):
        if not api_key:
            raise ValueError("Gemini API key is required.")
        if not model_name:
            raise ValueError("Gemini model name is required.")
            
        self.api_key = api_key
        self.model_name = model_name
        self.srt_output_dir = srt_output_dir
        self.instructions_filepath = instructions_filepath
        
        self.client = self._initialize_client()
        self.instructions = self._load_instructions(self.instructions_filepath)
        self._ensure_dir_exists(self.srt_output_dir)

    def _ensure_dir_exists(self, dir_path):
        os.makedirs(dir_path, exist_ok=True)

    def _initialize_client(self):
        try:
            # בשינוי האחרון, מספיק להעביר רק api_key או להגדיר את GOOGLE_API_KEY כמשתנה סביבה
            return genai.Client(api_key=self.api_key)
        except Exception as e:
            print(f"Error initializing Gemini client: {e}")
            raise

    def _load_instructions(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                instructions_data = yaml.safe_load(f)
            if not instructions_data:
                raise ValueError(f"Instructions file '{filepath}' is empty or invalid.")
            print(f"System instructions loaded successfully from '{filepath}'")
            return instructions_data
        except FileNotFoundError:
            print(f"CRITICAL ERROR: Instructions file not found at '{filepath}'.")
            raise
        except yaml.YAMLError as e:
            print(f"CRITICAL ERROR: Failed to parse instructions YAML file '{filepath}': {e}")
            raise
        except Exception as e:
            print(f"CRITICAL ERROR: An unexpected error occurred loading instructions file '{filepath}': {e}")
            raise

    def _format_time_srt(self, total_seconds):
        if not isinstance(total_seconds, (int, float)) or total_seconds < 0:
            total_seconds = 0.0
        total_seconds_int = int(total_seconds)
        milliseconds = int(round((total_seconds - total_seconds_int) * 1000))
        if milliseconds >= 1000:
            milliseconds = 999
        dt_object = datetime.timedelta(seconds=total_seconds_int)
        base_time_str = str(dt_object)
        if ',' in base_time_str:
             days_part, hms_part = base_time_str.split(',', 1)
             days = int(days_part.split()[0])
             total_hours_from_days = days * 24
             base_time_str = hms_part.strip()
        else:
             total_hours_from_days = 0
        parts = base_time_str.split(':')
        if '.' in parts[-1]:
             sec_part = parts[-1].split('.')[0]
             parts[-1] = sec_part
        if len(parts) == 3:
             hours = int(parts[0]) + total_hours_from_days
             minutes = int(parts[1])
             seconds = int(parts[2])
        elif len(parts) == 2:
             hours = total_hours_from_days
             minutes = int(parts[0])
             seconds = int(parts[1])
        else:
             hours = total_hours_from_days
             minutes = 0
             seconds = int(parts[0])
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

    def _save_srt_file(self, filepath, subtitle_data, song_name):
        if not subtitle_data:
            print(f"Info: No subtitle data to save for {filepath}")
            return
        try:
            srt_content = []
            for i, sub in enumerate(subtitle_data):
                sub_id = sub.get('id', i + 1)
                start_time_srt = self._format_time_srt(sub.get('start_time', 0.0))
                end_time_srt = self._format_time_srt(sub.get('end_time', 0.0))
                text = sub.get('text', '').strip()
                srt_content.append(str(sub_id))
                srt_content.append(f"{start_time_srt} --> {end_time_srt}")
                srt_content.append(text)
                srt_content.append("")
            full_srt_content = "\n".join(srt_content)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(full_srt_content)
            print(f"SRT file saved successfully to: {filepath}")
        except Exception as e:
            print(f"Error saving SRT file '{filepath}': {e}")

    def _parse_srt_time(self, time_str):
        try:
            parts = time_str.split(',')
            hms_part = parts[0]
            ms_part = int(parts[1])
            hms_parts = hms_part.split(':')
            hours = int(hms_parts[0])
            minutes = int(hms_parts[1])
            seconds = int(hms_parts[2])
            total_seconds = (hours * 3600) + (minutes * 60) + seconds + (ms_part / 1000.0)
            return total_seconds
        except Exception as e:
            print(f"Warning: Could not parse SRT time string '{time_str}': {e}. Returning 0.0")
            return 0.0

    def _load_srt_file(self, filepath):
        if not os.path.exists(filepath):
            return None
        subtitle_data = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
            srt_blocks = re.split(r'\n\s*\n|\r\n\s*\r\n', content)
            for block in srt_blocks:
                if not block.strip():
                    continue
                lines = block.strip().splitlines()
                if lines[0].startswith("#"):
                    lines = lines[1:]
                    if not lines: continue
                if len(lines) < 2:
                    print(f"Warning: Skipping invalid SRT block in '{filepath}' (not enough lines):\n{block}")
                    continue
                try:
                    time_line_index = -1
                    for i, line in enumerate(lines):
                        if re.match(r'\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}', line.strip()):
                            time_line_index = i
                            break
                    if time_line_index == -1:
                        print(f"Warning: Skipping SRT block with no valid time format in '{filepath}':\n{block}")
                        continue
                    if time_line_index > 0 and re.match(r'^\d+$', lines[time_line_index - 1].strip()):
                         sub_id = int(lines[time_line_index - 1].strip())
                    else:
                         sub_id = len(subtitle_data) + 1
                    time_line = lines[time_line_index].strip()
                    text_lines = lines[time_line_index + 1:]
                    if not text_lines:
                        print(f"Warning: Skipping SRT block with no text content after time line in '{filepath}':\n{block}")
                        continue
                    time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', time_line)
                    if not time_match: continue
                    start_time_str = time_match.group(1)
                    end_time_str = time_match.group(2)
                    start_time_float = self._parse_srt_time(start_time_str)
                    end_time_float = self._parse_srt_time(end_time_str)
                    text_content = "\n".join(text_lines).strip()
                    subtitle_data.append({
                        "id": sub_id,
                        "start_time": start_time_float,
                        "end_time": end_time_float,
                        "text": text_content
                    })
                except (ValueError, IndexError) as e:
                    print(f"Warning: Error parsing SRT block in '{filepath}': {e}\nBlock:\n{block}")
                    continue
            return subtitle_data
        except Exception as e:
            print(f"Error reading or parsing SRT file '{filepath}': {e}")
            return None

    def _clean_json_text(self, raw_text):
        pattern = r"```(?:json)?\s*(.*?)\s*```"
        match = re.search(pattern, raw_text, re.DOTALL)
        if match:
            cleaned_content = match.group(1).strip()
            if cleaned_content.startswith('{') and cleaned_content.endswith('}'):
                 try:
                     single_obj = json.loads(cleaned_content)
                     if isinstance(single_obj, dict):
                          print("Warning: Cleaned JSON appears to be a single object, wrapping in a list.")
                          return json.dumps([single_obj])
                 except json.JSONDecodeError:
                     pass
            if cleaned_content.startswith('[') and cleaned_content.endswith(']'):
                 return cleaned_content
            print("Warning: JSON cleaning resulted in content not clearly starting/ending with [] or {}. Proceeding with cleaned text.")
            return cleaned_content
        else:
            return raw_text.strip()

    def _parse_json_response(self, json_text, language_name):
        cleaned_text = self._clean_json_text(json_text)
        if not cleaned_text:
            print(f"Error: JSON text for {language_name} is empty after cleaning.")
            return None
        try:
            data = json.loads(cleaned_text)
            if not isinstance(data, list):
                print(f"Warning: Expected JSON list for {language_name}, but got {type(data)}. Trying to proceed if it's a single dict in a list.")
                if isinstance(data, dict): data = [data]
                else: raise ValueError("JSON response is not a list.")
            processed_data = []
            if data:
                for item_index, item in enumerate(data):
                    if not isinstance(item, dict):
                        raise ValueError(f"Item at index {item_index} in {language_name} JSON list is not a dictionary.")
                    required_keys = {"id", "start_time", "end_time", "text"}
                    missing_keys = required_keys - item.keys()
                    if missing_keys:
                         raise ValueError(f"Dictionary at index {item_index} in {language_name} JSON is missing required keys: {missing_keys}. Found: {item.keys()}")
                    processed_item = {}
                    processed_item['id'] = item['id']
                    processed_item['text'] = item['text']
                    for time_key in ["start_time", "end_time"]:
                        time_value = item.get(time_key)
                        if isinstance(time_value, str) and re.match(r"\d{2}:\d{2}\.\d{3}", time_value):
                            try:
                                minutes, seconds_milliseconds = time_value.split(":")
                                seconds, milliseconds = seconds_milliseconds.split(".")
                                total_seconds = int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000.0
                                processed_item[time_key] = float(total_seconds)
                            except ValueError as e:
                                print(f"Error converting time string '{time_value}' to float in {language_name} for key '{time_key}' at index {item_index}. Setting to 0. Error: {e}")
                                processed_item[time_key] = 0.0
                        elif isinstance(time_value, (int, float)):
                             processed_item[time_key] = float(time_value)
                        else:
                             print(f"Warning: Unexpected time format '{time_value}' (type: {type(time_value)}) in {language_name} for key '{time_key}' at index {item_index}. Setting to 0.")
                             processed_item[time_key] = 0.0
                    processed_data.append(processed_item)
            return processed_data
        except json.JSONDecodeError as e:
            print(f"Error: Failed to decode JSON response for {language_name}. Error: {e}")
            print("--- Received Text (after potential cleaning) ---")
            print(cleaned_text[:500] + "..." if len(cleaned_text) > 500 else cleaned_text)
            print("--- End of Received Text ---")
            return None
        except ValueError as e:
            print(f"Error: Invalid JSON structure or content for {language_name}. Error: {e}")
            try: print(f"--- Received Data Structure (attempted parse) ---\n{data}\n--- End of Received Data Structure ---")
            except NameError: print("(Could not assign data before error)")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during JSON parsing for {language_name}: {e}")
            return None

    def _sanitize_filename_part(self, text, max_len=60):
        if not text: return "unknown"
        text = re.sub(r'[\\/*?:"<>|]', '_', str(text))
        text = re.sub(r'\s+', '_', text).strip('_')
        return text[:max_len]

    def _extract_video_id(self, youtube_url):
        if not youtube_url:
            return None
        try:
            parsed_url = urllib.parse.urlparse(youtube_url)
            if parsed_url.hostname in ('youtu.be',):
                return self._sanitize_filename_part(parsed_url.path[1:], 20)
            if parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
                if parsed_url.path == '/watch':
                    query_params = urllib.parse.parse_qs(parsed_url.query)
                    vid = query_params.get('v', [None])[0]
                    return self._sanitize_filename_part(vid, 20) if vid else None
                if parsed_url.path.startswith(('/embed/', '/v/')):
                    return self._sanitize_filename_part(parsed_url.path.split('/')[2], 20)
        except Exception:
            pass
        return None

    def _calculate_filenames(self, song_name, youtube_url, mp3_audio_path, source_language):
        sanitized_song_name = self._sanitize_filename_part(song_name)
        if not sanitized_song_name or sanitized_song_name == "unknown":
            mp3_basename = os.path.splitext(os.path.basename(mp3_audio_path))[0]
            sanitized_song_name = self._sanitize_filename_part(mp3_basename)
            if not sanitized_song_name or sanitized_song_name == "unknown":
                sanitized_song_name = "untitled_song"
            print(f"Warning: Song name was empty or invalid, using '{sanitized_song_name}' from MP3/fallback for filenames.")
        source_lang_suffix = source_language.lower()
        base_filename_new = f"{sanitized_song_name}"
        source_filename_new = f"{base_filename_new}_{source_lang_suffix}.srt"
        hebrew_filename_new = f"{base_filename_new}_he.srt"
        write_source_path = os.path.join(self.srt_output_dir, source_filename_new)
        write_hebrew_path = os.path.join(self.srt_output_dir, hebrew_filename_new)
        read_source_paths = [write_source_path]
        read_hebrew_paths = [write_hebrew_path]
        if youtube_url:
            video_id = self._extract_video_id(youtube_url)
            if video_id:
                base_filename_legacy = f"{sanitized_song_name}_{video_id}"
                legacy_source_filename = f"{base_filename_legacy}_{source_lang_suffix}.srt"
                legacy_hebrew_filename = f"{base_filename_legacy}_he.srt"
                legacy_source_path = os.path.join(self.srt_output_dir, legacy_source_filename)
                legacy_hebrew_path = os.path.join(self.srt_output_dir, legacy_hebrew_filename)
                if legacy_source_path not in read_source_paths:
                    read_source_paths.append(legacy_source_path)
                if legacy_hebrew_path not in read_hebrew_paths:
                    read_hebrew_paths.append(legacy_hebrew_path)
            else:
                print(f"Info: YouTube URL '{youtube_url}' provided, but could not extract a video ID for legacy filename checking.")
        return (write_source_path, read_source_paths), \
               (write_hebrew_path, read_hebrew_paths)

    def _load_existing_subtitles(self, read_source_paths, read_target_paths, source_language_name):
        source_subs_data, target_subs_data = None, None
        print(f"Attempting to load Source ({source_language_name}) SRTs from: {read_source_paths}")
        for path in read_source_paths:
            if os.path.exists(path):
                print(f"  Trying path: {path}")
                source_subs_data = self._load_srt_file(path)
                if source_subs_data:
                    print(f"  Successfully loaded Source ({source_language_name}) SRT: {path}")
                    break
        if not source_subs_data:
            print(f"  No valid Source ({source_language_name}) SRT found or loaded.")
        print(f"Attempting to load Target (Hebrew) SRTs from: {read_target_paths}")
        for path in read_target_paths:
            if os.path.exists(path):
                print(f"  Trying path: {path}")
                target_subs_data = self._load_srt_file(path)
                if target_subs_data:
                    print(f"  Successfully loaded Target (Hebrew) SRT: {path}")
                    break
        if not target_subs_data:
            print(f"  No valid Target (Hebrew) SRT found or loaded.")
        return source_subs_data, target_subs_data

    def _get_api_config(self, system_instruction_text):
        """Creates a GenerateContentConfig object for the Gemini API call."""
        return types.GenerateContentConfig(
            system_instruction=system_instruction_text,
            response_mime_type="application/json",
            # ניתן להוסיף כאן פרמטרים נוספים (לדוגמה: temperature, max_output_tokens וכו')
        )

    def _call_gemini_api(self, contents, config, language_context):
        print(f"Generating {language_context} Subtitles (via API, model: {self.model_name})...")
        raw_json_output = ""
        try:
            # שימוש ב-param 'config' במקום 'generation_config'
            stream_response = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=config,
            )
            for chunk in stream_response:
                if chunk.text:
                     raw_json_output += chunk.text
                prompt_feedback = getattr(chunk, 'prompt_feedback', None)
                if prompt_feedback and prompt_feedback.block_reason:
                    print(f"Warning: Prompt blocked during streaming for {language_context}. Reason: {prompt_feedback.block_reason}")
        except types.generation_types.BlockedPromptException as bpe:
            print(f"ERROR: Gemini API call for {language_context} was blocked. Reason: {bpe}")
            return None
        except Exception as e:
            print(f"Error during Gemini API stream call for {language_context}: {e}")
            try:
                 if hasattr(e, 'response'):
                      print("Gemini response details (if available):", e.response)
                 elif hasattr(e, 'args') and e.args:
                      print("Exception arguments:", e.args)
            except Exception as report_err:
                 print(f"(Could not report detailed error info: {report_err})")
            return None
        print(f"\n{language_context} JSON stream finished. Parsing response...")
        if raw_json_output:
            return self._parse_json_response(raw_json_output, language_context)
        else:
            print(f"Warning: API stream for {language_context} finished but produced no text output.")
            return None

    def generate_or_load_subtitles(self, source_language, song_name, youtube_url, mp3_audio_path, lyrics_content=None, force_regenerate=False):
        source_language_name = "English" if source_language == 'en' else "Yiddish"
        (write_source_srt_path, read_source_srt_paths), \
        (write_hebrew_srt_path, read_hebrew_srt_paths) = \
            self._calculate_filenames(song_name, youtube_url, mp3_audio_path, source_language)
        source_subs, hebrew_subs = None, None
        if not force_regenerate:
            print("Checking for existing SRT files...")
            source_subs, hebrew_subs = self._load_existing_subtitles(
                read_source_srt_paths, read_hebrew_srt_paths, source_language_name
            )
            if source_subs and hebrew_subs:
                print(f"Both Source ({source_language_name}) and Target (Hebrew) subtitles loaded from existing files.")
                return source_subs, hebrew_subs
        else:
            print("Force regeneration requested. Skipping check for existing SRT files.")

        # Generate Source Subtitles if needed
        if source_subs is None:
            print(f"\n--- Generating Source ({source_language_name}) Subtitles ---")
            if not youtube_url:
                print(f"Cannot generate Source subtitles from API: YouTube URL not provided.")
            else:
                prompt_key = 'yiddish_transcription_system_prompt' if source_language == 'yi' else 'english_transcription_system_prompt'
                system_prompt = self.instructions.get(prompt_key)
                if not system_prompt:
                     print(f"CRITICAL ERROR: '{prompt_key}' not found in instructions YAML.")
                     return None, hebrew_subs

                api_config = self._get_api_config(system_prompt)

                # יצירת החלק הראשון כ-YouTube URL באמצעות FileData
                user_parts = [
                    types.Part(file_data=types.FileData(file_uri=youtube_url))
                ]
                if lyrics_content:
                    print("Adding provided lyrics to the user input for transcription.")
                    user_parts.append(types.Part(text=f"\n\n--- KNOWN LYRICS ---\n{lyrics_content}\n--- END KNOWN LYRICS ---"))
                
                contents = [types.Content(role="user", parts=user_parts)]
                source_subs = self._call_gemini_api(
                    contents=contents,
                    config=api_config,
                    language_context=source_language_name
                )
                if source_subs:
                    print(f"Source ({source_language_name}) subtitles generated successfully from API.")
                    self._save_srt_file(write_source_srt_path, source_subs, song_name)
                else:
                    print(f"Failed to generate valid Source ({source_language_name}) subtitle data from API.")

        # Generate Hebrew Subtitles if needed
        if hebrew_subs is None:
            if not source_subs:
                 print(f"\nCannot generate Hebrew subtitles because Source ({source_language_name}) subtitles are missing or empty.")
                 return source_subs, None
            print("\n--- Generating Hebrew Subtitles (Translation) ---")
            system_prompt = self.instructions.get('generic_translation_system_prompt')
            if not system_prompt:
                 print("CRITICAL ERROR: 'generic_translation_system_prompt' not found in instructions YAML.")
                 return source_subs, None

            api_config = self._get_api_config(system_prompt)
            try:
                source_json_str = json.dumps([
                    {
                        "id": item.get('id', 0),
                        "start_time": f"{int(s:=item.get('start_time',0))//60:02}:{int(s%60):02}.{min(999,int((s-int(s))*1000)):03}",
                        "end_time": f"{int(e:=item.get('end_time',0))//60:02}:{int(e%60):02}.{min(999,int((e-int(e))*1000)):03}",
                        "text": item.get('text', '')
                    } for item in source_subs
                ], ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"Error formatting Source JSON for translation prompt: {e}")
                return source_subs, None

            user_input_template = self.instructions.get('generic_translation_user_input_template')
            if not user_input_template:
                 print("CRITICAL ERROR: 'generic_translation_user_input_template' not found in instructions YAML.")
                 return source_subs, None
            user_prompt = user_input_template.format(source_json_prompt_string=source_json_str)

            hebrew_contents = [types.Content(role="user", parts=[types.Part(text=user_prompt)])]
            hebrew_subs = self._call_gemini_api(
                contents=hebrew_contents,
                config=api_config,
                language_context=f"Hebrew (from {source_language_name})"
            )
            if hebrew_subs:
                print("Hebrew subtitles generated successfully from API.")
                self._save_srt_file(write_hebrew_srt_path, hebrew_subs, song_name)
            else:
                print("Failed to generate valid Hebrew subtitle data from API.")
        
        return source_subs, hebrew_subs
