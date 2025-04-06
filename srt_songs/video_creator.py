import os
import re
import moviepy.editor as mp
from moviepy.video.tools.subtitles import SubtitlesClip
import imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
import time # For unique filenames if needed
import traceback # For detailed error reporting

class VideoCreator:
    """
    Creates a video file with background, optional title, subtitles, and audio.
    Handles subtitle rendering using PIL for advanced text layout (BiDi, stroke).
    Includes logic for saving subtitle frames.
    Configuration is loaded from an external JSON file via the main script.
    """
    def __init__(self, resolved_config):
        """
        Initializes the VideoCreator with resolved configuration settings.

        Args:
            resolved_config (dict): A dictionary containing configuration with
                                    *absolute paths* already resolved.
                                    Expected keys based on video_config.json structure:
                                    - paths (dict with absolute paths: assets_dir, fonts_dir, output_frames_dir, output_video_dir)
                                    - video_settings (dict)
                                    - background (dict with absolute background_image_path)
                                    - title_style (dict with font_name, size, color, etc.)
                                    - subtitle_style (dict with font_name, common, english, hebrew, layout sections)
        """
        self.cfg = resolved_config # Store the resolved config

        # Extract key paths and settings for easier access
        self.paths = self.cfg['paths']
        self.video_settings = self.cfg['video_settings']
        self.bg_settings = self.cfg['background']
        self.title_style = self.cfg['title_style']
        self.subtitle_style = self.cfg['subtitle_style']

        # Construct absolute font paths
        self.title_font_path = os.path.join(self.paths['fonts_dir'], self.title_style['font_name'])
        self.subtitle_font_path = os.path.join(self.paths['fonts_dir'], self.subtitle_style['font_name'])

        # --- Use paths directly from resolved_config ---
        self.background_image_path = self.bg_settings['background_image_path']
        self.output_frames_dir = self.paths['output_frames_dir']
        self.output_video_dir = self.paths['output_dir'] # Use the correct key 'output_dir'
        # --- End paths ---

        self._validate_paths()
        self._ensure_dirs_exist() # Directories should already be created by main, but double-check

        # State for frame saving during render
        self.combined_subs_list_for_frames = []
        self.saved_subtitle_ids = set()

    def _validate_paths(self):
        """Checks if essential files (fonts, background) exist using absolute paths."""
        if not os.path.exists(self.title_font_path):
            raise FileNotFoundError(f"Error: Title font file not found at '{self.title_font_path}'")
        if not os.path.exists(self.subtitle_font_path):
            raise FileNotFoundError(f"Error: Subtitle font file not found at '{self.subtitle_font_path}'")
        if not os.path.exists(self.background_image_path):
            raise FileNotFoundError(f"Error: Background image not found at '{self.background_image_path}'")

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

    def _create_title_clip(self, song_title_text, title_duration):
        """Creates the title text clip using settings from title_style."""
        if title_duration <= 0:
            print("Title duration is zero or negative, skipping title clip creation.")
            return None

        print(f"Creating title clip for duration: {title_duration:.2f}s")
        try:
            title_clip = mp.TextClip(song_title_text, font=self.title_font_path, # Use resolved path
                                     fontsize=self.title_style['font_size'],
                                     color=self.title_style['color'],
                                     stroke_color=self.title_style.get('stroke_color'), # Use .get for optional keys
                                     stroke_width=self.title_style.get('stroke_width', 0),
                                     method='label')

            # Resize if too wide
            max_width = self.video_settings['resolution'][0] * 0.9
            if title_clip.w > max_width:
                 title_clip = title_clip.resize(width=max_width)

            # Position uses list from JSON -> tuple for moviepy
            pos = tuple(self.title_style['position'])
            title_clip = title_clip.set_position(pos)
            title_clip = title_clip.set_duration(title_duration).set_start(0)
            print("Title clip created.")
            return title_clip
        except Exception as e:
            print(f"Error creating title clip: {e}")
            traceback.print_exc()
            return None

    # --- Subtitle Rendering Helpers ---

    def _draw_text_with_stroke(self, draw, pos, text, font, fill_color, stroke_color, stroke_width):
        """Draws text with an outline using PIL."""
        x, y = pos
        # Only draw stroke if width > 0 and color is defined
        if stroke_width > 0 and stroke_color:
            offset = stroke_width
            draw.text((x - offset, y), text, font=font, fill=stroke_color)
            draw.text((x + offset, y), text, font=font, fill=stroke_color)
            draw.text((x, y - offset), text, font=font, fill=stroke_color)
            draw.text((x, y + offset), text, font=font, fill=stroke_color)
            # Optional: Diagonal strokes for thicker outline (might be overkill)
            # draw.text((x-offset, y-offset), text, font=font, fill=stroke_color)
            # draw.text((x+offset, y-offset), text, font=font, fill=stroke_color)
            # draw.text((x-offset, y+offset), text, font=font, fill=stroke_color)
            # draw.text((x+offset, y+offset), text, font=font, fill=stroke_color)

        # Draw fill color on top
        draw.text((x, y), text, font=font, fill=fill_color)

    def _is_hebrew(self, text_line):
        """Checks if a string contains Hebrew characters."""
        return any('\u0590' <= char <= '\u05FF' for char in text_line)

    def _wrap_text(self, draw, line_text, font, max_width):
            """Wraps a single line of text to fit max_width."""
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
        Creates the subtitle clip using PIL for rendering BiDi text with stroke,
        using styles from subtitle_style config.
        Also prepares the list used for frame saving.
        """
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

        # --- PIL Text Rendering Generator Function ---
        def generator(txt):
            try:
                # Use font sizes from config
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

            # Extract common subtitle styles
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

            current_y = (video_h - total_text_height) / 2

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
                    sub_color, sub_stroke_color, sub_stroke_width # Use extracted styles
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
            subtitle_moviepy_clip = subtitle_moviepy_clip.set_duration(total_duration).set_position('center')
            print(f"SubtitlesClip created successfully. Duration: {subtitle_moviepy_clip.duration:.2f}s")
            return subtitle_moviepy_clip, self.combined_subs_list_for_frames
        except Exception as e:
            print(f"CRITICAL Error creating MoviePy SubtitlesClip: {e}")
            traceback.print_exc()
            empty_clip = mp.ColorClip(size=self.video_settings['resolution'], color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0)
            return empty_clip, []


    # --- Frame Saving Logic ---

    def _sanitize_filename(self, text, max_len=50):
        """Cleans text to be suitable for a filename."""
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
        """
        try:
            frame = get_frame(t)
            if frame is None:
                 return np.zeros((self.video_settings['resolution'][1], self.video_settings['resolution'][0], 3), dtype=np.uint8)
        except Exception as e:
            return np.zeros((self.video_settings['resolution'][1], self.video_settings['resolution'][0], 3), dtype=np.uint8)

        active_sub_info = None
        epsilon = 1 / (self.video_settings['fps'] * 2)
        for interval, text, sub_id in self.combined_subs_list_for_frames:
            start_time, end_time = interval
            if (start_time - epsilon) <= t < (end_time - epsilon):
                if text and text.strip():
                     active_sub_info = (text, sub_id, start_time)
                break

        if active_sub_info:
            text, sub_id, start_time = active_sub_info
            if sub_id not in self.saved_subtitle_ids:
                try:
                    time_sec = int(start_time)
                    time_ms = int((start_time - time_sec) * 1000)
                    time_str = f"{time_sec:04d}_{time_ms:03d}"
                    safe_text = self._sanitize_filename(text)
                    filename_base = f"frame_{time_str}_{safe_text}"
                    max_fname_len = 150
                    # Use the absolute path from config
                    filename = os.path.join(self.output_frames_dir, f"{filename_base[:max_fname_len]}.png")

                    if frame.shape[2] == 4:
                        frame_rgb = frame[..., :3]
                    else:
                         frame_rgb = frame

                    imageio.imwrite(filename, frame_rgb)
                    self.saved_subtitle_ids.add(sub_id)

                except Exception as e:
                    print(f"Error saving frame at t={t:.3f}s (sub_id: {sub_id}): {e}")
                    self.saved_subtitle_ids.add(sub_id)

        return frame


    # --- Main Video Creation Method ---

    def create_video(self, mp3_path, song_title_text, english_subtitle_data, hebrew_subtitle_data, output_video_filename_base):
        """
        Orchestrates the video creation process using external config.

        Args:
            mp3_path (str): Path to the input audio file.
            song_title_text (str): Text for the title card.
            english_subtitle_data (list | None): Parsed English subtitle data.
            hebrew_subtitle_data (list | None): Parsed Hebrew subtitle data.
            output_video_filename_base (str): Base name for the output video file (without extension).

        Returns:
            str | None: The path to the created video file, or None if creation failed.
        """
        print(f"\n--- Starting Video Creation for: {output_video_filename_base} ---")
        # Use the absolute output dir path
        output_video_file = os.path.join(self.output_video_dir, f"{output_video_filename_base}_subtitled.mp4")
        temp_audio_file = os.path.join(self.output_video_dir, f'temp-audio-{output_video_filename_base}-{int(time.time())}.m4a')

        audio_clip = None
        background_clip = None
        title_clip = None
        subtitles_clip = None
        final_clip_for_render = None

        try:
            audio_clip, audio_duration = self._load_audio(mp3_path)
            background_clip = self._create_background_clip(audio_duration)

            first_sub_time = self._get_first_subtitle_time(english_subtitle_data, hebrew_subtitle_data, audio_duration)
            min_title_threshold = 0.5
            title_duration = first_sub_time if first_sub_time >= min_title_threshold else 0
            title_clip = self._create_title_clip(song_title_text, title_duration)

            subtitles_clip, _ = self._create_styled_subtitle_clip_pil(
                english_subtitle_data, hebrew_subtitle_data, audio_duration
            )
            if not subtitles_clip or subtitles_clip.duration <= 0:
                 print("Warning: Subtitle clip generation failed or resulted in an empty clip.")
                 subtitles_clip = None
            elif subtitles_clip.duration > audio_duration + 1:
                print(f"Warning: Subtitles clip duration ({subtitles_clip.duration:.2f}s) significantly exceeds audio duration ({audio_duration:.2f}s). Trimming.")
                subtitles_clip = subtitles_clip.set_duration(audio_duration)

            print("Compositing video layers...")
            clips_to_composite = [background_clip]
            if title_clip: clips_to_composite.append(title_clip)
            if subtitles_clip: clips_to_composite.append(subtitles_clip)
            else: print("Info: No valid subtitle clip to composite.")

            # Use resolution from config
            composite_video = mp.CompositeVideoClip(clips_to_composite, size=self.video_settings['resolution'])
            composite_video = composite_video.set_duration(audio_duration)

            print("Attaching frame saving processor...")
            if self.combined_subs_list_for_frames:
                 final_video_layers = composite_video.fl(self._save_subtitle_frame_processor, apply_to=['color'])
                 final_video_layers = final_video_layers.set_duration(audio_duration)
                 print("Frame saving enabled.")
            else:
                print("No subtitle data for frame saving, skipping processor attachment.")
                final_video_layers = composite_video

            print("Adding audio...")
            final_clip_for_render = final_video_layers.set_audio(audio_clip)
            final_clip_for_render = final_clip_for_render.set_duration(audio_duration)

            print(f"Writing final video to '{output_video_file}'...")
            if not final_clip_for_render or final_clip_for_render.duration <= 0:
                 raise ValueError("Final video clip for rendering is invalid or has zero duration.")

            self.saved_subtitle_ids = set() # Reset before render

            final_clip_for_render.write_videofile(
                output_video_file,
                fps=self.video_settings['fps'], # Use FPS from config
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=temp_audio_file,
                remove_temp=True,
                threads=max(1, (os.cpu_count() or 2) // 2),
                preset='medium',
                logger='bar',
                # ffmpeg_params=["-loglevel", "error"]
            )
            print(f"\nVideo creation successful: '{output_video_file}'")
            if self.combined_subs_list_for_frames:
                 if self.saved_subtitle_ids:
                     # Use absolute path from config
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
            for clip in [audio_clip, background_clip, title_clip, subtitles_clip, final_clip_for_render]:
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