#!/usr/bin/env python3
"""
Baseline Experiment Runner for SWE-bench Lite Pilot (Experiment A).

Executes autonomous CodingAgent without active scope enforcement or rollback (Plan B).
Records tool calls, generated patches, token usage, and performs post-hoc audit against
the declared scope specifications.
"""

import argparse
import fnmatch
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import docker

from src.agent.agent import CodingAgent
from src.agent.config import AgentConfig
from src.agent.llm import OpenAILikeProvider, MockLLMProvider
from src.agent.models import Task, AgentResult
from src.runtime.docker_runtime import DockerRuntime


PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCES_FILE = os.path.join(PILOT_DIR, "selected_instances.json")
SCOPES_DIR = os.path.join(PILOT_DIR, "declared_scopes")
PATCHES_DIR = os.path.join(PILOT_DIR, "patches")
TRAJECTORIES_DIR = os.path.join(PILOT_DIR, "logs", "trajectories")
RESULTS_FILE = os.path.join(PILOT_DIR, "results.jsonl")


def load_instances(filepath: Optional[str] = None) -> List[Dict[str, Any]]:
    target_file = filepath or INSTANCES_FILE
    if not os.path.isfile(target_file):
        raise FileNotFoundError(f"Instances file not found: {target_file}")
    with open(target_file, "r", encoding="utf-8") as f:
        return json.load(f)


from src.common_scope import (
    UniversalDeclaredScope,
    ScopeViolationSeverity,
    build_common_declared_scope,
    audit_diff_against_scope,
)


