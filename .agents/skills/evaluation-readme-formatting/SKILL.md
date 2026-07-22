---
name: evaluation-readme-formatting
description: Create or restructure evaluation Markdown without changing code or experimental behavior. Use for prose, headings, tables, and execution-step readability only.
---

# Evaluation README Formatting

## Workflow

1. Read the target document, `docs/known_issues.md`, and the implementation it describes. Verify every script, option, path pattern, output name, and evaluation number against the current repository. Inspect `argparse` first; run `--help` only for entry points that handle it safely.
2. Preserve research claims, metrics, conditions, results, and command semantics. Classify conflicts as safe documentation fixes, confirmed current behavior, or unresolved research/implementation issues. Do not invent values, silently resolve conflicts, or present a suspected bug as intended specification.
3. Follow the target document's established structure. For a full README-style normalization, prefer: summary, RQ, metrics, inputs/outputs, result interpretation, execution steps, comparisons, internal procedure, parameters, and cautions. Omit sections unsupported by the source.
4. Use tables for compact mappings and numbered step headings for execution order. Put each command with its condition, and distinguish required, conditional, and optional steps only when the implementation supports that distinction.
5. Wrap paths, filenames, columns, options, and commands in code formatting. Remove repetition without removing safeguards or reproduction conditions.
6. Edit only requested documentation unless a verified inconsistency must be reported separately.

## Verification

- Check heading order, command order, code fences, links, and duplicate prose.
- Confirm options from `argparse` and safe `--help` output; do not add confirmation-only commands to the documented workflow.
- Confirm the recommended first result file, detail files, and reproduction metadata from current outputs or producer code.
