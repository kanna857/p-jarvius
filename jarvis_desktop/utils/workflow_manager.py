import json
import os
from pathlib import Path

class WorkflowManager:
    def __init__(self):
        self.filepath = Path.home() / ".jarvis" / "workflows.json"
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.workflows = self._load()

    def _load(self) -> dict:
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.workflows, f, indent=4)
        except Exception:
            pass

    def get_all(self) -> dict:
        return self.workflows

    def get_workflow(self, name: str) -> list:
        return self.workflows.get(name)

    def save_workflow(self, name: str, steps: list):
        self.workflows[name] = steps
        self.save()

    def delete_workflow(self, name: str):
        if name in self.workflows:
            del self.workflows[name]
            self.save()

# Singleton instance
workflow_manager = WorkflowManager()
