"""Emotion Agent"""
from utils.config import Config

class EmotionAgent:
    STRESSED = {"stressed","frustrated","angry","urgent","asap","broken","crash","help","panic","terrible","hate"}
    HAPPY    = {"great","awesome","happy","perfect","love","excellent","thanks","amazing"}

    def __init__(self, config: Config):
        self.config = config
        self.last_mood = "neutral"

    def analyze_text(self, text: str) -> str:
        words = set(text.lower().split())
        if words & self.STRESSED:
            self.last_mood = "stressed"
        elif words & self.HAPPY:
            self.last_mood = "happy"
        else:
            self.last_mood = "neutral"
        return self.last_mood
