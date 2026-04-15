import keyboard
import tkinter as tk
from tkinter import font
import threading
import os
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
    "THEME_COLOR": "#4a90e2",
    "BG_COLOR": "#f8f9fa",
    "ACCENT_COLOR": "#e1f5fe"
}

# נוודא שהמפתח אכן נטען בהצלחה לפני שהפרוייקט ממשיך לרוץ
if not CONFIG["GROQ_API_KEY"]:
    raise ValueError("Groq API Key is missing! Please make sure your .env file is set correctly.")

class ReflectAIApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.ui_queue = queue.Queue()
        
        self.client = Groq(api_key=CONFIG["GROQ_API_KEY"])
        self.current_buffer = ""
        self.is_processing = False
        self.shift_pressed = False
        
        self._setup_styles()
        
        # Start background listener
        self.listener_thread = threading.Thread(target=self._start_keyboard_listener, daemon=True)
        self.listener_thread.start()
        
        # Start polling the queue
        self.root.after(100, self._process_queue)
        
        print("--- ReflectAI Core Started ---")
        print("Listening for a safer digital world...")

    def _setup_styles(self):
        self.header_font = font.Font(family="Helvetica", size=14, weight="bold")
        self.body_font = font.Font(family="Helvetica", size=11)
        self.suggest_font = font.Font(family="Helvetica", size=11, slant="italic")

    def _start_keyboard_listener(self):
        """Initializes global hooks for buffer tracking and Enter suppression."""
        # 1. Global hook for buffer tracking (does NOT suppress keys)
        keyboard.hook(self._handle_buffer_event)
        
        # 2. Specific aggressive hook for Enter suppression
        self._register_enter_hook()
        
        keyboard.wait()

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
        """Triggered when Enter is pressed. Suppresses the key and starts analysis."""
        if self.is_processing:
            return

        text_to_check = self.current_buffer.strip()
        if len(text_to_check) < CONFIG["MIN_TEXT_LENGTH"]:
            self.current_buffer = ""
            self._send_enter_safely()
            return

        self.is_processing = True
        threading.Thread(target=self._process_submission, args=(text_to_check,), daemon=True).start()

    def _send_enter_safely(self):
        """Releases a single Enter key by temporarily unhooking suppression."""
        keyboard.unhook(self.enter_hook)
        keyboard.send('enter')
        # Tiny delay to ensure the key is processed before re-hooking
        time.sleep(0.01)
        self._register_enter_hook()

    def _analyze_text(self, text):
        """Analyze text via Groq and return 'SAFE' or a kinder alternative."""
        system_prompt = (
            "You are an advanced text-moderation engine for a child-safety application. "
            "Your task is to analyze user input and decide if it is SAFE or HURTFUL.\n\n"
            "DEFINITIONS:\n"
            "- SAFE: Normal everyday conversation, gaming slang (e.g., 'noob', 'bot'), mild annoyance, jokes, complaints about a situation (e.g., 'this game is stupid'), or neutral statements. When in doubt, lean heavily towards SAFE to avoid false positives.\n"
            "- HURTFUL: Direct bullying, severe personal insults, profanity, racism, threats, telling someone to harm themselves, or extreme aggression directed at a person.\n\n"
            "CORE DIRECTIVES:\n"
            "1. If the input is SAFE, output ONLY the exact word: SAFE\n"
            "2. If the input is HURTFUL, output ONLY a kinder, respectful replacement.\n"
            "3. PRESERVE MEANING: The replacement should convey the original intent but politely. If the original intent is purely malicious (e.g., 'go die', 'you are ugly'), output a neutral boundary like 'I need to take a break from this conversation.' or 'Please don't speak to me like that.'\n"
            "4. NO FILLER: Do not explain, do not use quotes, do not say 'Here is a replacement:'. Just output the final string.\n\n"
            "EXAMPLES:\n"
            "Input: 'Want to play?'\n"
            "Output: SAFE\n\n"
            "Input: 'you are an absolute idiot and I hate you'\n"
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
                    {"role": "user", "content": f"Input: '{text}'\nOutput:"}
                ],
                temperature=0.0,
                max_tokens=100
            )
            content = completion.choices[0].message.content.strip()
            # מנקה מרכאות או תווים מיותרים שהמודל עלול לפלוט בטעות
            return content.strip("\"' :.,")
        except Exception as e:
            print(f"Error: {e}")
            return "SAFE"

    def _process_submission(self, text):
        """Workflow for analyzing and responding to a message submission."""
        print(f"🔍 Analyzing: {text}")
        result = self._analyze_text(text)
        
        if result.upper() == "SAFE" or result.upper().startswith("SAFE"):
            self.current_buffer = ""
            self._send_enter_safely()
            self.is_processing = False
        else:
            print(f"🚨 Intervention triggered! Suggestion: {result}")
            self.ui_queue.put((text, result))

    def _process_queue(self):
        """Poll the queue for UI requests."""
        try:
            msg = self.ui_queue.get_nowait()
            original, suggestion = msg
            self._show_reflection_ui(original, suggestion)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_queue)

    def _show_reflection_ui(self, original, suggestion):
        """Displays the custom popup UI."""
        top = tk.Toplevel(self.root)
        top.title("ReflectAI - Pause & Think 💡")
        top.geometry("450x300")
        top.configure(bg=CONFIG["BG_COLOR"])
        top.attributes("-topmost", True)
        top.resizable(False, False)
        
        # Center Window
        x = (top.winfo_screenwidth() // 2) - 225
        y = (top.winfo_screenheight() // 2) - 150
        top.geometry(f"450x300+{x}+{y}")
        top.focus_force()

        header = tk.Label(top, text="Wait a second! 🛑", font=self.header_font, fg=CONFIG["THEME_COLOR"], bg=CONFIG["BG_COLOR"], pady=10)
        header.pack()

        subtext = tk.Label(top, text="That sounded a bit harsh. Would you like to try this instead?", font=self.body_font, bg=CONFIG["BG_COLOR"], wraplength=400)
        subtext.pack(pady=5)

        suggest_frame = tk.Frame(top, bg=CONFIG["ACCENT_COLOR"], padx=15, pady=15)
        suggest_frame.pack(pady=15, fill="x", padx=30)
        
        suggest_label = tk.Label(suggest_frame, text=f'"{suggestion}"', font=self.suggest_font, bg=CONFIG["ACCENT_COLOR"], wraplength=350, fg="#0277bd")
        suggest_label.pack()

        btn_frame = tk.Frame(top, bg=CONFIG["BG_COLOR"])
        btn_frame.pack(pady=10)

        def _use_suggest():
            top.destroy()
            time.sleep(0.3)
            
            # 1. Surgical deletion: End -> Shift+Home -> Backspace
            keyboard.press_and_release('end')
            time.sleep(0.1)
            keyboard.press('shift')
            keyboard.press_and_release('home')
            keyboard.release('shift')
            time.sleep(0.1)
            keyboard.press_and_release('backspace')
            time.sleep(0.1)

            # 2. Paste via Clipboard
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(suggestion)
                self.root.update()
                time.sleep(0.1)
                keyboard.press_and_release('ctrl+v')
            except:
                keyboard.write(suggestion)
            
            # 3. Finalize and Send
            time.sleep(0.1)
            self.current_buffer = ""
            self._send_enter_safely()
            self.is_processing = False

        def _retry():
            top.destroy()
            self.current_buffer = ""
            self.is_processing = False

        tk.Button(btn_frame, text="Use Suggestion ✅", command=_use_suggest, bg=CONFIG["THEME_COLOR"], fg="white", font=("Helvetica", 10, "bold"), padx=15, pady=8).pack(side="left", padx=10)
        tk.Button(btn_frame, text="I'll rewrite it myself ✏️", command=_retry, bg="#cfd8dc", fg="#37474f", font=("Helvetica", 10), padx=15, pady=8).pack(side="left", padx=10)
        
        top.protocol("WM_DELETE_WINDOW", _retry)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = ReflectAIApp()
    app.run()
