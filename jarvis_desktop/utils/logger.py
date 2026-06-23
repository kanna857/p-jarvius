"""JARVIS Logger — colored console + file output"""
import time
from pathlib import Path

LOG_DIR = Path.home() / ".jarvis"
LOG_DIR.mkdir(parents=True, exist_ok=True)

class JarvisLogger:
    R = "\033[0m"; C = "\033[96m"; G = "\033[92m"
    Y = "\033[93m"; E = "\033[91m"; D = "\033[2m"
    log_path = str(LOG_DIR / "jarvis.log")

    def __init__(self, name: str = "JARVIS"):
        self.name = name

    def _write(self, level: str, msg: str, color: str):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] [{level}] [{self.name}] {msg}"
        try:
            print(f"{self.D}[{ts}]{self.R} {color}[{self.name}]{self.R} {msg}")
        except UnicodeEncodeError:
            import sys
            # Fallback to ascii/current terminal encoding replacing invalid chars
            enc = sys.stdout.encoding or 'ascii'
            safe_msg = msg.encode(enc, errors='replace').decode(enc)
            print(f"{self.D}[{ts}]{self.R} {color}[{self.name}]{self.R} {safe_msg}")
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def info(self, msg):    self._write("INFO",    msg, self.C)
    def success(self, msg): self._write("OK",      msg, self.G)
    def warning(self, msg): self._write("WARN",    msg, self.Y)
    def error(self, msg):   self._write("ERROR",   msg, self.E)
