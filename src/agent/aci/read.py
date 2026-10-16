from typing import Any, Dict
import os

from src.agent.models import Action, Observation
from src.agent.runtime import Runtime


def execute_read(
    action: Action,
    runtime: Runtime,
    max_lines: int = 250,
    max_chars: int = 10000,
) -> Observation:
    """
    Read text content from a repository file with 1-indexed line numbers.
    
    Supports optional 'start_line' and 'end_line' slice arguments.
    Enforces repository boundaries and output limits.
    """
    args = action.args
    path = args.get("path")
    if not path or not isinstance(path, str) or not path.strip():
        return Observation(
            success=False,
            output="",
            error="read_file requires a non-empty string 'path' argument."
        )

    # Path traversal check
    if ".." in path or (os.path.isabs(path) and not path.startswith("/workspace")):
        return Observation(
            success=False,
            output="",
            error=f"Security violation: path traversal or file outside workspace rejected: '{path}'"
        )

    start_line = args.get("start_line", 1)
    end_line = args.get("end_line")

    if not isinstance(start_line, int) or start_line < 1:
        return Observation(
            success=False,
            output="",
            error=f"Invalid start_line '{start_line}'. Must be a positive integer >= 1."
        )

    if end_line is not None:
        if not isinstance(end_line, int) or end_line < start_line:
            return Observation(
                success=False,
                output="",
                error=f"Invalid end_line '{end_line}'. Must be an integer >= start_line ({start_line})."
            )

    # Delegate to runtime
    obs = runtime.execute(action)
    if not obs.success:
        return obs

    lines = obs.output.splitlines()
    total_lines = len(lines)
    truncated = False

    if total_lines > max_lines:
        lines = lines[:max_lines]
        truncated = True

    result_text = "\n".join(lines)
    if len(result_text) > max_chars:
        result_text = result_text[:max_chars]
        truncated = True

    if truncated:
        result_text += f"\n... [File content truncated: showing first {len(lines)} lines] ..."

    return Observation(
        success=True,
        output=result_text,
        metadata={"total_lines": total_lines, "truncated": truncated}
    )
