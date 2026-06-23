# JARVIS — Windows Background AI Assistant

Runs **100% in the background**. No browser, no website.
Lives in your **system tray** (bottom-right corner of your taskbar).

---

## How It Works

1. Run `start_jarvis.bat` once → JARVIS starts silently
2. A small **cyan icon** appears in your system tray
3. Say **"Hey Jarvis"** anytime — from any app, any window
4. JARVIS responds via your speakers and acts on your PC
5. Right-click the tray icon for controls

---

## Quick Setup

### Step 1 — Install Python 3.11+
Download from https://python.org — check "Add to PATH"

### Step 2 — Install PyAudio (tricky on Windows)
```
pip install pipwin
pipwin install pyaudio
```

### Step 3 — Install Tesseract OCR
Download installer: https://github.com/UB-Mannheim/tesseract/wiki
Install to default path: `C:\Program Files\Tesseract-OCR\`

### Step 4 — Install all packages
```
pip install -r requirements.txt
```

### Step 5 — Add your OpenAI key
```
copy .env.example .env
notepad .env
```
Add your key: `OPENAI_API_KEY=sk-...`

### Step 6 — Run JARVIS
```
pythonw main.py
```
(`pythonw` = no console window at all)

---

## Auto-Start with Windows

To make JARVIS start automatically at login:

1. Press `Win + R` → type `shell:startup` → Enter
2. Copy a **shortcut** to `start_jarvis.bat` into that folder
3. Done — JARVIS now starts silently every time you log in

---

## Tray Icon Colors

| Color | Meaning |
|---|---|
| Cyan | Active, listening for "Hey Jarvis" |
| Green flash | Wake word detected |
| Red | Muted |

---

## Voice Commands

### Apps & PC
- "Hey Jarvis, open Chrome"
- "Hey Jarvis, open VS Code"
- "Hey Jarvis, take a screenshot"
- "Hey Jarvis, volume up"
- "Hey Jarvis, lock my screen"
- "Hey Jarvis, close this window"
- "Hey Jarvis, scroll down"

### Web (headless, no visible browser)
- "Hey Jarvis, search Python tutorials"
- "Hey Jarvis, open YouTube"  ← opens in your browser
- "Hey Jarvis, email me flight options"

### Vision & Screen
- "Hey Jarvis, what's on my screen?"
- "Hey Jarvis, read the text on screen"
- "Hey Jarvis, how many faces can you see?"
- "Hey Jarvis, what objects do you see?"

### Memory
- "Hey Jarvis, remember that my deadline is Friday"
- "Hey Jarvis, recall my deadline"
- "Hey Jarvis, memory stats"

### AI / Conversation
- "Hey Jarvis, what is machine learning?"
- "Hey Jarvis, write a Python function to sort a list"
- "Hey Jarvis, tell me a joke"

### Control
- "Hey Jarvis, mute yourself"
- "Hey Jarvis, unmute"

---

## File Structure

```
jarvis_desktop/
├── main.py               ← entry point
├── tray_app.py           ← system tray icon & menu
├── start_jarvis.bat      ← Windows launch script
├── .env                  ← your API keys (create from .env.example)
├── requirements.txt
├── agents/
│   ├── voice_agent.py    ← wake word, STT, TTS, OpenAI
│   ├── vision_agent.py   ← webcam, OCR, YOLO, MediaPipe
│   ├── automation_agent.py ← apps, mouse, keyboard, files
│   ├── web_agent.py      ← headless Chrome, search
│   ├── memory_agent.py   ← SQLite memory
│   ├── emotion_agent.py  ← mood detection
│   └── security_agent.py ← command safety
└── utils/
    ├── config.py         ← settings from .env
    └── logger.py         ← file + console logging
```

Memory is stored in `C:\Users\YOU\.jarvis\memory.db`
Logs are stored in `C:\Users\YOU\.jarvis\jarvis.log`
