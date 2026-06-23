"""
JARVIS - Background System Tray App for Windows (Persistent Memory Edition)
Run this once — Jarvis lives silently in your system tray.
Uses LangChain's ConversationBufferMemory and FileChatMessageHistory to persist
and inject rolling conversational history.
"""

import sys
import os
import threading
import queue
import time
from pathlib import Path

# Add project root directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    import ctypes
    # Hide console window
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    
    # Enforce single instance
    jarvis_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "JarvisDesktopMemoryInstanceMutex")
    if ctypes.windll.kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
        sys.exit(0)

from utils.config import Config
from utils.logger import JarvisLogger
from agents.memory_agent import MemoryAgent
from agents.voice_agent import VoiceAgent
from main import Jarvis, _hotkey_listener_loop
from tray_app import JarvisTray

class LangChainMemoryAgent(MemoryAgent):
    def __init__(self, config: Config):
        super().__init__(config)
        self.logger = JarvisLogger("LC-Memory")

        # ── LangChain Setup ──
        try:
            from langchain_classic.memory import ConversationBufferMemory
            from langchain_community.chat_message_histories import FileChatMessageHistory
            
            history_dir = Path.home() / ".jarvis"
            history_dir.mkdir(parents=True, exist_ok=True)
            self.file_path = history_dir / "chat_history.json"
            
            # Using FileChatMessageHistory to persist messages in a JSON file
            self.chat_history = FileChatMessageHistory(file_path=str(self.file_path))
            self.lc_memory = ConversationBufferMemory(
                chat_memory=self.chat_history,
                return_messages=True,
                memory_key="chat_history"
            )
            self.logger.success(f"LangChain Persistent Memory linked to {self.file_path}")
        except Exception as e:
            self.logger.error(f"Failed to load LangChain memory: {e}")
            raise e

        # Synchronize/prepopulate short_term with history from file
        self.short_term = self.get_short_term()

    def store(self, cmd: str, resp: str):
        # Save to LangChain's rolling memory (FileChatMessageHistory handles JSON persistence automatically)
        try:
            self.lc_memory.chat_memory.add_user_message(cmd)
            self.lc_memory.chat_memory.add_ai_message(resp)
        except Exception as e:
            self.logger.error(f"Failed to write message turn to LangChain chat history: {e}")

        # Also store in the SQLite/Chroma DB parent class (for tags, facts, semantic vector lookup, etc.)
        super().store(cmd, resp)

        # Sync short_term memory for the local list representation
        self.short_term = self.get_short_term()

    def get_short_term(self) -> list:
        try:
            messages = self.lc_memory.chat_memory.messages
            out = []
            for msg in messages:
                role = "user" if msg.type == "human" else "assistant"
                out.append({"role": role, "content": msg.content})
            # Return the last 40 messages to prevent hitting token limit on small local models
            return out[-40:]
        except Exception as e:
            self.logger.error(f"Error reading short term memory from LangChain: {e}")
            return []


