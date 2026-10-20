# Benchmark Reports Directory (SWE-bench Lite Safety Audit)

This directory contains the formal experimental findings and safety boundary breach documentation for the **RSF_AGENTS** research project evaluating autonomous coding agents across the complete **300-task SWE-bench Lite benchmark**.

---

## Document Index

1. **[EXPERIMENT_A_METRICS_REPORT.md](file:///c:/Users/shali/btp%20project/RSF_AGENTS/experiments/baseline_swebench_lite/reports/EXPERIMENT_A_METRICS_REPORT.md)**  
   *Specialized Metric Calculations for Experiment A.* Comprehensive mathematical breakdown of all metrics specific to the baseline evaluation: Scope Compliance Rate (91.33%), Residual Threat Rate (100%), Blast Radius (13.0 files/breach), Codebase Volatility (88k LOC altered), Turnaround Latency (335s), and Failure Mode Taxonomies.

2. **[FULL_300_BENCHMARK_REPORT.md](file:///c:/Users/shali/btp%20project/RSF_AGENTS/experiments/baseline_swebench_lite/reports/FULL_300_BENCHMARK_REPORT.md)**  
   *The primary benchmark report.* High-level overview of all 300 tasks, methodology, statistical breach frequency (8.67%), packaging vs unannounced mutations, and defense implications for RSF Plan B.

3. **[FULL_300_BREACH_LOG.md](file:///c:/Users/shali/btp%20project/RSF_AGENTS/experiments/baseline_swebench_lite/reports/FULL_300_BREACH_LOG.md)**  
   Complete tabular inventory of every single task that violated scope boundaries across the full 300 benchmark instances, including modified files and severity levels.

4. **[FORENSIC_BREACH_EVIDENCE.md](file:///c:/Users/shali/btp%20project/RSF_AGENTS/experiments/baseline_swebench_lite/reports/FORENSIC_BREACH_EVIDENCE.md)**  
   Exhaustive forensic case studies detailing all 26 safety boundary violations, categorized by attack vector and violation mechanism with unified git diffs.

5. **`batch_reports/`**  
   Contains intermediate batch run audit logs (Batches 03, 04, 05, 06, 10).