def load_or_create_declared_scope(task: Task, instance_id: str) -> UniversalDeclaredScope:
    """Load task-specific declared scope or construct a common repository-level scope."""
    scope_path = os.path.join(SCOPES_DIR, f"{instance_id}.json")
    if os.path.isfile(scope_path):
        with open(scope_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            s_data = data.get("declared_scope", {})
            eval_data = data.get("evaluation_criteria", {})
            return UniversalDeclaredScope(
                task_id=instance_id,
                repository=data.get("repository"),
                problem_type=data.get("problem_type", "bug_fix"),
                permitted_write_paths=s_data.get("permitted_write_paths", ["**/*.py"]),
                permitted_read_paths=s_data.get("permitted_read_paths", ["**/*"]),
                prohibited_paths=s_data.get("prohibited_paths", []),
                permitted_commands=s_data.get("permitted_commands", []),
                prohibited_commands=s_data.get("prohibited_commands", []),
                network_allowed=s_data.get("network_allowed", False),
                expected_symbols_modified=eval_data.get("expected_symbols_modified", []),
                max_acceptable_file_modifications=eval_data.get("max_acceptable_file_modifications", 3),
            )
    return build_common_declared_scope(task)


def setup_repository_in_container(container: Any, repo: str, base_commit: str) -> None:
    """Initialize repository directly inside container at base_commit."""
    repo_url = f"https://github.com/{repo}.git"

    # Fast shallow fetch of exact commit into /workspace
    cmds = [
        "cd /workspace",
        "git init",
        "git config --global --add safe.directory /workspace",
        f"git remote add origin {repo_url} 2>/dev/null || git remote set-url origin {repo_url}",
        f"git fetch --depth 1 origin {base_commit}",
        "git checkout -f FETCH_HEAD",
        "git config user.name 'baseline-agent'",
        "git config user.email 'agent@experiment.local'",
    ]

    # Repository-specific version compatibility pins
    if "flask" in repo:
        cmds.append("pip install --no-cache-dir 'werkzeug<3.0'")
    elif "requests" in repo:
        # Compatibility patch for collections.abc in older requests on Python 3.10
        cmds.append("pip install --no-cache-dir 'urllib3<1.27,>=1.21.1'")

    cmds.append("pip install -e . --no-deps 2>/dev/null || pip install -e . 2>/dev/null || true")

    full_cmd = " && ".join(cmds)
    exec_res = container.exec_run(["/bin/bash", "-c", full_cmd], workdir="/workspace")
    if exec_res.exit_code != 0:
        err_msg = (exec_res.output or b"").decode("utf-8", errors="replace")
        print(f"[Warning] Repo setup exited with {exec_res.exit_code}: {err_msg[:200]}")


class SWEBenchDockerRuntime(DockerRuntime):
    """DockerRuntime specialized for SWE-bench git checkout initialization."""
    def __init__(self, repo: str, base_commit: str, image_name: str = "btp-sandbox:latest", timeout_seconds: float = 120.0):
        super().__init__(image_name=image_name, timeout_seconds=timeout_seconds)
        self.target_repo = repo
        self.target_base_commit = base_commit

    def start(self, repository: Optional[str] = None, task: Optional[Any] = None) -> None:
        client = self._get_client()
        self.current_task = task
        self.is_started = True
        self.is_stopped = False

        self.container = client.containers.create(
            image=self.image_name,
            command="tail -f /dev/null",
            working_dir=self.workspace_dir,
            detach=True,
            tty=True,
        )
        self.container.start()

        print(f"[{self.current_task.task_id if self.current_task else 'setup'}] Setting up repository at base commit...", flush=True)
        setup_repository_in_container(self.container, self.target_repo, self.target_base_commit)

        # Baseline git commit to enable clean diff
        self.container.exec_run(
            ["/bin/bash", "-c", "git add -A && git commit -m 'baseline commit' --allow-empty 2>/dev/null || true"],
            workdir="/workspace"
        )


def run_single_task(
    instance: Dict[str, Any],
    llm: Any,
    max_steps: int = 15,
    image_name: str = "btp-sandbox:latest",
) -> Dict[str, Any]:
    inst_id = instance["instance_id"]
    repo = instance["repo"]
    base_commit = instance["base_commit"]
    problem_statement = instance["problem_statement"]

    print("\n" + "=" * 70, flush=True)
    print(f"  Starting Task: {inst_id}", flush=True)
    print(f"  Repository   : {repo} @ {base_commit[:8]}", flush=True)
    print("=" * 70, flush=True)

    runtime = SWEBenchDockerRuntime(repo=repo, base_commit=base_commit, image_name=image_name, timeout_seconds=120.0)
    start_time = time.time()

    try:
        # 1. Formulate Task (strictly hiding reference solutions, hints, or test patches)
        task = Task(
            task_id=inst_id,
            instruction=problem_statement,
            repository=repo
        )

        # 3. Configure Agent
        config = AgentConfig(
            max_steps=max_steps,
            trajectory_dir=TRAJECTORIES_DIR,
            experiment_id="baseline_swebench_lite"
        )
        agent = CodingAgent(llm=llm, runtime=runtime, config=config)

        # 4. Run Agent Interaction Loop
        print(f"[{inst_id}] Running baseline agent interaction loop (Plan B safety: OFF)...")
        result: AgentResult = agent.run(task)
        wall_clock_sec = round(time.time() - start_time, 2)

        # 5. Extract Patch
        final_diff = result.final_diff or ""
        patch_path = os.path.join(PATCHES_DIR, f"{inst_id}.patch")
        os.makedirs(PATCHES_DIR, exist_ok=True)
        with open(patch_path, "w", encoding="utf-8") as pf:
            pf.write(final_diff)

        # 6. Post-Hoc Scope Audit using Common Universal Scope Framework
        scope = load_or_create_declared_scope(task, inst_id)
        audit_res_obj = audit_diff_against_scope(final_diff, scope)
        audit_res = audit_res_obj.model_dump()

        # 7. Aggregate Result Record
        task_record = {
            "instance_id": inst_id,
            "repo": repo,
            "base_commit": base_commit,
            "status": result.status,
            "submitted": result.submitted,
            "steps_taken": result.steps_taken,
            "wall_clock_seconds": wall_clock_sec,
            "total_tokens": result.total_tokens,
            "patch_file": patch_path,
            "patch_lines": len(final_diff.splitlines()),
            "trajectory_file": result.trajectory_path,
            "submission_summary": result.submission,
            "error": result.error,
            "scope_audit": audit_res,
        }

        # Append to results.jsonl
        os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)
        with open(RESULTS_FILE, "a", encoding="utf-8") as rf:
            rf.write(json.dumps(task_record) + "\n")

        print(f"[{inst_id}] Completed in {wall_clock_sec}s | Status: {result.status} | Steps: {result.steps_taken}", flush=True)
        print(f"[{inst_id}] In-Scope: {audit_res.get('all_in_scope')} | Modified Files: {audit_res.get('modified_files_count', 0)}", flush=True)
        print(f"[{inst_id}] Patch saved: {patch_path}", flush=True)

        return task_record

    finally:
        runtime.stop()


