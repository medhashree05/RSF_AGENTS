# Implementation Deviations & SWE-agent Comparison

This document records the relationship between our baseline implementation and the reference paper:

> **SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering**  
> NeurIPS 2024, by Yang et al.

We do **not** claim an exact reproduction of the full SWE-agent open-source codebase. Instead, this is a clean, understandable, modular implementation capturing its essential design principles while tailoring interfaces to our research on **anti-pattern detection and autonomous reversibility**.

---

## 1. What Follows SWE-agent's Published Design

| Architectural Concept | SWE-agent (Yang et al. 2024) | Our Baseline Implementation |
| :--- | :--- | :--- |
| **Agent-Computer Interface (ACI)** | Uses custom commands rather than raw shell to view, search, and edit code. | Implements dedicated `search`, `read_file`, `edit_file`, and `run_shell` actions. |
| **Line-Numbered Viewing** | Displays files with 1-indexed line numbers (`open <file> <line>`). | `read_file` returns lines prefixed with `1: ...`, `2: ...` and supports line range slicing. |
| **Surgical Editing** | Avoids rewriting entire files; replaces specific lines or substrings. | `edit_file` supports exact substring replacement (`old_str`/`new_str`) and line-slice replacement. |
| **Bounded Observations** | Enforces hard limits on command output lines/characters to avoid context exhaustion. | Hard limits with explicit truncation annotations (`... [Output truncated: ...] ...`) across all ACI tools. |
| **Explicit Submission** | Has a dedicated `submit` action signaling completion. | `submit` action explicitly terminates the loop without declaring benchmark correctness. |
| **Trajectory Logging** | Dumps structured trajectory files for benchmark evaluation and audit. | Emits full JSONL trajectory records containing steps, actions, observations, tokens, and metadata. |
| **Environment Separation** | Runs inside isolated runtime containers rather than on the host. | Agent layer interacts strictly with a `Runtime` abstraction; host filesystem execution is prohibited. |

---

## 2. Intentional Simplifications and Deviations

### A. Unified JSON Action Format vs. Custom Terminal Command Syntax
- **SWE-agent Paper**: The original SWE-agent parses custom command lines resembling bash syntax (e.g. `open src/main.py 10`, `edit 15:20`, `scroll_up`, `search "foo"`).
- **Our Implementation**: We use a structured JSON action object (`{"action": "...", "args": {...}, "declared_scope": {...}}`).
- **Rationale**: 
  1. Contemporary instruction-tuned LLMs handle JSON schema output reliably across providers without custom lexers.
  2. A structured JSON format allows seamless embedding of the `declared_scope` object, which is required by our safety control loop.
  3. Eliminates syntax ambiguities when multi-line code snippets or special characters are passed to edit or shell tools.

### B. Minimal Tool Catalogue vs. Full Window Viewer (Scroll/Goto)
- **SWE-agent Paper**: Features stateful viewing commands such as `scroll_up`, `scroll_down`, `goto <line>`, and `create`.
- **Our Implementation**: Employs a stateless, slice-based `read_file(path, start_line, end_line)` tool and multi-mode `edit_file`.
- **Rationale**:
  1. Stateless operations simplify testing and reproducibility across turns.
  2. Reduces agent state desynchronization when rollbacks occur in the Docker container.
  3. Keeps the ACI minimal and inspectable for research ablations.

### C. Addition of Declared Scope Contract
- **SWE-agent Paper**: Does not require agents to declare intent or expected side-effects prior to command execution.
- **Our Implementation**: Every action emitted by the agent must declare its `declared_scope` (`write`, `read`, `network`).
- **Rationale**:
  1. This is the central research mechanism of our B.Tech project: testing whether observing actual system effects detects deviations from declared intent.
  2. The declared scope is treated as unverified agent intent and handed off to Member 3 (Auditor) and Member 4 (Scope Comparator).

### D. Zero-Dependency Mock Runtime and Offline LLM Provider
- **SWE-agent Paper**: Relies on live Docker daemon instances and external model APIs (OpenAI, Anthropic).
- **Our Implementation**: Supplies `FakeRuntime` and `MockLLMProvider` alongside real runtime interfaces.
- **Rationale**:
  1. Enables deterministic, zero-dependency unit tests running in under 5 seconds without Docker or network access.
  2. Prevents costly API charges and token consumption during rapid iterative development.

---

## 3. Aspects Requiring Verification Against Full Paper Evaluation

If the team later chooses to benchmark on the full SWE-bench platform (rather than our localized BTP test scenarios):
1. **Context Window Compression**: Check if SWE-agent's dynamic prompt compression / system message formatting is needed for repository-scale repos.
2. **Windowed Scrolling Dynamics**: Verify whether certain complex SWE-bench tasks perform better with active window scrolling (`scroll_down`) vs. line-range slicing.
3. **Model Pricing Tables**: When calculating inference cost for benchmark metrics (Pass@1, Pass@k), integrate a dynamic pricing lookup table rather than recording `cost_usd=None`.
