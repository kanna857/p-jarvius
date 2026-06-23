"""Reminder Agent - Persistent reminders with SQLite and Windows Toast Notifications"""
import sqlite3
import time
import threading
from pathlib import Path
from utils.logger import JarvisLogger

class ReminderAgent:
    DB = Path.home() / ".jarvis" / "reminders.db"

    def __init__(self, speak_callback=None):
        self.logger = JarvisLogger("Reminders")
        self.DB.parent.mkdir(parents=True, exist_ok=True)
        self.speak_callback = speak_callback
        self.running = False
        self._init_db()

        try:
            from win10toast import ToastNotifier
            self.toaster = ToastNotifier()
        except ImportError:
            self.logger.warning("win10toast not installed. Pop-ups disabled.")
            self.toaster = None

    def _init_db(self):
        with sqlite3.connect(self.DB) as c:
            c.execute('''CREATE TABLE IF NOT EXISTS reminders 
                         (id INTEGER PRIMARY KEY, ts REAL, message TEXT, triggered INTEGER)''')
            c.commit()

    def set_reminder(self, minutes: float, message: str) -> str:
        """Saves a reminder to the database."""
        trigger_time = time.time() + (minutes * 60)
        with sqlite3.connect(self.DB) as c:
            c.execute("INSERT INTO reminders (ts, message, triggered) VALUES (?, ?, 0)", 
                      (trigger_time, message))
            c.commit()
        
        self.logger.success(f"Reminder set for {minutes} minutes: '{message}'")
        return f"I have set a reminder for {minutes} minutes from now."

    def check_reminders(self):
        """Background loop to check for due reminders."""
        while self.running:
            try:
                now = time.time()
                with sqlite3.connect(self.DB) as c:
                    cursor = c.cursor()
                    cursor.execute("SELECT id, message FROM reminders WHERE ts <= ? AND triggered = 0", (now,))
                    due_reminders = cursor.fetchall()
                    
                    for rid, msg in due_reminders:
                        self.logger.info(f"Reminder Triggered: {msg}")
                        
                        # 1. Voice
                        if self.speak_callback:
                            self.speak_callback(f"Reminder! {msg}")
                        
                        # 2. Pop-up Notification
                        if self.toaster:
                            try:
                                # Run in separate thread to prevent blocking
                                threading.Thread(target=self.toaster.show_toast, args=("Jarvis Reminder", msg), kwargs={"duration": 10, "threaded": True}, daemon=True).start()
                            except Exception as e:
                                self.logger.error(f"Failed to show toast: {e}")
                        
                        # Mark as triggered
                        cursor.execute("UPDATE reminders SET triggered = 1 WHERE id = ?", (rid,))
                    c.commit()
            except Exception as e:
                self.logger.error(f"Reminder check error: {e}")
            
            time.sleep(10)

    def start(self):
        self.running = True
        threading.Thread(target=self.check_reminders, daemon=True, name="ReminderLoop").start()
        self.logger.info("Reminder background monitor started.")

    def stop(self):
        self.running = False
