import pytest
from src.models import ToolCall, DeclaredScope
from src.policy import PolicyLimiter


def test_policy_allow_workspace_write():
    policy = PolicyLimiter(allowed_workspace="/workspace")
    tc = ToolCall(
        tool="write_file",
        arguments={"path": "/workspace/report.txt", "content": "hello"},
        declared_scope=DeclaredScope(write=["/workspace/report.txt"])
    )
    decision = policy.evaluate(tc)
    assert decision.allowed is True
    assert "satisfy policy" in decision.reason


def test_policy_reject_outside_workspace():
    policy = PolicyLimiter(allowed_workspace="/workspace")
    tc = ToolCall(
        tool="write_file",
        arguments={"path": "/etc/passwd", "content": "bad"},
        declared_scope=DeclaredScope(write=["/etc/passwd"])
    )
    decision = policy.evaluate(tc)
    assert decision.allowed is False
    assert "outside allowed workspace" in decision.reason


def test_policy_reject_network_when_disabled():
    policy = PolicyLimiter(allowed_workspace="/workspace", allow_network=False)
    tc = ToolCall(
        tool="run_shell",
        arguments={"command": "curl https://example.com"},
        declared_scope=DeclaredScope(write=[], network=True)
    )
    decision = policy.evaluate(tc)
    assert decision.allowed is False
    assert "Network access requested" in decision.reason


def test_policy_reject_forbidden_command_pattern():
    policy = PolicyLimiter(allowed_workspace="/workspace")
    tc = ToolCall(
        tool="run_shell",
        arguments={"command": "sudo rm -rf /workspace/test"},
        declared_scope=DeclaredScope(write=["/workspace/test"])
    )
    decision = policy.evaluate(tc)
    assert decision.allowed is False
    assert "forbidden dangerous pattern" in decision.reason
