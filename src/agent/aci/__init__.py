from typing import Dict, Any, Callable
from src.agent.models import Action, Observation
from src.agent.runtime import Runtime
from src.agent.aci.search import execute_search
from src.agent.aci.read import execute_read
from src.agent.aci.edit import execute_edit
from src.agent.aci.shell import execute_shell
from src.agent.aci.submit import execute_submit

SUPPORTED_ACTIONS = {"search", "read_file", "edit_file", "run_shell", "submit"}


class ACIDispatcher:
    """
    Central dispatcher routing agent Actions to specific ACI tool handlers.
    """
    def __init__(self, max_chars: int = 10000):
        self.max_chars = max_chars

    def dispatch(self, action: Action, runtime: Runtime) -> Observation:
        """
        Validate and execute an action through the ACI interface using the provided runtime.
        """
        atype = action.action_type
        if atype not in SUPPORTED_ACTIONS:
            return Observation(
                success=False,
                output="",
                error=f"Unknown action '{atype}'. Supported ACI actions: {sorted(list(SUPPORTED_ACTIONS))}"
            )

        if atype == "search":
            return execute_search(action, runtime, max_chars=self.max_chars)
        elif atype == "read_file":
            return execute_read(action, runtime, max_chars=self.max_chars)
        elif atype == "edit_file":
            return execute_edit(action, runtime)
        elif atype == "run_shell":
            return execute_shell(action, runtime, max_chars=self.max_chars)
        elif atype == "submit":
            return execute_submit(action, runtime)
        else:
            return Observation(success=False, output="", error=f"Unhandled action type: {atype}")


__all__ = [
    "ACIDispatcher",
    "SUPPORTED_ACTIONS",
    "execute_search",
    "execute_read",
    "execute_edit",
    "execute_shell",
    "execute_submit",
]
