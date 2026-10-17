import pytest
from src.sandbox import TransactionalSandbox
from src.models import ToolCall, DeclaredScope

pytestmark = pytest.mark.docker


def test_sandbox_execution_and_rollback():
    sandbox = TransactionalSandbox()
    container = sandbox.create_sandbox_container()
    tc = ToolCall(
        tool="write_file",
        arguments={"path": "/workspace/temp.txt", "content": "temp_data"},
        declared_scope=DeclaredScope(write=["/workspace/temp.txt"])
    )
    result = sandbox.execute_tool(container, tc)
    assert result.exit_code == 0
    
    # Rollback container
    sandbox.rollback_state(container)
    
    # Verify file does not exist in next fresh container
    new_c = sandbox.create_sandbox_container()
    check_res = new_c.exec_run("cat /workspace/temp.txt")
    assert check_res.exit_code != 0
    new_c.remove(force=True)
