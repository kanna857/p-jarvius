"""JARVIS Config — reads from .env"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

class Config:
    OPENAI_API_KEY:      str  = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL:        str  = os.getenv("OPENAI_MODEL", "llama-3.3-70b-versatile")
    GROQ_API_KEY:        str  = os.getenv("GROQ_API_KEY", "")
    GROK_API_KEY:        str  = os.getenv("GROK_API_KEY", "")
    GEMINI_API_KEY:      str  = os.getenv("GEMINI_API_KEY", "")
    OPENAI_GPT_KEY:      str  = os.getenv("OPENAI_GPT_KEY", "")
    DEEPSEEK_API_KEY:    str  = os.getenv("DEEPSEEK_API_KEY", "")

    # ── Ollama (local, offline AI) ────────────────────────
    OLLAMA_ENABLED:      bool = os.getenv("OLLAMA_ENABLED", "false").lower() == "true"
    OLLAMA_MODEL:        str  = os.getenv("OLLAMA_MODEL", "llama3.2")
    OLLAMA_BASE_URL:     str  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

    USE_ELEVENLABS:      bool = os.getenv("USE_ELEVENLABS", "false").lower() == "true"
    ELEVENLABS_API_KEY:  str  = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str  = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

    WAKE_WORD:           str  = os.getenv("WAKE_WORD", "hey jarvis")
    CAMERA_INDEX:        int  = int(os.getenv("CAMERA_INDEX", "0"))
    VISION_ENABLED:      bool = os.getenv("VISION_ENABLED", "true").lower() == "true"
    BROWSER_HEADLESS:    bool = True   # always headless in desktop mode
    WEATHER_API_KEY:     str  = os.getenv("WEATHER_API_KEY", "")
    NEWS_API_KEY:        str  = os.getenv("NEWS_API_KEY", "")
    CRICKET_API_KEY:     str  = os.getenv("CRICKET_API_KEY", "")

    EMAIL_ADDRESS:       str  = os.getenv("EMAIL_ADDRESS", "")
    EMAIL_APP_PASSWORD:  str  = os.getenv("EMAIL_APP_PASSWORD", "")
