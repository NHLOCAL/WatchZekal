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
    Saves and loads subtitles in SRT format.
    Optionally uses provided lyrics content to improve transcription.
    Allows forcing regeneration of subtitles.
    Adds song name to SRT filenames for user convenience.
    """
    def __init__(self, api_key, srt_output_dir, instructions_filepath):
        """
        Initializes the SubtitleGenerator.

        Args:
            api_key (str): The Gemini API key.
            srt_output_dir (str): Directory to save/load SRT subtitle files.
            instructions_filepath (str): Path to the YAML file with API instructions.
        """
        if not api_key:
            raise ValueError("Gemini API key is required.")
        self.api_key = api_key
        self.srt_output_dir = srt_output_dir
        self.model_name = "gemini-2.5-pro-exp-03-25" # Keep specified model
        self.client = self._initialize_client()
        self._ensure_dir_exists(self.srt_output_dir)

        self.instructions_filepath = instructions_filepath
        self.instructions = self._load_instructions(self.instructions_filepath)

    def _ensure_dir_exists(self, dir_path):
        """Creates the directory if it doesn't exist."""
        os.makedirs(dir_path, exist_ok=True)

    def _initialize_client(self):
        """Initializes the Gemini client."""
        try:
            # Use Client constructor as in original code
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

        # Handle cases like "1:23:45" or "23:45" or "1 day, 1:23:45"
        if ',' in base_time_str: # Handle timedelta format like "1 day, H:MM:SS"
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
        else: # Should not happen with timedelta, but as fallback
             hours = total_hours_from_days
             minutes = 0
             seconds = int(parts[0])


        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

    def _save_srt_file(self, filepath, subtitle_data, song_name):
        """
        Saves the subtitle data list (dicts with float times) to an SRT file.
        Adds the song name as a comment at the beginning.
        """
        if not subtitle_data:
            print(f"Info: No subtitle data to save for {filepath}")
            # Optionally create an empty file or just skip
            # with open(filepath, "w", encoding="utf-8") as f: f.write("")
            return
        try:
            srt_content = []
            # Add song name comment (non-standard SRT, but useful for humans)
            # Some players might ignore lines not starting with a number or time.
            # Alternative: Add it to the filename only. Let's stick to filename only for compatibility.
            # srt_content.append(f"# Song: {song_name}\n")

            for i, sub in enumerate(subtitle_data):
                sub_id = sub.get('id', i + 1)
                start_time_srt = self._format_time_srt(sub.get('start_time', 0.0))
                end_time_srt = self._format_time_srt(sub.get('end_time', 0.0))
                text = sub.get('text', '').strip()

                srt_content.append(str(sub_id))
                srt_content.append(f"{start_time_srt} --> {end_time_srt}")
                srt_content.append(text)
                srt_content.append("") # Blank line separator

            full_srt_content = "\n".join(srt_content)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(full_srt_content)
            print(f"SRT file saved successfully to: {filepath}")

        except Exception as e:
            print(f"Error saving SRT file '{filepath}': {e}")


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

            # Regex to handle different line endings and potential extra whitespace
            srt_blocks = re.split(r'\n\s*\n|\r\n\s*\r\n', content)

            for block in srt_blocks:
                if not block.strip():
                    continue

                lines = block.strip().splitlines()

                # Skip potential comment lines added manually (or by previous versions)
                if lines[0].startswith("#"):
                    print(f"Skipping comment line in SRT: {lines[0]}")
                    lines = lines[1:]
                    if not lines: continue

                if len(lines) < 3:
                    print(f"Warning: Skipping invalid SRT block in '{filepath}':\n{block}")
                    continue

                try:
                    # Find the ID and time lines robustly
                    id_line_index = -1
                    time_line_index = -1
                    for i, line in enumerate(lines):
                        if re.match(r'^\d+$', line.strip()):
                            id_line_index = i
                        elif re.match(r'\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}', line.strip()):
                            time_line_index = i
                            break # Found time, assume ID was before or is the first line

                    if time_line_index == -1:
                        print(f"Warning: Skipping SRT block with no valid time format in '{filepath}':\n{block}")
                        continue

                    # Assume ID is the line before time, or the first line if time is line 1
                    if id_line_index == -1:
                        if time_line_index > 0 and re.match(r'^\d+$', lines[time_line_index - 1].strip()):
                             id_line_index = time_line_index - 1
                        elif re.match(r'^\d+$', lines[0].strip()):
                             id_line_index = 0
                        else:
                             print(f"Warning: Could not determine subtitle ID for block in '{filepath}'. Assigning sequential ID.\n{block}")
                             sub_id = len(subtitle_data) + 1 # Assign sequential ID if missing
                             id_line_index = -1 # Mark as not found from file
                    else:
                         sub_id = int(lines[id_line_index].strip())


                    time_line = lines[time_line_index].strip()
                    text_lines = lines[time_line_index + 1:]

                    time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', time_line)
                    # Should always match due to check above, but keep for safety
                    if not time_match: continue

                    start_time_str = time_match.group(1)
                    end_time_str = time_match.group(2)

                    start_time_float = self._parse_srt_time(start_time_str)
                    end_time_float = self._parse_srt_time(end_time_str)

                    text_content = "\n".join(text_lines).strip()

                    # Use the ID found in the file, or the generated sequential one
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
                 print(f"Warning: No valid subtitle entries found or parsed in SRT file: {filepath}")
            return subtitle_data

        except Exception as e:
            print(f"Error reading or parsing SRT file '{filepath}': {e}")
            return None

    # --- INTERNAL API/JSON Handling (Remains unchanged as requested) ---
    def _clean_json_text(self, raw_text):
        """Removes potential Markdown fences (```json ... ```) from the raw text."""
        pattern = r"```(?:json)?\s*(.*?)\s*```"
        match = re.search(pattern, raw_text, re.DOTALL)
        if match:
            cleaned_content = match.group(1).strip()
            return cleaned_content
        else:
            # Also remove potential leading/trailing whitespace or newlines
            return raw_text.strip()

    def _parse_json_response(self, json_text, language_name):
        """
        Parses JSON response FROM API, validates structure, and returns the list.
        Converts API's "MM:SS.ms" time strings to float seconds internally.
        """
        cleaned_text = self._clean_json_text(json_text)
        if not cleaned_text:
            print(f"Error: JSON text for {language_name} is empty after cleaning.")
            return None
        try:
            data = json.loads(cleaned_text)
            if not isinstance(data, list):
                print(f"Warning: Expected JSON list for {language_name}, but got {type(data)}. Trying to proceed if it's a single dict in a list.")
                if isinstance(data, dict): data = [data] # Handle case where API returns single object instead of array
                else: raise ValueError("JSON response is not a list.")

            processed_data = []
            if data:
                for item_index, item in enumerate(data):
                    if not isinstance(item, dict):
                        raise ValueError(f"Item at index {item_index} in {language_name} JSON list is not a dictionary.")

                    # Ensure required keys exist
                    required_keys = {"id", "start_time", "end_time", "text"}
                    missing_keys = required_keys - item.keys()
                    if missing_keys:
                         raise ValueError(f"Dictionary at index {item_index} in {language_name} JSON is missing required keys: {missing_keys}. Found: {item.keys()}")

                    processed_item = {}
                    processed_item['id'] = item['id']
                    processed_item['text'] = item['text']

                    # Convert time strings to floats
                    for time_key in ["start_time", "end_time"]:
                        time_value = item.get(time_key) # Already checked existence
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
                             processed_item[time_key] = float(time_value) # Ensure it's float
                        else:
                             print(f"Warning: Unexpected time format '{time_value}' (type: {type(time_value)}) in {language_name} for key '{time_key}' at index {item_index}. Setting to 0.")
                             processed_item[time_key] = 0.0
                    processed_data.append(processed_item)
            return processed_data # Return list of dicts with float times
        except json.JSONDecodeError as e:
            print(f"Error: Failed to decode JSON response for {language_name}. Error: {e}")
            print("--- Received Text (after potential cleaning) ---")
            print(cleaned_text[:500] + "..." if len(cleaned_text) > 500 else cleaned_text)
            print("--- End of Received Text ---")
            return None
        except ValueError as e:
            print(f"Error: Invalid JSON structure or content for {language_name}. Error: {e}")
            print("--- Received Data Structure (attempted parse) ---")
            try: print(data)
            except NameError: print("(Could not assign data before error)")
            print("--- End of Received Data Structure ---")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during JSON parsing for {language_name}: {e}")
            return None

    # --- FILENAME CALCULATION (Changed to include song name) ---
    def _sanitize_filename_part(self, text, max_len=60):
        """Sanitizes text for use in filenames."""
        if not text: return "unknown"
        # Remove invalid characters
        text = re.sub(r'[\\/*?:"<>|]', '_', str(text))
        # Replace whitespace with underscore
        text = re.sub(r'\s+', '_', text).strip('_')
        # Limit length
        return text[:max_len]

    def _calculate_filenames(self, song_name, youtube_url, mp3_audio_path):
        """Calculates the expected SRT filenames based on Song Name and YouTube ID/MP3."""
        sanitized_song_name = self._sanitize_filename_part(song_name)

        # Prioritize YouTube ID for uniqueness if available
        video_id = None
        try:
            parsed_url = urllib.parse.urlparse(youtube_url)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            vid = query_params.get('v')
            if vid and vid[0]:
                video_id = self._sanitize_filename_part(vid[0], 20) # Sanitize and shorten ID
        except Exception:
             pass # Ignore URL parsing errors

        if video_id:
            base_identifier = video_id
        else:
            # Fallback to sanitized MP3 filename base
            mp3_basename = os.path.splitext(os.path.basename(mp3_audio_path))[0]
            base_identifier = self._sanitize_filename_part(mp3_basename)
            print(f"Warning: Could not extract Video ID from URL '{youtube_url}'. Using sanitized name from MP3: '{base_identifier}' for filename uniqueness.")

        # Construct filename: SongName_Identifier_lang.srt
        base_filename = f"{sanitized_song_name}_{base_identifier}"

        english_srt_filename = os.path.join(self.srt_output_dir, f"{base_filename}_en.srt")
        hebrew_srt_filename = os.path.join(self.srt_output_dir, f"{base_filename}_he.srt")
        return english_srt_filename, hebrew_srt_filename

    # --- LOADING EXISTING (Modified to return partial results) ---
    def _load_existing_subtitles(self, en_path, he_path):
        """
        Attempts to load subtitles from existing SRT files.
        Returns a tuple (english_data, hebrew_data), where either can be None if not found/loaded.
        """
        english_subs_data = None
        hebrew_subs_data = None
        found_en = False
        found_he = False

        if os.path.exists(en_path):
            print(f"Found existing English SRT: {en_path}")
            english_subs_data = self._load_srt_file(en_path)
            found_en = True
            if english_subs_data is None:
                print(f"Warning: Failed to parse existing English SRT: {en_path}")
            elif not english_subs_data:
                 print(f"Warning: Existing English SRT file is empty or contains no valid entries: {en_path}")


        if os.path.exists(he_path):
            print(f"Found existing Hebrew SRT: {he_path}")
            hebrew_subs_data = self._load_srt_file(he_path)
            found_he = True
            if hebrew_subs_data is None:
                print(f"Warning: Failed to parse existing Hebrew SRT: {he_path}")
            elif not hebrew_subs_data:
                 print(f"Warning: Existing Hebrew SRT file is empty or contains no valid entries: {he_path}")

        if not found_en and not found_he:
            print("No existing SRT files found.")
        elif found_en and found_he and english_subs_data is not None and hebrew_subs_data is not None:
             print("Both English and Hebrew SRTs loaded successfully.")
        elif found_en and english_subs_data is not None:
             print("Only English SRT loaded successfully.")
        elif found_he and hebrew_subs_data is not None:
             print("Only Hebrew SRT loaded successfully.")
        else:
             print("Found SRT file(s), but failed to load/parse at least one correctly.")


        return english_subs_data, hebrew_subs_data

    # --- API Call Logic (Remains unchanged) ---
    def _call_gemini_api(self, contents, config, language_context):
        """Handles the streaming call to the Gemini API."""
        print(f"Generating {language_context} Subtitles (via API, expecting JSON)...")
        raw_json_output = ""
        try:
            # Use generate_content_stream as in original code
            stream_response = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=config,
            )
            for chunk in stream_response:
                # Append text directly as in original code
                if chunk.text:
                     raw_json_output += chunk.text

        except types.generation_types.BlockedPromptException as e:
             print(f"Error: Prompt was blocked for {language_context} generation. Reason: {e}")
             return None
        except types.generation_types.StopCandidateException as e:
             print(f"Error: Generation stopped unexpectedly for {language_context}. Reason: {e}")
             # Original code might have handled this differently, but returning None is safe.
             return None
        except Exception as e:
            print(f"Error during Gemini API stream call for {language_context}: {e}")
            # Try to report details if available
            try:
                 if hasattr(e, 'response'):
                      print("Gemini response details (if available):", e.response)
            except Exception as report_err:
                 print(f"(Could not report detailed error info: {report_err})")
            return None

        print(f"\n{language_context} JSON stream finished. Parsing response...")
        return self._parse_json_response(raw_json_output, language_context)

    # --- API Config (Remains unchanged) ---
    def _get_api_config(self):
        """Returns the generation config with the required schema."""
        # Use the exact structure from the original code
        return types.GenerateContentConfig(
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_CIVIC_INTEGRITY",
                    threshold="OFF", # Assuming "OFF" means disable/block less
                ),
            ],
            temperature=1.0,
            response_mime_type="application/json", # Crucial
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
                            description = "זמן התחלת הכתובית בפורמט מחרוזת 'MM:SS.milliseconds'.",
                            pattern=r"^\d{2}:\d{2}\.\d{3}$" # Keep pattern
                        ),
                        "end_time": genai.types.Schema(
                            type = genai.types.Type.STRING,
                            description = "זמן סיום הכתובית בפורמט מחרוזת 'MM:SS.milliseconds'.",
                            pattern=r"^\d{2}:\d{2}\.\d{3}$" # Keep pattern
                        ),
                        "text": genai.types.Schema(
                            type = genai.types.Type.STRING,
                            description = "תוכן הכתובית.", # Simplified description ok
                        ),
                    },
                ),
            ),
        )

    # --- MAIN FUNCTION (Updated logic for conditional generation, lyrics, force flag) ---
    def generate_or_load_subtitles(self, song_name, youtube_url, mp3_audio_path, lyrics_content=None, force_regenerate=False):
        """
        Generates subtitles using Gemini API or loads them if SRT files exist.
        Saves generated subtitles as SRT files with song name in the filename.
        Optionally uses lyrics_content for transcription.
        Allows forcing regeneration.

        Args:
            song_name (str): The name of the song (used for filenames).
            youtube_url (str): The YouTube URL of the video.
            mp3_audio_path (str): Path to the MP3 audio file (used for fallback naming).
            lyrics_content (str, optional): String containing song lyrics. Defaults to None.
            force_regenerate (bool, optional): If True, ignore existing SRTs and regenerate. Defaults to False.

        Returns:
            tuple: (list | None, list | None): A tuple containing the English
                   subtitle data (list of dicts with float times) and Hebrew subtitle data.
                   Returns (None, None) or (data, None) / (None, data) on errors or partial success.
        """
        english_srt_path, hebrew_srt_path = self._calculate_filenames(song_name, youtube_url, mp3_audio_path)

        english_subs = None
        hebrew_subs = None

        if not force_regenerate:
            print("Checking for existing SRT files...")
            english_subs, hebrew_subs = self._load_existing_subtitles(english_srt_path, hebrew_srt_path)
            # If both loaded successfully, we are done
            if english_subs is not None and hebrew_subs is not None:
                print("Both English and Hebrew subtitles loaded from existing files.")
                return english_subs, hebrew_subs
            # If loading failed for some reason (e.g., parse error), treat as missing
            if english_subs is None:
                 print("Will attempt to generate English subtitles.")
            if hebrew_subs is None:
                 print("Will attempt to generate Hebrew subtitles.")
        else:
            print("Force regeneration requested. Skipping check for existing SRT files.")

        # --- English Generation ---
        if english_subs is None: # Generate only if not loaded successfully
            print("\n--- Generating English Subtitles ---")
            generate_content_config = self._get_api_config() # Get config just before API call

            transcription_prompt_text = self.instructions.get('transcription_prompt')
            if not transcription_prompt_text:
                 print("CRITICAL ERROR: 'transcription_prompt' not found in instructions YAML.")
                 return None, hebrew_subs # Return whatever Hebrew subs we might have loaded

            # Prepare contents for English API call
            parts_english = [
                types.Part.from_uri(
                    file_uri=youtube_url,
                    mime_type="video/*", # Use video/* as in original
                )
            ]
            # Add lyrics if provided
            if lyrics_content:
                print("Adding provided lyrics to the transcription request.")
                parts_english.append(types.Part.from_text(text=f"\n\n--- KNOWN LYRICS ---\n{lyrics_content}\n--- END KNOWN LYRICS ---"))

            # Add the main instruction prompt
            parts_english.append(types.Part.from_text(text=transcription_prompt_text))

            contents_english = [types.Content(role="user", parts=parts_english)]

            english_subs_data_from_api = self._call_gemini_api(contents_english, generate_content_config, "English")

            if english_subs_data_from_api is None:
                print("Failed to generate valid English subtitle data from API. Cannot proceed with translation if Hebrew is also missing.")
                # Return None for English, keep potentially loaded Hebrew
                return None, hebrew_subs
            else:
                english_subs = english_subs_data_from_api # Use the newly generated data
                print("English subtitles generated successfully.")
                self._save_srt_file(english_srt_path, english_subs, song_name)
        else:
             print("\nSkipping English subtitle generation (already loaded).")

        # --- Hebrew Generation ---
        if hebrew_subs is None: # Generate only if not loaded successfully
            if english_subs is None or not english_subs: # Check if we have English subs to translate from
                 print("\nCannot generate Hebrew subtitles because English subtitles are missing or empty.")
                 return english_subs, None # Return loaded/generated English, None for Hebrew

            print("\n--- Generating Hebrew Subtitles ---")
            generate_content_config = self._get_api_config() # Get config again

            # Format English subs back into the specific JSON string format expected by the translation prompt
            try:
                english_json_for_prompt = []
                for item in english_subs:
                     # Convert float seconds back to "MM:SS.ms" string format for the prompt
                     start_s = item.get('start_time', 0.0)
                     end_s = item.get('end_time', 0.0)
                     start_min, start_sec_rem = divmod(start_s, 60)
                     start_sec, start_ms = divmod(start_sec_rem, 1)
                     end_min, end_sec_rem = divmod(end_s, 60)
                     end_sec, end_ms = divmod(end_sec_rem, 1)
                     start_ms_int = min(999, int(round(start_ms * 1000)))
                     end_ms_int = min(999, int(round(end_ms * 1000)))
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
                return english_subs, None # Return generated English, None for Hebrew

            translation_prompt_template = self.instructions.get('translation_prompt_template')
            if not translation_prompt_template:
                 print("CRITICAL ERROR: 'translation_prompt_template' not found in instructions YAML.")
                 return english_subs, None # Return generated English, None for Hebrew

            translation_prompt_text = translation_prompt_template.format(
                english_json_prompt_string=english_json_prompt_string
            )

            # Prepare contents for Hebrew API call (Text only)
            contents_hebrew = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=translation_prompt_text)],
                ),
            ]

            hebrew_subs_data_from_api = self._call_gemini_api(contents_hebrew, generate_content_config, "Hebrew")

            if hebrew_subs_data_from_api is None:
                print("Failed to generate valid Hebrew subtitle data from API.")
                hebrew_subs = None # Ensure it's None
            else:
                hebrew_subs = hebrew_subs_data_from_api # Use newly generated data
                print("Hebrew subtitles generated successfully.")
                self._save_srt_file(hebrew_srt_path, hebrew_subs, song_name)
        else:
             print("\nSkipping Hebrew subtitle generation (already loaded).")

        return english_subs, hebrew_subs