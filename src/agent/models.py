from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import os

from src.models import DeclaredScope, ToolCall


class Action(BaseModel):
    """
    Structured action emitted by the agent to interact with the environment via ACI.
    
    Includes an explicit declared_scope for integration with the safety control loop
    (Policy Limiter, Ground-Truth Auditor, and Scope Comparator).
    """
    action_type: str = Field(..., description="ACI action type: search, read_file, edit_file, run_shell, submit")
    args: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the specific ACI command")
    declared_scope: DeclaredScope = Field(
        default_factory=DeclaredScope,
        description="Declared intent for paths to read/write and network access"
    )

    def to_tool_call(self) -> ToolCall:
        """
        Convert this action into a ToolCall compatible with the safety control loop
        (Orchestrator, PolicyLimiter, and TransactionalSandbox).
        """
        # Map ACI action to runtime tool name if needed
        tool_mapping = {
            "run_shell": "run_shell",
            "edit_file": "write_file",
        }
        tool_name = tool_mapping.get(self.action_type, self.action_type)
        return ToolCall(
            tool=tool_name,
            arguments=self.args,
            declared_scope=self.declared_scope
        )


class Observation(BaseModel):
    """
    Structured result returned from executing an ACI action in the runtime environment.
    """
    success: bool = Field(..., description="Whether the action succeeded")
    output: str = Field(default="", description="Output text (stdout, file content, search results)")
    error: Optional[str] = Field(default=None, description="Error message if execution failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional execution metadata")

    def to_display_text(self, max_chars: Optional[int] = None) -> str:
        """Format the observation as a string for inclusion in LLM history."""
        status_label = "SUCCESS" if self.success else "FAILURE"
        body = self.output
        if self.error:
            if body:
                body = f"{body}\n[Error details: {self.error}]"
            else:
                body = f"Error: {self.error}"

        if max_chars is not None and len(body) > max_chars:
            omitted = len(body) - max_chars
            body = body[:max_chars] + f"\n... [Output truncated: {omitted} characters omitted] ..."

        return f"[OBSERVATION: {status_label}]\n{body}"


class Task(BaseModel):
    """Specification of the software engineering coding task."""
    task_id: str = Field(..., description="Unique task identifier")
    instruction: str = Field(..., description="Detailed instructions or issue description")
    context: Optional[str] = Field(default=None, description="Optional background context or repository notes")


class AgentResult(BaseModel):
    """Final outcome returned by CodingAgent.run(task)."""
    task_id: str
    submitted: bool = Field(..., description="True only if the agent explicitly called the submit action")
    status: str = Field(..., description="Final status: SUBMITTED, MAX_STEPS_EXCEEDED, MAX_MALFORMED_EXCEEDED, ERROR")
    steps_taken: int
    submission: Optional[str] = Field(default=None, description="Summary or payload provided with submit action")
    error: Optional[str] = Field(default=None, description="Error details if terminated due to failure")
    trajectory_path: Optional[str] = Field(default=None, description="Path to structured JSONL trajectory log")
    total_tokens: Optional[int] = Field(default=None, description="Accumulated token count across steps")
    total_cost_usd: Optional[float] = Field(default=None, description="Estimated LLM API cost in USD if available")
