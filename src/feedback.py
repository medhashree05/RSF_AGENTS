from typing import Optional
from src.models import ComparisonResult, PolicyDecision


def generate_feedback(policy: PolicyDecision, comparison: Optional[ComparisonResult] = None) -> str:

    """Generate structured feedback string for the agent upon policy rejection or rollback."""
    if not policy.allowed:
        return (
            f"Policy Rejection: Tool execution blocked before execution.\n"
            f"Reason: {policy.reason}\n"
            f"No changes were made to workspace."
        )

    if comparison and not comparison.match:
        unexpected_str = "\n".join(f"  - {e}" for e in comparison.unexpected_effects)
        return (
            f"Execution violated declared scope.\n"
            f"Unexpected effect(s):\n{unexpected_str}\n"
            f"The transaction was rolled back. Workspace reverted to committed state."
        )


    return "Execution successful. Declared scope matched observed effects. Transaction committed."
