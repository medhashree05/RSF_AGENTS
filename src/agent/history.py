import logging
from typing import Dict, List, Optional
from src.agent.models import Action, Observation, Task

logger = logging.getLogger(__name__)


class AgentHistory:
    """
    Manages the message sequence exchanged between agent and LLM.
    
    Preserves task instruction, previous actions, and observations.
    Implements a bounded window strategy to manage context size while
    never silently truncating evidence (always annotating and logging truncations).
    """
    def __init__(
        self,
        system_prompt: str,
        task: Task,
        max_turns: int = 50,
        max_observation_chars: int = 10000,
    ):
        self.system_prompt = system_prompt
        self.task = task
        self.max_turns = max_turns
        self.max_observation_chars = max_observation_chars
        self.messages: List[Dict[str, str]] = []

        # Initialize conversation with system prompt and task description
        self.messages.append({"role": "system", "content": self.system_prompt})

        user_content = f"# TASK ID: {self.task.task_id}\n\n## INSTRUCTION:\n{self.task.instruction}"
        if self.task.context:
            user_content += f"\n\n## CONTEXT / NOTES:\n{self.task.context}"
        self.messages.append({"role": "user", "content": user_content})

    def add_assistant_action(self, raw_content: str):
        """Append the assistant's action response to conversation history."""
        self.messages.append({"role": "assistant", "content": raw_content})

    def add_observation(self, observation: Observation):
        """
        Append an environment observation to conversation history as a user role message.
        Enforces maximum observation character limits and logs when truncation occurs.
        """
        obs_text = observation.to_display_text(max_chars=self.max_observation_chars)
        if len(observation.output) > self.max_observation_chars:
            logger.info(
                f"Observation truncated: original length was {len(observation.output)} chars, "
                f"capped at {self.max_observation_chars}."
            )
        self.messages.append({"role": "user", "content": obs_text})
        self._enforce_history_window()

    def add_error_feedback(self, error_message: str):
        """Append a parsing or execution error notice as feedback for recovery."""
        feedback = f"[SYSTEM FEEDBACK: ACTION ERROR]\n{error_message}\nPlease correct your action and try again."
        self.messages.append({"role": "user", "content": feedback})
        self._enforce_history_window()

    def _enforce_history_window(self):
        """
        Enforce max_turns window to prevent context overflow.
        Always preserves initial system prompt (index 0) and task prompt (index 1).
        Prunes oldest intermediate turns when history exceeds limit, logging the event.
        """
        # 1 turn is 1 assistant + 1 user message (2 messages)
        # Total messages = 2 (initial) + max_turns * 2
        max_messages = 2 + (self.max_turns * 2)
        if len(self.messages) > max_messages:
            excess = len(self.messages) - max_messages
            # Prune in pairs (assistant + user) from index 2 onwards
            prune_count = excess + (excess % 2)
            removed = self.messages[2:2 + prune_count]
            self.messages = self.messages[:2] + self.messages[2 + prune_count:]
            logger.warning(
                f"History window exceeded: pruned {len(removed)} intermediate message(s) "
                f"to maintain maximum turn budget ({self.max_turns} turns)."
            )

    def get_messages(self) -> List[Dict[str, str]]:
        """Return the current list of messages formatted for LLM consumption."""
        return list(self.messages)
