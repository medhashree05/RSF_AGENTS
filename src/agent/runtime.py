from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
import os
import re
from abc import ABC, abstractmethod

from src.agent.models import Action, Observation
from src.models import ExecutionResult


@runtime_checkable
class Runtime(Protocol):
    """
    Abstract contract for the runtime execution environment (e.g. Docker container).
    
    The agent layer NEVER interacts with the host filesystem or spawns host processes.
    All environment interactions must pass through this interface.
    """

    def execute(self, action: Action) -> Observation:
        """
        Execute an Action emitted by the agent and return a structured Observation.
        
        Args:
            action: The validated Action containing action_type, args, and declared_scope.
            
        Returns:
            Observation: Structured observation with success flag, output text, and optional error.
        """
        ...

    def execute_shell(self, command: str, timeout: Optional[float] = None) -> ExecutionResult:
        """Execute a shell command inside the isolated runtime environment."""
        ...

    def read_file(self, path: str) -> str:
        """Read text content of a file inside the isolated runtime environment."""
        ...

    def write_file(self, path: str, content: str) -> None:
        """Write text content to a file inside the isolated runtime environment."""
        ...

    def file_exists(self, path: str) -> bool:
        """Check whether a file exists in the isolated runtime environment."""
        ...

    def list_files(self, directory: str = ".") -> List[str]:
        """List files relative to the workspace directory."""
        ...


