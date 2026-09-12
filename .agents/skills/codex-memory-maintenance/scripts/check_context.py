#!/usr/bin/env python3
"""Read-only checks for this repo's guidance: local inline links and size.

Supports inline Markdown links without titles, ATX headings and HTML id anchors.
Does not traverse linked files recursively or check external URLs/code semantics.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


LINK = re.compile(r"\[[^\]\n]*\]\((<[^>\n]+>|[^\s)]+)\)")


def prose_lines(text: str):
    fence_char, fence_length = "", 0
    for number, line in enumerate(text.splitlines(), 1):
        fence = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if fence:
            marker, tail = fence.groups()
            if not fence_char:
                fence_char, fence_length = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_length and not tail.strip():
                fence_char, fence_length = "", 0
            continue
        if not fence_char:
            yield number, line


def anchors(text: str) -> set[str]:
    found, used = set(), set()
    for _, line in prose_lines(text):
        found.update(re.findall(r'\bid=[\'"]([^\'"]+)[\'"]', line))
        heading = re.match(r"^ {0,3}#{1,6}\s+(.+?)(?:\s+#+\s*)?$", line)
        if heading:
            label = LINK.sub(lambda match: match.group(0).split("](", 1)[0][1:], heading[1])
            slug = re.sub(r"[^\w\- ]", "", label.lower()).replace(" ", "-")
            unique, suffix = slug, 0
            while unique in used:
                suffix += 1
                unique = f"{slug}-{suffix}"
            used.add(unique)
            found.add(unique)
    return found


def check(root: Path, stats: bool = False) -> int:
    root = root.resolve()
    files = [root / "AGENTS.md"]
    files += sorted((root / "docs/codex_memory").glob("*.md"))
    files += sorted((root / ".agents/skills").glob("*/SKILL.md"))
    errors, checked_links, warnings = [], 0, 0
    for path in files:
        relative = path.relative_to(root)
        if not path.is_file():
            errors.append(f"{relative}: missing guidance file")
            continue
        content = path.read_text(encoding="utf-8")
        count = len(content.splitlines())
        limit = 35 if path.name == "SKILL.md" else 60
        if path.name == "CURRENT_STATE.md":
            limit = 25
        if path.name == "EVALUATION_ROUTES.md":
            limit = 100  # Selectively read by evalN section, not loaded in full.
        if stats:
            print(f"{relative}: {count} lines, {len(content)} chars")
        if count > limit:
            warnings += 1
            print(f"WARN {relative}: {count} lines exceeds size guide {limit}")
        if path.name == "EVALUATION_ROUTES.md":
            lines = content.splitlines()
            starts = [i for i, line in enumerate(lines) if re.match(r"^## eval\d+ ", line)]
            for start, end in zip(starts, starts[1:] + [len(lines)]):
                if any(line.strip() for line in lines[start + 7:end]):
                    errors.append(f"{relative}:{start + 1}: route exceeds rg -A 6 window")
        for number, line in prose_lines(content):
            for match in LINK.finditer(line):
                url = urlsplit(match[1].strip("<>"))
                if url.scheme or url.netloc:
                    continue
                checked_links += 1
                target = (path.parent / unquote(url.path)).resolve() if url.path else path
                location = f"{relative}:{number}"
                if not target.is_relative_to(root):
                    errors.append(f"{location}: link leaves repo: {match[1]}")
                elif not target.exists():
                    errors.append(f"{location}: missing target: {match[1]}")
                elif url.fragment and target.suffix.lower() == ".md":
                    if unquote(url.fragment) not in anchors(target.read_text(encoding="utf-8")):
                        errors.append(f"{location}: missing anchor: {match[1]}")
    for error in errors:
        print(f"ERROR {error}")
    print(f"{'FAIL' if errors else 'OK'}: {len(files)} guidance files, "
          f"{checked_links} local links, {len(errors)} errors, {warnings} size warnings")
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4],
                        help="Repository root (default: inferred from this script)")
    parser.add_argument("--stats", action="store_true", help="Show lines and characters, not token counts")
    args = parser.parse_args()
    return check(args.root, args.stats)


if __name__ == "__main__":
    raise SystemExit(main())
