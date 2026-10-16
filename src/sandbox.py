import os
import time
import docker
from typing import Optional, Tuple
from src.models import ToolCall, ExecutionResult
from src.tools.base import run_shell_command, write_file_command


class TransactionalSandbox:
    """
    Docker-backed transactional sandbox for isolated tool execution.
    Supports state promotion (commit) and state discard (rollback).
    """
    def __init__(
        self,
        image_name: str = "btp-sandbox:latest",
        committed_tag: str = "btp-sandbox-state:current",
        workspace_dir: str = "/workspace",
    ):
        self.image_name = image_name
        self.committed_tag = committed_tag
        self.workspace_dir = workspace_dir
        self.client = docker.from_env()
        self.ensure_base_state()

    def ensure_base_state(self):
        """Ensure the committed tag exists, tagging base image if absent."""
        try:
            self.client.images.get(self.committed_tag)
        except docker.errors.ImageNotFound:
            try:
                base_img = self.client.images.get(self.image_name)
                base_img.tag(self.committed_tag)
            except docker.errors.ImageNotFound:
                raise RuntimeError(
                    f"Base sandbox image '{self.image_name}' not found. "
                    "Please run `docker build -t btp-sandbox:latest .`"
                )

    def create_sandbox_container(self, network_enabled: bool = False):
        """Create a fresh isolated container from the current committed state tag."""
        net_mode = "bridge" if network_enabled else "none"
        
        container = self.client.containers.create(
            image=self.committed_tag,
            command="tail -f /dev/null",  # Keep container running for exec
            working_dir=self.workspace_dir,
            network_mode=net_mode,
            detach=True,
            tty=True,
        )
        container.start()
        return container

    def execute_tool(self, container, tool_call: ToolCall, enable_strace: bool = True) -> ExecutionResult:
        """
        Execute a tool inside the running sandbox container.
        Optionally wraps shell execution with strace to capture process/file trace.
        """
        tool_name = tool_call.tool
        args = tool_call.arguments

        if tool_name == "run_shell":
            raw_cmd = run_shell_command(args["command"])
        elif tool_name == "write_file":
            raw_cmd = write_file_command(args["path"], args["content"])
        else:
            raise ValueError(f"Unsupported tool '{tool_name}'")

        if enable_strace:
            # Wrap execution with strace to record trace to /tmp/strace.log inside container
            exec_cmd = [
                "/bin/bash",
                "-c",
                f"strace -f -o /tmp/strace.log -e trace=open,openat,creat,unlink,unlinkat,execve bash -c {raw_cmd!r}"
            ]
        else:
            exec_cmd = ["/bin/bash", "-c", raw_cmd]

        start_time = time.time()
        exec_res = container.exec_run(exec_cmd, workdir=self.workspace_dir)
        duration_ms = (time.time() - start_time) * 1000.0

        exit_code = exec_res.exit_code
        output_bytes = exec_res.output or b""
        stdout = output_bytes.decode("utf-8", errors="replace")

        return ExecutionResult(
            stdout=stdout,
            stderr="",  # Container exec combines stdout/stderr unless demuxed
            exit_code=exit_code,
            duration_ms=round(duration_ms, 2),
        )

    def commit_state(self, container) -> str:
        """
        Promote (commit) the container's current state to the persistent state tag.
        Discards the container instance afterwards.
        """
        repository, tag = self.committed_tag.split(":", 1)
        container.commit(repository=repository, tag=tag)
        container.remove(force=True)
        return self.committed_tag

    def rollback_state(self, container):
        """
        Discard container without committing its state changes.
        """
        container.remove(force=True)

    def reset_state(self):
        """Reset the committed state back to the base image."""
        base_img = self.client.images.get(self.image_name)
        repository, tag = self.committed_tag.split(":", 1)
        base_img.tag(repository=repository, tag=tag)
