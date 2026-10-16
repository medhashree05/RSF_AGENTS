from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DeclaredScope(BaseModel):
    """Scope declared by the agent prior to tool execution."""
    write: List[str] = Field(default_factory=list, description="Files intended to be created or written")
    read: List[str] = Field(default_factory=list, description="Files intended to be read")
    network: bool = Field(default=False, description="Whether network access is requested")


class ToolCall(BaseModel):
    """Structured tool execution request issued by the agent."""
    tool: str = Field(..., description="Tool name, e.g. 'run_shell' or 'write_file'")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool call")
    declared_scope: DeclaredScope = Field(..., description="Declared scope of intended effects")


class PolicyDecision(BaseModel):
    """Outcome of the Policy / Scope Limiter evaluation."""
    allowed: bool = Field(..., description="Whether the tool call is permitted by policy")
    reason: str = Field(..., description="Explanation of policy decision")
    requires_approval: bool = Field(default=False, description="Whether explicit human approval is required")


class ExecutionResult(BaseModel):
    """Captured output from executing the tool inside the sandbox."""
    stdout: str = Field(default="", description="Captured standard output")
    stderr: str = Field(default="", description="Captured standard error")
    exit_code: int = Field(default=0, description="Process exit code")
    duration_ms: float = Field(default=0.0, description="Execution duration in milliseconds")


class ObservedEffects(BaseModel):
    """Ground-truth effects observed by Auditor during/after execution."""
    files_created: List[str] = Field(default_factory=list, description="Actual files created in workspace")
    files_modified: List[str] = Field(default_factory=list, description="Actual files modified in workspace")
    files_deleted: List[str] = Field(default_factory=list, description="Actual files deleted in workspace")
    files_read: List[str] = Field(default_factory=list, description="Actual files read during execution")
    processes: List[str] = Field(default_factory=list, description="Processes spawned")
    network: List[str] = Field(default_factory=list, description="Network connections/attempts observed")


class ComparisonResult(BaseModel):
    """Outcome of comparing DeclaredScope vs ObservedEffects."""
    match: bool = Field(..., description="True if observed effects are within declared scope")
    unexpected_effects: List[str] = Field(default_factory=list, description="Effects observed but not declared")
    missing_expected_effects: List[str] = Field(default_factory=list, description="Declared effects that did not occur")
    reason: str = Field(default="", description="Detailed reason for match or mismatch")


class EpisodeLog(BaseModel):
    """Structured log record for a complete tool execution episode."""
    scenario_id: str = Field(..., description="Identifier for test or execution run")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tool_call: ToolCall
    policy_decision: PolicyDecision
    execution_result: Optional[ExecutionResult] = None
    observed_effects: Optional[ObservedEffects] = None
    comparison_result: Optional[ComparisonResult] = None
    action_taken: str = Field(..., description="COMMITTED, ROLLED_BACK, or REJECTED")
    feedback: str = Field(default="", description="Feedback string returned to agent")
    latency_ms: float = Field(default=0.0, description="Total latency for episode in ms")
