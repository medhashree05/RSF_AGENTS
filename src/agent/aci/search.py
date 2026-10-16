from typing import Any, Dict
import os

from src.agent.models import Action, Observation
from src.agent.runtime import Runtime


def execute_search(
    action: Action,
    runtime: Runtime,
    max_matches: int = 50,
    max_chars: int = 8000,
) -> Observation:
    """
    Search repository files for text matching the query string.
    
    Args:
        action: Action containing 'query' and optional 'path' in args.
        runtime: Isolated runtime interface.
        max_matches: Maximum number of matched lines to include.
        max_chars: Maximum character limit for observation output.
        
    Returns:
        Observation with file paths and line numbers matching the query.
    """
    args = action.args
    query = args.get("query")
    if not query or not isinstance(query, str) or not query.strip():
        return Observation(
            success=False,
            output="",
            error="Search requires a non-empty string 'query' argument."
        )

    search_path = args.get("path", "")
    if search_path and isinstance(search_path, str):
        if ".." in search_path or os.path.isabs(search_path) and not search_path.startswith("/workspace"):
            return Observation(
                success=False,
                output="",
                error=f"Security violation: path traversal or search outside workspace is rejected: '{search_path}'"
            )

    # Delegate search execution to runtime
    obs = runtime.execute(action)
    if not obs.success:
        return obs

    output = obs.output
    lines = output.splitlines()

    truncated = False
    total_lines = len(lines)
    if total_lines > max_matches:
        lines = lines[:max_matches]
        truncated = True

    result_text = "\n".join(lines)
    if len(result_text) > max_chars:
        result_text = result_text[:max_chars]
        truncated = True

    if truncated:
        result_text += f"\n... [Search results truncated: showing first {len(lines)} of {total_lines} matches] ..."

    return Observation(
        success=True,
        output=result_text,
        metadata={"total_matches": total_lines, "truncated": truncated}
    )
