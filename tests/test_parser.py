import pytest
from src.agent.parser import parse_action, ActionParseError, extract_json_block
from src.agent.models import Action


def test_parse_valid_actions_all_types():
    """Verify parsing valid actions for all 5 SWE-agent ACI operations."""
    # 1. read_file
    a1 = parse_action('{"action": "read_file", "args": {"path": "main.py", "start_line": 1, "end_line": 10}}')
    assert a1.action_type == "read_file"
    assert a1.args["path"] == "main.py"
    assert a1.args["start_line"] == 1

    # 2. edit_file
    a2 = parse_action('{"action": "edit_file", "args": {"path": "main.py", "old_str": "foo", "new_str": "bar"}}')
    assert a2.action_type == "edit_file"
    assert a2.args["old_str"] == "foo"

    # 3. search
    a3 = parse_action('{"action": "search", "args": {"query": "def calculate"}}')
    assert a3.action_type == "search"
    assert a3.args["query"] == "def calculate"

    # 4. run_shell
    a4 = parse_action('{"action": "run_shell", "args": {"command": "pytest tests/"}}')
    assert a4.action_type == "run_shell"
    assert a4.args["command"] == "pytest tests/"

    # 5. submit
    a5 = parse_action('{"action": "submit", "args": {"summary": "Fixed the bug."}}')
    assert a5.action_type == "submit"
    assert a5.args["summary"] == "Fixed the bug."


def test_parse_aliases_normalized():
    """Verify known tool aliases normalize to canonical ACI action names."""
    assert parse_action('{"action": "view_file", "args": {"path": "a.py"}}').action_type == "read_file"
    assert parse_action('{"action": "read", "args": {"path": "a.py"}}').action_type == "read_file"
    assert parse_action('{"action": "write_file", "args": {"path": "a.py", "content": "x"}}').action_type == "edit_file"
    assert parse_action('{"action": "edit", "args": {"path": "a.py", "content": "x"}}').action_type == "edit_file"
    assert parse_action('{"action": "shell", "args": {"command": "ls"}}').action_type == "run_shell"
    assert parse_action('{"action": "bash", "args": {"command": "ls"}}').action_type == "run_shell"


def test_parse_markdown_and_xml_blocks():
    """Verify extraction of JSON wrapped in markdown code fences or XML tags."""
    # Markdown json fence
    md_text = """Here is my plan. I will read the file now.
```json
{
    "action": "read_file",
    "args": {"path": "src/app.py"}
}
```
"""
    a_md = parse_action(md_text)
    assert a_md.action_type == "read_file"
    assert a_md.args["path"] == "src/app.py"

    # XML tags
    xml_text = """Let me run tests.
<action>
{
    "action": "run_shell",
    "args": {"command": "pytest"}
}
</action>
"""
    a_xml = parse_action(xml_text)
    assert a_xml.action_type == "run_shell"


def test_reject_malformed_and_empty_actions():
    """Verify ActionParseError is raised on invalid, empty, or unparseable input."""
    with pytest.raises(ActionParseError, match="Empty response"):
        parse_action("")

    with pytest.raises(ActionParseError, match="Failed to decode action JSON"):
        parse_action("I am not sending JSON at all.")

    with pytest.raises(ActionParseError, match="must be an object"):
        parse_action('["list", "instead", "of", "dict"]')

    with pytest.raises(ActionParseError, match="non-empty string field 'action'"):
        parse_action('{"foo": "bar"}')

    with pytest.raises(ActionParseError, match="Unsupported action"):
        parse_action('{"action": "fly_to_moon", "args": {}}')
