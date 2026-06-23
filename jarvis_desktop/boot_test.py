"""Quick boot test — checks all Jarvis systems without hiding the console."""
import sys, os, queue, time
sys.path.insert(0, os.getcwd())

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from utils.config import Config

print("=" * 55)
print("  JARVIS BOOT TEST")
print("=" * 55)

config = Config()
print(f"\n[Config]")
print(f"  Ollama enabled : {config.OLLAMA_ENABLED}")
print(f"  Ollama model   : {config.OLLAMA_MODEL}")
print(f"  Ollama URL     : {config.OLLAMA_BASE_URL}")

print(f"\n[VoiceAgent] Initializing...")
from agents.voice_agent import VoiceAgent
q = queue.Queue()
v = VoiceAgent(q, config)

print(f"\n[Status]")
print(f"  Brain provider : {v.provider.upper()}")
print(f"  AI model       : {v.config.OPENAI_MODEL}")
print(f"  Groq cloud     : {'connected' if v.groq_client else 'not configured'}")
print(f"  TTS mode       : {v._tts_mode}")

print(f"\n[STT Models] Waiting for background load (6s)...")
time.sleep(6)
fw_ok = getattr(v, 'fw_available', False)
vosk_ok = getattr(v, 'vosk_available', False)
print(f"  faster-whisper : {'OK loaded' if fw_ok else 'loading / not installed'}")
print(f"  Vosk           : {'OK loaded' if vosk_ok else 'loading / not installed'}")

print(f"\n[Ollama] Testing connection...")
try:
    resp = v.client.chat.completions.create(
        model=config.OLLAMA_MODEL,
        messages=[{"role": "user", "content": "Say exactly: JARVIS online."}],
        max_tokens=20,
    )
    reply = resp.choices[0].message.content.strip()
    print(f"  Response : {reply}")
    print(f"  Ollama   : WORKING OK")
except Exception as e:
    print(f"  Ollama   : ERROR - {e}")

print("\n" + "=" * 55)
print("  BOOT TEST COMPLETE")
print("=" * 55)
v.stop()
