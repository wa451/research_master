# Repository guidance

## Scope

This repository is an independent clean-room implementation inspired by the HESTIA paper. Never clone, copy, translate, or intentionally reproduce the original HESTIA source. The paper and public behavioral requirements are acceptable references.

## Development rules

- Support Python 3.11 or newer and manage dependencies with uv.
- Keep configuration, topology, devices, engine, randomness, event collection, output transforms, CLI, and validation separated.
- Route every stochastic decision through `RandomManager`; do not use module-level randomness.
- Preserve deterministic ordering by sorting IDs before scheduling or serializing collections.
- Keep timestamps timezone-aware and store raw timestamps as ISO 8601 with microseconds.
- Add short Japanese comments only where concurrency or research logic is not obvious; keep identifiers and public APIs in English.
- Do not commit generated output. `outputs/` and temporary render files remain ignored.

## Required checks

Run all commands before declaring a change complete:

```bash
uv sync
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest -q
```

For engine or schema changes, also validate and simulate both example scenarios. Reproducibility changes must compare complete output-directory hashes for two independent runs with the same seed.

## Compressed external memory

- `docs/codex_memory/` holds concise conclusions, not work logs. Read only the relevant memo: `CODEBASE_MAP.md` for locations/flows, `DECISIONS.md` for design reasons, `KNOWN_ISSUES.md` for investigated problems, `CURRENT_STATE.md` for resuming work. Never preload all four.
- Investigation order: this file → relevant memory → existing docs → related current code → broader code search only if needed. Do not repeat a whole-repository investigation when memory is sufficient; verify only the affected code if a memo may be stale. Current code and current specifications take precedence over old notes/history; flag conflicts.
- Use `ctx` only when missing historical decisions still matter after those steps; restrict searches to this workspace and specific keywords. Do not routinely search history or read whole sessions. Consult external sources only when local evidence is insufficient and the task requires them.
- At task end, save only new reusable conclusions in the relevant long-term memo; replace obsolete text, deduplicate, and link to existing documentation. No raw output, code copies, diffs, transcripts, or chronological activity logs. Keep reading a memo clearly cheaper than repeating the investigation.
- Keep long-term knowledge separate from `CURRENT_STATE.md`: rewrite the latter as a current checkpoint when useful for continuation (implemented work, latest change, active/next work, unknowns, dated check results); never append a running history. Do not update every memo by default.
- Keep user-facing progress minimal, with short updates for material findings, decisions, or blockers; avoid command-by-command narration. Finish with changes, verification results, and remaining issues only.
