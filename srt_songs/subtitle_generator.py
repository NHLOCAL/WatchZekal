import os
import json
import re
import urllib.parse
from google import genai
from google.genai import types

class SubtitleGenerator:
    """
    Handles the generation or loading of subtitles using the Gemini API.
    Ensures the specific API structure and response format are maintained.
    """
    def __init__(self, api_key, json_output_dir):
        """
        Initializes the SubtitleGenerator.

        Args:
            api_key (str): The Gemini API key.
            json_output_dir (str): Directory to save/load JSON subtitle files.
        """
        if not api_key:
            raise ValueError("Gemini API key is required.")
        self.api_key = api_key
        self.json_output_dir = json_output_dir
        self.model_name = "gemini-2.5-pro-exp-03-25"
        self.client = self._initialize_client()
        self._ensure_dir_exists(self.json_output_dir)

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

    def _clean_json_text(self, raw_text):
        """Removes potential Markdown fences (```json ... ```) from the raw text."""
        pattern = r"```(?:json)?\s*(.*?)\s*```"
        match = re.search(pattern, raw_text, re.DOTALL)
        if match:
            cleaned_content = match.group(1).strip()
            # print("Info: Removed Markdown fences from JSON response.") # Optional info
            return cleaned_content
        else:
            return raw_text.strip()

    def _parse_json_response(self, json_text, language_name):
        """
        Parses JSON response, validates structure, and returns the list.
        Handles timecodes in "MM:SS.milliseconds" format and converts them to seconds *within this parser*.
        The API itself is requested to return MM:SS.ms strings.
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
                        raise ValueError(f"Dictionary in {language_name} JSON is missing required keys ({required_keys}). Found: {item.keys()}")

                    for time_key in ["start_time", "end_time"]:
                        time_value = item[time_key]
                        if isinstance(time_value, str):
                            # --- CRITICAL: Check for the MM:SS.ms format received from API ---
                            if re.match(r"\d{2}:\d{2}\.\d{3}", time_value):
                                try:
                                    minutes, seconds_milliseconds = time_value.split(":")
                                    seconds, milliseconds = seconds_milliseconds.split(".")
                                    total_seconds = int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000.0
                                    item[time_key] = float(total_seconds) # Convert to float seconds *after* receiving the string
                                except ValueError:
                                    print(f"Warning: Could not parse expected time string '{time_value}' in {language_name} for {time_key}. Keeping as string.")
                            else:
                                # If API didn't return the requested format, try float conversion as fallback
                                print(f"Warning: Time value '{time_value}' in {language_name} for {time_key} is a string but not in expected MM:SS.milliseconds format. Attempting float conversion.")
                                try:
                                    item[time_key] = float(time_value) # Try to convert string to float anyway
                                except ValueError:
                                    print(f"Error: Could not convert time string '{time_value}' to float in {language_name} for {time_key}. Setting to 0.")
                                    item[time_key] = 0.0 # Fallback
                        elif not isinstance(time_value, (int, float)):
                             # Handle cases where API might have ignored the string request (less likely with schema)
                            print(f"Warning: Timestamps in {language_name} JSON are not strings or numbers (int/float). Found: {type(time_value)} for {time_key}. Attempting conversion to float.")
                            try:
                                item[time_key] = float(time_value)
                            except ValueError:
                                print(f"Error: Could not convert timestamp to float in {language_name} for {time_key}. Setting to 0.")
                                item[time_key] = 0.0 # Fallback

            # print(f"Successfully parsed JSON for {language_name}.") # Optional info
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

    def _calculate_filenames(self, youtube_url, mp3_audio_path):
        """Calculates the expected JSON filenames based on YouTube URL or MP3 path."""
        try:
            parsed_url = urllib.parse.urlparse(youtube_url)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            video_id = query_params.get('v')
            if video_id:
                base_filename = video_id[0]
            else:
                base_filename = re.sub(r'\W+', '_', os.path.splitext(os.path.basename(mp3_audio_path))[0])
                print(f"Warning: Could not extract Video ID from URL. Using fallback name from MP3: {base_filename}")
        except Exception as e:
            print(f"Warning: Error parsing URL or deriving base filename: {e}. Using fallback name from MP3.")
            base_filename = re.sub(r'\W+', '_', os.path.splitext(os.path.basename(mp3_audio_path))[0])

        english_json_filename = os.path.join(self.json_output_dir, f"{base_filename}_en.json")
        hebrew_json_filename = os.path.join(self.json_output_dir, f"{base_filename}_he.json")
        return english_json_filename, hebrew_json_filename

    def _load_existing_subtitles(self, en_path, he_path):
        """Attempts to load subtitles from existing JSON files."""
        if os.path.exists(en_path) and os.path.exists(he_path):
            print(f"\nFound existing JSON files:\n  EN: {en_path}\n  HE: {he_path}")
            print("Attempting to load existing files...")
            try:
                with open(en_path, "r", encoding="utf-8") as f_en:
                    # Parse immediately to validate and convert times
                    english_subs_data = self._parse_json_response(f_en.read(), "Existing English")
                with open(he_path, "r", encoding="utf-8") as f_he:
                    # Parse immediately to validate and convert times
                    hebrew_subs_data = self._parse_json_response(f_he.read(), "Existing Hebrew")

                # Check if parsing was successful and data is valid list
                valid_en = isinstance(english_subs_data, list)
                valid_he = isinstance(hebrew_subs_data, list)

                if valid_en and valid_he:
                    if not english_subs_data and not hebrew_subs_data:
                         print("Warning: Both existing JSON files contain empty lists.")
                    elif not english_subs_data:
                         print("Warning: Existing English JSON file is empty.")
                    elif not hebrew_subs_data:
                         print("Warning: Existing Hebrew JSON file is empty.")
                    else:
                        print("Subtitle data successfully loaded and parsed from existing files.")
                    return english_subs_data, hebrew_subs_data
                else:
                    print("Warning: Failed to parse one or both existing JSON files correctly. Proceeding to generate new subtitles.")
                    return None, None # Indicate failure to load valid data

            except Exception as e:
                print(f"Error reading or parsing existing JSON files: {e}. Proceeding to generate new subtitles.")
                return None, None # Indicate failure
        else:
            # print("Existing JSON files not found.") # Optional info
            return None, None # Indicate files not found

    def _call_gemini_api(self, contents, config, language_context):
        """Handles the streaming call to the Gemini API."""
        print(f"Generating {language_context} Subtitles (JSON)...")
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

        print(f"\n{language_context} JSON stream finished.")
        # Parse the raw output AFTER the stream is complete
        return self._parse_json_response(raw_json_output, language_context)

    def _get_api_config(self):
        """Returns the generation config with the required schema."""
        return types.GenerateContentConfig(
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
                            type = genai.types.Type.STRING, # Requesting STRING
                            description = "זמן התחלת הכתובית בפורמט מחרוזת 'MM:SS.milliseconds' (לדוגמה '02:30.110').",
                            pattern=r"^\d{2}:\d{2}\.\d{3}$" # Enforce format
                        ),
                        "end_time": genai.types.Schema(
                            type = genai.types.Type.STRING, # Requesting STRING
                            description = "זמן סיום הכתובית בפורמט מחרוזת 'MM:SS.milliseconds' (לדוגמה '02:35.800').",
                            pattern=r"^\d{2}:\d{2}\.\d{3}$" # Enforce format
                        ),
                        "text": genai.types.Schema(
                            type = genai.types.Type.STRING,
                            description = "תוכן הכתובית, יכול להכיל תוכן קצר בעל שורה או שתיים עם הפרדה `\n`",
                        ),
                    },
                ),
            ),
        )

    def _get_system_instruction(self):
        """Returns the system instruction content."""
        return """You must create subtitles for the attached video. The output must be a **JSON Array** as shown below.

