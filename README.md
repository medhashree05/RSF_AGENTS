# Autonomous Reversibility Prototype: Baseline Coding Agent & Transactional Sandbox

[![Tests](https://img.shields.io/badge/pytest-68%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)]()
[![Docker](https://img.shields.io/badge/docker-containerized%20sandbox-orange.svg)]()
[![SWE--agent](https://img.shields.io/badge/architecture-SWE--agent%20NeurIPS%202024-purple.svg)]()

An end-to-end framework implementing a **SWE-agent-style baseline coding agent** and an isolated **Docker transactional sandbox** for detecting and reversing anti-patterns or unauthorized workspace modifications in LLM-assisted code generation.

---

## 📐 System Architecture

The project is structured into two complementary layers:

### 1. Baseline Layer (Agent & Runtime Boundary)
Inspired by **SWE-agent (Yang et al., NeurIPS 2024)**:
* **Coding Agent (`src/agent/agent.py`)**: Turn-based ReAct loop managing prompt history, action parsing, budget enforcement, and guaranteed cleanup via `try ... finally: runtime.stop()`.
* **Agent-Computer Interface (ACI) (`src/agent/aci/`)**: Minimal, bounded operations (`search`, `read_file`, `edit_file`, `run_shell`, `submit`).
* **Runtime Abstraction (`src/agent/runtime.py`)**: Abstract protocol decoupling the agent from the execution environment.
* **Docker Runtime (`src/runtime/docker_runtime.py`)**: Sandboxed container runtime that copies local repositories into `/workspace`, runs tests, computes git diffs, and isolates execution from the host.
* **Mock Runtime (`src/agent/runtime.py:FakeRuntime`)**: Zero-dependency, in-memory virtual runtime for fast, deterministic offline testing.

### 2. Safety Control Loop (Proposed Extension)
* **Policy Limiter (`src/policy.py`)**: Static gatekeeper validating file paths and rejecting dangerous commands prior to execution.
* **Transactional Sandbox (`src/sandbox.py`)**: Executes tool calls in Docker with state promotion (`commit_state`) and state discard (`rollback_state`).
* **Ground-Truth Auditor (`src/auditor.py`)**: Inspects container changes via `docker diff` and syscall tracking via `strace` log parsing.
* **Scope Comparator (`src/comparator.py`)**: Compares agent-declared scope against observed effects to detect undeclared file writes, unexpected reads, or unauthorized network calls.
* **Orchestrator & Feedback (`src/orchestrator.py`, `src/feedback.py`)**: Coordinates execution, triggering commits on match or rollbacks on violations, and returning structured feedback to the agent.

---

## 🚀 Quickstart & CLI Usage

### 1. Build the Docker Sandbox Image
Before running with Docker container isolation, build the local sandbox image:

```bash
docker build -t btp-sandbox:latest .
```

### 2. Run the Baseline Coding Agent (`run_agent.py`)

#### A. In Docker Sandbox (Isolated Container Mode)
Runs the agent against the target repository inside a real Docker container, executing tests and producing a `git diff`:

```bash
python run_agent.py --repo ./fixtures/sample_repo --task ./tasks/task_01.json --runtime docker
```

#### B. In Offline Virtual Mode (Zero Docker / No API Key Required)
Runs completely offline using `MockRuntime` and `MockLLMProvider` in under 1 second:

```bash
python run_agent.py --repo ./fixtures/sample_repo --task ./tasks/task_01.json --runtime mock
```

#### C. With Live LLM Provider (OpenAI / OpenRouter / Ollama / vLLM)
Export your API key:

```bash
# On Linux/macOS
export OPENAI_API_KEY="your-api-key"

# On Windows PowerShell
$env:OPENAI_API_KEY="your-api-key"
```

Execute with `--provider openai`:

```bash
python run_agent.py \
  --repo ./fixtures/sample_repo \
  --task ./tasks/task_01.json \
  --runtime docker \
  --provider openai \
  --model gpt-4o-mini
```

---

## 🧪 Running Automated Tests

Run the full test suite (all 68 tests across unit, mock, and live Docker suites):

```bash
pytest
```

To run offline unit tests only (without requiring Docker):

```bash
pytest -m "not docker"
```

---

## 📁 Directory Structure

```text
├── Dockerfile                   # Ubuntu 22.04 base sandbox image (git, strace, python3, pytest)
├── pyproject.toml               # Project dependencies and tool settings
├── requirements.txt             # Core dependencies (pydantic, docker, pytest)
├── run_agent.py                 # CLI entrypoint for baseline agent execution
├── tasks/
│   └── task_01.json             # Sample coding task specification
├── fixtures/
│   └── sample_repo/             # Disposable repository fixture with buggy code and tests
├── docs/                        # Architecture and contract documentation
│   ├── architecture.md          # Baseline component architecture and ReAct control flow
│   ├── implementation_plan.md   # Implementation plan and gap analysis
│   ├── integration_contract.md  # Docker runtime integration contract
│   ├── agent_architecture.md    # SWE-agent ACI detailed specification
│   └── implementation_deviations.md # Comparison against published SWE-agent paper
├── src/
│   ├── agent/                   # Baseline Coding Agent & ACI
│   │   ├── aci/                 # ACI commands (search, read_file, edit_file, run_shell, submit)
│   │   ├── agent.py             # Main CodingAgent interaction loop & lifecycle
│   │   ├── config.py            # Agent configuration models
│   │   ├── history.py           # Bounded conversation history manager
│   │   ├── llm.py               # LLM provider abstraction & OpenAILikeProvider
│   │   ├── logger.py            # Trajectory JSONL logger & secret redaction
│   │   ├── models.py            # Action, Observation, Task, AgentResult
│   │   ├── parser.py            # Action JSON parser with error recovery
│   │   ├── prompts/             # Agent system prompt
│   │   └── runtime.py           # Runtime protocol & MockRuntime / FakeRuntime
│   ├── runtime/
│   │   └── docker_runtime.py    # DockerRuntime implementing Runtime protocol
│   ├── auditor.py               # Ground-Truth Auditor (docker diff & strace)
│   ├── comparator.py            # Declared scope vs observed effects comparator
│   ├── feedback.py              # Feedback generator for agent self-correction
│   ├── logger.py                # Episode logger for safety audits
│   ├── mock_agent.py            # Deterministic agent scenarios for safety benchmarks
│   ├── models.py                # Core data models (ToolCall, DeclaredScope, EpisodeLog)
│   ├── orchestrator.py          # Central safety loop orchestrator
│   ├── policy.py                # Static policy limiter gate
│   └── sandbox.py               # Docker transactional sandbox with commit/rollback
└── tests/                       # Unit and end-to-end integration tests (68 tests)
```

---

## 📚 Technical Documentation

* [Baseline Architecture Documentation](docs/architecture.md)
* [Implementation Plan & Phasing](docs/implementation_plan.md)
* [Docker Runtime Integration Contract](docs/integration_contract.md)
* [SWE-agent Comparison & Deviations](docs/implementation_deviations.md)
