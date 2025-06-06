# בקובץ gui_runner.py

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

        # הגדרת סגנון
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TLabel", font=("Arial", 10), anchor="e")
        self.style.configure("TButton", font=("Arial", 10, "bold"))
        self.style.configure("TEntry", font=("Arial", 10))
        self.style.configure("TCombobox", font=("Arial", 10))
        self.style.configure("TLabelframe.Label", font=("Arial", 11, "bold"))

        # טעינת נתונים קיימים
        self.song_data = []
        self.song_names = []
        self.artist_names = []
        self._load_song_data()

        # יצירת הממשק
        self._create_widgets()

    def _load_song_data(self):
        """טוען את רשימת השירים ורשימת האמנים מהקובץ JSON"""
        config_dir = 'config'
        song_list_file = 'song_list.json'
        json_path = os.path.join(config_dir, song_list_file)

        if not os.path.exists(json_path):
            print(f"אזהרה: קובץ רשימת השירים '{json_path}' לא נמצא.")
            return

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.song_data = json.load(f)
            
            self.song_names = sorted([song.get('name', '') for song in self.song_data if song.get('name')])
            all_artists = {song.get('artist', '') for song in self.song_data if song.get('artist')}
            self.artist_names = sorted(list(all_artists))

        except (json.JSONDecodeError, Exception) as e:
            print(f"שגיאה בטעינת קובץ השירים '{json_path}': {e}")
            self.song_data = []

    def _create_widgets(self):
        """יוצר וממקם את כל הווידג'טים בחלון"""
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

        self.run_button = ttk.Button(main_frame, text="צור וידאו", command=self._start_processing, style="TButton")
        self.run_button.pack(pady=10, ipady=5, ipadx=10)

        output_frame = ttk.Labelframe(main_frame, text="פלט התהליך", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # ######### שינוי: הוספת כפתור העתקה #########
        self.copy_log_button = ttk.Button(output_frame, text="העתק לוג", command=self._copy_log_to_clipboard)
        self.copy_log_button.pack(anchor='nw', pady=(0, 5))
        # ###########################################

        self.output_console = scrolledtext.ScrolledText(output_frame, height=10, wrap=tk.WORD, font=("Courier New", 9))
        self.output_console.pack(fill=tk.BOTH, expand=True)

    def _create_main_details_frame(self, parent):
        parent.columnconfigure(1, weight=1)

        ttk.Label(parent, text="שם השיר:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.song_name_var = tk.StringVar()
        self.song_name_combo = ttk.Combobox(parent, textvariable=self.song_name_var, values=self.song_names)
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

    # ######### פונקציה חדשה להעתקת הלוג #########
    def _copy_log_to_clipboard(self):
        """מעתיקה את כל התוכן של תיבת הפלט ללוח."""
        log_content = self.output_console.get('1.0', tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(log_content)
        # אפשר להוסיף חיווי למשתמש, למשל:
        original_text = self.copy_log_button.cget("text")
        self.copy_log_button.config(text="הועתק!")
        self.root.after(1500, lambda: self.copy_log_button.config(text=original_text))
    # ###########################################
        
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
        if current_text not in self.song_names:
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
        self.output_console.delete('1.0', tk.END)
        self.output_console.insert(tk.END, "מתחיל עיבוד...\n" + "="*30 + "\n")

        song_name = self.song_name_var.get().strip()
        artist_name = self.artist_name_var.get().strip()
        hebrew_name = self.hebrew_name_var.get().strip()
        url = self.url_var.get().strip()
        mp3_path = self.mp3_path_var.get().strip()
        lyrics_path = self.lyrics_path_var.get().strip()
        source_subs_path = self.source_subs_path_var.get().strip()
        target_subs_path = self.target_subs_path_var.get().strip()
        language = self.lang_var.get()
        force_regenerate = self.force_regen_var.get()
        intro_subtitle = self.intro_subtitle_var.get()

        if not song_name:
            self._update_output_console("שגיאה: שם השיר הוא שדה חובה.\n")
            self.run_button.config(state=tk.NORMAL)
            return

        cmd_args = []
        is_new_song = song_name not in self.song_names
        
        if is_new_song:
            cmd_args.append("--add")
            cmd_args.extend(["-n", song_name])
            if artist_name: cmd_args.extend(["-ar", artist_name])
            if hebrew_name: cmd_args.extend(["-hn", hebrew_name])
            if url: cmd_args.extend(["-u", url])
            if not url and not (source_subs_path and target_subs_path):
                self._update_output_console("שגיאה: עבור שיר חדש, יש לספק קישור YouTube או גם קובץ כתוביות מקור וגם קובץ יעד.\n")
                self.run_button.config(state=tk.NORMAL)
                return
        else:
            cmd_args.extend(["-s", song_name])

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

    def _process_runner_thread(self, args):
        command = [sys.executable, "main.py"] + args
        self._update_output_console(f"מריץ פקודה: {' '.join(command)}\n\n")

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            for line in iter(process.stdout.readline, ''):
                self.root.after(0, self._update_output_console, line)
            
            process.stdout.close()
            return_code = process.wait()

            if return_code == 0:
                self.root.after(0, self._update_output_console, "\n\nתהליך הסתיים בהצלחה!\n")
            else:
                self.root.after(0, self._update_output_console, f"\n\nתהליך נכשל עם קוד שגיאה: {return_code}\n")

        except FileNotFoundError:
            self.root.after(0, self._update_output_console, "שגיאה: הקובץ 'main.py' לא נמצא. ודא שהסקריפט נמצא בתיקייה הנכונה.\n")
        except Exception as e:
            self.root.after(0, self._update_output_console, f"אירעה שגיאה בלתי צפויה: {e}\n")

        self.root.after(0, lambda: self.run_button.config(state=tk.NORMAL))

    def _update_output_console(self, text):
        self.output_console.insert(tk.END, text)
        self.output_console.see(tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoCreatorGUI(root)
    root.mainloop()