"""
Voice Agent — FAST Edition
- Streaming mic with energy-based VAD (no wasted silence)
- Wake word: "Hey Jarvis"
- Google STT for transcription
- pyttsx3 (offline) or ElevenLabs TTS
- Claude Haiku / OpenAI for speed
"""

import queue
import time
import threading
import io
import wave
import numpy as np
import sounddevice as sd
import speech_recognition as sr
import pyttsx3
from utils.logger import JarvisLogger
from utils.config import Config


class VoiceAgent:
    # ── VAD tuning ────────────────────────────────────────
    SAMPLE_RATE = 16000
    CHANNELS = 1
    CHUNK_SEC = 0.10           # duration of each mic chunk
    ENERGY_THRESHOLD = 800     # RMS above this = speech (increased to prevent false noise triggers)
    SILENCE_AFTER = 1.2        # seconds of silence to end recording
    PRE_BUFFER_N = 5           # chunks kept before speech starts

    def __init__(self, command_queue: queue.Queue, config: Config):
        self.command_queue = command_queue
        self.config = config
        self.logger = JarvisLogger("Voice")
        self.recognizer = sr.Recognizer()
        self._stop = threading.Event()
        self.tts_queue = queue.Queue()
        self.is_speaking = threading.Event()
        self.on_wake = None

        import openai
        self.client_type = "openai"
        cloud_api_key = config.OPENAI_API_KEY
        cloud_model   = config.OPENAI_MODEL

        # ── Primary brain ──────────────────
        if config.OLLAMA_ENABLED:
            self.provider = "ollama"
            self.client = openai.OpenAI(
                api_key="ollama",                    # ignored by Ollama server
                base_url=config.OLLAMA_BASE_URL,
            )
            self.config.OPENAI_MODEL = config.OLLAMA_MODEL
            self.logger.info(f"Initializing Ollama local brain ({config.OLLAMA_MODEL}) at {config.OLLAMA_BASE_URL}...")
        elif cloud_api_key.startswith("xai-") or (config.GROK_API_KEY and config.GROK_API_KEY.startswith("xai-")):
            self.provider = "grok"
            key = config.GROK_API_KEY if config.GROK_API_KEY.startswith("xai-") else cloud_api_key
            if not cloud_model or any(k in cloud_model.lower() for k in ("gpt", "llama", "gemini")):
                cloud_model = "grok-2-1212"
            self.client = openai.OpenAI(
                api_key=key,
                base_url="https://api.x.ai/v1",
            )
            self.config.OPENAI_MODEL = cloud_model
            self.logger.info(f"Initializing xAI Grok client ({cloud_model})...")
        elif cloud_api_key.startswith("AIza") or cloud_api_key.startswith("AQ."):      # Gemini
            self.provider = "gemini"
            if not cloud_model or "gemini" not in cloud_model.lower():
                cloud_model = "gemini-1.5-flash"
            self.client = openai.OpenAI(
                api_key=cloud_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
            self.config.OPENAI_MODEL = cloud_model
            self.logger.info("Initializing Google Gemini client...")
        elif cloud_api_key.startswith("sk-") and not cloud_api_key.startswith("sk-ant-"):  # OpenAI
            self.provider = "openai"
            if not cloud_model or "gpt" not in cloud_model.lower():
                cloud_model = "gpt-4o-mini"
            self.client = openai.OpenAI(api_key=cloud_api_key)
            self.config.OPENAI_MODEL = cloud_model
            self.logger.info("Initializing OpenAI client...")
        else:                                        # Groq / fallback
            self.provider = "groq"
            key = config.GROQ_API_KEY if config.GROQ_API_KEY.startswith("gsk_") else cloud_api_key
            if not cloud_model or not any(k in cloud_model.lower() for k in ("llama", "mixtral", "gemma")):
                cloud_model = "llama-3.3-70b-versatile"
            self.client = openai.OpenAI(
                api_key=key,
                base_url="https://api.groq.com/openai/v1",
            )
            self.config.OPENAI_MODEL = cloud_model
            self.logger.info("Initializing Groq client...")

        self.logger.success(f"Primary brain: {self.provider.upper()} ({self.config.OPENAI_MODEL})")

        # ── Cloud brains for routing complex queries ──
        self.grok_client = None
        self.grok_model  = "grok-3-mini"  # Updated from deprecated grok-2-1212
        grok_key = config.GROK_API_KEY if config.GROK_API_KEY else (cloud_api_key if cloud_api_key.startswith("xai-") else "")
        if grok_key and grok_key.startswith("xai-"):
            try:
                self.grok_client = openai.OpenAI(
                    api_key=grok_key,
                    base_url="https://api.x.ai/v1",
                )
                self.logger.success(f"Cloud brain: GROK ({self.grok_model}) — ready for complex queries")
            except Exception as ge:
                self.logger.warning(f"Grok cloud brain init failed: {ge}")

        self.groq_client       = None
        self.groq_model        = "llama-3.3-70b-versatile"
        groq_key = config.GROQ_API_KEY if config.GROQ_API_KEY else (cloud_api_key if cloud_api_key.startswith("gsk_") else "")
        if groq_key and groq_key.startswith("gsk_"):
            try:
                self.groq_client = openai.OpenAI(
                    api_key=groq_key,
                    base_url="https://api.groq.com/openai/v1",
                )
                self.logger.success(f"Cloud brain: GROQ ({self.groq_model}) — ready for complex queries")
            except Exception as ge:
                self.logger.warning(f"Groq cloud brain init failed: {ge}")
        else:
            self.logger.info("No Groq key found — complex queries will stay on local brain.")

        self.openai_client = None
        openai_key = config.OPENAI_GPT_KEY if config.OPENAI_GPT_KEY else (cloud_api_key if (cloud_api_key.startswith("sk-") and not cloud_api_key.startswith("sk-ant-")) else "")
        if openai_key and openai_key.startswith("sk-"):
            try:
                self.openai_client = openai.OpenAI(api_key=openai_key)
                self.logger.success("Cloud brain: OPENAI (gpt-4o-mini) — ready for complex queries")
            except Exception as e:
                self.logger.warning(f"OpenAI cloud brain init failed: {e}")

        self.gemini_client = None
        gemini_key = config.GEMINI_API_KEY if config.GEMINI_API_KEY else (cloud_api_key if (cloud_api_key.startswith("AIza") or cloud_api_key.startswith("AQ.")) else "")
        if gemini_key:
            try:
                self.gemini_client = openai.OpenAI(
                    api_key=gemini_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                )
                self.logger.success("Cloud brain: GEMINI (gemini-1.5-flash) — ready for complex queries")
            except Exception as e:
                self.logger.warning(f"Gemini cloud brain init failed: {e}")

        self.deepseek_client = None
        deepseek_key = config.DEEPSEEK_API_KEY if config.DEEPSEEK_API_KEY else ""
        if deepseek_key:
            try:
                self.deepseek_client = openai.OpenAI(
                    api_key=deepseek_key,
                    base_url="https://api.deepseek.com/v1",
                )
                self.logger.success("Cloud brain: DEEPSEEK — ready for complex queries")
            except Exception as e:
                self.logger.warning(f"DeepSeek cloud brain init failed: {e}")

        self.conversation_history = []
        self._init_tts()
        threading.Thread(target=self._init_faster_whisper, daemon=True).start()
        threading.Thread(target=self._init_vosk, daemon=True).start()
        threading.Thread(target=self._tts_worker, daemon=True).start()
        
        wake_env = config.WAKE_WORD.lower()
        self.wake_words = [wake_env]
        if "hey jarvis" not in self.wake_words: self.wake_words.append("hey jarvis")
        if "jarvis" not in self.wake_words: self.wake_words.append("jarvis")
        self.wake_words.sort(key=len, reverse=True)
        
        self.logger.success("Voice agent ready — Hybrid brain mode active (Local + Cloud routing)")

    # ── TTS ───────────────────────────────────────

    def _init_tts(self):
        # Priority 1: ElevenLabs (premium cloud voice)
        if self.config.USE_ELEVENLABS:
            try:
                from elevenlabs import ElevenLabs
                self.el = ElevenLabs(api_key=self.config.ELEVENLABS_API_KEY)
                self._tts_mode = "elevenlabs"
                self.logger.success("ElevenLabs TTS loaded")
                return
            except Exception as e:
                self.logger.warning(f"ElevenLabs failed ({e}), falling back")

        # Priority 2: Edge-TTS (Microsoft neural voice — free, natural-sounding)
        try:
            import edge_tts
            self._tts_mode = "edge_tts"
            self._edge_voice = getattr(self.config, 'EDGE_TTS_VOICE', 'en-US-GuyNeural')
            self.logger.success(f"Edge-TTS neural voice loaded ({self._edge_voice})")
            return
        except ImportError:
            self.logger.warning("edge-tts not installed, falling back to pyttsx3")

        # Priority 3: pyttsx3 (offline Windows SAPI voices)
        self._tts_mode = "pyttsx3"

    def _init_faster_whisper(self):
        """Load faster-whisper for high-accuracy offline speech recognition."""
        try:
            from faster_whisper import WhisperModel
            # 'base' model: ~145MB, ~10x faster than original Whisper, runs on CPU
            # Upgrade to 'small' or 'medium' if you have a GPU for even better accuracy
            fw_model_size = getattr(self.config, 'FASTER_WHISPER_MODEL', 'base')
            self.fw_model = WhisperModel(fw_model_size, device="cpu", compute_type="int8")
            self.fw_available = True
            self.logger.success(f"faster-whisper STT loaded (model: {fw_model_size}) — high accuracy offline")
        except ImportError:
            self.fw_available = False
            self.logger.warning("faster-whisper not installed — will use Vosk/Google STT instead")
        except Exception as e:
            self.fw_available = False
            self.logger.warning(f"faster-whisper load failed: {e}")

    def _init_vosk(self):
        try:
            # pyrefly: ignore [missing-import]
            import vosk
            from pathlib import Path
            import zipfile
            import urllib.request
            
            model_dir = Path.home() / ".jarvis" / "vosk"
            model_path = model_dir / "vosk-model-small-en-us-0.15"
            
            if not model_path.exists():
                self.logger.info("Downloading small Vosk offline language model (40MB)...")
                model_dir.mkdir(parents=True, exist_ok=True)
                zip_path = model_dir / "model.zip"
                
                url = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
                urllib.request.urlretrieve(url, zip_path)
                
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(model_dir)
                zip_path.unlink()
                self.logger.success("Vosk offline model ready.")
                
            self.vosk_model = vosk.Model(str(model_path))
            self.vosk_available = True
            self.logger.success("Offline Vosk STT loaded (fallback)")
        except Exception as e:
            self.logger.warning(f"Failed to load Vosk offline STT: {e}")
            self.vosk_available = False

    def _play_mp3_native(self, filename: str):
        import ctypes
        import time
        import os
        winmm = ctypes.windll.winmm
        abs_path = os.path.abspath(filename)
        short_buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.kernel32.GetShortPathNameW(abs_path, short_buf, 512)
        short_path = short_buf.value
        
        winmm.mciSendStringW(f"open \"{short_path}\" type mpegvideo alias mymp3", None, 0, 0)
        winmm.mciSendStringW("play mymp3", None, 0, 0)
        
        status = ctypes.create_unicode_buffer(256)
        while not self._stop.is_set():
            winmm.mciSendStringW("status mymp3 mode", status, 256, 0)
            if status.value != "playing":
                break
            time.sleep(0.05)
            
        winmm.mciSendStringW("close mymp3", None, 0, 0)

    def _tts_worker(self):
        if self._tts_mode == "elevenlabs":
            import tempfile
            import os
            while not self._stop.is_set():
                try:
                    text = self.tts_queue.get(timeout=0.5)
                    self.is_speaking.set()
                    self.logger.info(f"Speaking: {text[:80]}")
                    audio = self.el.text_to_speech.convert(
                        voice_id=self.config.ELEVENLABS_VOICE_ID, text=text)
                    
                    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                    tmp.write(b"".join(audio))
                    tmp.close()
                    try:
                        self._play_mp3_native(tmp.name)
                    finally:
                        try:
                            os.unlink(tmp.name)
                        except Exception:
                            pass
                except queue.Empty:
                    pass
                except Exception as e:
                    self.logger.error(f"ElevenLabs TTS error: {e}")
                finally:
                    self.is_speaking.clear()

        elif self._tts_mode == "edge_tts":
            # Microsoft Edge neural TTS — async generation, sync playback via native winmm
            import asyncio
            import tempfile
            import os

            async def _synth(text: str, voice: str, out_path: str):
                import edge_tts
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(out_path)

            while not self._stop.is_set():
                try:
                    text = self.tts_queue.get(timeout=0.5)
                    self.is_speaking.set()
                    self.logger.info(f"Speaking [Edge-TTS]: {text[:80]}")
                    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                    tmp.close()
                    try:
                        asyncio.run(_synth(text, self._edge_voice, tmp.name))
                        self._play_mp3_native(tmp.name)
                    finally:
                        try:
                            os.unlink(tmp.name)
                        except Exception:
                            pass
                except queue.Empty:
                    pass
                except Exception as e:
                    self.logger.error(f"Edge-TTS error: {e} — falling back to pyttsx3")
                    # One-shot pyttsx3 fallback for this utterance
                    try:
                        import pyttsx3, pythoncom
                        pythoncom.CoInitialize()
                        fb = pyttsx3.init()
                        fb.say(text)
                        fb.runAndWait()
                        pythoncom.CoUninitialize()
                    except Exception:
                        pass
                finally:
                    self.is_speaking.clear()

        else:  # pyttsx3 fallback
            import pyttsx3
            import pythoncom
            pythoncom.CoInitialize()
            local_tts = pyttsx3.init()
            local_tts.setProperty("rate", 185)
            # Prefer a clear, natural-sounding Windows voice
            preferred = ("david", "mark", "zira", "james", "george")
            for v in local_tts.getProperty("voices"):
                if any(n in v.name.lower() for n in preferred):
                    local_tts.setProperty("voice", v.id)
                    break
            
            while not self._stop.is_set():
                try:
                    text = self.tts_queue.get(timeout=0.5)
                    self.is_speaking.set()
                    self.logger.info(f"Speaking [pyttsx3]: {text[:80]}")
                    local_tts.say(text)
                    local_tts.runAndWait()
                except queue.Empty:
                    pass
                except Exception as e:
                    self.logger.error(f"TTS error: {e}")
                finally:
                    self.is_speaking.clear()
            pythoncom.CoUninitialize()

    def speak(self, text: str):
        """Speak text aloud — non-blocking via queue"""
        # Sanitize text to prevent TTS engine from hanging on special characters
        import re
        clean_text = text.replace('\n', ' ').replace('\r', ' ')
        clean_text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', 'a link', clean_text)
        
        self.tts_queue.put(clean_text)

    def stream_to_speech(self, prompt: str, model: str = None,
                         system: str = None, memory: list = None) -> str:
        """
        Groq streaming → sentence-by-sentence TTS pipeline.

        How it works:
          1. Opens a Groq streaming call (stream=True)
          2. Accumulates token chunks into a text buffer
          3. When a sentence boundary is detected (. ! ? newline),
             immediately calls self.speak(sentence) — voice starts in ~200ms
          4. Returns the full assembled response text for memory/logging

        Falls back to regular ask_ai() if Groq is unavailable.
        """
        import re

        # Sentence boundary pattern
        SENTENCE_END = re.compile(r'(?<=[.!?])\s+|(?<=\n)')

        if not self.groq_client:
            # Fallback: single blocking call
            result = self.ask_ai(prompt, short_term_memory=memory)
            self.speak(result)
            return result

        use_model = model or "llama-3.3-70b-versatile"

        msgs = [{"role": "system", "content": system or
                 "You are JARVIS, a helpful Windows AI assistant. Be concise and natural."}]
        if memory:
            msgs += memory[-10:]
        msgs.append({"role": "user", "content": prompt})

        buffer   = ""
        full_text = ""

        try:
            stream = self.groq_client.chat.completions.create(
                model=use_model,
                messages=msgs,
                max_tokens=600,
                temperature=0.7,
                stream=True,
            )

            for chunk in stream:
                delta = chunk.choices[0].delta
                token = getattr(delta, "content", None) or ""
                if not token:
                    continue

                buffer    += token
                full_text += token

                # Speak complete sentences immediately
                parts = SENTENCE_END.split(buffer)
                if len(parts) > 1:
                    # Everything except the last (incomplete) fragment
                    for sentence in parts[:-1]:
                        sentence = sentence.strip()
                        if sentence:
                            self.speak(sentence)
                    buffer = parts[-1]   # keep remainder for next iteration

            # Speak any remaining text in buffer
            if buffer.strip():
                self.speak(buffer.strip())

            self.logger.info(f"[Stream] Full response assembled ({len(full_text)} chars)")
            return full_text.strip()

        except Exception as e:
            self.logger.warning(f"Streaming failed ({e}), falling back to single call")
            result = self.ask_ai(prompt, short_term_memory=memory)
            self.speak(result)
            return result



    @staticmethod
    def _rms(chunk: np.ndarray) -> float:
        return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))

    def _record_vad(self, max_secs: float = 6.0) -> np.ndarray | None:
        """
        Stream mic → detect speech via energy → stop after silence.
        Returns int16 numpy array of JUST the speech, or None.
        """
        chunk_samples = int(self.SAMPLE_RATE * self.CHUNK_SEC)
        max_chunks = int(max_secs / self.CHUNK_SEC)
        silence_limit = int(self.SILENCE_AFTER / self.CHUNK_SEC)

        pre_buf = []
        speech_buf = []
        speech_on = False
        silent_n = 0

        try:
            stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype="int16",
                blocksize=chunk_samples,
            )
            stream.start()

            for _ in range(max_chunks):
                if self._stop.is_set():
                    break
                data, _ = stream.read(chunk_samples)
                
                # Mute the mic internally if Jarvis is currently speaking
                if getattr(self, 'is_speaking', None) and self.is_speaking.is_set():
                    speech_on = False
                    speech_buf.clear()
                    pre_buf.clear()
                    silent_n = 0
                    continue

                energy = self._rms(data)

                if not speech_on:
                    pre_buf.append(data.copy())
                    if len(pre_buf) > self.PRE_BUFFER_N:
                        pre_buf.pop(0)
                    if energy > self.ENERGY_THRESHOLD:
                        speech_on = True
                        speech_buf.extend(pre_buf)
                        speech_buf.append(data.copy())
                        silent_n = 0
                else:
                    speech_buf.append(data.copy())
                    if energy < self.ENERGY_THRESHOLD:
                        silent_n += 1
                        if silent_n >= silence_limit:
                            break
                    else:
                        silent_n = 0

            stream.stop()
            stream.close()
        except Exception as e:
            self.logger.error(f"Mic error: {e}")
            return None

        if not speech_on or not speech_buf:
            return None
        return np.concatenate(speech_buf)

    def _transcribe(self, audio: np.ndarray, wake_word_check: bool = False) -> str | None:
        """
        STT pipeline (best → fallback order):
          0. Vosk (if wake_word_check, fast, lightweight check)
          1. Groq Cloud Whisper (extremely fast, sub-second online)
          2. faster-whisper  (offline, high accuracy, runs Whisper locally)
          3. Cloud Whisper   (OpenAI, skipped when Ollama is primary)
          4. Vosk            (offline, lightweight, lower accuracy)
          5. Google STT      (online fallback)
        """
        try:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(self.CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)
                wf.writeframes(audio.tobytes())
            buf.seek(0)

            # ── Tier 0: Vosk for Wake-Word check (runs in milliseconds) ──
            if wake_word_check and getattr(self, 'vosk_available', False):
                try:
                    import vosk, json
                    buf.seek(0)
                    rec = vosk.KaldiRecognizer(self.vosk_model, self.SAMPLE_RATE)
                    rec.AcceptWaveform(audio.tobytes())
                    res = json.loads(rec.FinalResult())
                    text = res.get("text", "").lower()
                    if text:
                        self.logger.info(f"[Vosk Wake-Word STT] {text}")
                        return text
                except Exception as ve:
                    self.logger.warning(f"Vosk wake-word STT failed: {ve}")

            # ── Tier 1: Groq Cloud Whisper (extremely fast, sub-second online) ──
            if not wake_word_check and hasattr(self, 'groq_client') and self.groq_client and not getattr(self, 'groq_disabled', False):
                try:
                    buf.seek(0)
                    buf.name = "audio.wav"
                    transcript = self.groq_client.audio.transcriptions.create(
                        model="whisper-large-v3", file=buf
                    )
                    if transcript.text:
                        text = transcript.text.strip().lower()
                        self.logger.info(f"[Groq Cloud STT] {text}")
                        return text
                except Exception as e:
                    self.logger.warning(f"Groq Cloud Whisper STT failed: {e}")
                    buf.seek(0)

            # ── Tier 2: faster-whisper (offline, high accuracy) ──────────
            if getattr(self, 'fw_available', False):
                try:
                    import tempfile, os
                    # Write wav to temp file (faster-whisper needs a file path)
                    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                    tmp.write(buf.read())
                    tmp.close()
                    try:
                        segments, _ = self.fw_model.transcribe(
                            tmp.name,
                            language="en",
                            beam_size=3,
                            vad_filter=True,   # skip non-speech segments automatically
                        )
                        text = " ".join(s.text for s in segments).strip().lower()
                        if text:
                            self.logger.info(f"[faster-whisper STT] {text}")
                            return text
                    finally:
                        try: os.unlink(tmp.name)
                        except Exception: pass
                except Exception as fw_err:
                    self.logger.warning(f"faster-whisper failed: {fw_err}")
                    buf.seek(0)

            # ── Tier 3: Cloud Whisper (skipped when Ollama is primary brain) ──
            use_cloud_whisper = (self.client_type == "openai"
                                 and hasattr(self, 'client') and self.client
                                 and getattr(self, 'provider', '') != "ollama")
            if use_cloud_whisper:
                try:
                    buf.seek(0)
                    buf.name = "audio.wav"
                    model_n = "whisper-large-v3-turbo" if self.groq_client else "whisper-1"
                    transcript = self.client.audio.transcriptions.create(
                        model=model_n, file=buf
                    )
                    if transcript.text:
                        return transcript.text.lower()
                except Exception as e:
                    self.logger.warning(f"Cloud Whisper STT failed: {e}")
                    buf.seek(0)

            # ── Tier 4: Vosk (offline, lightweight fallback if not already run) ──
            if getattr(self, 'vosk_available', False):
                try:
                    import vosk, json
                    buf.seek(0)
                    rec = vosk.KaldiRecognizer(self.vosk_model, self.SAMPLE_RATE)
                    rec.AcceptWaveform(audio.tobytes())
                    res = json.loads(rec.FinalResult())
                    text = res.get("text", "").lower()
                    if text:
                        self.logger.info(f"[Vosk STT] {text}")
                        return text
                except Exception as ve:
                    self.logger.warning(f"Vosk STT failed: {ve}")

            # ── Tier 5: Google STT (online last resort) ──────────────────
            try:
                buf.seek(0)
                with sr.AudioFile(buf) as src:
                    aud = self.recognizer.record(src)
                text = self.recognizer.recognize_google(aud).lower()
                self.logger.info(f"[Google STT] {text}")
                return text
            except Exception as google_err:
                self.logger.error(f"Google STT error: {google_err}")
                return None
        except Exception as e:
            self.logger.error(f"STT pipeline error: {e}")
            return None

    def _listen_once(self, timeout=6, phrase_limit=None, wake_word_check: bool = False) -> str | None:
        """Record with VAD and transcribe — skips silence instantly"""
        audio = self._record_vad(max_secs=timeout)
        if audio is None:
            return None
        return self._transcribe(audio, wake_word_check=wake_word_check)

    # ── Main loop ─────────────────────────────────────────

    def listen_loop(self):
        self.logger.info(f"Listening for wake words: {self.wake_words}")

        while not self._stop.is_set():
            text = self._listen_once(timeout=6, wake_word_check=True)
            if not text:
                continue

            found_wake = next((w for w in self.wake_words if w in text), None)
            if found_wake:
                self.logger.success(f"Wake word detected: '{found_wake}'")

                # Check if command was said together with wake word
                inline = text.replace(found_wake, "").strip()

                if self.on_wake:
                    threading.Thread(target=self.on_wake, daemon=True).start()
                try:
                    import winsound
                    winsound.Beep(880, 120)
                except Exception:
                    pass

                if inline and len(inline) > 2:
                    self.logger.info(f"Inline cmd: '{inline}'")
                    self.command_queue.put(inline)
                else:
                    self.logger.info("Waiting for command...")
                    cmd = self._listen_once(timeout=6, wake_word_check=False)
                    if cmd:
                        cmd = cmd.replace(found_wake, "").strip()
                        if cmd:
                            self.logger.info(f"Command: '{cmd}'")
                            self.command_queue.put(cmd)
                        else:
                            self.speak("Yes?")
                    else:
                        self.speak("Didn't catch that. Try again.")

    # ── Hybrid Brain Router ───────────────────────────────

    # Keywords that signal a complex / research-heavy query → route to Groq cloud
    _COMPLEX_KEYWORDS = [
        # Deep research / analysis
        "research", "analyze", "analyse", "in depth", "detailed explanation",
        "explain why", "compare and contrast", "pros and cons", "advantages and disadvantages",
        "history of", "how does", "mechanism", "theory", "scientific",
        # Heavy math
        "calculate", "integral", "derivative", "differentiate", "integrate",
        "equation", "solve for", "probability", "statistics", "matrix",
        "algorithm", "complexity", "big o", "proof", "theorem",
        # Code generation / debugging (needs deeper reasoning)
        "write a program", "write a script", "debug this", "fix this code",
        "implement", "refactor", "optimize",
        # Finance / market data
        "stock price", "market cap", "investment", "portfolio", "crypto",
        "bitcoin", "ethereum", "nifty", "sensex", "nasdaq",
        # Medical / legal (nuanced answers needed)
        "diagnosis", "symptoms", "treatment", "legal advice", "law",
        # Long essays / writing
        "write an essay", "write a report", "summarize this article",
    ]

    def _needs_cloud_brain(self, text: str) -> bool:
        """Fast keyword router — returns True if this query needs a cloud brain."""
        if not self.grok_client and not self.groq_client:          # no cloud brain available
            return False
        lowered = text.lower()
        return any(kw in lowered for kw in self._COMPLEX_KEYWORDS)

    def _pick_client(self, use_cloud: bool):
        """Return (client, model) tuple for the chosen brain."""
        if use_cloud:
            if self.grok_client:
                return self.grok_client, self.grok_model
            elif self.groq_client:
                return self.groq_client, self.groq_model
        return self.client, self.config.OPENAI_MODEL

    # ── AI ────────────────────────────────────────────────

    def ask_ai(self, user_message: str, short_term_memory: list = None) -> str:
        use_cloud  = self._needs_cloud_brain(user_message)
        
        # Prepare fallback queue
        candidates = []
        if use_cloud:
            if self.grok_client:
                candidates.append((self.grok_client, self.grok_model, "Grok", "☁ Grok"))
            if self.groq_client:
                candidates.append((self.groq_client, self.groq_model, "Groq", "☁ Groq"))
            candidates.append((self.client, self.config.OPENAI_MODEL, "Ollama", f"🏠 {self.provider.upper()}"))
        else:
            # Non-complex: Groq first (fast), then fallback to local/Grok
            candidates.append((self.client, self.config.OPENAI_MODEL, "Ollama", f"🏠 {self.provider.upper()}"))
            if self.grok_client:
                candidates.append((self.grok_client, self.grok_model, "Grok", "☁ Grok"))
            if self.groq_client:
                candidates.append((self.groq_client, self.groq_model, "Groq", "☁ Groq"))

        system = (
            "You are JARVIS, a personal AI assistant on the user's Windows PC. "
            "Be helpful and informative. Keep answers concise unless the user asks to write or explain code, in which case provide complete, correct code in markdown code blocks. "
            "Never say you can't do something. If you don't know current real-time data (like live prices), give the best answer you can from your knowledge."
        )

        msgs = [{"role": "system", "content": system}]
        if short_term_memory:
            msgs += short_term_memory[-6:]
        msgs.append({"role": "user", "content": user_message})

        last_err = None
        for client, model, name, brain_tag in candidates:
            try:
                self.logger.info(f"[Brain Router] {brain_tag} → {user_message[:60]}")
                resp = client.chat.completions.create(
                    model=model,
                    messages=msgs,
                    max_tokens=800 if "Grok" in name or "Groq" in name else 600,
                    temperature=0.7,
                )
                reply = resp.choices[0].message.content.strip()
                self.conversation_history.append({"role": "assistant", "content": reply})
                return reply
            except Exception as e:
                self.logger.warning(f"Brain {name} failed: {e}")
                last_err = e
        
        return f"All AI backends failed. Last error: {last_err}"

    def ask_ai_with_tools(self, user_message: str, tools: list, short_term_memory: list = None):
        # Clean up tools schema (remove empty properties to prevent Groq API 400 errors)
        cleaned_tools = []
        for t in tools:
            import copy
            t_copy = copy.deepcopy(t)
            if "function" in t_copy and "parameters" in t_copy["function"]:
                params = t_copy["function"]["parameters"]
                if "properties" in params and not params["properties"]:
                    del params["properties"]
            cleaned_tools.append(t_copy)

        use_cloud  = self._needs_cloud_brain(user_message)
        
        # Prepare fallback queue
        candidates = []
        if use_cloud:
            if self.grok_client:
                candidates.append((self.grok_client, self.grok_model, "Grok", "☁ Grok"))
            if self.groq_client:
                candidates.append((self.groq_client, self.groq_model, "Groq", "☁ Groq"))
            candidates.append((self.client, self.config.OPENAI_MODEL, "Ollama", f"🏠 {self.provider.upper()}"))
        else:
            # Non-complex: try Groq first for speed, then local, then Grok
            if self.groq_client:
                candidates.append((self.groq_client, self.groq_model, "Groq", "☁ Groq"))
            candidates.append((self.client, self.config.OPENAI_MODEL, "Ollama", f"🏠 {self.provider.upper()}"))
            if self.grok_client:
                candidates.append((self.grok_client, self.grok_model, "Grok", "☁ Grok"))

        system = (
            "You are JARVIS, a personal AI assistant on the user's Windows PC. "
            "You have access to tools to control the PC and search the web. "
            "Use the search_web tool ONLY when the user asks for current/live/today's information such as prices, rates, news, scores, or weather (if check_weather is unavailable). "
            "For all other general knowledge questions, conversational queries, or explanations, respond directly without using any tools. "
            "Only use PC control tools (open_app, type_text, system_command etc.) when the user explicitly requests a PC action. "
            "When calling tools, you MUST strictly use ONLY the parameters defined in the tool's schema. Do NOT invent or add any extra arguments (e.g. do not add 'location' to search_web). "
            "Answer concisely. Code must be in markdown blocks."
        )

        msgs = [{"role": "system", "content": system}]
        if short_term_memory:
            msgs += short_term_memory[-6:]
        msgs.append({"role": "user", "content": user_message})

        last_err = None
        for client, model, name, brain_tag in candidates:
            try:
                self.logger.info(f"[Brain Router] {brain_tag} (tools) → {user_message[:60]}")
                resp = client.chat.completions.create(
                    model=model,
                    messages=msgs,
                    tools=cleaned_tools,
                    tool_choice="auto",
                    max_tokens=500 if "Grok" in name or "Groq" in name else 400,
                    temperature=0.0,
                )
                msg = resp.choices[0].message
                if msg.tool_calls:
                    return {"tool_calls": msg.tool_calls, "message": msg}
                
                reply = msg.content.strip() if msg.content else "Action requested."
                self.conversation_history.append({"role": "assistant", "content": reply})
                return {"text": reply}
            except Exception as e:
                self.logger.warning(f"Brain {name} (tools) failed: {e}")
                err_str = str(e).lower()
                # Don't disable backend just because of tool_use_failed (format error, not auth)
                fatal = any(x in err_str for x in ["model not found", "credit", "license",
                    "permission-denied", "permission_denied", "unauthorized", "billing",
                    "api_key", "api key", "auth", "forbidden", "403", "401"])
                if not fatal or "tool_use_failed" in err_str:
                    pass  # Transient error — try next candidate
                last_err = e
        
        # Fallback to plain ask_ai if tool calls fail completely
        self.logger.warning("Tool calls failed completely on all backends. Falling back to plain AI completion.")
        try:
            fallback_reply = self.ask_ai(user_message, short_term_memory=short_term_memory)
            return {"text": fallback_reply}
        except Exception as fe:
            return {"text": f"I'm having trouble connecting to all AI backends right now. Last error: {last_err}"}

    def plan_task(self, task: str) -> list[str]:
        import json
        raw = self.ask_ai(
            f"Break into 3-5 actionable steps: '{task}'. Return ONLY a JSON array."
        )
        try:
            raw = raw.strip().strip("```json").strip("```").strip()
            return json.loads(raw)
        except Exception:
            return [task]

    def stop(self):
        self._stop.set()
