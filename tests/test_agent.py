import os
import pytest
from src.agent.agent import CodingAgent
from src.agent.config import AgentConfig
from src.agent.models import Task
from src.agent.llm import MockLLMProvider, LLMTimeoutError, TokenUsage, LLMResponse
from src.agent.runtime import FakeRuntime
from src.agent.logger import TrajectoryLogger
from src.models import ExecutionResult


@pytest.fixture
def test_trajectory_dir(tmp_path):
    log_dir = tmp_path / "trajectories"
    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir)


def test_agent_successful_submission_flow(test_trajectory_dir):
    """Test full multi-turn coding agent loop ending in explicit submission."""
    # Scenario: Agent reads file, edits file, runs test, submits
    responses = [
        # Turn 1: read file
        """```json
        {
            "action": "read_file",
            "args": {"path": "calculator.py"},
            "declared_scope": {"read": ["calculator.py"], "write": [], "network": false}
        }
        ```""",
        # Turn 2: edit file
        """```json
        {
            "action": "edit_file",
            "args": {"path": "calculator.py", "old_str": "return a - b", "new_str": "return a + b"},
            "declared_scope": {"read": [], "write": ["calculator.py"], "network": false}
        }
        ```""",
        # Turn 3: run shell test
        """```json
        {
            "action": "run_shell",
            "args": {"command": "pytest test_calc.py"},
            "declared_scope": {"read": ["test_calc.py"], "write": [], "network": false}
        }
        ```""",
        # Turn 4: submit
        """```json
        {
            "action": "submit",
            "args": {"summary": "Fixed add function to return a + b and passed tests."},
            "declared_scope": {"read": [], "write": [], "network": false}
        }
        ```"""
    ]

    llm = MockLLMProvider(responses=responses, model_name="mock-gpt4")
    runtime = FakeRuntime(
        initial_files={
            "calculator.py": "def add(a, b):\n    return a - b\n",
            "test_calc.py": "def test_add(): assert add(2, 3) == 5\n"
        },
        mock_commands={
            "pytest test_calc.py": ExecutionResult(stdout="1 passed in 0.01s", stderr="", exit_code=0)
        }
    )
    config = AgentConfig(max_steps=10, trajectory_dir=test_trajectory_dir)
    agent = CodingAgent(llm=llm, runtime=runtime, config=config)

    task = Task(task_id="task_calc_fix", instruction="Fix bug in calculator.py add function")
    result = agent.run(task)

    assert result.submitted is True
    assert result.status == "SUBMITTED"
    assert result.steps_taken == 4
    assert "Fixed add function" in (result.submission or "")
    assert runtime.read_file("calculator.py") == "def add(a, b):\n    return a + b\n"
    assert os.path.exists(result.trajectory_path)


def test_agent_max_steps_termination(test_trajectory_dir):
    """
    Requirement 5 & 13: Exceeding max steps must terminate with submitted=False
    and must not be reported as resolved/successful.
    """
    # Infinite read loop
    responses = [
        """```json
        {
            "action": "read_file",
            "args": {"path": "file.txt"},
            "declared_scope": {"read": ["file.txt"], "write": [], "network": false}
        }
        ```"""
    ] * 5

    llm = MockLLMProvider(responses=responses)
    runtime = FakeRuntime(initial_files={"file.txt": "some content"})
    config = AgentConfig(max_steps=3, trajectory_dir=test_trajectory_dir)
    agent = CodingAgent(llm=llm, runtime=runtime, config=config)

    task = Task(task_id="task_loop", instruction="Loop forever")
    result = agent.run(task)

    assert result.submitted is False
    assert result.status == "MAX_STEPS_EXCEEDED"
    assert result.steps_taken == 3
    assert result.submission is None
    assert "exceeded maximum step limit" in result.error


