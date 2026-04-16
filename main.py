import argparse
import json
try:
    import keyboard
except Exception:
    keyboard = None
import tkinter as tk
from tkinter import font
from dataclasses import dataclass
from pathlib import Path
import threading
import os
import re
import time
import queue
try:
    from groq import Groq
except Exception:
    Groq = None
try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv():
        return None

load_dotenv()

# --- Configuration centralizes environment, model, and UI constants for safer tuning. ---
CONFIG = {
    # API keys stay in the environment so source control never owns secrets.
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

SETTINGS_FILE = Path(__file__).with_name("reflectai_settings.json")
DEFAULT_SETTINGS = {
    "sensitivity": "balanced",
    "hebrew_support": True,
    "local_rules": True,
    "confidence_threshold": 0.70,
    "paused_until": 0.0,
}

# --- Keyboard layout maps let moderation understand text typed under the wrong language layout. ---
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

# --- Language hint vocabularies help choose the most meaningful interpretation before calling AI. ---
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
    "מגיב", "מגיבה", "שיחה", "בבקשה", "תפסיק", "תפסיקי", "זונה",
    "שרמוטה", "מפגר", "מטומטם", "חרא", "מניאק", "תודה", "מלך"
}

# --- Local moderation vocabularies catch obvious harm before slower and less deterministic AI checks. ---
HEBREW_HARMFUL_TERMS = {
    "זונה", "זונות", "בן זונה", "בת זונה", "שרמוטה", "שרמוט",
    "מפגר", "מפגרת", "מטומטם", "מטומטמת", "סתום", "סתומה",
    "מכוער", "מכוערת", "מניאק", "חרא", "לך תמות", "לכי תמותי",
    "להרוג", "אהרוג", "ארצח", "תרצח", "תמות", "תמותי",
    "שונא אותך", "שונאת אותך", "אני שונא אותך", "אני שונאת אותך",
}

ENGLISH_HARMFUL_TERMS = {
    "fuck you", "fucking idiot", "bitch", "asshole", "moron", "you idiot",
    "you are stupid", "youre stupid", "you are ugly", "youre ugly",
    "kill yourself", "go die", "hate you", "i hate you", "trash player",
}

HEBREW_POSITIVE_TERMS = {
    "אוהב", "אוהבת", "אוהבים", "אוהבות", "תודה", "מעריך", "מעריכה",
    "גאה", "שמח", "שמחה", "אחי", "אחותי", "חבר", "חברה", "מלך",
    "מלכה", "אלוף", "אלופה", "מעולה", "יפה", "נהדר", "מקסים",
}

HEBREW_NEGATIVE_INTENT_TERMS = {
    "שונא", "שונאת", "כועס", "כועסת", "עצבני", "עצבנית", "מגעיל",
    "מגעילה", "דוחה", "פוגע", "פוגעת", "שנאה", "שונאים", "שונאות",
}


# --- Data contracts keep captured text, moderation results, and replacement plans explicit. ---
@dataclass(frozen=True)
class TextContext:
    raw_text: str
    intended_text: str
    intended_language: str
    best_label: str
    candidates: tuple
    raw_length: int


@dataclass(frozen=True)
class ModerationResult:
    status: str
    language: str
    confidence: float
    replacement: str
    source: str


@dataclass(frozen=True)
class ReplacementPlan:
    raw_text: str
    raw_length: int
    replacement_text: str


