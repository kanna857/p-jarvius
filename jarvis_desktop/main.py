"""
JARVIS - Background System Tray App for Windows
Run this once — Jarvis lives silently in your system tray.
Right-click the tray icon to access controls.
Say "Hey Jarvis" anytime to activate.
"""

import threading
import queue
import sys
import os
import time

if sys.platform == "win32":
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    
    # Enforce single instance
    jarvis_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "JarvisDesktopInstanceMutex")
    if ctypes.windll.kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
        sys.exit(0)

from utils.config import Config
from utils.logger import JarvisLogger
from agents.voice_agent import VoiceAgent
from agents.automation_agent import AutomationAgent
from agents.web_agent import WebAgent
from agents.memory_agent import MemoryAgent
from agents.vision_agent import VisionAgent
from agents.emotion_agent import EmotionAgent
from agents.security_agent import SecurityAgent
from agents.api_master import APIMaster
from agents.reminder_agent import ReminderAgent
from agents.task_agent import TaskAgent
from utils.state_manager import state_manager
from utils.workflow_manager import workflow_manager
from utils.cache import jarvis_cache
from agents.orchestrator import Orchestrator
from tray_app import JarvisTray

# ── Global Hotkey listener using Windows API ────────────────
def _hotkey_listener_loop(jarvis_instance):
    import keyboard
    import time
    
    def on_hotkey():
        jarvis_instance._trigger_chat_box()
        
    def on_solve_hotkey():
        jarvis_instance._trigger_solve_coding_problem()
        
    try:
        keyboard.add_hotkey('ctrl+space', on_hotkey)
        keyboard.add_hotkey('ctrl+alt+j', on_solve_hotkey)
        jarvis_instance.logger.success("Global hotkeys Ctrl+Space and Ctrl+Alt+J registered.")
        
        while jarvis_instance.running:
            time.sleep(0.5)
    except Exception as e:
        jarvis_instance.logger.error(f"Failed to register global hotkeys: {e}")
    finally:
        try:
            keyboard.remove_hotkey('ctrl+space')
        except Exception:
            pass
        try:
            keyboard.remove_hotkey('ctrl+alt+j')
        except Exception:
            pass


