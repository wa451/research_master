#!/usr/bin/env python3
"""Evaluation 10: generate and holdout-evaluate patterns from a SwitchBot snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.behavior_pattern_mining.evaluation.evaluation10_switchbot import (  # noqa: E402
    METHODS,
    STAGES,
    evaluate,
    extract,
    prepare,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True, help="Directory containing events.csv and manifest.json")
    parser.add_argument("--stage", choices=STAGES, default="run")
    parser.add_argument("--output-dir", type=Path, help="Intermediate output; default: output/10_switchbot/<snapshot>")
    parser.add_argument("--results-dir", type=Path, help="Evaluation output; default: results/10_switchbot/<snapshot>")
    parser.add_argument("--split-at", help="Local midnight starting the held-out test period")
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--n-states", type=int, default=15)
    parser.add_argument("--hamming-threshold", type=int, default=0)
    parser.add_argument("--smoothing-window-sec", type=int, default=5)
    parser.add_argument("--sampling-seconds", type=int, default=1)
    parser.add_argument("--min-sequence-length", type=int, default=2)
    parser.add_argument("--max-sequence-length", type=int, default=4)
    parser.add_argument("--min-train-occurrences", type=int, default=2)
    parser.add_argument("--top-k-per-mode", type=int, default=20)
    parser.add_argument("--method", choices=METHODS, default="both")
    parser.add_argument("--llm-patterns", type=Path, help="Optional existing LLM pattern JSON")
    parser.add_argument("--allow-api", action="store_true", help="Permit paid Gemini calls during extract/run")
    parser.add_argument("--dry-run", action="store_true", help="Validate arguments and print stages without writing")
    return parser


def _resolve(path: Path) -> Path:
    return (path if path.is_absolute() else ROOT / path).resolve()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot = _resolve(args.snapshot)
    output_dir = _resolve(args.output_dir or Path("output/10_switchbot") / snapshot.name)
    results_dir = _resolve(args.results_dir or Path("results/10_switchbot") / snapshot.name)
    stages = (
        ["prepare", *(["extract"] if args.allow_api else []), "evaluate"]
        if args.stage == "run"
        else [args.stage]
    )
    if args.allow_api and args.stage not in ("extract", "run"):
        print("--allow-api is only valid for extract or run", file=sys.stderr)
        return 2
    if args.stage == "extract" and not args.allow_api:
        print("extract requires --allow-api", file=sys.stderr)
        return 2
    print(f"snapshot: {snapshot}")
    print(f"intermediate output: {output_dir}")
    print(f"results: {results_dir}")
    print(f"stages: {', '.join(stages)}")
    if args.dry_run:
        return 0
    try:
        for stage in stages:
            if stage == "prepare":
                prepare(
                    snapshot_dir=snapshot,
                    output_dir=output_dir,
                    split_at=args.split_at,
                    train_ratio=args.train_ratio,
                    n_states=args.n_states,
                    hamming_threshold=args.hamming_threshold,
                    smoothing_window_sec=args.smoothing_window_sec,
                    sampling_seconds=args.sampling_seconds,
                    min_sequence_length=args.min_sequence_length,
                    max_sequence_length=args.max_sequence_length,
                    min_train_occurrences=args.min_train_occurrences,
                    top_k_per_mode=args.top_k_per_mode,
                )
            elif stage == "extract":
                extract(output_dir=output_dir, allow_api=args.allow_api)
            elif stage == "evaluate":
                evaluate(
                    output_dir=output_dir,
                    results_dir=results_dir,
                    method=args.method,
                    llm_patterns=_resolve(args.llm_patterns) if args.llm_patterns else None,
                )
    except (FileNotFoundError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
