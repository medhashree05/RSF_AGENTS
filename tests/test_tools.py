import pytest
from src.models import ToolCall, DeclaredScope
from src.tools.base import validate_tool_call, run_shell_command, write_file_command


def test_validate_unknown_tool():
    tc = ToolCall(
        tool="unknown_tool",
        arguments={},
        declared_scope=DeclaredScope()
    )
    valid, msg = validate_tool_call(tc)
    assert valid is False
    assert "Unknown tool" in msg


def test_validate_run_shell_valid():
    tc = ToolCall(
        tool="run_shell",
        arguments={"command": "ls -la"},
        declared_scope=DeclaredScope()
    )
    valid, msg = validate_tool_call(tc)
    assert valid is True


def test_validate_run_shell_missing_arg():
    tc = ToolCall(
        tool="run_shell",
        arguments={},
        declared_scope=DeclaredScope()
    )
    valid, msg = validate_tool_call(tc)
    assert valid is False
    assert "requires a string 'command'" in msg


def test_write_file_command_encoding():
    cmd = write_file_command("/workspace/a.txt", "line1\nline2")
    assert "/workspace/a.txt" in cmd
    assert "base64" in cmd
