#!/usr/bin/env python3
"""Estimate full-rerun Bedrock tokens and cost for Evaluations 5--10."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from experiment_config import (
    BEDROCK_ESTIMATED_OUTPUT_TOKENS,
    BEDROCK_MAX_TOKENS,
    BEDROCK_MODEL_ID,
    BEDROCK_REGION,
    LLM_MODEL_NAME,
    LLM_PROVIDER,
    LLM_TEMPERATURE,
    current_model_output_root,
)
from src.behavior_pattern_mining.llm.client import load_dotenv, resolve_llm_runtime_config
from src.behavior_pattern_mining.llm.evaluation_costs import (
    DEFAULT_EVALUATIONS,
    build_evaluation_plans,
    estimate_models,
    format_model_comparison,
    save_model_comparison_reports,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-ids",
        "--evaluations",
        dest="evaluations",
        type=int,
        nargs="+",
        default=list(DEFAULT_EVALUATIONS),
        help="Evaluation IDs to estimate (default: 5 6 7 8 9 10).",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        help=(
            "Bedrock model IDs to compare. Defaults to BEDROCK_MODEL_ID when omitted."
        ),
    )
    parser.add_argument(
        "--evaluation9-experiment",
        type=Path,
        default=None,
        help="Prepared Hestia standard experiment directory.",
    )
    parser.add_argument(
        "--evaluation9-duration-experiment",
        type=Path,
        default=None,
        help="Prepared Hestia train-duration experiment directory.",
    )
    parser.add_argument(
        "--evaluation10-output-dir",
        type=Path,
        default=None,
        help="Prepared Evaluation 10 output directory containing preparation.json and network/.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for estimate CSV/JSON (default: output/<model>/cost_estimates).",
    )
    return parser


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT_DIR / path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(ROOT_DIR / ".env")
    llm_config = resolve_llm_runtime_config(
        default_provider=LLM_PROVIDER,
        gemini_model_name=LLM_MODEL_NAME,
        temperature=LLM_TEMPERATURE,
        bedrock_region=BEDROCK_REGION,
        bedrock_model_id=(args.models[0] if args.models else BEDROCK_MODEL_ID),
        bedrock_max_tokens=BEDROCK_MAX_TOKENS,
        bedrock_estimated_output_tokens=BEDROCK_ESTIMATED_OUTPUT_TOKENS,
    )
    if llm_config.provider != "bedrock":
        raise RuntimeError(
            "Evaluation cost estimation requires LLM_PROVIDER=bedrock; no inference was executed."
        )
    if llm_config.estimated_output_tokens is None:
        raise RuntimeError(
            "Set BEDROCK_ESTIMATED_OUTPUT_TOKENS (or llm.bedrock.estimated_output_tokens) "
            "to calculate the expected-output and expected-total estimates."
        )
    model_ids = args.models or [llm_config.model_name]
    if len(set(model_ids)) != len(model_ids):
        raise ValueError("--models must not contain duplicate model IDs")
    llm_configs = [replace(llm_config, model_name=model_id) for model_id in model_ids]
    model_output_root = current_model_output_root()
    plans = build_evaluation_plans(
        root=ROOT_DIR,
        evaluations=args.evaluations,
        evaluation9_experiment=_resolve(args.evaluation9_experiment or model_output_root / "9_hestia/full"),
        evaluation9_duration_experiment=_resolve(
            args.evaluation9_duration_experiment or model_output_root / "9_hestia/duration"
        ),
        evaluation10_output_dir=_resolve(
            args.evaluation10_output_dir or model_output_root / "10_switchbot/2026-09-01_2026-09-08"
        ),
    )
    reports = estimate_models(llm_configs=llm_configs, plans=plans)
    output_dir = _resolve(args.output_dir or model_output_root / "cost_estimates")
    suffix = (
        f"{args.evaluations[0]}_{args.evaluations[-1]}"
        if args.evaluations
        == list(range(args.evaluations[0], args.evaluations[-1] + 1))
        else "_".join(str(value) for value in args.evaluations)
    )
    stem = f"evaluation_{suffix}_cost_estimate"
    csv_path = output_dir / f"{stem}.csv"
    json_path = output_dir / f"{stem}.json"
    summary_csv_path = output_dir / "model_comparison_summary.csv"
    save_model_comparison_reports(
        reports,
        csv_path=csv_path,
        json_path=json_path,
        summary_csv_path=summary_csv_path,
    )
    print(
        format_model_comparison(
            reports,
            csv_path=csv_path,
            json_path=json_path,
            summary_csv_path=summary_csv_path,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
