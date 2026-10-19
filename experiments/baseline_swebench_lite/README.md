# SWE-bench Lite Baseline Experiment (Experiment A)

## Overview
This directory contains the experimental artifacts, configuration, declared scope specifications, execution logs, and generated patches for **Experiment A (Baseline)**.

The objective is to measure an autonomous software engineering agent's natural problem-solving performance, error modes, and scope compliance without active safety enforcement, transactional rollback, or policy limitation.

---

## Directory Layout
```text
experiments/baseline_swebench_lite/
├── README.md                           # Setup and reproduction guide
├── common_scope_framework.md           # Formal, universal declared-scope taxonomy & specification
├── common_declared_scope_schema.json   # JSON Schema for task scope definitions
├── experiment_config.json              # Frozen model, hyperparameter, and runtime settings
├── selected_instances.json             # 25 fixed SWE-bench Lite pilot instances across 6 domains
├── run_pilot.py                        # Autonomous baseline experiment runner
├── declared_scopes/                    # Predefined task scopes (1 per task)
├── logs/
│   └── trajectories/                   # Step-by-step agent ReAct interaction JSONL logs
├── patches/                            # Generated git diff patches
└── results.jsonl                       # Structured per-task records with post-hoc scope audits
```

---

## Execution Instructions

### 1. Prerequisites
- Docker active and running (`docker ps`).
- Sandbox image built: `docker build -t btp-sandbox:latest .`
- `GEMINI_API_KEY` defined in `.env` or exported in shell.

### 2. Run Smoke Test (Single Task)
Execute the smoke test on `pallets__flask-4045`:
```powershell
python experiments/baseline_swebench_lite/run_pilot.py --instance-id pallets__flask-4045
```

### 3. Run Full 25-Task Pilot
```powershell
python experiments/baseline_swebench_lite/run_pilot.py
```
Or execute a bounded subset:
```powershell
python experiments/baseline_swebench_lite/run_pilot.py --max-tasks 5
```
