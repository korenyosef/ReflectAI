import requests
import threading
from pynput import keyboard

# הכתובת שקיבלת מקולאב - תחליף אותה!
SERVER_URL = "https://samiyah-nonsyntonic-shante.ngrok-free.dev/analyze"
current_text = ""


def send_to_ai(text):
    print(f"\n[נשלח לבדיקה]: {text}")
    try:
        # מוסיפים כותרת (Header) שמכריחה את ngrok לדלג על מסך האזהרה החינמי שלו
        headers = {"ngrok-skip-browser-warning": "true"}

        # שים לב שוב שה-SERVER_URL שלך נגמר ב /analyze !
        response = requests.post(SERVER_URL, json={"text": text}, headers=headers)

        # בודקים אם השרת החזיר שגיאה (כמו קוד 404 או 500)
        if not response.ok:
            print(f"[שגיאת שרת - קוד {response.status_code}]: {response.text}")
            return

        result = response.json()

        # מוודאים שהתשובה התקבלה כמו שצריך
        if 'raw_response' in result:
            print(f"[תשובת ה-AI]: {result['raw_response']}\n")
        else:
            print(f"[השרת החזיר משהו לא צפוי]: {result}")

    except Exception as e:
        print(f"[שגיאה כללית]: {e}")

def on_press(key):
    global current_text
    try:
        # אם הוקלדה אות או מספר
        if key.char:
            current_text += key.char
    except AttributeError:
        # טיפול במקשים מיוחדים
        if key == keyboard.Key.space:
            current_text += " "
        elif key == keyboard.Key.backspace:
            current_text = current_text[:-1] # מוחק את האות האחרונה
        elif key == keyboard.Key.enter:
            # ברגע שלוחצים אנטר, שולחים לשרת ומאפסים את משתנה הטקסט
            text_to_send = current_text.strip()
            if text_to_send:
                # מפעיל את השליחה בתהליך נפרד כדי שההקלדה לא תיתקע
                threading.Thread(target=send_to_ai, args=(text_to_send,)).start()
            current_text = ""

print("מתחיל להאזין למקלדת... הקלד טקסט ולחץ Enter. (כדי לעצור סגור את החלון)")

# הפעלת ההאזנה למקלדת
with keyboard.Listener(on_press=on_press) as listener:
    listener.join()