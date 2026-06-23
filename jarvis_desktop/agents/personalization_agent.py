"""
JARVIS PersonalizationAgent — Learns User Preferences
──────────────────────────────────────────────────────
Stores and retrieves user profile data to make responses personalized.

Tracks:
  - Name, location, language preferences
  - Favorite apps, websites, music genres
  - Interaction patterns (most-asked topics)
  - Custom nicknames and response style preferences
  - Frequently used commands (auto-suggest)

Storage: SQLite at ~/.jarvis/user_profile.db
"""

import sqlite3
import json
import time
from pathlib import Path
from collections import Counter
from utils.logger import JarvisLogger


class PersonalizationAgent:
    DB = Path.home() / ".jarvis" / "user_profile.db"

    def __init__(self, config=None):
        self.config = config
        self.logger = JarvisLogger("Personal")
        self.DB.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._profile_cache = None  # In-memory cache
        self.logger.success("Personalization agent ready")

    def _init_db(self):
        with sqlite3.connect(self.DB) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS profile (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at REAL
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT,
                command TEXT,
                timestamp REAL
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS knowledge_graph (
                subject TEXT,
                relation TEXT,
                object TEXT,
                updated_at REAL,
                PRIMARY KEY (subject, relation, object)
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS habits (
                hour INTEGER,
                day_of_week INTEGER,
                action TEXT,
                count INTEGER,
                PRIMARY KEY (hour, day_of_week, action)
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS rl_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT,
                arguments TEXT,
                success INTEGER,
                rating INTEGER,
                notes TEXT,
                timestamp REAL
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS projects (
                path TEXT PRIMARY KEY,
                name TEXT,
                status TEXT,
                summary TEXT,
                current_goals TEXT,
                updated_at REAL
            )""")
            c.commit()

    # ── Profile CRUD ──────────────────────────────────────────────────────────

    def set_preference(self, key: str, value: str) -> str:
        """Store a user preference."""
        key = key.strip().lower().replace(" ", "_")
        with sqlite3.connect(self.DB) as c:
            c.execute(
                "INSERT OR REPLACE INTO profile (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, time.time())
            )
            c.commit()
        self._profile_cache = None  # Invalidate cache
        self.logger.info(f"Preference set: {key} = {value}")
        return f"✅ I'll remember that: {key} = {value}"

    def get_preference(self, key: str) -> str:
        """Retrieve a user preference."""
        key = key.strip().lower().replace(" ", "_")
        with sqlite3.connect(self.DB) as c:
            row = c.execute("SELECT value FROM profile WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def get_all_preferences(self) -> dict:
        """Returns all stored preferences as a dict."""
        if self._profile_cache:
            return self._profile_cache
        with sqlite3.connect(self.DB) as c:
            rows = c.execute("SELECT key, value FROM profile").fetchall()
        self._profile_cache = {k: v for k, v in rows}
        return self._profile_cache

    def delete_preference(self, key: str) -> str:
        """Delete a user preference."""
        key = key.strip().lower().replace(" ", "_")
        with sqlite3.connect(self.DB) as c:
            c.execute("DELETE FROM profile WHERE key = ?", (key,))
            c.commit()
        self._profile_cache = None
        return f"Preference '{key}' deleted."

    # ── Interaction Tracking ──────────────────────────────────────────────────

    def log_interaction(self, command: str, topic: str = None):
        """Log a user interaction for pattern analysis."""
        if not topic:
            # Auto-classify topic from keywords
            cmd = command.lower()
            if any(k in cmd for k in ("weather", "temperature")):
                topic = "weather"
            elif any(k in cmd for k in ("news", "headline")):
                topic = "news"
            elif any(k in cmd for k in ("cricket", "score", "match")):
                topic = "cricket"
            elif any(k in cmd for k in ("open", "launch", "run")):
                topic = "app_control"
            elif any(k in cmd for k in ("code", "python", "program", "debug")):
                topic = "coding"
            elif any(k in cmd for k in ("music", "play", "spotify")):
                topic = "entertainment"
            elif any(k in cmd for k in ("email", "mail", "inbox")):
                topic = "email"
            elif any(k in cmd for k in ("task", "todo", "remind")):
                topic = "productivity"
            else:
                topic = "general"

        try:
            with sqlite3.connect(self.DB) as c:
                c.execute(
                    "INSERT INTO interactions (topic, command, timestamp) VALUES (?, ?, ?)",
                    (topic, command[:200], time.time())
                )
                c.commit()
            self.log_habit(topic)
        except Exception:
            pass

    def get_top_topics(self, n: int = 5) -> list[tuple[str, int]]:
        """Returns the user's most-interacted topics."""
        with sqlite3.connect(self.DB) as c:
            rows = c.execute(
                "SELECT topic, COUNT(*) as cnt FROM interactions "
                "GROUP BY topic ORDER BY cnt DESC LIMIT ?", (n,)
            ).fetchall()
        return rows

    def get_frequent_commands(self, n: int = 5) -> list[str]:
        """Returns the user's most-frequent commands."""
        with sqlite3.connect(self.DB) as c:
            rows = c.execute(
                "SELECT command, COUNT(*) as cnt FROM interactions "
                "GROUP BY command ORDER BY cnt DESC LIMIT ?", (n,)
            ).fetchall()
        return [r[0] for r in rows]

    # ── Profile Summary (for LLM system prompt injection) ─────────────────────

    def get_profile_summary(self) -> str:
        """
        Returns a compact profile string suitable for injecting into
        the LLM system prompt. This makes all responses personalized.
        """
        prefs = self.get_all_preferences()
        if not prefs:
            return ""

        lines = ["User Profile:"]
        # Key personal info
        name = prefs.get("name") or prefs.get("user_name")
        if name:
            lines.append(f"  Name: {name}")
        loc = prefs.get("location") or prefs.get("city")
        if loc:
            lines.append(f"  Location: {loc}")
        lang = prefs.get("language") or prefs.get("preferred_language")
        if lang:
            lines.append(f"  Language: {lang}")
        style = prefs.get("response_style") or prefs.get("style")
        if style:
            lines.append(f"  Response Style: {style}")

        # Other preferences
        skip = {"name", "user_name", "location", "city", "language",
                "preferred_language", "response_style", "style"}
        for k, v in prefs.items():
            if k not in skip:
                lines.append(f"  {k.replace('_', ' ').title()}: {v}")

        # Top topics
        topics = self.get_top_topics(3)
        if topics:
            topic_str = ", ".join(f"{t[0]}({t[1]})" for t in topics)
            lines.append(f"  Interests: {topic_str}")

        return "\n".join(lines) if len(lines) > 1 else ""

    # ── Natural language preference setting ───────────────────────────────────

    def handle_command(self, command: str) -> str:
        """Parse natural language preference commands."""
        cmd = command.lower()

        if "my name is" in cmd:
            name = cmd.split("my name is")[-1].strip().strip(".!").title()
            return self.set_preference("name", name)

        if "i live in" in cmd or "i'm from" in cmd or "i am from" in cmd:
            loc = cmd.split("in" if "in" in cmd else "from")[-1].strip().strip(".!").title()
            return self.set_preference("location", loc)

        if "call me" in cmd:
            nick = cmd.split("call me")[-1].strip().strip(".!").title()
            return self.set_preference("nickname", nick)

        if "favorite" in cmd or "favourite" in cmd:
            parts = cmd.split("is")
            if len(parts) >= 2:
                key = parts[0].replace("my", "").replace("favorite", "fav").replace("favourite", "fav").strip()
                val = parts[-1].strip().strip(".!")
                return self.set_preference(key, val)

        if "remember that" in cmd:
            fact = command[cmd.find("remember that") + len("remember that"):].strip().strip(".!")
            # Classify into simple semantic triples if possible
            if " is " in fact.lower():
                parts = fact.lower().split(" is ", 1)
                return self.add_triple(parts[0].strip(), "is", parts[1].strip())
            elif " works on " in fact.lower():
                parts = fact.lower().split(" works on ", 1)
                return self.add_triple(parts[0].strip(), "works_on", parts[1].strip())
            elif " lives in " in fact.lower():
                parts = fact.lower().split(" lives in ", 1)
                return self.add_triple(parts[0].strip(), "lives_in", parts[1].strip())
            else:
                return self.set_preference(f"fact_{int(time.time())}", fact)

        if "forget" in cmd and "about" in cmd:
            key = cmd.split("about")[-1].strip().strip(".!").lower().replace(" ", "_")
            return self.delete_preference(key)

        if "what do you know about me" in cmd or "my profile" in cmd:
            summary = self.get_profile_summary()
            kg_summary = self.get_knowledge_graph_summary()
            full_summary = ""
            if summary:
                full_summary += summary + "\n"
            if kg_summary:
                full_summary += "\n" + kg_summary
            return full_summary if full_summary else "I don't have any preferences saved for you yet. Tell me about yourself!"

        return None  # Not a personalization command

    # ── Knowledge Graph Triples ───────────────────────────────────────────────

    def add_triple(self, subject: str, relation: str, obj: str) -> str:
        """Add a semantic relationship triple to the knowledge graph."""
        subject = subject.strip().lower()
        relation = relation.strip().lower()
        obj = obj.strip().lower()
        with sqlite3.connect(self.DB) as c:
            c.execute(
                "INSERT OR REPLACE INTO knowledge_graph (subject, relation, object, updated_at) VALUES (?, ?, ?, ?)",
                (subject, relation, obj, time.time())
            )
            c.commit()
        return f"Added relationship: {subject} --({relation})--> {obj}"

    def query_triples(self, subject: str = None, relation: str = None, obj: str = None) -> list:
        """Query semantic relationships from the knowledge graph."""
        query = "SELECT subject, relation, object FROM knowledge_graph WHERE 1=1"
        params = []
        if subject:
            query += " AND subject = ?"
            params.append(subject.strip().lower())
        if relation:
            query += " AND relation = ?"
            params.append(relation.strip().lower())
        if obj:
            query += " AND object = ?"
            params.append(obj.strip().lower())
            
        with sqlite3.connect(self.DB) as c:
            rows = c.execute(query, params).fetchall()
        return rows

    def delete_triple(self, subject: str, relation: str, obj: str) -> str:
        """Remove a relationship triple from the knowledge graph."""
        subject = subject.strip().lower()
        relation = relation.strip().lower()
        obj = obj.strip().lower()
        with sqlite3.connect(self.DB) as c:
            c.execute(
                "DELETE FROM knowledge_graph WHERE subject = ? AND relation = ? AND object = ?",
                (subject, relation, obj)
            )
            c.commit()
        return f"Deleted relationship: {subject} --({relation})--> {obj}"

    def get_knowledge_graph_summary(self) -> str:
        """Returns a string list of all knowledge graph relationships."""
        with sqlite3.connect(self.DB) as c:
            rows = c.execute("SELECT subject, relation, object FROM knowledge_graph").fetchall()
        if not rows:
            return ""
        lines = ["Knowledge Graph Facts:"]
        for s, r, o in rows:
            lines.append(f"  - {s} {r} {o}")
        return "\n".join(lines)

    # ── Habits Tracking & Anticipation ───────────────────────────────────────

    def log_habit(self, action: str):
        """Log that an action/command was run at this current hour and day."""
        import datetime
        now = datetime.datetime.now()
        hour = now.hour
        day_of_week = now.weekday() # 0 = Monday, 6 = Sunday
        action = action.strip().lower()
        
        with sqlite3.connect(self.DB) as c:
            row = c.execute(
                "SELECT count FROM habits WHERE hour = ? AND day_of_week = ? AND action = ?",
                (hour, day_of_week, action)
            ).fetchone()
            if row:
                c.execute(
                    "UPDATE habits SET count = count + 1 WHERE hour = ? AND day_of_week = ? AND action = ?",
                    (hour, day_of_week, action)
                )
            else:
                c.execute(
                    "INSERT INTO habits (hour, day_of_week, action, count) VALUES (?, ?, ?, 1)",
                    (hour, day_of_week, action)
                )
            c.commit()

    def get_habits_for_time(self, hour: int = None, day_of_week: int = None) -> list:
        """Get high-probability actions for the given hour/day."""
        import datetime
        now = datetime.datetime.now()
        if hour is None:
            hour = now.hour
        if day_of_week is None:
            day_of_week = now.weekday()
            
        with sqlite3.connect(self.DB) as c:
            rows = c.execute(
                "SELECT action, count FROM habits WHERE hour = ? AND day_of_week = ? ORDER BY count DESC",
                (hour, day_of_week)
            ).fetchall()
        return rows

    # ── Reinforcement Learning Tool Feedback ──────────────────────────────────

    def log_rl_feedback(self, tool_name: str, arguments: str, success: int, rating: int = 1, notes: str = ""):
        """Logs the feedback/performance of a tool execution."""
        with sqlite3.connect(self.DB) as c:
            c.execute(
                "INSERT INTO rl_feedback (tool_name, arguments, success, rating, notes, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (tool_name, arguments, success, rating, notes, time.time())
            )
            c.commit()

    def get_failing_tools(self, limit: int = 5) -> list:
        """Retrieve tools with high failure counts."""
        with sqlite3.connect(self.DB) as c:
            rows = c.execute(
                "SELECT tool_name, COUNT(*) as fail_count FROM rl_feedback "
                "WHERE success = 0 "
                "GROUP BY tool_name ORDER BY fail_count DESC LIMIT ?", (limit,)
            ).fetchall()
        return rows

    # ── Projects Registry ────────────────────────────────────────────────────

    def register_project(self, path: str, name: str, status: str = "Active", summary: str = "", current_goals: str = "") -> str:
        """Register or update a workspace project."""
        with sqlite3.connect(self.DB) as c:
            c.execute(
                "INSERT OR REPLACE INTO projects (path, name, status, summary, current_goals, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (path, name, status, summary, current_goals, time.time())
            )
            c.commit()
        return f"Registered project '{name}' at {path}"

    def get_projects(self) -> list:
        with sqlite3.connect(self.DB) as c:
            rows = c.execute("SELECT path, name, status, summary, current_goals FROM projects").fetchall()
        return [{"path": r[0], "name": r[1], "status": r[2], "summary": r[3], "current_goals": r[4]} for r in rows]
