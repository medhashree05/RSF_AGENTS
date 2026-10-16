import logging
from typing import Any, Dict, List, Optional, Union

from src.agent.models import Action, AgentResult, Observation, Task
from src.agent.config import AgentConfig
from src.agent.llm import LLMProvider, LLMResponse, LLMError, TokenUsage
from src.agent.runtime import Runtime
from src.agent.aci import ACIDispatcher
from src.agent.parser import parse_action, ActionParseError
from src.agent.history import AgentHistory
from src.agent.prompts import load_system_prompt
from src.agent.logger import TrajectoryLogger

logger = logging.getLogger(__name__)


class CodingAgent:
    """
    SWE-agent-inspired coding agent operating via an Agent-Computer Interface (ACI).
    
    Interacts with an isolated repository environment iteratively, parsing structured actions,
    preserving an explicit declared scope, executing tools via Runtime abstraction,
    and logging complete trajectories to reproducible JSONL files.
    """
    def __init__(
        self,
        llm: LLMProvider,
        runtime: Runtime,
        config: Optional[AgentConfig] = None,
        logger: Optional[TrajectoryLogger] = None,
        system_prompt: Optional[str] = None,
    ):
        self.llm = llm
        self.runtime = runtime
        self.config = config or AgentConfig()
        self.trajectory_logger = logger or TrajectoryLogger(
            log_dir=self.config.trajectory_dir,
            experiment_id=self.config.experiment_id,
        )
        self.system_prompt = system_prompt or load_system_prompt()
        self.aci_dispatcher = ACIDispatcher(max_chars=self.config.max_observation_chars)

    def run(self, task: Union[Task, str, Dict[str, Any]]) -> AgentResult:
        """
        Execute the iterative interaction loop on a software engineering task.
        
        Args:
            task: Task instance, instruction string, or task dict.
            
        Returns:
            AgentResult detailing whether task was submitted, final status, steps taken,
            trajectory path, and cost/token usage.
        """
        if isinstance(task, str):
            task_obj = Task(task_id="adhoc_task", instruction=task)
        elif isinstance(task, dict):
            task_obj = Task(**task)
        else:
            task_obj = task

        history = AgentHistory(
            system_prompt=self.system_prompt,
            task=task_obj,
            max_turns=self.config.max_history_turns,
            max_observation_chars=self.config.max_observation_chars,
        )

        steps_taken = 0
        consecutive_malformed = 0
        total_tokens = 0
        total_cost_usd: Optional[float] = None
        trajectory_file = self.trajectory_logger.get_trajectory_path(task_obj.task_id)

        while steps_taken < self.config.max_steps:
            steps_taken += 1
            messages = history.get_messages()

            # 1. LLM Generation
            try:
                llm_response: LLMResponse = self.llm.generate(messages)
            except Exception as e:
                err_msg = f"LLM generation failed at step {steps_taken}: {e}"
                logger.error(err_msg)
                self.trajectory_logger.log_step(
                    task_id=task_obj.task_id,
                    step=steps_taken,
                    model=self.llm.get_model_name(),
                    action_type="error",
                    action_args={},
                    declared_scope={},
                    observation_success=False,
                    observation_output="",
                    observation_error=err_msg,
                    is_terminal=True,
                    termination_reason="LLM_EXCEPTION",
                )
                return AgentResult(
                    task_id=task_obj.task_id,
                    submitted=False,
                    status="ERROR",
                    steps_taken=steps_taken,
                    error=err_msg,
                    trajectory_path=trajectory_file,
                    total_tokens=total_tokens,
                    total_cost_usd=total_cost_usd,
                )

            # Accumulate usage and cost
            if llm_response.usage:
                total_tokens += llm_response.usage.total_tokens
            if llm_response.cost_usd is not None:
                total_cost_usd = (total_cost_usd or 0.0) + llm_response.cost_usd

            raw_text = llm_response.content
            history.add_assistant_action(raw_text)

            # 2. Parse and Validate Action
            try:
                action = parse_action(raw_text)
                consecutive_malformed = 0  # Reset counter upon valid action
            except ActionParseError as ape:
                consecutive_malformed += 1
                parse_err = str(ape)
                logger.warning(
                    f"Action parse error at step {steps_taken} "
                    f"({consecutive_malformed}/{self.config.max_consecutive_malformed_actions}): {parse_err}"
                )

                self.trajectory_logger.log_step(
                    task_id=task_obj.task_id,
                    step=steps_taken,
                    model=llm_response.model,
                    action_type="malformed",
                    action_args={"raw_content": raw_text},
                    declared_scope={},
                    observation_success=False,
                    observation_output="",
                    observation_error=parse_err,
                    token_usage=llm_response.usage.model_dump() if llm_response.usage else None,
                    cost_usd=llm_response.cost_usd,
                    is_terminal=(consecutive_malformed >= self.config.max_consecutive_malformed_actions),
                    termination_reason="MAX_MALFORMED_EXCEEDED" if consecutive_malformed >= self.config.max_consecutive_malformed_actions else None,
                )

                if consecutive_malformed >= self.config.max_consecutive_malformed_actions:
                    return AgentResult(
                        task_id=task_obj.task_id,
                        submitted=False,
                        status="MAX_MALFORMED_EXCEEDED",
                        steps_taken=steps_taken,
                        error=f"Exceeded maximum consecutive malformed actions limit ({self.config.max_consecutive_malformed_actions}). Last error: {parse_err}",
                        trajectory_path=trajectory_file,
                        total_tokens=total_tokens,
                        total_cost_usd=total_cost_usd,
                    )

                # Feed error back into conversation so model can self-correct next turn
                history.add_error_feedback(parse_err)
                continue

            # 3. Handle Explicit Submit Action
            if action.action_type == "submit":
                summary = action.args.get("summary", "Task submitted.")
                obs = self.aci_dispatcher.dispatch(action, self.runtime)

                self.trajectory_logger.log_step(
                    task_id=task_obj.task_id,
                    step=steps_taken,
                    model=llm_response.model,
                    action_type="submit",
                    action_args=action.args,
                    declared_scope=action.declared_scope.model_dump(),
                    observation_success=obs.success,
                    observation_output=obs.output,
                    observation_error=obs.error,
                    token_usage=llm_response.usage.model_dump() if llm_response.usage else None,
                    cost_usd=llm_response.cost_usd,
                    is_terminal=True,
                    termination_reason="SUBMITTED",
                )

                return AgentResult(
                    task_id=task_obj.task_id,
                    submitted=True,
                    status="SUBMITTED",
                    steps_taken=steps_taken,
                    submission=summary,
                    error=None,
                    trajectory_path=trajectory_file,
                    total_tokens=total_tokens,
                    total_cost_usd=total_cost_usd,
                )

            # 4. Execute Action via ACI and Runtime
            try:
                obs = self.aci_dispatcher.dispatch(action, self.runtime)
            except Exception as e:
                obs = Observation(
                    success=False,
                    output="",
                    error=f"Execution exception during {action.action_type}: {e}"
                )

            # 5. Record Observation in History
            history.add_observation(obs)

            # 6. Log Trajectory Step
            self.trajectory_logger.log_step(
                task_id=task_obj.task_id,
                step=steps_taken,
                model=llm_response.model,
                action_type=action.action_type,
                action_args=action.args,
                declared_scope=action.declared_scope.model_dump(),
                observation_success=obs.success,
                observation_output=obs.output,
                observation_error=obs.error,
                token_usage=llm_response.usage.model_dump() if llm_response.usage else None,
                cost_usd=llm_response.cost_usd,
                is_terminal=False,
                termination_reason=None,
            )

        # Budget exhausted: Max steps reached without submission
        self.trajectory_logger.log_step(
            task_id=task_obj.task_id,
            step=steps_taken,
            model=self.llm.get_model_name(),
            action_type="budget_exhausted",
            action_args={},
            declared_scope={},
            observation_success=False,
            observation_output="Maximum step budget reached without submission.",
            is_terminal=True,
            termination_reason="MAX_STEPS_EXCEEDED",
        )

        return AgentResult(
            task_id=task_obj.task_id,
            submitted=False,
            status="MAX_STEPS_EXCEEDED",
            steps_taken=steps_taken,
            submission=None,
            error=f"Agent exceeded maximum step limit ({self.config.max_steps}) without submitting.",
            trajectory_path=trajectory_file,
            total_tokens=total_tokens,
            total_cost_usd=total_cost_usd,
        )
