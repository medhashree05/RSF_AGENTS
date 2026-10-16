import pytest
from src.agent.models import Action, Task, AgentResult
from src.agent.parser import parse_action, ActionParseError, extract_json_block
from src.models import DeclaredScope, ToolCall


def test_extract_json_block_fenced():
    raw = "Here is my reasoning.\n```json\n{\"action\": \"read_file\", \"args\": {\"path\": \"main.py\"}}\n```\nDone."
    extracted = extract_json_block(raw)
    assert extracted == '{"action": "read_file", "args": {"path": "main.py"}}'


def test_extract_json_block_xml():
    raw = "Reasoning... <action>{\"action\": \"submit\", \"args\": {}}</action>"
    extracted = extract_json_block(raw)
    assert extracted == '{"action": "submit", "args": {}}'


def test_extract_json_block_bare():
    raw = "Some preamble {\"action\": \"search\", \"args\": {\"query\": \"test\"}} extra text"
    extracted = extract_json_block(raw)
    assert extracted == '{"action": "search", "args": {"query": "test"}}'


def test_parse_valid_action_with_declared_scope():
    raw = """
    ```json
    {
        "action": "edit_file",
        "args": {
            "path": "src/utils.py",
            "content": "def add(a, b): return a + b"
        },
        "declared_scope": {
            "write": ["src/utils.py"],
            "read": ["src/config.py"],
            "network": false
        }
    }
    ```
    """
    action = parse_action(raw)
    assert action.action_type == "edit_file"
    assert action.args["path"] == "src/utils.py"
    assert action.declared_scope.write == ["src/utils.py"]
    assert action.declared_scope.read == ["src/config.py"]
    assert action.declared_scope.network is False


def test_parse_action_aliases():
    # 'read' -> 'read_file', 'shell' -> 'run_shell'
    a1 = parse_action('{"action": "read", "args": {"path": "a.txt"}}')
    assert a1.action_type == "read_file"

    a2 = parse_action('{"action": "shell", "args": {"command": "pytest"}}')
    assert a2.action_type == "run_shell"


def test_parse_action_missing_action():
    with pytest.raises(ActionParseError) as exc_info:
        parse_action('{"args": {"command": "ls"}}')
    assert "must contain a non-empty string field 'action'" in str(exc_info.value)


def test_parse_action_unsupported():
    with pytest.raises(ActionParseError) as exc_info:
        parse_action('{"action": "destroy_world", "args": {}}')
    assert "Unsupported action 'destroy_world'" in str(exc_info.value)


def test_parse_action_malformed_json():
    with pytest.raises(ActionParseError) as exc_info:
        parse_action('```json\n{"action": "read_file", "args": ...broken json\n```')
    assert "Failed to decode action JSON" in str(exc_info.value)


def test_parse_action_empty_input():
    with pytest.raises(ActionParseError) as exc_info:
        parse_action("")
    assert "Empty response received" in str(exc_info.value)


def test_declared_scope_preserved_without_conferring_authority():
    """
    Requirement 12: Declared scope is preserved as metadata describing agent intent,
    but is never used as self-authorizing proof of safety or actual execution effects.
    """
    action = parse_action("""
    {
        "action": "run_shell",
        "args": {"command": "rm -rf /"},
        "declared_scope": {
            "write": ["safe.txt"],
            "read": [],
            "network": false
        }
    }
    """)
    # Declared scope is stored faithfully
    assert action.declared_scope.write == ["safe.txt"]
    # But does not validate or sanitize the dangerous shell command itself
    tool_call = action.to_tool_call()
    assert isinstance(tool_call, ToolCall)
    assert tool_call.arguments["command"] == "rm -rf /"
    assert tool_call.declared_scope.write == ["safe.txt"]
