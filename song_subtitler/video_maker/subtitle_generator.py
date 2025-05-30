import os
import json
import re
import urllib.parse
import yaml
from google import genai
from google.genai import types
import datetime

class SubtitleGenerator:

    def __init__(self, api_key, srt_output_dir, instructions_filepath):

        if not api_key:
            raise ValueError("Gemini API key is required.")
        self.api_key = api_key
        self.srt_output_dir = srt_output_dir

        self.model_name = "gemini-1.5-flash-preview-0514" # "gemini-1.5-pro-preview-0514"
        self.client = self._initialize_client()
        self._ensure_dir_exists(self.srt_output_dir)

        self.instructions_filepath = instructions_filepath
        self.instructions = self._load_instructions(self.instructions_filepath)

    def _ensure_dir_exists(self, dir_path):

        os.makedirs(dir_path, exist_ok=True)

    def _initialize_client(self):

        try:

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
        else: # len(parts) == 1
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

        # print(f"Attempting to load SRT file: {filepath}") # Made less verbose
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
                    # print(f"Skipping comment line in SRT: {lines[0]}")
                    lines = lines[1:]
                    if not lines: continue

                if len(lines) < 2: # ID line is optional, so min 2 lines (time + text)
                    print(f"Warning: Skipping invalid SRT block in '{filepath}' (not enough lines):\n{block}")
                    continue

                try:

                    id_line_index = -1
                    time_line_index = -1
                    # Search for the time line first, as it's more uniquely formatted
                    for i, line in enumerate(lines):
                        if re.match(r'\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}', line.strip()):
                            time_line_index = i
                            break # Found time line

                    if time_line_index == -1:
                        print(f"Warning: Skipping SRT block with no valid time format in '{filepath}':\n{block}")
                        continue

                    # Try to find ID line: it should be directly before the time line if it's a standard 3-liner
                    # or the first line if it's a 2-liner (ID omitted)
                    if time_line_index > 0 and re.match(r'^\d+$', lines[time_line_index - 1].strip()):
                         id_line_index = time_line_index - 1
                         sub_id = int(lines[id_line_index].strip())
                    elif time_line_index == 0 and re.match(r'^\d+$', lines[0].strip()):
                         # This case is unlikely if time is line 0 and it's also an ID
                         # But if time is line 1, and line 0 is ID, id_line_index should be 0
                         # This means the above condition (time_line_index > 0) handles the 3-liner case.
                         # For a 2-liner (time, text), no explicit ID line.
                         sub_id = len(subtitle_data) + 1 # Assign sequential ID
                    else:
                         # print(f"Warning: Could not determine subtitle ID for block in '{filepath}'. Assigning sequential ID.\n{block}")
                         sub_id = len(subtitle_data) + 1


                    time_line = lines[time_line_index].strip()
                    text_lines = lines[time_line_index + 1:]

                    if not text_lines: # Check if there's any text after the time line
                        print(f"Warning: Skipping SRT block with no text content after time line in '{filepath}':\n{block}")
                        continue

                    time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', time_line)

                    if not time_match: continue # Should have been caught by outer loop logic, but double check

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

            # if subtitle_data:
            #      print(f"Successfully loaded and parsed {len(subtitle_data)} entries from SRT: {filepath}")
            # else:
            #      print(f"Warning: No valid subtitle entries found or parsed in SRT file: {filepath}")
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
                     pass # Will be caught by the main parser

            if cleaned_content.startswith('[') and cleaned_content.endswith(']'):
                 return cleaned_content

            print("Warning: JSON cleaning resulted in content not clearly starting/ending with [] or {}. Proceeding with cleaned text.")
            return cleaned_content

        else:
            # If no markdown block, assume the text is already the JSON content or needs to be parsed as is.
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
                if isinstance(data, dict): data = [data] # Wrap single dict in a list
                else: raise ValueError("JSON response is not a list.")

            processed_data = []
            if data: # Ensure data is not an empty list before iterating
                for item_index, item in enumerate(data):
                    if not isinstance(item, dict):
                        raise ValueError(f"Item at index {item_index} in {language_name} JSON list is not a dictionary.")

                    # Validate required keys
                    required_keys = {"id", "start_time", "end_time", "text"}
                    missing_keys = required_keys - item.keys()
                    if missing_keys:
                         raise ValueError(f"Dictionary at index {item_index} in {language_name} JSON is missing required keys: {missing_keys}. Found: {item.keys()}")

                    # Process item
                    processed_item = {}
                    processed_item['id'] = item['id'] # Assuming id is always valid as per schema
                    processed_item['text'] = item['text'] # Assuming text is always valid as per schema

                    # Time conversion logic (from MM:SS.ms string to float seconds)
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
                        elif isinstance(time_value, (int, float)): # Allow if already number
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
        except ValueError as e: # Catches our custom ValueErrors for structure
            print(f"Error: Invalid JSON structure or content for {language_name}. Error: {e}")
            print("--- Received Data Structure (attempted parse) ---")
            try: print(data) # If 'data' was assigned before error
            except NameError: print("(Could not assign data before error)")
            print("--- End of Received Data Structure ---")
            return None
        except Exception as e: # Catch any other unexpected errors
            print(f"An unexpected error occurred during JSON parsing for {language_name}: {e}")
            return None

    def _sanitize_filename_part(self, text, max_len=60):

        if not text: return "unknown"
        text = re.sub(r'[\\/*?:"<>|]', '_', str(text)) # Remove invalid chars
        text = re.sub(r'\s+', '_', text).strip('_') # Replace whitespace with underscore
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
                sanitized_song_name = "untitled_song" # Ultimate fallback
            print(f"Warning: Song name was empty or invalid, using '{sanitized_song_name}' from MP3/fallback for filenames.")

        source_lang_suffix = source_language.lower() # en, yi

        # New filename format (preferred for writing and primary for reading)
        base_filename_new = f"{sanitized_song_name}"
        source_filename_new = f"{base_filename_new}_{source_lang_suffix}.srt"
        hebrew_filename_new = f"{base_filename_new}_he.srt"

        write_source_path = os.path.join(self.srt_output_dir, source_filename_new)
        write_hebrew_path = os.path.join(self.srt_output_dir, hebrew_filename_new)

        # List of paths to try for reading, in order of preference
        read_source_paths = [write_source_path]
        read_hebrew_paths = [write_hebrew_path]

        # Legacy filename format (secondary for reading, if YouTube URL is available)
        if youtube_url:
            video_id = self._extract_video_id(youtube_url)
            if video_id:
                base_filename_legacy = f"{sanitized_song_name}_{video_id}"
                legacy_source_filename = f"{base_filename_legacy}_{source_lang_suffix}.srt"
                legacy_hebrew_filename = f"{base_filename_legacy}_he.srt"
                
                legacy_source_path = os.path.join(self.srt_output_dir, legacy_source_filename)
                legacy_hebrew_path = os.path.join(self.srt_output_dir, legacy_hebrew_filename)

                if legacy_source_path not in read_source_paths: # Avoid duplicates if names are same
                    read_source_paths.append(legacy_source_path)
                if legacy_hebrew_path not in read_hebrew_paths:
                    read_hebrew_paths.append(legacy_hebrew_path)
            else:
                print(f"Info: YouTube URL '{youtube_url}' provided, but could not extract a video ID for legacy filename checking.")

        return (write_source_path, read_source_paths), \
               (write_hebrew_path, read_hebrew_paths)

    def _load_existing_subtitles(self, read_source_paths, read_target_paths, source_language_name):
        source_subs_data = None
        target_subs_data = None
        source_path_used = None
        target_path_used = None

        print(f"Attempting to load Source ({source_language_name}) SRTs from: {read_source_paths}")
        for path in read_source_paths:
            if os.path.exists(path):
                print(f"  Trying path: {path}")
                source_subs_data = self._load_srt_file(path)
                if source_subs_data:
                    print(f"  Successfully loaded Source ({source_language_name}) SRT: {path}")
                    source_path_used = path
                    break
                else:
                    print(f"  Found Source ({source_language_name}) SRT: {path}, but it was empty or failed to parse.")
        
        if not source_path_used and read_source_paths:
            print(f"  No valid Source ({source_language_name}) SRT found or loaded from potential paths.")


        print(f"Attempting to load Target (Hebrew) SRTs from: {read_target_paths}")
        for path in read_target_paths:
            if os.path.exists(path):
                print(f"  Trying path: {path}")
                target_subs_data = self._load_srt_file(path)
                if target_subs_data:
                    print(f"  Successfully loaded Target (Hebrew) SRT: {path}")
                    target_path_used = path
                    break
                else:
                    print(f"  Found Target (Hebrew) SRT: {path}, but it was empty or failed to parse.")
        
        if not target_path_used and read_target_paths:
            print(f"  No valid Target (Hebrew) SRT found or loaded from potential paths.")


        if not source_subs_data and not target_subs_data:
            print("No existing SRT files loaded successfully.")
        elif source_subs_data and target_subs_data:
             pass # Already printed success for both
        elif source_subs_data:
             pass # Already printed success for source
        elif target_subs_data:
             pass # Already printed success for target
        
        return source_subs_data, target_subs_data


    def _call_gemini_api(self, contents, config, language_context):

        print(f"Generating {language_context} Subtitles (via API, expecting JSON)...")
        raw_json_output = ""
        try:

            stream_response = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                generation_config=config, # Renamed from 'config' to 'generation_config'
            )
            for chunk in stream_response:

                if chunk.text:
                     raw_json_output += chunk.text



                prompt_feedback = getattr(chunk, 'prompt_feedback', None)
                if prompt_feedback is not None and prompt_feedback.block_reason:
                    print(f"Warning: Prompt blocked during streaming for {language_context}. Reason: {prompt_feedback.block_reason}")
                    # Consider how to handle this - maybe return a specific error indicator?
                    # For now, it will likely result in empty or partial JSON.

        except types.generation_types.BlockedPromptException as bpe:
            print(f"ERROR: Gemini API call for {language_context} was blocked. Reason: {bpe}")
            # This exception means the entire prompt was blocked before streaming.
            return None # Indicate failure due to blocking
        except Exception as e:

            print(f"Error during Gemini API stream call for {language_context}: {e}")

            try:


                 if hasattr(e, 'response'): # For google.api_core.exceptions
                      print("Gemini response details (if available):", e.response)
                 elif hasattr(e, 'args') and e.args: # General exception args
                      print("Exception arguments:", e.args)

            except Exception as report_err:
                 print(f"(Could not report detailed error info: {report_err})")
            return None

        print(f"\n{language_context} JSON stream finished. Parsing response...")
        # print(f"DEBUG: Raw JSON output for {language_context}:\n{raw_json_output[:1000]}...\n") # For debugging

        if raw_json_output:
            return self._parse_json_response(raw_json_output, language_context)
        else:
            # Handle cases where the stream completed but produced no text output
            print(f"Warning: API stream for {language_context} finished but produced no text output.")
            return None

    def _get_api_config(self, system_instruction_text):
        # This structure matches the new SDK's GenerateContentConfig
        # The system_instruction is now a top-level parameter to generate_content,
        # not part of GenerateContentConfig. However, to keep the _get_api_config
        # somewhat similar, we'll prepare it here and the caller can decide.
        # For now, let's assume system_instruction is handled by the caller.

        # The schema is now passed directly to `tools` or as `response_schema` in `tool_config`
        # if using function calling. For direct JSON mode, it's part of `response_mime_type`.

        # Simplified config focusing on JSON output and safety.
        # The schema itself is specified by the "application/json" mime type + the schema in system prompt.
        config = types.GenerationConfig(
            # candidate_count=1, # Default is 1
            # stop_sequences=["..."],
            # max_output_tokens=2048, # Example, adjust as needed
            temperature=1.0, # As per original
            # top_p=0.9,
            # top_k=40,
            response_mime_type="application/json", # Crucial for JSON mode
        )

        # Safety settings are part of the main `generate_content` call or client-level.
        # For this method, we'll return the config, and safety can be set by the caller.
        # Example of how safety_settings would be structured if set per-call:
        # safety_settings = [
        #     {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        #     {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxthreshold": "BLOCK_NONE"},
        #     {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        # ]
        # This method will just return the GenerationConfig for now.
        return config

    def generate_or_load_subtitles(self, source_language, song_name, youtube_url, mp3_audio_path, lyrics_content=None, force_regenerate=False):
        source_language_name = "English" if source_language == 'en' else "Yiddish"
        
        (write_source_srt_path, read_source_srt_paths), \
        (write_hebrew_srt_path, read_hebrew_srt_paths) = \
            self._calculate_filenames(song_name, youtube_url, mp3_audio_path, source_language)

        source_subs = None
        hebrew_subs = None

        if not force_regenerate:
            print("Checking for existing SRT files...")
            source_subs, hebrew_subs = self._load_existing_subtitles(
                read_source_srt_paths, read_hebrew_srt_paths, source_language_name
            )
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
            if not youtube_url:
                print(f"Cannot generate Source ({source_language_name}) subtitles from API: YouTube URL not provided.")
                # source_subs remains None
            else:
                if source_language == 'yi':
                    transcription_prompt_key = 'yiddish_transcription_system_prompt'
                else: # Default to English
                    transcription_prompt_key = 'english_transcription_system_prompt'
                
                transcription_system_prompt_text = self.instructions.get(transcription_prompt_key)
                if not transcription_system_prompt_text:
                     print(f"CRITICAL ERROR: '{transcription_prompt_key}' not found in instructions YAML.")
                     return None, hebrew_subs 

                api_gen_config = self._get_api_config(transcription_system_prompt_text)
                
                parts_source_user = [
                    types.Part.from_uri(file_uri=youtube_url, mime_type="video/youtube") # More specific mime type
                ]
                if lyrics_content:
                    print("Adding provided lyrics to the user input for transcription.")
                    parts_source_user.append(types.Part.from_text(text=f"\n\n--- KNOWN LYRICS ---\n{lyrics_content}\n--- END KNOWN LYRICS ---"))
                
                contents_source = [types.Content(role="user", parts=parts_source_user)]
                
                # Construct the model instance for generation
                model_instance = self.client.get_model(f"models/{self.model_name}")
                
                source_subs_data_from_api = self._call_gemini_api(
                    contents=contents_source, # Pass only user content here
                    config=api_gen_config,    # Pass generation config
                    language_context=source_language_name
                    # System instruction is now part of the model.generate_content call
                )


                if source_subs_data_from_api is None:
                    print(f"Failed to generate valid Source ({source_language_name}) subtitle data from API.")
                    # source_subs remains None
                else:
                    source_subs = source_subs_data_from_api
                    print(f"Source ({source_language_name}) subtitles generated successfully from API.")
                    self._save_srt_file(write_source_srt_path, source_subs, song_name)
        else:
             print(f"\nSkipping Source ({source_language_name}) subtitle generation (already loaded).")

        # --- Hebrew Generation (Translation) ---
        if hebrew_subs is None:
            if source_subs is None or not source_subs:
                 print(f"\nCannot generate Hebrew subtitles because Source ({source_language_name}) subtitles are missing or empty.")
                 return source_subs, None # hebrew_subs is already None

            print("\n--- Generating Hebrew Subtitles (Translation) ---")
            translation_prompt_key = 'generic_translation_system_prompt' # Use the generic key
            translation_system_prompt_text = self.instructions.get(translation_prompt_key)
            if not translation_system_prompt_text:
                 print(f"CRITICAL ERROR: '{translation_prompt_key}' not found in instructions YAML.")
                 return source_subs, None

            api_gen_config_translation = self._get_api_config(translation_system_prompt_text)

            try:
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

            user_input_template_key = 'generic_translation_user_input_template'
            translation_user_input_template = self.instructions.get(user_input_template_key)
            if not translation_user_input_template:
                 print(f"CRITICAL ERROR: '{user_input_template_key}' not found in instructions YAML.")
                 return source_subs, None
            
            user_translation_prompt_text = translation_user_input_template.format(
                source_json_prompt_string=source_json_prompt_string
            )
            
            contents_hebrew = [
                types.Content(role="user", parts=[types.Part.from_text(text=user_translation_prompt_text)])
            ]
            
            model_instance_translation = self.client.get_model(f"models/{self.model_name}")
            hebrew_subs_data_from_api = self._call_gemini_api(
                contents=contents_hebrew,
                config=api_gen_config_translation,
                language_context=f"Hebrew (from {source_language_name})"
            )

            if hebrew_subs_data_from_api is None:
                print("Failed to generate valid Hebrew subtitle data from API.")
                # hebrew_subs remains None
            else:
                hebrew_subs = hebrew_subs_data_from_api
                print("Hebrew subtitles generated successfully from API.")
                self._save_srt_file(write_hebrew_srt_path, hebrew_subs, song_name)
        else:
             print("\nSkipping Hebrew subtitle generation (already loaded).")

        return source_subs, hebrew_subs