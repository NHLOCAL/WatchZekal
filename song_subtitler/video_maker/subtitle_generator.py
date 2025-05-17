import os
import json
import re
import urllib.parse
import yaml
from google import genai # Using the original import structure
from google.genai import types # Using the original import structure
import datetime # Needed for SRT time formatting

class SubtitleGenerator:
    """
    Handles the generation or loading of subtitles using the Gemini API.
    Saves and loads subtitles in SRT format.
    Optionally uses provided lyrics content to improve transcription.
    Allows forcing regeneration of subtitles.
    Adds song name to SRT filenames for user convenience.
    Supports multiple source languages (English, Yiddish) using the original API structure.
    Uses a generic translation prompt.
    """
    def __init__(self, api_key, srt_output_dir, instructions_filepath):
        """
        Initializes the SubtitleGenerator using the original API structure.

        Args:
            api_key (str): The Gemini API key.
            srt_output_dir (str): Directory to save/load SRT subtitle files.
            instructions_filepath (str): Path to the YAML file with API instructions.
        """
        if not api_key:
            raise ValueError("Gemini API key is required.")
        self.api_key = api_key
        self.srt_output_dir = srt_output_dir
        # *** Using the EXACT original model name ***
        self.model_name = "gemini-2.5-pro-preview-03-25"
        self.client = self._initialize_client() # Uses the original client initialization
        self._ensure_dir_exists(self.srt_output_dir)

        self.instructions_filepath = instructions_filepath
        self.instructions = self._load_instructions(self.instructions_filepath)

    def _ensure_dir_exists(self, dir_path):
        """Creates the directory if it doesn't exist."""
        os.makedirs(dir_path, exist_ok=True)

    def _initialize_client(self):
        """Initializes the Gemini client using the original genai.Client."""
        try:
            # *** Using the EXACT original client initialization ***
            return genai.Client(api_key=self.api_key)
        except Exception as e:
            print(f"Error initializing Gemini client: {e}")
            raise

    def _load_instructions(self, filepath):
        """Loads ALL instructions from the specified YAML file."""
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
        """
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

    def _clean_json_text(self, raw_text):
        """Removes potential Markdown fences (```json ... ```) from the raw text."""
        pattern = r"```(?:json)?\s*(.*?)\s*```"
        match = re.search(pattern, raw_text, re.DOTALL)
        if match:
            cleaned_content = match.group(1).strip()
            # Additional check: if the cleaned content *still* looks like a full JSON object
            if cleaned_content.startswith('{') and cleaned_content.endswith('}'):
                 try:
                     single_obj = json.loads(cleaned_content)
                     if isinstance(single_obj, dict):
                          print("Warning: Cleaned JSON appears to be a single object, wrapping in a list.")
                          return json.dumps([single_obj]) # Return as JSON string representation of a list
                 except json.JSONDecodeError:
                     pass # If it fails, proceed with the original cleaned content

            if cleaned_content.startswith('[') and cleaned_content.endswith(']'):
                 return cleaned_content

            print("Warning: JSON cleaning resulted in content not clearly starting/ending with [] or {}. Proceeding with cleaned text.")
            return cleaned_content

        else:
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
            print("--- Received Data Structure (attempted parse) ---")
            try: print(data)
            except NameError: print("(Could not assign data before error)")
            print("--- End of Received Data Structure ---")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during JSON parsing for {language_name}: {e}")
            return None

    def _sanitize_filename_part(self, text, max_len=60):
        """Sanitizes text for use in filenames."""
        if not text: return "unknown"
        text = re.sub(r'[\\/*?:"<>|]', '_', str(text))
        text = re.sub(r'\s+', '_', text).strip('_')
        return text[:max_len]

    def _calculate_filenames(self, song_name, youtube_url, mp3_audio_path, source_language):
        """Calculates the expected SRT filenames based on Song Name, ID/MP3, and source language."""
        sanitized_song_name = self._sanitize_filename_part(song_name)
        video_id = None
        try:
            parsed_url = urllib.parse.urlparse(youtube_url)
            if parsed_url.hostname in ('youtu.be',):
                video_id = self._sanitize_filename_part(parsed_url.path[1:], 20)
            elif parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
                 query_params = urllib.parse.parse_qs(parsed_url.query)
                 vid = query_params.get('v')
                 if vid and vid[0]:
                     video_id = self._sanitize_filename_part(vid[0], 20)
        except Exception:
             pass

        if not video_id:
            mp3_basename = os.path.splitext(os.path.basename(mp3_audio_path))[0]
            base_identifier = self._sanitize_filename_part(mp3_basename)
            print(f"Warning: Could not extract Video ID from URL '{youtube_url}'. Using sanitized name from MP3: '{base_identifier}' for filename uniqueness.")
        else:
             base_identifier = video_id

        source_lang_suffix = source_language # 'en' or 'yi'
        base_filename = f"{sanitized_song_name}_{base_identifier}"

        source_srt_filename = os.path.join(self.srt_output_dir, f"{base_filename}_{source_lang_suffix}.srt")
        hebrew_srt_filename = os.path.join(self.srt_output_dir, f"{base_filename}_he.srt")
        return source_srt_filename, hebrew_srt_filename

    def _load_existing_subtitles(self, source_srt_path, target_srt_path, source_language_name):
        """
        Attempts to load subtitles from existing SRT files.
        Returns a tuple (source_data, target_data), where either can be None if not found/loaded.
        """
        source_subs_data = None
        target_subs_data = None # Target is always Hebrew
        found_source = False
        found_target = False

        if os.path.exists(source_srt_path):
            print(f"Found existing Source ({source_language_name}) SRT: {source_srt_path}")
            source_subs_data = self._load_srt_file(source_srt_path)
            found_source = True
            if source_subs_data is None:
                print(f"Warning: Failed to parse existing Source ({source_language_name}) SRT: {source_srt_path}")
            elif not source_subs_data:
                 print(f"Warning: Existing Source ({source_language_name}) SRT file is empty or contains no valid entries: {source_srt_path}")

        if os.path.exists(target_srt_path):
            print(f"Found existing Target (Hebrew) SRT: {target_srt_path}")
            target_subs_data = self._load_srt_file(target_srt_path)
            found_target = True
            if target_subs_data is None:
                print(f"Warning: Failed to parse existing Target (Hebrew) SRT: {target_srt_path}")
            elif not target_subs_data:
                 print(f"Warning: Existing Target (Hebrew) SRT file is empty or contains no valid entries: {target_srt_path}")

        if not found_source and not found_target:
            print("No existing SRT files found.")
        elif found_source and found_target and source_subs_data is not None and target_subs_data is not None:
             print(f"Both Source ({source_language_name}) and Target (Hebrew) SRTs loaded successfully.")
        elif found_source and source_subs_data is not None:
             print(f"Only Source ({source_language_name}) SRT loaded successfully.")
        elif found_target and target_subs_data is not None:
             print("Only Target (Hebrew) SRT loaded successfully.")
        else:
             print("Found SRT file(s), but failed to load/parse at least one correctly.")

        return source_subs_data, target_subs_data

    # --- API Call Logic (Using original Client/Stream structure - CORRECTED) ---
    def _call_gemini_api(self, contents, config, language_context):
        """
        Handles the streaming call to the Gemini API using the original structure - CORRECTED.
        Uses self.client.models.generate_content_stream and passes the config object.
        Handles potential NoneType for prompt_feedback and removes outdated specific exceptions.

        Args:
            contents (list): The user contents for the API call.
            config (types.GenerateContentConfig): The configuration object including system prompt.
            language_context (str): String describing the language being generated (e.g., "English", "Yiddish").

        Returns:
            list | None: Parsed subtitle data as a list of dictionaries, or None on failure.
        """
        print(f"Generating {language_context} Subtitles (via API, expecting JSON)...")
        raw_json_output = ""
        try:
            # *** Using the EXACT original stream call structure ***
            stream_response = self.client.models.generate_content_stream(
                model=self.model_name, # Using the original model name: "gemini-2.5-pro-exp-03-25"
                contents=contents,     # Passing user contents
                config=config,         # Passing the config object (which includes system_instruction)
            )
            for chunk in stream_response:
                # Append text directly as in original code
                if chunk.text:
                     raw_json_output += chunk.text

                # *** CORRECTED Check for blocking using prompt_feedback ***
                # Check if prompt_feedback exists AND is not None before accessing block_reason
                prompt_feedback = getattr(chunk, 'prompt_feedback', None)
                if prompt_feedback is not None and prompt_feedback.block_reason:
                    print(f"Warning: Prompt blocked during streaming for {language_context}. Reason: {prompt_feedback.block_reason}")

        except Exception as e:
            # Catching general exceptions which might include API errors or other issues
            print(f"Error during Gemini API stream call for {language_context}: {e}")
            # Attempt to print response details if available (might not exist on all exceptions)
            try:
                 # Check if the exception object itself might contain useful info, like response details
                 # This is speculative as the exact error structure can vary.
                 if hasattr(e, 'response'):
                      print("Gemini response details (if available):", e.response)
                 elif hasattr(e, 'args') and e.args:
                      print("Exception arguments:", e.args)

            except Exception as report_err:
                 print(f"(Could not report detailed error info: {report_err})")
            return None # Return None on any exception during the API call

        print(f"\n{language_context} JSON stream finished. Parsing response...")
        # Ensure parsing happens only if the API call didn't return None implicitly before
        if raw_json_output:
            return self._parse_json_response(raw_json_output, language_context)
        else:
            # Handle cases where the stream completed but produced no text output
            print(f"Warning: API stream for {language_context} finished but produced no text output.")
            return None
            
    # --- API Config (Using original structure with system_instruction inside) ---
    def _get_api_config(self, system_instruction_text):
        """
        Returns the generation config using the original structure,
        including the system_instruction.
        """
        # *** Using the EXACT original config structure ***
        return types.GenerateContentConfig(
            safety_settings=[
                # Keeping original safety settings structure
                types.SafetySetting(
                    category="HARM_CATEGORY_CIVIC_INTEGRITY",
                    threshold="OFF", # As per original code example
                ),
                 # Add other safety settings if they were present in the original config
                 # e.g., HARM_CATEGORY_HARASSMENT, HARM_CATEGORY_HATE_SPEECH, etc.
                 # If none were specified besides civic integrity, keep it minimal.
            ],
            temperature=1.0,
            response_mime_type="application/json", # Crucial
            response_schema=genai.types.Schema( # Using original schema structure
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
            # *** Including system_instruction within the config object ***
            system_instruction=[types.Part.from_text(text=system_instruction_text)] if system_instruction_text else None
        )

    # --- MAIN FUNCTION (Updated logic for language handling, API calls with original structure) ---
    def generate_or_load_subtitles(self, source_language, song_name, youtube_url, mp3_audio_path, lyrics_content=None, force_regenerate=False):
        """
        Generates subtitles using Gemini API or loads them if SRT files exist.
        Uses system_instruction for prompts and user role for dynamic data.
        Saves generated subtitles as SRT files with song name in the filename.
        Optionally uses lyrics_content for transcription.
        Allows forcing regeneration.
        Supports different source languages ('en', 'yi') using language-specific transcription prompts
        and a generic translation prompt, adhering to the original API structure.

        Args:
            source_language (str): The source language code ('en' or 'yi').
            song_name (str): The name of the song (used for filenames).
            youtube_url (str): The YouTube URL of the video.
            mp3_audio_path (str): Path to the MP3 audio file.
            lyrics_content (str, optional): String containing song lyrics. Defaults to None.
            force_regenerate (bool, optional): If True, ignore existing SRTs and regenerate. Defaults to False.

        Returns:
            tuple: (list | None, list | None): A tuple containing the Source
                   subtitle data (English or Yiddish) and Target (Hebrew) subtitle data.
                   Returns (None, None) or (data, None) / (None, data) on errors or partial success.
        """
        source_language_name = "English" if source_language == 'en' else "Yiddish"
        source_srt_path, hebrew_srt_path = self._calculate_filenames(song_name, youtube_url, mp3_audio_path, source_language)

        source_subs = None
        hebrew_subs = None

        if not force_regenerate:
            print("Checking for existing SRT files...")
            source_subs, hebrew_subs = self._load_existing_subtitles(source_srt_path, hebrew_srt_path, source_language_name)
            if source_subs is not None and hebrew_subs is not None:
                print(f"Both Source ({source_language_name}) and Target (Hebrew) subtitles loaded from existing files.")
                return source_subs, hebrew_subs
            if source_subs is None:
                 print(f"Will attempt to generate Source ({source_language_name}) subtitles.")
            if hebrew_subs is None:
                 print("Will attempt to generate Target (Hebrew) subtitles.")
        else:
            print("Force regeneration requested. Skipping check for existing SRT files.")

        # --- Source Language Generation (Transcription) ---
        if source_subs is None:
            print(f"\n--- Generating Source ({source_language_name}) Subtitles ---")

            # Get the correct system prompt text for transcription based on language
            if source_language == 'yi':
                transcription_prompt_key = 'yiddish_transcription_system_prompt'
            else: # Default to English
                transcription_prompt_key = 'english_transcription_system_prompt'

            transcription_system_prompt_text = self.instructions.get(transcription_prompt_key)
            if not transcription_system_prompt_text:
                 print(f"CRITICAL ERROR: '{transcription_prompt_key}' not found in instructions YAML.")
                 return None, hebrew_subs # Return potentially loaded Hebrew subs

            # *** Get the API config using the original structure, including the system prompt ***
            transcription_config = self._get_api_config(transcription_system_prompt_text)

            # Prepare user content (dynamic parts only - video URI and optional lyrics)
            parts_source_user = [
                # *** Using original types.Part structure ***
                types.Part.from_uri(
                    # Assuming the model can handle YouTube URLs directly
                    file_uri=youtube_url, # Parameter name was file_uri in original example
                    mime_type="video/*", # Using generic video mime type as in original
                )
            ]
            if lyrics_content:
                print("Adding provided lyrics to the user input for transcription.")
                parts_source_user.append(types.Part.from_text(text=f"\n\n--- KNOWN LYRICS ---\n{lyrics_content}\n--- END KNOWN LYRICS ---"))

            # Construct the 'contents' list with role="user" using original types.Content
            contents_source = [types.Content(role="user", parts=parts_source_user)]

            # Make the API call using the original structure
            source_subs_data_from_api = self._call_gemini_api(
                contents=contents_source,
                config=transcription_config, # Pass the config object
                language_context=source_language_name
            )

            if source_subs_data_from_api is None:
                print(f"Failed to generate valid Source ({source_language_name}) subtitle data from API. Cannot proceed with translation if Hebrew is also missing.")
                return None, hebrew_subs
            else:
                source_subs = source_subs_data_from_api
                print(f"Source ({source_language_name}) subtitles generated successfully.")
                self._save_srt_file(source_srt_path, source_subs, song_name) # Save to the correct source file path
        else:
             print(f"\nSkipping Source ({source_language_name}) subtitle generation (already loaded).")

        # --- Hebrew Generation (Translation using Generic Prompt and Original API Structure) ---
        if hebrew_subs is None:
            if source_subs is None or not source_subs:
                 print(f"\nCannot generate Hebrew subtitles because Source ({source_language_name}) subtitles are missing or empty.")
                 return source_subs, None

            print("\n--- Generating Hebrew Subtitles (Using Generic Translation Prompt) ---")

            # *** Use the GENERIC translation prompt key ***
            translation_prompt_key = 'generic_translation_system_prompt'
            translation_system_prompt_text = self.instructions.get(translation_prompt_key)
            if not translation_system_prompt_text:
                 print(f"CRITICAL ERROR: '{translation_prompt_key}' not found in instructions YAML.")
                 return source_subs, None

            # *** Get the API config using the original structure, including the generic system prompt ***
            translation_config = self._get_api_config(translation_system_prompt_text)

            try:
                # Format the SOURCE subs (English or Yiddish) back into the specific JSON string format for the prompt
                source_json_for_prompt = []
                for item in source_subs:
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
                     source_json_for_prompt.append({
                         "id": item.get('id', 0),
                         "start_time": start_time_str_api,
                         "end_time": end_time_str_api,
                         "text": item.get('text', '')
                     })
                source_json_prompt_string = json.dumps(source_json_for_prompt, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"Error formatting Source ({source_language_name}) JSON for translation prompt: {e}")
                return source_subs, None

            # *** Use the GENERIC user input template key ***
            user_input_template_key = 'generic_translation_user_input_template'
            translation_user_input_template = self.instructions.get(user_input_template_key)
            if not translation_user_input_template:
                 print(f"CRITICAL ERROR: '{user_input_template_key}' not found in instructions YAML.")
                 return source_subs, None

            # Format the user input text including the JSON data
            user_translation_prompt_text = translation_user_input_template.format(
                source_json_prompt_string=source_json_prompt_string
            )

            # Prepare user content (the formatted JSON string) using original types.Content
            contents_hebrew = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=user_translation_prompt_text)],
                ),
            ]

            # Make the API call using the original structure
            hebrew_subs_data_from_api = self._call_gemini_api(
                contents=contents_hebrew,
                config=translation_config, # Pass the config object
                language_context="Hebrew (from "+source_language_name+")"
            )

            if hebrew_subs_data_from_api is None:
                print("Failed to generate valid Hebrew subtitle data from API.")
                hebrew_subs = None
            else:
                hebrew_subs = hebrew_subs_data_from_api
                print("Hebrew subtitles generated successfully.")
                self._save_srt_file(hebrew_srt_path, hebrew_subs, song_name) # Save to the Hebrew file path
        else:
             print("\nSkipping Hebrew subtitle generation (already loaded).")

        return source_subs, hebrew_subs