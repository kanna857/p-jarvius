"""
JARVIS DesktopAgent — Full Autonomous Desktop Control
─────────────────────────────────────────────────────
Observes screen changes, drives apps like a human, recovers from errors.

Capabilities:
  1. Screen Monitoring   — detect visual changes via frame diffing
  2. UI Automation       — click/type/scroll at UI elements found by Vision AI
  3. Browser Control     — navigate, fill forms, extract data from pages
  4. Error Recovery      — detect error dialogs, dismiss or retry automatically
  5. Workflow Execution  — multi-step desktop tasks described in natural language

Architecture:
  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │ VisionAgent  │───▶│ DesktopAgent │───▶│ PyAutoGUI    │
  │ (understand) │    │ (plan+act)   │    │ (execute)    │
  └──────────────┘    └──────────────┘    └──────────────┘

Uses a think-act-observe loop:
  1. THINK   → Vision model analyzes current screen
  2. ACT     → Execute the next action (click, type, scroll, wait)
  3. OBSERVE → Check if the action succeeded or an error appeared
  4. ADAPT   → If error detected, try alternative approach
"""

import time
import base64
import threading
import hashlib
import numpy as np
from pathlib import Path
from utils.logger import JarvisLogger


class DesktopAgent:
    """Autonomous desktop controller that uses Vision AI to drive apps like a human."""

    # Screen change detection thresholds
    CHANGE_THRESHOLD = 0.05   # 5% pixel difference = meaningful change
    MAX_RETRIES = 3           # Retries before giving up on a step
    ACTION_DELAY = 0.8        # Seconds to wait between actions for UI to settle

    def __init__(self, config=None, vision_agent=None, voice_agent=None):
        self.config = config
        self.vision = vision_agent
        self.voice = voice_agent
        self.logger = JarvisLogger("DesktopAgent")
        self._monitoring = False
        self._last_screen_hash = None
        self._screen_watchers = []  # callbacks for screen change events
        self.logger.success("DesktopAgent ready — autonomous desktop control active")

    # ─────────────────────────────────────────────────────────────────────────
    # Screen Observation & Change Detection
    # ─────────────────────────────────────────────────────────────────────────

    def _capture_screen(self) -> np.ndarray:
        """Capture the current screen as a numpy array."""
        import pyautogui
        from PIL import Image
        pil_img = pyautogui.screenshot()
        return np.array(pil_img)

    def _screen_hash(self, frame: np.ndarray) -> str:
        """Fast perceptual hash of a screen frame."""
        from PIL import Image
        # Downscale to 32x32 grayscale for fast comparison
        img = Image.fromarray(frame).convert("L").resize((32, 32))
        return hashlib.md5(np.array(img).tobytes()).hexdigest()

    def _screen_diff_pct(self, frame1: np.ndarray, frame2: np.ndarray) -> float:
        """Returns the percentage of pixels that differ between two frames."""
        if frame1.shape != frame2.shape:
            return 1.0  # Completely different
        diff = np.abs(frame1.astype(np.int16) - frame2.astype(np.int16))
        changed = np.mean(diff > 30)  # Threshold per-pixel
        return float(changed)

    def detect_screen_change(self) -> dict:
        """
        Check if the screen has changed since last observation.
        Returns: {"changed": bool, "diff_pct": float, "description": str}
        """
        current = self._capture_screen()
        current_hash = self._screen_hash(current)

        if self._last_screen_hash is None:
            self._last_screen_hash = current_hash
            self._last_frame = current
            return {"changed": False, "diff_pct": 0.0, "description": "Initial screen capture."}

        if current_hash == self._last_screen_hash:
            return {"changed": False, "diff_pct": 0.0, "description": "No visible change."}

        diff = self._screen_diff_pct(self._last_frame, current)
        self._last_screen_hash = current_hash
        self._last_frame = current

        changed = diff > self.CHANGE_THRESHOLD
        desc = f"Screen changed ({diff*100:.1f}% different)." if changed else "Minor flicker, no meaningful change."
        return {"changed": changed, "diff_pct": diff, "description": desc}

    def start_screen_monitor(self, interval: float = 2.0, callback=None):
        """
        Start monitoring the screen for changes in a background thread.
        Calls callback(change_info) when a significant change is detected.
        """
        if self._monitoring:
            return "Screen monitor is already running."

        def _monitor_loop():
            self._monitoring = True
            self.logger.info(f"Screen monitor started (checking every {interval}s)")
            while self._monitoring:
                try:
                    result = self.detect_screen_change()
                    if result["changed"]:
                        self.logger.info(f"📺 Screen changed: {result['diff_pct']*100:.1f}%")
                        if callback:
                            callback(result)
                        for watcher in self._screen_watchers:
                            watcher(result)
                except Exception as e:
                    self.logger.warning(f"Screen monitor error: {e}")
                time.sleep(interval)

        threading.Thread(target=_monitor_loop, daemon=True, name="ScreenMonitor").start()
        return "📺 Screen monitor started."

    def stop_screen_monitor(self):
        self._monitoring = False
        return "Screen monitor stopped."

    # ─────────────────────────────────────────────────────────────────────────
    # AI-Powered UI Element Finding
    # ─────────────────────────────────────────────────────────────────────────

    def _ask_vision(self, question: str, client=None) -> str:
        """Ask the Vision AI about the current screen."""
        if not self.vision:
            return "Vision agent not available."
        try:
            # Use Groq vision client if available
            if client:
                return self.vision.analyze_screen_with_ai(client, question, max_tokens=600)
            # Fallback to OCR
            return self.vision.run_ocr()
        except Exception as e:
            return f"Vision query failed: {e}"

    def find_element(self, description: str, client=None) -> dict:
        """
        Use Vision AI to locate a UI element described in natural language.
        Returns {"found": bool, "x": int, "y": int, "description": str}
        """
        prompt = (
            f"Look at this screenshot. I need to click on: '{description}'.\n\n"
            f"Find the exact pixel coordinates (x, y) of the CENTER of that element.\n"
            f"Respond in this exact format:\n"
            f"FOUND: x=123 y=456\n"
            f"or if not found:\n"
            f"NOT_FOUND: reason"
        )
        result = self._ask_vision(prompt, client)
        import re
        match = re.search(r'FOUND:\s*x=(\d+)\s*y=(\d+)', result)
        if match:
            x, y = int(match.group(1)), int(match.group(2))
            return {"found": True, "x": x, "y": y, "description": f"Found '{description}' at ({x}, {y})"}
        return {"found": False, "x": 0, "y": 0, "description": f"Could not find '{description}': {result[:100]}"}

    # ─────────────────────────────────────────────────────────────────────────
    # Desktop Actions
    # ─────────────────────────────────────────────────────────────────────────

    def click_at(self, x: int, y: int, button: str = "left") -> str:
        """Click at specific screen coordinates."""
        import pyautogui
        pyautogui.click(x, y, button=button)
        time.sleep(self.ACTION_DELAY)
        return f"✅ Clicked at ({x}, {y}) [{button}]"

    def click_element(self, description: str, client=None) -> str:
        """Find and click a UI element described in natural language."""
        elem = self.find_element(description, client)
        if not elem["found"]:
            return elem["description"]
        return self.click_at(elem["x"], elem["y"])

    def type_text(self, text: str, delay: float = 0.02) -> str:
        """Type text at the current cursor position."""
        import pyautogui
        pyautogui.typewrite(text, interval=delay) if text.isascii() else pyautogui.write(text)
        return f"✅ Typed: '{text[:50]}'"

    def hotkey(self, *keys) -> str:
        """Press a keyboard shortcut."""
        import pyautogui
        pyautogui.hotkey(*keys)
        time.sleep(0.3)
        return f"✅ Pressed: {'+'.join(keys)}"

    def scroll(self, clicks: int = -3) -> str:
        """Scroll up (positive) or down (negative)."""
        import pyautogui
        pyautogui.scroll(clicks)
        time.sleep(0.3)
        return f"✅ Scrolled {'up' if clicks > 0 else 'down'} by {abs(clicks)}"

    def wait_for_change(self, timeout: float = 10.0) -> bool:
        """Wait for the screen to change (e.g., after clicking a button)."""
        start = time.time()
        self._capture_screen()  # Capture baseline
        self._last_frame = self._capture_screen()
        while time.time() - start < timeout:
            time.sleep(0.5)
            result = self.detect_screen_change()
            if result["changed"]:
                return True
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # Browser Automation (Like a Human)
    # ─────────────────────────────────────────────────────────────────────────

    def open_browser_url(self, url: str) -> str:
        """Open a URL in the default browser."""
        import webbrowser
        webbrowser.open(url)
        time.sleep(2.0)  # Wait for browser to load
        return f"✅ Opened browser: {url}"

    def browser_search(self, query: str) -> str:
        """Open browser and search Google."""
        from urllib.parse import quote_plus
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        return self.open_browser_url(url)

    def browser_fill_form(self, fields: dict, client=None) -> str:
        """
        Fill a form on the current page by finding each field and typing into it.
        fields: {"field_description": "value_to_type", ...}
        """
        results = []
        for field_desc, value in fields.items():
            # Find and click the field
            click_result = self.click_element(field_desc, client)
            if "Could not find" in click_result:
                results.append(f"⚠️ {field_desc}: not found")
                continue
            time.sleep(0.3)
            # Type the value
            self.type_text(value)
            results.append(f"✅ {field_desc}: filled")
        return "\n".join(results)

    def browser_extract_text(self, client=None) -> str:
        """Extract visible text from the current browser page using Vision AI."""
        return self._ask_vision(
            "Extract all visible text content from this browser page. "
            "Return it as plain text, organized by sections.",
            client
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Error Recovery
    # ─────────────────────────────────────────────────────────────────────────

    def detect_error_dialog(self, client=None) -> dict:
        """
        Check if there's an error dialog or popup visible on screen.
        Returns {"has_error": bool, "error_text": str, "suggested_action": str}
        """
        prompt = (
            "Analyze this screenshot. Is there any error dialog, warning popup, "
            "crash notification, or 'Not Responding' message visible?\n\n"
            "If YES, respond exactly:\n"
            "ERROR_FOUND: [error text visible] | ACTION: [click OK / click X / press Enter / dismiss / retry]\n\n"
            "If NO errors visible, respond exactly:\n"
            "NO_ERROR"
        )
        result = self._ask_vision(prompt, client)

        if "ERROR_FOUND:" in result:
            import re
            err_match = re.search(r'ERROR_FOUND:\s*(.+?)\s*\|\s*ACTION:\s*(.+)', result)
            if err_match:
                return {
                    "has_error": True,
                    "error_text": err_match.group(1).strip(),
                    "suggested_action": err_match.group(2).strip()
                }
        return {"has_error": False, "error_text": "", "suggested_action": ""}

    def dismiss_error(self, client=None) -> str:
        """Detect and automatically dismiss any visible error dialog."""
        error_info = self.detect_error_dialog(client)
        if not error_info["has_error"]:
            return "No error dialog detected."

        self.logger.warning(f"Error detected: {error_info['error_text']}")
        action = error_info["suggested_action"].lower()

        import pyautogui
        if "enter" in action or "ok" in action:
            pyautogui.press("enter")
        elif "x" in action or "close" in action:
            pyautogui.hotkey("alt", "F4")
        elif "escape" in action or "dismiss" in action:
            pyautogui.press("escape")
        elif "retry" in action:
            pyautogui.press("enter")
        else:
            pyautogui.press("escape")  # Default: try escape

        time.sleep(0.5)
        return f"🔧 Dismissed error: '{error_info['error_text']}' via {action}"

    # ─────────────────────────────────────────────────────────────────────────
    # Autonomous Task Execution (Think → Act → Observe → Adapt)
    # ─────────────────────────────────────────────────────────────────────────

    def execute_desktop_task(self, task_description: str, client=None, max_steps: int = 10) -> str:
        """
        Execute a multi-step desktop task using the Think-Act-Observe-Adapt loop.

        Example: "Open Chrome, go to Gmail, find unread emails, copy the first subject line"

        1. THINK   → Vision AI analyzes current screen + determines next action
        2. ACT     → Executes the action (click, type, scroll, open app)
        3. OBSERVE → Checks if it worked (screen change + error detection)
        4. ADAPT   → If error, tries alternative approach
        """
        self.logger.info(f"🤖 Starting desktop task: {task_description}")
        log = [f"📋 Task: {task_description}", ""]
        retries = 0

        for step in range(1, max_steps + 1):
            # ── THINK ──
            plan_prompt = (
                f"I'm performing this task: '{task_description}'\n\n"
                f"Steps completed so far:\n{'  '.join(log[-6:])}\n\n"
                f"Look at the current screenshot and tell me the NEXT SINGLE action to take.\n"
                f"Respond in this exact format:\n"
                f"ACTION: [click/type/scroll/hotkey/open_url/wait/done] | TARGET: [what to click or type or the URL] | DETAIL: [coordinates x=N y=N, or text to type, or keys for hotkey]\n\n"
                f"If the task is complete, respond: ACTION: done | TARGET: result summary | DETAIL: success\n"
                f"If you're stuck, respond: ACTION: done | TARGET: could not complete | DETAIL: reason"
            )

            think_result = self._ask_vision(plan_prompt, client)
            self.logger.info(f"  Step {step} THINK: {think_result[:100]}")

            # ── Parse action ──
            import re
            action_match = re.search(
                r'ACTION:\s*(\w+)\s*\|\s*TARGET:\s*(.+?)\s*\|\s*DETAIL:\s*(.+)',
                think_result, re.IGNORECASE
            )

            if not action_match:
                log.append(f"Step {step}: ⚠️ Could not parse AI action, retrying...")
                retries += 1
                if retries >= self.MAX_RETRIES:
                    log.append("❌ Max retries reached. Task aborted.")
                    break
                continue

            action = action_match.group(1).lower()
            target = action_match.group(2).strip()
            detail = action_match.group(3).strip()

            # ── DONE? ──
            if action == "done":
                log.append(f"✅ Task complete: {target}")
                break

            # ── ACT ──
            try:
                import pyautogui
                if action == "click":
                    coord_match = re.search(r'x=(\d+)\s*y=(\d+)', detail)
                    if coord_match:
                        x, y = int(coord_match.group(1)), int(coord_match.group(2))
                        self.click_at(x, y)
                        act_result = f"Clicked at ({x}, {y})"
                    else:
                        act_result = self.click_element(target, client)

                elif action == "type":
                    self.type_text(detail if detail != "success" else target)
                    act_result = f"Typed: '{detail[:40]}'"

                elif action == "scroll":
                    direction = -3 if "down" in detail.lower() else 3
                    self.scroll(direction)
                    act_result = f"Scrolled {'down' if direction < 0 else 'up'}"

                elif action == "hotkey":
                    keys = [k.strip() for k in detail.split("+")]
                    self.hotkey(*keys)
                    act_result = f"Pressed {'+'.join(keys)}"

                elif action == "open_url":
                    self.open_browser_url(target)
                    act_result = f"Opened {target}"

                elif action == "wait":
                    secs = float(re.search(r'(\d+)', detail).group(1)) if re.search(r'\d+', detail) else 2
                    time.sleep(min(secs, 5))
                    act_result = f"Waited {secs}s"

                else:
                    act_result = f"Unknown action: {action}"

                log.append(f"Step {step}: {act_result}")

            except Exception as e:
                log.append(f"Step {step}: ⚠️ Action failed: {e}")

            # ── OBSERVE ── (error recovery)
            time.sleep(self.ACTION_DELAY)
            error_info = self.detect_error_dialog(client)
            if error_info["has_error"]:
                dismiss_result = self.dismiss_error(client)
                log.append(f"  🔧 {dismiss_result}")
                retries += 1
                if retries >= self.MAX_RETRIES:
                    log.append("❌ Too many errors. Task aborted.")
                    break

        result = "\n".join(log)
        self.logger.info(f"Desktop task finished: {len(log)} steps")
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Convenience: App-Specific Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def take_annotated_screenshot(self) -> str:
        """Capture screenshot and describe all visible UI elements."""
        return self._ask_vision(
            "Describe every visible UI element on this screen: buttons, text fields, "
            "menus, tabs, status bars, notifications. List them with approximate (x, y) positions."
        )

    def read_current_page(self, client=None) -> str:
        """Read all text from the current screen/page."""
        return self._ask_vision(
            "Read and return ALL visible text on this screen, organized by section. "
            "Include headings, body text, button labels, and status messages.",
            client
        )
