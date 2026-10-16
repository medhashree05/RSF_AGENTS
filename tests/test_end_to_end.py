import pytest
from src.mock_agent import MockAgent
from src.orchestrator import ReversibilityOrchestrator


@pytest.fixture
def orchestrator():
    orch = ReversibilityOrchestrator()
    orch.reset_system()
    yield orch
    orch.reset_system()


def test_end_to_end_scenario_1_commit(orchestrator):
    mock = MockAgent()
    s1 = mock.get_scenario("scenario_1")
    ep = orchestrator.run_episode("test_s1", s1["tool_call"])
    assert ep.action_taken == "COMMITTED"
    assert ep.policy_decision.allowed is True
    assert ep.comparison_result.match is True


def test_end_to_end_scenario_2_rollback_read(orchestrator):
    mock = MockAgent()
    s2 = mock.get_scenario("scenario_2")
    ep = orchestrator.run_episode("test_s2", s2["tool_call"])
    assert ep.action_taken == "ROLLED_BACK"
    assert ep.comparison_result.match is False


def test_end_to_end_scenario_3_rollback_delete(orchestrator):
    mock = MockAgent()
    s3 = mock.get_scenario("scenario_3")
    ep = orchestrator.run_episode("test_s3", s3["tool_call"])
    assert ep.action_taken == "ROLLED_BACK"
    assert ep.comparison_result.match is False


def test_end_to_end_scenario_4_policy_reject(orchestrator):
    mock = MockAgent()
    s4 = mock.get_scenario("scenario_4")
    ep = orchestrator.run_episode("test_s4", s4["tool_call"])
    assert ep.action_taken == "REJECTED"
    assert ep.policy_decision.allowed is False


def test_end_to_end_scenario_5_multi_dir_commit(orchestrator):
    mock = MockAgent()
    s5 = mock.get_scenario("scenario_5")
    ep = orchestrator.run_episode("test_s5", s5["tool_call"])
    assert ep.action_taken == "COMMITTED"
    assert ep.policy_decision.allowed is True
    assert ep.comparison_result.match is True
