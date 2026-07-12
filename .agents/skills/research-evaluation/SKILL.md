---
name: research-evaluation
description: Add, change, or debug numbered evaluation logic, metrics, CLIs, modules, or tests. Excludes prose-only docs, dashboard-only UI, baseline algorithms, and repository-wide artifact policy.
---

# Research Evaluation

## Workflow

1. Find and read the matching `docs/evaluation_*.md`; inspect the target script/module, its `argparse` definition or `--help`, and focused tests.
2. Identify the evaluation grain, inputs, outputs, split rules, defaults, aggregation, and missing-input/run behavior from the current code and documentation. Report conflicts before choosing a behavior.
3. Search for downstream readers before changing a filename or CSV/JSON field.
4. Implement evaluation logic in `src/behavior_pattern_mining/evaluation/` when reusable; keep `scripts/` as a thin CLI.
5. Preserve upstream preprocessing, extraction, defaults, schemas, and existing artifacts unless the request explicitly changes them. Prevent labels or test-period information from influencing training-side generation or mapping.
6. When an interface or result contract intentionally changes, update its evaluation document, focused tests, and Streamlit command wiring if that evaluation is exposed in `app/`.

## Verification

- Run the target CLI with `--help`.
- Run the narrowest relevant unit test or fixture-based evaluation.
- Compare produced headers/summary keys when the output contract changes; write only to a temporary or explicitly requested output directory.
- Inspect the final diff and state any research rule or path that remains uncertain.
