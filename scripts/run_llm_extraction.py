#!/usr/bin/env python3
"""Run LLM pattern extraction for the proposed method."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.behavior_pattern_mining.llm import pattern_extractor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run LLM pattern extraction for the proposed method"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Number of days used to choose picture/input and output directories",
    )
    run_group = parser.add_mutually_exclusive_group()
    run_group.add_argument(
        "--runs",
        type=int,
        default=None,
        help="Number of LLM runs to generate. Defaults to configs/default.yaml llm.runs_default.",
    )
    run_group.add_argument(
        "--run-ids",
        type=int,
        nargs="+",
        default=None,
        help="Explicit run IDs to generate, e.g. 2 3 4. Cannot be combined with --runs.",
    )
    parser.add_argument(
        "--n-states",
        type=int,
        default=None,
        help="Number of representative states K used in the input/output directory suffix.",
    )
    parser.add_argument(
        "--hamming-threshold",
        type=int,
        default=None,
        help="Hamming distance threshold used in the input/output directory suffix.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    pattern_extractor.main(
        days=args.days,
        runs=args.runs,
        run_ids=args.run_ids,
        n_states=args.n_states,
        hamming_threshold=args.hamming_threshold,
    )
