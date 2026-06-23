import tkinter as tk
from tkinter import ttk, messagebox
import json
from utils.workflow_manager import workflow_manager
from utils.state_manager import state_manager
from agents.task_agent import TaskAgent

class JarvisLocalApp:
    def __init__(self, root):
        self.root = root
        self.root.title("JARVIS Local Control Panel")
        self.root.geometry("600x500")
        self.root.configure(bg="#0b0f19")
        
        # Initialize agents
        self.task_agent = TaskAgent()
        
        # Setup dark theme styling
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background="#0b0f19")
        style.configure("TLabel", background="#0b0f19", foreground="#00f2fe", font=("Segoe UI", 10))
        style.configure("TButton", background="#1f2937", foreground="#00f2fe", borderwidth=1, font=("Segoe UI", 9, "bold"))
        style.map("TButton", background=[("active", "#00f2fe")], foreground=[("active", "#0b0f19")])
        style.configure("TNotebook", background="#0b0f19", borderwidth=0)
        style.configure("TNotebook.Tab", background="#111827", foreground="#9ca3af", padding=[10, 5])
        style.map("TNotebook.Tab", background=[("selected", "#1f2937")], foreground=[("selected", "#00f2fe")])
        style.configure("Treeview", background="#111827", fieldbackground="#111827", foreground="#ffffff", borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#1f2937", foreground="#00f2fe", font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#00f2fe")], foreground=[("selected", "#0b0f19")])
        
        # Create Notebook Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.tab_home = ttk.Frame(self.notebook)
        self.tab_builder = ttk.Frame(self.notebook)
        self.tab_tasks = ttk.Frame(self.notebook)
        
        self.notebook.add(self.tab_home, text="  ⚡ QUICK RUN  ")
        self.notebook.add(self.tab_builder, text="  🛠️ WORKFLOW BUILDER  ")
        self.notebook.add(self.tab_tasks, text="  📋 TASK MANAGER  ")
        
        self.setup_home_tab()
        self.setup_builder_tab()
        self.setup_tasks_tab()
        
        # Current working steps for new workflow
        self.pending_steps = []

    def setup_home_tab(self):
        # Header
        hdr = tk.Label(self.tab_home, text="JARVIS COMMANDER", font=("Segoe UI", 16, "bold"), bg="#0b0f19", fg="#00f2fe")
        hdr.pack(pady=20)
        
        # Container for list
        frame = tk.Frame(self.tab_home, bg="#0b0f19")
        frame.pack(fill="both", expand=True, padx=40)
        
        lbl = tk.Label(frame, text="Saved Workflows:", bg="#0b0f19", fg="#9ca3af")
        lbl.pack(anchor="w")
        
        self.listbox = tk.Listbox(frame, bg="#111827", fg="#ffffff", selectbackground="#00f2fe", selectforeground="#0b0f19", borderwidth=0, height=10, font=("Segoe UI", 10))
        self.listbox.pack(fill="both", expand=True, pady=5)
        
        # Button Frame
        btn_frame = tk.Frame(self.tab_home, bg="#0b0f19")
        btn_frame.pack(fill="x", padx=40, pady=20)
        
        run_btn = ttk.Button(btn_frame, text="🚀 LAUNCH WORKFLOW", command=self.run_selected_workflow)
        run_btn.pack(side="left", fill="x", expand=True, padx=5)
        
        refresh_btn = ttk.Button(btn_frame, text="🔄 REFRESH", command=self.refresh_list)
        refresh_btn.pack(side="left", fill="x", expand=True, padx=5)
        
        self.refresh_list()

    def setup_builder_tab(self):
        # Top container for naming
        top = tk.Frame(self.tab_builder, bg="#0b0f19")
        top.pack(fill="x", padx=20, pady=10)
        
        tk.Label(top, text="Workflow Name:", bg="#0b0f19", fg="#9ca3af").pack(side="left")
        self.wf_name_entry = tk.Entry(top, bg="#111827", fg="#ffffff", insertbackground="#ffffff", borderwidth=1)
        self.wf_name_entry.pack(side="left", fill="x", expand=True, padx=10)
        
        # Middle container split in two
        mid = tk.Frame(self.tab_builder, bg="#0b0f19")
        mid.pack(fill="both", expand=True, padx=20)
        
        # Left: Add inputs
        left = tk.LabelFrame(mid, text=" Add Step ", bg="#0b0f19", fg="#00f2fe")
        left.pack(side="left", fill="both", expand=True, padx=5)
        
        tk.Label(left, text="Type:", bg="#0b0f19", fg="#9ca3af").pack(anchor="w", padx=5)
        self.step_type = ttk.Combobox(left, values=["tool", "ai_prompt", "wait"], state="readonly")
        self.step_type.pack(fill="x", padx=5, pady=5)
        self.step_type.set("tool")
        
        tk.Label(left, text="Value / Tool:", bg="#0b0f19", fg="#9ca3af").pack(anchor="w", padx=5)
        self.val_entry = tk.Entry(left, bg="#111827", fg="#ffffff", insertbackground="#ffffff")
        self.val_entry.pack(fill="x", padx=5, pady=5)
        tk.Label(left, text="(e.g. check_weather, open_app, prompt text)", bg="#0b0f19", fg="#64748b", font=("Segoe UI", 8)).pack(anchor="w", padx=5)
        
        tk.Label(left, text="Arguments (JSON if tool):", bg="#0b0f19", fg="#9ca3af").pack(anchor="w", padx=5)
        self.arg_entry = tk.Entry(left, bg="#111827", fg="#ffffff", insertbackground="#ffffff")
        self.arg_entry.pack(fill="x", padx=5, pady=5)
        self.arg_entry.insert(0, "{}")
        
        ttk.Button(left, text="➕ ADD STEP", command=self.add_step_to_pending).pack(pady=15, padx=5, fill="x")
        
        # Right: Preview
        right = tk.LabelFrame(mid, text=" Current Sequence ", bg="#0b0f19", fg="#00f2fe")
        right.pack(side="left", fill="both", expand=True, padx=5)
        
        self.preview_list = tk.Listbox(right, bg="#111827", fg="#84cc16", borderwidth=0, font=("Consolas", 9))
        self.preview_list.pack(fill="both", expand=True, padx=5, pady=5)
        
        ttk.Button(right, text="🧹 CLEAR", command=self.clear_pending).pack(pady=5, padx=5, fill="x")
        
        # Bottom: Save
        bot = tk.Frame(self.tab_builder, bg="#0b0f19")
        bot.pack(fill="x", pady=15, padx=20)
        
        ttk.Button(bot, text="💾 SAVE COMPLETED WORKFLOW", command=self.save_workflow).pack(fill="x", ipady=5)

    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        workflows = workflow_manager.get_all()
        for name in workflows.keys():
            self.listbox.insert(tk.END, name)

    def run_selected_workflow(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("Jarvis", "Please select a workflow first.")
            return
        wf_name = self.listbox.get(sel[0])
        state_manager.inject_command(f"Execute {wf_name} workflow")
        messagebox.showinfo("Sent", f"Executed {wf_name} request sent to JARVIS.")

    def add_step_to_pending(self):
        stype = self.step_type.get()
        val = self.val_entry.get().strip()
        arg_str = self.arg_entry.get().strip() or "{}"
        
        if not val and stype != "wait":
            messagebox.showerror("Error", "Please enter a value/tool name.")
            return
            
        step = {"type": stype}
        
        if stype == "tool":
            step["name"] = val
            try:
                step["args"] = json.loads(arg_str)
            except:
                messagebox.showerror("Error", "Invalid JSON in arguments.")
                return
            self.preview_list.insert(tk.END, f"Tool: {val}")
            
        elif stype == "ai_prompt":
            step["prompt"] = val
            self.preview_list.insert(tk.END, f"AI: {val[:20]}...")
            
        elif stype == "wait":
            step["seconds"] = int(val) if val.isdigit() else 5
            self.preview_list.insert(tk.END, f"Wait: {step['seconds']}s")
            
        self.pending_steps.append(step)
        self.val_entry.delete(0, tk.END)

    def clear_pending(self):
        self.pending_steps = []
        self.preview_list.delete(0, tk.END)

    def save_workflow(self):
        name = self.wf_name_entry.get().strip()
        if not name or not self.pending_steps:
            messagebox.showerror("Error", "Need both workflow name and at least 1 step.")
            return
            
        workflow_manager.save_workflow(name, self.pending_steps)
        messagebox.showinfo("Success", f"Workflow '{name}' saved!")
        self.clear_pending()
        self.wf_name_entry.delete(0, tk.END)
        self.refresh_list()
        # Switch to first tab
        self.notebook.select(0)

    def setup_tasks_tab(self):
        # We split the tab into Left (Add Task Form) and Right (Task list Treeview)
        left = tk.Frame(self.tab_tasks, bg="#0b0f19", width=200)
        left.pack(side="left", fill="both", expand=False, padx=10, pady=10)
        
        right = tk.Frame(self.tab_tasks, bg="#0b0f19")
        right.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        
        # --- Left Pane: Add Task Form ---
        lbl_title = tk.Label(left, text="Add New Task", font=("Segoe UI", 12, "bold"), bg="#0b0f19", fg="#00f2fe")
        lbl_title.pack(anchor="w", pady=(0, 10))
        
        tk.Label(left, text="Title:", bg="#0b0f19", fg="#9ca3af").pack(anchor="w")
        self.task_title_entry = tk.Entry(left, bg="#111827", fg="#ffffff", insertbackground="#ffffff", borderwidth=1)
        self.task_title_entry.pack(fill="x", pady=(0, 10))
        
        tk.Label(left, text="Description:", bg="#0b0f19", fg="#9ca3af").pack(anchor="w")
        self.task_desc_entry = tk.Entry(left, bg="#111827", fg="#ffffff", insertbackground="#ffffff", borderwidth=1)
        self.task_desc_entry.pack(fill="x", pady=(0, 10))
        
        tk.Label(left, text="Priority:", bg="#0b0f19", fg="#9ca3af").pack(anchor="w")
        self.task_priority = ttk.Combobox(left, values=["Low", "Medium", "High"], state="readonly")
        self.task_priority.pack(fill="x", pady=(0, 10))
        self.task_priority.set("Medium")
        
        tk.Label(left, text="Due Date (optional):", bg="#0b0f19", fg="#9ca3af").pack(anchor="w")
        self.task_due_entry = tk.Entry(left, bg="#111827", fg="#ffffff", insertbackground="#ffffff", borderwidth=1)
        self.task_due_entry.pack(fill="x", pady=(0, 15))
        
        btn_add = ttk.Button(left, text="➕ ADD TASK", command=self.add_task_gui)
        btn_add.pack(fill="x")
        
        # --- Right Pane: Task List ---
        lbl_list = tk.Label(right, text="Task List", font=("Segoe UI", 12, "bold"), bg="#0b0f19", fg="#00f2fe")
        lbl_list.pack(anchor="w", pady=(0, 10))
        
        # Treeview Scrollbar
        scroll = ttk.Scrollbar(right)
        scroll.pack(side="right", fill="y")
        
        self.task_tree = ttk.Treeview(right, columns=("ID", "Title", "Priority", "Due", "Status"), show="headings", yscrollcommand=scroll.set)
        scroll.config(command=self.task_tree.yview)
        
        self.task_tree.heading("ID", text="ID")
        self.task_tree.heading("Title", text="Title")
        self.task_tree.heading("Priority", text="Priority")
        self.task_tree.heading("Due", text="Due Date")
        self.task_tree.heading("Status", text="Status")
        
        self.task_tree.column("ID", width=40, anchor="center")
        self.task_tree.column("Title", width=150, anchor="w")
        self.task_tree.column("Priority", width=70, anchor="center")
        self.task_tree.column("Due", width=90, anchor="center")
        self.task_tree.column("Status", width=80, anchor="center")
        
        self.task_tree.pack(fill="both", expand=True, pady=(0, 10))
        
        # Action Buttons
        btn_frame = tk.Frame(right, bg="#0b0f19")
        btn_frame.pack(fill="x")
        
        btn_complete = ttk.Button(btn_frame, text="✅ COMPLETE", command=self.complete_task_gui)
        btn_complete.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        btn_delete = ttk.Button(btn_frame, text="❌ DELETE", command=self.delete_task_gui)
        btn_delete.pack(side="left", fill="x", expand=True, padx=5)
        
        btn_refresh = ttk.Button(btn_frame, text="🔄 REFRESH", command=self.refresh_tasks)
        btn_refresh.pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        # Load tasks
        self.refresh_tasks()

    def refresh_tasks(self):
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)
            
        tasks = self.task_agent.get_tasks()
        for t in tasks:
            due = t.get("due_date") or "-"
            self.task_tree.insert("", "end", values=(t["id"], t["title"], t["priority"], due, t["status"]))

    def add_task_gui(self):
        title = self.task_title_entry.get().strip()
        desc = self.task_desc_entry.get().strip() or None
        priority = self.task_priority.get()
        due = self.task_due_entry.get().strip() or None
        
        if not title:
            messagebox.showerror("Error", "Task Title is required.")
            return
            
        self.task_agent.add_task(title, desc, priority, due)
        self.refresh_tasks()
        
        # Clear fields
        self.task_title_entry.delete(0, tk.END)
        self.task_desc_entry.delete(0, tk.END)
        self.task_due_entry.delete(0, tk.END)
        self.task_priority.set("Medium")

    def complete_task_gui(self):
        selected = self.task_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a task to complete.")
            return
            
        for sel in selected:
            item_vals = self.task_tree.item(sel, "values")
            task_id = item_vals[0]
            self.task_agent.complete_task(task_id)
            
        self.refresh_tasks()

    def delete_task_gui(self):
        selected = self.task_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a task to delete.")
            return
            
        if not messagebox.askyesno("Confirm Delete", "Are you sure you want to delete the selected task(s)?"):
            return
            
        for sel in selected:
            item_vals = self.task_tree.item(sel, "values")
            task_id = item_vals[0]
            self.task_agent.delete_task(task_id)
            
        self.refresh_tasks()

def launch():
    root = tk.Tk()
    app = JarvisLocalApp(root)
    root.mainloop()

if __name__ == "__main__":
    launch()
