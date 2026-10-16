import pytest
from src.agent.models import Action
from src.agent.runtime import FakeRuntime
from src.agent.aci import ACIDispatcher
from src.models import DeclaredScope, ExecutionResult


@pytest.fixture
def fake_runtime():
    return FakeRuntime(
        initial_files={
            "src/main.py": "def hello():\n    return 'world'\n\ndef goodbye():\n    return 'bye'\n",
            "tests/test_main.py": "def test_hello():\n    assert hello() == 'world'\n",
            "README.md": "# Sample Project\nDocumentation content here.\n",
        },
        mock_commands={
            "pytest": ExecutionResult(stdout="2 passed in 0.05s", stderr="", exit_code=0),
            "flake8": ExecutionResult(stdout="src/main.py:1:1: E302", stderr="", exit_code=1),
        }
    )


@pytest.fixture
def dispatcher():
    return ACIDispatcher(max_chars=500)


# --- 1. Search Tool Tests ---

def test_search_valid(fake_runtime, dispatcher):
    action = Action(
        action_type="search",
        args={"query": "goodbye"},
        declared_scope=DeclaredScope(read=["src/main.py"])
    )
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is True
    assert "src/main.py:4: def goodbye():" in obs.output


def test_search_empty_query(fake_runtime, dispatcher):
    action = Action(action_type="search", args={"query": ""})
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is False
    assert "Search requires a non-empty string 'query'" in obs.error


def test_search_no_matches(fake_runtime, dispatcher):
    action = Action(action_type="search", args={"query": "non_existent_symbol"})
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is True
    assert "No matches found" in obs.output


def test_search_path_traversal_rejection(fake_runtime, dispatcher):
    action = Action(action_type="search", args={"query": "root", "path": "../../etc"})
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is False
    assert "Security violation: path traversal" in obs.error


# --- 2. Read Tool Tests ---

def test_read_file_valid_full(fake_runtime, dispatcher):
    action = Action(action_type="read_file", args={"path": "src/main.py"})
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is True
    assert "1: def hello():" in obs.output
    assert "4: def goodbye():" in obs.output


def test_read_file_line_range(fake_runtime, dispatcher):
    action = Action(action_type="read_file", args={"path": "src/main.py", "start_line": 2, "end_line": 3})
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is True
    assert "2:     return 'world'" in obs.output
    assert "3: " in obs.output
    assert "4: def goodbye():" not in obs.output


def test_read_file_missing(fake_runtime, dispatcher):
    action = Action(action_type="read_file", args={"path": "non_existent.py"})
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is False
    assert "File not found" in obs.error


def test_read_file_path_traversal_rejection(fake_runtime, dispatcher):
    action = Action(action_type="read_file", args={"path": "../../../etc/shadow"})
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is False
    assert "Security violation: path traversal" in obs.error


def test_read_file_invalid_range(fake_runtime, dispatcher):
    action = Action(action_type="read_file", args={"path": "src/main.py", "start_line": 10, "end_line": 5})
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is False
    assert "Invalid end_line" in obs.error


# --- 3. Edit Tool Tests ---

def test_edit_file_content_write(fake_runtime, dispatcher):
    action = Action(
        action_type="edit_file",
        args={"path": "src/new.py", "content": "x = 42\n"},
        declared_scope=DeclaredScope(write=["src/new.py"])
    )
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is True
    assert fake_runtime.read_file("src/new.py") == "x = 42\n"


def test_edit_file_str_replace_success(fake_runtime, dispatcher):
    action = Action(
        action_type="edit_file",
        args={
            "path": "src/main.py",
            "old_str": "return 'world'",
            "new_str": "return 'universe'"
        },
        declared_scope=DeclaredScope(write=["src/main.py"])
    )
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is True
    assert "return 'universe'" in fake_runtime.read_file("src/main.py")


def test_edit_file_str_replace_not_found(fake_runtime, dispatcher):
    action = Action(
        action_type="edit_file",
        args={
            "path": "src/main.py",
            "old_str": "missing_text_pattern",
            "new_str": "replacement"
        }
    )
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is False
    assert "Target old_str not found" in obs.error


def test_edit_file_path_traversal_rejection(fake_runtime, dispatcher):
    action = Action(
        action_type="edit_file",
        args={"path": "../../etc/passwd", "content": "hacked"}
    )
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is False
    assert "Security violation: path traversal" in obs.error


# --- 4. Shell Tool Tests ---

def test_shell_valid_execution(fake_runtime, dispatcher):
    action = Action(
        action_type="run_shell",
        args={"command": "pytest"},
        declared_scope=DeclaredScope(read=["tests/test_main.py"])
    )
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is True
    assert "2 passed in 0.05s" in obs.output
    assert obs.metadata.get("exit_code") == 0


def test_shell_failing_command(fake_runtime, dispatcher):
    action = Action(action_type="run_shell", args={"command": "flake8"})
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is False
    assert "E302" in obs.output
    assert obs.metadata.get("exit_code") == 1


def test_shell_empty_command(fake_runtime, dispatcher):
    action = Action(action_type="run_shell", args={"command": "   "})
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is False
    assert "run_shell requires a non-empty string 'command'" in obs.error


# --- 5. Submit Tool Tests ---

def test_submit_action(fake_runtime, dispatcher):
    action = Action(
        action_type="submit",
        args={"summary": "Fixed bug in hello function."}
    )
    obs = dispatcher.dispatch(action, fake_runtime)
    assert obs.success is True
    assert "Fixed bug in hello function" in obs.output
    assert obs.metadata.get("is_submission") is True
