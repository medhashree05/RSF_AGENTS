from typing import Any, Dict
from src.agent.models import Action, Observation
from src.agent.runtime import Runtime


def execute_submit(action: Action, runtime: Runtime) -> Observation:
    """
    Handle the agent's explicit submission action.
    
    IMPORTANT: Submission signals termination of the agent's attempt.
    It DOES NOT evaluate correctness, verify task completion, or guarantee
    that workspace state is valid. Task resolution must be independently verified
    by the external benchmark or test harness.
    """
    args = action.args
    summary = args.get("summary", "Task submitted by agent.")
    return Observation(
        success=True,
        output=f"Agent has submitted its work: {summary}",
        error=None,
        metadata={"is_submission": True, "summary": summary}
    )
