"""Memory Agent — SQLite persistent memory"""

import sqlite3, time, re
from pathlib import Path
from utils.logger import JarvisLogger
from utils.config import Config

class MemoryAgent:
    DB = Path.home() / ".jarvis" / "memory.db"

    def __init__(self, config: Config):
        self.config = config
        self.logger = JarvisLogger("Memory")
        self.DB.parent.mkdir(parents=True, exist_ok=True)
        self.short_term = []
        self._init_db()
        
        # Load last 10 memories from SQLite to prepopulate short term history
        try:
            with sqlite3.connect(self.DB) as c:
                rows = c.execute("SELECT cmd, resp FROM memories ORDER BY ts DESC LIMIT 10").fetchall()
                for cmd, resp in reversed(rows):
                    self.short_term.append({"role": "user", "content": cmd})
                    self.short_term.append({"role": "assistant", "content": resp})
        except Exception as e:
            self.logger.warning(f"Failed to load historical memories: {e}")
        
        # Initialize High-End Vectorized Database
        try:
            import chromadb
            chroma_path = str(Path.home() / ".jarvis" / "vector_db")
            self.chroma = chromadb.PersistentClient(path=chroma_path)
            self.collection = self.chroma.get_or_create_collection(name="jarvis_vmem")
            self.vector_active = True
            self.logger.success("ChromaDB Vector Brain Loaded")
        except Exception as e:
            self.logger.warning(f"Vector store initiation partial fail: {e}")
            self.vector_active = False

        self.logger.success("Memory agent ready")

    def _init_db(self):
        with sqlite3.connect(self.DB) as c:
            c.execute("CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY, ts REAL, cmd TEXT, resp TEXT, tags TEXT)")
            c.execute("CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT, updated REAL)")
            c.commit()

    def store(self, cmd: str, resp: str):
        tags = ",".join(self._tags(cmd))
        ts = time.time()
        with sqlite3.connect(self.DB) as c:
            c.execute("INSERT INTO memories (ts,cmd,resp,tags) VALUES (?,?,?,?)", (ts, cmd, resp, tags))
            c.commit()
        
        # Also commit to Vector Store for High-Recall semantic processing
        if self.vector_active:
            try:
                doc_id = f"mem_{int(ts)}"
                self.collection.add(
                    documents=[f"User said: {cmd}. Jarvis responded: {resp}"],
                    metadatas=[{"ts": ts, "cmd": cmd, "resp": resp}],
                    ids=[doc_id]
                )
            except Exception as ve:
                self.logger.warning(f"Vector insertion skip: {ve}")

        self.short_term.append({"role": "user", "content": cmd})
        self.short_term.append({"role": "assistant", "content": resp})
        if len(self.short_term) > 40:
            self.short_term = self.short_term[-40:]

    def recall(self, q: str, n: int = 3) -> list:
        # 1. Attempt Semantic Brain Retrieval First (Contextual matching)
        if self.vector_active:
            try:
                results = self.collection.query(query_texts=[q], n_results=n)
                if results and results['metadatas'] and len(results['metadatas'][0]) > 0:
                    # Successfully retrieved vector contexts!
                    out = []
                    for meta in results['metadatas'][0]:
                        out.append({
                            "ts": meta.get("ts", 0), 
                            "cmd": meta.get("cmd", ""), 
                            "resp": meta.get("resp", "")
                        })
                    return out
            except Exception as re:
                self.logger.warning(f"Vector recall issue: {re}")

        # 2. Fallback to exact keyword legacy retrieval if vector was offline
        kws = q.lower().split()
        rows, out = [], []
        with sqlite3.connect(self.DB) as c:
            rows = c.execute("SELECT ts,cmd,resp,tags FROM memories ORDER BY ts DESC LIMIT 300").fetchall()
        for ts, cmd, resp, tags in rows:
            score = sum(k in (cmd + " " + (tags or "")).lower() for k in kws)
            if score: out.append((score, ts, cmd, resp))
        out.sort(reverse=True)
        return [{"ts": t, "cmd": c, "resp": r} for _, t, c, r in out[:n]]

    def remember_fact(self, key: str, val: str):
        with sqlite3.connect(self.DB) as c:
            c.execute("INSERT OR REPLACE INTO facts (key,value,updated) VALUES (?,?,?)", (key.lower(), val, time.time()))
            c.commit()

    def get_fact(self, key: str):
        with sqlite3.connect(self.DB) as c:
            r = c.execute("SELECT value FROM facts WHERE key=?", (key.lower(),)).fetchone()
            return r[0] if r else None

    def forget(self, q: str) -> str:
        kws = q.lower().split()
        with sqlite3.connect(self.DB) as c:
            rows = c.execute("SELECT id, cmd FROM memories").fetchall()
            ids = [r[0] for r in rows if any(k in r[1].lower() for k in kws)]
            if ids:
                c.executemany("DELETE FROM memories WHERE id=?", [(i,) for i in ids])
                c.commit()
                return f"Deleted {len(ids)} memories."
        return "No matching memories found."

    def get_short_term(self): return self.short_term[-10:]

    def stats(self):
        with sqlite3.connect(self.DB) as c:
            m = c.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            f = c.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        return {"total_memories": m, "stored_facts": f}

    def _tags(self, text):
        stop = {"a","the","is","was","are","it","to","in","on","and","or","i","you","me","my"}
        return list(set(w for w in re.findall(r"\b[a-z]{3,}\b", text.lower()) if w not in stop))[:8]

    def handle_command(self, cmd: str) -> str:
        c = cmd.lower()
        if "remember" in c:
            m = re.search(r"remember (?:that )?(.+?) is (.+)", c)
            if m:
                self.remember_fact(m.group(1).strip(), m.group(2).strip())
                return f"Got it. I'll remember that {m.group(1)} is {m.group(2)}."
            return "What should I remember?"
        elif "recall" in c or "what did" in c:
            q = c.replace("recall","").replace("what did i say about","").strip()
            rs = self.recall(q)
            if rs:
                t = time.strftime("%d %b %H:%M", time.localtime(rs[0]["ts"]))
                return f"At {t} you said: '{rs[0]['cmd']}'"
            return f"No memories found for '{q}'."
        elif "forget" in c:
            return self.forget(c.replace("forget","").replace("about","").strip())
        elif "memory" in c:
            s = self.stats()
            return f"I have {s['total_memories']} memories and {s['stored_facts']} stored facts."
        return "Memory command not understood."
