import os
import pytest
from src.agent.runtime import Runtime
from src.runtime.docker_runtime import DockerRuntime
from src.agent.models import Action

pytestmark = pytest.mark.docker


def test_docker_runtime_complies_with_protocol():
    """Verify DockerRuntime conforms to the Runtime protocol."""
    runtime = DockerRuntime()
    assert isinstance(runtime, Runtime)


def test_docker_runtime_lifecycle_and_operations():
    """Test full DockerRuntime lifecycle: start, file ops, test execution, diff, and stop."""
    runtime = DockerRuntime(image_name="btp-sandbox:latest")
    
    # 1. Start with sample repo
    runtime.start(repository="./fixtures/sample_repo")
    try:
        assert runtime.is_started is True
        assert runtime.container is not None

        # 2. File exists & read file
        assert runtime.file_exists("src/calculator.py") is True
        content = runtime.read_file("src/calculator.py", start_line=1, end_line=5)
        assert "1: def add" in content

        # 3. Write file / edit
        runtime.write_file("new_module.py", "def hello(): return 'world'\n")
        assert runtime.file_exists("new_module.py") is True
        assert "world" in runtime.read_file("new_module.py")

        # 4. Execute ACI action
        action = Action(
            action_type="run_shell",
            args={"command": "python3 -c \"import new_module; print(new_module.hello())\""}
        )
        obs = runtime.execute(action)
        assert obs.success is True
        assert "world" in obs.output

        # 5. Run tests inside container
        test_res = runtime.run_tests("pytest tests/test_calculator.py")
        assert test_res.exit_code is not None

        # 6. Get changes (git diff)
        diff = runtime.get_changes()
        assert diff is not None

    finally:
        # 7. Stop and clean up container
        runtime.stop()
        assert runtime.container is None
        assert runtime.is_stopped is True
