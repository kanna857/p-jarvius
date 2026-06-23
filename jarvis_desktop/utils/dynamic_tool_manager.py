import os
import sys
import importlib.util
from pathlib import Path
from utils.logger import JarvisLogger

class DynamicToolManager:
    def __init__(self, workspace_dir=None):
        self.logger = JarvisLogger("DynTools")
        if workspace_dir is None:
            self.workspace_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        else:
            self.workspace_dir = Path(workspace_dir)
            
        self.tools_dir = self.workspace_dir / "dynamic_tools"
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure dynamic_tools dir is in sys.path
        if str(self.tools_dir) not in sys.path:
            sys.path.insert(0, str(self.tools_dir))
            
        self.loaded_tools = {} # name -> { "schema": dict, "execute": function, "module": module }
        self.load_all_tools()

    def load_all_tools(self):
        """Scan tools_dir and load all valid python tool files."""
        self.loaded_tools.clear()
        if not self.tools_dir.exists():
            return
            
        for file in self.tools_dir.glob("*.py"):
            if file.name.startswith("__"):
                continue
            try:
                tool_name = file.stem
                spec = importlib.util.spec_from_file_location(tool_name, file)
                module = importlib.util.module_from_spec(spec)
                sys.modules[tool_name] = module
                spec.loader.exec_module(module)
                
                # Check for required schema and execute function
                if hasattr(module, "SCHEMA") and hasattr(module, "execute"):
                    self.loaded_tools[module.SCHEMA["function"]["name"]] = {
                        "schema": module.SCHEMA,
                        "execute": module.execute,
                        "module": module
                    }
                    self.logger.success(f"Loaded dynamic tool: {tool_name}")
                else:
                    self.logger.warning(f"File {file.name} is missing SCHEMA or execute() function.")
            except Exception as e:
                self.logger.error(f"Failed to load dynamic tool {file.name}: {e}")

    def get_tool_schemas(self) -> list:
        """Returns the list of schemas for all loaded tools."""
        return [t["schema"] for t in self.loaded_tools.values()]

    def has_tool(self, name: str) -> bool:
        return name in self.loaded_tools

    def execute_tool(self, name: str, args: dict) -> str:
        """Executes a dynamic tool by name and returns result string."""
        if not self.has_tool(name):
            return f"Error: dynamic tool '{name}' not found."
        try:
            res = self.loaded_tools[name]["execute"](args)
            return str(res)
        except Exception as e:
            return f"Error executing dynamic tool {name}: {e}"

# Global instance
dynamic_tool_manager = DynamicToolManager()