**Pay attention**: Some songs include Hebrew words with English pronunciation (like "yerushalim habnuya"). Transcribe these words into English phonetically, as they sound in the English pronunciation.

**CRITICAL REQUIREMENT for Time Format:**
The `start_time` and `end_time` fields must be **strings** in the exact format `MM:SS.milliseconds` (two digits for minutes, two digits for seconds, a period, and three digits for milliseconds).
**Example:** `"start_time": "01:45.320"`, `"end_time": "01:50.100"`.
**Do NOT use float seconds or any other format.**

Each subtitle object in the JSON array must include:
- **`id`**: Sequential number (integer).
- **`start_time`**: Start time (string in `MM:SS.milliseconds` format).
- **`end_time`**: End time (string in `MM:SS.milliseconds` format).
- **`text`**: Subtitle text (string, can contain `\\n` for new lines).

Maintain accuracy in the timings (using the specified string format) and the content. Output ONLY the JSON array.

### **Example JSON Structure:**
```json
[
  {
    "id": 1,
    "start_time": "00:12.759",
    "end_time": "00:18.859",
    "text": "I will never forget\\nthe night I saw my father cry"
  },
  {
    "id": 2,
    "start_time": "00:21.359",
    "end_time": "00:28.729",
    "text": "I was frightened and alone\\nand his tears"
  },
  {
    "id": 3,
    "start_time": "02:30.110",
    "end_time": "02:35.800",
    "text": "This shows the required\\nMM:SS.ms format"
  }
]
```"""

    def generate_or_load_subtitles(self, youtube_url, mp3_audio_path):
        """
        Generates subtitles using Gemini API or loads them if JSON files exist.

        Args:
            youtube_url (str): The YouTube URL of the video.
            mp3_audio_path (str): Path to the MP3 audio file (used for fallback naming).

        Returns:
            tuple: (list | None, list | None): A tuple containing the English
                   subtitle data (list of dicts) and Hebrew subtitle data (list of dicts).
                   Returns (None, None) or (data, None) / (None, data) on errors.
        """
        english_json_path, hebrew_json_path = self._calculate_filenames(youtube_url, mp3_audio_path)

        # Try loading existing files first
        english_subs, hebrew_subs = self._load_existing_subtitles(english_json_path, hebrew_json_path)
        if english_subs is not None or hebrew_subs is not None:
            # If loading was attempted and returned something (even empty lists or None), return it.
            return english_subs, hebrew_subs

        # --- Proceed with Generation ---
        print("\nExisting JSON files not found or invalid. Starting generation process...")

        # --- Common Config and Instruction ---
        generate_content_config = self._get_api_config()
        system_instruction = self._get_system_instruction() # Although not used directly in stream call, it defines the expected output format.

        # --- English Generation ---
        transcription_prompt_text = """Transcribe the following song accurately.