class VoiceAgentWithMemory(VoiceAgent):
    def __init__(self, command_queue, config):
        super().__init__(command_queue, config)
        self.grok_disabled = False
        self.groq_disabled = False

    def ask_ai(self, user_message: str, short_term_memory: list = None) -> str:
        # Prepare fallback queue: Groq FIRST (fastest cloud), then Grok, then local Ollama
        candidates = []
        if self.groq_client and not self.groq_disabled:
            candidates.append((self.groq_client, self.groq_model, "Groq", "☁ Groq"))
        if self.grok_client and not self.grok_disabled:
            candidates.append((self.grok_client, self.grok_model, "Grok", "☁ Grok"))
        candidates.append((self.client, self.config.OPENAI_MODEL, "Ollama", f"🏠 {self.provider.upper()}"))

        system = (
            "You are JARVIS, a personal AI assistant on the user's Windows PC. "
            "Be helpful and informative. Keep answers concise unless the user asks to write or explain code, in which case provide complete, correct code in markdown code blocks. "
            "Never say you can't do something. If you don't know current real-time data (like live prices), give the best answer you can from your knowledge."
        )

        msgs = [{"role": "system", "content": system}]
        if short_term_memory:
            # Slices the last 20 messages (10 conversation turns) for LLM context injection
            msgs += short_term_memory[-20:]
        msgs.append({"role": "user", "content": user_message})
        
        last_err = None
        for client, model, name, brain_tag in candidates:
            try:
                self.logger.info(f"[Brain Router] {brain_tag} (memory) → {user_message[:60]}")
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
                self.logger.warning(f"Brain {name} (memory) failed: {e}")
                err_str = str(e).lower()
                fatal = any(x in err_str for x in ["model not found", "credit", "license",
                    "permission-denied", "permission_denied", "unauthorized", "billing",
                    "api_key", "api key", "auth", "forbidden", "403", "401"])
                if fatal:
                    self.logger.error(f"Brain {name} has a fatal error. Disabling {name} backend.")
                    if name == "Grok":
                        self.grok_disabled = True
                    elif name == "Groq":
                        self.groq_disabled = True
                last_err = e
        
        return f"All AI backends failed. Last error: {last_err}"

    def ask_ai_with_tools(self, user_message: str, tools: list, short_term_memory: list = None):
        # Deep-clean tool schemas to prevent Groq API tool_use_failed errors
        import copy
        cleaned_tools = []
        for t in tools:
            t_copy = copy.deepcopy(t)
            if "function" in t_copy and "parameters" in t_copy["function"]:
                params = t_copy["function"]["parameters"]
                # Remove empty properties dict entirely
                if "properties" in params and not params["properties"]:
                    del params["properties"]
                    # Also remove required if it's empty or references nothing
                    params.pop("required", None)
            cleaned_tools.append(t_copy)

        # Prepare fallback queue: Groq FIRST (fastest cloud), then Grok, then Ollama
        candidates = []
        if self.groq_client and not self.groq_disabled:
            candidates.append((self.groq_client, self.groq_model, "Groq", "☁ Groq"))
        if self.grok_client and not self.grok_disabled:
            candidates.append((self.grok_client, self.grok_model, "Grok", "☁ Grok"))
        candidates.append((self.client, self.config.OPENAI_MODEL, "Ollama", f"🏠 {self.provider.upper()}"))

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
            # Slices the last 20 messages (10 conversation turns) for LLM context injection
            msgs += short_term_memory[-20:]
        msgs.append({"role": "user", "content": user_message})
        
        last_err = None
        for client, model, name, brain_tag in candidates:
            try:
                self.logger.info(f"[Brain Router] {brain_tag} (tools + memory) → {user_message[:60]}")
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
                self.logger.warning(f"Brain {name} (tools + memory) failed: {e}")
                err_str = str(e).lower()
                # Only disable backend on truly fatal errors (NOT tool_use_failed or 400 format errors)
                fatal = any(x in err_str for x in ["model not found", "credit", "license",
                    "permission-denied", "permission_denied", "unauthorized", "billing",
                    "api_key", "api key", "auth", "forbidden", "403", "401"])
                if fatal and "tool_use_failed" not in err_str:
                    self.logger.error(f"Brain {name} has a fatal error. Disabling {name} backend.")
                    if name == "Grok":
                        self.grok_disabled = True
                    elif name == "Groq":
                        self.groq_disabled = True
                last_err = e

        # Fallback to plain ask_ai if tool calls fail completely
        self.logger.warning("Tool calls failed completely on all backends. Falling back to plain AI completion.")
        try:
            fallback_reply = self.ask_ai(user_message, short_term_memory=short_term_memory)
            return {"text": fallback_reply}
        except Exception as fe:
            return {"text": f"I'm having trouble connecting to all AI backends right now. Last error: {last_err}"}


class JarvisWithMemory(Jarvis):
    def __init__(self):
        super().__init__()
        # Override memory and voice with memory-enabled agents
        self.memory = LangChainMemoryAgent(self.config)
        self.voice = VoiceAgentWithMemory(self.command_queue, self.config)
        self.logger.success("Jarvis initialized with LangChain Persistent Memory!")


def main():
    jarvis = JarvisWithMemory()
    jarvis.start()

    # Hand control to the system tray (blocks until user quits)
    tray = JarvisTray(jarvis)
    tray.run()  # blocking — stays alive here

    jarvis.stop()
    sys.exit(0)


if __name__ == "__main__":
    main()
