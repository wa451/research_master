---
name: research-evaluation
description: Change numbered evaluation metrics, logic, CLIs, or tests. Excludes prose-only docs, dashboard-only UI, and baseline algorithms.
---

# Research Evaluation

- Locate only the target evalN section in [EVALUATION_ROUTES.md](../../../docs/codex_memory/EVALUATION_ROUTES.md); follow its document, CLI/module, tests, and known-issue IDs. Shared safety and lookup rules are in [AGENTS.md](../../../AGENTS.md).
- Establish grain, split, defaults, aggregation, missing-run behavior, and output contract from the relevant code and docs; report unresolved conflicts. Do not change upstream extraction/preprocessing incidentally.
- Keep reusable logic in the evaluation package. Some eval5–8 aggregation still lives in scripts; inspect both sides. Before changing a path or field, find downstream readers with scoped `rg`.
- Prevent labels/test-period data from influencing training generation, mapping, thresholds, or caches. Update the evaluation doc, focused tests, and exposed dashboard wiring for intentional interface changes.
- Verify safe argparse `--help`, the target fixture/test, deterministic behavior where applicable, and produced headers/summary keys in temporary output. Do not run extraction or a full experiment merely to check an evaluation edit.
