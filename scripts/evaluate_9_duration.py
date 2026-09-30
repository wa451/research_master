#!/usr/bin/env python3
"""Evaluation 9 train-duration sensitivity with one shared 35-day raw log."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiment_config import (
    current_model_identity,
    current_model_output_root,
    current_model_results_root,
)

from src.behavior_pattern_mining.evaluation.evaluation9_duration import (
    DEFAULT_TRAIN_DAYS,
    STAGES,
    build_duration_commands,
    execute_duration_commands,
    parse_train_days,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, default="run")
    parser.add_argument("--hestia-root", type=Path, default=Path("Hestia"))
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path("Hestia/examples/experiments/noise_free_duration.yaml"),
    )
    parser.add_argument(
        "--experiment", type=Path, default=None
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Summary/LLM output; default: results/<model>/9_hestia/duration",
    )
    parser.add_argument("--train-days", default=",".join(map(str, DEFAULT_TRAIN_DAYS)))
    parser.add_argument(
        "--method", choices=("frequency", "llm", "both"), default="both"
    )
    parser.add_argument("--allow-api", action="store_true")
    parser.add_argument(
        "--duration-workers",
        type=int,
        default=4,
        help="Maximum concurrent train-duration windows (default: 4).",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        identity = current_model_identity()
        experiment = args.experiment or current_model_output_root() / "9_hestia/duration"
        output_dir = args.output_dir or current_model_results_root() / "9_hestia/duration"
        commands = build_duration_commands(
            stage=args.stage,
            hestia_root=args.hestia_root,
            experiment=experiment,
            plan=args.plan,
            output_dir=output_dir,
            train_days=parse_train_days(args.train_days),
            method=args.method,
            allow_api=args.allow_api,
            model_id=identity.model_id,
        )
        for command in commands:
            print(shlex.join(command), flush=True)
        if not args.dry_run:
            execute_duration_commands(
                commands,
                args.hestia_root,
                duration_workers=args.duration_workers,
            )
    except subprocess.CalledProcessError as exc:
        return exc.returncode
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
