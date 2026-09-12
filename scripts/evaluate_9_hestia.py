#!/usr/bin/env python3
"""Evaluation 9: staged synthetic-log recovery and ADL evaluation."""

from __future__ import annotations

import argparse
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.behavior_pattern_mining.evaluation.evaluation9_hestia import (
    STAGES,
    build_commands,
    execute,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, default="run")
    parser.add_argument("--hestia-root", type=Path, default=Path("Hestia"))
    parser.add_argument(
        "--plan", type=Path, help="JSON/YAML plan; default: Hestia noise-free pilot"
    )
    parser.add_argument(
        "--experiment", type=Path, default=Path("output/9_hestia/pilot")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("results/9_hestia/pilot")
    )
    parser.add_argument(
        "--method", choices=("frequency", "llm", "both"), default="both"
    )
    parser.add_argument(
        "--allow-api",
        action="store_true",
        help="Permit paid LLM calls during extract/run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing or writing",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        commands = build_commands(
            stage=args.stage,
            hestia_root=args.hestia_root,
            plan=args.plan,
            experiment=args.experiment,
            output_dir=args.output_dir,
            method=args.method,
            allow_api=args.allow_api,
        )
        for command in commands:
            print(shlex.join(command), flush=True)
        if not args.dry_run:
            execute(commands, args.hestia_root)
    except subprocess.CalledProcessError as exc:
        return exc.returncode
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
