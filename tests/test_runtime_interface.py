import os
import pytest
from src.agent.agent import CodingAgent
from src.agent.config import AgentConfig
from src.agent.models import Task
from src.agent.llm import MockLLMProvider, LLMError
from src.agent.runtime import FakeRuntime, MockRuntime
from src.models import ExecutionResult


def test_runtime_start_and_cleanup_on_success(tmp_path):
    """Verify runtime.start() and runtime.stop() are called cleanly on successful run."""
    responses = [
        '{"action": "submit", "args": {"summary": "Done"}}'
    ]
    llm = MockLLMProvider(responses=responses)
    runtime = MockRuntime(initial_files={"hello.py": "print('hello')"})
    config = AgentConfig(max_steps=5, trajectory_dir=str(tmp_path / "trajectories"))
    agent = CodingAgent(llm=llm, runtime=runtime, config=config)

    assert runtime.is_started is False
    assert runtime.is_stopped is False

    task = Task(task_id="task_lifecycle", instruction="Say hello", repository="test/repo")
    result = agent.run(task)

    assert result.submitted is True
    assert result.runtime_cleaned_up is True
    assert runtime.is_stopped is True
    assert runtime.repository == "test/repo"


def test_runtime_cleanup_on_failure_or_exception(tmp_path):
    """Verify runtime.stop() is guaranteed to execute even if LLM crashes or step limit is exceeded."""
    llm = MockLLMProvider(responses=[LLMError("Fatal API Error")])
    runtime = MockRuntime(initial_files={"app.py": "x = 1\n"})
    config = AgentConfig(max_steps=5, trajectory_dir=str(tmp_path / "trajectories"))
    agent = CodingAgent(llm=llm, runtime=runtime, config=config)

    result = agent.run("Crash test")

    assert result.status == "ERROR"
    assert result.runtime_cleaned_up is True
    # Crucial: stop() must have been called via try/finally
    assert runtime.is_stopped is True


def test_runtime_get_changes_unified_diff():
    """Verify in-memory diff computation produces standard unified git diff format."""
    runtime = FakeRuntime(initial_files={
        "src/calc.py": "def add(a, b):\n    return a - b\n"
    })
    runtime.start()

    # Modify file
    runtime.write_file("src/calc.py", "def add(a, b):\n    return a + b\n")

    diff = runtime.get_changes()
    assert "--- a/src/calc.py" in diff
    assert "+++ b/src/calc.py" in diff
    assert "-    return a - b" in diff
    assert "+    return a + b" in diff


def test_runtime_run_tests_execution():
    """Verify run_tests invokes test runner and returns structured ExecutionResult."""
    runtime = FakeRuntime(
        mock_commands={
            "pytest tests/test_math.py": ExecutionResult(
                stdout="3 passed in 0.05s",
                stderr="",
                exit_code=0,
                duration_ms=50.0
            )
        }
    )
    task = Task(task_id="t1", instruction="Run tests", test_command="pytest tests/test_math.py")
    runtime.start(task=task)

    res = runtime.run_tests()
    assert res.exit_code == 0
    assert "3 passed" in res.stdout
    assert res.duration_ms == 50.0


def test_runtime_read_file_line_ranges():
    """Verify read_file supports slice boundaries with 1-indexed numbering."""
    runtime = FakeRuntime(initial_files={
        "data.txt": "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
    })
    # Read full file
    assert runtime.read_file("data.txt") == "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"

    # Read slice range lines 2-4
    sliced = runtime.read_file("data.txt", start_line=2, end_line=4)
    assert "2: Line 2" in sliced
    assert "3: Line 3" in sliced
    assert "4: Line 4" in sliced
    assert "Line 1" not in sliced
    assert "Line 5" not in sliced


def test_runtime_invalid_path_and_path_traversal():
    """Verify runtime rejects path traversal outside workspace directory."""
    runtime = FakeRuntime(initial_files={"test.py": "# test"})

    with pytest.raises(PermissionError, match="Path traversal"):
        runtime.read_file("../../etc/shadow")

    with pytest.raises(FileNotFoundError, match="File not found"):
        runtime.read_file("nonexistent.py")


def test_runtime_nonzero_command_exit_code():
    """Verify nonzero shell exit codes return clean failure observations without crashing."""
    runtime = FakeRuntime(
        mock_commands={
            "pytest tests/": ExecutionResult(stdout="Failing test", stderr="AssertionError", exit_code=1)
        }
    )
    action = {"action": "run_shell", "args": {"command": "pytest tests/"}}
    from src.agent.models import Action
    obs = runtime.execute(Action(action_type="run_shell", args={"command": "pytest tests/"}))

    assert obs.success is False
    assert "Failing test" in obs.output
    assert "non-zero status code: 1" in obs.error
    assert obs.metadata.get("exit_code") == 1