class Jarvis:
    def __init__(self):
        self.config = Config()
        self.logger = JarvisLogger()
        self.command_queue = queue.Queue()
        self.running = False
        self.is_muted = False

        self.logger.info("Booting JARVIS...")

        self.memory   = MemoryAgent(self.config)
        self.security = SecurityAgent(self.config)
        self.emotion  = EmotionAgent(self.config)
        self.auto     = AutomationAgent(self.config)
        self.web      = WebAgent(self.config)
        self.vision   = VisionAgent(self.config) if self.config.VISION_ENABLED else None
        self.voice    = VoiceAgent(self.command_queue, self.config)
        self.ext_api  = APIMaster(self.config)
        self.reminders = ReminderAgent(speak_callback=self.voice.speak)
        self.tasks    = TaskAgent()
        self.chat_box_proc = None

        self.logger.success("All agents online.")

        # Lazy-loaded agents (initialized on first use to speed up startup)
        self._system_agent = None
        self._messaging_agent = None
        self._personalization_agent = None
        self._desktop_agent = None
        self._research_agent = None
        self._swarm_agent = None

        # Central Orchestrator — must be created after all agents are ready
        self.orchestrator = Orchestrator(self)

    @property
    def system(self):
        """Lazy-load SystemAgent on first use."""
        if self._system_agent is None:
            from agents.system_agent import SystemAgent
            self._system_agent = SystemAgent(self.config)
            self.logger.info("SystemAgent initialized (lazy load).")
        return self._system_agent

    @property
    def messaging(self):
        """Lazy-load MessagingAgent on first use."""
        if self._messaging_agent is None:
            from agents.messaging_agent import MessagingAgent
            self._messaging_agent = MessagingAgent(self.config)
            self.logger.info("MessagingAgent initialized (lazy load).")
        return self._messaging_agent

    @property
    def personalization(self):
        """Lazy-load PersonalizationAgent on first use."""
        if self._personalization_agent is None:
            from agents.personalization_agent import PersonalizationAgent
            self._personalization_agent = PersonalizationAgent(self.config)
            self.logger.info("PersonalizationAgent initialized (lazy load).")
        return self._personalization_agent

    @property
    def desktop(self):
        """Lazy-load DesktopAgent on first use."""
        if self._desktop_agent is None:
            from agents.desktop_agent import DesktopAgent
            self._desktop_agent = DesktopAgent(
                config=self.config,
                vision_agent=self.vision,
                voice_agent=self.voice
            )
            self.logger.info("DesktopAgent initialized (lazy load).")
        return self._desktop_agent

    @property
    def research(self):
        """Lazy-load ResearchAgent on first use."""
        if self._research_agent is None:
            from agents.research_agent import ResearchAgent
            self._research_agent = ResearchAgent(
                config=self.config,
                voice_agent=self.voice
            )
            self.logger.info("ResearchAgent initialized (lazy load).")
        return self._research_agent

    @property
    def swarm(self):
        """Lazy-load SwarmAgent on first use."""
        if self._swarm_agent is None:
            from agents.swarm_agent import SwarmAgent
            self._swarm_agent = SwarmAgent(voice_agent=self.voice)
            self.logger.info("SwarmAgent initialized (lazy load).")
        return self._swarm_agent

    def _get_vision_client(self):
        """Return the best vision-capable OpenAI-compatible client."""
        if hasattr(self.voice, 'groq_client') and self.voice.groq_client and not getattr(self.voice, 'groq_disabled', False):
            return self.voice.groq_client
        if hasattr(self.voice, 'grok_client') and self.voice.grok_client and not getattr(self.voice, 'grok_disabled', False):
            return self.voice.grok_client
        if hasattr(self.voice, 'openai_client') and self.voice.openai_client:
            return self.voice.openai_client
        if hasattr(self.voice, 'gemini_client') and self.voice.gemini_client:
            return self.voice.gemini_client
        return self.voice.client

    def _start_chat_box(self):
        self.logger.info("Launching persistent Chat Box in background...")
        import subprocess, sys, os
        chat_script = os.path.join(os.path.dirname(__file__), "chat_box.py")
        self.chat_box_proc = subprocess.Popen([sys.executable, chat_script], 
                                              creationflags=subprocess.CREATE_NO_WINDOW)

    def _trigger_chat_box(self):
        self.logger.info("Ctrl+Space Hotkey detected. Waking up Quick Command Bar...")
        is_alive = False
        if hasattr(self, 'chat_box_proc') and self.chat_box_proc:
            if self.chat_box_proc.poll() is None:
                is_alive = True
                
        if not is_alive:
            self._start_chat_box()
            time.sleep(0.3)
            
        state_manager.update_key("wake_chat_box", True)

    def _trigger_solve_coding_problem(self):
        self.logger.info("Ctrl+Alt+J Hotkey detected. Solving coding problem on screen...")
        def run():
            res = self._execute_tool("solve_coding_problem", {})
            self.voice.speak(res)
        threading.Thread(target=run, daemon=True).start()

    def process_command(self, command: str) -> str:
        self.logger.info(f"CMD: {command}")

        if not self.security.is_allowed(command):
            return "That action requires your confirmation. Please try again and confirm."

        mood = self.emotion.analyze_text(command)
        cmd  = command.lower()

        # Hardcoded overrides for mute
        if "mute jarvis" in cmd or "be quiet" in cmd:
            self.is_muted = True
            return "Muted."
        elif "unmute" in cmd or "wake up" in cmd:
            self.is_muted = False
            return "I'm back. How can I help?"

        # ── Route through Orchestrator ──────────────────────────────────────
        memory = self.memory.get_short_term()

        # Check for personalization commands first ("my name is...", "call me...")
        personal_result = self.personalization.handle_command(command)
        if personal_result:
            result_text = personal_result
        else:
            # Check for research commands ("search papers...", "hypotheses...")
            research_result = self.research.handle_command(command)
            if research_result:
                result_text = research_result
            else:
                result_text = self.orchestrator.route(command, memory=memory)

        # Log interaction for personalization tracking
        self.personalization.log_interaction(command)

        if mood == "stressed":
            result_text = "Take a breath — " + result_text

        self.memory.store(command, result_text.strip())

        # Update Dashboard State
        try:
            state = state_manager.get_state()
            state["last_command"] = command
            state["last_response"] = result_text.strip()
            state["conversation_history"] = self.memory.get_short_term()
            state_manager.save_state(state)
        except Exception:
            pass

        return result_text.strip()

    def run_workflow(self, name: str) -> str:
        """Executes a saved workflow sequence."""
        steps = workflow_manager.get_workflow(name)
        if not steps:
            return f"Workflow '{name}' not found."
        
        self.logger.info(f"Starting Workflow: {name}")
        self.voice.speak(f"Executing {name} workflow.")
        
        context = ""
        for i, step in enumerate(steps):
            stype = step.get("type", "")
            self.logger.info(f"Workflow [{name}] Step {i+1}: {stype}")
            
            try:
                if stype == "tool":
                    tool_name = step.get("name")
                    args = step.get("args", {})
                    # Support primitive variable injection from previous step if user defined it
                    # (Keeping it simple for now, direct exec)
                    res = self._execute_tool(tool_name, args)
                    context = res
                
                elif stype == "ai_prompt":
                    prompt = step.get("prompt", "")
                    # Inject context from previous step if context is set
                    full_prompt = prompt.replace("{{result}}", str(context))
                    res = self.voice.ask_ai(full_prompt, short_term_memory=self.memory.get_short_term())
                    self.voice.speak(res)
                    context = res
                
                elif stype == "wait":
                    secs = float(step.get("seconds", 1))
                    time.sleep(secs)
            except Exception as e:
                self.logger.error(f"Step {i+1} failed: {e}")
                return f"Workflow failed at step {i+1}."
            
        return f"Workflow '{name}' completed."

    def get_tools(self):
        from utils.dynamic_tool_manager import dynamic_tool_manager
        dyn_tools = dynamic_tool_manager.get_tool_schemas()
        
        standard_tools = [
            {
                "type": "function",
                "function": {
                    "name": "create_dynamic_tool",
                    "description": "Dynamically creates a new python tool for JARVIS. Use this when the user requests a new custom capability or automation that cannot be resolved with existing tools. The code must define a SCHEMA dictionary and an execute(args) function.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tool_name": {"type": "string", "description": "The python filename stem (e.g. 'fetch_prices')"},
                            "tool_code": {"type": "string", "description": "The complete Python code. Must define SCHEMA = {...} and def execute(args): ..."}
                        },
                        "required": ["tool_name", "tool_code"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_swarm_task",
                    "description": "Executes a complex task collaboratively using a swarm of specialized virtual sub-agents (Planner, Coder, Critic, Aggregator). Use this for advanced reasoning, design architecture, or large complex prompts.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_description": {"type": "string", "description": "The complex task description for the swarm to solve."}
                        },
                        "required": ["task_description"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "self_maintenance",
                    "description": "Performs codebase self-maintenance: scans files for syntax warnings, compiles modules, cleans __pycache__ folders, and removes stale temporary log files.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "open_app",
                    "description": "Opens a Windows application or executable by name.",
                    "parameters": {
                        "type": "object",
                        "properties": {"name": {"type": "string", "description": "Name of the app (e.g. 'notepad', 'chrome')"}},
                        "required": ["name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "open_website",
                    "description": "Opens a website in the default browser.",
                    "parameters": {
                        "type": "object",
                        "properties": {"site": {"type": "string", "description": "URL or name of the site (e.g. 'youtube.com')"}},
                        "required": ["site"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "type_text",
                    "description": "Simulates keyboard typing to type text at the current cursor position. Use this ONLY when the user explicitly asks to type, paste, or enter text into an active window/editor. Do NOT use this if the user simply asks to write, generate, show, or explain text/code.",
                    "parameters": {
                        "type": "object",
                        "properties": {"text": {"type": "string", "description": "Text to type"}},
                        "required": ["text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "system_command",
                    "description": "Executes a system-level command.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string", 
                                "enum": ["close_window", "minimize_window", "maximize_window", "lock_screen", "screenshot", "volume_up", "volume_down", "mute_volume", "media_play_pause", "media_next", "media_prev", "shutdown", "restart", "abort_shutdown", "get_system_status"]
                            }
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_brightness",
                    "description": "Sets the screen brightness to a specific percentage.",
                    "parameters": {
                        "type": "object",
                        "properties": {"level": {"type": "integer", "description": "Brightness percentage (0-100)"}},
                        "required": ["level"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Searches the web for a query.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string", "description": "Search query"}},
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_screen",
                    "description": "Takes a screenshot and uses AI to answer a question about what is visible on the screen.",
                    "parameters": {
                        "type": "object",
                        "properties": {"question": {"type": "string", "description": "Question to ask the AI about the screen"}},
                        "required": ["question"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_file_contents",
                    "description": "Searches local documents for a keyword or phrase.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The text to search for"},
                            "search_dir": {"type": "string", "description": "Optional specific directory to search (defaults to Documents)"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_python_code",
                    "description": "Executes a python script locally to perform complex actions/computations on the PC (e.g., file cleanup, complex calculations, data gathering). Do NOT use this if the user just wants to see, write, generate, or learn a code snippet/script. Only use it when execution of python code is required to achieve the user's task.",
                    "parameters": {
                        "type": "object",
                        "properties": {"script_code": {"type": "string", "description": "The complete Python code to execute"}},
                        "required": ["script_code"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_weather",
                    "description": "Retrieves current local weather forecast for Hyderabad.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_cricket",
                    "description": "Returns the latest live cricket match scores.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_news",
                    "description": "Retrieves the latest top news headlines.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_repo_status",
                    "description": "Scans user's active repository for uncommitted files or current development progress summary.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_workflow",
                    "description": "Executes a pre-saved automation workflow chain by name.",
                    "parameters": {
                        "type": "object",
                        "properties": {"workflow_name": {"type": "string", "description": "Name of the workflow to run"}},
                        "required": ["workflow_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_reminder",
                    "description": "Sets a reminder for a specific number of minutes from now.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "minutes": {"type": "number", "description": "Minutes from now"},
                            "message": {"type": "string", "description": "The reminder text"}
                        },
                        "required": ["minutes", "message"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_emails",
                    "description": "Connects to the user's email inbox and reads the latest unread emails out loud.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer", "description": "Number of emails to read (default 3)"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "add_task",
                    "description": "Adds a new task to the user's todo list / task manager.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "The title or action of the task (e.g. 'Buy milk')"},
                            "description": {"type": "string", "description": "Optional details or notes for the task"},
                            "priority": {"type": "string", "enum": ["Low", "Medium", "High"], "description": "Priority level of the task"},
                            "due_date": {"type": "string", "description": "Optional due date or time for the task"}
                        },
                        "required": ["title"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_tasks",
                    "description": "Lists tasks from the user's todo list, optionally filtered by status.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "enum": ["Pending", "Completed"], "description": "Filter by task status (defaults to Pending)"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "complete_task",
                    "description": "Marks a task as completed in the task manager using its ID or title.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "identifier": {"type": "string", "description": "The task ID (number) or part of the task title (e.g. 'Buy milk')"}
                        },
                        "required": ["identifier"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_task",
                    "description": "Deletes/removes a task from the task manager using its ID or title.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "identifier": {"type": "string", "description": "The task ID (number) or part of the task title to delete"}
                        },
                        "required": ["identifier"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "solve_coding_problem",
                    "description": "Takes a screenshot of the user's screen, identifies a coding challenge, programming problem, or a bug/error/traceback currently visible/displayed on their screen, generates the correct solution or fixed code, and automatically pastes it into the active editor. Use this ONLY if the user explicitly asks to solve a problem/question or fix an error/bug shown on their screen. Do NOT use this if the user asks to write, generate, or explain code generally without referring to a question or error on their screen.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_joke",
                    "description": "Tells a random funny, safe joke.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_definition",
                    "description": "Looks up the dictionary definition of an English word.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "word": {"type": "string", "description": "The English word to define"}
                        },
                        "required": ["word"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_quote",
                    "description": "Gets a random motivational or inspirational quote.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "convert_currency",
                    "description": "Converts an amount of money from one currency code to another (e.g. USD to INR).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "amount": {"type": "number", "description": "The amount to convert"},
                            "from_curr": {"type": "string", "description": "The source currency code (e.g. USD, EUR)"},
                            "to_curr": {"type": "string", "description": "The destination currency code (e.g. INR, GBP)"}
                        },
                        "required": ["amount", "from_curr", "to_curr"]
                    }
                }
            },
            # ── Cricket Intelligence ──────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_cricket_matches",
                    "description": "Returns a list of upcoming and recent cricket matches (schedules).",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_cricket_match_info",
                    "description": "Returns detailed info, venue, and scorecard of a specific cricket match by its match ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {"match_id": {"type": "string", "description": "The unique cricket match ID from CricAPI"}},
                        "required": ["match_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_cricket_player",
                    "description": "Searches for a cricket player by name. Returns player name, country, and their ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {"name": {"type": "string", "description": "The player's name to search (e.g. Virat Kohli)"}},
                        "required": ["name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_cricket_player_info",
                    "description": "Returns detailed bio, batting style, bowling style, and career info for a cricket player by their ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {"player_id": {"type": "string", "description": "The unique player ID from CricAPI (get it from search_cricket_player first)"}},
                        "required": ["player_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_cricket_squad",
                    "description": "Returns the playing squads (team lineups) for a specific cricket match by its match ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {"match_id": {"type": "string", "description": "The unique cricket match ID"}},
                        "required": ["match_id"]
                    }
                }
            },
            # ── System Agent (Deep PC Control) ───────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "kill_process",
                    "description": "Kills a running process by name or PID.",
                    "parameters": {
                        "type": "object",
                        "properties": {"name_or_pid": {"type": "string", "description": "Process name (e.g. 'chrome') or PID number"}},
                        "required": ["name_or_pid"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_processes",
                    "description": "Lists running processes, optionally filtered by name. Shows PID, CPU%, RAM%.",
                    "parameters": {
                        "type": "object",
                        "properties": {"filter_name": {"type": "string", "description": "Optional process name filter"}}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_battery",
                    "description": "Returns detailed battery status (percentage, charging state, time remaining).",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_full_system_status",
                    "description": "Returns comprehensive system health: CPU per-core, RAM, Disk, Battery, Network, Uptime.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_network_info",
                    "description": "Returns network info: Wi-Fi SSID, signal, IP addresses, data usage.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            # ── Messaging ─────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "send_whatsapp",
                    "description": "Sends a WhatsApp message to a phone number via WhatsApp Web.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "phone": {"type": "string", "description": "Phone number with country code (e.g. +919876543210)"},
                            "message": {"type": "string", "description": "The message to send"}
                        },
                        "required": ["phone", "message"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_telegram",
                    "description": "Sends a Telegram message via the JARVIS bot.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string", "description": "The message to send"},
                            "chat_id": {"type": "string", "description": "Telegram chat ID (optional, uses default)"}
                        },
                        "required": ["message"]
                    }
                }
            },
            # ── Vision (Webcam) ──────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "detect_objects",
                    "description": "Uses the webcam + YOLO to detect and list objects visible in front of the camera.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "count_faces",
                    "description": "Counts the number of human faces currently visible on the webcam.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            # ── Desktop Agent (Autonomous Control) ──────────────────
            {
                "type": "function",
                "function": {
                    "name": "execute_desktop_task",
                    "description": "Executes a multi-step desktop automation task described in natural language. Uses Vision AI to observe the screen and PyAutoGUI to act like a human (clicking, typing, scrolling). Handles error dialogs automatically. Use this when the user wants to automate a complex desktop workflow.",
                    "parameters": {
                        "type": "object",
                        "properties": {"task": {"type": "string", "description": "Natural language description of the desktop task to perform"}},
                        "required": ["task"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "start_screen_monitor",
                    "description": "Starts monitoring the screen for visual changes in the background. Reports when significant changes occur.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            # ── Research Scientist ──────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "search_papers",
                    "description": "Searches arXiv for academic/research papers on a topic. Returns titles, authors, dates, and abstracts.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search topic (e.g. 'transformer attention mechanism')"},
                            "max_results": {"type": "integer", "description": "Number of papers to return (default 5)"},
                            "category": {"type": "string", "description": "arXiv category filter (e.g. cs.AI, cs.CL, physics)"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "summarize_paper",
                    "description": "Fetches an arXiv paper by ID and generates an AI summary of its key contributions, methods, results, and limitations.",
                    "parameters": {
                        "type": "object",
                        "properties": {"arxiv_id": {"type": "string", "description": "The arXiv paper ID (e.g. 2301.12345)"}},
                        "required": ["arxiv_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_hypotheses",
                    "description": "Generates 3-5 novel, testable research hypotheses for a given topic using AI.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string", "description": "Research topic to generate hypotheses for"},
                            "context": {"type": "string", "description": "Optional additional context or constraints"}
                        },
                        "required": ["topic"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "plan_experiment",
                    "description": "Designs a detailed experiment plan for testing a research hypothesis.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "hypothesis": {"type": "string", "description": "The hypothesis to design an experiment for"},
                            "constraints": {"type": "string", "description": "Optional resource constraints or limitations"}
                        },
                        "required": ["hypothesis"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "literature_review",
                    "description": "Performs a full automated literature review: searches papers, summarizes each, compares findings, identifies gaps, and generates new hypotheses.",
                    "parameters": {
                        "type": "object",
                        "properties": {"topic": {"type": "string", "description": "Research topic for the literature review"}},
                        "required": ["topic"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_trending_papers",
                    "description": "Gets the latest trending papers from arXiv in a specific category.",
                    "parameters": {
                        "type": "object",
                        "properties": {"category": {"type": "string", "description": "arXiv category (e.g. cs.AI, cs.CL, cs.CV, physics, math)"}},
                        "required": ["category"]
                    }
                }
            }
        ]
        return standard_tools + dyn_tools

    def _execute_tool(self, name: str, args: dict) -> str:
        # Check if the tool needs a clear screen (screenshots/vision)
        needs_hide = name in ["analyze_screen", "solve_coding_problem"] or (name == "system_command" and (args or {}).get("command") == "screenshot")
        
        if needs_hide:
            state_manager.update_key("hide_chat_box", True)
            time.sleep(0.4)  # Wait for chat box to withdraw
            
        try:
            res = self._execute_tool_inner(name, args)
            success = 0 if (isinstance(res, str) and (res.startswith("Error") or "failed" in res.lower())) else 1
            import json
            try:
                self.personalization.log_rl_feedback(
                    tool_name=name,
                    arguments=json.dumps(args),
                    success=success,
                    rating=success,
                    notes=res[:200] if not success else "Executed successfully."
                )
            except Exception:
                pass
            return res
        except Exception as e:
            import json
            try:
                self.personalization.log_rl_feedback(
                    tool_name=name,
                    arguments=json.dumps(args),
                    success=0,
                    rating=0,
                    notes=str(e)
                )
            except Exception:
                pass
            raise e
        finally:
            if needs_hide:
                state_manager.update_key("hide_chat_box", False)

    def _execute_tool_inner(self, name: str, args: dict) -> str:
        if not isinstance(args, dict):
            args = {}
        self.logger.info(f"Executing tool: {name} with args {args}")
        
        # Intercept dynamic tools first
        from utils.dynamic_tool_manager import dynamic_tool_manager
        if dynamic_tool_manager.has_tool(name):
            return dynamic_tool_manager.execute_tool(name, args)
            
        friendly_msgs = {
            "self_maintenance": "Running codebase self-maintenance checks.",
            "execute_swarm_task": "Spawning a multi-agent swarm to collaboratively solve your task.",
            "create_dynamic_tool": "Creating a new custom tool dynamically.",
            "open_app": f"Opening {args.get('name', 'application')}.",
            "open_website": f"Opening {args.get('site', 'website')}.",
            "type_text": "Typing requested text.",
            "system_command": f"Running {args.get('command', 'system command').replace('_', ' ')}.",
            "set_brightness": f"Setting brightness to {args.get('level', '')}.",
            "search_web": "Searching the web.",
            "analyze_screen": "Analyzing the screen.",
            "search_file_contents": "Searching files.",
            "execute_python_code": "Running python code.",
            "check_weather": "Checking weather.",
            "check_news": "Fetching the latest news.",
            "check_cricket": "Checking cricket scores.",
            "get_repo_status": "Checking repository.",
            "execute_workflow": f"Running {args.get('workflow_name', 'workflow')}.",
            "set_reminder": "Setting your reminder.",
            "read_emails": "Fetching your latest unread emails.",
            "add_task": f"Adding task: {args.get('title', '')}.",
            "list_tasks": "Retrieving your task list.",
            "complete_task": f"Completing task: {args.get('identifier', '')}.",
            "delete_task": f"Deleting task: {args.get('identifier', '')}.",
            "get_joke": "Fetching a random joke.",
            "get_definition": f"Looking up definition of {args.get('word', 'word')}.",
            "get_quote": "Fetching a motivational quote.",
            "convert_currency": "Converting currency.",
            "solve_coding_problem": "Analyzing coding website to write the correct solution code.",
            "execute_desktop_task": "Running autonomous desktop automation.",
            "start_screen_monitor": "Starting screen change monitoring.",
            "search_papers": "Searching research papers.",
            "summarize_paper": "Summarizing paper.",
            "generate_hypotheses": "Generating research hypotheses.",
            "plan_experiment": "Planning research experiment.",
            "literature_review": "Conducting literature review.",
            "get_trending_papers": "Fetching trending academic papers."
        }
        self.voice.speak(friendly_msgs.get(name, f"Executing {name.replace('_', ' ')}."))
        
        try:
            if name == "create_dynamic_tool":
                tool_name = args["tool_name"]
                tool_code = args["tool_code"]
                try:
                    compile(tool_code, f"<dynamic_tool_{tool_name}>", "exec")
                except Exception as syntax_err:
                    return f"Error: Invalid Python syntax in the code provided: {syntax_err}"
                import os
                from pathlib import Path
                tools_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "dynamic_tools"
                tools_dir.mkdir(parents=True, exist_ok=True)
                file_path = tools_dir / f"{tool_name}.py"
                try:
                    file_path.write_text(tool_code, encoding="utf-8")
                    from utils.dynamic_tool_manager import dynamic_tool_manager
                    dynamic_tool_manager.load_all_tools()
                    return f"Success: Custom tool '{tool_name}' created, compiled, and registered successfully."
                except Exception as write_err:
                    return f"Error writing custom tool file: {write_err}"
            elif name == "execute_swarm_task":
                return self.swarm.run_collaborative_task(args["task_description"])
            elif name == "self_maintenance":
                return self.system.maintain_codebase()
            elif name == "open_app": return self.auto.open_app(args["name"])
            elif name == "open_website": return self.auto.open_website(args["site"])
            elif name == "type_text": return self.auto.type_text(args["text"])
            elif name == "system_command":
                cmd = args["command"]
                if cmd == "close_window": return self.auto.close_active_window()
                elif cmd == "minimize_window": return self.auto.minimize_window()
                elif cmd == "maximize_window": return self.auto.maximize_window()
                elif cmd == "lock_screen": return self.auto.lock_screen()
                elif cmd == "screenshot": return self.auto.screenshot()
                elif cmd == "volume_up": return self.auto.volume_up()
                elif cmd == "volume_down": return self.auto.volume_down()
                elif cmd == "mute_volume": return self.auto.mute_volume()
                elif cmd == "media_play_pause": return self.auto.media_play_pause()
                elif cmd == "media_next": return self.auto.media_next()
                elif cmd == "media_prev": return self.auto.media_prev()
                elif cmd == "shutdown": return self.auto.shutdown()
                elif cmd == "restart": return self.auto.restart()
                elif cmd == "abort_shutdown": return self.auto.abort_shutdown()
                elif cmd == "get_system_status": return self.auto.get_system_status()
            elif name == "set_brightness": return self.auto.set_brightness(args["level"])
            elif name == "search_web": return self.web.search(args["query"])
            elif name == "analyze_screen":
                if self.vision: return self.vision.analyze_screen_with_ai(self._get_vision_client(), args.get("question", "What's on the screen?"))
                return "Vision agent is not enabled."
            elif name == "search_file_contents":
                return self.auto.search_file_contents(args["query"], args.get("search_dir"))
            elif name == "execute_python_code":
                return self.auto.execute_python_code(args["script_code"])
            elif name == "check_weather":
                return self.ext_api.get_hyderabad_weather()
            elif name == "check_news":
                return self.ext_api.get_latest_news()
            elif name == "check_cricket":
                return self.ext_api.check_live_cricket()
            elif name == "get_repo_status":
                return self.ext_api.get_local_github_diff()
            elif name == "execute_workflow":
                return self.run_workflow(args["workflow_name"])
            elif name == "set_reminder":
                return self.reminders.set_reminder(args["minutes"], args["message"])
            elif name == "read_emails":
                return self.ext_api.read_latest_emails(args.get("count", 3))
            elif name == "add_task":
                return self.tasks.add_task(args["title"], args.get("description"), args.get("priority", "Medium"), args.get("due_date"))
            elif name == "list_tasks":
                status = args.get("status", "Pending")
                tasks = self.tasks.get_tasks(status=status)
                if not tasks:
                    return f"You have no {status.lower()} tasks."
                resp = f"Here are your {status.lower()} tasks:\n"
                for t in tasks:
                    due = f" due {t['due_date']}" if t.get("due_date") else ""
                    resp += f"- [ID: {t['id']}] {t['title']} ({t['priority']} priority){due}\n"
                return resp
            elif name == "complete_task":
                return self.tasks.complete_task(args["identifier"])
            elif name == "delete_task":
                return self.tasks.delete_task(args["identifier"])
            elif name == "get_joke":
                return self.ext_api.get_joke()
            elif name == "get_definition":
                return self.ext_api.get_definition(args["word"])
            elif name == "get_quote":
                return self.ext_api.get_quote()
            elif name == "convert_currency":
                return self.ext_api.convert_currency(args["amount"], args["from_curr"], args["to_curr"])
            # ── Cricket Intelligence ──────────────────────────────
            elif name == "get_cricket_matches":
                return self.ext_api.get_cricket_matches()
            elif name == "get_cricket_match_info":
                return self.ext_api.get_cricket_match_info(args["match_id"])
            elif name == "search_cricket_player":
                return self.ext_api.search_cricket_player(args["name"])
            elif name == "get_cricket_player_info":
                return self.ext_api.get_cricket_player_info(args["player_id"])
            elif name == "get_cricket_squad":
                return self.ext_api.get_cricket_squad(args["match_id"])
            # ── System Agent (Deep PC Control) ────────────────────
            elif name == "kill_process":
                return self.system.kill_process(args["name_or_pid"])
            elif name == "list_processes":
                return self.system.list_processes(args.get("filter_name"))
            elif name == "get_battery":
                return self.system.get_battery()
            elif name == "get_full_system_status":
                return self.system.get_full_system_status()
            elif name == "get_network_info":
                return self.system.get_network_info()
            # ── Messaging ─────────────────────────────────────────
            elif name == "send_whatsapp":
                return self.messaging.send_whatsapp(args["phone"], args["message"])
            elif name == "send_telegram":
                return self.messaging.send_telegram(args["message"], args.get("chat_id"))
            # ── Vision (Webcam) ───────────────────────────────────
            elif name == "detect_objects":
                if self.vision:
                    objs = self.vision.detect_objects()
                    return f"Objects detected: {', '.join(objs)}." if objs else "No objects detected in webcam view."
                return "Vision agent is not enabled."
            elif name == "count_faces":
                if self.vision:
                    n = self.vision.count_faces()
                    return f"I detect {n} face{'s' if n != 1 else ''} in the webcam view."
                return "Vision agent is not enabled."
            # ── Desktop Agent (Autonomous Control) ──────────────────
            elif name == "execute_desktop_task":
                return self.desktop.execute_desktop_task(args["task"], client=self._get_vision_client())
            elif name == "start_screen_monitor":
                return self.desktop.start_screen_monitor()
            # ── Research Scientist ──────────────────────────────────
            elif name == "search_papers":
                return self.research.search_papers(
                    query=args["query"], 
                    max_results=args.get("max_results", 5), 
                    category=args.get("category")
                )
            elif name == "summarize_paper":
                return self.research.summarize_paper(args["arxiv_id"])
            elif name == "generate_hypotheses":
                return self.research.generate_hypotheses(
                    topic=args["topic"], 
                    context=args.get("context")
                )
            elif name == "plan_experiment":
                return self.research.plan_experiment(
                    hypothesis=args["hypothesis"], 
                    constraints=args.get("constraints")
                )
            elif name == "literature_review":
                return self.research.literature_review(args["topic"])
            elif name == "get_trending_papers":
                return self.research.get_trending_papers(args["category"])
            elif name == "solve_coding_problem":
                # 1. Ask vision system to get solution
                prompt = (
                    "Analyze this screenshot of the user's screen. It displays a coding task, a fill-in-the-blank question, "
                    "or an editor with a bug/error.\n\n"
                    "Identify the following:\n"
                    "1. Is it a standard full-editor coding challenge (e.g. LeetCode) where the entire code should be replaced?\n"
                    "2. Is it a fill-in-the-blank question or a cursor-focused input field where only a specific snippet or word/statement "
                    "should be pasted/inserted at the current cursor position?\n"
                    "3. Is there a bug, syntax error, or compile error visible? If so, analyze the error and the code to figure out the fix.\n\n"
                    "Determine the correct solution code/text. If it's a fill-in-the-blank or a cursor insertion, determine ONLY the exact "
                    "missing code/text to fill the blank. If it's a full editor, determine the complete correct code.\n\n"
                    "You must return your response in JSON format. Do not write any conversational text before or after the JSON. "
                    "Use the following JSON structure:\n"
                    "{\n"
                    "  \"mode\": \"replace\" or \"cursor\",\n"
                    "  \"explanation\": \"Brief explanation of what was detected (e.g. 'Detected a fill-in-the-blank input. Providing the missing statement.')\",\n"
                    "  \"code\": \"The code or text to write. (Ensure newlines and quotes are properly escaped in the JSON string)\"\n"
                    "}\n\n"
                    "Values for \"mode\":\n"
                    "- Use \"replace\" ONLY if it is a standard full-editor coding screen (like LeetCode or VS Code editor) where we want to overwrite the entire editor content.\n"
                    "- Use \"cursor\" if it is a fill-in-the-blank input, a small text box, or a specific blank space where the user's cursor is already focused.\n"
                )
                solution_raw = self.vision.analyze_screen_with_ai(self._get_vision_client(), prompt, max_tokens=1000)
                
                # Clean up and parse the JSON response
                import re
                import json
                
                def parse_json_response(response_text):
                    text = response_text.strip()
                    # Remove ```json ... ``` or ``` ... ```
                    json_match = re.search(r'```(?:json)?\n(.*?)\n```', text, re.DOTALL)
                    if json_match:
                        text = json_match.group(1).strip()
                    else:
                        start_idx = text.find('{')
                        end_idx = text.rfind('}')
                        if start_idx != -1 and end_idx != -1:
                            text = text[start_idx:end_idx+1].strip()
                    try:
                        return json.loads(text)
                    except Exception:
                        # Fallback parsing using regex in case of unescaped newlines or simple formatting
                        try:
                            mode_match = re.search(r'"mode"\s*:\s*"([^"]+)"', text)
                            code_match = re.search(r'"code"\s*:\s*"(.*?)"', text, re.DOTALL)
                            explanation_match = re.search(r'"explanation"\s*:\s*"(.*?)"', text, re.DOTALL)
                            
                            mode = mode_match.group(1) if mode_match else "cursor"
                            explanation = explanation_match.group(1) if explanation_match else ""
                            
                            if code_match:
                                code_content = code_match.group(1)
                                # Unescape basic escapes
                                code_content = code_content.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace('\\\\', '\\')
                                return {"mode": mode, "code": code_content, "explanation": explanation}
                        except Exception:
                            pass
                        # Ultimate fallback: treat entire raw response as code to paste at cursor
                        return {"mode": "cursor", "code": response_text, "explanation": "Fallback due to JSON parse error."}

                parsed = parse_json_response(solution_raw)
                mode = parsed.get("mode", "cursor")
                code_to_paste = parsed.get("code", "").strip()
                explanation = parsed.get("explanation", "Solving problem")
                
                self.logger.info(f"Solve coding problem - Mode: {mode}, Expl: {explanation}")
                
                if not code_to_paste:
                    return "I couldn't identify the solution or code to write."
                
                # 2. Copy code to clipboard using tkinter, backing up current clipboard
                import tkinter as tk
                old_clip = None
                try:
                    root = tk.Tk()
                    root.withdraw()
                    try:
                        old_clip = root.clipboard_get()
                    except Exception:
                        pass
                    
                    root.clipboard_clear()
                    root.clipboard_append(code_to_paste)
                    root.update()
                    root.destroy()
                except Exception as clipboard_err:
                    self.logger.error(f"Failed to copy solution code to clipboard: {clipboard_err}")
                    return "I found the solution, but was unable to copy it to the clipboard."
                
                # 3. Focus and paste/type solution
                # Pause briefly to allow focus to return to the active application window
                time.sleep(0.6)
                
                import pyautogui
                if mode == "replace":
                    try:
                        # Focus the editor by clicking the middle of the right-half of the screen
                        width, height = pyautogui.size()
                        click_x = int(width * 0.75)
                        click_y = int(height * 0.5)
                        pyautogui.click(click_x, click_y)
                        time.sleep(0.3)
                    except Exception as click_err:
                        self.logger.warning(f"Could not automatically click editor: {click_err}")
                    
                    # Select all and delete
                    pyautogui.hotkey('ctrl', 'a')
                    time.sleep(0.15)
                    pyautogui.press('backspace')
                    time.sleep(0.15)
                
                # Paste the clipboard content
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.15) # Pause to let the paste complete
                
                # Restore the previous clipboard content
                if old_clip is not None:
                    try:
                        root = tk.Tk()
                        root.withdraw()
                        root.clipboard_clear()
                        root.clipboard_append(old_clip)
                        root.update()
                        root.destroy()
                    except Exception:
                        pass
                
                return f"I have solved the problem ({explanation}) and entered the solution directly (clipboard restored)."
        except Exception as e:
            return f"Error executing {name}: {e}"
        return "Executed."

    def command_loop(self):
        """Main loop: pull commands from queue and respond"""
        while self.running:
            try:
                command = self.command_queue.get(timeout=0.1)
                response = self.process_command(command)
                if response and not self.is_muted:
                    # Filter out markdown code blocks to avoid reading code aloud
                    speak_text = response
                    if "```" in response:
                        import re
                        parts = re.split(r'```.*?```', response, flags=re.DOTALL)
                        clean_parts = [p.strip() for p in parts if p.strip()]
                        if clean_parts:
                            speak_text = " ".join(clean_parts)
                        else:
                            speak_text = "Here is the code."
                    self.voice.speak(speak_text)
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Command loop error: {e}")

    def _startup_greeting_loop(self):
        """Wait until the owner's face is recognized via webcam, then greet."""
        import datetime
        import os
        self.logger.info("Startup Greeting Agent monitoring for your face...")
        
        user_img = os.path.join(os.path.dirname(__file__), "user_face.jpg")
        
        # Give it up to 5 mins to find the user, or stop monitoring after one successful greeting
        attempts = 0
        max_attempts = 60  # (60 * 5 seconds = 300 seconds / 5 minutes)
        
        while self.running and attempts < max_attempts:
            try:
                attempts += 1
                time.sleep(5)
                if not self.vision or not self.vision.running:
                    continue
                
                # Quick local check: Is anyone there?
                if self.vision.count_faces() > 0:
                    self.logger.info("Face detected! Verifying identity...")
                    # AI check: Is it the specific user?
                    if self.vision.verify_user_face(self._get_vision_client(), user_img):
                        now = datetime.datetime.now()
                        hour = now.hour
                        if 5 <= hour < 12:
                            greeting = "Good morning."
                        elif 12 <= hour < 17:
                            greeting = "Good afternoon."
                        else:
                            greeting = "Good evening."
                        
                        self.logger.success(f"Owner verified. Saying: {greeting}")
                        self.voice.speak(greeting)
                        break  # Done! We greeted the user.
                    else:
                        self.logger.warning("Face did not match user profile.")
            except Exception as e:
                self.logger.error(f"Greeting agent loop error: {e}")
    def _telemetry_loop(self):
        """Pushes live computer stats and health metrics to the cross-process state manager."""
        import psutil
        self.logger.info("Dashboard Telemetry Broadcast initiated.")
        while self.running:
            try:
                state = state_manager.get_state()
                state["status"] = "Active" if not self.is_muted else "Muted"
                state["cpu"] = psutil.cpu_percent()
                state["ram"] = psutil.virtual_memory().percent
                state["vision_active"] = bool(self.vision and self.vision.running)
                
                # Check object detection cache if active
                if self.vision and self.vision.yolo_available and self.vision.current_frame is not None:
                    # To avoid performance load, we won't run full YOLO here, only update flags
                    state["face_detected"] = self.vision.count_faces() > 0
                
                state_manager.save_state(state)
            except Exception:
                pass
            time.sleep(2.0)

    def _dashboard_command_listener(self):
        """Watches the state manager for injected commands from dashboard."""
        self.logger.info("Dashboard Command Listener active.")
        while self.running:
            try:
                cmds = state_manager.pop_commands()
                for c in cmds:
                    self.logger.info(f"UI Injected Cmd: {c}")
                    self.command_queue.put(c)
            except Exception:
                pass
            time.sleep(0.1)

    def _proactive_assistant_loop(self):
        """Periodically check user habits and status to anticipate tasks and proactively assist."""
        self.logger.info("Proactive assistant loop started.")
        # Wait a bit after startup for other agents to settle
        time.sleep(30)
        while self.running:
            try:
                import datetime
                now = datetime.datetime.now()
                hour = now.hour
                day_of_week = now.weekday()
                
                # Query top habits for this specific time
                habits = self.personalization.get_habits_for_time(hour, day_of_week)
                if habits:
                    top_action, count = habits[0]
                    # If user has run this action more than 3 times at this hour/day
                    if count >= 3:
                        self.logger.info(f"Proactive: User frequently runs {top_action} at this time (count={count}).")
                        
                        # Trigger alert or pre-fetch information based on category
                        if top_action == "weather":
                            weather_info = self.ext_api.get_hyderabad_weather()
                            self.voice.speak(f"Pardon me, since you normally check the weather around this time, here is the update: {weather_info}")
                        elif top_action == "news":
                            news_info = self.ext_api.get_latest_news()
                            self.voice.speak(f"Here is your routine news briefing: {news_info}")
                        elif top_action == "email":
                            email_info = self.ext_api.read_latest_emails(count=2)
                            self.voice.speak(f"Just checking: you normally look at emails now. {email_info}")
                
                # Check system metrics for proactive help
                import psutil
                battery = psutil.sensors_battery()
                if battery and battery.percent < 20 and not battery.power_plugged:
                    self.voice.speak("Warning: Your laptop battery is below 20 percent and not charging. Please plug in.")
                    
            except Exception as e:
                self.logger.error(f"Proactive assistant loop error: {e}")
            
            # Check every 10 minutes (600 seconds)
            for _ in range(600):
                if not self.running:
                    break
                time.sleep(1)

    def start(self):
        self.running = True
        
        # Set status to Active/Muted immediately on startup
        state = state_manager.get_state()
        state["status"] = "Active" if not self.is_muted else "Muted"
        state_manager.save_state(state)

        # Voice listener thread (wake word → STT)
        threading.Thread(target=self.voice.listen_loop, daemon=True, name="VoiceListener").start()

        # Vision loop thread (optional)
        if self.vision and self.config.VISION_ENABLED:
            threading.Thread(target=self.vision.run_background, daemon=True, name="Vision").start()
            # Start the greeting loop only if vision exists and is on
            threading.Thread(target=self._startup_greeting_loop, daemon=True, name="GreetingMonitor").start()

        # Command processor thread
        threading.Thread(target=self.command_loop, daemon=True, name="CmdLoop").start()
        
        # Dashboard Input Listener
        threading.Thread(target=self._dashboard_command_listener, daemon=True, name="UICmd").start()
        
        # Reminder Background Loop
        self.reminders.start()

        # Ctrl+Space Global Hotkey Listener
        threading.Thread(target=_hotkey_listener_loop, args=(self,), daemon=True, name="HotkeyListener").start()

        # Proactive Assistant Loop
        threading.Thread(target=self._proactive_assistant_loop, daemon=True, name="ProactiveAssistant").start()

        # Launch persistent chat box in background
        self._start_chat_box()

        self.voice.speak("Jarvis is online.")
        self.logger.success("JARVIS running in background. Listening for 'Jarvis' or 'Hey Jarvis'...")

    def stop(self):
        self.running = False
        self.voice.stop()
        if self.vision:
            self.vision.stop()
        self.reminders.stop()
        
        # Signal chat box to terminate by setting status to Offline
        state_manager.update_key("status", "Offline")
        
        # Also terminate process directly if running
        if hasattr(self, 'chat_box_proc') and self.chat_box_proc:
            try:
                self.chat_box_proc.terminate()
            except Exception:
                pass
                
        self.logger.info("JARVIS shutdown complete.")


def main():
    jarvis = Jarvis()
    jarvis.start()

    # Hand control to the system tray (blocks until user quits)
    tray = JarvisTray(jarvis)
    tray.run()  # blocking — stays alive here

    jarvis.stop()
    sys.exit(0)


if __name__ == "__main__":
    main()
