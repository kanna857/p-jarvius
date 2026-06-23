"""Security Agent"""
from utils.config import Config
from utils.logger import JarvisLogger

class SecurityAgent:
    BLOCKED = [":(){ :|:& };:", "del /f /s /q c:\\", "format c:"]
    HIGH_RISK = ["delete all", "wipe", "send email to all", "transfer money", "buy now"]

    def __init__(self, config: Config):
        self.config = config
        self.logger = JarvisLogger("Security")
        self.allowed_high_risk: set = set()

    def is_allowed(self, cmd: str) -> bool:
        c = cmd.lower()
        for b in self.BLOCKED:
            if b in c:
                self.logger.error(f"BLOCKED: {cmd}")
                return False
        for h in self.HIGH_RISK:
            if h in c and h not in self.allowed_high_risk:
                self.logger.warning(f"High-risk blocked: {h}")
                return False
        return True
