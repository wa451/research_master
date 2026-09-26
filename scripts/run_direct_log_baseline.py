#!/usr/bin/env python3
"""Run the direct-log LLM baseline and evaluate it."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from experiment_config import DAYS
from src.behavior_pattern_mining.evaluation import direct_log
from src.behavior_pattern_mining.llm import direct_log_extractor
from src.behavior_pattern_mining.data.sensor_representation import (
    DEFAULT_SENSOR_REPRESENTATION,
    SENSOR_REPRESENTATIONS,
    artifact_dataset_name,
    sensor_map_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the direct-log LLM baseline"
    )
    parser.add_argument(
        "--log-days",
        type=int,
        default=None,
        help="Number of days passed to the direct-log LLM input. Defaults to configs/default.yaml days.",
    )
    parser.add_argument(
        "--state-days",
        type=int,
        default=None,
        help="Number of days used to choose the representative state table. Defaults to the effective log days.",
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Only generate the direct-log LLM JSON. Skip the evaluation-3 baseline comparison.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=None,
        help="Number of direct-log LLM runs to generate. Defaults to configs/default.yaml llm.runs_default.",
    )
    parser.add_argument(
        "--n-states",
        type=int,
        default=None,
        help="Number of representative states K used by the state table and direct-log state mapping.",
    )
    parser.add_argument(
        "--hamming-threshold",
        type=int,
        default=None,
        help="Hamming distance threshold used by the state table and direct-log state mapping.",
    )
    parser.add_argument(
        "--sensor-representation",
        choices=SENSOR_REPRESENTATIONS,
        default=DEFAULT_SENSOR_REPRESENTATION,
        help="Aruba feature representation shared with the proposed method.",
    )
    parser.add_argument(
        "--llm-only-time-mode",
        choices=["split", "legacy"],
        default="split",
        help=(
            "split (default): call the LLM separately for each configured time period; "
            "legacy: reproduce the previous one-prompt whole-period baseline."
        ),
    )
    parser.add_argument(
        "--estimate-cost",
        action="store_true",
        help="Estimate Bedrock tokens and USD cost without model inference or evaluation.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Explicit direct-log LLM artifact directory. By default it is selected "
            "under results/<model> from the active model."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if (
        args.log_days is not None
        and args.log_days != DAYS
        and not args.extract_only
        and not args.estimate_cost
    ):
        raise ValueError(
            "--log-days differs from the project default DAYS. "
            "Use --extract-only for evaluation 6, or keep the default for evaluation 3."
        )

    direct_log_extractor.main(
        log_days=args.log_days,
        state_days=args.state_days,
        runs=args.runs,
        n_states=args.n_states,
        hamming_threshold=args.hamming_threshold,
        dataset_name=artifact_dataset_name("aruba", args.sensor_representation),
        sensor_map_path=sensor_map_path(ROOT_DIR, args.sensor_representation),
        estimate_cost=args.estimate_cost,
        output_dir=args.output_dir,
        llm_only_time_mode=args.llm_only_time_mode,
    )
    if not args.extract_only and not args.estimate_cost:
        direct_log.main()


if __name__ == "__main__":
    main()