# --- SettingsManager isolates persistence so UI and moderation code do not touch JSON directly. ---
class SettingsManager:
    def __init__(self, path=SETTINGS_FILE):
        self.path = Path(path)
        self.values = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self):
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key in DEFAULT_SETTINGS:
                    if key in loaded:
                        self.values[key] = loaded[key]
        except Exception:
            # Bad settings should reset to safe defaults instead of preventing the app from starting.
            self.values = dict(DEFAULT_SETTINGS)

    def save(self):
        self.path.write_text(
            json.dumps(self.values, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, key):
        return self.values.get(key, DEFAULT_SETTINGS.get(key))

    def update(self, **updates):
        self.values.update(updates)
        # Settings persist immediately so preview and normal mode stay aligned after a change.
        self.save()

    def is_paused(self):
        return time.time() < float(self.values.get("paused_until", 0.0) or 0.0)

    def pause_for_minutes(self, minutes):
        self.update(paused_until=time.time() + (minutes * 60))


# --- TextInterpreter normalizes multilingual keyboard intent before moderation decisions are made. ---
class TextInterpreter:
    @staticmethod
    def contains_latin(text):
        return any("a" <= char.lower() <= "z" for char in text)

    @staticmethod
    def contains_hebrew(text):
        return any("\u0590" <= char <= "\u05ff" for char in text)

    @staticmethod
    def truncate_text(text, limit=140):
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[:limit - 3].rstrip() + "..."

    def english_keyboard_to_hebrew(self, text):
        converted_chars = []
        for index, char in enumerate(text):
            converted = char.translate(ENGLISH_TO_HEBREW_TRANSLATION)
            next_char = text[index + 1] if index + 1 < len(text) else ""
            # A trailing period is preserved as punctuation so converted Hebrew sentences stay readable.
            if char == "." and (not next_char or next_char.isspace()):
                converted = "."
            converted_chars.append(converted)
        return "".join(converted_chars)

    def keyboard_layout_candidates(self, text, hebrew_support=True):
        candidates = [("Original typed text", text)]
        seen = {text}
        # All plausible layout candidates are kept so harmful intent is caught even when the keyboard layout was wrong.
        if hebrew_support and self.contains_latin(text):
            hebrew_guess = self.english_keyboard_to_hebrew(text)
            if hebrew_guess not in seen:
                candidates.append(("English keyboard, Hebrew intended", hebrew_guess))
                seen.add(hebrew_guess)
        if hebrew_support and self.contains_hebrew(text):
            english_guess = text.translate(HEBREW_TO_ENGLISH_TRANSLATION)
            if english_guess not in seen:
                candidates.append(("Hebrew keyboard, English intended", english_guess))
        return tuple(candidates)

    def language_scores(self, text):
        english_words = re.findall(r"[a-z']+", text.lower())
        hebrew_words = re.findall(r"[\u0590-\u05ff]+", text)
        # Known-word scoring chooses the most meaningful layout candidate without needing an AI call.
        english_score = sum(1 for word in english_words if word in ENGLISH_WORD_HINTS)
        hebrew_score = sum(1 for word in hebrew_words if word in HEBREW_WORD_HINTS)
        return english_score, hebrew_score

    def language_from_characters(self, text):
        if self.contains_hebrew(text) and not self.contains_latin(text):
            return "Hebrew"
        if self.contains_latin(text) and not self.contains_hebrew(text):
            return "English"
        return "Unknown"

    def interpret(self, text, hebrew_support=True):
        candidates = self.keyboard_layout_candidates(text, hebrew_support)
        best_label, best_text = candidates[0]
        best_language = self.language_from_characters(text)
        best_score = -1
        # The best interpretation is the candidate with the strongest recognizable-language signal.
        for label, value in candidates:
            english_score, hebrew_score = self.language_scores(value)
            score = max(english_score, hebrew_score)
            if hebrew_score > english_score:
                language = "Hebrew"
            elif english_score > hebrew_score:
                language = "English"
            else:
                language = self.language_from_characters(value)
            if score > best_score:
                best_label = label
                best_text = value
                best_language = language
                best_score = score
        return TextContext(
            raw_text=text,
            intended_text=best_text,
            intended_language=best_language,
            best_label=best_label,
            candidates=candidates,
            raw_length=len(text),
        )


# --- PopupTextFormatter keeps display truncation separate from the original message data. ---
class PopupTextFormatter:
    def __init__(self, interpreter=None):
        self.interpreter = interpreter or TextInterpreter()

    def label_text_options(self, text, limit):
        display_text = self.interpreter.truncate_text(text, limit)
        # Hebrew stays logical here because visual RTL fixes belong in the renderer, not in the stored text.
        if self.interpreter.contains_hebrew(display_text):
            return display_text, "right", "e"
        return display_text, "left", "w"

    def text_height_for(self, text, wrap_chars=48):
        return max(1, min(3, (len(text) // wrap_chars) + 1))


# --- LocalModerator provides deterministic safety rules that run before any network call. ---
class LocalModerator:
    def __init__(self, settings=None, interpreter=None):
        self.settings = settings or dict(DEFAULT_SETTINGS)
        self.interpreter = interpreter or TextInterpreter()

    def fallback_suggestion(self, language):
        if language == "Hebrew":
            return "אני כועס כרגע, אבל אני לא רוצה לפגוע."
        return "I'm upset right now, but I don't want to be hurtful."

    def evaluate(self, context):
        if not self.settings.get("local_rules", True):
            return None
        # Harmful intent wins over positive wording so mixed love/hate messages are never treated as safe.
        if self.contains_harmful_language(context):
            return ModerationResult(
                "HURTFUL",
                context.intended_language,
                1.0,
                self.fallback_suggestion(context.intended_language),
                "local_harmful",
            )
        if self.is_positive_safe(context):
            return ModerationResult("SAFE", context.intended_language, 1.0, "", "local_safe")
        return None

    def contains_harmful_language(self, context):
        texts_to_check = [
            context.raw_text,
            context.intended_text,
            *(value for _label, value in context.candidates),
        ]
        for text in texts_to_check:
            normalized = " ".join(text.lower().split())
            # Raw and converted candidates are checked so curses typed under the wrong keyboard layout are still caught.
            if self.has_term(normalized, ENGLISH_HARMFUL_TERMS, r"a-z"):
                return True
            if self.has_term(normalized, HEBREW_HARMFUL_TERMS, r"\u0590-\u05ff"):
                return True
        return False

    def is_positive_safe(self, context):
        if context.intended_language != "Hebrew":
            return False
        if self.contains_harmful_language(context):
            return False
        normalized = " ".join(context.intended_text.split())
        has_positive = self.has_term(normalized, HEBREW_POSITIVE_TERMS, r"\u0590-\u05ff")
        has_negative = self.has_term(normalized, HEBREW_NEGATIVE_INTENT_TERMS, r"\u0590-\u05ff")
        return has_positive and not has_negative

    @staticmethod
    def has_term(text, terms, alphabet_range):
        for term in terms:
            # Script-aware boundaries prevent matching harmful fragments inside unrelated words.
            pattern = rf"(?<![{alphabet_range}]){re.escape(term.lower())}(?![{alphabet_range}])"
            if re.search(pattern, text):
                return True
        return False


# --- AIResponseParser turns unstable model output into strict app-level moderation decisions. ---
class AIResponseParser:
    def __init__(self, interpreter=None, moderator=None):
        self.interpreter = interpreter or TextInterpreter()
        self.moderator = moderator or LocalModerator(interpreter=self.interpreter)

    def parse(self, content, language_hint, candidates):
        content = (content or "").strip()
        if not content:
            return self._fallback_result(language_hint)
        parsed = self._parse_json(content)
        if parsed:
            result = self._result_from_json(parsed, language_hint)
            if result:
                return result
        # Legacy parsing protects the app from non-JSON model output during provider drift.
        return self._parse_legacy_text(content, language_hint, candidates)

    def _parse_json(self, content):
        cleaned = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Extracting a JSON object keeps the parser resilient when a model ignores the strict-output prompt.
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if not match:
                return None
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

    def _result_from_json(self, parsed, language_hint):
        status = str(parsed.get("status", "")).upper().strip()
        replacement = str(parsed.get("replacement", "") or "").strip().strip("\"' :.,")
        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            # Invalid confidence is treated as low confidence so AI-only decisions remain conservative.
            confidence = 0.0
        if status == "SAFE":
            return ModerationResult("SAFE", language_hint, confidence, "", "ai_json")
        if status != "HURTFUL":
            return None
        # Wrong-language AI suggestions are rejected so the replacement matches the user's intended language.
        if not self._replacement_matches_language(replacement, language_hint):
            replacement = self.moderator.fallback_suggestion(language_hint)
        return ModerationResult("HURTFUL", language_hint, confidence, replacement, "ai_json")

    def _parse_legacy_text(self, content, language_hint, candidates):
        cleaned = content.strip().replace("\\n", "\n")
        cleaned = re.sub(r"^```(?:\w+)?|```$", "", cleaned, flags=re.MULTILINE).strip()
        cleaned = re.sub(r"(?i)^\s*(output|replacement|suggestion)\s*:\s*", "", cleaned).strip()
        if cleaned.upper() == "SAFE" or cleaned.upper().startswith("SAFE"):
            return ModerationResult("SAFE", language_hint, 0.75, "", "ai_legacy")
        candidate_values = {
            value.strip().strip("\"' :.,")
            for _label, value in candidates
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
            return self._fallback_result(language_hint)
        replacement = " ".join(lines).strip("\"' :.,")
        if language_hint == "Hebrew":
            # Parenthesized translations are stripped because the UI replacement must stay in one language.
            hebrew_lines = []
            for line in lines:
                no_translation = re.sub(r"\([^)]*[A-Za-z][^)]*\)", "", line).strip()
                no_translation = no_translation.strip("\"' :.,")
                if self.interpreter.contains_hebrew(no_translation) and no_translation not in candidate_values:
                    hebrew_lines.append(no_translation)
            replacement = " ".join(hebrew_lines).strip()
        if not self._replacement_matches_language(replacement, language_hint):
            replacement = self.moderator.fallback_suggestion(language_hint)
        return ModerationResult("HURTFUL", language_hint, 0.70, replacement, "ai_legacy")

    def _fallback_result(self, language_hint):
        return ModerationResult(
            "HURTFUL",
            language_hint,
            1.0,
            self.moderator.fallback_suggestion(language_hint),
            "fallback",
        )

    def _replacement_matches_language(self, replacement, language_hint):
        if not replacement:
            # Empty replacements are rejected because the popup cannot safely paste a missing suggestion.
            return False
        has_hebrew = self.interpreter.contains_hebrew(replacement)
        has_latin = self.interpreter.contains_latin(replacement)
        if language_hint == "Hebrew":
            return has_hebrew and not has_latin
        if language_hint == "English":
            return has_latin and not has_hebrew
        return True


# --- ReplacementPlanner separates what must be deleted from what should be pasted. ---
class ReplacementPlanner:
    @staticmethod
    def create_plan(context, replacement):
        # The plan keeps raw deletion length separate from the human-readable replacement.
        return ReplacementPlan(context.raw_text, context.raw_length, replacement)


# --- ReflectAIApp owns side effects including Tk windows, global hooks, clipboard, and API calls. ---
class ReflectAIApp:
    def __init__(self, preview=False, start_hooks=True):
        self.preview = preview
        self.root = tk.Tk()
        if preview:
            self.root.title("ReflectAI Preview")
        else:
            self.root.withdraw()
        self.ui_queue = queue.Queue()

        self.settings_manager = SettingsManager()
        self.interpreter = TextInterpreter()
        self.formatter = PopupTextFormatter(self.interpreter)
        self.moderator = LocalModerator(self.settings_manager.values, self.interpreter)
        self.ai_parser = AIResponseParser(self.interpreter, self.moderator)
        self.client = None
        if not preview:
            # Normal mode fails fast so the user never assumes protection is active when hooks or AI are missing.
            if keyboard is None:
                raise RuntimeError("The keyboard package is required to run ReflectAI normally.")
            if Groq is None:
                raise RuntimeError("The groq package is required to run ReflectAI normally.")
            if not CONFIG["GROQ_API_KEY"]:
                raise ValueError("Groq API Key is missing! Please make sure your .env file is set correctly.")
            self.client = Groq(api_key=CONFIG["GROQ_API_KEY"], timeout=8.0)

        self.current_buffer = ""
        self.is_processing = False
        self.shift_pressed = False
        self.ctrl_pressed = False
        self.alt_pressed = False
        self.loading_window = None
        self.loading_animation_after = None
        self.last_submit_time = 0
        self.popup_open = False
        self.last_processed_text = ""
        self.enter_hook = None
        
        self._setup_styles()

        if preview:
            self._show_preview_ui()
        elif start_hooks:
            self.listener_thread = threading.Thread(target=self._start_keyboard_listener, daemon=True)
            self.listener_thread.start()
            self.root.after(100, self._process_queue)
            print("--- ReflectAI Core Started ---")
            print("Listening for a safer digital world...")

    # --- Style helpers keep popup typography and controls consistent across preview and normal mode. ---
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
        # Helvetica keeps the UI usable on machines without the preferred Windows fonts.
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

    # --- Popup text helpers keep logical text intact while adapting rendering to English or Hebrew. ---
    def _label_text_options(self, text, limit):
        display_text = self._truncate_text(text, limit)
        # Hebrew data remains logical so downstream renderers can choose the safest visual strategy.
        if self._contains_hebrew(display_text):
            return display_text, "right", "e"
        return display_text, "left", "w"

    def _text_height_for(self, text, wrap_chars=48):
        return max(1, min(3, (len(text) // wrap_chars) + 1))

    def _hebrew_canvas_units(self, chunk, display_font):
        units = []
        for run in re.findall(r"[\u0590-\u05ff]+|[A-Za-z0-9']+|.", chunk):
            if self._contains_hebrew(run):
                # Small drawing units avoid Tkinter BiDi surprises without reversing the stored string.
                for char in run:
                    units.append((char, display_font.measure(char), True))
            else:
                units.append((run, display_font.measure(run), bool(run.strip())))
        return units

    def _wrap_hebrew_canvas_lines(self, text, display_font, max_width):
        chunks = re.findall(r"\S+", text.strip())
        if not chunks:
            return [([], 0)]

        max_width = max(1, int(max_width))
        space_width = display_font.measure(" ")
        lines = []
        current = []
        current_width = 0

        for chunk in chunks:
            chunk_units = self._hebrew_canvas_units(chunk, display_font)
            chunk_width = sum(width for _text, width, _visible in chunk_units)
            extra_width = chunk_width if not current else space_width + chunk_width

            if current and current_width + extra_width > max_width:
                # Wrapping by measured pixels preserves the popup layout better than character counts.
                lines.append((current, current_width))
                current = list(chunk_units)
                current_width = chunk_width
                continue

            if current:
                current.append((" ", space_width, False))
                current_width += space_width
            current.extend(chunk_units)
            current_width += chunk_width

        if current:
            lines.append((current, current_width))
        return lines

    def _add_hebrew_canvas_text(self, parent, display_text, display_font, bg, fg, wraplength, pady):
        line_height = max(1, display_font.metrics("linespace")) + 2
        canvas = tk.Canvas(
            parent,
            width=wraplength,
            height=line_height,
            bg=bg,
            relief="flat",
            bd=0,
            highlightthickness=0,
            takefocus=False
        )
        canvas.pack(anchor="e", fill="x", pady=pady)

        def _redraw(event=None):
            width = event.width if event else canvas.winfo_width()
            if width <= 1:
                width = wraplength

            # The render width is capped so Hebrew text keeps the same visual rhythm as English labels.
            render_width = min(width, wraplength)
            lines = self._wrap_hebrew_canvas_lines(display_text, display_font, render_width)
            height = max(line_height, line_height * len(lines))
            if int(canvas.cget("height")) != height:
                canvas.configure(height=height)
            canvas.delete("all")

            y = 0
            for tokens, _line_width in lines:
                x = width
                for token, token_width, visible in tokens:
                    if visible:
                        canvas.create_text(
                            x,
                            y,
                            text=token,
                            font=display_font,
                            fill=fg,
                            anchor="ne"
                        )
                    x -= token_width
                y += line_height

        canvas.bind("<Configure>", _redraw)
        canvas.after_idle(_redraw)
        return canvas

    def _add_readable_text(self, parent, text, display_font, bg, fg, wraplength, limit, pady=(4, 0)):
        display_text, justify, anchor = self._label_text_options(text, limit)
        if self._contains_hebrew(display_text):
            # Hebrew uses the canvas path because Tk Label/Text can reorder mixed RTL content unpredictably.
            return self._add_hebrew_canvas_text(parent, display_text, display_font, bg, fg, wraplength, pady)

        label = tk.Label(
            parent,
            text=display_text,
            font=display_font,
            bg=bg,
            fg=fg,
            wraplength=wraplength,
            justify=justify,
            anchor=anchor
        )
        label.pack(anchor=anchor, fill="x", pady=pady)
        return label

    # --- Legacy interpretation helpers remain as compatibility support for older fallback paths. ---
    def _contains_latin(self, text):
        return any(("a" <= char.lower() <= "z") for char in text)

    def _contains_hebrew(self, text):
        return any("\u0590" <= char <= "\u05ff" for char in text)

    def _english_keyboard_to_hebrew(self, text):
        converted_chars = []
        for index, char in enumerate(text):
            converted = char.translate(ENGLISH_TO_HEBREW_TRANSLATION)
            next_char = text[index + 1] if index + 1 < len(text) else ""

            # Trailing punctuation is preserved so converted Hebrew sentences do not end with an unintended letter.
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
            # Legacy bilingual output is filtered so Hebrew replacements do not carry English translations.
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

    # --- Window factory helpers keep all popup chrome consistent and easy to change. ---
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

    # --- Keyboard listener helpers maintain the outgoing draft without owning the active chat app. ---
    def _start_keyboard_listener(self):
        # Normal typing is observed passively while Enter is handled separately because it may need interception.
        keyboard.hook(self._handle_buffer_event)
        
        # The settings hotkey gives a recovery path without adding permanent UI chrome.
        keyboard.add_hotkey("ctrl+shift+comma", lambda: self.ui_queue.put(("settings", None)))
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

        preview_frame = tk.Frame(
            shell,
            bg=CONFIG["SURFACE_ALT"],
            padx=12,
            pady=10
        )
        preview_frame.pack(fill="x")
        self._add_readable_text(
            preview_frame,
            original_text,
            self.small_font,
            CONFIG["SURFACE_ALT"],
            CONFIG["MUTED_TEXT"],
            360,
            120,
            pady=(0, 0)
        )

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
                # Cleanup is best-effort because the popup may already be gone during rapid user actions.
                pass
            self.loading_window = None

    def _register_enter_hook(self):
        self.enter_hook = keyboard.on_press_key("enter", self._handle_enter_press, suppress=True)

    def _handle_buffer_event(self, event):
        if event.name in ('shift', 'left shift', 'right shift'):
            self.shift_pressed = (event.event_type == keyboard.KEY_DOWN)
            return
        if event.name in ('ctrl', 'left ctrl', 'right ctrl'):
            self.ctrl_pressed = (event.event_type == keyboard.KEY_DOWN)
            return
        if event.name in ('alt', 'left alt', 'right alt'):
            self.alt_pressed = (event.event_type == keyboard.KEY_DOWN)
            return

        if event.event_type != keyboard.KEY_DOWN:
            return

        # Tracking pauses during intervention because new keystrokes would no longer match the captured draft.
        if self.is_processing:
            return

        if self.ctrl_pressed or self.alt_pressed:
            self._handle_shortcut_key(event.name)
            return

        if event.name == 'backspace':
            self.current_buffer = self.current_buffer[:-1]
        elif event.name in ('delete', 'left', 'right', 'up', 'down', 'home', 'end', 'tab', 'esc'):
            # Cursor movement resets the buffer because future keystrokes may land in the middle of text.
            self.current_buffer = ""
        elif event.name == 'space':
            self.current_buffer += " "
        elif len(event.name) == 1:
            char = event.name
            if self.shift_pressed:
                if 'a' <= char <= 'z':
                    char = char.upper()
                shift_map = {'1':'!','2':'@','3':'#','4':'$','5':'%','6':'^','7':'&','8':'*','9':'(','0':')','-':'_','=':'+'}
                char = shift_map.get(char, char)
            self.current_buffer += char

    def _handle_shortcut_key(self, name):
        if name == 'a':
            self.current_buffer = ""
        elif name == 'v':
            try:
                # Clipboard paste is mirrored into the buffer so pasted drafts can still be moderated.
                pasted = self.root.clipboard_get()
                if pasted:
                    self.current_buffer += pasted
            except tk.TclError:
                self.current_buffer = ""
        elif name in ('x', 'delete', 'backspace'):
            self.current_buffer = ""

    def _handle_enter_press(self, event):
        now = time.time()

        if self.is_processing:
            return

        if now - self.last_submit_time < 0.4:
            return

        self.last_submit_time = now

        text_to_check = self.current_buffer.strip()
        # Tiny messages and paused periods pass through so ReflectAI does not block ordinary chat flow.
        if len(text_to_check) < CONFIG["MIN_TEXT_LENGTH"] or self.settings_manager.is_paused():
            self.current_buffer = ""
            self._send_enter_safely()
            return

        text_context = self.interpreter.interpret(
            text_to_check,
            hebrew_support=bool(self.settings_manager.get("hebrew_support")),
        )
        self.is_processing = True
        self.ui_queue.put(("loading", text_context.intended_text))
        threading.Thread(target=self._process_submission, args=(text_context,), daemon=True).start()

    def _send_enter_safely(self):
        if self.enter_hook is not None:
            keyboard.unhook(self.enter_hook)
        keyboard.send('enter')
        # The short delay prevents slower apps from feeding the synthetic Enter back into our hook.
        time.sleep(0.01)
        self._register_enter_hook()

    # --- AI moderation helpers keep remote model behavior behind a structured parser boundary. ---
    def _analyze_text(self, text_context):
        candidate_lines = "\n".join(f"- {label}: {value}" for label, value in text_context.candidates)
        # The prompt demands strict JSON so downstream code can validate confidence and replacement language.
        system_prompt = (
            "You are a child-safety text moderation engine. Return ONLY strict JSON with keys: "
            "status, language, confidence, replacement.\n"
            "status must be SAFE or HURTFUL. confidence is a number from 0 to 1.\n"
            "If status is SAFE, replacement must be an empty string.\n"
            "If status is HURTFUL, replacement must be a kinder message in the required language.\n"
            "Never include the original hurtful text, translations, markdown, or explanations.\n"
            "Hebrew insults/profanity such as זונה, בן זונה, שרמוטה, מפגר, סתום את הפה are HURTFUL when directed at a person.\n"
            "Positive Hebrew such as אני אוהב אותך אחי and תודה אחי אתה מלך is SAFE.\n"
            "If positive and harmful phrases both appear, classify as HURTFUL.\n"
        )
        user_prompt = (
            f"Original typed text: {text_context.raw_text}\n"
            f"Best interpretation to moderate: {text_context.intended_text}\n"
            f"Required replacement language: {text_context.intended_language}\n"
            f"Candidate interpretations:\n{candidate_lines}\n"
            "Return strict JSON now."
        )
        try:
            completion = self.client.chat.completions.create(
                model=CONFIG["MODEL_NAME"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=140,
            )
            content = completion.choices[0].message.content.strip()
            return self.ai_parser.parse(
                content,
                text_context.intended_language,
                text_context.candidates,
            )
        except Exception as e:
            # AI failures fall open because deterministic local rules already had a chance to intervene.
            print(f"Error: {e}")
            return ModerationResult("SAFE", text_context.intended_language, 0.0, "", "ai_error")

    def _legacy_analyze_text(self, text, text_context=None):
        text_context = text_context or self._interpret_text(text)
        intended_text = text_context["intended_text"]
        language_hint = text_context["intended_language"]
        candidates = text_context["candidates"]
        candidate_lines = "\n".join(f"- {label}: {value}" for label, value in candidates)

        # The legacy prompt is retained as a compatibility fallback while the JSON parser remains the main path.
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
            # Legacy cleanup strips filler because the old prompt allowed less structured model output.
            return self._clean_ai_response(content, language_hint, candidates)
        except Exception as e:
            print(f"Error: {e}")
            return "SAFE"

    # --- Submission and queue helpers bridge worker-thread moderation back into the Tk main thread. ---
    def _process_submission(self, text_context):
        if text_context.raw_text == self.last_processed_text:
            return

        self.last_processed_text = text_context.raw_text

        print(f"Analyzing: {text_context.intended_text}")
        local_result = self.moderator.evaluate(text_context)
        if local_result is not None:
            result = local_result
        else:
            result = self._analyze_text(text_context)

        if result.status == "HURTFUL" and local_result is None:
            threshold = float(self.settings_manager.get("confidence_threshold") or 0.70)
            # Local hits are trusted immediately while AI-only hits must satisfy the user's confidence threshold.
            if result.confidence < threshold:
                result = ModerationResult("SAFE", text_context.intended_language, result.confidence, "", "low_confidence")

        if result.status == "SAFE":
            self.ui_queue.put(("safe", None))
        else:
            replacement_plan = ReplacementPlanner.create_plan(text_context, result.replacement)
            print(f"Intervention triggered! Suggestion: {result.replacement}")
            self.ui_queue.put(("harmful", (text_context, result, replacement_plan)))

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
                text_context, result, replacement_plan = payload
                self._show_reflection_ui(text_context, result, replacement_plan)

            elif action == "settings":
                self._show_settings_ui()

        except queue.Empty:
            pass
        finally:
            # Background workers use this queue because Tkinter widgets must be touched only on the main thread.
            self.root.after(50, self._process_queue)

    # --- Reflection popup helpers handle the user-facing intervention and safe replacement flow. ---
    def _show_reflection_ui(self, text_context, result, replacement_plan):
        if self.popup_open:
            return

        self.popup_open = True
        top = self._create_popup_window("ReflectAI - Pause & Think", 560, 440)
        shell = self._make_shell(top, padx=14, pady=14)

        content = tk.Frame(shell, bg=CONFIG["SURFACE_COLOR"])
        content.pack(fill="both", expand=True)

        accent = tk.Frame(content, bg=CONFIG["DANGER_COLOR"], width=6)
        accent.pack(side="left", fill="y", padx=(0, 18))

        panel = tk.Frame(content, bg=CONFIG["SURFACE_COLOR"])
        panel.pack(side="left", fill="both", expand=True)

        # The button row is packed first at the bottom so longer text blocks cannot push actions off-screen.
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
        self._add_readable_text(
            original_frame,
            text_context.intended_text,
            self.small_font,
            CONFIG["DANGER_SOFT"],
            CONFIG["TEXT_COLOR"],
            410,
            110
        )

        suggest_frame = tk.Frame(panel, bg=CONFIG["ACCENT_COLOR"], padx=14, pady=10)
        suggest_frame.pack(anchor="w", fill="x")
        tk.Label(
            suggest_frame,
            text="Try this instead",
            font=self.kicker_font,
            bg=CONFIG["ACCENT_COLOR"],
            fg=CONFIG["TEXT_COLOR"]
        ).pack(anchor="w")
        self._add_readable_text(
            suggest_frame,
            replacement_plan.replacement_text,
            self.suggest_font,
            CONFIG["ACCENT_COLOR"],
            CONFIG["TEXT_COLOR"],
            410,
            150,
            pady=(5, 0)
        )

        def _use_suggest():
            self.popup_open = False
            self.last_processed_text = ""

            # Clipboard paste is preferred because it handles Hebrew text more reliably than simulated typing.
            clipboard_ready = False
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(replacement_plan.replacement_text)
                self.root.update()
                clipboard_ready = True
            except:
                clipboard_ready = False

            top.destroy()
            # Preview mode exercises the popup path without touching the user's active app or global keyboard state.
            if keyboard is None or self.preview:
                self.current_buffer = ""
                self.is_processing = False
                return

            time.sleep(0.35)

            keyboard.press_and_release('ctrl+end')
            time.sleep(0.05)
            # Deletion uses the captured raw length so layout interpretation stays separate from app automation.
            for _ in range(min(replacement_plan.raw_length, 500)):
                keyboard.press_and_release('backspace')
                time.sleep(0.004)

            time.sleep(0.08)
            if clipboard_ready:
                keyboard.press_and_release('ctrl+v')
            else:
                keyboard.write(replacement_plan.replacement_text)

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

    # --- Preview helpers provide a hook-free test harness for moderation and popup rendering. ---
    def _show_preview_ui(self):
        self.root.configure(bg=CONFIG["BG_COLOR"])
        self.root.geometry("760x520")

        # Preview mode reuses production rendering so RTL fixes can be tested without global hooks.
        frame = tk.Frame(self.root, bg=CONFIG["BG_COLOR"], padx=18, pady=18)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame,
            text="ReflectAI Preview",
            font=self.title_font,
            bg=CONFIG["BG_COLOR"],
            fg=CONFIG["TEXT_COLOR"],
        ).pack(anchor="w")

        tk.Label(
            frame,
            text="Test popup rendering and moderation helpers without global keyboard hooks.",
            font=self.body_font,
            bg=CONFIG["BG_COLOR"],
            fg=CONFIG["MUTED_TEXT"],
        ).pack(anchor="w", pady=(2, 14))

        raw_box = self._labeled_textbox(frame, "Original / raw text", 4)
        intended_box = self._labeled_textbox(frame, "Intended text", 3)
        suggestion_box = self._labeled_textbox(frame, "Suggested replacement", 3)
        suggestion_box.insert("1.0", "אני כועס כרגע, אבל אני לא רוצה לפגוע.")

        info_var = tk.StringVar(value="Ready.")
        tk.Label(
            frame,
            textvariable=info_var,
            font=self.small_font,
            bg=CONFIG["BG_COLOR"],
            fg=CONFIG["MUTED_TEXT"],
        ).pack(anchor="w", pady=(8, 0))

        button_row = tk.Frame(frame, bg=CONFIG["BG_COLOR"])
        button_row.pack(anchor="w", pady=(12, 0))

        def _get_text(widget):
            return widget.get("1.0", "end").strip()

        def _interpret():
            raw = _get_text(raw_box)
            context = self.interpreter.interpret(
                raw,
                hebrew_support=bool(self.settings_manager.get("hebrew_support")),
            )
            intended_box.delete("1.0", "end")
            intended_box.insert("1.0", context.intended_text)
            local_result = self.moderator.evaluate(context)
            local_status = local_result.status if local_result else "AI needed"
            info_var.set(
                f"Language: {context.intended_language} | Source: {context.best_label} | Local: {local_status}"
            )
            return context

        def _show_popup():
            context = _interpret()
            suggestion = _get_text(suggestion_box) or self.moderator.fallback_suggestion(context.intended_language)
            result = ModerationResult("HURTFUL", context.intended_language, 1.0, suggestion, "preview")
            plan = ReplacementPlanner.create_plan(context, suggestion)
            self._show_reflection_ui(context, result, plan)

        def _show_loading():
            context = _interpret()
            self._show_loading_ui(context.intended_text)
            self.root.after(1500, self._close_loading_ui)

        self._styled_button(button_row, "Interpret", _interpret).pack(side="left")
        self._styled_button(button_row, "Show Popup", _show_popup).pack(side="left", padx=(10, 0))
        self._styled_button(button_row, "Show Loading", _show_loading, variant="secondary").pack(side="left", padx=(10, 0))
        self._styled_button(button_row, "Settings", self._show_settings_ui, variant="secondary").pack(side="left", padx=(10, 0))

    def _labeled_textbox(self, parent, label, height):
        tk.Label(
            parent,
            text=label,
            font=self.kicker_font,
            bg=CONFIG["BG_COLOR"],
            fg=CONFIG["TEXT_COLOR"],
        ).pack(anchor="w")
        text_box = tk.Text(parent, height=height, wrap="word", font=self.body_font, relief="flat", padx=8, pady=8)
        text_box.pack(fill="x", pady=(4, 10))
        return text_box

    def _refresh_helpers(self):
        # Settings changes rebuild stateless helpers so future moderation uses the latest toggles.
        self.moderator = LocalModerator(self.settings_manager.values, self.interpreter)
        self.ai_parser = AIResponseParser(self.interpreter, self.moderator)

    # --- Settings UI helpers expose runtime safety controls without changing code. ---
    def _show_settings_ui(self):
        top = self._create_popup_window("ReflectAI Settings", 420, 360)
        shell = self._make_shell(top)

        tk.Label(
            shell,
            text="Settings",
            font=self.header_font,
            bg=CONFIG["SURFACE_COLOR"],
            fg=CONFIG["TEXT_COLOR"],
        ).pack(anchor="w")

        sensitivity = tk.StringVar(value=str(self.settings_manager.get("sensitivity")))
        hebrew_support = tk.BooleanVar(value=bool(self.settings_manager.get("hebrew_support")))
        local_rules = tk.BooleanVar(value=bool(self.settings_manager.get("local_rules")))
        # Tk variables mirror persisted settings so save can write the UI state directly.
        confidence = tk.DoubleVar(value=float(self.settings_manager.get("confidence_threshold") or 0.70))

        form = tk.Frame(shell, bg=CONFIG["SURFACE_COLOR"])
        form.pack(fill="x", pady=(14, 8))

        tk.Label(form, text="Sensitivity", font=self.body_font, bg=CONFIG["SURFACE_COLOR"], fg=CONFIG["TEXT_COLOR"]).pack(anchor="w")
        for value in ("conservative", "balanced", "strict"):
            tk.Radiobutton(
                form,
                text=value.title(),
                variable=sensitivity,
                value=value,
                bg=CONFIG["SURFACE_COLOR"],
                fg=CONFIG["TEXT_COLOR"],
                activebackground=CONFIG["SURFACE_COLOR"],
            ).pack(anchor="w")

        tk.Checkbutton(
            form,
            text="Hebrew support",
            variable=hebrew_support,
            bg=CONFIG["SURFACE_COLOR"],
            fg=CONFIG["TEXT_COLOR"],
            activebackground=CONFIG["SURFACE_COLOR"],
        ).pack(anchor="w", pady=(8, 0))

        tk.Checkbutton(
            form,
            text="Local safety rules",
            variable=local_rules,
            bg=CONFIG["SURFACE_COLOR"],
            fg=CONFIG["TEXT_COLOR"],
            activebackground=CONFIG["SURFACE_COLOR"],
        ).pack(anchor="w")

        tk.Label(
            form,
            text="AI confidence threshold",
            font=self.body_font,
            bg=CONFIG["SURFACE_COLOR"],
            fg=CONFIG["TEXT_COLOR"],
        ).pack(anchor="w", pady=(8, 0))
        tk.Scale(
            form,
            from_=0.40,
            to=0.95,
            resolution=0.05,
            orient="horizontal",
            variable=confidence,
            bg=CONFIG["SURFACE_COLOR"],
            highlightthickness=0,
        ).pack(fill="x")

        button_row = tk.Frame(shell, bg=CONFIG["SURFACE_COLOR"])
        button_row.pack(anchor="w", pady=(10, 0))

        def _save():
            # Saving closes the dialog only after helpers are refreshed with the new behavior.
            self.settings_manager.update(
                sensitivity=sensitivity.get(),
                hebrew_support=bool(hebrew_support.get()),
                local_rules=bool(local_rules.get()),
                confidence_threshold=float(confidence.get()),
            )
            self._refresh_helpers()
            top.destroy()

        def _pause():
            # Pause is persisted so restarting the app does not silently resume moderation early.
            self.settings_manager.pause_for_minutes(10)
            top.destroy()

        self._styled_button(button_row, "Save", _save).pack(side="left")
        self._styled_button(button_row, "Pause 10 min", _pause, variant="secondary").pack(side="left", padx=(10, 0))

    # --- App entry helpers keep command-line startup separate from application construction. ---
    def run(self):
        self.root.mainloop()

def main():
    # Preview mode is intentionally hook-free so UI/debug work cannot interfere with active apps.
    parser = argparse.ArgumentParser(description="ReflectAI")
    parser.add_argument("--preview", action="store_true", help="Open preview mode without keyboard hooks")
    args = parser.parse_args()
    app = ReflectAIApp(preview=args.preview, start_hooks=not args.preview)
    app.run()

if __name__ == "__main__":
    main()

