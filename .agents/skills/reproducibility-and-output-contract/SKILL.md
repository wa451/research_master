---
name: reproducibility-and-output-contract
description: Change repository-wide reproducibility, artifact placement, logging, or shared CSV/JSON contracts. Excludes evaluation-local outputs.
---

# Reproducibility And Output Contract

- Read relevant sections of [artifact_policy.md](../../../docs/operations/artifact_policy.md), [experiment_reproduction.md](../../../docs/operations/experiment_reproduction.md), [known_issues.md](../../../docs/research/known_issues.md), and the target producer's document.
- Trace the changed path/field from producer to every reader with scoped `rg`; inspect tests and only representative headers/summary keys. Classify the artifact as input, intermediate, or paper result.
- Preserve paths, names, types, row grain and defaults. Prefer additive fields; breaking migrations require an explicit request. Keep input/parameter metadata consistent with existing producer summaries rather than inventing a universal schema.
- Update producer, consumers, docs and focused tests together. Verify headers/keys, downstream reading and deterministic fixture/dry-run behavior using temporary/new output; do not overwrite experiments or alter tracked fixed artifacts.
- Report compatibility impact, regenerated files and anything not reproducible locally.
