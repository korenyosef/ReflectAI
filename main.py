import keyboard
import tkinter as tk
from tkinter import font
import threading
import os
import re
import time
import queue
from groq import Groq
from dotenv import load_dotenv

# טוען את קובץ ה-.env (ואם הוא חסר או שהספריה חסרה, תקבל שגיאה ברורה במקום קריסה שקטה)
load_dotenv()

# --- Configuration ---
CONFIG = {
    # עכשיו הוא ייקח את המפתח אך ורק מקובץ ה-.env שלך
    "GROQ_API_KEY": os.environ.get("GROQ_API_KEY"),
    "MODEL_NAME": "llama-3.1-8b-instant",
    "MIN_TEXT_LENGTH": 3,
    "THEME_COLOR": "#0f8b8d",
    "THEME_HOVER": "#0a6f71",
    "BG_COLOR": "#eef7f1",
    "SURFACE_COLOR": "#ffffff",
    "SURFACE_ALT": "#e8f6f5",
    "ACCENT_COLOR": "#fff2b8",
    "BORDER_COLOR": "#b8d8d1",
    "TEXT_COLOR": "#1f302f",
    "MUTED_TEXT": "#5f6f6b",
    "DANGER_COLOR": "#d94f45",
    "DANGER_SOFT": "#ffe7e3",
    "SHADOW_COLOR": "#d6e4de"
}

ENGLISH_TO_HEBREW_KEYS = {
    "q": "/", "w": "'", "e": "ק", "r": "ר", "t": "א", "y": "ט", "u": "ו",
    "i": "ן", "o": "ם", "p": "פ", "a": "ש", "s": "ד", "d": "ג",
    "f": "כ", "g": "ע", "h": "י", "j": "ח", "k": "ל", "l": "ך",
    ";": "ף", "z": "ז", "x": "ס", "c": "ב", "v": "ה", "b": "נ",
    "n": "מ", "m": "צ", ",": "ת", ".": "ץ", "/": "."
}

ENGLISH_TO_HEBREW_TRANSLATION = str.maketrans({
    **ENGLISH_TO_HEBREW_KEYS,
    **{key.upper(): value for key, value in ENGLISH_TO_HEBREW_KEYS.items() if key.isalpha()}
})

HEBREW_TO_ENGLISH_TRANSLATION = str.maketrans({
    value: key for key, value in ENGLISH_TO_HEBREW_KEYS.items() if "\u0590" <= value <= "\u05ff"
})

ENGLISH_WORD_HINTS = {
    "i", "you", "hate", "kill", "die", "ugly", "idiot", "stupid", "dumb",
    "trash", "noob", "bot", "your", "youre", "are", "go", "me", "my",
    "im", "i'm", "really", "frustrated", "with", "right", "now", "mad",
    "angry", "upset", "please", "stop", "need", "break", "conversation"
}

HEBREW_WORD_HINTS = {
    "אני", "אתה", "את", "אותך", "שונא", "שונאת", "אוהב", "אוהבת",
    "תמות", "למות", "מכוער", "מכוערת", "טיפש", "טיפשה", "סתום",
    "חביבי", "שלך", "לך", "לי", "לא", "כן", "על", "עם", "זה", "זאת",
    "ממש", "כועס", "כועסת", "כרגע", "צריך", "צריכה", "רגע", "לפני",
    "מגיב", "מגיבה", "שיחה", "בבקשה", "תפסיק", "תפסיקי"
}

# נוודא שהמפתח אכן נטען בהצלחה לפני שהפרוייקט ממשיך לרוץ
if not CONFIG["GROQ_API_KEY"]:
    raise ValueError("Groq API Key is missing! Please make sure your .env file is set correctly.")

class ReflectAIApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.ui_queue = queue.Queue()

        self.client = Groq(api_key=CONFIG["GROQ_API_KEY"], timeout=8.0)
        self.current_buffer = ""
        self.is_processing = False
        self.shift_pressed = False
        self.loading_window = None
        self.loading_animation_after = None
        self.last_submit_time = 0
        self.popup_open = False
        self.last_processed_text = ""
        
        self._setup_styles()
        
        # Start background listener
        self.listener_thread = threading.Thread(target=self._start_keyboard_listener, daemon=True)
        self.listener_thread.start()
        
        # Start polling the queue
        self.root.after(100, self._process_queue)
        
        print("--- ReflectAI Core Started ---")
        print("Listening for a safer digital world...")

    def _setup_styles(self):
        display_family = self._pick_font(
            ("Aptos Display", "Segoe UI Variable Display", "Bahnschrift", "Trebuchet MS", "Helvetica")
        )
        body_family = self._pick_font(
            ("Aptos", "Segoe UI Variable Text", "Segoe UI", "Trebuchet MS", "Helvetica")
        )

        self.kicker_font = font.Font(family=body_family, size=9, weight="bold")
        self.title_font = font.Font(family=display_family, size=20, weight="bold")
        self.header_font = font.Font(family=display_family, size=16, weight="bold")
        self.body_font = font.Font(family=body_family, size=11)
        self.small_font = font.Font(family=body_family, size=9)
        self.suggest_font = font.Font(family=body_family, size=12, slant="italic")
        self.button_font = font.Font(family=body_family, size=10, weight="bold")

    def _pick_font(self, candidates):
        available_fonts = set(font.families(self.root))
        for family in candidates:
            if family in available_fonts:
                return family
        return "Helvetica"

    def _truncate_text(self, text, limit=140):
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[:limit - 3].rstrip() + "..."

    def _is_hebrew_dominant(self, text):
        hebrew_count = sum(1 for char in text if "\u0590" <= char <= "\u05ff")
        latin_count = sum(1 for char in text if "a" <= char.lower() <= "z")
        return hebrew_count > 0 and hebrew_count >= latin_count

    def _label_text_options(self, text, limit):
        display_text = self._truncate_text(text, limit)
        if self._is_hebrew_dominant(display_text):
            return f"\u202b{display_text}\u202c", "right", "e"
        return display_text, "left", "w"

    def _contains_latin(self, text):
        return any(("a" <= char.lower() <= "z") for char in text)

    def _contains_hebrew(self, text):
        return any("\u0590" <= char <= "\u05ff" for char in text)

    def _english_keyboard_to_hebrew(self, text):
        converted_chars = []
        for index, char in enumerate(text):
            converted = char.translate(ENGLISH_TO_HEBREW_TRANSLATION)
            next_char = text[index + 1] if index + 1 < len(text) else ""

            if char == "." and (not next_char or next_char.isspace()):
                converted = "."

            converted_chars.append(converted)

        return "".join(converted_chars)

    def _language_scores(self, text):
        normalized = text.lower()
        english_words = re.findall(r"[a-z']+", normalized)
        hebrew_words = re.findall(r"[\u0590-\u05ff]+", text)

        english_score = sum(1 for word in english_words if word in ENGLISH_WORD_HINTS)
        hebrew_score = sum(1 for word in hebrew_words if word in HEBREW_WORD_HINTS)

        return english_score, hebrew_score

    def _interpret_text(self, text):
        candidates = self._keyboard_layout_candidates(text)
        best_label, best_text = candidates[0]
        best_language = self._language_from_characters(text)
        best_score = -1

        for label, value in candidates:
            english_score, hebrew_score = self._language_scores(value)
            score = max(english_score, hebrew_score)

            if hebrew_score > english_score:
                language = "Hebrew"
            elif english_score > hebrew_score:
                language = "English"
            else:
                language = self._language_from_characters(value)

            if score > best_score:
                best_label = label
                best_text = value
                best_language = language
                best_score = score

        return {
            "original_text": text,
            "intended_text": best_text,
            "intended_language": best_language,
            "best_label": best_label,
            "candidates": candidates
        }

    def _language_from_characters(self, text):
        if self._contains_hebrew(text) and not self._contains_latin(text):
            return "Hebrew"
        if self._contains_latin(text) and not self._contains_hebrew(text):
            return "English"
        return "Unknown"

    def _infer_intended_language(self, text):
        return self._interpret_text(text)["intended_language"]

    def _keyboard_layout_candidates(self, text):
        candidates = [("Original typed text", text)]
        seen = {text}

        if self._contains_latin(text):
            hebrew_guess = self._english_keyboard_to_hebrew(text)
            if hebrew_guess not in seen:
                candidates.append(("English keyboard, Hebrew intended", hebrew_guess))
                seen.add(hebrew_guess)

        if self._contains_hebrew(text):
            english_guess = text.translate(HEBREW_TO_ENGLISH_TRANSLATION)
            if english_guess not in seen:
                candidates.append(("Hebrew keyboard, English intended", english_guess))

        return candidates

    def _fallback_suggestion(self, language_hint):
        if language_hint == "Hebrew":
            return "אני צריך לקחת רגע לפני שאני מגיב."
        return "I need to take a moment before I respond."

    def _clean_ai_response(self, content, language_hint, original_candidates):
        cleaned = content.strip()
        cleaned = cleaned.replace("\\n", "\n")
        cleaned = re.sub(r"^```(?:\w+)?|```$", "", cleaned, flags=re.MULTILINE).strip()
        cleaned = re.sub(r"(?i)^\s*(output|replacement|suggestion)\s*:\s*", "", cleaned).strip()

        if cleaned.upper() == "SAFE" or cleaned.upper().startswith("SAFE"):
            return "SAFE"

        candidate_values = {
            value.strip().strip("\"' :.,")
            for _label, value in original_candidates
            if value.strip()
        }

        lines = []
        for line in cleaned.splitlines():
            line = re.sub(r"(?i)^\s*(output|replacement|suggestion)\s*:\s*", "", line).strip()
            line = line.strip("\"' :.,")
            if not line or line in candidate_values:
                continue
            lines.append(line)

        if not lines:
            return self._fallback_suggestion(language_hint)

        if language_hint == "Hebrew":
            hebrew_lines = []
            for line in lines:
                no_translation = re.sub(r"\([^)]*[A-Za-z][^)]*\)", "", line).strip()
                no_translation = no_translation.strip("\"' :.,")
                if self._contains_hebrew(no_translation) and no_translation not in candidate_values:
                    hebrew_lines.append(no_translation)
            if hebrew_lines:
                return " ".join(hebrew_lines).strip() or self._fallback_suggestion(language_hint)
            return self._fallback_suggestion(language_hint)

        if language_hint == "English":
            english_lines = [
                line for line in lines
                if self._contains_latin(line) and line not in candidate_values
            ]
            if english_lines:
                return " ".join(english_lines).strip("\"' :.,")
            return self._fallback_suggestion(language_hint)

        return lines[0].strip("\"' :.,") or self._fallback_suggestion(language_hint)

    def _create_popup_window(self, title, width, height):
        window = tk.Toplevel(self.root)
        window.title(title)
        window.configure(bg=CONFIG["BG_COLOR"])
        window.attributes("-topmost", True)
        window.resizable(False, False)
        self._center_window(window, width, height)
        window.lift()
        window.focus_force()
        return window

    def _make_shell(self, window, padx=18, pady=18):
        outer = tk.Frame(window, bg=CONFIG["BG_COLOR"], padx=padx, pady=pady)
        outer.pack(fill="both", expand=True)

        shell = tk.Frame(
            outer,
            bg=CONFIG["SURFACE_COLOR"],
            highlightbackground=CONFIG["BORDER_COLOR"],
            highlightthickness=1,
            padx=24,
            pady=22
        )
        shell.pack(fill="both", expand=True)
        return shell

    def _styled_button(self, parent, text, command, variant="primary"):
        if variant == "primary":
            bg = CONFIG["THEME_COLOR"]
            fg = "white"
            hover_bg = CONFIG["THEME_HOVER"]
        else:
            bg = CONFIG["SURFACE_ALT"]
            fg = CONFIG["TEXT_COLOR"]
            hover_bg = "#d9eeeb"

        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=hover_bg,
            activeforeground=fg,
            font=self.button_font,
            relief="flat",
            bd=0,
            padx=18,
            pady=10,
            cursor="hand2",
            takefocus=True
        )
        button.bind("<Enter>", lambda _event: button.configure(bg=hover_bg))
        button.bind("<Leave>", lambda _event: button.configure(bg=bg))
        return button

    def _start_keyboard_listener(self):
        """Initializes global hooks for buffer tracking and Enter suppression."""
        # 1. Global hook for buffer tracking (does NOT suppress keys)
        keyboard.hook(self._handle_buffer_event)
        
        # 2. Specific aggressive hook for Enter suppression
        self._register_enter_hook()
        
        keyboard.wait()

    def _center_window(self, window, width, height):
        window.update_idletasks()
        x = (window.winfo_screenwidth() // 2) - (width // 2)
        y = (window.winfo_screenheight() // 2) - (height // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _show_loading_ui(self, original_text):
        if hasattr(self, "loading_window") and self.loading_window and self.loading_window.winfo_exists():
            return

        self.loading_window = self._create_popup_window("ReflectAI", 460, 230)
        shell = self._make_shell(self.loading_window)

        tk.Label(
            shell,
            text="REFLECTAI",
            font=self.kicker_font,
            fg=CONFIG["THEME_COLOR"],
            bg=CONFIG["SURFACE_COLOR"]
        ).pack(anchor="w")

        tk.Label(
            shell,
            text="Checking before send",
            font=self.header_font,
            bg=CONFIG["SURFACE_COLOR"],
            fg=CONFIG["TEXT_COLOR"]
        ).pack(anchor="w", pady=(6, 4))

        tk.Label(
            shell,
            text="One moment while I read the tone.",
            font=self.body_font,
            bg=CONFIG["SURFACE_COLOR"],
            fg=CONFIG["MUTED_TEXT"]
        ).pack(anchor="w")

        progress = tk.Canvas(shell, width=360, height=8, bg=CONFIG["SURFACE_COLOR"], highlightthickness=0)
        progress.pack(anchor="w", fill="x", pady=(18, 14))
        progress.create_rectangle(0, 0, 360, 8, fill=CONFIG["SURFACE_ALT"], outline="")
        bar = progress.create_rectangle(0, 0, 92, 8, fill=CONFIG["THEME_COLOR"], outline="")

        preview_text, preview_justify, preview_anchor = self._label_text_options(original_text, 120)
        preview = tk.Label(
            shell,
            text=preview_text,
            font=self.small_font,
            bg=CONFIG["SURFACE_ALT"],
            fg=CONFIG["MUTED_TEXT"],
            wraplength=360,
            justify=preview_justify,
            anchor=preview_anchor,
            padx=12,
            pady=10
        )
        preview.pack(anchor=preview_anchor, fill="x")

        def _animate(offset=0):
            window = self.loading_window
            try:
                if not window or not window.winfo_exists():
                    return
                left = (offset % 452) - 92
                progress.coords(bar, left, 0, left + 92, 8)
                self.loading_animation_after = window.after(24, lambda: _animate(offset + 8))
            except tk.TclError:
                return

        _animate()

        self.loading_window.protocol("WM_DELETE_WINDOW", lambda: None)

    def _close_loading_ui(self):
        if hasattr(self, "loading_window") and self.loading_window:
            try:
                if self.loading_animation_after:
                    self.loading_window.after_cancel(self.loading_animation_after)
                    self.loading_animation_after = None
                if self.loading_window.winfo_exists():
                    self.loading_window.destroy()
            except:
                pass
            self.loading_window = None

    def _register_enter_hook(self):
        """Registers the driver-level Enter suppression hook."""
        self.enter_hook = keyboard.on_press_key("enter", self._handle_enter_press, suppress=True)

    def _handle_buffer_event(self, event):
        """Tracks keystrokes to maintain a real-time buffer of what the user is typing."""
        if event.name == 'shift':
            self.shift_pressed = (event.event_type == keyboard.KEY_DOWN)
            return

        if event.event_type != keyboard.KEY_DOWN:
            return

        # Don't track if we are currently intervening
        if self.is_processing:
            return

        if event.name == 'backspace':
            self.current_buffer = self.current_buffer[:-1]
        elif event.name == 'space':
            self.current_buffer += " "
        elif len(event.name) == 1:
            char = event.name
            if self.shift_pressed:
                # Basic Shift mapping for letters
                if 'a' <= char <= 'z':
                    char = char.upper()
                # Common symbol mappings (US layout)
                shift_map = {'1':'!','2':'@','3':'#','4':'$','5':'%','6':'^','7':'&','8':'*','9':'(','0':')','-':'_','=':'+'}
                char = shift_map.get(char, char)
            self.current_buffer += char

    def _handle_enter_press(self, event):
        now = time.time()

        if self.is_processing:
            return

        if now - self.last_submit_time < 0.4:
            return

        self.last_submit_time = now

        text_to_check = self.current_buffer.strip()
        if len(text_to_check) < CONFIG["MIN_TEXT_LENGTH"]:
            self.current_buffer = ""
            self._send_enter_safely()
            return

        text_context = self._interpret_text(text_to_check)
        self.is_processing = True
        self.ui_queue.put(("loading", text_context["intended_text"]))
        threading.Thread(target=self._process_submission, args=(text_to_check, text_context), daemon=True).start()

    def _send_enter_safely(self):
        """Releases a single Enter key by temporarily unhooking suppression."""
        keyboard.unhook(self.enter_hook)
        keyboard.send('enter')
        # Tiny delay to ensure the key is processed before re-hooking
        time.sleep(0.01)
        self._register_enter_hook()

    def _analyze_text(self, text, text_context=None):
        """Analyze text via Groq and return 'SAFE' or a kinder alternative."""
        text_context = text_context or self._interpret_text(text)
        intended_text = text_context["intended_text"]
        language_hint = text_context["intended_language"]
        candidates = text_context["candidates"]
        candidate_lines = "\n".join(f"- {label}: {value}" for label, value in candidates)

        system_prompt = (
            "You are an advanced text-moderation engine for a child-safety application. "
            "Your task is to analyze user input and decide if it is SAFE or HURTFUL.\n\n"
            "IMPORTANT KEYBOARD-LAYOUT RULE:\n"
            "The user may have typed Hebrew while the keyboard was set to English, or English while the keyboard was set to Hebrew. "
            "You will receive a best interpretation and candidate interpretations. Evaluate the best interpretation unless it is clearly nonsensical. "
            "Choose the candidate that is meaningful natural language. "
            "Ignore candidates that look like keyboard-layout gibberish. If both the original and a candidate are meaningful, prefer the original typed text.\n\n"
            "DEFINITIONS:\n"
            "- SAFE: Normal everyday conversation, gaming slang (e.g., 'noob', 'bot'), mild annoyance, jokes, complaints about a situation (e.g., 'this game is stupid'), or neutral statements. When in doubt, lean heavily towards SAFE to avoid false positives.\n"
            "- HURTFUL: Direct bullying, severe personal insults, profanity, racism, threats, telling someone to harm themselves, or extreme aggression directed at a person.\n\n"
            "CORE DIRECTIVES:\n"
            "1. If the input is SAFE, output ONLY the exact word: SAFE\n"
            "2. If the input is HURTFUL, output ONLY a kinder, respectful replacement.\n"
            "3. Never output the original hurtful text.\n"
            "4. PRESERVE MEANING: The replacement should convey the original intent but politely. If the original intent is purely malicious (e.g., 'go die', 'you are ugly'), output a neutral boundary like 'I need to take a break from this conversation.' or 'Please don't speak to me like that.'\n"
            "5. LANGUAGE: Output the replacement in the same language as the meaningful intended text, including Hebrew when the Hebrew candidate is the intended text.\n"
            "6. ONE LANGUAGE ONLY: Do not include translations, parentheses, slash alternatives, or both Hebrew and English in the same answer.\n"
            "7. NO FILLER: Do not explain, do not use quotes, do not say 'Here is a replacement:'. Just output the final string.\n\n"
            "EXAMPLES:\n"
            "Input: 'Want to play?'\n"
            "Output: SAFE\n\n"
            "Input: 'you are an absolute idiot and I hate you'\n"
            "Output: I'm really frustrated with you right now.\n\n"
            "Input: 'אני שונא אותך חביבי'\n"
            "Output: אני ממש כועס עליך כרגע.\n\n"
            "Input candidates: Original typed text: 'tbh aubt tu,l' / English keyboard, Hebrew intended: 'אני שונא אותך'\n"
            "Output: אני ממש כועס עליך כרגע.\n\n"
            "Input candidates: Original typed text: 'ן ישאק טםו' / Hebrew keyboard, English intended: 'i hate you'\n"
            "Output: I'm really frustrated with you right now.\n\n"
            "Input: 'kill yourself'\n"
            "Output: I'm stepping away from this conversation.\n\n"
            "Input: 'this homework is garbage'\n"
            "Output: SAFE\n\n"
            "Input: 'you are so ugly'\n"
            "Output: I don't think we should talk right now.\n\n"
            "Input: 'stop stealing my loot you trash player'\n"
            "Output: SAFE"
        )
        try:
            completion = self.client.chat.completions.create(
                model=CONFIG["MODEL_NAME"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            f"Original typed text: {text}\n\n"
                            f"Best interpretation to moderate: {intended_text}\n\n"
                            f"Likely intended language: {language_hint}\n\n"
                            f"Required replacement language: {language_hint}\n\n"
                            f"Candidate interpretations:\n{candidate_lines}\n\n"
                            "Output:"
                        )
                    }
                ],
                temperature=0.0,
                max_tokens=100
            )
            content = completion.choices[0].message.content.strip()
            # מנקה מרכאות או תווים מיותרים שהמודל עלול לפלוט בטעות
            return self._clean_ai_response(content, language_hint, candidates)
        except Exception as e:
            print(f"Error: {e}")
            return "SAFE"

    def _process_submission(self, text, text_context=None):
        if text == self.last_processed_text:
            return

        text_context = text_context or self._interpret_text(text)
        self.last_processed_text = text

        print(f"🔍 Analyzing: {text_context['intended_text']}")
        result = self._analyze_text(text, text_context)

        if result.upper() == "SAFE" or result.upper().startswith("SAFE"):
            self.ui_queue.put(("safe", None))
        else:
            print(f"🚨 Intervention triggered! Suggestion: {result}")
            self.ui_queue.put(("harmful", (text, text_context["intended_text"], result)))

    def _process_queue(self):
        try:
            msg = self.ui_queue.get_nowait()
            action, payload = msg

            if action == "loading":
                self._show_loading_ui(payload)

            elif action == "safe":
                self._close_loading_ui()
                self.current_buffer = ""
                self._send_enter_safely()
                self.is_processing = False
                self.last_processed_text = ""

            elif action == "harmful":
                self._close_loading_ui()
                original, intended_text, suggestion = payload
                self._show_reflection_ui(original, intended_text, suggestion)

        except queue.Empty:
            pass
        finally:
            self.root.after(50, self._process_queue)

    def _show_reflection_ui(self, original, intended_text, suggestion):
        """Displays the custom popup UI."""
        if self.popup_open:
            return

        original_text, original_justify, original_anchor = self._label_text_options(intended_text, 110)
        suggestion_text, suggestion_justify, suggestion_anchor = self._label_text_options(suggestion, 150)

        self.popup_open = True
        top = self._create_popup_window("ReflectAI - Pause & Think", 560, 440)
        shell = self._make_shell(top, padx=14, pady=14)

        content = tk.Frame(shell, bg=CONFIG["SURFACE_COLOR"])
        content.pack(fill="both", expand=True)

        accent = tk.Frame(content, bg=CONFIG["DANGER_COLOR"], width=6)
        accent.pack(side="left", fill="y", padx=(0, 18))

        panel = tk.Frame(content, bg=CONFIG["SURFACE_COLOR"])
        panel.pack(side="left", fill="both", expand=True)

        btn_frame = tk.Frame(panel, bg=CONFIG["SURFACE_COLOR"])
        btn_frame.pack(side="bottom", anchor="w", fill="x", pady=(12, 0))

        tk.Label(
            panel,
            text="PAUSE BEFORE SENDING",
            font=self.kicker_font,
            bg=CONFIG["SURFACE_COLOR"],
            fg=CONFIG["DANGER_COLOR"]
        ).pack(anchor="w")

        tk.Label(
            panel,
            text="This might land harder than you mean.",
            font=self.title_font,
            bg=CONFIG["SURFACE_COLOR"],
            fg=CONFIG["TEXT_COLOR"],
            wraplength=430,
            justify="left"
        ).pack(anchor="w", pady=(4, 6))

        tk.Label(
            panel,
            text="Take a breath, then choose a kinder version or write it again in your own words.",
            font=self.body_font,
            bg=CONFIG["SURFACE_COLOR"],
            fg=CONFIG["MUTED_TEXT"],
            wraplength=430,
            justify="left"
        ).pack(anchor="w")

        original_frame = tk.Frame(panel, bg=CONFIG["DANGER_SOFT"], padx=12, pady=10)
        original_frame.pack(anchor="w", fill="x", pady=(14, 8))
        tk.Label(
            original_frame,
            text="Your draft",
            font=self.kicker_font,
            bg=CONFIG["DANGER_SOFT"],
            fg=CONFIG["DANGER_COLOR"]
        ).pack(anchor="w")
        tk.Label(
            original_frame,
            text=original_text,
            font=self.small_font,
            bg=CONFIG["DANGER_SOFT"],
            fg=CONFIG["TEXT_COLOR"],
            wraplength=410,
            justify=original_justify,
            anchor=original_anchor
        ).pack(anchor=original_anchor, fill="x", pady=(4, 0))

        suggest_frame = tk.Frame(panel, bg=CONFIG["ACCENT_COLOR"], padx=14, pady=10)
        suggest_frame.pack(anchor="w", fill="x")
        tk.Label(
            suggest_frame,
            text="Try this instead",
            font=self.kicker_font,
            bg=CONFIG["ACCENT_COLOR"],
            fg=CONFIG["TEXT_COLOR"]
        ).pack(anchor="w")
        tk.Label(
            suggest_frame,
            text=suggestion_text,
            font=self.suggest_font,
            bg=CONFIG["ACCENT_COLOR"],
            fg=CONFIG["TEXT_COLOR"],
            wraplength=410,
            justify=suggestion_justify,
            anchor=suggestion_anchor
        ).pack(anchor=suggestion_anchor, fill="x", pady=(5, 0))

        def _use_suggest():
            self.popup_open = False
            self.last_processed_text = ""

            clipboard_ready = False
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(suggestion)
                self.root.update()
                clipboard_ready = True
            except:
                clipboard_ready = False

            top.destroy()
            time.sleep(0.35)

            delete_count = min(max(len(original), len(self.current_buffer), 1) + 2, 500)
            keyboard.press_and_release('ctrl+end')
            time.sleep(0.05)
            for _ in range(delete_count):
                keyboard.press_and_release('backspace')
                time.sleep(0.004)

            time.sleep(0.08)
            if clipboard_ready:
                keyboard.press_and_release('ctrl+v')
            else:
                keyboard.write(suggestion)

            time.sleep(0.08)
            self.current_buffer = ""
            self._send_enter_safely()
            self.is_processing = False

        def _retry():
            self.popup_open = False
            top.destroy()
            self.current_buffer = ""
            self.is_processing = False
            self.last_processed_text = ""

        self._styled_button(btn_frame, "Use kinder version", _use_suggest).pack(side="left")
        self._styled_button(btn_frame, "Rewrite myself", _retry, variant="secondary").pack(side="left", padx=(12, 0))
        
        top.bind("<Return>", lambda _event: _use_suggest())
        top.bind("<Escape>", lambda _event: _retry())
        top.protocol("WM_DELETE_WINDOW", _retry)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = ReflectAIApp()
    app.run()
