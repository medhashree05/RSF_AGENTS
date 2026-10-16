import json
import os
import pytest
from src.agent.logger import TrajectoryLogger, redact_secrets, TrajectoryStepRecord


def test_redact_secrets_string():
    raw = "My OpenAI key is sk-1234567890abcdef1234567890 and Github ghp_123456789012345678901234567890123456"
    sanitized = redact_secrets(raw)
    assert "sk-" not in sanitized
    assert "ghp_" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized


def test_redact_secrets_bearer_and_env():
    raw_dict = {
        "auth": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token",
        "nested": {
            "api_key": "SECRET_KEY_XYZ999",
            "safe_field": "public_data"
        }
    }
    sanitized = redact_secrets(raw_dict)
    assert sanitized["auth"] == "[REDACTED_SECRET]"
    assert sanitized["nested"]["api_key"] == "[REDACTED_SECRET]"
    assert sanitized["nested"]["safe_field"] == "public_data"


def test_trajectory_logger_writes_jsonl(tmp_path):
    log_dir = str(tmp_path / "logs")
    logger = TrajectoryLogger(log_dir=log_dir, experiment_id="test_exp_1")

    task_id = "test_task_42"
    log_path = logger.log_step(
        task_id=task_id,
        step=1,
        model="gpt-4o",
        action_type="read_file",
        action_args={"path": "src/app.py", "token": "SECRET_TOKEN_ABC123"},
        declared_scope={"read": ["src/app.py"], "write": [], "network": False},
        observation_success=True,
        observation_output="Bearer sensitive_token_data in file output",
        observation_error=None,
        token_usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        cost_usd=0.002,
        is_terminal=False,
        termination_reason=None,
    )

    assert os.path.exists(log_path)
    records = logger.load_trajectory(task_id)
    assert len(records) == 1
    rec = records[0]

    assert rec["experiment_id"] == "test_exp_1"
    assert rec["task_id"] == task_id
    assert rec["step"] == 1
    assert rec["action_type"] == "read_file"
    assert rec["token_usage"]["total_tokens"] == 120
    assert rec["cost_usd"] == 0.002

    # Verify secrets were redacted in args and output
    assert rec["action_args"]["token"] == "[REDACTED_SECRET]"
    assert "sensitive_token_data" not in rec["observation_output"]
    assert "[REDACTED_SECRET]" in rec["observation_output"]
