"""
Automation Agent — Windows
- Open apps via subprocess/os.startfile
- PyAutoGUI mouse/keyboard control
- File management
- System commands
"""

import os
import subprocess
import time
import webbrowser
import pyautogui
import psutil
import screen_brightness_control as sbc
from pathlib import Path
from utils.logger import JarvisLogger
from utils.config import Config

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.08

class AutomationAgent:

    # Windows app commands
    APP_MAP = {
        "chrome":         "chrome",
        "firefox":        "firefox",
        "edge":           "msedge",
        "vscode":         "code",
        "notepad":        "notepad",
        "calculator":     "calc",
        "terminal":       "wt",           # Windows Terminal
        "cmd":            "cmd",
        "powershell":     "powershell",
        "explorer":       "explorer",
        "task manager":   "taskmgr",
        "control panel":  "control",
        "settings":       "ms-settings:",
        "paint":          "mspaint",
        "word":           "winword",
        "excel":          "excel",
        "powerpoint":     "powerpnt",
        "outlook":        "outlook",
        "spotify":        "spotify",
        "discord":        "discord",
        "obs":            "obs64",
        "steam":          "steam",
        "vlc":            "vlc",
        "snipping tool":  "snippingtool",
    }

    WEBSITE_MAP = {
        "youtube":      "https://youtube.com",
        "google":       "https://google.com",
        "github":       "https://github.com",
        "gmail":        "https://mail.google.com",
        "chatgpt":      "https://chat.openai.com",
        "netflix":      "https://netflix.com",
        "twitter":      "https://twitter.com",
        "reddit":       "https://reddit.com",
        "linkedin":     "https://linkedin.com",
        "whatsapp":     "https://web.whatsapp.com",
        "stackoverflow":"https://stackoverflow.com",
        "amazon":       "https://amazon.in",
        "maps":         "https://maps.google.com",
        "drive":        "https://drive.google.com",
        "claude":       "https://claude.ai",
    }

    def __init__(self, config: Config):
        self.config = config
        self.logger = JarvisLogger("AutoAgent")
        self.logger.success("Automation agent ready")

    def open_app(self, name: str) -> str:
        n = name.lower().strip()
        
        # If it is in WEBSITE_MAP, redirect to open_website
        for key in self.WEBSITE_MAP.keys():
            if key == n or key in n:
                return self.open_website(name)
                
        for key, cmd in self.APP_MAP.items():
            if key in n:
                try:
                    if cmd.startswith("ms-"):
                        os.startfile(cmd)
                    else:
                        subprocess.Popen(cmd, shell=True,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                    self.logger.success(f"Opened: {key}")
                    return f"Opening {key}."
                except Exception as e:
                    return f"Couldn't open {key}: {e}"
                    
        # Check if it could be a website (contains domain suffix or url-like)
        if any(suffix in n for suffix in [".com", ".org", ".net", ".in", ".edu", ".gov", "http://", "https://"]):
            return self.open_website(name)
            
        # Try running it as a generic system command as a fallback
        try:
            subprocess.Popen(n, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return f"Opening {name}."
        except Exception:
            pass
            
        return f"I don't know how to open '{name}'."

    def open_website(self, site: str) -> str:
        s = site.lower().strip()
        for key, url in self.WEBSITE_MAP.items():
            if key in s:
                webbrowser.open(url)
                return f"Opening {key}."
        if "." in s:
            url = s if s.startswith("http") else f"https://{s}"
            webbrowser.open(url)
            return f"Opened {url}."
        return f"I don't recognise the site '{site}'."

    def type_text(self, text: str) -> str:
        import tkinter as tk
        
        # Check if the text is short, single-line, and doesn't contain tabs/newlines.
        is_simple_and_short = len(text) < 150 and '\n' not in text and '\t' not in text
        
        if is_simple_and_short:
            try:
                time.sleep(0.1)
                pyautogui.write(text, interval=0.01)
                return f"Typed directly: '{text[:50]}'"
            except Exception as e:
                self.logger.warning(f"Direct typing failed: {e}. Falling back to clipboard.")
        
        # Backup, paste, and restore clipboard for longer/complex text
        old_clip = None
        try:
            root = tk.Tk()
            root.withdraw()
            try:
                old_clip = root.clipboard_get()
            except Exception:
                pass # Clipboard was empty or did not contain text
            
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            root.destroy()
            
            time.sleep(0.1)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.15) # Give OS time to process paste
            
            # Restore previous clipboard content
            if old_clip is not None:
                root = tk.Tk()
                root.withdraw()
                root.clipboard_clear()
                root.clipboard_append(old_clip)
                root.update()
                root.destroy()
                
            return f"Typed via clipboard (clipboard restored): '{text[:50]}'"
        except Exception as e:
            self.logger.warning(f"Clipboard paste failed: {e}. Falling back to typewrite.")
            time.sleep(0.4)
            pyautogui.typewrite(text, interval=0.01)
            return f"Typed: '{text[:50]}'"

    def press_keys(self, *keys) -> str:
        pyautogui.hotkey(*keys)
        return f"Pressed: {' + '.join(keys)}"

    def click(self, x=None, y=None) -> str:
        if x and y:
            pyautogui.click(x, y)
            return f"Clicked ({x}, {y})."
        pyautogui.click()
        return "Clicked."

    def scroll(self, direction="down", amount=5) -> str:
        pyautogui.scroll(-amount if direction == "down" else amount)
        return f"Scrolled {direction}."

    def screenshot(self) -> str:
        path = Path.home() / "Pictures" / f"jarvis_{int(time.time())}.png"
        pyautogui.screenshot(str(path))
        return f"Screenshot saved to {path.name} in Pictures."

    def close_active_window(self) -> str:
        pyautogui.hotkey("alt", "F4")
        return "Closed the active window."

    def minimize_window(self) -> str:
        pyautogui.hotkey("win", "down")
        return "Minimized."

    def maximize_window(self) -> str:
        pyautogui.hotkey("win", "up")
        return "Maximized."

    def lock_screen(self) -> str:
        pyautogui.hotkey("win", "l")
        return "Screen locked."

    def volume_up(self, steps=5) -> str:
        for _ in range(steps):
            pyautogui.press("volumeup")
        return f"Volume increased."

    def volume_down(self, steps=5) -> str:
        for _ in range(steps):
            pyautogui.press("volumedown")
        return "Volume decreased."

    def mute_volume(self) -> str:
        pyautogui.press("volumemute")
        return "Volume muted."
    
    def media_play_pause(self) -> str:
        pyautogui.press("playpause")
        return "Media toggled."

    def media_next(self) -> str:
        pyautogui.press("nexttrack")
        return "Skipped track."

    def media_prev(self) -> str:
        pyautogui.press("prevtrack")
        return "Previous track."

    def set_brightness(self, level: int) -> str:
        try:
            sbc.set_brightness(level)
            return f"Brightness set to {level}%."
        except Exception as e:
            return f"Couldn't set brightness: {e}"

    def get_system_status(self) -> str:
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        battery = psutil.sensors_battery()
        batt_str = f", Battery: {battery.percent}%" if battery else ""
        return f"CPU: {cpu}%, RAM: {ram}% used{batt_str}."

    def shutdown(self) -> str:
        os.system("shutdown /s /t 60")
        return "Shutting down in 60 seconds. Say 'abort shutdown' to stop."

    def restart(self) -> str:
        os.system("shutdown /r /t 60")
        return "Restarting in 60 seconds."

    def abort_shutdown(self) -> str:
        os.system("shutdown /a")
        return "Shutdown aborted."

    def run_shell(self, cmd: str) -> str:
        dangerous = ["rm -rf", "format", "del /f /s", "rd /s"]
        if any(d in cmd.lower() for d in dangerous):
            return "Blocked: potentially dangerous command."
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True,
                               text=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            out = (r.stdout or r.stderr or "").strip()
            return out[:400] or "Command executed."
        except subprocess.TimeoutExpired:
            return "Command timed out."
        except Exception as e:
            return f"Error: {e}"

    def list_files(self, path: str = None) -> str:
        p = Path(path) if path else Path.home()
        if not p.exists():
            return f"Path not found: {p}"
        items = [f.name for f in sorted(p.iterdir())][:15]
        return f"Files in {p.name}: {', '.join(items)}"

    def search_file(self, name: str) -> str:
        matches = list(Path.home().rglob(f"*{name}*"))[:5]
        if not matches:
            return f"No files matching '{name}' found."
        return "Found: " + ", ".join(m.name for m in matches)

    def search_file_contents(self, query: str, search_dir: str = None) -> str:
        """Naively search text files for a query string."""
        import glob
        if not search_dir:
            search_dir = str(Path.home() / "Documents")
        
        results = []
        try:
            exts = ['*.txt', '*.md', '*.py', '*.json', '*.csv']
            files = []
            for ext in exts:
                files.extend(glob.glob(os.path.join(search_dir, '**', ext), recursive=True))
            
            for fpath in files[:100]:
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        for i, line in enumerate(lines):
                            if query.lower() in line.lower():
                                snippet = "".join(lines[max(0, i-2):min(len(lines), i+3)])
                                results.append(f"File: {fpath}\nSnippet:\n{snippet}\n---")
                                break
                except Exception:
                    pass
            if not results:
                return f"No matches found for '{query}' in {search_dir}."
            return "Found matches:\n" + "\n".join(results[:5])
        except Exception as e:
            return f"Error searching files: {e}"

    def execute_python_code(self, script_code: str) -> str:
        """Saves script to a temp file and executes it, returning output."""
        import tempfile
        try:
            fd, path = tempfile.mkstemp(suffix=".py", prefix="jarvis_script_")
            with open(fd, 'w', encoding='utf-8') as f:
                f.write(script_code)
            
            r = subprocess.run(["python", path], capture_output=True, text=True, timeout=30)
            
            try:
                os.remove(path)
            except:
                pass
            
            out = r.stdout.strip()
            err = r.stderr.strip()
            
            res = ""
            if out: res += f"Output:\n{out}\n"
            if err: res += f"Errors:\n{err}\n"
            
            return res[:1000] if res else "Script executed successfully with no output."
        except subprocess.TimeoutExpired:
            return "Execution timed out after 30 seconds."
        except Exception as e:
            return f"Failed to execute code: {e}"

    def handle_command(self, cmd: str) -> str:
        c = cmd.lower()

        if "open" in c or "launch" in c:
            target = c.replace("open", "").replace("launch", "").strip()
            for site in self.WEBSITE_MAP:
                if site in target:
                    return self.open_website(target)
            return self.open_app(target)

        elif "close" in c or "exit" in c:
            return self.close_active_window()

        elif "minimize" in c:
            return self.minimize_window()

        elif "maximize" in c:
            return self.maximize_window()

        elif "type" in c:
            text = c.replace("type", "").strip().strip('"\'')
            return self.type_text(text)

        elif "screenshot" in c or "capture screen" in c:
            return self.screenshot()

        elif "scroll" in c:
            d = "up" if "up" in c else "down"
            return self.scroll(d)

        elif "lock" in c:
            return self.lock_screen()

        elif "volume up" in c or "louder" in c:
            return self.volume_up()

        elif "volume down" in c or "quieter" in c:
            return self.volume_down()

        elif "mute" in c:
            return self.mute_volume()

        elif "file" in c or "folder" in c or "list" in c:
            return self.list_files()

        elif "find file" in c or "search file" in c:
            name = c.replace("find file", "").replace("search file", "").strip()
            return self.search_file(name)

        elif "run" in c or "execute" in c:
            shell_cmd = c.replace("run", "").replace("execute", "").strip()
            return self.run_shell(shell_cmd)

        elif "shutdown" in c:
            return self.shutdown()

        elif "restart" in c:
            return self.restart()

        elif "abort shutdown" in c:
            return self.abort_shutdown()

        elif "brightness" in c:
            if "up" in c: return self.set_brightness(min(100, sbc.get_brightness()[0] + 20))
            if "down" in c: return self.set_brightness(max(0, sbc.get_brightness()[0] - 20))
            # Try to find a number
            import re
            nums = re.findall(r'\d+', c)
            if nums: return self.set_brightness(int(nums[0]))
            return "Specify a brightness level or use 'up/down'."

        elif "system status" in c or "pc status" in c or "battery" in c:
            return self.get_system_status()

        elif "play" in c or "pause" in c or "resume" in c:
            return self.media_play_pause()

        elif "next" in c:
            return self.media_next()

        elif "previous" in c:
            return self.media_prev()

        else:
            return self.open_app(c)
