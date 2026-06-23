import json
import time
import os
from pathlib import Path

class StateManager:
    def __init__(self):
        self.filepath = Path.home() / ".jarvis" / "runtime_state.json"
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.default_state = {
            "last_update": 0,
            "status": "Offline",
            "last_command": "",
            "last_response": "",
            "cpu": 0,
            "ram": 0,
            "vision_active": False,
            "detected_objects": [],
            "face_detected": False,
            "conversation_history": [],
            "pending_commands": []
        }
        if not self.filepath.exists():
            self.save_state(self.default_state)

    def save_state(self, state_dict: dict):
        state_dict["last_update"] = time.time()
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(state_dict, f, indent=2)
        except Exception:
            pass

    def update_key(self, key: str, value):
        state = self.get_state()
        state[key] = value
        self.save_state(state)

    def get_state(self) -> dict:
        try:
            if self.filepath.exists():
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return self.default_state

    def inject_command(self, cmd_text: str):
        """Add a command to the pending queue for Jarvis to consume."""
        state = self.get_state()
        if "pending_commands" not in state:
            state["pending_commands"] = []
        state["pending_commands"].append(cmd_text)
        state["last_command"] = ""
        state["last_response"] = ""
        self.save_state(state)

    def pop_commands(self) -> list:
        """Extract and clear all pending commands. Used by Jarvis Main loop."""
        state = self.get_state()
        cmds = state.get("pending_commands", [])
        if cmds:
            state["pending_commands"] = []
            self.save_state(state)
        return cmds

# Global singleton for runtime
state_manager = StateManager()
