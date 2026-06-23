import tkinter as tk
from tkinter import ttk
import sys
import os
import time
import ctypes

# Ensure project directory is in path for importing utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.state_manager import state_manager

class ChatBox:
    def __init__(self, root):
        self.root = root
        self.root.title("JARVIS AI")
        
        # Borderless window, always on top
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#0b0f19")
        
        # Window dimensions - vertical chatbot copilot style
        self.width = 450
        self.height = 600
        
        # Position on the right side of the screen, offset from edge
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.x = screen_width - self.width - 40
        self.y = (screen_height - self.height) // 2
        
        self.root.geometry(f"{self.width}x{self.height}+{self.x}+{self.y}")
        
        # Glowing border frame (cyan color look)
        border_frame = tk.Frame(self.root, bg="#00f2fe", bd=1)
        border_frame.pack(fill="both", expand=True)
        
        # Inner main container
        self.inner = tk.Frame(border_frame, bg="#0b0f19")
        self.inner.pack(fill="both", expand=True, padx=1, pady=1)
        
        # ── 1. HEADER BAR ──
        self.header = tk.Frame(self.inner, bg="#0d1117", height=40)
        self.header.pack(fill="x", side="top")
        self.header.pack_propagate(False)
        
        # Drag bindings for header
        self.header.bind("<Button-1>", self.start_drag)
        self.header.bind("<B1-Motion>", self.drag)
        
        # Title
        self.lbl_title = tk.Label(self.header, text="⚡ JARVIS AI", font=("Segoe UI", 10, "bold"), bg="#0d1117", fg="#00f2fe")
        self.lbl_title.pack(side="left", padx=12)
        self.lbl_title.bind("<Button-1>", self.start_drag)
        self.lbl_title.bind("<B1-Motion>", self.drag)
        
        # Status dot / label
        self.lbl_status = tk.Label(self.header, text="● ONLINE", font=("Segoe UI", 8, "bold"), bg="#0d1117", fg="#10b981")
        self.lbl_status.pack(side="left", padx=(5, 0))
        self.lbl_status.bind("<Button-1>", self.start_drag)
        self.lbl_status.bind("<B1-Motion>", self.drag)
        
        # Close button (×)
        self.btn_close = tk.Label(self.header, text=" × ", font=("Segoe UI", 12, "bold"), bg="#0d1117", fg="#9ca3af", cursor="hand2")
        self.btn_close.pack(side="right", padx=(0, 6))
        self.btn_close.bind("<Button-1>", lambda e: self.go_idle())
        self.btn_close.bind("<Enter>", lambda e: self.btn_close.config(fg="#ef4444", bg="#1f2937"))
        self.btn_close.bind("<Leave>", lambda e: self.btn_close.config(fg="#9ca3af", bg="#0d1117"))
        
        # Minimize/Hide button (−)
        self.btn_min = tk.Label(self.header, text=" − ", font=("Segoe UI", 12, "bold"), bg="#0d1117", fg="#9ca3af", cursor="hand2")
        self.btn_min.pack(side="right")
        self.btn_min.bind("<Button-1>", lambda e: self.root.withdraw())
        self.btn_min.bind("<Enter>", lambda e: self.btn_min.config(fg="#ffffff", bg="#1f2937"))
        self.btn_min.bind("<Leave>", lambda e: self.btn_min.config(fg="#9ca3af", bg="#0d1117"))
        
        # Pin toggle button (📌)
        self.pinned = False
        self.btn_pin = tk.Label(self.header, text="📌", font=("Segoe UI", 10), bg="#0d1117", fg="#64748b", cursor="hand2")
        self.btn_pin.pack(side="right", padx=6)
        self.btn_pin.bind("<Button-1>", lambda e: self.toggle_pin())
        self.btn_pin.bind("<Enter>", lambda e: self.btn_pin.config(bg="#1f2937") if not self.pinned else None)
        self.btn_pin.bind("<Leave>", lambda e: self.btn_pin.config(bg="#0d1117") if not self.pinned else None)
        
        # Separator line under header
        sep = tk.Frame(self.inner, bg="#1e293b", height=1)
        sep.pack(fill="x")
        
        # ── 2. SCROLLABLE CHAT AREA ──
        self.chat_frame = tk.Frame(self.inner, bg="#0b0f19")
        self.chat_frame.pack(fill="both", expand=True, padx=12, pady=(10, 5))
        
        self.scrollbar = tk.Scrollbar(self.chat_frame, orient="vertical", width=10)
        self.scrollbar.pack(side="right", fill="y")
        
        self.txt_history = tk.Text(
            self.chat_frame,
            bg="#0b0f19",
            fg="#ffffff",
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=0,
            yscrollcommand=self.scrollbar.set,
            wrap="word",
            padx=5,
            pady=5
        )
        self.txt_history.pack(side="left", fill="both", expand=True)
        self.scrollbar.config(command=self.txt_history.yview)
        
        # Text Tags for formatting messages beautifully
        self.txt_history.tag_configure("user_hdr", foreground="#00f2fe", font=("Segoe UI", 9, "bold"), spacing1=12)
        self.txt_history.tag_configure("user_msg", foreground="#ffffff", font=("Segoe UI", 10), lmargin1=15, lmargin2=15, spacing3=12)
        self.txt_history.tag_configure("jarvis_hdr", foreground="#84cc16", font=("Segoe UI", 9, "bold"), spacing1=12)
        self.txt_history.tag_configure("jarvis_msg", foreground="#e5e7eb", font=("Segoe UI", 10), lmargin1=15, lmargin2=15, spacing3=12)
        self.txt_history.tag_configure(
            "code_block",
            background="#1e293b",
            foreground="#f1f5f9",
            font=("Consolas", 9),
            lmargin1=25,
            lmargin2=25,
            spacing1=8,
            spacing3=8
        )
        self.txt_history.config(state="disabled")
        
        # Right-click context menu for Copy/Copy All functionality
        self.context_menu = tk.Menu(self.root, tearoff=0, bg="#0d1117", fg="#ffffff", activebackground="#1e293b", activeforeground="#00f2fe")
        self.context_menu.add_command(label="Copy Selected", command=self.copy_selection)
        self.context_menu.add_command(label="Copy All Messages", command=self.copy_all)
        self.txt_history.bind("<Button-3>", self.show_context_menu)
        
        # ── 3. INPUT AREA ──
        self.input_container = tk.Frame(self.inner, bg="#0b0f19")
        self.input_container.pack(fill="x", side="bottom", padx=12, pady=(5, 12))
        
        self.entry_border = tk.Frame(self.input_container, bg="#1e293b", bd=1)
        self.entry_border.pack(fill="x", side="left", expand=True)
        
        self.entry_bg = tk.Frame(self.entry_border, bg="#111827")
        self.entry_bg.pack(fill="x", padx=1, pady=1)
        
        self.entry = tk.Entry(
            self.entry_bg,
            font=("Segoe UI", 10),
            bg="#111827",
            fg="#ffffff",
            bd=0,
            highlightthickness=0,
            insertbackground="#00f2fe"
        )
        self.entry.pack(fill="x", padx=10, pady=8)
        
        # Send Button
        self.btn_send = tk.Label(self.input_container, text=" ➤ ", font=("Segoe UI", 12, "bold"), bg="#1f2937", fg="#00f2fe", cursor="hand2")
        self.btn_send.pack(side="right", padx=(8, 0))
        self.btn_send.bind("<Button-1>", lambda e: self.submit())
        self.btn_send.bind("<Enter>", lambda e: self.btn_send.config(bg="#00f2fe", fg="#0b0f19"))
        self.btn_send.bind("<Leave>", lambda e: self.btn_send.config(bg="#1f2937", fg="#00f2fe"))
        
        # Resize grip in bottom-right corner
        self.grip = tk.Label(self.inner, text=" ◢ ", bg="#0b0f19", fg="#00f2fe", font=("Segoe UI", 14), cursor="size_nw_se")
        self.grip.place(relx=1.0, rely=1.0, anchor="se", x=-2, y=-2)
        self.grip.bind("<Button-1>", self.start_resize)
        self.grip.bind("<B1-Motion>", self.resize)
        
        # Event bindings
        self.entry.bind("<Return>", self.submit)
        self.root.bind("<Escape>", lambda e: self.go_idle())
        self.root.bind("<FocusOut>", self.on_focus_out)
        
        # State tracking
        self.waiting = False
        self.displayed_history_len = 0
        self.last_history = []
        self.hwnd = self.root.winfo_id()
        self.startup_time = time.time()
        
        # Hide initially
        self.go_idle()
        
        # Start state manager polling loop
        self.poll_state()

    def go_idle(self):
        self.waiting = False
        self.entry.delete(0, tk.END)
        self.root.withdraw()

    def wake_up(self):
        # Center or restore right-side coordinates
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.x = screen_width - self.width - 40
        self.y = (screen_height - self.height) // 2
        self.root.geometry(f"{self.width}x{self.height}+{self.x}+{self.y}")
        
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.root.lift()
        
        try:
            ctypes.windll.user32.SetForegroundWindow(self.hwnd)
        except Exception:
            pass
            
        self.entry.focus_force()

    def toggle_pin(self):
        self.pinned = not self.pinned
        if self.pinned:
            self.btn_pin.config(fg="#00f2fe")
        else:
            self.btn_pin.config(fg="#64748b")

    def start_drag(self, event):
        self.drag_start_x = event.x_root
        self.drag_start_y = event.y_root
        self.window_start_x = self.root.winfo_x()
        self.window_start_y = self.root.winfo_y()

    def drag(self, event):
        dx = event.x_root - self.drag_start_x
        dy = event.y_root - self.drag_start_y
        self.x = self.window_start_x + dx
        self.y = self.window_start_y + dy
        self.root.geometry(f"+{self.x}+{self.y}")

    def start_resize(self, event):
        self.resize_start_x = event.x_root
        self.resize_start_y = event.y_root
        self.resize_start_width = self.root.winfo_width()
        self.resize_start_height = self.root.winfo_height()

    def resize(self, event):
        dx = event.x_root - self.resize_start_x
        dy = event.y_root - self.resize_start_y
        self.width = max(300, self.resize_start_width + dx)
        self.height = max(350, self.resize_start_height + dy)
        self.root.geometry(f"{self.width}x{self.height}+{self.root.winfo_x()}+{self.root.winfo_y()}")

    def on_focus_out(self, event=None):
        if self.pinned or self.waiting:
            return
            
        # Check if the new focused widget belongs to this window
        focused = self.root.focus_get()
        if focused is None:
            self.go_idle()

    def submit(self, event=None):
        cmd = self.entry.get().strip()
        if not cmd:
            return
            
        self.entry.delete(0, tk.END)
        
        # Append User Message locally immediately for instant feedback
        self.txt_history.config(state="normal")
        self.txt_history.insert(tk.END, "👤 You\n", "user_hdr")
        self.txt_history.insert(tk.END, f"{cmd}\n\n", "user_msg")
        self.txt_history.config(state="disabled")
        self.txt_history.see(tk.END)
        
        # Increment displayed history length by 1 for user message
        self.displayed_history_len += 1
        
        # Inject command into state manager for Jarvis to process
        state_manager.inject_command(cmd)
        self.waiting = True

    def poll_state(self):
        try:
            state = state_manager.get_state()
            
            # 1. Shutdown signal
            if state.get("status") == "Offline":
                if time.time() - self.startup_time > 5:
                    self.root.destroy()
                    return
            
            # 2. Wake chat box signal
            if state.get("wake_chat_box", False):
                state["wake_chat_box"] = False
                state_manager.save_state(state)
                if self.root.winfo_viewable():
                    self.go_idle()
                else:
                    self.wake_up()
            
            # 3. Temporary hide signal (for vision/screenshots)
            if state.get("hide_chat_box", False):
                if self.root.winfo_viewable():
                    self.root.withdraw()
            else:
                # Re-appear if temporary hide finished and we are waiting
                if not self.root.winfo_viewable() and self.waiting:
                    self.root.deiconify()
                    self.root.attributes("-topmost", True)
                    self.root.lift()
            
            # 4. Sync conversation log
            history = state.get("conversation_history", [])
            if history != self.last_history:
                self.rebuild_chat_log(history)
                # Response is received, stop waiting status
                self.waiting = False
            
            # 5. Sync thinking/mute status
            is_thinking = state.get("pending_commands", [])
            if is_thinking:
                self.lbl_status.config(text="● JARVIS IS THINKING...", fg="#eab308")
            else:
                status = state.get("status", "Active")
                if status == "Muted":
                    self.lbl_status.config(text="● MUTED", fg="#ef4444")
                else:
                    self.lbl_status.config(text="● ONLINE", fg="#10b981")
                    
        except Exception:
            pass
            
        self.root.after(50, self.poll_state)

    def rebuild_chat_log(self, history):
        self.txt_history.config(state="normal")
        self.txt_history.delete("1.0", tk.END)
        
        for msg in history:
            role = msg.get("role")
            content = msg.get("content", "")
            
            if role == "user":
                self.txt_history.insert(tk.END, "👤 You\n", "user_hdr")
                self.txt_history.insert(tk.END, f"{content}\n\n", "user_msg")
            else:
                self.txt_history.insert(tk.END, "🤖 JARVIS\n", "jarvis_hdr")
                
                # Render text with parsed markdown code blocks
                parts = content.split("```")
                for i, part in enumerate(parts):
                    if i % 2 == 1:
                        # Inside code block
                        lines = part.split("\n")
                        first_line = lines[0].strip()
                        # Skip programming language label line if present
                        if first_line and first_line.isidentifier() and not first_line.isnumeric():
                            code_text = "\n".join(lines[1:])
                        else:
                            code_text = part
                        self.txt_history.insert(tk.END, code_text.strip("\n") + "\n", "code_block")
                    else:
                        # Normal text content
                        self.txt_history.insert(tk.END, part, "jarvis_msg")
                self.txt_history.insert(tk.END, "\n\n")
                
        self.txt_history.config(state="disabled")
        self.txt_history.see(tk.END)
        self.last_history = list(history)
        self.displayed_history_len = len(history)

    def show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def copy_selection(self):
        try:
            selected_text = self.txt_history.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_text)
        except tk.TclError:
            pass # No selection or disabled copy

    def copy_all(self):
        entire_text = self.txt_history.get("1.0", tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(entire_text)

def main():
    root = tk.Tk()
    app = ChatBox(root)
    root.focus_force()
    root.mainloop()

if __name__ == "__main__":
    main()
