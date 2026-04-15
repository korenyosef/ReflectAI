import keyboard
import requests
import tkinter as tk
from tkinter import messagebox
import threading

# שים פה את הכתובת המעודכנת מהקולאב
API_URL = "https://samiyah-nonsyntonic-shante.ngrok-free.dev/analyze"
current_text = ""


def show_popup(analysis_result):
    """מקפיץ חלונית עם התוצאה"""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    messagebox.showwarning("ReflectAI - Think Before You Type! 🛑", analysis_result)
    root.destroy()


def check_text(text_to_check):
    """שולח את הטקסט לשרת בקולאב ומדפיס את התהליך"""
    print(f"\n⏳ שולח ל-AI לבדיקה: '{text_to_check}'...")
    try:
        # ההגדרות שעוקפות את החסימה של ngrok
        headers = {"ngrok-skip-browser-warning": "true"}

        # שלחנו את הבקשה עם הגבלת זמן של 30 שניות
        response = requests.post(API_URL, json={"text": text_to_check}, headers=headers, timeout=30)

        if response.status_code == 200:
            result = response.json().get("analysis", "")
            print(f"🤖 תשובת המודל: {result}")

            if result != "SAFE":
                print("🚨 המודל זיהה בעיה! מקפיץ התראה...")
                show_popup(result)
            else:
                print("✅ הכל טוב (SAFE), ממשיך להאזין ברקע.")
        else:
            print(f"❌ שגיאה מהשרת בקולאב! קוד: {response.status_code}")
            print(f"תוכן השגיאה: {response.text}")  # יוסיף לנו מידע מה קרה

    except requests.exceptions.Timeout:
        print("❌ עבר יותר מדי זמן (Timeout)! הקולאב לא עונה.")
    except Exception as e:
        print(f"❌ שגיאת התחברות: {e}")

def on_key_event(event):
    global current_text

    if event.event_type == keyboard.KEY_DOWN:
        # טריגר בדיקה: רק בלחיצה על Enter
        if event.name == 'enter':
            if len(current_text.strip()) > 3:
                text_to_send = current_text.strip()
                threading.Thread(target=check_text, args=(text_to_send,)).start()
            current_text = ""  # איפוס אחרי אנטר

        # בניית המשפט: רווח נחשב רק כרווח, לא שולח בקשה!
        elif event.name == 'space':
            current_text += " "
        elif event.name == 'backspace':
            current_text = current_text[:-1]
        elif len(event.name) == 1:  # תו רגיל
            current_text += event.name


print("ReflectAI is listening in the background... 👀")
print("נסה לכתוב משפט שלם וללחוץ *רק בסוף* על Enter.")
keyboard.hook(on_key_event)
keyboard.wait('esc')