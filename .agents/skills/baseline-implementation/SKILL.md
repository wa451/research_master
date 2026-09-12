---
name: baseline-implementation
description: Change comparison baseline extraction, filtering, algorithms, or fairness. Excludes running existing baselines and evaluation-only integration.
---

# Baseline Implementation

- Use the baseline row in [CODEBASE_MAP.md](../../../docs/codex_memory/CODEBASE_MAP.md) and the consuming [evaluation route](../../../docs/codex_memory/EVALUATION_ROUTES.md). FP-Growth/ADL baselines live in the evaluation package, outside the baseline directory.
- Read the consuming evaluation document, relevant [known issues](../../../docs/known_issues.md), producer, consumer, CLI and focused tests. Compare nearby implementations only when needed.
- Establish period, split, state settings, sequence constraints, method ID, record shape and failure handling. Preserve compatibility; use the compared methods' inputs/split unless the research specification differs.
- Put reusable extraction/filtering outside the CLI. Prevent test labels from influencing generation, thresholds, filtering, caches or train-side label assignment. Expose meaningful thresholds as CLI arguments and record them in the existing summary convention.
- Verify a small fixture, empty/invalid input, comparison conditions, and the consuming CLI's safe argparse `--help`. Update focused tests and consuming docs; update Web only if its interface/results change. Check the diff for unintended proposed-method, metric or artifact changes.
