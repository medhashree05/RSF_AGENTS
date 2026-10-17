#!/usr/bin/env python3
"""
CLI entry point for running the SWE-agent baseline coding agent.

Usage Examples:
    # 1. Run offline with Mock LLM and in-memory runtime:
    python run_agent.py --repo ./fixtures/sample_repo --task ./tasks/task_01.json

    # 2. Run with live OpenAI-compatible LLM provider:
    export OPENAI_API_KEY="your-api-key"
    python run_agent.py --repo ./fixtures/sample_repo --task ./tasks/task_01.json --provider openai --model gpt-4o-mini
"""

import argparse
import json
import os
import sys
from typing import Optional

from src.agent.agent import CodingAgent
from src.agent.config import AgentConfig
from src.agent.llm import LLMProvider, MockLLMProvider, OpenAILikeProvider
from src.agent.models import Task, AgentResult
from src.agent.runtime import FakeRuntime, MockRuntime


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SWE-agent-style baseline coding agent runner."
    )
    parser.add_argument(
        "--repo",
        type=str,
        default="./fixtures/sample_repo",
        help="Path to target repository directory."
    )
    parser.add_argument(
        "--task",
        type=str,
        default="./tasks/task_01.json",
        help="Path to JSON task file or raw instruction string."
    )
    parser.add_argument(
        "--runtime",
        type=str,
        choices=["docker", "mock"],
        default="docker",
        help="Runtime environment: 'docker' for isolated container sandbox, 'mock' for in-memory runtime."
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=["mock", "openai"],
        default="mock",
        help="LLM provider: 'mock' for deterministic offline run, 'openai' for live API."
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model identifier (e.g. 'gpt-4o-mini'). Defaults to provider default."
    )
    parser.add_argument(
        "--api-key-env",
        type=str,
        default="OPENAI_API_KEY",
        help="Environment variable name for provider API key."
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="https://api.openai.com/v1/chat/completions",
        help="Base URL for OpenAI-compatible completions API."
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=15,
        help="Maximum agent interaction steps allowed before termination."
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default="logs/trajectories",
        help="Directory to write trajectory JSONL log files."
    )
    parser.add_argument(
        "--experiment-id",
        type=str,
        default="baseline_eval",
        help="Experiment identifier tag for trajectory records."
    )
    return parser.parse_args()


def load_task(task_input: str) -> Task:
    """Load task from JSON file or parse as direct instruction string."""
    if os.path.isfile(task_input):
        with open(task_input, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Task(**data)
    else:
        return Task(
            task_id="adhoc_task",
            instruction=task_input
        )


def build_llm_provider(args: argparse.Namespace) -> LLMProvider:
    """Instantiate configured LLM provider with appropriate credentials."""
    if args.provider == "mock":
        model_name = args.model or "mock-swe-agent-v1"
        # Scripted deterministic sequence solving task_01.json if run against sample_repo
        scripted_steps = [
            # Step 1: Read calculator.py
            json.dumps({
                "action": "read_file",
                "args": {"path": "src/calculator.py", "start_line": 1, "end_line": 20}
            }),
            # Step 2: Surgically edit calculator.py to raise ValueError on b == 0
            json.dumps({
                "action": "edit_file",
                "args": {
                    "path": "src/calculator.py",
                    "old_str": "    # BUG: Raises ZeroDivisionError instead of ValueError(\"Cannot divide by zero\")\n    return a / b",
                    "new_str": "    if b == 0:\n        raise ValueError(\"Cannot divide by zero\")\n    return a / b"
                }
            }),
            # Step 3: Run test suite via shell
            json.dumps({
                "action": "run_shell",
                "args": {"command": "pytest tests/test_calculator.py"}
            }),
            # Step 4: Submit task
            json.dumps({
                "action": "submit",
                "args": {"summary": "Fixed divide(a, b) in src/calculator.py to raise ValueError('Cannot divide by zero') on zero division."}
            })
        ]
        return MockLLMProvider(responses=scripted_steps, model_name=model_name)

    elif args.provider == "openai":
        model_name = args.model or "gpt-4o-mini"
        return OpenAILikeProvider(
            model_name=model_name,
            api_key_env_var=args.api_key_env,
            base_url=args.base_url
        )
    else:
        raise ValueError(f"Unsupported provider: {args.provider}")


def main():
    args = parse_arguments()

    print("=" * 60)
    print("  SWE-Agent Baseline Coding Agent Runner")
    print("=" * 60)
    print(f"Target Repository : {args.repo}")
    print(f"Task Specification: {args.task}")
    print(f"LLM Provider      : {args.provider}")
    print(f"Max Steps         : {args.max_steps}")
    print(f"Trajectory Dir    : {args.log_dir}")
    print("-" * 60)

    # 1. Load Task
    try:
        task = load_task(args.task)
        print(f"Loaded Task ID    : {task.task_id}")
        print(f"Instruction       : {task.instruction[:80]}...")
    except Exception as e:
        print(f"Error loading task from '{args.task}': {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Setup LLM Provider
    try:
        llm = build_llm_provider(args)
        print(f"LLM Model         : {llm.get_model_name()}")
    except Exception as e:
        print(f"Error initializing LLM provider: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. Setup Runtime
    if args.runtime == "docker":
        from src.runtime.docker_runtime import DockerRuntime
        print("Runtime Mode      : Isolated Docker Container (btp-sandbox:latest)")
        runtime = DockerRuntime(image_name="btp-sandbox:latest")
    else:
        print("Runtime Mode      : In-Memory Virtual Runtime (MockRuntime)")
        runtime = FakeRuntime()

    # 4. Configure & Initialize Agent
    config = AgentConfig(
        max_steps=args.max_steps,
        trajectory_dir=args.log_dir,
        experiment_id=args.experiment_id
    )
    agent = CodingAgent(llm=llm, runtime=runtime, config=config)

    # 5. Execute Agent Loop
    print("\nStarting agent interaction loop...")
    result: AgentResult = agent.run(task, repo_path=args.repo)

    # 6. Report Execution Outcomes
    print("\n" + "=" * 60)
    print("  Agent Run Complete: Execution Summary")
    print("=" * 60)
    print(f"Task ID         : {result.task_id}")
    print(f"Status          : {result.status}")
    print(f"Submitted       : {result.submitted}")
    print(f"Steps Taken     : {result.steps_taken}")
    if result.submission:
        print(f"Submission Note : {result.submission}")
    if result.error:
        print(f"Error Details   : {result.error}")
    print(f"Trajectory Log  : {result.trajectory_path}")
    print(f"Tokens Used     : {result.total_tokens or 'N/A'}")
    print(f"Cleaned Up      : {result.runtime_cleaned_up}")

    if result.final_diff:
        print("\n--- Final Repository Diff ---")
        print(result.final_diff.strip())
    else:
        print("\nFinal Repository Diff: [No changes recorded]")

    if result.test_result:
        print("\n--- Final Test Execution ---")
        exit_code = result.test_result.get("exit_code")
        print(f"Test Exit Code  : {exit_code}")
        stdout = result.test_result.get("stdout", "").strip()
        if stdout:
            print(f"Test Output     :\n{stdout}")

    print("=" * 60)

    # Exit code indicates task submission status
    sys.exit(0 if result.submitted else 1)


if __name__ == "__main__":
    main()
