"""Task Agent - Manage To-Do tasks with SQLite database support"""
import sqlite3
import time
from pathlib import Path
from utils.logger import JarvisLogger

class TaskAgent:
    DB = Path.home() / ".jarvis" / "tasks.db"

    def __init__(self, config=None):
        self.logger = JarvisLogger("Tasks")
        self.DB.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.logger.success("Task agent ready")

    def _init_db(self):
        with sqlite3.connect(self.DB) as c:
            c.execute('''CREATE TABLE IF NOT EXISTS tasks 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                          title TEXT NOT NULL, 
                          description TEXT, 
                          priority TEXT, 
                          due_date TEXT, 
                          status TEXT DEFAULT 'Pending', 
                          created_at REAL)''')
            c.commit()

    def add_task(self, title: str, description: str = None, priority: str = "Medium", due_date: str = None) -> str:
        """Adds a new task to the database."""
        created_at = time.time()
        # Default priority validation
        priority = priority.capitalize() if priority else "Medium"
        if priority not in ["Low", "Medium", "High"]:
            priority = "Medium"

        with sqlite3.connect(self.DB) as c:
            c.execute("INSERT INTO tasks (title, description, priority, due_date, status, created_at) VALUES (?, ?, ?, ?, 'Pending', ?)",
                      (title, description, priority, due_date, created_at))
            c.commit()
        
        self.logger.success(f"Task added: '{title}' (Priority: {priority})")
        return f"I have added the task: '{title}' with {priority} priority."

    def get_tasks(self, status: str = None) -> list:
        """Retrieves tasks from the database, optionally filtering by status."""
        query = "SELECT id, title, description, priority, due_date, status, created_at FROM tasks"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status.capitalize())
        query += " ORDER BY created_at DESC"

        with sqlite3.connect(self.DB) as c:
            c.row_factory = sqlite3.Row
            cursor = c.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def complete_task(self, identifier: str) -> str:
        """Marks a task as completed by its ID or title."""
        task_id = None
        # Try to treat identifier as integer ID
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            task_id = int(identifier)
            query = "SELECT title FROM tasks WHERE id = ?"
            params = [task_id]
        else:
            # Treat as title
            query = "SELECT id, title FROM tasks WHERE title LIKE ? AND status = 'Pending' LIMIT 1"
            params = [f"%{identifier}%"]

        with sqlite3.connect(self.DB) as c:
            cursor = c.cursor()
            cursor.execute(query, params)
            res = cursor.fetchone()
            if not res:
                return f"Could not find any pending task matching '{identifier}'."
            
            if task_id is None:
                task_id, title = res
            else:
                title = res[0]

            cursor.execute("UPDATE tasks SET status = 'Completed' WHERE id = ?", (task_id,))
            c.commit()

        self.logger.success(f"Task completed: '{title}' (ID: {task_id})")
        return f"Task '{title}' is now marked as completed."

    def delete_task(self, identifier: str) -> str:
        """Deletes a task by its ID or title."""
        task_id = None
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            task_id = int(identifier)
            query = "SELECT title FROM tasks WHERE id = ?"
            params = [task_id]
        else:
            query = "SELECT id, title FROM tasks WHERE title LIKE ? LIMIT 1"
            params = [f"%{identifier}%"]

        with sqlite3.connect(self.DB) as c:
            cursor = c.cursor()
            cursor.execute(query, params)
            res = cursor.fetchone()
            if not res:
                return f"Could not find any task matching '{identifier}'."
            
            if task_id is None:
                task_id, title = res
            else:
                title = res[0]

            cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            c.commit()

        self.logger.success(f"Task deleted: '{title}' (ID: {task_id})")
        return f"Task '{title}' has been deleted."
