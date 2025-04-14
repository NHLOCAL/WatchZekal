import os
import json
import re
import urllib.parse
import yaml
from google import genai
from google.genai import types
import datetime # Needed for SRT time formatting

class SubtitleGenerator:
    """
    Handles the generation or loading of subtitles using the Gemini API.
    Saves and loads subtitles in SRT format instead of JSON.
    Ensures the specific API structure and response format are maintained internally.
    Loads system instructions from an external YAML file.
    """
    # --- CORRECTED __init__ ---
    def __init__(self, api_key, srt_output_dir, instructions_filepath):
        """
        Initializes the SubtitleGenerator.

        Args:
            api_key (str): The Gemini API key.
            srt_output_dir (str): Directory to save/load SRT subtitle files.
                                   (Parameter name matches caller, value used for SRTs)
        """
        if not api_key:
            raise ValueError("Gemini API key is required.")
        self.api_key = api_key
        # Assign the passed value (which came via 'srt_output_dir' keyword)
        # to the internal variable. The name 'self.srt_output_dir' is kept for internal consistency
        # with the original structure, even though it now points to the SRT directory.
        self.srt_output_dir = srt_output_dir
        self.model_name = "gemini-2.5-pro-exp-03-25"
        self.client = self._initialize_client()
        self._ensure_dir_exists(self.srt_output_dir)

        self.instructions_filepath = instructions_filepath
        self.instructions = self._load_instructions(self.instructions_filepath)
    # --- END OF CORRECTION ---

    def _ensure_dir_exists(self, dir_path):
        """Creates the directory if it doesn't exist."""
        os.makedirs(dir_path, exist_ok=True)

    def _initialize_client(self):
        """Initializes the Gemini client."""
        try:
            return genai.Client(api_key=self.api_key)
        except Exception as e:
            print(f"Error initializing Gemini client: {e}")
            raise

    def _load_instructions(self, filepath):
        """Loads instructions from the specified YAML file."""
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

    # --- SRT FORMATTING HELPER ---
    def _format_time_srt(self, total_seconds):
        """Converts total seconds (float) to SRT time format HH:MM:SS,ms."""
        if not isinstance(total_seconds, (int, float)) or total_seconds < 0:
            total_seconds = 0.0
        total_seconds_int = int(total_seconds)
        milliseconds = int(round((total_seconds - total_seconds_int) * 1000))
        if milliseconds >= 1000:
            milliseconds = 999

        dt_object = datetime.timedelta(seconds=total_seconds_int)
        base_time_str = str(dt_object)

        parts = base_time_str.split(':')
        if '.' in parts[-1]:
             sec_part = parts[-1].split('.')[0]
             parts[-1] = sec_part

        hours = int(parts[0]) if len(parts) == 3 else 0
        minutes = int(parts[-2])
        seconds = int(parts[-1])

        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

    # --- SRT SAVING FUNCTION ---
    def _save_srt_file(self, filepath, subtitle_data):
        """Saves the subtitle data list (dicts with float times) to an SRT file."""
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


    # --- SRT LOADING/PARSING FUNCTION ---
    def _parse_srt_time(self, time_str):
        """Parses SRT time format HH:MM:SS,ms into float seconds."""
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
        """Loads and parses an SRT file into the internal list-of-dicts format."""
        if not os.path.exists(filepath):
            return None

        print(f"Attempting to load SRT file: {filepath}")
        subtitle_data = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()

            srt_blocks = re.split(r'\n\s*\n|\r\n\s*\r\n', content)

            for block in srt_blocks:
                if not block.strip():
                    continue

                lines = block.strip().splitlines()
                if len(lines) < 3:
                    print(f"Warning: Skipping invalid SRT block in '{filepath}':\n{block}")
                    continue

                try:
                    sub_id = int(lines[0])
                    time_line = lines[1]
                    text_lines = lines[2:]

                    time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', time_line)
                    if not time_match:
                        print(f"Warning: Skipping SRT block with invalid time format in '{filepath}': {time_line}")
                        continue

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

            if subtitle_data:
                 print(f"Successfully loaded and parsed {len(subtitle_data)} entries from SRT: {filepath}")
            else:
                 print(f"Warning: No valid subtitle entries found in SRT file: {filepath}")
            return subtitle_data

        except Exception as e:
            print(f"Error reading or parsing SRT file '{filepath}': {e}")
            return None

    # --- INTERNAL API/JSON Handling (No changes needed here as per request) ---
    def _clean_json_text(self, raw_text):
        """Removes potential Markdown fences (```json ... ```) from the raw text."""
        pattern = r"```(?:json)?\s*(.*?)\s*```"
        match = re.search(pattern, raw_text, re.DOTALL)
        if match:
            cleaned_content = match.group(1).strip()
            return cleaned_content
        else:
            return raw_text.strip()

    def _parse_json_response(self, json_text, language_name):
        """
        Parses JSON response FROM API, validates structure, and returns the list.
        Handles timecodes in "MM:SS.milliseconds" format and converts them to seconds *within this parser*.
        This produces the internal format needed by the rest of the application.
        (Function remains unchanged as API interaction and internal format are stable)
        """
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

            if data:
                for item in data: # Iterate through each item to process timestamps
                    if not isinstance(item, dict):
                        raise ValueError(f"Items in {language_name} JSON list are not dictionaries.")
                    required_keys = {"start_time", "end_time", "text"}
                    if not required_keys.issubset(item.keys()):
                        if 'id' not in item.keys():
                             print(f"Warning: Dictionary in {language_name} JSON is missing required key 'id'. Found: {item.keys()}")
                        else:
                             raise ValueError(f"Dictionary in {language_name} JSON is missing required keys ({required_keys}). Found: {item.keys()}")


                    for time_key in ["start_time", "end_time"]:
                        time_value = item.get(time_key)
                        if time_value is None:
                            print(f"Warning: Missing time key '{time_key}' in an item for {language_name}. Setting to 0.0")
                            item[time_key] = 0.0
                            continue

                        if isinstance(time_value, str):
                            if re.match(r"\d{2}:\d{2}\.\d{3}", time_value):
                                try:
                                    minutes, seconds_milliseconds = time_value.split(":")
                                    seconds, milliseconds = seconds_milliseconds.split(".")
                                    total_seconds = int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000.0
                                    item[time_key] = float(total_seconds)
                                except ValueError:
                                    print(f"Warning: Could not parse expected time string '{time_value}' in {language_name} for {time_key}. Keeping as string.")
                            else:
                                print(f"Warning: Time value '{time_value}' in {language_name} for {time_key} is a string but not in expected MM:SS.milliseconds format. Attempting float conversion.")
                                try:
                                    item[time_key] = float(time_value)
                                except ValueError:
                                    print(f"Error: Could not convert time string '{time_value}' to float in {language_name} for {time_key}. Setting to 0.")
                                    item[time_key] = 0.0
                        elif not isinstance(time_value, (int, float)):
                            print(f"Warning: Timestamps in {language_name} JSON are not strings or numbers (int/float). Found: {type(time_value)} for {time_key}. Attempting conversion to float.")
                            try:
                                item[time_key] = float(time_value)
                            except ValueError:
                                print(f"Error: Could not convert timestamp to float in {language_name} for {time_key}. Setting to 0.")
                                item[time_key] = 0.0

            return data
        except json.JSONDecodeError as e:
            print(f"Error: Failed to decode JSON response for {language_name}. Error: {e}")
            print("--- Received Text (after potential cleaning) ---")
            print(cleaned_text[:500] + "..." if len(cleaned_text) > 500 else cleaned_text)
            print("--- End of Received Text ---")
            return None
        except ValueError as e:
            print(f"Error: Invalid JSON structure for {language_name}. Error: {e}")
            print("--- Received Data Structure ---")
            try: print(data)
            except NameError: print("(Could not assign data before error)")
            print("--- End of Received Data Structure ---")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during JSON parsing for {language_name}: {e}")
            return None

    # --- FILENAME CALCULATION (Changed to SRT) ---
    def _calculate_filenames(self, youtube_url, mp3_audio_path):
        """Calculates the expected SRT filenames based on YouTube URL or MP3 path."""
        try:
            parsed_url = urllib.parse.urlparse(youtube_url)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            video_id = query_params.get('v')
            if video_id:
                base_filename = video_id[0]
            else:
                mp3_basename = os.path.splitext(os.path.basename(mp3_audio_path))[0]
                safe_basename = re.sub(r'[\\/*?:"<>|]', '_', mp3_basename)
                safe_basename = re.sub(r'\s+', '_', safe_basename).strip('_')
                base_filename = safe_basename if safe_basename else "audio_file"
                print(f"Warning: Could not extract Video ID from URL. Using sanitized name from MP3: {base_filename}")
        except Exception as e:
            print(f"Warning: Error parsing URL or deriving base filename: {e}. Using sanitized name from MP3.")
            mp3_basename = os.path.splitext(os.path.basename(mp3_audio_path))[0]
            safe_basename = re.sub(r'[\\/*?:"<>|]', '_', mp3_basename)
            safe_basename = re.sub(r'\s+', '_', safe_basename).strip('_')
            base_filename = safe_basename if safe_basename else "audio_file"

        # Use the same output directory variable name but change the extension
        english_srt_filename = os.path.join(self.srt_output_dir, f"{base_filename}_en.srt")
        hebrew_srt_filename = os.path.join(self.srt_output_dir, f"{base_filename}_he.srt")
        return english_srt_filename, hebrew_srt_filename

    # --- LOADING EXISTING (Changed to SRT) ---
    def _load_existing_subtitles(self, en_path, he_path):
        """Attempts to load subtitles from existing SRT files."""
        if os.path.exists(en_path) and os.path.exists(he_path):
            print(f"\nFound existing SRT files:\n  EN: {en_path}\n  HE: {he_path}")
            print("Attempting to load existing SRT files...")

            english_subs_data = self._load_srt_file(en_path)
            hebrew_subs_data = self._load_srt_file(he_path)

            if english_subs_data is not None and hebrew_subs_data is not None:
                if not english_subs_data and not hebrew_subs_data:
                     print("Warning: Both existing SRT files parsed successfully but contain no valid entries.")
                elif not english_subs_data:
                     print("Warning: Existing English SRT file parsed successfully but contains no valid entries.")
                elif not hebrew_subs_data:
                     print("Warning: Existing Hebrew SRT file parsed successfully but contains no valid entries.")
                else:
                    print("Subtitle data successfully loaded and parsed from existing SRT files.")
                return english_subs_data, hebrew_subs_data
            else:
                print("Warning: Failed to load or parse one or both existing SRT files correctly. Proceeding to generate new subtitles.")
                return None, None
        else:
            return None, None

    # --- API Call Logic (No changes needed here) ---
    def _call_gemini_api(self, contents, config, language_context):
        """Handles the streaming call to the Gemini API."""
        print(f"Generating {language_context} Subtitles (via API, expecting JSON)...")
        raw_json_output = ""
        try:
            stream_response = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=config,
            )
            for chunk in stream_response:
                if chunk.text:
                     raw_json_output += chunk.text

        except types.generation_types.BlockedPromptException as e:
             print(f"Error: Prompt was blocked for {language_context} generation. Reason: {e}")
             return None
        except types.generation_types.StopCandidateException as e:
             print(f"Error: Generation stopped unexpectedly for {language_context}. Reason: {e}")
             return None
        except Exception as e:
            print(f"Error during Gemini API stream call for {language_context}: {e}")
            try:
                 if hasattr(e, 'response'):
                      print("Gemini response details (if available):", e.response)
            except Exception as report_err:
                 print(f"(Could not report detailed error info: {report_err})")
            return None

        print(f"\n{language_context} JSON stream finished. Parsing response...")
        return self._parse_json_response(raw_json_output, language_context)

    # --- API Config (No changes needed here) ---
    def _get_api_config(self):
        """Returns the generation config with the required schema."""
        return types.GenerateContentConfig(
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_CIVIC_INTEGRITY",
                    threshold="OFF",
                ),
            ],
            temperature=1.0,
            response_mime_type="application/json",
            response_schema=genai.types.Schema(
                type = genai.types.Type.ARRAY,
                items = genai.types.Schema(
                    type = genai.types.Type.OBJECT,
                    required = ["id", "start_time", "end_time", "text"],
                    properties = {
                        "id": genai.types.Schema(
                            type = genai.types.Type.INTEGER,
                            description = "מספר סידורי של הכתובית",
                        ),
                        "start_time": genai.types.Schema(
                            type = genai.types.Type.STRING,
                            description = "זמן התחלת הכתובית בפורמט מחרוזת 'MM:SS.milliseconds' (לדוגמה '02:30.110').",
                            pattern=r"^\d{2}:\d{2}\.\d{3}$"
                        ),
                        "end_time": genai.types.Schema(
                            type = genai.types.Type.STRING,
                            description = "זמן סיום הכתובית בפורמט מחרוזת 'MM:SS.milliseconds' (לדוגמה '02:35.800').",
                            pattern=r"^\d{2}:\d{2}\.\d{3}$"
                        ),
                        "text": genai.types.Schema(
                            type = genai.types.Type.STRING,
                            description = "תוכן הכתובית, יכול להכיל תוכן קצר בעל שורה או שתיים עם הפרדה `\\n`",
                        ),
                    },
                ),
            ),
        )

    # --- MAIN FUNCTION (Updated to load/save SRT) ---
    def generate_or_load_subtitles(self, youtube_url, mp3_audio_path):
        """
        Generates subtitles using Gemini API or loads them if SRT files exist.
        Saves generated subtitles as SRT files.

        Args:
            youtube_url (str): The YouTube URL of the video.
            mp3_audio_path (str): Path to the MP3 audio file (used for fallback naming).

        Returns:
            tuple: (list | None, list | None): A tuple containing the English
                   subtitle data (list of dicts with float times) and Hebrew subtitle data
                   (list of dicts with float times). This internal format is returned
                   regardless of whether data was loaded from SRT or generated via API.
                   Returns (None, None) or (data, None) / (None, data) on errors.
        """
        english_srt_path, hebrew_srt_path = self._calculate_filenames(youtube_url, mp3_audio_path)

        english_subs, hebrew_subs = self._load_existing_subtitles(english_srt_path, hebrew_srt_path)
        if english_subs is not None or hebrew_subs is not None:
            return english_subs, hebrew_subs

        print("\nExisting SRT files not found or invalid. Starting generation process via API...")

        generate_content_config = self._get_api_config()

        transcription_prompt_text = self.instructions.get('transcription_prompt')
        if not transcription_prompt_text:
             print("CRITICAL ERROR: 'transcription_prompt' not found in instructions YAML.")
             return None, None

        contents_english = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_uri(
                        file_uri=youtube_url,
                        mime_type="video/*",
                    ),
                    types.Part.from_text(text=transcription_prompt_text),
                ],
            ),
        ]

        english_subs_data = self._call_gemini_api(contents_english, generate_content_config, "English")

        if english_subs_data is None:
            print("Failed to generate valid English subtitle data from API. Cannot proceed.")
            return None, None

        self._save_srt_file(english_srt_path, english_subs_data)

        try:
            english_json_for_prompt = []
            for item in english_subs_data:
                 start_s = item.get('start_time', 0.0)
                 end_s = item.get('end_time', 0.0)

                 start_min, start_sec_rem = divmod(start_s, 60)
                 start_sec, start_ms = divmod(start_sec_rem, 1)
                 end_min, end_sec_rem = divmod(end_s, 60)
                 end_sec, end_ms = divmod(end_sec_rem, 1)
                 start_ms_int = int(round(start_ms * 1000))
                 end_ms_int = int(round(end_ms * 1000))
                 if start_ms_int >= 1000: start_ms_int = 999
                 if end_ms_int >= 1000: end_ms_int = 999
                 start_time_str_api = f"{int(start_min):02}:{int(start_sec):02}.{start_ms_int:03}"
                 end_time_str_api = f"{int(end_min):02}:{int(end_sec):02}.{end_ms_int:03}"

                 english_json_for_prompt.append({
                     "id": item.get('id', 0),
                     "start_time": start_time_str_api,
                     "end_time": end_time_str_api,
                     "text": item.get('text', '')
                 })
            english_json_prompt_string = json.dumps(english_json_for_prompt, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error formatting English JSON for translation prompt: {e}")
            return english_subs_data, None


        translation_prompt_template = self.instructions.get('translation_prompt_template')
        if not translation_prompt_template:
             print("CRITICAL ERROR: 'translation_prompt_template' not found in instructions YAML.")
             return english_subs_data, None

        translation_prompt_text = translation_prompt_template.format(
            english_json_prompt_string=english_json_prompt_string
        )

        contents_hebrew = [
            types.Content(
                role="user",
                parts=[
                     types.Part.from_text(text=translation_prompt_text),
                ],
            ),
        ]

        hebrew_subs_data = self._call_gemini_api(contents_hebrew, generate_content_config, "Hebrew")

        if hebrew_subs_data is None:
            print("Failed to generate valid Hebrew subtitle data from API.")
            return english_subs_data, None

        self._save_srt_file(hebrew_srt_path, hebrew_subs_data)

        return english_subs_data, hebrew_subs_data
# END OF FILE: subtitle_generator.py