def test_agent_malformed_action_recovery(test_trajectory_dir):
    """Agent receives malformed action error feedback and successfully recovers."""
    responses = [
        # Turn 1: malformed JSON
        "Sorry, I forgot to output JSON: I want to read file.txt",
        # Turn 2: valid action after seeing error feedback
        """```json
        {
            "action": "submit",
            "args": {"summary": "Recovered from error and submitted."}
        }
        ```"""
    ]

    llm = MockLLMProvider(responses=responses)
    runtime = FakeRuntime()
    config = AgentConfig(max_steps=5, max_consecutive_malformed_actions=3, trajectory_dir=test_trajectory_dir)
    agent = CodingAgent(llm=llm, runtime=runtime, config=config)

    task = Task(task_id="task_recovery", instruction="Test recovery")
    result = agent.run(task)

    assert result.submitted is True
    assert result.status == "SUBMITTED"
    assert result.steps_taken == 2


def test_agent_max_malformed_termination(test_trajectory_dir):
    """Repeated malformed actions terminate the agent safely without crashing."""
    responses = ["not valid json 1", "not valid json 2", "not valid json 3"]

    llm = MockLLMProvider(responses=responses)
    runtime = FakeRuntime()
    config = AgentConfig(max_steps=10, max_consecutive_malformed_actions=2, trajectory_dir=test_trajectory_dir)
    agent = CodingAgent(llm=llm, runtime=runtime, config=config)

    task = Task(task_id="task_malformed", instruction="Test malformed termination")
    result = agent.run(task)

    assert result.submitted is False
    assert result.status == "MAX_MALFORMED_EXCEEDED"
    assert result.steps_taken == 2
    assert "Exceeded maximum consecutive malformed actions" in result.error


def test_agent_llm_exception_handling(test_trajectory_dir):
    """LLM timeouts or exceptions are safely caught and return structured error."""
    llm = MockLLMProvider(responses=[LLMTimeoutError("API timed out after 60s")])
    runtime = FakeRuntime()
    config = AgentConfig(max_steps=5, trajectory_dir=test_trajectory_dir)
    agent = CodingAgent(llm=llm, runtime=runtime, config=config)

    task = Task(task_id="task_timeout", instruction="Test timeout")
    result = agent.run(task)

    assert result.submitted is False
    assert result.status == "ERROR"
    assert "API timed out" in result.error


def test_agent_runtime_error_handled_in_observation(test_trajectory_dir):
    """When a tool execution encounters an error, it is passed into observation and loop continues."""
    responses = [
        # Turn 1: Try reading non-existent file
        """```json
        {"action": "read_file", "args": {"path": "does_not_exist.py"}}
        ```""",
        # Turn 2: Submit after realizing file was missing
        """```json
        {"action": "submit", "args": {"summary": "Finished attempt."}}
        ```"""
    ]

    llm = MockLLMProvider(responses=responses)
    runtime = FakeRuntime()
    config = AgentConfig(max_steps=5, trajectory_dir=test_trajectory_dir)
    agent = CodingAgent(llm=llm, runtime=runtime, config=config)

    task = Task(task_id="task_missing_file", instruction="Test missing file handling")
    result = agent.run(task)

    assert result.submitted is True
    assert result.status == "SUBMITTED"
    assert result.steps_taken == 2


def test_no_host_execution_or_modification(tmp_path):
    """
    Requirement 14: Verifies the agent layer strictly acts on the Runtime abstraction
    and never modifies files on the host machine directly.
    """
    host_file = tmp_path / "host_file.txt"
    host_file.write_text("INITIAL_HOST_CONTENT")

    # Agent attempts to write to host path
    responses = [
        f"""```json
        {{"action": "edit_file", "args": {{"path": "{host_file}", "content": "MODIFIED_CONTENT"}}}}
        ```""",
        """```json
        {"action": "submit", "args": {}}
        ```"""
    ]

    llm = MockLLMProvider(responses=responses)
    fake_runtime = FakeRuntime()
    config = AgentConfig(max_steps=5, trajectory_dir=str(tmp_path / "trajectories"))
    agent = CodingAgent(llm=llm, runtime=fake_runtime, config=config)

    agent.run("Test host isolation")

    # Ensure the real host file was NOT modified!
    assert host_file.read_text() == "INITIAL_HOST_CONTENT"
