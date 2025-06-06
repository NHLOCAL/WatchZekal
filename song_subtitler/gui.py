import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import json
import os
import subprocess
import threading
import sys

class VideoCreatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("יוצר סרטוני כתוביות")
        self.root.geometry("800x750")
        self.process = None

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TLabel", font=("Arial", 10), anchor="e")
        self.style.configure("TButton", font=("Arial", 10, "bold"))
        self.style.configure("TEntry", font=("Arial", 10))
        self.style.configure("TCombobox", font=("Arial", 10))
        self.style.configure("TLabelframe.Label", font=("Arial", 11, "bold"))

        self.song_data = []
        self.song_names_for_dropdown = []
        self.artist_names = []
        self.song_artist_pairs = set()
        self._load_song_data()

        self._create_widgets()

    def _load_song_data(self):
        """טוען את רשימת השירים, האמנים, ויוצר סט של זוגות (שם+אמן) לבדיקת ייחודיות"""
        config_dir = 'config'
        song_list_file = 'song_list.json'
        json_path = os.path.join(config_dir, song_list_file)

        if not os.path.exists(json_path):
            print(f"אזהרה: קובץ רשימת השירים '{json_path}' לא נמצא.")
            return

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.song_data = json.load(f)
            
            self.song_names_for_dropdown = sorted([song.get('name', '') for song in self.song_data if song.get('name')])
            all_artists = {song.get('artist', '') for song in self.song_data if song.get('artist')}
            self.artist_names = sorted(list(all_artists))

            self.song_artist_pairs = {
                (s.get('name', '').strip().lower(), s.get('artist', '').strip().lower())
                for s in self.song_data if s.get('name')
            }
        except (json.JSONDecodeError, Exception) as e:
            print(f"שגיאה בטעינת קובץ השירים '{json_path}': {e}")
            self.song_data = []

    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        details_frame = ttk.Labelframe(main_frame, text="פרטי השיר", padding="10")
        details_frame.pack(fill=tk.X, expand=True, pady=5)
        self._create_main_details_frame(details_frame)

        files_frame = ttk.Labelframe(main_frame, text="נתיבי קבצים (אופציונלי)", padding="10")
        files_frame.pack(fill=tk.X, expand=True, pady=5)
        self._create_file_paths_frame(files_frame)
        
        advanced_frame = ttk.Labelframe(main_frame, text="הגדרות מתקדמות", padding="10")
        advanced_frame.pack(fill=tk.X, expand=True, pady=5)
        self._create_advanced_options_frame(advanced_frame)

        action_frame = ttk.Frame(main_frame)
        action_frame.pack(pady=10)
        
        self.run_button = ttk.Button(action_frame, text="צור וידאו", command=self._start_processing, style="TButton")
        self.run_button.pack(side=tk.LEFT, ipady=5, ipadx=10, padx=5)

        self.cancel_button = ttk.Button(action_frame, text="בטל תהליך", command=self._cancel_processing, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, ipady=5, ipadx=10, padx=5)

        output_frame = ttk.Labelframe(main_frame, text="פלט התהליך", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.copy_log_button = ttk.Button(output_frame, text="העתק לוג", command=self._copy_log_to_clipboard)
        self.copy_log_button.pack(anchor='nw', pady=(0, 5))

        self.output_console = scrolledtext.ScrolledText(output_frame, height=10, wrap=tk.WORD, font=("Courier New", 9))
        self.output_console.pack(fill=tk.BOTH, expand=True)

    def _create_main_details_frame(self, parent):
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text="שם השיר:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.song_name_var = tk.StringVar()
        self.song_name_combo = ttk.Combobox(parent, textvariable=self.song_name_var, values=self.song_names_for_dropdown)
        self.song_name_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.song_name_combo.bind('<<ComboboxSelected>>', self._on_song_select)
        self.song_name_combo.bind('<KeyRelease>', self._on_song_name_change)
        ttk.Label(parent, text="שם הזמר:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.artist_name_var = tk.StringVar()
        self.artist_name_combo = ttk.Combobox(parent, textvariable=self.artist_name_var, values=self.artist_names)
        self.artist_name_combo.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(parent, text="שם בעברית:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        self.hebrew_name_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.hebrew_name_var).grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(parent, text="קישור YouTube:").grid(row=3, column=0, padx=5, pady=5, sticky=tk.W)
        self.url_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.url_var).grid(row=3, column=1, padx=5, pady=5, sticky="ew")

    def _create_file_paths_frame(self, parent):
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text="קובץ MP3:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.mp3_path_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.mp3_path_var).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(parent, text="עיון...", command=lambda: self._browse_file(self.mp3_path_var, [("MP3 files", "*.mp3")])).grid(row=0, column=2, padx=5, pady=5)
        ttk.Label(parent, text="קובץ מילים:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.lyrics_path_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.lyrics_path_var).grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(parent, text="עיון...", command=lambda: self._browse_file(self.lyrics_path_var, [("Text files", "*.txt")])).grid(row=1, column=2, padx=5, pady=5)
        ttk.Label(parent, text="כתוביות מקור:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        self.source_subs_path_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.source_subs_path_var).grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(parent, text="עיון...", command=lambda: self._browse_file(self.source_subs_path_var, [("Subtitle files", "*.srt *.json")])).grid(row=2, column=2, padx=5, pady=5)
        ttk.Label(parent, text="כתוביות יעד:").grid(row=3, column=0, padx=5, pady=5, sticky=tk.W)
        self.target_subs_path_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.target_subs_path_var).grid(row=3, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(parent, text="עיון...", command=lambda: self._browse_file(self.target_subs_path_var, [("Subtitle files", "*.srt *.json")])).grid(row=3, column=2, padx=5, pady=5)

    def _create_advanced_options_frame(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)
        lang_frame = ttk.Frame(parent)
        ttk.Label(lang_frame, text="שפת מקור:").pack(side=tk.LEFT, padx=5)
        self.lang_var = tk.StringVar(value='en')
        ttk.Radiobutton(lang_frame, text="אנגלית", variable=self.lang_var, value='en').pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(lang_frame, text="יידיש", variable=self.lang_var, value='yi').pack(side=tk.LEFT, padx=5)
        lang_frame.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
        self.force_regen_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(parent, text="אלץ יצירה מחדש מה-API", variable=self.force_regen_var).grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
        ttk.Label(parent, text="כותרת משנה בפתיח:").grid(row=0, column=2, padx=15, pady=5, sticky=tk.W)
        self.intro_subtitle_var = tk.StringVar(value='artist')
        intro_combo = ttk.Combobox(parent, textvariable=self.intro_subtitle_var, values=['artist', 'hebrew'], state='readonly')
        intro_combo.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

    # ######### פונקציה חדשה לניקוי קלט #########
    def _sanitize_input(self, value):
        """מנקה את הקלט: מסיר רווחים ומרכאות חיצוניות."""
        if not isinstance(value, str):
            return value
        s = value.strip()
        # לולאה להסרת מספר שכבות של מרכאות אפשריות
        while len(s) >= 2 and s.startswith(('"', "'")) and s.startswith(s[0]) and s.endswith(s[0]):
            s = s[1:-1].strip()
        return s
    # ###########################################

    # ######### פונקציה חדשה לעיצוב פקודה לתצוגה #########
    def _format_command_for_display(self, command_list):
        """מעצבת רשימת ארגומנטים למחרוזת פקודה קריאה עם מרכאות."""
        display_parts = []
        for part in command_list:
            # הוסף מרכאות אם הארגומנט מכיל רווחים
            if ' ' in part:
                display_parts.append(f'"{part}"')
            else:
                display_parts.append(part)
        return ' '.join(display_parts)
    # ###########################################
    
    def _copy_log_to_clipboard(self):
        log_content = self.output_console.get('1.0', tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(log_content)
        original_text = self.copy_log_button.cget("text")
        self.copy_log_button.config(text="הועתק!")
        self.root.after(1500, lambda: self.copy_log_button.config(text=original_text))
        
    def _on_song_select(self, event=None):
        selected_name = self.song_name_var.get()
        song_info = next((s for s in self.song_data if s.get('name') == selected_name), None)
        if song_info:
            self.artist_name_var.set(song_info.get('artist', ''))
            self.hebrew_name_var.set(song_info.get('hebrew_name', ''))
            self.url_var.set(song_info.get('youtube_url', ''))
            self.lang_var.set(song_info.get('language', 'en'))
            self.mp3_path_var.set('')
            self.lyrics_path_var.set(song_info.get('lyrics_file', ''))
            self.source_subs_path_var.set('')
            self.target_subs_path_var.set('')

    def _on_song_name_change(self, event=None):
        current_text = self.song_name_var.get()
        if current_text not in self.song_names_for_dropdown:
            self.artist_name_var.set('')
            self.hebrew_name_var.set('')
            self.url_var.set('')
            self.lyrics_path_var.set('')
            
    def _browse_file(self, string_var, file_types):
        file_path = filedialog.askopenfilename(filetypes=file_types)
        if file_path:
            string_var.set(file_path)

    def _start_processing(self):
        self.run_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.NORMAL)
        self.output_console.delete('1.0', tk.END)
        self.output_console.insert(tk.END, "מתחיל עיבוד...\n" + "="*30 + "\n")

        # ######### שינוי: שימוש בפונקציית הניקוי על כל הקלטים #########
        song_name = self._sanitize_input(self.song_name_var.get())
        artist_name = self._sanitize_input(self.artist_name_var.get())
        
        if not song_name:
            self._update_output_console("שגיאה: שם השיר הוא שדה חובה.\n")
            self._reset_buttons()
            return
        
        current_pair = (song_name.lower(), artist_name.lower())
        is_existing_song = current_pair in self.song_artist_pairs

        cmd_args = []
        if is_existing_song:
            cmd_args.extend(["-s", song_name])
        else:
            cmd_args.append("--add")
            cmd_args.extend(["-n", song_name])
            if artist_name: cmd_args.extend(["-ar", artist_name])
        
        hebrew_name = self._sanitize_input(self.hebrew_name_var.get())
        url = self._sanitize_input(self.url_var.get())
        mp3_path = self._sanitize_input(self.mp3_path_var.get())
        lyrics_path = self._sanitize_input(self.lyrics_path_var.get())
        source_subs_path = self._sanitize_input(self.source_subs_path_var.get())
        target_subs_path = self._sanitize_input(self.target_subs_path_var.get())
        # #############################################################

        language = self.lang_var.get()
        force_regenerate = self.force_regen_var.get()
        intro_subtitle = self.intro_subtitle_var.get()

        if hebrew_name: cmd_args.extend(["-hn", hebrew_name])
        if url: cmd_args.extend(["-u", url])
        if mp3_path: cmd_args.extend(["-sm", mp3_path])
        if lyrics_path: cmd_args.extend(["-lf", lyrics_path])
        if source_subs_path: cmd_args.extend(["-ss", source_subs_path])
        if target_subs_path: cmd_args.extend(["-ts", target_subs_path])
        if language: cmd_args.extend(["-l", language])
        if force_regenerate: cmd_args.append("-f")
        if intro_subtitle: cmd_args.extend(["-is", intro_subtitle])

        thread = threading.Thread(target=self._process_runner_thread, args=(cmd_args,))
        thread.daemon = True
        thread.start()

    def _cancel_processing(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self._update_output_console("\n\n*** נשלחה בקשת ביטול לתהליך... ***\n")
            except Exception as e:
                self._update_output_console(f"\nשגיאה בעת ניסיון לבטל את התהליך: {e}\n")
        else:
            self._update_output_console("\nאין תהליך פעיל לביטול.\n")
        self.cancel_button.config(state=tk.DISABLED)

    def _reset_buttons(self):
        self.run_button.config(state=tk.NORMAL)
        self.cancel_button.config(state=tk.DISABLED)

    def _process_runner_thread(self, args):
        command = [sys.executable, "main.py"] + args
        
        # ######### שינוי: שימוש בפונקציית העיצוב לתצוגה #########
        display_command = self._format_command_for_display(command)
        self._update_output_console(f"מריץ פקודה: {display_command}\n\n")
        # #######################################################

        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            for line in iter(self.process.stdout.readline, ''):
                self.root.after(0, self._update_output_console, line)
            
            self.process.stdout.close()
            return_code = self.process.wait()

            if return_code == 0:
                self.root.after(0, self._update_output_console, "\n\nתהליך הסתיים בהצלחה!\n")
            else:
                self.root.after(0, self._update_output_console, f"\n\nתהליך נכשל או בוטל עם קוד: {return_code}\n")

        except FileNotFoundError:
            self.root.after(0, self._update_output_console, "שגיאה: הקובץ 'main.py' לא נמצא. ודא שהסקריפט נמצא בתיקייה הנכונה.\n")
        except Exception as e:
            self.root.after(0, self._update_output_console, f"אירעה שגיאה בלתי צפויה: {e}\n")
        finally:
            self.process = None
            self.root.after(0, self._reset_buttons)

    def _update_output_console(self, text):
        self.output_console.insert(tk.END, text)
        self.output_console.see(tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoCreatorGUI(root)
    root.mainloop()