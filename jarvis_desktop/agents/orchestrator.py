"""
JARVIS Central Orchestrator
────────────────────────────
Every user command flows through here.

Flow:
  1. classify_intent()  → llama-3.1-8b-instant (~80ms), uses last 3 memory turns
  2. dispatch()         → runs handler(s) with task-specific model — single or parallel
  3. merge()            → combine parallel results into one response

Model routing (all via Groq):
  Classification  → llama-3.1-8b-instant       (ultra-fast, cheap)
  Complex/Chat    → llama-3.3-70b-versatile     (deep reasoning)
  Code/Automation → deepseek-r1-distill-llama-70b (strong at code)
  Vision          → llama-3.2-11b-vision        (multimodal)

Intent categories:
  CONVERSATION   — general chat, knowledge Q&A, code help
  SYSTEM_CONTROL — open apps, volume, brightness, type text, shutdown
  WEB_SEARCH     — explicit "search", "look up online", "find on web"
  INFO           — direct APIs: cricket, weather, news, currency, jokes
  VISION         — analyze screen, solve coding problem visible on screen
  MEMORY_TASKS   — add/list/complete/delete tasks, set reminders
  EMAIL          — read / check emails
"""

import re
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.logger import JarvisLogger


# ── Groq model constants ──────────────────────────────────────────────────────
GROQ_CLASSIFY  = "llama-3.1-8b-instant"           # intent classification — ultra-fast
GROQ_REASON    = "llama-3.3-70b-versatile"         # complex reasoning & conversation
GROQ_CODE      = "deepseek-r1-distill-llama-70b"   # code generation & automation
GROQ_VISION    = "llama-3.2-11b-vision"            # vision / multimodal



# ─────────────────────────────────────────────────────────────────────────────
# Intent Classifier (Groq-powered, ~150ms)
# ─────────────────────────────────────────────────────────────────────────────

