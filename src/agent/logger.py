import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

SECRET_PATTERNS = [
    r"sk-[a-zA-Z0-9_\-]{20,}",
    r"Bearer\s+[a-zA-Z0-9_\-\.]+",
    r"ghp_[a-zA-Z0-9]{36}",
    r"SECRET_[a-zA-Z0-9_\-]+",
    r"(?:api[_-]?key|password|token|secret)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{12,})['\"]?",
]


def redact_secrets(data: Any) -> Any:
    """Recursively redact recognized API keys and tokens from strings or dict structures."""
    if isinstance(data, str):
        redacted = data
        for pattern in SECRET_PATTERNS:
            redacted = re.sub(pattern, "[REDACTED_SECRET]", redacted, flags=re.IGNORECASE)
        return redacted
    elif isinstance(data, dict):
        return {k: redact_secrets(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [redact_secrets(item) for item in data]
    return data


class TrajectoryStepRecord(BaseModel):
    """Structured record for an individual step in the agent's trajectory."""
    experiment_id: str
    task_id: str
    step: int
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model: str
    action_type: str
    action_args: Dict[str, Any]
    declared_scope: Dict[str, Any]
    observation_success: bool
    observation_output: str
    observation_error: Optional[str] = None
    token_usage: Optional[Dict[str, int]] = None
    cost_usd: Optional[float] = None
    is_terminal: bool = False
    termination_reason: Optional[str] = None


class TrajectoryLogger:
    """
    Structured JSONL trajectory logger for recording full agent execution episodes.
    Ensures secret redaction and reproducible reconstruction of agent actions and observations.
    """
    def __init__(self, log_dir: str = "logs/trajectories", experiment_id: str = "exp_default"):
        self.log_dir = log_dir
        self.experiment_id = experiment_id
        os.makedirs(self.log_dir, exist_ok=True)

    def get_trajectory_path(self, task_id: str) -> str:
        """Generate trajectory file path for a given task."""
        sanitized_task_id = re.sub(r"[^a-zA-Z0-9_-]", "_", task_id)
        return os.path.join(self.log_dir, f"trajectory_{sanitized_task_id}.jsonl")

    def log_step(
        self,
        task_id: str,
        step: int,
        model: str,
        action_type: str,
        action_args: Dict[str, Any],
        declared_scope: Dict[str, Any],
        observation_success: bool,
        observation_output: str,
        observation_error: Optional[str] = None,
        token_usage: Optional[Dict[str, int]] = None,
        cost_usd: Optional[float] = None,
        is_terminal: bool = False,
        termination_reason: Optional[str] = None,
    ) -> str:
        """
        Record a single trajectory step into the task-specific JSONL file.
        All arguments and outputs are sanitized through redact_secrets.
        """
        sanitized_args = redact_secrets(action_args)
        sanitized_output = redact_secrets(observation_output)
        sanitized_error = redact_secrets(observation_error) if observation_error else None

        record = TrajectoryStepRecord(
            experiment_id=self.experiment_id,
            task_id=task_id,
            step=step,
            model=model,
            action_type=action_type,
            action_args=sanitized_args,
            declared_scope=declared_scope,
            observation_success=observation_success,
            observation_output=sanitized_output,
            observation_error=sanitized_error,
            token_usage=token_usage,
            cost_usd=cost_usd,
            is_terminal=is_terminal,
            termination_reason=termination_reason,
        )

        file_path = self.get_trajectory_path(task_id)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.model_dump()) + "\n")

        return file_path

    def load_trajectory(self, task_id: str) -> List[Dict[str, Any]]:
        """Load and return all recorded steps for a task."""
        file_path = self.get_trajectory_path(task_id)
        if not os.path.exists(file_path):
            return []
        steps = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    steps.append(json.loads(line))
        return steps
