---
name: codex-memory-maintenance
description: Maintain this repository's Codex memory, file routing, and skill guidance when they become stale or expensive to read. Not needed for routine code edits.
---

# Codex Memory Maintenance

- Start with [AGENTS.md](../../../AGENTS.md) and only the affected memory/skill. Inspect the worktree first; preserve unrelated pending work. Audit all guidance only when the request covers the whole navigation system.
- Keep common constraints in AGENTS; file/doc/test routing in [CODEBASE_MAP.md](../../../docs/codex_memory/CODEBASE_MAP.md) or the target evalN section of [EVALUATION_ROUTES.md](../../../docs/codex_memory/EVALUATION_ROUTES.md); adopted reasons in [DECISIONS.md](../../../docs/codex_memory/DECISIONS.md); issue pointers in [KNOWN_ISSUES.md](../../../docs/codex_memory/KNOWN_ISSUES.md). Research specifications remain in their existing docs.
- Verify changed routes against current files, symbols, tests and CLI definitions without importing/running research code. Keep links relative to each Markdown file. The checker supports inline links without titles; use those for concrete file references.
- Store a conclusion plus evidence link, not copied code, output, chat or duplicate inventories. Replace stale entries. Keep CURRENT_STATE scoped to the work just handled, with remaining work and actual checks; never infer that other pending work is complete.
- Use approximate size guides: root AGENTS 60 lines, general map/decision/issue files 60 each, checkpoint 25, each skill 35. Evaluation routes are read per section; keep each evalN block within the heading plus 6 lines so the documented `rg -A 6` command retrieves it completely. Compress repetition before adding files or skills.
- Check realistic routes (e.g. eval6 run aggregation, eval8 frequency ownership, eval9 Web batch, prompt parsing). Each should reach source, document and a relevant test without reading unrelated memories or the full inventory. Identify test gaps rather than implying coverage.
- Run `python3 .agents/skills/codex-memory-maintenance/scripts/check_context.py --stats` from the repo root after updates. The [checker](scripts/check_context.py) uses only the standard library; it checks local inline Markdown links/anchors and reports size, not semantics, code symbols, external URLs, or real token usage. Run the skill-creator validator when changing SKILL.md if available.
- Report changed guidance, verification and remaining uncertainty. Measure actual task tokens separately; character/line counts are only context-size indicators. Do not run experiments or rewrite global Codex settings as an incidental part of memory upkeep.
