import re
from typing import Dict, List, Set
from src.models import ObservedEffects


# Docker diff event kinds:
DOCKER_DIFF_MODIFIED = 0
DOCKER_DIFF_ADDED = 1
DOCKER_DIFF_DELETED = 2

SYSTEM_DIFF_IGNORE_PREFIXES = (
    "/tmp/",
    "/dev/",
    "/run/",
    "/proc/",
    "/sys/",
    "/etc/resolv.conf",
    "/etc/hostname",
    "/etc/hosts",
)

SYSTEM_READ_IGNORE_PREFIXES = (
    "/lib/",
    "/usr/lib/",
    "/lib64/",
    "/usr/share/",
    "/etc/ld.so",
    "/etc/nsswitch.conf",
    "/etc/locale",
    "/etc/gai.conf",
    "/etc/passwd",
    "/etc/group",
    "/etc/shadow",
    "/etc/login.defs",
    "/etc/pam.d",
    "/etc/profile",
    "/etc/bash.bashrc",
    "/tmp/",
    "/dev/",
    "/proc/",
    "/sys/",
)


class GroundTruthAuditor:
    """
    Independently inspects running container to audit ground-truth execution effects.
    Uses `docker diff` for filesystem changes and parses `/tmp/strace.log` for access/process events.
    """
    def __init__(self, workspace_dir: str = "/workspace"):
        self.workspace_dir = workspace_dir

    def is_system_diff_path(self, path: str) -> bool:
        """Check if path is container system internal directory or metadata."""
        if path == self.workspace_dir or path == "/":
            return True
        for prefix in SYSTEM_DIFF_IGNORE_PREFIXES:
            if path == prefix.rstrip("/") or path.startswith(prefix):
                return True
        return False

    def is_system_read_path(self, path: str) -> bool:
        """Check if path is dynamic linker or system runtime library access."""
        for prefix in SYSTEM_READ_IGNORE_PREFIXES:
            if path == prefix.rstrip("/") or path.startswith(prefix):
                return True
        return False

    def audit(self, container) -> ObservedEffects:
        """Derive observed execution effects from actual container diff and traces."""
        files_created: Set[str] = set()
        files_modified: Set[str] = set()
        files_deleted: Set[str] = set()
        files_read: Set[str] = set()
        processes: Set[str] = set()
        network: Set[str] = set()

        # 1. Primary Filesystem Audit via `docker diff`
        try:
            diffs = container.diff() or []
            for item in diffs:
                path = item.get("Path", "")
                kind = item.get("Kind")

                # Filter system directory metadata
                if self.is_system_diff_path(path):
                    continue

                if kind == DOCKER_DIFF_ADDED:
                    files_created.add(path)
                elif kind == DOCKER_DIFF_MODIFIED:
                    files_modified.add(path)
                elif kind == DOCKER_DIFF_DELETED:
                    files_deleted.add(path)

        except Exception as e:
            print(f"[Auditor Warning] Error querying docker diff: {e}")

        # 2. Secondary Audit via `strace` log parsing
        try:
            strace_res = container.exec_run("cat /tmp/strace.log")
            if strace_res.exit_code == 0 and strace_res.output:
                log_text = strace_res.output.decode("utf-8", errors="ignore")
                
                # Parse read access: openat(AT_FDCWD, "/workspace/secrets/api_key", O_RDONLY...) = 3
                open_matches = re.findall(
                    r'(?:open|openat)\([^,]*,\s*"([^"]+)"\s*,\s*(?:O_RDONLY|O_RDWR)[^=]*=\s*([0-9]+)',
                    log_text
                )
                for path, fd in open_matches:
                    if not self.is_system_read_path(path):
                        if path not in files_created and path not in files_modified:
                            files_read.add(path)

                # Parse file deletion from strace: unlink / unlinkat
                unlink_matches = re.findall(r'unlink(?:at)?\([^,]*,\s*"([^"]+)"', log_text)
                for path in unlink_matches:
                    if not self.is_system_read_path(path):
                        files_deleted.add(path)

                # Parse process executions: execve("/bin/bash", ...) = 0
                exec_matches = re.findall(r'execve\("([^"]+)"', log_text)
                for proc in exec_matches:
                    if not self.is_system_read_path(proc):
                        processes.add(proc)

                # Parse network calls
                socket_matches = re.findall(r'socket\((AF_INET|AF_INET6|AF_NETLINK)', log_text)
                for sock in socket_matches:
                    network.add(f"socket:{sock}")

                connect_matches = re.findall(r'connect\([^,]*,\s*({[^}]+})', log_text)
                for conn in connect_matches:
                    network.add(f"connect:{conn}")

        except Exception as e:
            pass

        return ObservedEffects(
            files_created=sorted(list(files_created)),
            files_modified=sorted(list(files_modified)),
            files_deleted=sorted(list(files_deleted)),
            files_read=sorted(list(files_read)),
            processes=sorted(list(processes)),
            network=sorted(list(network)),
        )
