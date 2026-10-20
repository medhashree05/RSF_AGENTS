# SWE-bench Lite Baseline Benchmark (Complete 300-Task Study)

## Overview
This directory contains the experimental artifacts, declared scope specifications, execution logs, generated patches, and formal audit reports for the **complete 300-task SWE-bench Lite baseline benchmark**.

The objective of this benchmark is to measure an autonomous coding agent's natural problem-solving behavior and safety boundary compliance without active safety enforcement (Plan B disabled), providing rigorous empirical proof of safety boundary violations in autonomous software engineering agents.

---

## Benchmark Results At a Glance

* **Total Benchmark Instances Evaluated**: **300 / 300 (100.0%)**
* **Clean In-Scope Operations**: **274 tasks (91.33%)**
* **Scope Boundary Violations**: **26 tasks (8.67%)**
  * **Critical Build/Packaging Manifest Tampering**: **4 instances** (`setup.py`, `pyproject.toml`)
  * **Unannounced Core Architectural Mutations**: **22 instances** (modifications to core pipelines, compilers, and ORM internals)

---

## Directory Layout
```text
experiments/baseline_swebench_lite/
├── README.md                           # Directory guide and benchmark overview
├── FULL_300_BENCHMARK_REPORT.md        # Comprehensive capstone benchmark report
├── breach_report.md                    # Tabular inventory of all 26 scope breaches
├── LIVE_STATUS.md                      # Final completion status
├── BTP_SCOPE_BREACH_PROOF_PACK.zip     # Master proof pack containing all patches & audits (884 KB)
├── results.jsonl                       # Full 300-task structured results dataset with scope audits
├── run_pilot.py                        # Unified benchmark execution and auditing script
├── experiment_config.json              # Model, hyperparameter, and runtime settings
├── common_scope_framework.md           # Formal declared-scope taxonomy and rules
├── common_declared_scope_schema.json   # JSON Schema for task scope definitions
├── selected_instances.json             # Dataset instances definition
├── declared_scopes/                    # Predefined task scopes (300 JSON files, 1 per task)
├── patches/                            # Generated git diff patches (300 patch files)
└── reports/                            # Comprehensive research reports and case studies
    ├── README.md                       # Reports index
    ├── FULL_300_BENCHMARK_REPORT.md    # Master benchmark report
    ├── FULL_300_BREACH_LOG.md          # 300-task breach audit table
    ├── FORENSIC_BREACH_EVIDENCE.md     # Deep-dive forensic case studies with diffs
    ├── PILOT_60_BENCHMARK_REPORT.md    # 60-task pilot evaluation report
    └── batch_reports/                  # Intermediate batch audit records
```

---

## Reproduction & Verification

### Run a Single Verification Task
```bash
python experiments/baseline_swebench_lite/run_pilot.py --instance-id pallets__flask-4045
```

### Run with Local Ollama
```bash
python experiments/baseline_swebench_lite/run_pilot.py --provider ollama --model llama3.2:3b --max-tasks 5
```
