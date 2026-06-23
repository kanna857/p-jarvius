"""
JARVIS System Tray
- Tray icon with right-click menu
- Toast notifications for responses
- Status control (mute, vision, quit)
- No window — purely tray-based
"""

import threading
import time
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item, Menu


def _make_icon(color: tuple = (0, 200, 255)) -> Image.Image:
    """Generate the JARVIS tray icon dynamically (cyan 'J' on dark bg)"""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark circle background
    draw.ellipse([2, 2, size - 2, size - 2], fill=(10, 20, 30, 240))

    # Cyan ring
    draw.ellipse([2, 2, size - 2, size - 2], outline=color, width=3)

    # Letter "J" in the centre
    draw.text((22, 14), "J", fill=color)

    return img


def _make_icon_muted() -> Image.Image:
    return _make_icon(color=(255, 80, 80))


def _make_icon_listening() -> Image.Image:
    return _make_icon(color=(0, 255, 128))


class JarvisTray:
    def __init__(self, jarvis):
        self.jarvis = jarvis
        self.icon = None
        self._pulse_thread = None
        self._pulsing = False

    # ── Notification ──────────────────────────────────────────────
    def notify(self, title: str, message: str):
        """Show a Windows toast notification from the tray icon"""
        if self.icon:
            self.icon.notify(message, title)

    def pulse_icon(self):
        """Flash the icon green briefly to show Jarvis heard you"""
        if not self.icon:
            return
        self.icon.icon = _make_icon_listening()
        time.sleep(1.5)
        if not self.jarvis.is_muted:
            self.icon.icon = _make_icon()
        else:
            self.icon.icon = _make_icon_muted()

    # ── Menu actions ─────────────────────────────────────────────
    def _toggle_mute(self, icon, item):
        self.jarvis.is_muted = not self.jarvis.is_muted
        if self.jarvis.is_muted:
            icon.icon = _make_icon_muted()
            self.notify("JARVIS Muted", "Say 'Hey Jarvis unmute' or click Unmute.")
        else:
            icon.icon = _make_icon()
            self.notify("JARVIS Active", "Listening for 'Hey Jarvis'...")
        self._rebuild_menu()

    def _toggle_vision(self, icon, item):
        self.jarvis.config.VISION_ENABLED = not self.jarvis.config.VISION_ENABLED
        state = "ON" if self.jarvis.config.VISION_ENABLED else "OFF"
        self.notify("JARVIS Vision", f"Vision system turned {state}.")
        self._rebuild_menu()

    def _show_status(self, icon, item):
        stats = self.jarvis.memory.stats()
        mood  = self.jarvis.emotion.last_mood
        muted = "MUTED" if self.jarvis.is_muted else "ACTIVE"
        vision= "ON" if self.jarvis.config.VISION_ENABLED else "OFF"
        msg = (f"Status: {muted} | Vision: {vision}\n"
               f"Memories: {stats['total_memories']} | Mood: {mood}")
        self.notify("JARVIS Status", msg)

    def _open_log(self, icon, item):
        import subprocess, os
        log_path = self.jarvis.logger.log_path
        if os.path.exists(log_path):
            subprocess.Popen(["notepad.exe", log_path])
        else:
            self.notify("JARVIS", "Log file not found.")

    def _open_local_gui(self, icon, item):
        import subprocess, sys, os
        gui_script = os.path.join(os.path.dirname(__file__), "jarvis_gui.py")
        # Run via pythonw to not block, no console pop
        subprocess.Popen([sys.executable, gui_script], 
                         creationflags=subprocess.CREATE_NO_WINDOW)

    def _quit(self, icon, item):
        self.notify("JARVIS", "Shutting down. Goodbye.")
        time.sleep(1)
        icon.stop()

    # ── Menu builder ─────────────────────────────────────────────
    def _build_menu(self) -> Menu:
        mute_label = "Unmute JARVIS" if self.jarvis.is_muted else "Mute JARVIS"
        vision_label = "Disable Vision" if self.jarvis.config.VISION_ENABLED else "Enable Vision"
        return Menu(
            item("⚡ Control Panel", self._open_local_gui, default=True),
            Menu.SEPARATOR,
            item("🎙 Status", self._show_status),
            item(mute_label, self._toggle_mute),
            item(vision_label, self._toggle_vision),
            Menu.SEPARATOR,
            item("📋 Open Log", self._open_log),
            Menu.SEPARATOR,
            item("❌ Quit JARVIS", self._quit),
        )

    def _rebuild_menu(self):
        if self.icon:
            self.icon.menu = self._build_menu()

    # ── Run ──────────────────────────────────────────────────────
    def run(self):
        """Start tray icon — blocks until quit"""
        icon_img = _make_icon()
        self.icon = pystray.Icon(
            name="JARVIS",
            icon=icon_img,
            title="JARVIS — Say 'Jarvis' or 'Hey Jarvis'",
            menu=self._build_menu(),
        )

        # Attach notify shortcut to jarvis for use from voice agent
        self.jarvis.tray = self
        self.jarvis.voice.on_wake = self.pulse_icon

        self.notify("JARVIS Online", "Say 'Jarvis' or 'Hey Jarvis' to begin.")
        self.icon.run()  # blocks here
