import sys
import json
from src.mock_agent import MockAgent
from src.orchestrator import ReversibilityOrchestrator


def run_demo():
    print("=" * 80)
    print("  AUTONOMOUS REVERSIBILITY OF ANTI-PATTERNS IN LLM-ASSISTED CODE GENERATION")
    print("  Phase 1 End-to-End Safety Control Loop Demonstration")
    print("=" * 80)

    orchestrator = ReversibilityOrchestrator()
    mock_agent = MockAgent()

    # Ensure system state is fresh
    orchestrator.reset_system()

    scenarios = mock_agent.get_all_scenarios()
    results_summary = []

    for item in scenarios:
        sid = item["scenario_id"]
        name = item["name"]
        desc = item["description"]
        tool_call = item["tool_call"]
        expected = item["expected_action"]

        print(f"\n" + "-" * 80)
        print(f"▶ RUNNING {name}")
        print(f"  Description: {desc}")
        print(f"  Tool: {tool_call.tool} | Declared Scope: {tool_call.declared_scope.model_dump()}")
        print("-" * 80)

        episode = orchestrator.run_episode(sid, tool_call)

        print(f"  [1] Policy Decision : {'ALLOWED' if episode.policy_decision.allowed else 'REJECTED'}")
        print(f"      Reason          : {episode.policy_decision.reason}")

        if episode.execution_result:
            print(f"  [2] Execution Result: exit_code={episode.execution_result.exit_code} ({episode.execution_result.duration_ms} ms)")
            if episode.execution_result.stdout.strip():
                print(f"      Stdout          : {episode.execution_result.stdout.strip()}")

        if episode.observed_effects:
            print(f"  [3] Ground-Truth Auditor Effects:")
            print(f"      - Files Created : {episode.observed_effects.files_created}")
            print(f"      - Files Modified: {episode.observed_effects.files_modified}")
            print(f"      - Files Deleted : {episode.observed_effects.files_deleted}")
            print(f"      - Files Read    : {episode.observed_effects.files_read}")

        if episode.comparison_result:
            print(f"  [4] Scope Comparator:")
            print(f"      - Match         : {episode.comparison_result.match}")
            print(f"      - Unexpected    : {episode.comparison_result.unexpected_effects}")

        status_color = "\033[92m" if episode.action_taken == "COMMITTED" else ("\033[91m" if episode.action_taken == "ROLLED_BACK" else "\033[93m")
        reset_color = "\033[0m"

        print(f"\n  [5] FINAL ACTION     : {status_color}{episode.action_taken}{reset_color} (Expected: {expected})")
        print(f"  [6] FEEDBACK TO AGENT:\n\"\"\"\n{episode.feedback}\n\"\"\"")

        status_ok = "PASS" if episode.action_taken == expected else "FAIL"
        results_summary.append({
            "scenario": sid,
            "name": name,
            "action": episode.action_taken,
            "expected": expected,
            "status": status_ok
        })

    print("\n" + "=" * 80)
    print("  PHASE 1 DEMO EXECUTION SUMMARY")
    print("=" * 80)
    print(f"{'SCENARIO':<15} | {'ACTION TAKEN':<15} | {'EXPECTED':<15} | {'STATUS'}")
    print("-" * 65)
    for r in results_summary:
        print(f"{r['scenario']:<15} | {r['action']:<15} | {r['expected']:<15} | {r['status']}")
    print("=" * 80)
    print(f"\nStructured log file appended to logs/episodes.jsonl")


if __name__ == "__main__":
    run_demo()