class FakeRuntime:
    """
    Deterministic, in-memory runtime for testing and offline execution.
    
    Operates strictly within an in-memory virtual file dictionary and mocked command
    table without any real host execution, Docker daemon access, or filesystem mutation.
    """
    def __init__(
        self,
        initial_files: Optional[Dict[str, str]] = None,
        mock_commands: Optional[Dict[str, ExecutionResult]] = None,
        default_shell_output: str = "Command executed successfully.",
    ):
        # Normalize paths by stripping leading slashes or workspace prefixes
        self.files: Dict[str, str] = {}
        if initial_files:
            for p, content in initial_files.items():
                self.files[self._normalize_path(p)] = content

        self.mock_commands: Dict[str, ExecutionResult] = mock_commands or {}
        self.default_shell_output = default_shell_output
        self.executed_actions: List[Action] = []
        self.executed_commands: List[str] = []

    def _normalize_path(self, path: str) -> str:
        path = path.strip()
        if path.startswith("/workspace/"):
            path = path[len("/workspace/"):]
        elif path.startswith("/"):
            path = path.lstrip("/")
        # Normalize double slashes or current dir prefixes
        parts = []
        for segment in path.split("/"):
            if segment == "." or not segment:
                continue
            if segment == "..":
                if parts:
                    parts.pop()
                else:
                    raise PermissionError(f"Path traversal detected: {path}")
            else:
                parts.append(segment)
        return "/".join(parts)

    def file_exists(self, path: str) -> bool:
        norm = self._normalize_path(path)
        return norm in self.files

    def read_file(self, path: str) -> str:
        norm = self._normalize_path(path)
        if norm not in self.files:
            raise FileNotFoundError(f"File not found: {path}")
        return self.files[norm]

    def write_file(self, path: str, content: str) -> None:
        norm = self._normalize_path(path)
        self.files[norm] = content

    def list_files(self, directory: str = ".") -> List[str]:
        norm_dir = self._normalize_path(directory) if directory != "." else ""
        results = []
        for p in self.files:
            if not norm_dir:
                results.append(p)
            elif p.startswith(norm_dir.rstrip("/") + "/"):
                results.append(p)
        return sorted(results)

    def execute_shell(self, command: str, timeout: Optional[float] = None) -> ExecutionResult:
        self.executed_commands.append(command)
        # Check explicit mock table
        if command in self.mock_commands:
            return self.mock_commands[command]
        
        # Regex or substring match fallback
        for pattern, res in self.mock_commands.items():
            if pattern in command or (re.search(pattern, command) is not None):
                return res

        return ExecutionResult(
            stdout=self.default_shell_output,
            stderr="",
            exit_code=0,
            duration_ms=5.0
        )

    def execute(self, action: Action) -> Observation:
        """Default dispatch for FakeRuntime matching ACI requirements."""
        self.executed_actions.append(action)
        action_type = action.action_type
        args = action.args

        try:
            if action_type == "search":
                query = args.get("query", "")
                if not query:
                    return Observation(success=False, output="", error="Search query cannot be empty")
                matches = []
                for fpath, content in sorted(self.files.items()):
                    for idx, line in enumerate(content.splitlines(), start=1):
                        if query in line:
                            matches.append(f"{fpath}:{idx}: {line}")
                if not matches:
                    return Observation(success=True, output=f"No matches found for query: '{query}'")
                return Observation(success=True, output="\n".join(matches))

            elif action_type == "read_file":
                path = args.get("path", "")
                if not path:
                    return Observation(success=False, output="", error="Path cannot be empty")
                content = self.read_file(path)
                lines = content.splitlines()
                start_line = args.get("start_line", 1)
                end_line = args.get("end_line", len(lines))
                
                # Validation of line range
                if start_line < 1:
                    start_line = 1
                if end_line < start_line:
                    return Observation(success=False, output="", error=f"Invalid line range: start_line ({start_line}) > end_line ({end_line})")
                
                selected = lines[start_line - 1:end_line]
                formatted = [f"{start_line + i}: {line}" for i, line in enumerate(selected)]
                return Observation(success=True, output="\n".join(formatted))

            elif action_type == "edit_file":
                path = args.get("path", "")
                if not path:
                    return Observation(success=False, output="", error="Path cannot be empty")
                
                # Check edit mode: replace_lines, str_replace, or full content write
                if "content" in args:
                    self.write_file(path, args["content"])
                    return Observation(success=True, output=f"Successfully updated file '{path}'")
                
                elif "old_str" in args and "new_str" in args:
                    if not self.file_exists(path):
                        return Observation(success=False, output="", error=f"File not found: {path}")
                    current = self.read_file(path)
                    old_str = args["old_str"]
                    new_str = args["new_str"]
                    count = current.count(old_str)
                    if count == 0:
                        return Observation(success=False, output="", error=f"Target old_str not found in '{path}'")
                    if count > 1:
                        return Observation(
                            success=False,
                            output="",
                            error=f"Target old_str appears {count} times in '{path}'. Must be unique."
                        )
                    updated = current.replace(old_str, new_str, 1)
                    self.write_file(path, updated)
                    return Observation(success=True, output=f"Successfully replaced text in '{path}'")
                
                elif "start_line" in args and "end_line" in args and "replacement_text" in args:
                    if not self.file_exists(path):
                        return Observation(success=False, output="", error=f"File not found: {path}")
                    current = self.read_file(path)
                    lines = current.splitlines()
                    s = args["start_line"]
                    e = args["end_line"]
                    rep = args["replacement_text"].splitlines()
                    new_lines = lines[:s-1] + rep + lines[e:]
                    self.write_file(path, "\n".join(new_lines))
                    return Observation(success=True, output=f"Successfully replaced lines {s}-{e} in '{path}'")
                
                else:
                    return Observation(
                        success=False,
                        output="",
                        error="edit_file requires either 'content', ('old_str', 'new_str'), or ('start_line', 'end_line', 'replacement_text')"
                    )

            elif action_type == "run_shell":
                cmd = args.get("command", "")
                if not cmd.strip():
                    return Observation(success=False, output="", error="Shell command cannot be empty")
                res = self.execute_shell(cmd)
                success = res.exit_code == 0
                out = res.stdout
                if res.stderr:
                    out = f"{out}\n{res.stderr}".strip()
                err = None if success else f"Command exited with non-zero status code: {res.exit_code}"
                return Observation(success=success, output=out, error=err, metadata={"exit_code": res.exit_code})

            elif action_type == "submit":
                summary = args.get("summary", "Task submitted.")
                return Observation(success=True, output=f"Submission accepted: {summary}")

            else:
                return Observation(success=False, output="", error=f"Unknown action_type '{action_type}'")

        except PermissionError as pe:
            return Observation(success=False, output="", error=str(pe))
        except Exception as e:
            return Observation(success=False, output="", error=f"Runtime error executing '{action_type}': {e}")
