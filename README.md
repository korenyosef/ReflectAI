# ReflectAI ✨

**Building Empathy, One Keystroke at a Time.**

ReflectAI is an intelligent background assistant designed to help children and young adults "Think Before They Type." Developed for the **Nitzanim 2026 Hackathon**, this tool acts as a gentle guardian against cyberbullying by detecting hurtful language in real-time and suggesting kinder alternatives.

## 🚀 Key Features

- **Real-Time Intervention:** Automatically intercepts the 'Enter' key when a potentially harmful message is detected.
- **AI-Powered Alternatives:** Uses Groq-hosted Llama 3.1 models to provide context-aware, kinder ways to express emotions.
- **Educational UI:** Features a modern, friendly interface that encourages reflection rather than just punishing negative behavior.
- **Seamless Integration:** Runs quietly in the background, compatible with most chat applications and browsers.

## 🧠 How it Works

1. **Listen:** The app monitors global keyboard input (locally and privately).
2. **Analyze:** Upon pressing 'Enter', the current line is securely analyzed by a fast-inference AI model.
3. **Reflect:** If the message is flagged as aggressive or hurtful, a "Reflection Prompt" appears.
4. **Learn:** The user can choose to adopt the AI's kinder suggestion or rewrite the message themselves, turning a moment of anger into a lesson in empathy.

## 🛠️ Tech Stack

- **Language:** Python 3.x
- **AI Inference:** [Groq](https://groq.com/) (Llama 3.1 8B)
- **Keyboard Handling:** `keyboard` library for global hooks and event suppression.
- **UI Framework:** `Tkinter` with custom styling for a modern look.
- **Concurrency:** Multi-threading to ensure the AI check doesn't freeze the user's computer.

## 💻 Installation & Setup

### Prerequisites

- Python 3.8+
- A Groq API Key (Get one at [console.groq.com](https://console.groq.com/))

### Steps

1. **Clone the repository:**

   ```bash
   git clone https://github.com/korenyosef/ReflectAI.git
   cd reflect-ai
   ```

2. **Install dependencies:**

   ```bash
   pip install keyboard groq
   ```

3. **Configure API Key:**
   Open `main.py` and replace the `GROQ_API_KEY` in the `CONFIG` section with your actual key, or set it as an environment variable.

4. **Run the application:**
   _(Note: Keyboard hooks usually require Administrator/Root privileges on Windows/Linux)_
   ```bash
   python main.py
   ```

## 🛡️ Privacy & Safety

ReflectAI is designed with privacy in mind. Text is only sent for analysis when the 'Enter' key is pressed, and no keystrokes are logged permanently or stored on any server.

---

_Created with ❤️ for Nitzanim 2026 Hackathon._
