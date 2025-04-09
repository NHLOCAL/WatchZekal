import os
import re
import moviepy.editor as mp
from moviepy.video.tools.subtitles import SubtitlesClip
import imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
import time
import traceback

class VideoCreator:
    """
    Creates a video file with background, optional title, artist name, subtitles, and audio.
    Handles subtitle rendering using PIL for advanced text layout (BiDi, stroke).
    Includes logic for saving subtitle frames.
    Configuration is loaded from an external JSON file via the main script.
    """
    def __init__(self, resolved_config):
        """
        Initializes the VideoCreator with resolved configuration settings.
        """
        self.cfg = resolved_config

        self.paths = self.cfg['paths']
        self.video_settings = self.cfg['video_settings']
        self.bg_settings = self.cfg['background']
        self.title_style = self.cfg['title_style']
        self.subtitle_style = self.cfg['subtitle_style']
        # --- הוספה: קריאת הגדרות עיצוב הזמר ---
        self.artist_style = self.cfg.get('artist_style') # Use .get() in case it's missing
        # --- סוף הוספה ---

        self.title_font_path = os.path.join(self.paths['fonts_dir'], self.title_style['font_name'])
        self.subtitle_font_path = os.path.join(self.paths['fonts_dir'], self.subtitle_style['font_name'])
        # --- הוספה: נתיב פונט הזמר (רק אם הוגדר הסגנון) ---
        self.artist_font_path = None
        if self.artist_style and 'font_name' in self.artist_style:
            self.artist_font_path = os.path.join(self.paths['fonts_dir'], self.artist_style['font_name'])
        # --- סוף הוספה ---


        self.background_image_path = self.bg_settings['background_image_path']
        self.intro_background_image_path = self.bg_settings.get('intro_background_image_path')

        self.output_frames_dir = self.paths['output_frames_dir']
        self.output_video_dir = self.paths['output_dir']

        self._validate_paths() # נעדכן את המתודה הזו
        self._ensure_dirs_exist()

        self.combined_subs_list_for_frames = []
        self.saved_subtitle_ids = set()

    def _validate_paths(self):
        """Checks if essential files (fonts, backgrounds) exist using absolute paths."""
        if not os.path.exists(self.title_font_path):
            raise FileNotFoundError(f"Error: Title font file not found at '{self.title_font_path}'")
        if not os.path.exists(self.subtitle_font_path):
            raise FileNotFoundError(f"Error: Subtitle font file not found at '{self.subtitle_font_path}'")
        if not os.path.exists(self.background_image_path):
            raise FileNotFoundError(f"Error: Background image not found at '{self.background_image_path}'")
        if self.intro_background_image_path and not os.path.exists(self.intro_background_image_path):
             raise FileNotFoundError(f"Error: Intro background image specified but not found at '{self.intro_background_image_path}'")
        # --- הוספה: ולידציה לפונט הזמר (אם הוגדר) ---
        if self.artist_font_path and not os.path.exists(self.artist_font_path):
             raise FileNotFoundError(f"Error: Artist font file specified in config but not found at '{self.artist_font_path}'")
        # --- סוף הוספה ---

    def _ensure_dirs_exist(self):
        """Creates output directories if they don't exist."""
        os.makedirs(self.output_frames_dir, exist_ok=True)
        os.makedirs(self.output_video_dir, exist_ok=True)

    def _load_audio(self, mp3_path):
        """Loads the audio clip and returns it along with its duration."""
        print("Loading audio...")
        try:
            audio_clip = mp.AudioFileClip(mp3_path)
            duration = audio_clip.duration
            if not duration or duration <= 0:
                raise ValueError("Audio duration is invalid (zero or negative).")
            print(f"Audio duration: {duration:.2f} seconds")
            return audio_clip, duration
        except Exception as e:
            print(f"Error loading audio file '{mp3_path}': {e}")
            raise

    def _create_background_clip(self, duration):
        """Creates the background video clip from an image."""
        print("Loading background image...")
        try:
            bg_clip = mp.ImageClip(self.background_image_path, duration=duration)
            target_w, target_h = self.video_settings['resolution']
            # Resize height first, then crop width if needed, then final resize
            bg_clip = bg_clip.resize(height=target_h)
            if bg_clip.w > target_w:
                bg_clip = bg_clip.crop(x_center=bg_clip.w / 2, width=target_w)
            bg_clip = bg_clip.resize((target_w, target_h))
            bg_clip = bg_clip.set_fps(self.video_settings['fps'])
            return bg_clip
        except Exception as e:
            print(f"Error loading or processing background image '{self.background_image_path}': {e}")
            raise

    def _get_first_subtitle_time(self, subs_data_en, subs_data_he, audio_duration):
        """Finds the start time of the first subtitle."""
        first_start_time = audio_duration # Default to end if no subs
        try:
            times = []
            if isinstance(subs_data_en, list):
                for sub in subs_data_en:
                    start = float(sub.get('start_time', float('inf')))
                    if start >= 0: times.append(start)
            if isinstance(subs_data_he, list):
                 for sub in subs_data_he:
                    start = float(sub.get('start_time', float('inf')))
                    if start >= 0: times.append(start)

            if times:
                first_start_time = min(times)

        except (ValueError, TypeError, KeyError) as e:
             print(f"Warning: Could not reliably determine first subtitle start time from JSON data. Error: {e}")
             first_start_time = 0 # Default to 0 if unsure

        # Ensure time is within bounds and not infinite
        first_start_time = max(0, min(first_start_time, audio_duration))
        if first_start_time == float('inf'): first_start_time = 0

        return first_start_time

    # --- שינוי: הוספת פרמטר artist_name_text ---
    def _create_title_clip(self, song_title_text, artist_name_text, title_duration):
        """
        Creates the title text clip (including artist name) using PIL rendering.
        """
        if title_duration <= 0:
            print("Title duration is zero or negative, skipping title clip creation.")
            return None
        if not song_title_text or not song_title_text.strip():
             print("Title text is empty, skipping title clip creation.")
             return None

        print(f"Creating title clip (Title & Artist) using PIL for duration: {title_duration:.2f}s")
        try:
            # 1. Load Fonts and Get Settings
            title_font_size = self.title_style['font_size']
            video_w, video_h = self.video_settings['resolution']
            horizontal_margin = 100
            max_text_width = video_w - (2 * horizontal_margin)
            if max_text_width <= 0:
                max_text_width = video_w * 0.8
                print(f"Warning: Calculated max title width is too small. Using {max_text_width}px.")

            try:
                title_font = ImageFont.truetype(self.title_font_path, title_font_size)
            except IOError:
                print(f"CRITICAL Error: Could not load title font file '{self.title_font_path}' with PIL.")
                raise

            # --- הוספה: טעינת פונט וסגנון הזמר (אם קיים) ---
            artist_font = None
            render_artist = False
            if artist_name_text and self.artist_style and self.artist_font_path:
                try:
                    artist_font_size = self.artist_style['font_size']
                    artist_font = ImageFont.truetype(self.artist_font_path, artist_font_size)
                    render_artist = True
                    print(f"Artist font loaded: {self.artist_style['font_name']} ({artist_font_size}pt)")
                except IOError:
                    print(f"Warning: Could not load artist font file '{self.artist_font_path}'. Artist name will not be rendered.")
                except KeyError as e:
                     print(f"Warning: Missing key {e} in 'artist_style' config. Artist name might not render correctly.")
                     render_artist = False # Disable rendering if style is incomplete
            elif artist_name_text:
                print("Warning: Artist name provided, but 'artist_style' or font is missing/invalid in config. Artist name will not be rendered.")
            # --- סוף הוספה ---

            # 2. Create Transparent Image and Draw Context
            img = Image.new('RGBA', (video_w, video_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # 3. Wrap Title Text
            print(f"Wrapping title text with max width: {max_text_width}px")
            wrapped_title_lines = self._wrap_text(draw, song_title_text, title_font, max_text_width)

            if not wrapped_title_lines:
                print("Warning: Title text resulted in no lines after wrapping.")
                # אם אין כותרת, כנראה גם לא נרצה אמן
                return None

            # --- לוגיקת איזון שורות כותרת (ללא שינוי) ---
            if len(wrapped_title_lines) == 2:
                # ... (קוד איזון שורות כותרת נשאר זהה) ...
                # (הדפסת ניסיון איזון, בדיקת תנאים, והתאמת wrapped_title_lines אם צריך)
                line1_text = wrapped_title_lines[0]
                line2_text = wrapped_title_lines[1]
                line1_words = line1_text.split()
                should_adjust = False
                try:
                    bbox1 = draw.textbbox((0, 0), line1_text, font=title_font)
                    width1 = bbox1[2] - bbox1[0] if bbox1 else 0
                    bbox2 = draw.textbbox((0, 0), line2_text, font=title_font)
                    width2 = bbox2[2] - bbox2[0] if bbox2 else 0
                    if width1 > 0 and width2 > 0 and (width2 / width1 < 0.4) and len(line1_words) > 1:
                         should_adjust = True
                except AttributeError:
                    line2_words = line2_text.split()
                    if len(line2_words) == 1 and len(line1_words) > 1:
                        should_adjust = True

                if should_adjust:
                    print(f"Adjusting title lines...")
                    last_word_line1 = line1_words.pop()
                    new_line1_text = " ".join(line1_words)
                    if new_line1_text.strip():
                        new_line2_text = f"{last_word_line1} {line2_text}"
                        wrapped_title_lines = [new_line1_text, new_line2_text]
                        print(f"Adjusted title lines:\n1: {new_line1_text}\n2: {new_line2_text}")
                    else:
                         print("Title line adjustment aborted: Line 1 would become empty.")
            # --- סוף לוגיקת איזון ---

            # 4. Calculate Title Block Dimensions
            title_line_height = 0
            max_title_line_width = 0
            title_line_details = []
            for line in wrapped_title_lines:
                try:
                    line_bbox = draw.textbbox((0, 0), line, font=title_font)
                    current_line_width = line_bbox[2] - line_bbox[0]
                    current_line_height = line_bbox[3] - line_bbox[1]
                    title_line_details.append({'text': line, 'width': current_line_width, 'height': current_line_height, 'bbox': line_bbox})
                    if title_line_height == 0 and current_line_height > 0:
                         title_line_height = current_line_height
                    max_title_line_width = max(max_title_line_width, current_line_width)
                except AttributeError:
                     # Fallback...
                     current_line_width = draw.textlength(line, font=title_font) if hasattr(draw, 'textlength') else len(line) * title_font_size * 0.6
                     title_line_details.append({'text': line, 'width': current_line_width, 'height': title_font_size * 1.2, 'bbox': None}) # Approximation
                     if title_line_height == 0: title_line_height = title_font_size * 1.2
                     max_title_line_width = max(max_title_line_width, current_line_width)

            if title_line_height == 0: title_line_height = title_font_size * 1.2
            total_title_block_height = len(wrapped_title_lines) * title_line_height

            # --- הוספה: חישוב גובה ורוחב של בלוק האמן (אם קיים) ---
            artist_line_height = 0
            total_artist_block_height = 0
            artist_line_details = []
            vertical_offset = 0
            if render_artist:
                artist_vertical_offset_from_title = self.artist_style.get('vertical_offset_from_title', 10) # Default offset
                vertical_offset += artist_vertical_offset_from_title # הוסף את המרווח לגובה הכולל

                # הנחה פשוטה: שם האמן הוא שורה אחת ולא עובר גלישה (ניתן להרחיב אם צריך)
                # אם שם האמן עלול להיות ארוך, תצטרך להוסיף כאן לוגיקת wrap_text דומה לכותרת
                artist_line = artist_name_text.strip()
                if artist_line:
                    try:
                        bbox = draw.textbbox((0,0), artist_line, font=artist_font)
                        a_width = bbox[2] - bbox[0]
                        a_height = bbox[3] - bbox[1]
                        artist_line_details.append({'text': artist_line, 'width': a_width, 'height': a_height, 'bbox': bbox})
                        artist_line_height = a_height if a_height > 0 else artist_font.size * 1.2
                    except AttributeError:
                         # Fallback...
                         a_width = draw.textlength(artist_line, font=artist_font) if hasattr(draw, 'textlength') else len(artist_line) * artist_font.size * 0.6
                         artist_line_height = artist_font.size * 1.2
                         artist_line_details.append({'text': artist_line, 'width': a_width, 'height': artist_line_height, 'bbox': None})

                    total_artist_block_height = artist_line_height

            # 5. Calculate Combined Starting Position
            total_combined_height = total_title_block_height + vertical_offset + total_artist_block_height
            start_y = (video_h - total_combined_height) / 2

            # 6. Draw Title Lines
            current_y = start_y
            for detail in title_line_details:
                line_text = detail['text']
                line_width = detail['width']
                line_x = (video_w - line_width) / 2
                self._draw_text_with_stroke(
                    draw=draw, pos=(line_x, current_y), text=line_text, font=title_font,
                    fill_color=self.title_style['color'],
                    stroke_color=self.title_style.get('stroke_color'),
                    stroke_width=self.title_style.get('stroke_width', 0)
                )
                current_y += title_line_height # התקדמות לפי גובה שורת כותרת

            # --- הוספה: ציור שם הזמר ---
            if render_artist and artist_line_details:
                current_y += vertical_offset # הוסף את המרווח לפני ציור האמן

                # נניח שכרגע יש רק שורה אחת לאמן
                artist_detail = artist_line_details[0]
                artist_text = artist_detail['text']
                artist_width = artist_detail['width']
                artist_x = (video_w - artist_width) / 2

                # ציור האמן
                self._draw_text_with_stroke(
                    draw=draw, pos=(artist_x, current_y), text=artist_text, font=artist_font,
                    fill_color=self.artist_style['color'],
                    stroke_color=self.artist_style.get('stroke_color'),
                    stroke_width=self.artist_style.get('stroke_width', 0)
                )
                # אם היו מספר שורות לאמן, היית צריך לולאה ולקדם את current_y בהתאם
            # --- סוף הוספה ---


            # 7. Convert PIL Image to NumPy array
            frame_array = np.array(img)

            # 8. Create MoviePy ImageClip
            title_clip = mp.ImageClip(frame_array, ismask=False, transparent=True)
            title_clip = title_clip.set_duration(title_duration).set_start(0)

            print("Title clip (with optional artist) created using PIL.")
            return title_clip

        except Exception as e:
            print(f"Error creating title clip using PIL: {e}")
            traceback.print_exc()
            return None


    # --- Subtitle Rendering Helpers (ללא שינוי) ---
    def _draw_text_with_stroke(self, draw, pos, text, font, fill_color, stroke_color, stroke_width):
        """Draws text with an outline using PIL."""
        # ... (קוד זהה) ...
        x, y = pos
        if stroke_width > 0 and stroke_color:
            offset = stroke_width
            draw.text((x - offset, y), text, font=font, fill=stroke_color)
            draw.text((x + offset, y), text, font=font, fill=stroke_color)
            draw.text((x, y - offset), text, font=font, fill=stroke_color)
            draw.text((x, y + offset), text, font=font, fill=stroke_color)
        draw.text((x, y), text, font=font, fill=fill_color)


    def _is_hebrew(self, text_line):
        """Checks if a string contains Hebrew characters."""
        # ... (קוד זהה) ...
        return any('\u0590' <= char <= '\u05FF' for char in text_line)


    def _wrap_text(self, draw, line_text, font, max_width):
            """Wraps a single line of text to fit max_width."""
            # ... (קוד זהה) ...
            words = line_text.split(' ')
            wrapped_lines = []
            current_line = ''
            for word in words:
                if not word: continue
                test_line = f"{current_line} {word}".strip()
                try:
                    bbox = draw.textbbox((0, 0), test_line, font=font)
                    line_width = bbox[2] - bbox[0]
                except AttributeError:
                    try:
                        line_width = draw.textlength(test_line, font=font)
                    except AttributeError:
                        line_width = len(test_line) * font.size * 0.6

                if line_width <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        wrapped_lines.append(current_line)
                    current_line = word
                    try:
                        bbox_word = draw.textbbox((0, 0), current_line, font=font)
                        word_width = bbox_word[2] - bbox_word[0]
                    except AttributeError:
                         try:
                              word_width = draw.textlength(current_line, font=font)
                         except AttributeError:
                              word_width = len(current_line) * font.size * 0.6

                    if word_width > max_width and len(wrapped_lines) > 0 :
                         wrapped_lines.append(current_line)
                         current_line = ""
                    elif word_width > max_width and len(wrapped_lines) == 0:
                         wrapped_lines.append(current_line)
                         current_line = ""

            if current_line:
                wrapped_lines.append(current_line)
            return wrapped_lines if wrapped_lines else ([line_text.strip()] if line_text.strip() else [])


    def _create_styled_subtitle_clip_pil(self, subs_data_en, subs_data_he, total_duration):
        """
        Creates the subtitle clip using PIL for rendering BiDi text with stroke...
        (הפונקציה הזו נשארת ללא שינוי מבחינת הלוגיקה שלה, היא עוסקת בכתוביות ולא בכותרת/אמן)
        """
        # ... (כל הקוד של הפונקציה הזו נשאר זהה) ...
        print("Processing combined subtitles (EN/HE) using PIL with BiDi...")
        subs_en = subs_data_en if isinstance(subs_data_en, list) else []
        subs_he = subs_data_he if isinstance(subs_data_he, list) else []
        combined_subs_format = [] # Will store ((start, end), text, unique_id)
        self.combined_subs_list_for_frames = [] # Reset for this run
        subtitle_id_counter = 0

        if not subs_en and not subs_he:
            print("Warning: No subtitle data provided (English or Hebrew).")
            empty_clip = mp.ColorClip(size=self.video_settings['resolution'], color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0)
            return empty_clip, []

        subs_en_map = {str(sub.get('id', f'en_{i}')): sub for i, sub in enumerate(subs_en)}
        subs_he_map = {str(sub.get('id', f'he_{i}')): sub for i, sub in enumerate(subs_he)}

        def sort_key(id_str):
             match = re.search(r'\d+', str(id_str))
             return int(match.group()) if match else float('inf')

        all_ids = sorted(list(set(subs_en_map.keys()) | set(subs_he_map.keys())), key=sort_key)
        print(f"DEBUG: Starting merge. Found {len(subs_en_map)} EN keys, {len(subs_he_map)} HE keys. Total unique IDs: {len(all_ids)}")

        # --- Merge Logic (largely unchanged, uses parsed data) ---
        for idx_str in all_ids:
            sub_en = subs_en_map.get(idx_str)
            sub_he = subs_he_map.get(idx_str)
            en_start, en_end, en_text = (0, 0, "")
            he_start, he_end, he_text = (0, 0, "")
            valid_en, valid_he = False, False

            try:
                if sub_en and 'start_time' in sub_en and 'end_time' in sub_en and 'text' in sub_en:
                    en_start = max(0, float(sub_en['start_time']))
                    en_end = max(en_start, float(sub_en['end_time']))
                    en_text_raw = sub_en.get('text', '')
                    en_text = str(en_text_raw).strip().replace('\\n', '\n')
                    if en_end > en_start: valid_en = True
            except (ValueError, TypeError) as e: print(f"Warning: Invalid data in English sub ID {idx_str}: {e}")

            try:
                if sub_he and 'start_time' in sub_he and 'end_time' in sub_he and 'text' in sub_he:
                    he_start = max(0, float(sub_he['start_time']))
                    he_end = max(he_start, float(sub_he['end_time']))
                    he_text_raw = sub_he.get('text', '')
                    he_text = str(he_text_raw).strip().replace('\\n', '\n')
                    if he_end > he_start: valid_he = True
            except (ValueError, TypeError) as e: print(f"Warning: Invalid data in Hebrew sub ID {idx_str}: {e}")

            combined_text_parts = []
            start_time = float('inf')
            end_time = 0
            has_en_text = valid_en and en_text
            has_he_text = valid_he and he_text

            if has_en_text:
                combined_text_parts.append(en_text)
                start_time = min(start_time, en_start)
                end_time = max(end_time, en_end)

            if has_he_text:
                combined_text_parts.append(he_text)
                start_time = min(start_time, he_start)
                end_time = max(end_time, he_end)

            if not has_en_text and not has_he_text:
                 if valid_en:
                     start_time = min(start_time, en_start)
                     end_time = max(end_time, en_end)
                 if valid_he:
                     start_time = min(start_time, he_start)
                     end_time = max(end_time, he_end)

            if combined_text_parts or (start_time != float('inf') and end_time > 0):
                separator = "\n\n" if has_en_text and has_he_text else ""
                combined_text = separator.join(combined_text_parts)
                sub_id = f"combined_{idx_str}_{subtitle_id_counter}"
                subtitle_id_counter += 1
                min_duration = 1.0 / self.video_settings['fps']
                start_time = 0 if start_time == float('inf') else start_time
                if end_time <= start_time: end_time = start_time + min_duration
                start_time = min(start_time, total_duration)
                end_time = min(end_time, total_duration)

                if end_time > start_time:
                    time_interval = (start_time, end_time)
                    combined_subs_format.append((time_interval, combined_text, sub_id))
        # --- End Merge Logic ---

        if not combined_subs_format:
            print("Warning: No valid combined subtitles were created.")
            empty_clip = mp.ColorClip(size=self.video_settings['resolution'], color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0)
            return empty_clip, []

        combined_subs_format.sort(key=lambda item: item[0][0])
        print(f"DEBUG: Finished merge. Combined {len(combined_subs_format)} subtitle entries.")
        self.combined_subs_list_for_frames = combined_subs_format

        # --- PIL Text Rendering Generator Function (ללא שינוי) ---
        def generator(txt):
            # ... (קוד זהה) ...
            try:
                font_en = ImageFont.truetype(self.subtitle_font_path, self.subtitle_style['english']['font_size'])
                font_he = ImageFont.truetype(self.subtitle_font_path, self.subtitle_style['hebrew']['font_size'])
            except Exception as e:
                print(f"CRITICAL Error loading PIL subtitle font '{self.subtitle_font_path}': {e}")
                return mp.ImageClip(np.zeros((10, 10, 4), dtype=np.uint8), ismask=False, transparent=True).set_duration(0.1)

            video_w, video_h = self.video_settings['resolution']
            max_text_width = video_w * 0.85

            if not txt or not txt.strip():
                empty_frame = np.zeros((video_h, video_w, 4), dtype=np.uint8)
                return mp.ImageClip(empty_frame, ismask=False, transparent=True).set_duration(1.0 / self.video_settings['fps'])

            img = Image.new('RGBA', (video_w, video_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            language_blocks = txt.split('\n\n')
            processed_lines_details = []
            total_text_height = 0
            line_counter = 0

            sub_color = self.subtitle_style['common']['color']
            sub_stroke_color = self.subtitle_style['common'].get('stroke_color')
            sub_stroke_width = self.subtitle_style['common'].get('stroke_width', 0)
            spacing_within = self.subtitle_style['layout']['spacing_within_language']
            spacing_between = self.subtitle_style['layout']['spacing_between_languages']

            for block_index, block in enumerate(language_blocks):
                original_lines_in_block = [line for line in block.splitlines() if line.strip()]
                if not original_lines_in_block: continue

                is_heb_block = self._is_hebrew(original_lines_in_block[0])
                font_for_block = font_he if is_heb_block else font_en

                for i, line in enumerate(original_lines_in_block):
                    wrapped_lines = self._wrap_text(draw, line, font_for_block, max_text_width)

                    for k, wrapped_line in enumerate(wrapped_lines):
                        try:
                            bbox = draw.textbbox((0, 0), wrapped_line, font=font_for_block)
                            line_width = bbox[2] - bbox[0]
                            line_height = bbox[3] - bbox[1]
                        except AttributeError:
                            line_width = draw.textlength(wrapped_line, font=font_for_block) if hasattr(draw, 'textlength') else 100
                            line_height = font_for_block.size * 1.2

                        is_last_wrapped_in_line = (k == len(wrapped_lines) - 1)
                        is_last_line_in_block = (i == len(original_lines_in_block) - 1)
                        is_last_block = (block_index == len(language_blocks) - 1)

                        spacing_after_this_line = 0
                        if not is_last_wrapped_in_line: spacing_after_this_line = spacing_within
                        elif not is_last_line_in_block: spacing_after_this_line = spacing_within
                        elif not is_last_block: spacing_after_this_line = spacing_between

                        line_detail = {
                            'text': wrapped_line, 'font': font_for_block, 'is_hebrew': is_heb_block,
                            'width': line_width, 'height': line_height,
                            'spacing_after': spacing_after_this_line, 'line_index': line_counter
                        }
                        processed_lines_details.append(line_detail)
                        total_text_height += line_height + spacing_after_this_line
                        line_counter += 1

            if processed_lines_details:
                total_text_height -= processed_lines_details[-1]['spacing_after']

            current_y = (video_h - total_text_height) / 2 # מרכוז אנכי של כל בלוק הכתוביות

            for detail in processed_lines_details:
                x_pos = (video_w - detail['width']) / 2
                text_to_draw = detail['text']

                if detail['is_hebrew']:
                    try:
                        reshaped_text = arabic_reshaper.reshape(text_to_draw)
                        text_to_draw = get_display(reshaped_text)
                    except Exception as e:
                        print(f"Warning: BiDi reshaping/display failed for '{text_to_draw}': {e}")

                self._draw_text_with_stroke(
                    draw, (x_pos, current_y), text_to_draw, detail['font'],
                    sub_color, sub_stroke_color, sub_stroke_width
                )
                current_y += detail['height'] + detail['spacing_after']

            frame_array = np.array(img)
            return mp.ImageClip(frame_array, ismask=False, transparent=True).set_duration(1.0 / self.video_settings['fps'])
        # --- End of PIL Generator Function ---

        subs_for_moviepy = [(item[0], item[1]) for item in combined_subs_format]

        if not subs_for_moviepy:
             print("Warning: No subtitle data to feed into MoviePy SubtitlesClip.")
             empty_clip = mp.ColorClip(size=self.video_settings['resolution'], color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0)
             return empty_clip, self.combined_subs_list_for_frames

        try:
            subtitle_moviepy_clip = SubtitlesClip(subs_for_moviepy, generator)
            subtitle_moviepy_clip = subtitle_moviepy_clip.set_duration(total_duration).set_position('center') # Position is handled by generator drawing now
            print(f"SubtitlesClip created successfully. Duration: {subtitle_moviepy_clip.duration:.2f}s")
            return subtitle_moviepy_clip, self.combined_subs_list_for_frames
        except Exception as e:
            print(f"CRITICAL Error creating MoviePy SubtitlesClip: {e}")
            traceback.print_exc()
            empty_clip = mp.ColorClip(size=self.video_settings['resolution'], color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0)
            return empty_clip, []


    # --- Frame Saving Logic (ללא שינוי) ---
    def _sanitize_filename(self, text, max_len=50):
        """Cleans text to be suitable for a filename."""
        # ... (קוד זהה) ...
        text = text.replace('\n', ' ').replace('\r', '')
        text = re.sub(r'[\\/*?:"<>|.!@#$%^&+=~`{}\[\];\'’,]', "", text)
        text = text.strip()
        text = re.sub(r'\s+', '_', text)
        if not text: return "subtitle"

        if len(text) > max_len:
            cut_point = text.rfind('_', 0, max_len)
            if cut_point != -1 and cut_point > max_len // 2 :
                 text = text[:cut_point] + "_etc"
            else:
                 text = text[:max_len] + "_etc"
        return text


    def _save_subtitle_frame_processor(self, get_frame, t):
        """
        MoviePy frame processor function (called via fl).
        Saves a frame when a new subtitle (with text) appears.
        (הפונקציה הזו נשארת ללא שינוי)
        """
        # ... (כל הקוד של הפונקציה הזו נשאר זהה) ...
        try:
            frame = get_frame(t)
            if frame is None:
                 return np.zeros((self.video_settings['resolution'][1], self.video_settings['resolution'][0], 3), dtype=np.uint8)
        except Exception as e:
             # Provide a default frame on error to avoid crashing the render
            # print(f"Warning: Error in get_frame({t:.3f}): {e}")
            return np.zeros((self.video_settings['resolution'][1], self.video_settings['resolution'][0], 3), dtype=np.uint8) # Return black frame

        active_sub_info = None
        epsilon = 1 / (self.video_settings['fps'] * 2) # Small offset for timing checks
        for interval, text, sub_id in self.combined_subs_list_for_frames:
            start_time, end_time = interval
            # Check if time 't' falls within the subtitle interval (considering epsilon)
            if (start_time - epsilon) <= t < (end_time - epsilon):
                if text and text.strip(): # Only consider subtitles with actual text content
                     active_sub_info = (text, sub_id, start_time)
                break # Found the active subtitle for this time 't'

        if active_sub_info:
            text, sub_id, start_time = active_sub_info
            if sub_id not in self.saved_subtitle_ids:
                # Save frame for this new subtitle ID
                try:
                    time_sec = int(start_time)
                    time_ms = int((start_time - time_sec) * 1000)
                    time_str = f"{time_sec:04d}_{time_ms:03d}" # Format: 0015_320 for 15.320s
                    safe_text = self._sanitize_filename(text)
                    filename_base = f"frame_{time_str}_{safe_text}"
                    max_fname_len = 150 # Limit filename length
                    # Use the absolute path from config
                    filename = os.path.join(self.output_frames_dir, f"{filename_base[:max_fname_len]}.png")

                    # Ensure frame is RGB before saving
                    if frame.shape[2] == 4: # Check if alpha channel exists
                        frame_rgb = frame[..., :3] # Select only R, G, B channels
                    else:
                         frame_rgb = frame # Assume it's already RGB

                    imageio.imwrite(filename, frame_rgb)
                    self.saved_subtitle_ids.add(sub_id)
                    # print(f"Saved frame for sub_id {sub_id} at t={t:.3f}s -> {os.path.basename(filename)}")

                except Exception as e:
                    print(f"Error saving frame at t={t:.3f}s (sub_id: {sub_id}): {e}")
                    # Add to set even if saving failed to prevent repeated attempts/errors
                    self.saved_subtitle_ids.add(sub_id)

        # Crucially, return the original frame for video composition
        return frame


    # --- Main Video Creation Method (Modified Signature) ---

    # --- שינוי: הוספת פרמטר artist_name_text ---
    def create_video(self, mp3_path, song_title_text, artist_name_text, english_subtitle_data, hebrew_subtitle_data, output_video_filename_base):
        """
        Orchestrates the video creation process using external config.
        Includes separate intro background and PIL-based title/artist rendering.
        """
        print(f"\n--- Starting Video Creation for: {output_video_filename_base} ---")
        output_video_file = os.path.join(self.output_video_dir, f"{output_video_filename_base}_subtitled.mp4")
        temp_audio_file = os.path.join(self.output_video_dir, f'temp-audio-{output_video_filename_base}-{int(time.time())}.m4a')

        audio_clip = None
        background_clip = None
        intro_background_clip = None
        title_clip = None # This will now contain both title and artist
        subtitles_clip = None
        final_clip_for_render = None

        try:
            # 1. Load Audio
            audio_clip, audio_duration = self._load_audio(mp3_path)

            # 2. Create Main Background (Full Duration)
            background_clip = self._create_background_clip(audio_duration)

            # 3. Determine Title Duration
            first_sub_time = self._get_first_subtitle_time(english_subtitle_data, hebrew_subtitle_data, audio_duration)
            min_title_threshold = 0.5
            title_duration = first_sub_time if first_sub_time >= min_title_threshold else 0

            # 4. Create Intro Background Clip (If applicable)
            if title_duration > 0 and self.intro_background_image_path:
                print("Creating intro background clip...")
                try:
                    intro_background_clip = mp.ImageClip(self.intro_background_image_path, duration=title_duration)
                    target_w, target_h = self.video_settings['resolution']
                    intro_background_clip = intro_background_clip.resize(height=target_h)
                    if intro_background_clip.w > target_w:
                        intro_background_clip = intro_background_clip.crop(x_center=intro_background_clip.w / 2, width=target_w)
                    intro_background_clip = intro_background_clip.resize((target_w, target_h))
                    intro_background_clip = intro_background_clip.set_fps(self.video_settings['fps'])
                    intro_background_clip = intro_background_clip.set_start(0).set_duration(title_duration)
                    print("Intro background clip created.")
                except Exception as e:
                    print(f"Warning: Could not create intro background clip from '{self.intro_background_image_path}': {e}")
                    intro_background_clip = None

            # --- שינוי: העברת שם הזמר ליצירת קליפ הכותרת ---
            # 5. Create Title Clip (Using PIL, now includes artist)
            title_clip = self._create_title_clip(song_title_text, artist_name_text, title_duration)
            # --- סוף שינוי ---

            # 6. Create Subtitle Clip (ללא שינוי כאן)
            subtitles_clip, _ = self._create_styled_subtitle_clip_pil(
                english_subtitle_data, hebrew_subtitle_data, audio_duration
            )
            if not subtitles_clip or subtitles_clip.duration <= 0:
                 print("Warning: Subtitle clip generation failed or resulted in an empty clip.")
                 subtitles_clip = None
            elif subtitles_clip.duration > audio_duration + 1:
                print(f"Warning: Subtitles clip duration ({subtitles_clip.duration:.2f}s) significantly exceeds audio duration ({audio_duration:.2f}s). Trimming.")
                subtitles_clip = subtitles_clip.set_duration(audio_duration)


            # 7. Composite Clips (Order Matters!)
            print("Compositing video layers...")
            clips_to_composite = [background_clip] # Start with main background

            if intro_background_clip:
                clips_to_composite.append(intro_background_clip) # Layer intro bg on top if exists
                print("Adding intro background layer.")
            else:
                 print("Using main background for intro section.")

            if title_clip: # title_clip now potentially includes the artist
                clips_to_composite.append(title_clip) # Add Title/Artist layer

            if subtitles_clip:
                clips_to_composite.append(subtitles_clip) # Add Subtitles layer last (topmost text)
            else:
                 print("Info: No valid subtitle clip to composite.")

            composite_video = mp.CompositeVideoClip(clips_to_composite, size=self.video_settings['resolution'])
            composite_video = composite_video.set_duration(audio_duration)

            # 8. Apply Frame Saving (Logic unchanged)
            print("Attaching frame saving processor...")
            if self.combined_subs_list_for_frames:
                 final_video_layers = composite_video.fl(self._save_subtitle_frame_processor, apply_to=['color'])
                 final_video_layers = final_video_layers.set_duration(audio_duration)
                 print("Frame saving enabled.")
            else:
                print("No subtitle data for frame saving, skipping processor attachment.")
                final_video_layers = composite_video

            # 9. Add Audio
            print("Adding audio...")
            final_clip_for_render = final_video_layers.set_audio(audio_clip)
            final_clip_for_render = final_clip_for_render.set_duration(audio_duration)

            # 10. Write Video File (Logic unchanged)
            print(f"Writing final video to '{output_video_file}'...")
            if not final_clip_for_render or final_clip_for_render.duration <= 0:
                 raise ValueError("Final video clip for rendering is invalid or has zero duration.")

            self.saved_subtitle_ids = set() # Reset before render

            final_clip_for_render.write_videofile(
                output_video_file,
                fps=self.video_settings['fps'],
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=temp_audio_file,
                remove_temp=True,
                threads=max(1, (os.cpu_count() or 2) // 2),
                preset='medium',
                logger='bar',
                # ffmpeg_params=["-loglevel", "error"] # Uncomment for less ffmpeg output
            )
            print(f"\nVideo creation successful: '{output_video_file}'")
            if self.combined_subs_list_for_frames:
                 if self.saved_subtitle_ids:
                    print(f"Subtitle frames saved in: '{self.output_frames_dir}'")
                 else:
                    print("No subtitle frames were saved (perhaps no text content in subs?).")

            return output_video_file

        except FileNotFoundError as e:
             print(f"\nError: Required file not found. {e}")
             traceback.print_exc()
             return None
        except ValueError as e:
            print(f"\nError: Invalid value encountered. {e}")
            traceback.print_exc()
            return None
        except Exception as e:
            print(f"\nAn unexpected error occurred during video creation: {e}")
            traceback.print_exc()
            return None

        finally:
            print("Releasing resources...")
            # Add intro_background_clip to the list of clips to close
            for clip in [audio_clip, background_clip, intro_background_clip, title_clip, subtitles_clip, final_clip_for_render]:
                 if clip and hasattr(clip, 'close') and callable(getattr(clip, 'close', None)):
                    try:
                        clip.close()
                    except Exception as e_close:
                        print(f"Warning: Error closing a clip object: {e_close}")

            if os.path.exists(temp_audio_file):
                try:
                    os.remove(temp_audio_file)
                except Exception as e:
                    print(f"Warning: Could not remove temporary audio file '{temp_audio_file}': {e}")

            print("--- Video Creation Process Finished ---")