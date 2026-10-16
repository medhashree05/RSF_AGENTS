import os
import re
from typing import List, Optional
from src.models import ToolCall, PolicyDecision
from src.tools.base import validate_tool_call


DANGEROUS_COMMAND_PATTERNS = [
    r"\bsudo\b",
    r"\brm\s+-rf\s+/(?!\w)",  # rm -rf / or rm -rf /*
    r"\bmkfs\b",
    r"\bdd\b.*of=/dev/",
    r"\bchmod\s+777\s+/",
    r"\bchown\b.*root",
    r">\s*/etc/",
    r">\s*/usr/",
    r">\s*/var/",
]


class PolicyLimiter:
    """
    Deterministic policy engine that validates tool calls and declared scopes
    before sandbox execution.
    """
    def __init__(
        self,
        allowed_workspace: str = "/workspace",
        allow_network: bool = False,
        forbidden_patterns: Optional[List[str]] = None
    ):
        self.allowed_workspace = os.path.abspath(allowed_workspace)
        self.allow_network = allow_network
        self.forbidden_patterns = forbidden_patterns or DANGEROUS_COMMAND_PATTERNS

    def is_path_in_workspace(self, path: str) -> bool:
        """Check if a path is inside or equal to the allowed workspace."""
        # Normalize relative path assuming relative to workspace root
        if not path.startswith("/"):
            normalized = os.path.abspath(os.path.join(self.allowed_workspace, path))
        else:
            normalized = os.path.abspath(path)
        
        # Check prefix match
        return normalized == self.allowed_workspace or normalized.startswith(self.allowed_workspace + "/")

    def evaluate(self, tool_call: ToolCall) -> PolicyDecision:
        """Evaluate a ToolCall against system security policy."""
        # 1. Structural schema validation
        valid, msg = validate_tool_call(tool_call)
        if not valid:
            return PolicyDecision(allowed=False, reason=f"Tool call schema error: {msg}")

        scope = tool_call.declared_scope

        # 2. Network policy check
        if scope.network and not self.allow_network:
            return PolicyDecision(
                allowed=False,
                reason="Network access requested in declared_scope but network is disabled by policy"
            )

        # 3. Declared write paths check
        for wpath in scope.write:
            if not self.is_path_in_workspace(wpath):
                return PolicyDecision(
                    allowed=False,
                    reason=f"Declared write path '{wpath}' is outside allowed workspace '{self.allowed_workspace}'"
                )

        # 4. Declared read paths check
        for rpath in scope.read:
            if not self.is_path_in_workspace(rpath):
                return PolicyDecision(
                    allowed=False,
                    reason=f"Declared read path '{rpath}' is outside allowed workspace '{self.allowed_workspace}'"
                )

        # 5. Tool-specific argument policy checks
        if tool_call.tool == "write_file":
            target_path = tool_call.arguments["path"]
            if not self.is_path_in_workspace(target_path):
                return PolicyDecision(
                    allowed=False,
                    reason=f"Target file path '{target_path}' is outside allowed workspace '{self.allowed_workspace}'"
                )

        elif tool_call.tool == "run_shell":
            command = tool_call.arguments["command"]
            for pattern in self.forbidden_patterns:
                if re.search(pattern, command):
                    return PolicyDecision(
                        allowed=False,
                        reason=f"Shell command contains forbidden dangerous pattern matching '{pattern}'"
                    )

        return PolicyDecision(
            allowed=True,
            reason="Tool call and declared scope satisfy policy",
            requires_approval=False
        )
