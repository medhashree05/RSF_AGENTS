import os
from typing import List, Set
from src.models import DeclaredScope, ObservedEffects, ComparisonResult


class ScopeComparator:
    """
    Deterministically compares DeclaredScope against Auditor's ObservedEffects.
    Identifies scope matches, unexpected side-effects, and missing expected effects.
    """
    def __init__(self, workspace_dir: str = "/workspace"):
        self.workspace_dir = workspace_dir

    def normalize_path(self, path: str) -> str:
        """Normalize file path to absolute path relative to workspace with forward slashes."""
        if not path.startswith("/"):
            norm = os.path.abspath(os.path.join(self.workspace_dir, path))
        else:
            norm = os.path.abspath(path)
        return os.path.normpath(norm).replace("\\", "/")

    def is_path_declared_or_parent(self, path: str, declared_write_set: Set[str]) -> bool:
        """Check if path matches a declared write path or is a parent directory of one."""
        norm_p = self.normalize_path(path)
        if norm_p in declared_write_set:
            return True
        # Check if norm_p is a parent directory of any declared target path
        for dpath in declared_write_set:
            if dpath.startswith(norm_p.rstrip("/") + "/"):
                return True
        return False

    def compare(self, declared: DeclaredScope, observed: ObservedEffects) -> ComparisonResult:
        """Compare declared scope against actual ground-truth observed effects."""
        unexpected_effects: List[str] = []
        missing_expected_effects: List[str] = []

        # Normalize declared scopes
        declared_write_set: Set[str] = {self.normalize_path(p) for p in declared.write}
        declared_read_set: Set[str] = {self.normalize_path(p) for p in declared.read}

        # Combine all write/modify/delete file modifications observed
        observed_mutations = (
            set(observed.files_created) |
            set(observed.files_modified) |
            set(observed.files_deleted)
        )

        # 1. Check for unexpected file writes / modifications / deletions
        for path in sorted(list(observed_mutations)):
            if not self.is_path_declared_or_parent(path, declared_write_set):
                if path in observed.files_deleted:
                    unexpected_effects.append(f"delete {path}")
                elif path in observed.files_created:
                    unexpected_effects.append(f"create {path}")
                else:
                    unexpected_effects.append(f"write {path}")

        # 2. Check for unexpected file reads
        for path in sorted(list(observed.files_read)):
            norm_p = self.normalize_path(path)
            # A path is permitted to be read if declared in `read` or covered by `write`
            if norm_p not in declared_read_set and not self.is_path_declared_or_parent(norm_p, declared_write_set):
                unexpected_effects.append(f"read {path}")

        # 3. Check for unexpected network access
        if observed.network and not declared.network:
            for net_event in observed.network:
                unexpected_effects.append(f"network {net_event}")

        # 4. Check for missing expected write effects (warning indicator)
        for dpath in sorted(list(declared_write_set)):
            # Check if declared file or any child was created/modified
            covered = any(
                p == dpath or p.startswith(dpath.rstrip("/") + "/")
                for p in observed_mutations
            )
            if not covered:
                missing_expected_effects.append(f"write {dpath}")

        match = len(unexpected_effects) == 0

        if match:
            reason = "Observed effects strictly match declared scope"
        else:
            reason = f"Scope violation detected: {len(unexpected_effects)} unexpected effect(s)"

        return ComparisonResult(
            match=match,
            unexpected_effects=unexpected_effects,
            missing_expected_effects=missing_expected_effects,
            reason=reason,
        )
