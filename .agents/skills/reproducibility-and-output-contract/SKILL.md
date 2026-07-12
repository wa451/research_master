---
name: reproducibility-and-output-contract
description: Change repository-wide reproducibility, artifact placement, logging policy, or shared cross-pipeline CSV/JSON contracts. Excludes outputs local to one evaluation or baseline.
---

# Reproducibility And Output Contract

## Workflow

1. Read `docs/artifact_policy.md`, `docs/experiment_reproduction.md`, and the relevant producer documentation.
2. Inspect the producer, every downstream reader found with `rg`, tests, and representative existing headers or summary keys. Determine whether each artifact is an input, intermediate output, or paper-facing result.
3. Preserve paths, field names, types, row grain, and defaults. Prefer additive fields; make a breaking migration only when explicitly requested and document compatibility impact.
4. Keep reproduction metadata consistent with existing summaries, including the inputs and parameters needed to explain the run. Do not invent a universal schema when producers use different contracts.
5. Never overwrite existing experiment artifacts during verification. Use a temporary or new output directory and keep generated data out of Git.
6. Update producer, consumers, documentation, and tests together.

## Verification

- Compare old and new CSV headers or JSON keys and test downstream readers.
- Run a small deterministic fixture or dry run where available.
- Report regenerated files, compatibility risks, and anything not reproducible locally.
