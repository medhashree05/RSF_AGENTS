# Integration Contract for Docker Runtime Teammate

This document specifies the exact interface and behavioral contract that the **Docker / Execution Environment Teammate** must implement to integrate their container runtime with the baseline coding agent.

---

## 1. Target Class Specification

The teammate should implement a concrete runtime class (e.g. `DockerRuntime` in `src/runtime/docker_runtime.py` or `src/sandbox.py`) conforming to `src.agent.runtime.Runtime`:

```python
from typing import Any, Dict, List, Optional
from src.agent.models import Action, Observation
from src.models import ExecutionResult


class DockerRuntime:
    def __init__(
        self,
        image_name: str = "btp-sandbox:latest",
        workspace_dir: str = "/workspace",
        timeout_seconds: float = 60.0
    ):
        ...
```

---

## 2. Required Methods & Contracts

### 1. `start(self, repository: Optional[str] = None, task: Optional[Any] = None) -> None`
- **Purpose**: Prepare a fresh isolated Docker container for the agent run.
- **Requirements**:
  - If `repository` is provided (path to local repo), copy or mount it cleanly into container `/workspace`.
  - Ensure working directory is set to `/workspace`.
  - Start container in background (e.g., `command="tail -f /dev/null"`).
  - Snapshot or tag the base state so clean diffs can be calculated later.

### 2. `stop(self) -> None`
- **Purpose**: Clean up and tear down the container environment.
- **Requirements**:
  - Must safely stop and remove the container (`container.remove(force=True)`).
  - Must not raise uncaught exceptions if the container was already stopped.
  - Guarantees zero orphaned containers on the host.

### 3. `execute(self, action: Action) -> Observation`
- **Purpose**: Execute an ACI Action inside the container workspace.
- **Actions handled**:
  - `run_shell`: Execute `action.args["command"]` via `container.exec_run` in `/workspace`. Return `Observation(success=(exit_code == 0), output=stdout+stderr)`.
  - `read_file`: Read file from container `/workspace`. Return lines with 1-based indexing if `start_line`/`end_line` are specified.
  - `edit_file`: Apply edits (substring replace or write content) inside container filesystem.
  - `search`: Search for text across container `/workspace`.
  - `submit`: Acknowledge completion.

### 4. `execute_shell(self, command: str, timeout: Optional[float] = None) -> ExecutionResult`
- **Purpose**: Raw command execution in container.
- **Returns**: `ExecutionResult(stdout=..., stderr=..., exit_code=..., duration_ms=...)`.

### 5. `read_file(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str`
- **Purpose**: Read file contents from container `/workspace`.
- **Requirements**:
  - Reject paths containing `..` or attempting to access files outside `/workspace`.
  - Raise `FileNotFoundError` if the path does not exist in container.

### 6. `write_file(self, path: str, content: str) -> None`
- **Purpose**: Write or update a file in container `/workspace`.

### 7. `file_exists(self, path: str) -> bool`
- **Purpose**: Check if path exists in container `/workspace`.

### 8. `list_files(self, directory: str = ".") -> List[str]`
- **Purpose**: Return recursive list of files relative to `/workspace`.

### 9. `get_changes(self) -> str`
- **Purpose**: Return a unified git diff representing all code changes made by the agent.
- **Implementation**: Run `git diff HEAD` (or diff against initial commit/tag) inside container `/workspace`.

### 10. `run_tests(self, command: Optional[str] = None) -> ExecutionResult`
- **Purpose**: Run repository tests inside container.
- **Implementation**: Run `command` (e.g. `pytest`) via `execute_shell`.

---

## 3. Compliance Verification Test

The teammate can verify that their `DockerRuntime` complies with this contract by running the following integration test against their class:

```python
from src.agent.runtime import Runtime
from src.runtime.docker_runtime import DockerRuntime  # Teammate's class

def test_docker_runtime_contract():
    runtime = DockerRuntime()
    # 1. Typecheck against Runtime protocol
    assert isinstance(runtime, Runtime)

    # 2. Lifecycle
    runtime.start(repository="./fixtures/sample_repo")
    try:
        assert runtime.file_exists("src/calculator.py")
        content = runtime.read_file("src/calculator.py")
        assert "def divide" in content

        # 3. Test execution
        test_res = runtime.run_tests("pytest tests/test_calculator.py")
        assert test_res.exit_code is not None

        # 4. Changes
        runtime.write_file("test.txt", "sample")
        diff = runtime.get_changes()
        assert diff is not None
    finally:
        runtime.stop()
```

---

## 4. Teammate Handoff & Next Steps

When the Docker teammate is ready:
1. Provide `DockerRuntime` implementing this protocol.
2. In `run_agent.py`, replace `runtime = FakeRuntime()` with:
   ```python
   runtime = DockerRuntime()
   ```
3. Run the baseline coding agent directly inside Docker:
   ```bash
   python run_agent.py --repo ./fixtures/sample_repo --task ./tasks/task_01.json
   ```
No changes to `CodingAgent`, `ACI`, prompts, or parsing will be required!