Output the result as a JSON array following the specified format (id, start_time, end_time, text).
**CRITICAL:** Use the `MM:SS.milliseconds` string format for `start_time` and `end_time`.
Divide segments intelligently.
Output ONLY the JSON array."""

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
            print("Failed to generate valid English JSON data. Cannot proceed to translation.")
            return None, None

        # Save English JSON
        try:
             with open(english_json_path, "w", encoding="utf-8") as f:
                json.dump(english_subs_data, f, ensure_ascii=False, indent=2)
             print(f"English JSON (with float times) saved to: {english_json_path}")
        except Exception as e:
            print(f"Error saving English JSON file '{english_json_path}': {e}")
            # Return the generated English data even if saving failed, but no Hebrew.
            return english_subs_data, None

        # --- Hebrew Translation ---
        # Re-generate the JSON string *with the required MM:SS.ms format* for the translation prompt
        try:
            english_json_for_prompt = []
            for item in english_subs_data:
                 start_s = item.get('start_time', 0.0)
                 end_s = item.get('end_time', 0.0)
                 start_min, start_sec_rem = divmod(start_s, 60)
                 start_sec, start_ms = divmod(start_sec_rem, 1)
                 end_min, end_sec_rem = divmod(end_s, 60)
                 end_sec, end_ms = divmod(end_sec_rem, 1)
                 start_time_str = f"{int(start_min):02}:{int(start_sec):02}.{int(start_ms*1000):03}"
                 end_time_str = f"{int(end_min):02}:{int(end_sec):02}.{int(end_ms*1000):03}"

                 english_json_for_prompt.append({
                     "id": item.get('id'),
                     "start_time": start_time_str, # Use the formatted string
                     "end_time": end_time_str,     # Use the formatted string
                     "text": item.get('text')
                 })
            english_json_prompt_string = json.dumps(english_json_for_prompt, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error formatting English JSON for translation prompt: {e}")
            return english_subs_data, None


        translation_prompt_text = f"""Translate the `text` field in the following English JSON subtitles into **natural-sounding Hebrew**.

Maintain the exact same JSON structure, including the 'id', 'start_time', and 'end_time' values (in `MM:SS.milliseconds` string format). Only translate the 'text' field for each object.

The Hebrew translation must be accurate but phrased naturally, as someone would speak or sing.

**Crucially, do not add any Hebrew diacritics (nikud) to the translated text.** Use only standard Hebrew letters. Ensure line breaks (`\\n`) are preserved or used appropriately in the Hebrew translation where needed.

Output ONLY the translated JSON array.

Original English JSON (with times as MM:SS.ms strings):
{english_json_prompt_string}"""

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
            print("Failed to generate valid Hebrew JSON data.")
            # Return English data even if Hebrew failed
            return english_subs_data, None

        # Save Hebrew JSON
        try:
             with open(hebrew_json_path, "w", encoding="utf-8") as f:
                 # Again, save the parsed (float time) version
                json.dump(hebrew_subs_data, f, ensure_ascii=False, indent=2)
             print(f"Hebrew JSON (with float times) saved to: {hebrew_json_path}")
        except Exception as e:
            print(f"Error saving Hebrew JSON file '{hebrew_json_path}': {e}")
            # Return both, but flag the save error
            return english_subs_data, hebrew_subs_data # Still return Hebrew data

        return english_subs_data, hebrew_subs_data