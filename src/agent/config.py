from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """
    Configuration parameters for the SWE-agent-style CodingAgent.
    """
    model_name: str = Field(default="mock-model", description="Identifier of LLM to use")
    max_steps: int = Field(default=30, description="Maximum number of turns before terminating")
    max_consecutive_malformed_actions: int = Field(
        default=3,
        description="Maximum consecutive action parse errors allowed before terminating"
    )
    request_timeout: float = Field(default=60.0, description="Timeout in seconds for LLM and tool calls")
    max_observation_chars: int = Field(default=8000, description="Maximum characters per tool observation")
    max_history_turns: int = Field(default=50, description="Maximum turns retained in conversation window")
    trajectory_dir: str = Field(default="logs/trajectories", description="Directory to store trajectory JSONL files")
    experiment_id: str = Field(default="default_experiment", description="Tag/ID for trajectory experiment grouping")
