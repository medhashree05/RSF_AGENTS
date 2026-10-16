from typing import Any, Dict
from src.agent.models import Action, Observation
from src.agent.runtime import Runtime


def execute_shell(
    action: Action,
    runtime: Runtime,
    max_chars: int = 10000,
) -> Observation:
    """
    Execute a shell command inside the isolated runtime environment.
    
    NEVER runs commands on the host machine. Output is bounded and exit code is captured.
    """
    args = action.args
    command = args.get("command")
    if not command or not isinstance(command, str) or not command.strip():
        return Observation(
            success=False,
            output="",
            error="run_shell requires a non-empty string 'command' argument."
        )

    # Delegate execution to isolated runtime
    obs = runtime.execute(action)

    output = obs.output
    truncated = False
    if len(output) > max_chars:
        output = output[:max_chars]
        truncated = True

    if truncated:
        output += f"\n... [Command output truncated: exceeded {max_chars} character limit] ..."

    metadata = dict(obs.metadata)
    metadata["truncated"] = truncated

    return Observation(
        success=obs.success,
        output=output,
        error=obs.error,
        metadata=metadata
    )
