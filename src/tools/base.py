from typing import Any, Dict, List, Tuple
from src.models import ToolCall


ALLOWED_TOOLS = {"run_shell", "write_file"}


def validate_tool_call(tool_call: ToolCall) -> Tuple[bool, str]:
    """Validate that a ToolCall conforms to defined tool schemas."""
    if tool_call.tool not in ALLOWED_TOOLS:
        return False, f"Unknown tool '{tool_call.tool}'. Supported tools: {sorted(ALLOWED_TOOLS)}"
    
    if tool_call.tool == "run_shell":
        if "command" not in tool_call.arguments or not isinstance(tool_call.arguments["command"], str):
            return False, "run_shell requires a string 'command' argument"
        if not tool_call.arguments["command"].strip():
            return False, "run_shell command cannot be empty"

    elif tool_call.tool == "write_file":
        if "path" not in tool_call.arguments or not isinstance(tool_call.arguments["path"], str):
            return False, "write_file requires a string 'path' argument"
        if "content" not in tool_call.arguments or not isinstance(tool_call.arguments["content"], str):
            return False, "write_file requires a string 'content' argument"
        if not tool_call.arguments["path"].strip():
            return False, "write_file path cannot be empty"

    return True, "Tool call valid"


def run_shell_command(command: str) -> str:
    """Generate shell command execution payload."""
    return command


def write_file_command(path: str, content: str) -> str:
    """Generate shell command to write content safely to target file path."""
    # Escapes or writes content using python inside container or bash heredoc
    import base64
    b64_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    # Creates parent directory if missing and writes decoded content
    return f"mkdir -p $(dirname '{path}') && echo '{b64_content}' | base64 -d > '{path}'"