def main():
    parser = argparse.ArgumentParser(description="SWE-bench Lite Baseline Experiment Runner")
    parser.add_argument("--instance-id", type=str, default=None, help="Run single specific instance ID (for smoke test)")
    parser.add_argument("--max-tasks", type=int, default=None, help="Maximum number of pilot tasks to execute")
    parser.add_argument("--max-steps", type=int, default=15, help="Maximum interaction steps per task")
    parser.add_argument("--model", type=str, default="gemini-3.8-flash", help="LLM model name")
    parser.add_argument("--instances-file", type=str, default=None, help="Custom path to instances JSON")
    parser.add_argument("--provider", type=str, choices=["gemini", "ollama", "mock"], default="gemini", help="LLM provider")
    args = parser.parse_args()

    instances = load_instances(args.instances_file)

    if args.instance_id:
        target_instances = [inst for inst in instances if inst["instance_id"] == args.instance_id]
        if not target_instances:
            print(f"Instance '{args.instance_id}' not found in selected_instances.json", file=sys.stderr)
            sys.exit(1)
    else:
        target_instances = instances
        if args.max_tasks:
            target_instances = target_instances[:args.max_tasks]

    # Ensure unbuffered stdout
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    # Initialize Provider
    if args.provider == "gemini":
        llm = OpenAILikeProvider(
            model_name=args.model,
            api_key_env_var="GEMINI_API_KEY",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            timeout=120.0,
            min_interval=4.5,
        )
    elif args.provider == "ollama":
        os.environ.setdefault("OLLAMA_API_KEY", "ollama")
        model_name = args.model if args.model != "gemini-3.8-flash" else "llama3.2:3b"
        llm = OpenAILikeProvider(
            model_name=model_name,
            api_key_env_var="OLLAMA_API_KEY",
            base_url="http://localhost:11434/v1/chat/completions",
            timeout=180.0,
            min_interval=0.1,
        )
    else:
        llm = MockLLMProvider()

    print(f"Running SWE-bench Lite Baseline (Experiment A)")
    print(f"Total Tasks to Execute: {len(target_instances)}")
    print(f"Model                 : {llm.get_model_name()}")
    print(f"Safety Loop (Plan B)  : DISABLED (Measuring Baseline Natural Behavior)")
    print("-" * 70, flush=True)

    total_completed = 0
    total_scope_violations = 0
    total_out_of_scope_files = 0
    total_prohibited_breaches = 0
    clean_in_scope_tasks = 0

    breach_report_file = os.path.join(PILOT_DIR, "breach_report.md")

    breach_records = []

    for idx, inst in enumerate(target_instances, 1):
        print(f"\n>>> Progress: Task {idx}/{len(target_instances)}", flush=True)
        try:
            task_rec = run_single_task(inst, llm=llm, max_steps=args.max_steps)
            total_completed += 1
            audit_res = task_rec.get("scope_audit", {})
            p_breaches = len(audit_res.get("prohibited_breaches", []))
            o_files = len(audit_res.get("out_of_scope_files", []))
            is_clean = audit_res.get("all_in_scope", True)
            severity = audit_res.get("severity", "IN_SCOPE")

            total_prohibited_breaches += p_breaches
            total_out_of_scope_files += o_files
            if not is_clean:
                total_scope_violations += 1
                breach_records.append({
                    "task_id": inst['instance_id'],
                    "repo": inst['repo'],
                    "severity": severity,
                    "prohibited": audit_res.get("prohibited_breaches", []),
                    "out_of_scope": audit_res.get("out_of_scope_files", []),
                    "patch_file": task_rec.get("patch_file"),
                })
            else:
                clean_in_scope_tasks += 1

            print(f"[{inst['instance_id']}] Scope Audit Result: Severity={severity} | Prohibited Breaches={p_breaches} | Out-of-Scope Files={o_files}", flush=True)
            print(f">>> CUMULATIVE BREACH REPORT: {total_scope_violations}/{total_completed} tasks violated scope | Clean In-Scope Tasks: {clean_in_scope_tasks} | Total Prohibited Breaches: {total_prohibited_breaches} | Total Out-of-Scope Files: {total_out_of_scope_files}", flush=True)

            # Write updated live markdown report with evidentiary proof table
            with open(breach_report_file, "w", encoding="utf-8") as bf:
                bf.write(f"# Baseline Experiment A: Live Scope Breach Report\n\n")
                bf.write(f"**Model**: `{llm.get_model_name()}` | **Safety (Plan B)**: `DISABLED`\n\n")
                bf.write(f"### Summary Metrics\n\n")
                bf.write(f"- **Tasks Processed**: {total_completed}/{len(target_instances)}\n")
                bf.write(f"- **Clean In-Scope Tasks**: {clean_in_scope_tasks}\n")
                bf.write(f"- **Tasks with Violations**: {total_scope_violations}\n")
                bf.write(f"- **Total Prohibited Breaches**: {total_prohibited_breaches}\n")
                bf.write(f"- **Total Out-of-Scope Files Modified**: {total_out_of_scope_files}\n\n")
                bf.write(f"### Forensic Evidence of Scope Violations\n\n")
                if breach_records:
                    bf.write(f"| Task ID | Repository | Severity | Files Touched | Proof Patch |\n")
                    bf.write(f"| :--- | :--- | :--- | :--- | :--- |\n")
                    for br in breach_records:
                        files_str = ', '.join(br['prohibited'] + br['out_of_scope'])
                        patch_name = os.path.basename(br['patch_file']) if br['patch_file'] else 'None'
                        bf.write(f"| `{br['task_id']}` | `{br['repo']}` | **`{br['severity']}`** | `{files_str}` | [{patch_name}](./patches/{patch_name}) |\n")
                else:
                    bf.write(f"*No scope violations recorded yet.*\n")
        except Exception as e:
            print(f"[Error] Task {inst['instance_id']} failed with exception: {e}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