class IntentClassifier:
    SYSTEM_PROMPT = """You are an intent classifier for JARVIS, a Windows AI assistant.
Classify the user's message into ONE or MORE of these exact category names:

CONVERSATION   - General chat, greetings, Q&A, explanations, code generation/help (not on screen)
SYSTEM_CONTROL - Open/close apps, volume, brightness, minimize, maximize, type text, shutdown, restart, screenshot, kill process, battery, network, system status
WEB_SEARCH     - ONLY when user explicitly says "search", "look up", "find online", "google", or asks for web results
INFO           - Direct data fetch: live cricket scores, weather, news, currency conversion, jokes, quotes, definitions, player stats
VISION         - Analyze screen, solve a problem/bug visible on screen, describe what's on screen, detect objects, count faces
MEMORY_TASKS   - Add, list, complete, or delete tasks; set reminders
EMAIL          - Read, check, or summarize emails
MESSAGING      - Send WhatsApp message, send Telegram message
RESEARCH       - Academic research, search arXiv papers, summarize papers, generate hypotheses, plan experiments, literature review

Rules:
  - Prefer INFO over WEB_SEARCH for cricket/weather/news unless user says "search"
  - For compound requests like "open chrome AND check the weather", return MULTIPLE intents
  - Return ONLY valid JSON, no extra text

Output:
  Single intent:  {"intents": ["INFO"], "confidence": 0.95}
  Multi-intent:   {"intents": ["SYSTEM_CONTROL", "INFO"], "confidence": 0.85}"""

    def __init__(self, groq_client):
        self.client = groq_client
        self.logger = JarvisLogger("Classifier")

    def classify(self, text: str, memory: list = None) -> list[str]:
        """
        Returns list of intent strings.
        Uses llama-3.1-8b-instant — ultra-fast, cheap, perfect for classification.
        Injects last 3 conversation turns for context-aware classification.
        Falls back to ['CONVERSATION'] on any error.
        """
        msgs = [{"role": "system", "content": self.SYSTEM_PROMPT}]

        # Inject last 3 conversation turns for context
        if memory:
            msgs += memory[-6:]

        msgs.append({"role": "user", "content": f"Classify: {text}"})

        try:
            resp = self.client.chat.completions.create(
                model=GROQ_CLASSIFY,          # llama-3.1-8b-instant — fast & cheap
                messages=msgs,
                max_tokens=50,
                temperature=0.0,
            )
            raw = resp.choices[0].message.content.strip()
            m = re.search(r"\{.*?\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                intents = [i.upper() for i in data.get("intents", ["CONVERSATION"])]
                self.logger.info(f"✦ Intent: {intents}  ← '{text[:55]}'")
                return intents
        except Exception as e:
            self.logger.warning(f"Classification error: {e}")

        return ["CONVERSATION"]


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class Orchestrator:
    """Central command router — classifies, dispatches, merges."""

    VALID_INTENTS = {
        "CONVERSATION", "SYSTEM_CONTROL", "WEB_SEARCH",
        "INFO", "VISION", "MEMORY_TASKS", "EMAIL", "MESSAGING", "RESEARCH"
    }

    # Tools each handler is allowed to use
    _SYSTEM_TOOL_NAMES = {
        "open_app", "open_website", "type_text", "system_command",
        "set_brightness", "execute_python_code", "execute_workflow",
        "kill_process", "list_processes", "get_battery",
        "get_full_system_status", "get_network_info",
        "execute_desktop_task", "start_screen_monitor"
    }
    _INFO_TOOL_NAMES = {
        "check_weather", "check_news", "check_cricket", "get_joke", "get_quote",
        "get_definition", "convert_currency", "get_cricket_matches",
        "search_cricket_player", "get_cricket_player_info",
        "get_cricket_squad", "get_cricket_match_info"
    }
    _VISION_TOOL_NAMES  = {"analyze_screen", "solve_coding_problem", "search_file_contents",
                           "detect_objects", "count_faces"}
    _TASK_TOOL_NAMES    = {"add_task", "list_tasks", "complete_task", "delete_task", "set_reminder"}
    _EMAIL_TOOL_NAMES   = {"read_emails"}
    _MESSAGING_TOOL_NAMES = {"send_whatsapp", "send_telegram"}
    _RESEARCH_TOOL_NAMES = {
        "search_papers", "summarize_paper", "generate_hypotheses",
        "plan_experiment", "literature_review", "get_trending_papers"
    }

    def __init__(self, jarvis):
        self.jarvis = jarvis
        self.logger = JarvisLogger("Orchestrator")

        voice = jarvis.voice
        if hasattr(voice, "groq_client") and voice.groq_client and not getattr(voice, "groq_disabled", False):
            self.groq_client = voice.groq_client
            self.classifier  = IntentClassifier(voice.groq_client)
            self.logger.success(
                f"Orchestrator online — Models: "
                f"Classify={GROQ_CLASSIFY} | Reason={GROQ_REASON} | "
                f"Code={GROQ_CODE} | Vision={GROQ_VISION} ⚡"
            )
        else:
            self.groq_client = None
            self.classifier  = None
            self.logger.warning("Orchestrator: no Groq client — falling back to full LLM tool routing.")

    # ── Tool filter helper ────────────────────────────────────────────────────

    def _tools(self, names: set) -> list:
        from utils.dynamic_tool_manager import dynamic_tool_manager
        all_names = set(names)
        # Always allow create_dynamic_tool
        all_names.add("create_dynamic_tool")
        # Allow all currently loaded dynamic tools
        for dyn_name in dynamic_tool_manager.loaded_tools.keys():
            all_names.add(dyn_name)
        return [t for t in self.jarvis.get_tools() if t["function"]["name"] in all_names]

    # ── Specialized Groq caller — picks the right model per task ─────────────

    def _groq_call(self, model: str, messages: list,
                   tools: list = None, max_tokens: int = 600) -> dict:
        """
        Direct Groq call with a specific model.
        Returns dict with 'text' or 'tool_calls' key — same format as ask_ai_with_tools.
        Falls back to voice.ask_ai_with_tools on error.
        """
        if not self.groq_client:
            return {"text": ""}
        import copy
        # Clean empty properties from tool schemas (prevents tool_use_failed)
        cleaned = []
        if tools:
            for t in tools:
                tc = copy.deepcopy(t)
                if "function" in tc and "parameters" in tc["function"]:
                    p = tc["function"]["parameters"]
                    if "properties" in p and not p["properties"]:
                        del p["properties"]
                        p.pop("required", None)
                cleaned.append(tc)
        try:
            kwargs = dict(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.0,
            )
            if cleaned:
                kwargs["tools"] = cleaned
                kwargs["tool_choice"] = "auto"
            resp = self.groq_client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                return {"tool_calls": msg.tool_calls, "message": msg}
            return {"text": (msg.content or "").strip()}
        except Exception as e:
            self.logger.warning(f"Groq [{model}] call failed: {e}")
            return {"text": ""}

    def _build_msgs(self, system: str, command: str, memory: list = None) -> list:
        """Build a standard messages list with system prompt + optional memory + user command."""
        msgs = [{"role": "system", "content": system}]
        if memory:
            msgs += memory[-10:]
        msgs.append({"role": "user", "content": command})
        return msgs

    # ── Execute LLM tool-call response ────────────────────────────────────────

    def _exec(self, resp: dict) -> str:
        """Execute tool_calls from an LLM response dict and return combined text."""
        if "tool_calls" in resp:
            parts = []
            for tc in resp["tool_calls"]:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}
                parts.append(self.jarvis._execute_tool(name, args))
            return " ".join(p for p in parts if p).strip()
        return resp.get("text", "Done.")

    # ── Intent Handlers ───────────────────────────────────────────────────────

    def _handle_conversation(self, command: str, memory: list) -> str:
        """Deep reasoning with llama-3.3-70b-versatile — streams to TTS for instant response."""
        # Use stream_to_speech if available — voice starts in ~200ms
        if hasattr(self.jarvis.voice, 'stream_to_speech'):
            return self.jarvis.voice.stream_to_speech(
                prompt=command,
                model="llama-3.3-70b-versatile",
                system="You are JARVIS, a helpful Windows AI assistant. "
                       "Be concise and natural. Use markdown only for code blocks.",
                memory=memory
            )
        # Fallback: direct Groq call (no streaming)
        msgs = self._build_msgs(
            "You are JARVIS, a helpful Windows AI assistant. Be concise and clear. "
            "For code, use markdown code blocks.",
            command, memory
        )
        result = self._groq_call(GROQ_REASON, msgs, max_tokens=800)
        return result.get("text") or self.jarvis.voice.ask_ai(command, short_term_memory=memory)

    def _handle_system_control(self, command: str, memory: list) -> str:
        """Code/automation tasks use deepseek-r1-distill-llama-70b."""
        msgs = self._build_msgs(
            "You are JARVIS. Use the provided tools to control the Windows PC. "
            "Only call tools that are needed. Never invent tool arguments.",
            command, memory
        )
        resp = self._groq_call(GROQ_CODE, msgs, tools=self._tools(self._SYSTEM_TOOL_NAMES), max_tokens=400)
        if not resp.get("tool_calls") and not resp.get("text"):
            # Fallback to voice agent if specialized call fails
            resp = self.jarvis.voice.ask_ai_with_tools(
                command, tools=self._tools(self._SYSTEM_TOOL_NAMES), short_term_memory=memory
            )
        return self._exec(resp)

    def _handle_web_search(self, command: str, memory: list) -> str:
        """Extract search query with 8b-instant (fast), then call WebAgent directly."""
        try:
            msgs = self._build_msgs(
                "Extract only the search query from the user's message. Return the query text only, nothing else.",
                command
            )
            result = self._groq_call(GROQ_CLASSIFY, msgs, max_tokens=30)
            q = result.get("text", "").strip().strip("\"'") or command
        except Exception:
            q = command
        return self.jarvis.web.search(q)

    def _handle_info(self, command: str, memory: list) -> str:
        """Routes to the right API call based on keywords — no LLM needed for most cases."""
        cmd = command.lower()

        # ── Direct keyword dispatch (zero LLM overhead) ──
        if any(k in cmd for k in ("weather", "temperature", "forecast", "raining", "humid")):
            return self.jarvis.ext_api.get_hyderabad_weather()
        if any(k in cmd for k in ("news", "headline", "today's news", "what's happening")):
            return self.jarvis.ext_api.get_latest_news()
        if any(k in cmd for k in ("live cricket", "cricket score", "ipl score", "t20 score",
                                   "odi score", "test score", "cricket live")):
            return self.jarvis.ext_api.check_live_cricket()
        if any(k in cmd for k in ("joke", "funny", "make me laugh", "tell me a joke")):
            return self.jarvis.ext_api.get_joke()
        if any(k in cmd for k in ("quote", "motivat", "inspir", "wisdom")):
            return self.jarvis.ext_api.get_quote()

        # ── LLM-assisted for structured params (currency, definitions, player search) ──
        if any(k in cmd for k in ("convert", "currency", " usd", " inr", " eur", " gbp", "dollar", "rupee")):
            return self._exec(self.jarvis.voice.ask_ai_with_tools(
                command, tools=self._tools({"convert_currency"}), short_term_memory=memory
            ))
        if any(k in cmd for k in ("define ", "definition of", "meaning of", "what does", " word ")):
            return self._exec(self.jarvis.voice.ask_ai_with_tools(
                command, tools=self._tools({"get_definition"}), short_term_memory=memory
            ))
        if any(k in cmd for k in ("cricket player", "player info", "player stats", "who is")):
            return self._exec(self.jarvis.voice.ask_ai_with_tools(
                command, tools=self._tools({"search_cricket_player", "get_cricket_player_info"}),
                short_term_memory=memory
            ))
        if any(k in cmd for k in ("cricket match", "upcoming match", "match schedule")):
            return self.jarvis.ext_api.get_cricket_matches()

        # ── Fallback: LLM picks the right INFO tool ──
        return self._exec(self.jarvis.voice.ask_ai_with_tools(
            command, tools=self._tools(self._INFO_TOOL_NAMES), short_term_memory=memory
        ))

    def _handle_vision(self, command: str, memory: list) -> str:
        """Vision tasks route to llama-3.2-11b-vision via the existing vision agent."""
        # The vision agent handles actual image capture — we just route the tool call
        resp = self.jarvis.voice.ask_ai_with_tools(
            command, tools=self._tools(self._VISION_TOOL_NAMES), short_term_memory=memory
        )
        return self._exec(resp)

    def _handle_memory_tasks(self, command: str, memory: list) -> str:
        """Task/reminder management uses llama-3.3-70b-versatile for accurate param extraction."""
        msgs = self._build_msgs(
            "You are JARVIS. Use the provided tools to manage the user's tasks and reminders. "
            "Extract all required parameters carefully from the user's request.",
            command, memory
        )
        resp = self._groq_call(GROQ_REASON, msgs, tools=self._tools(self._TASK_TOOL_NAMES), max_tokens=300)
        if not resp.get("tool_calls") and not resp.get("text"):
            resp = self.jarvis.voice.ask_ai_with_tools(
                command, tools=self._tools(self._TASK_TOOL_NAMES), short_term_memory=memory
            )
        return self._exec(resp)

    def _handle_email(self, command: str, memory: list) -> str:
        """Email uses llama-3.3-70b-versatile for accurate inbox reading."""
        msgs = self._build_msgs(
            "You are JARVIS. Use the provided tools to read and summarize the user's emails.",
            command, memory
        )
        resp = self._groq_call(GROQ_REASON, msgs, tools=self._tools(self._EMAIL_TOOL_NAMES), max_tokens=300)
        if not resp.get("tool_calls") and not resp.get("text"):
            resp = self.jarvis.voice.ask_ai_with_tools(
                command, tools=self._tools(self._EMAIL_TOOL_NAMES), short_term_memory=memory
            )
        return self._exec(resp)

    def _handle_messaging(self, command: str, memory: list) -> str:
        """WhatsApp/Telegram messaging uses deepseek for precise param extraction."""
        msgs = self._build_msgs(
            "You are JARVIS. Use the provided tools to send messages. "
            "Extract the phone number and message text from the user's request. "
            "For Indian numbers without country code, prepend +91.",
            command, memory
        )
        resp = self._groq_call(GROQ_CODE, msgs, tools=self._tools(self._MESSAGING_TOOL_NAMES), max_tokens=300)
        if not resp.get("tool_calls") and not resp.get("text"):
            resp = self.jarvis.voice.ask_ai_with_tools(
                command, tools=self._tools(self._MESSAGING_TOOL_NAMES), short_term_memory=memory
            )
        return self._exec(resp)

    def _handle_research(self, command: str, memory: list) -> str:
        """Academic research tasks use deepseek-r1-distill-llama-70b or llama-3.3-70b-versatile."""
        msgs = self._build_msgs(
            "You are JARVIS. Use the provided tools to search academic papers, summarize them, "
            "generate hypotheses, design experiments, or perform literature reviews.",
            command, memory
        )
        # Using llama-3.3-70b-versatile for complex reasoning/research tasks
        resp = self._groq_call(GROQ_REASON, msgs, tools=self._tools(self._RESEARCH_TOOL_NAMES), max_tokens=600)
        if not resp.get("tool_calls") and not resp.get("text"):
            resp = self.jarvis.voice.ask_ai_with_tools(
                command, tools=self._tools(self._RESEARCH_TOOL_NAMES), short_term_memory=memory
            )
        return self._exec(resp)

    # ── Handler dispatch map ──────────────────────────────────────────────────

    _HANDLER_MAP = {
        "CONVERSATION":   "_handle_conversation",
        "SYSTEM_CONTROL": "_handle_system_control",
        "WEB_SEARCH":     "_handle_web_search",
        "INFO":           "_handle_info",
        "VISION":         "_handle_vision",
        "MEMORY_TASKS":   "_handle_memory_tasks",
        "EMAIL":          "_handle_email",
        "MESSAGING":      "_handle_messaging",
        "RESEARCH":       "_handle_research",
    }

    # Merge order: action results first, info second, conversation last
    _MERGE_ORDER = [
        "SYSTEM_CONTROL", "MEMORY_TASKS", "EMAIL", "MESSAGING", "RESEARCH",
        "INFO", "WEB_SEARCH", "VISION", "CONVERSATION"
    ]

    # ── Main entry point ──────────────────────────────────────────────────────

    def route(self, command: str, memory: list = None) -> str:
        """
        Classify intent → dispatch handler(s) → merge results.
        Single intent: direct call (fastest).
        Multi-intent: parallel ThreadPoolExecutor, results merged in priority order.
        """
        # ── Classify ──
        if self.classifier:
            intents = self.classifier.classify(command, memory=memory)
        else:
            intents = ["CONVERSATION"]

        # Filter to known intents
        valid = [i for i in intents if i in self.VALID_INTENTS]
        if not valid:
            valid = ["CONVERSATION"]

        # ── Single intent (fast path) ──
        if len(valid) == 1:
            handler = getattr(self, self._HANDLER_MAP[valid[0]])
            return handler(command, memory)

        # ── Multi-intent: parallel execution ──
        self.logger.info(f"⚡ Multi-intent [{', '.join(valid)}] — running in parallel")
        results: dict[str, str] = {}

        with ThreadPoolExecutor(max_workers=len(valid), thread_name_prefix="OrcHandler") as pool:
            futures = {
                pool.submit(getattr(self, self._HANDLER_MAP[intent]), command, memory): intent
                for intent in valid
            }
            for future in as_completed(futures, timeout=15):
                intent = futures[future]
                try:
                    result = future.result(timeout=12)
                    if result:
                        results[intent] = result
                except Exception as e:
                    self.logger.warning(f"Handler {intent} failed: {e}")

        # ── Merge in priority order ──
        parts = [results[i] for i in self._MERGE_ORDER if i in results and results[i]]
        return "\n\n".join(parts) if parts else "Done."
