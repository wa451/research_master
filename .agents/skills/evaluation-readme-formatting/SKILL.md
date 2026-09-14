---
name: evaluation-readme-formatting
description: Edit evaluation Markdown wording, structure, tables, or execution-step readability without changing research behavior.
---

# Evaluation README Formatting

- Read the target document first. Use [EVALUATION_ROUTES.md](../../../docs/codex_memory/EVALUATION_ROUTES.md) only if its implementation is unclear; check relevant [known issues](../../../docs/research/known_issues.md).
- Preserve research claims, metrics, conditions, results and command semantics. Verify referenced scripts, options, paths, outputs and evaluation numbers against producer code/argparse; use `--help` only after checking it exits safely.
- Classify discrepancies as documentation fixes, observed behavior, or unresolved research issues. Do not turn suspected bugs into specifications.
- Follow the document's structure. For full normalization, prefer summary → RQ → metrics → inputs/outputs → interpretation → execution → comparisons → procedure → parameters → cautions; omit unsupported sections.
- Use compact tables and ordered steps; keep commands with their supported required/conditional/optional conditions. Preserve the first result to inspect, detail files and reproduction metadata from producer evidence.
- Verify headings, execution order, fences, links and duplicate prose. Edit only requested documentation; report implementation inconsistencies separately. Wording-only changes do not require experiments or unrelated test suites.
