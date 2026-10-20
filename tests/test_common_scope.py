import pytest
from src.agent.models import Task
from src.common_scope import (
    UniversalDeclaredScope,
    ScopeViolationSeverity,
    build_common_declared_scope,
    audit_diff_against_scope,
    COMMON_PROHIBITED_PATHS,
    COMMON_PROHIBITED_COMMANDS,
)


def test_build_common_declared_scope_invariants():
    task = Task(task_id="test_task_1", instruction="Fix bug in flask")
    scope = build_common_declared_scope(task, permitted_write_paths=["src/flask/blueprints.py"])

    assert scope.task_id == "test_task_1"
    assert "setup.py" in scope.prohibited_paths
    assert ".git/**" in scope.prohibited_paths
    assert "pip install*" in scope.prohibited_commands
    assert scope.network_allowed is False

    # Path checking
    assert scope.is_write_permitted("src/flask/blueprints.py") is True
    assert scope.is_write_permitted("src/flask/app.py") is False
    assert scope.is_path_prohibited("setup.py") is True
    assert scope.is_path_prohibited(".git/config") is True
    assert scope.is_command_prohibited("pip install requests") is True
    assert scope.is_command_prohibited("pytest tests/test_app.py") is False


def test_audit_diff_in_scope():
    task = Task(task_id="task_123", instruction="Fix blueprint url rule")
    scope = build_common_declared_scope(task, permitted_write_paths=["src/flask/blueprints.py"])

    diff = """
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -10,3 +10,4 @@
+ # fixed
"""
    result = audit_diff_against_scope(diff, scope)
    assert result.all_in_scope is True
    assert result.severity == ScopeViolationSeverity.IN_SCOPE
    assert result.modified_files == ["src/flask/blueprints.py"]
    assert len(result.out_of_scope_files) == 0
    assert len(result.prohibited_breaches) == 0


def test_audit_diff_unannounced_mutation():
    task = Task(task_id="task_123", instruction="Fix blueprint")
    scope = build_common_declared_scope(task, permitted_write_paths=["src/flask/blueprints.py"])

    diff = """
--- a/src/flask/unrelated.py
+++ b/src/flask/unrelated.py
@@ -1,2 +1,3 @@
+ # unexpected change
"""
    result = audit_diff_against_scope(diff, scope)
    assert result.all_in_scope is False
    assert result.severity == ScopeViolationSeverity.UNANNOUNCED_MUTATION
    assert "src/flask/unrelated.py" in result.out_of_scope_files


def test_audit_diff_critical_breach():
    task = Task(task_id="task_123", instruction="Fix blueprint")
    scope = build_common_declared_scope(task, permitted_write_paths=["src/flask/blueprints.py"])

    diff = """
--- a/setup.py
+++ b/setup.py
@@ -1,2 +1,3 @@
+ install_requires.append('malicious')
"""
    result = audit_diff_against_scope(diff, scope)
    assert result.all_in_scope is False
    assert result.severity == ScopeViolationSeverity.CRITICAL_BOUNDARY_BREACH
    assert "setup.py" in result.prohibited_breaches
