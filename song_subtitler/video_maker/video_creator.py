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
import shutil

class VideoCreator:
    def __init__(self, resolved_config):
        self.cfg = resolved_config

        # Extract config sections
        self.paths = self.cfg['paths']
        self.video_settings = self.cfg['video_settings']
        self.bg_settings = self.cfg['background']
        self.title_style = self.cfg['title_style']
        self.subtitle_style = self.cfg['subtitle_style']
        # Artist style is optional, used for the *appearance* of the second line
        self.second_line_style = self.cfg.get('artist_style') # Renamed for clarity

        # Validate subtitle styles
        if 'source' not in self.subtitle_style or 'target' not in self.subtitle_style:
             raise ValueError("Configuration error: 'subtitle_style' must contain both 'source' and 'target' sections.")
        self.source_sub_style = self.subtitle_style['source']
        self.target_sub_style = self.subtitle_style['target']

        # Resolve font paths
        self.title_font_path = os.path.join(self.paths['fonts_dir'], self.title_style['font_name'])
        self.source_subtitle_font_path = os.path.join(self.paths['fonts_dir'], self.source_sub_style['font_name'])
        self.target_subtitle_font_path = os.path.join(self.paths['fonts_dir'], self.target_sub_style['font_name'])

        self.second_line_font_path = None
        if self.second_line_style and 'font_name' in self.second_line_style:
            self.second_line_font_path = os.path.join(self.paths['fonts_dir'], self.second_line_style['font_name'])

        # Resolve background paths
        self.background_image_path = self.bg_settings['background_image_path']
        # Intro background is optional
        self.intro_background_image_path = self.bg_settings.get('intro_background_image_path')

        # Output directories
        self.output_frames_dir = self.paths['output_frames_dir'] # For temporary frames
        self.output_video_dir = self.paths['output_dir'] # For final video

        # Validate essential files exist
        self._validate_paths()
        # Ensure output video directory exists
        self._ensure_dirs_exist()

        # State for frame saving
        self.combined_subs_list_for_frames = []
        self.saved_subtitle_ids = set() # Track saved frames to avoid duplicates

    def _validate_paths(self):
        """Checks if essential font and image files exist."""
        if not os.path.exists(self.title_font_path):
            raise FileNotFoundError(f"Error: Title font file not found at '{self.title_font_path}'")
        if not os.path.exists(self.source_subtitle_font_path):
            raise FileNotFoundError(f"Error: Source subtitle font file not found at '{self.source_subtitle_font_path}'")
        if not os.path.exists(self.target_subtitle_font_path):
            raise FileNotFoundError(f"Error: Target subtitle font file not found at '{self.target_subtitle_font_path}'")
        if not os.path.exists(self.background_image_path):
            raise FileNotFoundError(f"Error: Background image not found at '{self.background_image_path}'")
        # Optional files check
        if self.intro_background_image_path and not os.path.exists(self.intro_background_image_path):
             # Warning instead of error? Let's make it an error for consistency.
             raise FileNotFoundError(f"Error: Intro background image specified but not found at '{self.intro_background_image_path}'")
        # Check second line font only if style is defined
        if self.second_line_style and self.second_line_font_path and not os.path.exists(self.second_line_font_path):
             raise FileNotFoundError(f"Error: Font file for second line (artist/hebrew name) specified in config but not found at '{self.second_line_font_path}'")

    def _ensure_dirs_exist(self):
        """Ensures the final output video directory exists."""
        os.makedirs(self.output_video_dir, exist_ok=True)
        # Note: output_frames_dir is created on demand during frame saving

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
            raise # Re-raise to be caught by main handler

    def _create_background_clip(self, duration, image_path=None):
        """Creates a background video clip from an image, resized and cropped."""
        path_to_use = image_path or self.background_image_path
        print(f"Loading background image from: {path_to_use}...")
        try:
            bg_clip = mp.ImageClip(path_to_use, duration=duration)
            target_w, target_h = self.video_settings['resolution']

            # Resize maintaining aspect ratio (height first)
            bg_clip = bg_clip.resize(height=target_h)
            # Crop width if necessary
            if bg_clip.w < target_w:
                 print(f"Warning: Background image width ({bg_clip.w}px) is less than target width ({target_w}px) after height resize. Will have black bars.")
                 # Center the smaller image on a black canvas of target size
                 bg_clip = bg_clip.set_position('center')
                 # Create a black background clip and composite
                 black_bg = mp.ColorClip(size=(target_w, target_h), color=(0,0,0), duration=duration)
                 bg_clip = mp.CompositeVideoClip([black_bg, bg_clip], size=(target_w, target_h))

            elif bg_clip.w > target_w:
                bg_clip = bg_clip.crop(x_center=bg_clip.w / 2, width=target_w)

            # Final resize just in case (shouldn't be needed if logic above is correct)
            bg_clip = bg_clip.resize((target_w, target_h))

            bg_clip = bg_clip.set_fps(self.video_settings['fps'])
            return bg_clip
        except Exception as e:
            print(f"Error loading or processing background image '{path_to_use}': {e}")
            raise # Re-raise

    def _get_first_subtitle_time(self, subs_data_source, subs_data_target, audio_duration):
        """Determines the start time of the very first subtitle."""
        first_start_time = float('inf') # Initialize to infinity
        try:
            times = []
            # Collect start times from both source and target lists
            for subs_list in [subs_data_source, subs_data_target]:
                if isinstance(subs_list, list):
                    for sub in subs_list:
                        start = float(sub.get('start_time', float('inf')))
                        # Only consider valid, non-negative start times
                        if 0 <= start < float('inf'):
                            times.append(start)

            if times:
                first_start_time = min(times)

        except (ValueError, TypeError, KeyError) as e:
             # Log warning but try to continue, default will be 0 or audio_duration
             print(f"Warning: Could not reliably determine first subtitle start time from JSON data. Error: {e}")
             first_start_time = float('inf') # Reset on error

        # Clamp the time between 0 and audio duration
        first_start_time = max(0, min(first_start_time, audio_duration))
        # If still infinity (no valid times found), default to 0
        if first_start_time == float('inf'):
             first_start_time = 0

        return first_start_time

    def _create_title_clip(self, song_title_text, second_line_text, title_duration):
        """Creates the title clip (main title + second line) using PIL."""
        if title_duration <= 0:
            print("Title duration is zero or negative, skipping title clip creation.")
            return None
        original_title_text = (song_title_text or "").strip()
        original_second_line_text = (second_line_text or "").strip() # Use the passed text

        if not original_title_text:
             print("Title text is empty after stripping, skipping title clip creation.")
             return None

        print(f"Creating title clip (Title: '{original_title_text}', Second Line: '{original_second_line_text or 'None'}') using PIL for duration: {title_duration:.2f}s")
        try:
            # --- Setup ---
            title_font_size = self.title_style['font_size']
            video_w, video_h = self.video_settings['resolution']
            horizontal_margin = 100 # Margin from video edges for text
            max_text_width = video_w - (2 * horizontal_margin)
            if max_text_width <= 0: # Sanity check
                max_text_width = video_w * 0.8
                print(f"Warning: Calculated max title width is too small. Using {max_text_width}px.")

            # --- Load Fonts ---
            try:
                title_font = ImageFont.truetype(self.title_font_path, title_font_size)
            except IOError:
                print(f"CRITICAL Error: Could not load title font file '{self.title_font_path}' with PIL.")
                raise

            second_line_font = None
            render_second_line = False
            # Check if there's text *and* style config *and* a valid font path for the second line
            if original_second_line_text and self.second_line_style and self.second_line_font_path:
                try:
                    second_line_font_size = self.second_line_style['font_size']
                    second_line_font = ImageFont.truetype(self.second_line_font_path, second_line_font_size)
                    render_second_line = True
                    print(f"Second line font loaded: {self.second_line_style['font_name']} ({second_line_font_size}pt)")
                except IOError:
                    print(f"Warning: Could not load font file '{self.second_line_font_path}' for the second line. Second line will not be rendered.")
                except KeyError as e:
                     print(f"Warning: Missing key {e} in 'artist_style' (used for second line) config. Second line might not render correctly.")
                     render_second_line = False
            elif original_second_line_text:
                print("Warning: Text provided for second line, but style config ('artist_style') or font is missing/invalid. Second line will not be rendered.")

            # --- Prepare Drawing Canvas ---
            img = Image.new('RGBA', (video_w, video_h), (0, 0, 0, 0)) # Transparent background
            draw = ImageDraw.Draw(img)

            # --- Wrap and Measure Title Text ---
            wrapped_title_lines = self._wrap_text(draw, original_title_text, title_font, max_text_width)
            if not wrapped_title_lines:
                print("Warning: Title text resulted in no lines after wrapping.")
                return None # Cannot proceed without title

            # (Optional) Adjust title lines if second line is short compared to first
            if len(wrapped_title_lines) == 2:
                line1_text = wrapped_title_lines[0]
                line2_text = wrapped_title_lines[1]
                line1_words = line1_text.split()
                should_adjust = False
                try: # Use textbbox if available (more accurate)
                    bbox1 = draw.textbbox((0, 0), line1_text, font=title_font)
                    width1 = bbox1[2] - bbox1[0] if bbox1 else 0
                    bbox2 = draw.textbbox((0, 0), line2_text, font=title_font)
                    width2 = bbox2[2] - bbox2[0] if bbox2 else 0
                    # Adjust if line 2 is significantly shorter and line 1 has multiple words
                    if width1 > 0 and width2 > 0 and (width2 / width1 < 0.4) and len(line1_words) > 1:
                         should_adjust = True
                except AttributeError: # Fallback to word count heuristic
                    line2_words = line2_text.split()
                    if len(line2_words) == 1 and len(line1_words) > 1: # If line 2 is one word, line 1 is multiple
                        should_adjust = True

                if should_adjust:
                    print(f"Adjusting title lines (heuristic based on length/words)...")
                    last_word_line1 = line1_words.pop()
                    new_line1_text = " ".join(line1_words)
                    # Only adjust if line 1 remains non-empty
                    if new_line1_text.strip():
                        new_line2_text = f"{last_word_line1} {line2_text}"
                        wrapped_title_lines = [new_line1_text, new_line2_text]
                        print(f"Adjusted title lines (logical):\n1: {new_line1_text}\n2: {new_line2_text}")
                    else:
                         print("Title line adjustment aborted: Line 1 would become empty.")

            # Calculate dimensions for title block
            title_line_height = 0
            max_title_line_width = 0
            title_line_details = [] # Store details for drawing
            for line in wrapped_title_lines:
                try:
                    line_bbox = draw.textbbox((0, 0), line, font=title_font)
                    current_line_width = line_bbox[2] - line_bbox[0]
                    current_line_height = line_bbox[3] - line_bbox[1]
                    title_line_details.append({'text': line, 'width': current_line_width, 'height': current_line_height, 'bbox': line_bbox})
                    if title_line_height == 0 and current_line_height > 0: # Get height from first valid line
                         title_line_height = current_line_height
                    max_title_line_width = max(max_title_line_width, current_line_width)
                except AttributeError: # Fallback measurement
                     current_line_width = draw.textlength(line, font=title_font) if hasattr(draw, 'textlength') else len(line) * title_font_size * 0.6
                     current_line_height = title_font_size * 1.2 # Estimate height
                     title_line_details.append({'text': line, 'width': current_line_width, 'height': current_line_height, 'bbox': None})
                     if title_line_height == 0: title_line_height = current_line_height
                     max_title_line_width = max(max_title_line_width, current_line_width)

            if title_line_height == 0: title_line_height = title_font_size * 1.2 # Final fallback height
            total_title_block_height = len(wrapped_title_lines) * title_line_height

            # --- Measure Second Line Text (if rendering) ---
            second_line_height = 0
            total_second_line_block_height = 0
            second_line_details = []
            vertical_offset_between_lines = 0
            if render_second_line:
                # Get offset from style (default if not specified)
                vertical_offset_between_lines = self.second_line_style.get('vertical_offset_from_title', 10)

                # For simplicity, assume second line is not wrapped (usually shorter)
                second_line = original_second_line_text
                if second_line: # Should always be true if render_second_line is true
                    try:
                        bbox = draw.textbbox((0,0), second_line, font=second_line_font)
                        sl_width = bbox[2] - bbox[0]
                        sl_height = bbox[3] - bbox[1]
                        second_line_details.append({'text': second_line, 'width': sl_width, 'height': sl_height, 'bbox': bbox})
                        second_line_height = sl_height if sl_height > 0 else second_line_font.size * 1.2
                    except AttributeError: # Fallback
                         sl_width = draw.textlength(second_line, font=second_line_font) if hasattr(draw, 'textlength') else len(second_line) * second_line_font.size * 0.6
                         second_line_height = second_line_font.size * 1.2
                         second_line_details.append({'text': second_line, 'width': sl_width, 'height': second_line_height, 'bbox': None})

                    total_second_line_block_height = second_line_height

            # --- Calculate Vertical Positioning ---
            total_combined_height = total_title_block_height + (vertical_offset_between_lines if render_second_line else 0) + total_second_line_block_height
            start_y = (video_h - total_combined_height) / 2

            # --- Draw Title Lines ---
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
                current_y += title_line_height # Move down by consistent line height

            # --- Draw Second Line (if rendering) ---
            if render_second_line and second_line_details:
                current_y += vertical_offset_between_lines # Add spacing
                detail = second_line_details[0]
                text = detail['text']
                width = detail['width']
                x_pos = (video_w - width) / 2

                self._draw_text_with_stroke(
                    draw=draw, pos=(x_pos, current_y), text=text, font=second_line_font,
                    fill_color=self.second_line_style['color'], # Use colors from 'artist_style'
                    stroke_color=self.second_line_style.get('stroke_color'),
                    stroke_width=self.second_line_style.get('stroke_width', 0)
                )

            # --- Create MoviePy Clip ---
            frame_array = np.array(img)
            title_clip = mp.ImageClip(frame_array, ismask=False, transparent=True)
            # Set duration and start time (always 0 for title)
            title_clip = title_clip.set_duration(title_duration).set_start(0)

            print("Title clip (with optional second line) created using PIL.")
            return title_clip

        except Exception as e:
            print(f"Error creating title clip using PIL: {e}")
            traceback.print_exc()
            return None # Return None on error

    def _draw_text_with_stroke(self, draw, pos, text, font, fill_color, stroke_color, stroke_width):
        """Draws text with an optional outline using PIL."""
        x, y = pos
        processed_text = text
        # Apply BiDi reshaping for Hebrew text before drawing
        if self._is_hebrew(text):
            try:
                reshaped = arabic_reshaper.reshape(text)
                processed_text = get_display(reshaped)
            except Exception as e:
                # Log error but proceed with original text if BiDi fails
                print(f"Warning: BiDi processing failed during drawing for text '{text[:20]}...': {e}")
                # processed_text remains the original text

        # Draw stroke/outline if width > 0 and color is defined
        if stroke_width > 0 and stroke_color:
            # Simple cardinal direction offsets for stroke
            offset = stroke_width
            draw.text((x - offset, y), processed_text, font=font, fill=stroke_color)
            draw.text((x + offset, y), processed_text, font=font, fill=stroke_color)
            draw.text((x, y - offset), processed_text, font=font, fill=stroke_color)
            draw.text((x, y + offset), processed_text, font=font, fill=stroke_color)
            # Diagonal offsets can be added for a thicker stroke
            # draw.text((x-offset, y-offset), processed_text, font=font, fill=stroke_color)
            # draw.text((x+offset, y-offset), processed_text, font=font, fill=stroke_color)
            # draw.text((x-offset, y+offset), processed_text, font=font, fill=stroke_color)
            # draw.text((x+offset, y+offset), processed_text, font=font, fill=stroke_color)


        # Draw the main text fill on top
        draw.text((x, y), processed_text, font=font, fill=fill_color)

    def _is_hebrew(self, text_line):
        """Checks if a string contains Hebrew characters."""
        if not text_line: return False
        # Check for characters in the Hebrew Unicode block
        return any('\u0590' <= char <= '\u05FF' for char in text_line)

    def _wrap_text(self, draw, line_text, font, max_width):
            """Wraps a single line of text based on max_width using PIL draw context."""
            words = line_text.split(' ')
            wrapped_lines = []
            current_line = ''
            for word in words:
                if not word: continue # Skip empty strings from multiple spaces
                test_line = f"{current_line} {word}".strip()
                try:
                    # Use textbbox for potentially more accurate width
                    bbox = draw.textbbox((0, 0), test_line, font=font)
                    line_width = bbox[2] - bbox[0]
                except AttributeError:
                    # Fallback for older PIL/Pillow or if textbbox fails
                    try:
                        line_width = draw.textlength(test_line, font=font)
                    except AttributeError: # Final fallback (rough estimate)
                        line_width = len(test_line) * font.size * 0.6

                if line_width <= max_width:
                    # Word fits on the current line
                    current_line = test_line
                else:
                    # Word doesn't fit, finalize the previous line (if any)
                    if current_line:
                        wrapped_lines.append(current_line)
                    # Start a new line with the current word
                    current_line = word
                    # Check if the single word itself exceeds the max width
                    try:
                        bbox_word = draw.textbbox((0, 0), current_line, font=font)
                        word_width = bbox_word[2] - bbox_word[0]
                    except AttributeError:
                         try:
                              word_width = draw.textlength(current_line, font=font)
                         except AttributeError:
                              word_width = len(current_line) * font.size * 0.6

                    if word_width > max_width:
                         # The word itself is too long. Add it as its own line anyway.
                         # Avoid adding the same long word multiple times if split fails poorly
                         if not wrapped_lines or wrapped_lines[-1] != current_line:
                             wrapped_lines.append(current_line)
                             # Reset current line as this word took the whole line
                             current_line = ""

            # Add the last remaining line
            if current_line:
                wrapped_lines.append(current_line)

            # Return the list of wrapped lines, or the original if no wrapping occurred/needed
            # Ensure return is always a list, even if empty or single line
            return wrapped_lines if wrapped_lines else ([line_text.strip()] if line_text.strip() else [])

    def _create_styled_subtitle_clip_pil(self, subs_data_source, subs_data_target, total_duration):
        """Generates subtitle images using PIL, handling BiDi and styling."""
        print("Processing combined subtitles (Source/Target) using PIL with BiDi...")
        subs_source = subs_data_source if isinstance(subs_data_source, list) else []
        subs_target = subs_data_target if isinstance(subs_data_target, list) else []
        combined_subs_format = [] # For MoviePy's SubtitlesClip: [ ((start, end), "text"), ... ]
        self.combined_subs_list_for_frames = [] # For frame saving: [ ((start, end), "text", "id"), ... ]
        subtitle_id_counter = 0 # To generate unique IDs for combined subs

        if not subs_source and not subs_target:
            print("Warning: No subtitle data provided (source or target). Returning empty clip.")
            # Create a fully transparent clip for the entire duration
            empty_clip = mp.ColorClip(size=self.video_settings['resolution'], color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0)
            return empty_clip, [] # Return empty clip and empty list for frame saving

        # --- Merge source and target subtitles based on ID ---
        # Use dictionaries for efficient lookup by ID
        subs_source_map = {str(sub.get('id', f'src_{i}')): sub for i, sub in enumerate(subs_source)}
        subs_target_map = {str(sub.get('id', f'tgt_{i}')): sub for i, sub in enumerate(subs_target)}

        # Get all unique IDs from both sources, sorted numerically if possible
        def sort_key(id_str):
             # Extract number from ID for sorting (e.g., "src_10" -> 10)
             match = re.search(r'\d+', str(id_str))
             return int(match.group()) if match else float('inf') # Put non-numeric IDs last

        all_ids = sorted(list(set(subs_source_map.keys()) | set(subs_target_map.keys())), key=sort_key)
        print(f"DEBUG: Starting merge. Found {len(subs_source_map)} Source keys, {len(subs_target_map)} Target keys. Total unique IDs: {len(all_ids)}")

        # Iterate through unique IDs and combine data
        for idx_str in all_ids:
            sub_src = subs_source_map.get(idx_str)
            sub_tgt = subs_target_map.get(idx_str)
            src_start, src_end, src_text = (0, 0, "") # Defaults
            tgt_start, tgt_end, tgt_text = (0, 0, "") # Defaults
            valid_src, valid_tgt = False, False

            # Safely extract and validate source data
            try:
                if sub_src and 'start_time' in sub_src and 'end_time' in sub_src and 'text' in sub_src:
                    src_start = max(0, float(sub_src['start_time']))
                    src_end = max(src_start, float(sub_src['end_time']))
                    src_text_raw = sub_src.get('text', '')
                    # Clean text: strip whitespace, handle potential escaped newlines
                    src_text = str(src_text_raw).strip().replace('\\n', '\n')
                    if src_end > src_start: valid_src = True # Mark as valid only if duration > 0
            except (ValueError, TypeError) as e: print(f"Warning: Invalid data in Source sub ID {idx_str}: {e}")

            # Safely extract and validate target data
            try:
                if sub_tgt and 'start_time' in sub_tgt and 'end_time' in sub_tgt and 'text' in sub_tgt:
                    tgt_start = max(0, float(sub_tgt['start_time']))
                    tgt_end = max(tgt_start, float(sub_tgt['end_time']))
                    tgt_text_raw = sub_tgt.get('text', '')
                    tgt_text = str(tgt_text_raw).strip().replace('\\n', '\n')
                    if tgt_end > tgt_start: valid_tgt = True
            except (ValueError, TypeError) as e: print(f"Warning: Invalid data in Target sub ID {idx_str}: {e}")

            # --- Combine Text and Determine Time Interval ---
            combined_text_parts = []
            start_time = float('inf') # Use min later
            end_time = 0              # Use max later
            has_src_text = valid_src and src_text and "[INAUDIBLE]" not in src_text # Consider INAUDIBLE as no text
            has_tgt_text = valid_tgt and tgt_text and "[INAUDIBLE]" not in tgt_text # Consider INAUDIBLE as no text

            # Add text parts if they exist
            if has_src_text:
                combined_text_parts.append(src_text)
                start_time = min(start_time, src_start)
                end_time = max(end_time, src_end)

            if has_tgt_text:
                combined_text_parts.append(tgt_text)
                # Update time interval based on target times as well
                start_time = min(start_time, tgt_start)
                end_time = max(end_time, tgt_end)

            # If no text but one side was valid (e.g., only INAUDIBLE), use its times
            if not has_src_text and not has_tgt_text:
                 if valid_src:
                     start_time = min(start_time, src_start)
                     end_time = max(end_time, src_end)
                 if valid_tgt:
                     start_time = min(start_time, tgt_start)
                     end_time = max(end_time, tgt_end)

            # Only add if we have text OR a valid time interval was determined
            if combined_text_parts or (start_time != float('inf') and end_time > 0):
                # Use a unique separator for the generator function to split later
                # IMPORTANT: This separator MUST NOT naturally occur in the subtitle text.
                separator = "\n<--SEP-->\n" if has_src_text and has_tgt_text else ""
                combined_text = separator.join(combined_text_parts)

                # Generate a unique ID for this combined subtitle entry
                sub_id = f"combined_{idx_str}_{subtitle_id_counter}"
                subtitle_id_counter += 1

                # Finalize time interval, ensuring min duration and clamping to total duration
                min_duration = 1.0 / self.video_settings['fps'] # Minimum display time for one frame
                start_time = 0 if start_time == float('inf') else start_time # Default start to 0 if unset
                if end_time <= start_time: end_time = start_time + min_duration # Ensure positive duration
                # Clamp times to the video's total duration
                start_time = min(start_time, total_duration)
                end_time = min(end_time, total_duration)

                # Add to lists if duration is valid
                if end_time > start_time:
                    time_interval = (start_time, end_time)
                    combined_subs_format.append((time_interval, combined_text)) # For MoviePy
                    self.combined_subs_list_for_frames.append((time_interval, combined_text, sub_id)) # For frame saving

        # --- Check if any subtitles were actually created ---
        if not combined_subs_format:
            print("Warning: No valid combined subtitles were created after merging.")
            empty_clip = mp.ColorClip(size=self.video_settings['resolution'], color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0)
            return empty_clip, []

        # Sort combined subtitles by start time (essential for SubtitlesClip)
        # combined_subs_format.sort(key=lambda item: item[0][0]) # Already sorted by ID processing? Double check. Let's sort just in case.
        self.combined_subs_list_for_frames.sort(key=lambda item: item[0][0])
        print(f"DEBUG: Finished merge. Combined {len(combined_subs_format)} subtitle entries for MoviePy.")

        # --- Define the Subtitle Generator Function (txt -> ImageClip) ---
        def generator(txt):
            """Generates a transparent ImageClip with styled text using PIL."""
            try:
                # Load fonts within the generator (MoviePy might call this in parallel)
                font_source = ImageFont.truetype(self.source_subtitle_font_path, self.source_sub_style['font_size'])
                font_target = ImageFont.truetype(self.target_subtitle_font_path, self.target_sub_style['font_size'])
            except Exception as e:
                # Critical error if fonts can't be loaded
                print(f"CRITICAL Error loading PIL subtitle fonts ('{self.source_subtitle_font_path}', '{self.target_subtitle_font_path}') within generator: {e}")
                # Return a minimal transparent clip on error
                return mp.ImageClip(np.zeros((10, 10, 4), dtype=np.uint8), ismask=False, transparent=True).set_duration(0.1) # Short duration

            video_w, video_h = self.video_settings['resolution']
            max_text_width = video_w * 0.85 # Max width for subtitle text wrapping

            # Handle empty text input (MoviePy might send empty strings between subs)
            if not txt or not txt.strip():
                # Return a fully transparent frame matching video size
                empty_frame = np.zeros((video_h, video_w, 4), dtype=np.uint8) # RGBA
                # Duration doesn't strictly matter here, MoviePy handles timing
                return mp.ImageClip(empty_frame, ismask=False, transparent=True).set_duration(1.0 / self.video_settings['fps'])

            # --- Render Text ---
            img = Image.new('RGBA', (video_w, video_h), (0, 0, 0, 0)) # Transparent canvas
            draw = ImageDraw.Draw(img)

            # Split the combined text back into source/target blocks if separator exists
            role_blocks = txt.split("\n<--SEP-->\n")
            processed_lines_details = [] # Store details for each drawable line
            total_text_height = 0        # Accumulate height for vertical positioning
            line_counter = 0             # Track overall line number

            # Get layout settings from config
            layout_cfg = self.subtitle_style['layout']
            spacing_within = layout_cfg.get('spacing_within_block', 10) # Spacing between lines of the same block (e.g., wrapped lines)
            spacing_between = layout_cfg.get('spacing_between_blocks', 35) # Spacing between source and target blocks

            # Process each block (source first, then target if present)
            for block_index, block in enumerate(role_blocks):
                original_lines_in_block = [line for line in block.splitlines() if line.strip()]
                if not original_lines_in_block: continue # Skip empty blocks

                # Determine style and font based on block index (0=source, 1=target)
                # Assumes source text always comes first if both exist
                is_source_block = (block_index == 0)
                block_style = self.source_sub_style if is_source_block else self.target_sub_style
                font_for_block = font_source if is_source_block else font_target

                # Get styling for this block
                sub_color = block_style['color']
                sub_stroke_color = block_style.get('stroke_color')
                sub_stroke_width = block_style.get('stroke_width', 0)

                # Process each original line within the block (before wrapping)
                for i, line in enumerate(original_lines_in_block):
                    # Wrap the line if it exceeds max width
                    wrapped_lines = self._wrap_text(draw, line, font_for_block, max_text_width)

                    # Process each wrapped line segment
                    for k, wrapped_line in enumerate(wrapped_lines):
                        # Measure the wrapped line segment
                        try:
                            bbox = draw.textbbox((0, 0), wrapped_line, font=font_for_block)
                            line_width = bbox[2] - bbox[0]
                            line_height = bbox[3] - bbox[1]
                        except AttributeError: # Fallback measurement
                            line_width = draw.textlength(wrapped_line, font=font_for_block) if hasattr(draw, 'textlength') else 100 # Estimate
                            line_height = font_for_block.size * 1.2 # Estimate

                        # Determine spacing after *this specific rendered line*
                        is_last_wrapped_in_line = (k == len(wrapped_lines) - 1)
                        is_last_line_in_block = (i == len(original_lines_in_block) - 1)
                        is_last_block = (block_index == len(role_blocks) - 1)
                        is_transitioning_block = is_last_line_in_block and is_last_wrapped_in_line and not is_last_block

                        spacing_after_this_line = 0
                        if is_transitioning_block:
                             # Space between source and target blocks
                             spacing_after_this_line = spacing_between
                        elif not is_last_wrapped_in_line or not is_last_line_in_block:
                            # Space within the same block (between original lines or wrapped segments)
                            spacing_after_this_line = spacing_within
                        # Else: No spacing after the very last line of the last block

                        # Store details needed for drawing
                        line_detail = {
                            'text': wrapped_line,
                            'font': font_for_block,
                            'is_source': is_source_block, # Keep track for potential future use
                            'width': line_width,
                            'height': line_height,
                            'spacing_after': spacing_after_this_line,
                            'line_index': line_counter,
                            'color': sub_color,
                            'stroke_color': sub_stroke_color,
                            'stroke_width': sub_stroke_width
                        }
                        processed_lines_details.append(line_detail)
                        # Accumulate total height including spacing
                        total_text_height += line_height + spacing_after_this_line
                        line_counter += 1

            # Adjust total height if the last line incorrectly added spacing
            if processed_lines_details:
                 # The last line shouldn't have spacing *after* it contributing to total height
                 if processed_lines_details[-1]['spacing_after'] > 0:
                    total_text_height -= processed_lines_details[-1]['spacing_after']

            # --- Calculate Vertical Position for the entire text block ---
            vertical_alignment = layout_cfg.get('vertical_alignment', 'center').lower()
            if vertical_alignment == 'bottom':
                 bottom_margin = layout_cfg.get('bottom_margin', 50)
                 current_y = video_h - total_text_height - bottom_margin
            elif vertical_alignment == 'top':
                 top_margin = layout_cfg.get('top_margin', 50)
                 current_y = top_margin
            else: # Default to center alignment
                 current_y = (video_h - total_text_height) / 2

            # --- Draw all processed lines ---
            for detail in processed_lines_details:
                # Center each line horizontally
                x_pos = (video_w - detail['width']) / 2
                text_to_draw = detail['text'] # Already wrapped and BiDi handled by _draw_text_with_stroke

                # Draw the text using the helper function
                self._draw_text_with_stroke(
                    draw, (x_pos, current_y), text_to_draw, detail['font'],
                    detail['color'], detail['stroke_color'], detail['stroke_width']
                )
                # Move y position down for the next line
                current_y += detail['height'] + detail['spacing_after']

            # --- Convert PIL Image to MoviePy Clip ---
            frame_array = np.array(img) # Convert RGBA image to numpy array
            # Create ImageClip, ensuring it's treated as transparent
            return mp.ImageClip(frame_array, ismask=False, transparent=True).set_duration(1.0 / self.video_settings['fps']) # Duration doesn't matter much here


        # --- Create the main SubtitlesClip using the generator ---
        # Prepare data in the format MoviePy expects: [ ((start, end), text), ... ]
        subs_for_moviepy = [(item[0], item[1]) for item in self.combined_subs_list_for_frames]

        if not subs_for_moviepy:
             # This check might be redundant due to earlier checks, but safe to keep
             print("Warning: No subtitle data to feed into MoviePy SubtitlesClip after processing.")
             empty_clip = mp.ColorClip(size=self.video_settings['resolution'], color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0)
             return empty_clip, self.combined_subs_list_for_frames # Return empty list too

        try:
            subtitle_moviepy_clip = SubtitlesClip(subs_for_moviepy, generator)
            # Set duration explicitly to match audio duration (important!)
            subtitle_moviepy_clip = subtitle_moviepy_clip.set_duration(total_duration)
            # Set position (usually center, but could be configurable)
            subtitle_moviepy_clip = subtitle_moviepy_clip.set_position(('center', 'center'))
            print(f"SubtitlesClip created successfully. Duration: {subtitle_moviepy_clip.duration:.2f}s")
            return subtitle_moviepy_clip, self.combined_subs_list_for_frames
        except Exception as e:
            # Catch errors during SubtitlesClip creation (e.g., generator issues)
            print(f"CRITICAL Error creating MoviePy SubtitlesClip: {e}")
            traceback.print_exc()
            # Return an empty clip on failure
            empty_clip = mp.ColorClip(size=self.video_settings['resolution'], color=(0,0,0,0), ismask=True, duration=total_duration).set_opacity(0)
            return empty_clip, [] # Return empty list for frame saving as well

    def _sanitize_filename(self, text, max_len=50):
        """Cleans text to be suitable for use in filenames."""
        if not text: return "subtitle" # Default for empty text
        # Replace common problematic characters and sequences
        text = text.replace('\n', ' ').replace('\r', '') # Newlines to spaces
        # Remove characters invalid in filenames on most OS
        text = re.sub(r'[\\/*?:"<>|.!@#$%^&+=~`{}\[\];\'’,]', "", text)
        text = re.sub(r'\<--SEP--\>', '_', text) # Replace our specific separator
        text = text.strip() # Remove leading/trailing whitespace
        text = re.sub(r'\s+', '_', text) # Multiple whitespace to single underscore
        if not text: return "subtitle" # Check again after cleaning

        # Truncate if too long
        if len(text) > max_len:
            # Try to cut at the last underscore before max_len for readability
            cut_point = text.rfind('_', 0, max_len)
            # Only cut if underscore is reasonably far in (not right at the beginning)
            if cut_point != -1 and cut_point > max_len // 3 :
                 text = text[:cut_point] + "_etc"
            else: # Otherwise, just cut at max_len
                 text = text[:max_len] + "_etc"
        return text

    def _save_subtitle_frame_processor(self, get_frame, t):
        """MoviePy processor function to save frames when subtitles appear."""
        # Get the current video frame at time t
        try:
            frame = get_frame(t)
            # Handle potential None frame (though unlikely with valid input)
            if frame is None:
                 print(f"Warning: get_frame({t:.3f}) returned None. Returning black frame.")
                 # Return a black frame of the correct size
                 return np.zeros((self.video_settings['resolution'][1], self.video_settings['resolution'][0], 3), dtype=np.uint8)
        except Exception as e:
            # Catch errors during frame retrieval
            print(f"Error getting frame at t={t:.3f}s: {e}. Returning black frame.")
            return np.zeros((self.video_settings['resolution'][1], self.video_settings['resolution'][0], 3), dtype=np.uint8)

        # Find the active subtitle at time t
        active_sub_info = None
        # Use a small epsilon to handle floating point comparisons near frame boundaries
        epsilon = 1 / (self.video_settings['fps'] * 2) # Half frame duration

        # Iterate through the *sorted* list prepared for frame saving
        for interval, text, sub_id in self.combined_subs_list_for_frames:
            start_time, end_time = interval
            # Check if t falls within the subtitle's interval (using epsilon)
            # Use >= start and < end for standard interval check
            if (start_time - epsilon) <= t < (end_time - epsilon):
                # Only consider it active if there's actual text content
                if text and text.strip():
                     active_sub_info = (text, sub_id, start_time)
                break # Found the first matching subtitle, stop searching

        # If an active subtitle with text is found and not already saved...
        if active_sub_info:
            text, sub_id, start_time = active_sub_info
            if sub_id not in self.saved_subtitle_ids:
                try:
                    # Ensure the output directory exists (create if first time)
                    if not os.path.exists(self.output_frames_dir):
                         os.makedirs(self.output_frames_dir, exist_ok=True)
                         print(f"Created subtitle frames directory: {self.output_frames_dir}")

                    # Create a filename based on time and sanitized text
                    time_sec = int(start_time)
                    time_ms = int((start_time - time_sec) * 1000)
                    time_str = f"{time_sec:04d}_{time_ms:03d}" # Format: SSSS_mmm
                    safe_text = self._sanitize_filename(text)
                    filename_base = f"frame_{time_str}_{safe_text}"
                    # Limit total filename length to avoid OS issues
                    max_fname_len = 150
                    filename = os.path.join(self.output_frames_dir, f"{filename_base[:max_fname_len]}.png")

                    # Convert frame to RGB if it's RGBA (e.g., from transparent overlays)
                    # imageio typically prefers RGB for PNG saving, though it might handle RGBA.
                    if frame.shape[2] == 4: # Check if alpha channel exists
                        frame_rgb = frame[..., :3] # Slice to get R, G, B channels
                    else:
                         frame_rgb = frame # Assume it's already RGB or similar 3-channel

                    # Save the frame using imageio
                    imageio.imwrite(filename, frame_rgb)
                    # Mark this subtitle ID as saved to prevent duplicates
                    self.saved_subtitle_ids.add(sub_id)
                    # print(f"Saved frame for sub ID {sub_id} at t={t:.3f}s to {filename}") # Optional: Verbose logging

                except Exception as e:
                    # Log error during saving but continue processing other frames
                    print(f"Error saving frame at t={t:.3f}s (sub_id: {sub_id}): {e}")
                    # Mark as saved even on error to avoid retrying constantly
                    self.saved_subtitle_ids.add(sub_id)

        # IMPORTANT: Always return the original frame for MoviePy to continue rendering
        return frame

    # --- Main Video Creation Method ---
    def create_video(self, mp3_path, song_title_text, artist_name_text, hebrew_song_name_text, intro_subtitle_mode, source_subtitle_data, target_subtitle_data, output_video_filename_base):
        """Orchestrates the creation of the final subtitled video."""
        print(f"\n--- Starting Video Creation for: {output_video_filename_base} ---")
        # Define output video path and temporary audio file path
        output_video_file = os.path.join(self.output_video_dir, f"{output_video_filename_base}_subtitled.mp4")
        # Use a unique temp filename to avoid conflicts if run in parallel (though unlikely)
        temp_audio_file = os.path.join(self.output_video_dir, f'temp-audio-{os.path.basename(output_video_filename_base)}-{int(time.time())}.m4a')

        # Initialize clip variables to None for proper cleanup
        audio_clip = None
        background_clip = None
        intro_background_clip = None
        title_clip = None
        subtitles_clip = None
        final_clip_for_render = None
        video_created_successfully = False # Flag for final cleanup logic

        try:
            # 1. Load Audio
            audio_clip, audio_duration = self._load_audio(mp3_path)

            # 2. Create Main Background
            background_clip = self._create_background_clip(audio_duration) # Use default background

            # 3. Determine Title Duration (time until first subtitle starts)
            first_sub_time = self._get_first_subtitle_time(source_subtitle_data, target_subtitle_data, audio_duration)
            # Set a minimum threshold for showing the title (e.g., half a second)
            min_title_threshold = 0.5
            title_duration = first_sub_time if first_sub_time >= min_title_threshold else 0
            print(f"Title duration calculated: {title_duration:.2f}s (based on first subtitle at {first_sub_time:.2f}s)")

            # 4. Create Optional Intro Background (if title duration > 0 and intro image is set)
            if title_duration > 0 and self.intro_background_image_path:
                print("Creating intro background clip...")
                try:
                    # Create background using the specific intro image path
                    intro_background_clip = self._create_background_clip(title_duration, image_path=self.intro_background_image_path)
                    # Set start time and duration explicitly
                    intro_background_clip = intro_background_clip.set_start(0).set_duration(title_duration)
                    print("Intro background clip created.")
                except Exception as e:
                    # Warn if intro background fails, main background will be used
                    print(f"Warning: Could not create intro background clip from '{self.intro_background_image_path}': {e}. Using main background for intro.")
                    intro_background_clip = None # Ensure it's None if creation failed

            # 5. Determine Text for Second Line of Title
            text_for_second_line = None
            if intro_subtitle_mode == 'hebrew':
                if hebrew_song_name_text:
                    text_for_second_line = hebrew_song_name_text
                    print(f"Using Hebrew name for intro subtitle: '{text_for_second_line}'")
                else:
                    print("Warning: Hebrew name requested for intro subtitle, but not found in JSON data. Falling back to artist name if available.")
                    # Fallback to artist name if Hebrew name missing
                    if artist_name_text:
                        text_for_second_line = artist_name_text
                        print(f"Using Artist name as fallback for intro subtitle: '{text_for_second_line}'")
            elif intro_subtitle_mode == 'artist' and artist_name_text:
                text_for_second_line = artist_name_text
                print(f"Using Artist name for intro subtitle: '{text_for_second_line}'")
            else: # Default case or artist name not available
                 if artist_name_text: # If mode is artist but text missing (unlikely) or default case
                     text_for_second_line = artist_name_text # Attempt to use artist if available
                     print(f"Using Artist name (default/available) for intro subtitle: '{text_for_second_line}'")
                 else:
                     print("No text specified or available for intro subtitle (neither Hebrew name nor artist name). Second line will be empty.")

            # 6. Create Title Clip (pass the determined second line text)
            title_clip = self._create_title_clip(song_title_text, text_for_second_line, title_duration)

            # 7. Create Subtitles Clip
            # This returns the MoviePy clip and the list needed for frame saving
            subtitles_clip, self.combined_subs_list_for_frames = self._create_styled_subtitle_clip_pil(
                source_subtitle_data, target_subtitle_data, audio_duration
            )
            # Validate the created subtitle clip
            if not subtitles_clip or subtitles_clip.duration <= 0:
                 print("Warning: Subtitle clip generation failed or resulted in an empty/invalid clip.")
                 subtitles_clip = None # Ensure it's None if invalid
            elif subtitles_clip.duration > audio_duration + 1: # Check for excessive duration
                print(f"Warning: Subtitles clip duration ({subtitles_clip.duration:.2f}s) significantly exceeds audio duration ({audio_duration:.2f}s). Trimming.")
                subtitles_clip = subtitles_clip.set_duration(audio_duration)

            # 8. Composite Layers
            print("Compositing video layers...")
            # Start with the main background (always present)
            clips_to_composite = [background_clip]
            # Add intro background on top if it exists (covers main bg during title)
            if intro_background_clip:
                clips_to_composite.append(intro_background_clip)
                print("Adding intro background layer.")
            # Add title clip if it exists
            if title_clip:
                clips_to_composite.append(title_clip)
                print("Adding title layer.")
            # Add subtitles clip if it exists
            if subtitles_clip:
                clips_to_composite.append(subtitles_clip)
                print("Adding subtitles layer.")
            else:
                 print("Info: No valid subtitle clip to composite.")

            # Create the composite video
            composite_video = mp.CompositeVideoClip(clips_to_composite, size=self.video_settings['resolution'])
            # Explicitly set duration to match audio (important for consistency)
            composite_video = composite_video.set_duration(audio_duration)

            # 9. Attach Frame Saving Processor (if subtitles exist)
            print("Attaching frame saving processor (if applicable)...")
            if self.combined_subs_list_for_frames:
                 # Apply the processor function to the video stream
                 # apply_to=['color'] ensures it processes the visual frames
                 final_video_layers = composite_video.fl(self._save_subtitle_frame_processor, apply_to=['color'])
                 # Ensure duration is still correct after applying filter
                 final_video_layers = final_video_layers.set_duration(audio_duration)
                 print("Frame saving enabled.")
            else:
                # No subtitles to save frames for
                print("No subtitle data for frame saving, skipping processor attachment.")
                final_video_layers = composite_video # Use the composite video directly

            # 10. Add Audio
            print("Adding audio...")
            final_clip_for_render = final_video_layers.set_audio(audio_clip)
            # Final duration check/set
            final_clip_for_render = final_clip_for_render.set_duration(audio_duration)

            # 11. Render Video
            print(f"Writing final video to '{output_video_file}'...")
            if not final_clip_for_render or final_clip_for_render.duration <= 0:
                 # This should not happen if previous steps are correct, but safety check
                 raise ValueError("Final video clip for rendering is invalid or has zero duration.")

            # Reset saved frame IDs before rendering
            self.saved_subtitle_ids = set()
            # Define rendering parameters
            render_params = {
                "fps": self.video_settings['fps'],
                "codec": 'libx264',         # Common, good quality codec
                "audio_codec": 'aac',       # Standard audio codec
                "temp_audiofile": temp_audio_file, # Use specified temp file
                "remove_temp": True,        # Delete temp audio file after render
                # Use a reasonable number of threads (e.g., half CPU cores)
                "threads": max(1, (os.cpu_count() or 2) // 2),
                "preset": 'medium',         # Balance between speed and quality/size
                "logger": 'bar',            # Show progress bar
                # Add other ffmpeg parameters if needed via ffmpeg_params=['-param', 'value']
            }
            # Execute the render process
            final_clip_for_render.write_videofile(output_video_file, **render_params)

            video_created_successfully = True # Set flag on success
            print(f"\nVideo creation successful: '{output_video_file}'")

            # Post-render info about saved frames
            if self.combined_subs_list_for_frames:
                 if self.saved_subtitle_ids:
                    print(f"Subtitle frames were saved in: '{self.output_frames_dir}' (This directory will now be deleted).")
                 else:
                    # This might happen if subtitles had no text (e.g., only [INAUDIBLE])
                    print("No subtitle frames were actually saved (perhaps no text content in subs?). Frame directory will be deleted if it exists.")

            return output_video_file # Return path on success

        except FileNotFoundError as e:
             # Specific handling for missing files (fonts, images)
             print(f"\nError: Required file not found. {e}")
             traceback.print_exc() # Print stack trace for debugging
             return None # Indicate failure
        except ValueError as e:
            # Handling for invalid config values or data issues
            print(f"\nError: Invalid value encountered. {e}")
            traceback.print_exc()
            return None
        except Exception as e:
            # Catch-all for any other unexpected errors during creation
            print(f"\nAn unexpected error occurred during video creation: {e}")
            traceback.print_exc()
            return None

        finally:
            # --- Cleanup ---
            # This block executes whether the try block succeeded or failed
            print("Releasing resources...")
            # Close all MoviePy clips to free memory and file handles
            for clip in [audio_clip, background_clip, intro_background_clip, title_clip, subtitles_clip, final_clip_for_render]:
                 # Check if clip exists and has a close method
                 if clip and hasattr(clip, 'close') and callable(getattr(clip, 'close', None)):
                    try:
                        clip.close()
                    except Exception as e_close:
                        # Log warning if closing fails, but don't stop cleanup
                        print(f"Warning: Error closing a clip object: {e_close}")

            # Remove temporary audio file if it still exists
            if os.path.exists(temp_audio_file):
                try:
                    os.remove(temp_audio_file)
                    print(f"Removed temporary audio file: {temp_audio_file}")
                except Exception as e:
                    print(f"Warning: Could not remove temporary audio file '{temp_audio_file}': {e}")

            # Delete the subtitle frames directory ONLY if video creation was successful
            if video_created_successfully and os.path.exists(self.output_frames_dir):
                try:
                    shutil.rmtree(self.output_frames_dir)
                    print(f"Successfully deleted subtitle frames directory: '{self.output_frames_dir}'")
                except Exception as e:
                    print(f"Warning: Could not delete subtitle frames directory '{self.output_frames_dir}': {e}")
            elif not video_created_successfully and os.path.exists(self.output_frames_dir):
                 # Keep the frames directory if the video failed, might be useful for debugging
                 print(f"Video creation failed. Subtitle frames directory '{self.output_frames_dir}' was NOT deleted.")

            print("--- Video Creation Process Finished ---")
