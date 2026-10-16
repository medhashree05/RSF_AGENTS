from typing import Any, Dict
import os

from src.agent.models import Action, Observation
from src.agent.runtime import Runtime


def execute_edit(action: Action, runtime: Runtime) -> Observation:
    """
    Apply modifications to a file in the repository environment.
    
    Supports three editing modes:
    1. Full write/create: args={"path": str, "content": str}
    2. Exact text replacement: args={"path": str, "old_str": str, "new_str": str}
    3. Line range replacement: args={"path": str, "start_line": int, "end_line": int, "replacement_text": str}
    
    Validates path boundaries and rejects path traversal.
    Ensures that modifications are strictly validated and failures are reported explicitly.
    """
    args = action.args
    path = args.get("path")
    if not path or not isinstance(path, str) or not path.strip():
        return Observation(
            success=False,
            output="",
            error="edit_file requires a non-empty string 'path' argument."
        )

    # Path traversal validation
    if ".." in path or (os.path.isabs(path) and not path.startswith("/workspace")):
        return Observation(
            success=False,
            output="",
            error=f"Security violation: path traversal or file outside workspace rejected: '{path}'"
        )

    # Validate presence of at least one valid edit mode
    has_content = "content" in args and isinstance(args["content"], str)
    has_str_replace = "old_str" in args and "new_str" in args
    has_line_replace = "start_line" in args and "end_line" in args and "replacement_text" in args

    if not (has_content or has_str_replace or has_line_replace):
        return Observation(
            success=False,
            output="",
            error=(
                "edit_file requires one of the following argument combinations:\n"
                "  - 'content': full file write/create\n"
                "  - 'old_str' and 'new_str': exact unique substring replacement\n"
                "  - 'start_line', 'end_line', and 'replacement_text': line range replacement"
            )
        )

    if has_str_replace:
        if not isinstance(args["old_str"], str) or not isinstance(args["new_str"], str):
            return Observation(
                success=False,
                output="",
                error="old_str and new_str must both be strings."
            )
        if not args["old_str"]:
            return Observation(
                success=False,
                output="",
                error="old_str cannot be empty string in substring replacement."
            )

    if has_line_replace:
        s = args["start_line"]
        e = args["end_line"]
        if not isinstance(s, int) or s < 1:
            return Observation(success=False, output="", error=f"Invalid start_line '{s}'. Must be integer >= 1.")
        if not isinstance(e, int) or e < s:
            return Observation(success=False, output="", error=f"Invalid end_line '{e}'. Must be integer >= start_line ({s}).")
        if not isinstance(args["replacement_text"], str):
            return Observation(success=False, output="", error="replacement_text must be a string.")

    # Delegate to runtime
    obs = runtime.execute(action)
    return obs
