import io
import os
import re
import tarfile
import time
from typing import Any, Dict, List, Optional

import docker
from docker.models.containers import Container

from src.agent.models import Action, Observation
from src.models import ExecutionResult


class DockerRuntime:
    """
    Docker-sandboxed execution environment implementing the Runtime protocol.
    
    Isolates all file access, shell execution, and test execution inside a dedicated
    Docker container. Host filesystem is never touched during task execution.
    """
    def __init__(
        self,
        image_name: str = "btp-sandbox:latest",
        workspace_dir: str = "/workspace",
        timeout_seconds: float = 60.0
    ):
        self.image_name = image_name
        self.workspace_dir = workspace_dir
        self.timeout_seconds = timeout_seconds
        self.client: Optional[docker.DockerClient] = None
        self.container: Optional[Container] = None
        self.current_task: Optional[Any] = None
        self.is_started: bool = False
        self.is_stopped: bool = False

    def _get_client(self) -> docker.DockerClient:
        if self.client is None:
            self.client = docker.from_env()
        return self.client

    def _normalize_container_path(self, path: str) -> str:
        """Ensure path is within /workspace and reject path traversal."""
        path = path.strip()
        if ".." in path:
            raise PermissionError(f"Security violation: path traversal rejected: '{path}'")
        
        # Replace backslashes if any were passed from Windows host
        path = path.replace("\\", "/")
        
        if path.startswith(self.workspace_dir + "/"):
            return path
        elif path == self.workspace_dir:
            return path
        elif path.startswith("/"):
            # Strips leading slash to nest under workspace
            return f"{self.workspace_dir}/{path.lstrip('/')}"
        else:
            return f"{self.workspace_dir}/{path}"

    def start(self, repository: Optional[str] = None, task: Optional[Any] = None) -> None:
        """Start container, ingest repository files into /workspace, and init git baseline."""
        client = self._get_client()
        self.current_task = task
        self.is_started = True
        self.is_stopped = False

        # 1. Create and start isolated container
        self.container = client.containers.create(
            image=self.image_name,
            command="tail -f /dev/null",
            working_dir=self.workspace_dir,
            detach=True,
            tty=True,
        )
        self.container.start()

        # 2. Copy repository into container if provided
        if repository and os.path.isdir(repository):
            self._copy_local_dir_to_container(repository, self.workspace_dir)

        # 3. Initialize git repository in workspace for clean diff tracking
        git_setup_cmd = (
            "git config --global --add safe.directory /workspace && "
            "git init && "
            "git config user.name 'btp-agent' && "
            "git config user.email 'agent@btp.local' && "
            "git add -A && "
            "git commit -m 'initial state' --allow-empty"
        )
        self.container.exec_run(["/bin/bash", "-c", git_setup_cmd], workdir=self.workspace_dir)

    def stop(self) -> None:
        """Safely destroy container and release docker resources."""
        self.is_started = False
        self.is_stopped = True
        if self.container is not None:
            try:
                self.container.remove(force=True)
            except Exception:
                pass
            finally:
                self.container = None

    def _copy_local_dir_to_container(self, local_path: str, container_dest: str) -> None:
        """Archive local directory into in-memory tar stream and extract into container."""
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            for root, dirs, files in os.walk(local_path):
                # Ignore version control and virtual env directories
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "venv", ".venv")]
                for fname in files:
                    if fname.startswith("."):
                        continue
                    full_p = os.path.join(root, fname)
                    rel_p = os.path.relpath(full_p, local_path).replace("\\", "/")
                    tar.add(full_p, arcname=rel_p)
        tar_stream.seek(0)
        self.container.put_archive(container_dest, tar_stream.getvalue())

    def execute_shell(self, command: str, timeout: Optional[float] = None) -> ExecutionResult:
        """Run a shell command inside the container environment."""
        if not self.container:
            raise RuntimeError("DockerRuntime container is not running. Call start() first.")

        start_time = time.time()
        timeout_sec = int(timeout or 120)
        safe_cmd = f"timeout {timeout_sec}s /bin/bash -c {command!r}"
        exec_res = self.container.exec_run(
            ["/bin/bash", "-c", safe_cmd],
            workdir=self.workspace_dir,
            demux=True
        )
        duration_ms = round((time.time() - start_time) * 1000.0, 2)

        stdout_bytes, stderr_bytes = exec_res.output or (b"", b"")
        stdout = (stdout_bytes or b"").decode("utf-8", errors="replace")
        stderr = (stderr_bytes or b"").decode("utf-8", errors="replace")
        exit_code = exec_res.exit_code if exec_res.exit_code is not None else 0

        return ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms
        )

    def file_exists(self, path: str) -> bool:
        """Check file existence inside container."""
        full_path = self._normalize_container_path(path)
        cmd = f"test -e {full_path!r}"
        res = self.execute_shell(cmd)
        return res.exit_code == 0

    def read_file(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """Read file content from container with optional line range slice."""
        if not self.container:
            raise RuntimeError("DockerRuntime container is not running.")
        full_path = self._normalize_container_path(path)
        if not self.file_exists(path):
            raise FileNotFoundError(f"File not found in container: {path}")

        try:
            bits, _ = self.container.get_archive(full_path)
            tar_stream = io.BytesIO()
            for chunk in bits:
                tar_stream.write(chunk)
            tar_stream.seek(0)
            with tarfile.open(fileobj=tar_stream, mode="r") as tar:
                member = tar.next()
                if not member or not member.isfile():
                    raise FileNotFoundError(f"Path is not a regular file: {path}")
                extracted = tar.extractfile(member)
                content = extracted.read().decode("utf-8", errors="replace") if extracted else ""
        except Exception as e:
            # Fallback to cat command
            res = self.execute_shell(f"cat {full_path!r}")
            if res.exit_code != 0:
                raise FileNotFoundError(f"Could not read file {path}: {res.stderr}")
            content = res.stdout

        if start_line is not None or end_line is not None:
            lines = content.splitlines()
            s = max(1, start_line if start_line is not None else 1)
            e = end_line if end_line is not None else len(lines)
            selected = lines[s - 1:e]
            return "\n".join(f"{s + i}: {line}" for i, line in enumerate(selected))
        return content

    def write_file(self, path: str, content: str) -> None:
        """Write text content to a file inside the container."""
        if not self.container:
            raise RuntimeError("DockerRuntime container is not running.")
        full_path = self._normalize_container_path(path)
        parent_dir = os.path.dirname(full_path)

        # Ensure parent directory exists in container
        if parent_dir and parent_dir != self.workspace_dir:
            self.execute_shell(f"mkdir -p {parent_dir!r}")

        # Put file via in-memory tar archive to avoid shell escaping issues
        tar_stream = io.BytesIO()
        encoded = content.encode("utf-8")
        tar_info = tarfile.TarInfo(name=os.path.basename(full_path))
        tar_info.size = len(encoded)
        tar_info.mtime = int(time.time())

        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            tar.addfile(tar_info, io.BytesIO(encoded))
        tar_stream.seek(0)

        self.container.put_archive(parent_dir or self.workspace_dir, tar_stream.getvalue())

    def list_files(self, directory: str = ".") -> List[str]:
        """List files relative to workspace."""
        cmd = "find . -type f | sed 's|^\\./||'"
        res = self.execute_shell(cmd)
        if res.exit_code == 0 and res.stdout:
            files = [f.strip() for f in res.stdout.splitlines() if f.strip() and not f.startswith(".git/")]
            return sorted(files)
        return []

    def get_changes(self) -> str:
        """Return unified git diff of all modifications made in workspace."""
        res = self.execute_shell("git diff HEAD")
        diff = res.stdout
        # Also check untracked files
        untracked = self.execute_shell("git status --porcelain")
        if untracked.stdout.strip():
            diff = f"{diff}\n\n# Untracked files:\n{untracked.stdout}".strip()
        return diff

    def run_tests(self, command: Optional[str] = None) -> ExecutionResult:
        """Run tests inside container workspace."""
        cmd = command
        if not cmd and self.current_task:
            if hasattr(self.current_task, "test_command") and self.current_task.test_command:
                cmd = self.current_task.test_command
        if not cmd:
            cmd = "pytest"
        return self.execute_shell(cmd)

    def execute(self, action: Action) -> Observation:
        """Execute an ACI Action inside the container."""
        action_type = action.action_type
        args = action.args

        try:
            if action_type == "search":
                query = args.get("query", "")
                if not query:
                    return Observation(success=False, output="", error="Search query cannot be empty")
                # Run grep inside container workspace
                res = self.execute_shell(f"grep -rn --exclude-dir='.git' {query!r} .")
                out = res.stdout.strip()
                if not out:
                    return Observation(success=True, output=f"No matches found for query: '{query}'")
                return Observation(success=True, output=out)

            elif action_type == "read_file":
                path = args.get("path", "")
                if not path:
                    return Observation(success=False, output="", error="Path cannot be empty")
                start_l = args.get("start_line", 1)
                end_l = args.get("end_line")
                content = self.read_file(path, start_line=start_l, end_line=end_l)
                return Observation(success=True, output=content)

            elif action_type == "edit_file":
                path = args.get("path", "")
                if not path:
                    return Observation(success=False, output="", error="Path cannot be empty")

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
                        return Observation(success=False, output="", error=f"Target old_str appears {count} times in '{path}'. Must be unique.")
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
                    new_lines = lines[:s - 1] + rep + lines[e:]
                    self.write_file(path, "\n".join(new_lines))
                    return Observation(success=True, output=f"Successfully replaced lines {s}-{e} in '{path}'")

                else:
                    return Observation(success=False, output="", error="edit_file requires content, old_str/new_str, or start_line/end_line/replacement_text")

            elif action_type == "run_shell":
                cmd = args.get("command", "")
                if not cmd.strip():
                    return Observation(success=False, output="", error="Shell command cannot be empty")
                res = self.execute_shell(cmd)
                success = res.exit_code == 0
                out = res.stdout
                if res.stderr:
                    out = f"{out}\n{res.stderr}".strip()
                err = None if success else f"Command exited with non-zero exit code: {res.exit_code}"
                return Observation(success=success, output=out, error=err, metadata={"exit_code": res.exit_code})

            elif action_type == "submit":
                summary = args.get("summary", "Task submitted.")
                return Observation(success=True, output=f"Submission accepted: {summary}")

            else:
                return Observation(success=False, output="", error=f"Unknown action_type '{action_type}'")

        except PermissionError as pe:
            return Observation(success=False, output="", error=str(pe))
        except FileNotFoundError as fe:
            return Observation(success=False, output="", error=str(fe))
        except Exception as e:
            return Observation(success=False, output="", error=f"Runtime error executing '{action_type}': {e}")
