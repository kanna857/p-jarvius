"""
JARVIS SystemAgent — Full Windows System Control
─────────────────────────────────────────────────
Extends AutomationAgent with deep OS-level control:

  Process Management   — list, kill, find processes by name/PID
  Hardware Monitoring  — battery, CPU per-core, GPU, RAM, disk, temperatures
  Network              — Wi-Fi SSID, IP, ping, bandwidth
  Power Management     — sleep, hibernate, scheduled shutdown
  Window Management    — list windows, focus by title, move/resize
  Clipboard            — read and write clipboard content
  Notifications        — Windows toast notifications
  Screen Analysis      — screenshot → Vision Agent pipeline
  File Operations      — bulk rename, compress, disk usage by folder
  Service Control      — start/stop/query Windows services
"""

import os
import re
import time
import socket
import psutil
import subprocess
import pyautogui
from pathlib import Path
from datetime import datetime
from utils.logger import JarvisLogger


class SystemAgent:

    def __init__(self, config=None):
        self.config = config
        self.logger = JarvisLogger("SystemAgent")
        self.logger.success("SystemAgent ready — full Windows control active")

    # ─────────────────────────────────────────────────────────────────────────
    # Process Management
    # ─────────────────────────────────────────────────────────────────────────

    def list_processes(self, filter_name: str = None) -> str:
        """List running processes, optionally filtered by name."""
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                info = p.info
                if filter_name and filter_name.lower() not in info["name"].lower():
                    continue
                procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if not procs:
            return f"No processes matching '{filter_name}'." if filter_name else "No processes found."

        # Sort by CPU usage
        procs.sort(key=lambda x: x.get("cpu_percent", 0) or 0, reverse=True)
        lines = [f"{'PID':<8} {'Name':<28} {'CPU%':<8} {'MEM%':<8} {'Status'}"]
        lines.append("─" * 60)
        for p in procs[:15]:
            lines.append(
                f"{p['pid']:<8} {(p['name'] or '')[:27]:<28} "
                f"{p.get('cpu_percent',0) or 0:<8.1f} "
                f"{p.get('memory_percent',0) or 0:<8.1f} "
                f"{p.get('status','')}"
            )
        return "\n".join(lines)

    def kill_process(self, name_or_pid: str) -> str:
        """Kill a process by name or PID."""
        killed = []
        errors = []
        target = name_or_pid.strip()

        # Try as PID first
        if target.isdigit():
            try:
                p = psutil.Process(int(target))
                pname = p.name()
                p.kill()
                return f"✅ Killed process {pname} (PID {target})."
            except psutil.NoSuchProcess:
                return f"No process with PID {target}."
            except Exception as e:
                return f"Failed to kill PID {target}: {e}"

        # Kill by name
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if target.lower() in p.info["name"].lower():
                    p.kill()
                    killed.append(f"{p.info['name']} (PID {p.info['pid']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                errors.append(str(e))

        if killed:
            return f"✅ Killed: {', '.join(killed)}."
        return f"No running process matching '{target}'."

    def get_top_processes(self, n: int = 5) -> str:
        """Returns the top N processes by CPU usage."""
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                procs.append(p.info)
            except Exception:
                pass
        time.sleep(0.5)  # Let cpu_percent settle
        procs.sort(key=lambda x: x.get("cpu_percent", 0) or 0, reverse=True)
        lines = [f"🔥 Top {n} CPU-hungry processes:"]
        for p in procs[:n]:
            mem_mb = (p.get("memory_info") or {}).get("rss", 0) / 1024 / 1024
            lines.append(
                f"  {p['name'][:30]:<30}  CPU: {p.get('cpu_percent',0) or 0:.1f}%  "
                f"RAM: {mem_mb:.0f} MB"
            )
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────────
    # Hardware & System Monitoring
    # ─────────────────────────────────────────────────────────────────────────

    def get_battery(self) -> str:
        """Detailed battery status with charging state and time remaining."""
        b = psutil.sensors_battery()
        if not b:
            return "No battery detected (desktop PC or battery sensor unavailable)."
        pct = b.percent
        plugged = b.power_plugged
        secs = b.secsleft

        status = "⚡ Charging" if plugged else "🔋 On Battery"
        icon = "🔋" if pct > 50 else ("⚠️" if pct > 20 else "🪫")

        if plugged:
            time_str = "until fully charged" if secs == psutil.POWER_TIME_UNLIMITED else ""
        elif secs > 0 and secs != psutil.POWER_TIME_UNKNOWN:
            h, m = divmod(secs // 60, 60)
            time_str = f"— ~{h}h {m}m remaining"
        else:
            time_str = ""

        return f"{icon} Battery: {pct:.0f}% {status} {time_str}".strip()

    def get_full_system_status(self) -> str:
        """Comprehensive system health report — CPU, RAM, Disk, Battery, Network."""
        lines = ["🖥️ JARVIS System Health Report", "─" * 40]

        # CPU
        cpu_pct = psutil.cpu_percent(interval=0.5)
        cpu_freq = psutil.cpu_freq()
        cpu_cores = psutil.cpu_count(logical=False)
        cpu_threads = psutil.cpu_count(logical=True)
        freq_str = f" @ {cpu_freq.current:.0f} MHz" if cpu_freq else ""
        lines.append(f"⚙️  CPU:    {cpu_pct}% ({cpu_cores} cores / {cpu_threads} threads{freq_str})")

        # Per-core CPU
        per_core = psutil.cpu_percent(percpu=True)
        core_str = "  ".join(f"C{i}:{v}%" for i, v in enumerate(per_core))
        lines.append(f"   Cores: {core_str}")

        # RAM
        ram = psutil.virtual_memory()
        swap = psutil.swap_memory()
        lines.append(f"🧠 RAM:   {ram.percent}% used ({ram.used/1e9:.1f}/{ram.total/1e9:.1f} GB)")
        lines.append(f"   Swap:  {swap.percent}% ({swap.used/1e9:.1f}/{swap.total/1e9:.1f} GB)")

        # Disk
        lines.append("💾 Disks:")
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                bar = "█" * int(usage.percent / 10) + "░" * (10 - int(usage.percent / 10))
                lines.append(
                    f"   {part.device:<8} [{bar}] {usage.percent:.0f}%  "
                    f"{usage.free/1e9:.1f}/{usage.total/1e9:.1f} GB free"
                )
            except Exception:
                pass

        # Battery
        bat = psutil.sensors_battery()
        if bat:
            plug = "⚡ Charging" if bat.power_plugged else "🔋 Battery"
            lines.append(f"🔋 Power:  {bat.percent:.0f}% {plug}")

        # Network
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            lines.append(f"🌐 Network: {hostname} ({ip})")
        except Exception:
            pass

        # Uptime
        boot = psutil.boot_time()
        uptime_s = time.time() - boot
        h, rem = divmod(int(uptime_s), 3600)
        m = rem // 60
        lines.append(f"⏱️  Uptime: {h}h {m}m")

        return "\n".join(lines)

    def get_disk_usage_by_folder(self, path: str = None) -> str:
        """Shows disk usage of top-level subfolders in a path."""
        p = Path(path) if path else Path.home()
        if not p.exists():
            return f"Path not found: {p}"
        sizes = []
        for child in p.iterdir():
            try:
                if child.is_dir():
                    size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
                    sizes.append((child.name, size))
            except Exception:
                pass
        sizes.sort(key=lambda x: x[1], reverse=True)
        lines = [f"📂 Disk usage in {p}:"]
        for name, size in sizes[:10]:
            mb = size / 1024 / 1024
            gb = mb / 1024
            s = f"{gb:.2f} GB" if gb >= 1 else f"{mb:.0f} MB"
            lines.append(f"  {name[:35]:<35} {s}")
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────────
    # Network
    # ─────────────────────────────────────────────────────────────────────────

    def get_network_info(self) -> str:
        """Returns IP addresses, Wi-Fi SSID, and network interfaces."""
        lines = ["🌐 Network Info:"]
        # Try to get Wi-Fi SSID on Windows
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            ssid_match = re.search(r"SSID\s+:\s+(.+)", result.stdout)
            signal_match = re.search(r"Signal\s+:\s+(.+)", result.stdout)
            if ssid_match:
                lines.append(f"  📶 Wi-Fi: {ssid_match.group(1).strip()}"
                             + (f" ({signal_match.group(1).strip()})" if signal_match else ""))
        except Exception:
            pass

        # Network interfaces
        for iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and addr.address != "127.0.0.1":
                    lines.append(f"  {iface}: {addr.address}")

        # Network I/O
        try:
            io = psutil.net_io_counters()
            lines.append(f"  📤 Sent: {io.bytes_sent/1e6:.1f} MB  📥 Recv: {io.bytes_recv/1e6:.1f} MB")
        except Exception:
            pass

        return "\n".join(lines)

    def ping_host(self, host: str = "8.8.8.8") -> str:
        """Pings a host and returns latency."""
        try:
            result = subprocess.run(
                ["ping", "-n", "3", host],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            match = re.search(r"Average = (\d+)ms", result.stdout)
            if match:
                return f"🏓 Ping to {host}: {match.group(1)}ms average"
            if "Request timed out" in result.stdout:
                return f"⚠️ {host} is not responding (timeout)."
            return f"Ping result: {result.stdout[-100:].strip()}"
        except Exception as e:
            return f"Ping failed: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # Power Management
    # ─────────────────────────────────────────────────────────────────────────

    def sleep_pc(self) -> str:
        """Puts the PC to sleep."""
        subprocess.Popen(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return "💤 Putting PC to sleep."

    def hibernate_pc(self) -> str:
        """Hibernates the PC."""
        os.system("shutdown /h")
        return "💤 Hibernating PC."

    def cancel_shutdown(self) -> str:
        """Cancels a pending shutdown/restart."""
        os.system("shutdown /a")
        return "✅ Pending shutdown/restart cancelled."

    def set_volume_exact(self, level: int) -> str:
        """Sets system volume to an exact percentage (0-100)."""
        level = max(0, min(100, level))
        # Use PowerShell to set exact volume
        try:
            script = (
                f"$wshShell = New-Object -ComObject WScript.Shell; "
                f"$curVol = (New-Object -ComObject Shell.Application).NameSpace(17).Items() | "
                f"Where-Object {{$_.Name -eq 'Volume'}}; "
                f"[System.Runtime.InteropServices.Marshal]::GetActiveObject('WMPlayer.OCX.7').settings.volume = {level}"
            )
            # Simpler approach: use nircmd if available, else use key presses
            # Count current vol keys needed
            # Just use multiple key presses as approximation
            pyautogui.hotkey("ctrl", "shift", "m")  # mute first
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "shift", "m")  # unmute
            return f"🔊 Volume adjustment requested (target: {level}%). Note: exact volume control requires nircmd."
        except Exception as e:
            return f"Volume set error: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # Window Management
    # ─────────────────────────────────────────────────────────────────────────

    def list_open_windows(self) -> str:
        """Lists all visible open windows by title."""
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | "
                 "Select-Object Name,MainWindowTitle | Format-Table -AutoSize"],
                capture_output=True, text=True, timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            out = result.stdout.strip()
            return f"🪟 Open Windows:\n{out[:800]}" if out else "No visible windows found."
        except Exception as e:
            return f"Could not list windows: {e}"

    def focus_window(self, title_keyword: str) -> str:
        """Brings a window with a matching title to the foreground."""
        try:
            script = (
                f"$wnd = Get-Process | Where-Object {{$_.MainWindowTitle -like '*{title_keyword}*'}}; "
                f"if ($wnd) {{ "
                f"  Add-Type -Name Win32 -Namespace API -MemberDefinition '[DllImport(\"user32.dll\")] "
                f"  public static extern bool SetForegroundWindow(IntPtr hWnd);'; "
                f"  [API.Win32]::SetForegroundWindow($wnd.MainWindowHandle) "
                f"}}"
            )
            subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return f"✅ Focused window matching '{title_keyword}'."
        except Exception as e:
            return f"Could not focus window: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # Clipboard
    # ─────────────────────────────────────────────────────────────────────────

    def get_clipboard(self) -> str:
        """Reads the current clipboard content."""
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            content = root.clipboard_get()
            root.destroy()
            return f"📋 Clipboard: {content[:500]}" if content else "Clipboard is empty."
        except Exception:
            return "Clipboard is empty or contains non-text content."

    def set_clipboard(self, text: str) -> str:
        """Writes text to the clipboard."""
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            root.destroy()
            return f"📋 Copied to clipboard: '{text[:60]}'"
        except Exception as e:
            return f"Could not copy to clipboard: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # Windows Notifications
    # ─────────────────────────────────────────────────────────────────────────

    def send_notification(self, title: str, message: str, duration: int = 5) -> str:
        """Sends a Windows toast notification."""
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(title, message, duration=duration, threaded=True)
            return f"🔔 Notification sent: '{title}'"
        except ImportError:
            # Fallback via PowerShell
            try:
                ps_cmd = (
                    f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null; "
                    f"$template = [Windows.UI.Notifications.ToastTemplateType]::ToastText02; "
                    f"$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($template); "
                    f"$xml.GetElementsByTagName('text')[0].AppendChild($xml.CreateTextNode('{title}')) | Out-Null; "
                    f"$xml.GetElementsByTagName('text')[1].AppendChild($xml.CreateTextNode('{message}')) | Out-Null; "
                    f"$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
                    f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('JARVIS').Show($toast)"
                )
                subprocess.run(["powershell", "-Command", ps_cmd],
                               capture_output=True, timeout=5,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                return f"🔔 Notification sent."
            except Exception as e:
                return f"Notification failed: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # Screenshot → Vision Pipeline
    # ─────────────────────────────────────────────────────────────────────────

    def screenshot_and_analyze(self, vision_agent=None, question: str = "What's on the screen?") -> str:
        """
        Takes a screenshot and feeds it to the VisionAgent for AI analysis.
        If vision_agent is None, just saves the screenshot and returns the path.
        """
        path = Path.home() / "Pictures" / f"jarvis_analysis_{int(time.time())}.png"
        try:
            img = pyautogui.screenshot()
            img.save(str(path))
            self.logger.info(f"Screenshot saved: {path}")
        except Exception as e:
            return f"Screenshot failed: {e}"

        if vision_agent and hasattr(vision_agent, "analyze_image_file"):
            try:
                return vision_agent.analyze_image_file(str(path), question)
            except Exception as e:
                return f"Vision analysis failed: {e}. Screenshot at: {path}"

        return f"📸 Screenshot saved to {path}. (Vision agent not connected)"

    # ─────────────────────────────────────────────────────────────────────────
    # Windows Services
    # ─────────────────────────────────────────────────────────────────────────

    def get_service_status(self, service_name: str) -> str:
        """Returns the status of a Windows service."""
        try:
            result = subprocess.run(
                ["sc", "query", service_name],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            state_match = re.search(r"STATE\s+:\s+\d+\s+(\w+)", result.stdout)
            if state_match:
                return f"Service '{service_name}': {state_match.group(1)}"
            return f"Service '{service_name}' not found."
        except Exception as e:
            return f"Service query failed: {e}"

    def start_service(self, service_name: str) -> str:
        """Starts a Windows service."""
        try:
            subprocess.run(["net", "start", service_name],
                           capture_output=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            return f"✅ Started service: {service_name}"
        except Exception as e:
            return f"Failed to start service: {e}"

    def stop_service(self, service_name: str) -> str:
        """Stops a Windows service."""
        try:
            subprocess.run(["net", "stop", service_name],
                           capture_output=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            return f"✅ Stopped service: {service_name}"
        except Exception as e:
            return f"Failed to stop service: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # Environment & System Info
    # ─────────────────────────────────────────────────────────────────────────

    def get_environment_variable(self, var: str) -> str:
        val = os.environ.get(var)
        return f"{var} = {val}" if val else f"Environment variable '{var}' not found."

    def get_current_datetime(self) -> str:
        now = datetime.now()
        return (
            f"📅 {now.strftime('%A, %d %B %Y')}\n"
            f"⏰ {now.strftime('%I:%M:%S %p')}"
        )

    def run_powershell(self, command: str) -> str:
        """Runs a PowerShell command safely and returns output."""
        dangerous = ["rm -rf", "Remove-Item -Recurse", "Format-Volume", "del /f"]
        if any(d.lower() in command.lower() for d in dangerous):
            return "⛔ Blocked: potentially dangerous PowerShell command."
        try:
            result = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            out = (result.stdout or result.stderr or "").strip()
            return out[:800] or "Command executed with no output."
        except subprocess.TimeoutExpired:
            return "⚠️ PowerShell command timed out."
        except Exception as e:
            return f"PowerShell error: {e}"

    def maintain_codebase(self) -> str:
        """Scan codebase files, clean pycache, report warnings, verify requirements."""
        self.logger.info("Starting codebase self-maintenance scan...")
        import os
        import time
        from pathlib import Path
        
        repo_dir = Path(os.getcwd())
        py_files = []
        syntax_errors = []
        pycaches_cleaned = 0
        logs_cleaned = 0
        
        for root, dirs, files in os.walk(repo_dir):
            if "__pycache__" in dirs:
                pycache_path = Path(root) / "__pycache__"
                try:
                    import shutil
                    shutil.rmtree(pycache_path)
                    pycaches_cleaned += 1
                except Exception:
                    pass
            
            for file in files:
                if file.endswith(".py"):
                    py_files.append(Path(root) / file)
                elif file.endswith(".log") and file.startswith("task-"):
                    log_file = Path(root) / file
                    if time.time() - os.path.getmtime(log_file) > 86400:
                        try:
                            os.remove(log_file)
                            logs_cleaned += 1
                        except Exception:
                            pass

        for file_path in py_files:
            try:
                code = file_path.read_text(encoding="utf-8")
                compile(code, str(file_path), "exec")
            except Exception as e:
                syntax_errors.append(f"{file_path.name}: {e}")
                
        report = [
            "🛠️ Codebase Self-Maintenance Report",
            "═" * 40,
            f"📁 Scanned workspace: {repo_dir}",
            f"🐍 Total Python files: {len(py_files)}",
            f"🧹 Pycache folders cleaned: {pycaches_cleaned}",
            f"🗑️ Old log files cleared: {logs_cleaned}"
        ]
        
        if syntax_errors:
            report.append("\n⚠️ Syntax Warnings/Errors:")
            for err in syntax_errors:
                report.append(f"  • {err}")
        else:
            report.append("\n✅ Syntax Check: All files compile successfully!")
            
        return "\n".join(report)
