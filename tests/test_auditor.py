import pytest
from src.auditor import GroundTruthAuditor
from src.sandbox import TransactionalSandbox
from src.models import ToolCall, DeclaredScope


def test_auditor_detects_created_file():
    sandbox = TransactionalSandbox()
    auditor = GroundTruthAuditor()
    container = sandbox.create_sandbox_container()
    
    tc = ToolCall(
        tool="write_file",
        arguments={"path": "/workspace/audit_test.txt", "content": "hello auditor"},
        declared_scope=DeclaredScope(write=["/workspace/audit_test.txt"])
    )
    sandbox.execute_tool(container, tc)
    effects = auditor.audit(container)
    
    assert "/workspace/audit_test.txt" in effects.files_created
    sandbox.rollback_state(container)
