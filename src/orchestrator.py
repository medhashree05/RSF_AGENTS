import time
from src.models import ToolCall, EpisodeLog
from src.policy import PolicyLimiter
from src.sandbox import TransactionalSandbox
from src.auditor import GroundTruthAuditor
from src.comparator import ScopeComparator
from src.feedback import generate_feedback
from src.logger import EpisodeLogger


class ReversibilityOrchestrator:
    """
    Main Safety Loop Orchestrator managing Policy evaluation, Sandbox execution,
    Ground-Truth Auditing, Scope Comparison, State Commit/Rollback, and Feedback.
    """
    def __init__(
        self,
        workspace_dir: str = "/workspace",
        allow_network: bool = False,
        log_dir: str = "logs",
        image_name: str = "btp-sandbox:latest",
    ):
        self.workspace_dir = workspace_dir
        self.policy = PolicyLimiter(allowed_workspace=workspace_dir, allow_network=allow_network)
        self.sandbox = TransactionalSandbox(image_name=image_name, workspace_dir=workspace_dir)
        self.auditor = GroundTruthAuditor(workspace_dir=workspace_dir)
        self.comparator = ScopeComparator(workspace_dir=workspace_dir)
        self.logger = EpisodeLogger(log_dir=log_dir)

    def run_episode(self, scenario_id: str, tool_call: ToolCall) -> EpisodeLog:
        """Execute a complete single-turn episode through the safety control loop."""
        start_time = time.time()

        # 1. Policy Evaluation Gate
        policy_decision = self.policy.evaluate(tool_call)

        if not policy_decision.allowed:
            latency_ms = round((time.time() - start_time) * 1000.0, 2)
            feedback = generate_feedback(policy_decision, None)
            episode = EpisodeLog(
                scenario_id=scenario_id,
                tool_call=tool_call,
                policy_decision=policy_decision,
                execution_result=None,
                observed_effects=None,
                comparison_result=None,
                action_taken="REJECTED",
                feedback=feedback,
                latency_ms=latency_ms,
            )
            self.logger.log_episode(episode)
            return episode

        # 2. Transactional Sandbox Execution
        container = self.sandbox.create_sandbox_container(network_enabled=tool_call.declared_scope.network)
        try:
            exec_result = self.sandbox.execute_tool(container, tool_call, enable_strace=True)

            # 3. Ground-Truth Auditor Observation
            observed_effects = self.auditor.audit(container)

            # 4. Scope Comparison
            comparison_result = self.comparator.compare(tool_call.declared_scope, observed_effects)

            # 5. Commit or Rollback Control Gate
            if comparison_result.match:
                # MATCH -> Commit resulting state to container image tag
                self.sandbox.commit_state(container)
                action_taken = "COMMITTED"
            else:
                # MISMATCH -> Discard container state (Rollback)
                self.sandbox.rollback_state(container)
                action_taken = "ROLLED_BACK"

            feedback = generate_feedback(policy_decision, comparison_result)
            latency_ms = round((time.time() - start_time) * 1000.0, 2)

            episode = EpisodeLog(
                scenario_id=scenario_id,
                tool_call=tool_call,
                policy_decision=policy_decision,
                execution_result=exec_result,
                observed_effects=observed_effects,
                comparison_result=comparison_result,
                action_taken=action_taken,
                feedback=feedback,
                latency_ms=latency_ms,
            )
            self.logger.log_episode(episode)
            return episode

        except Exception as e:
            # Ensure container cleanup on unexpected execution failure
            self.sandbox.rollback_state(container)
            raise e

    def reset_system(self):
        """Reset container image state to clean base state."""
        self.sandbox.reset_state()
