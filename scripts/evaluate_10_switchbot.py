#!/usr/bin/env python3
"""Evaluation 10: generate and holdout-evaluate patterns from a SwitchBot snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiment_config import current_model_output_root, current_model_results_root  # noqa: E402

from src.behavior_pattern_mining.evaluation.evaluation10_switchbot import (  # noqa: E402
    FORMAL_OUTPUT_NAMESPACE,
    FORMAL_EVALUATION7_BEST_CONDITION_MANIFEST,
    FORMAL_RUNS,
    METHODS,
    STAGES,
    evaluate,
    llm_patterns_path,
    prepare,
    verify_preparation,
)
from src.behavior_pattern_mining.evaluation.evaluation6_manifest import (  # noqa: E402
    load_evaluation7_best_condition_manifest,
)
from src.behavior_pattern_mining.llm import pattern_extractor  # noqa: E402


# A request can time out after prior mode checkpoints have been persisted.  Retry
# only transport failures here; parsing/validation errors must remain visible.
# The shared Bedrock client also retries a transient request once.  Limit this
# outer, checkpoint-aware resume to two attempts so an unresolved mode is not
# sent more than four times in total.
EXTRACT_TRANSPORT_MAX_ATTEMPTS = 2
RETRYABLE_TRANSPORT_ERROR_MARKERS = (
    "bedrock runtimeエンドポイントへ接続できません",
    "read timeout",
    "connect timeout",
    "endpointconnectionerror",
    "connectionclosederror",
)
EVALUATION_RESULT_FILENAMES = (
    "evaluation10_summary.csv",
    "evaluation10_summary_by_run.csv",
    "evaluation10_pattern_details.csv",
    "evaluation10_by_time_band.csv",
    "evaluation10_by_pattern_length.csv",
    "evaluation10_manifest.json",
    "evaluation10_summary.json",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True, help="Directory containing events.csv and manifest.json")
    parser.add_argument("--stage", choices=STAGES, default="run")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Intermediate output; default: output/<model>/10_real_home_temporal_generalization/<snapshot>",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        help="Evaluation/LLM output; default: results/<model>/10_real_home_temporal_generalization/<snapshot>",
    )
    parser.add_argument(
        "--eval7-best-condition-manifest",
        type=Path,
        default=FORMAL_EVALUATION7_BEST_CONDITION_MANIFEST,
        help="Required source of the fixed formal K/h condition",
    )
    parser.add_argument("--split-at", help="Local midnight starting the held-out test period")
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--n-states", type=int, help="Must equal the Evaluation 7 manifest K")
    parser.add_argument("--hamming-threshold", type=int, help="Must equal the Evaluation 7 manifest h")
    parser.add_argument("--smoothing-window-sec", type=int, default=5)
    parser.add_argument("--sampling-seconds", type=int, default=1)
    parser.add_argument("--min-sequence-length", type=int, default=2)
    parser.add_argument("--max-sequence-length", type=int, default=4)
    parser.add_argument("--min-train-occurrences", type=int, default=2)
    parser.add_argument("--top-k-per-mode", type=int, default=20)
    parser.add_argument("--method", choices=METHODS, default="llm")
    parser.add_argument("--runs", type=int, default=FORMAL_RUNS, help="LLM extraction/evaluation runs; formal default: 5")
    parser.add_argument("--llm-patterns", type=Path, help="Optional existing LLM pattern JSON")
    parser.add_argument(
        "--overwrite-results",
        action="store_true",
        help="Permit replacing existing evaluation10 CSV/JSON summaries during the evaluate stage only",
    )
    parser.add_argument("--allow-api", action="store_true", help="Permit paid Bedrock calls during extract/run")
    parser.add_argument("--dry-run", action="store_true", help="Validate the formal plan and print train-only estimates without writing")
    return parser


def _resolve(path: Path) -> Path:
    return (path if path.is_absolute() else ROOT / path).resolve()


def _missing_run_ids(paths: list[Path]) -> list[int]:
    return [run for run, path in enumerate(paths, start=1) if not path.is_file()]


def _is_retryable_transport_error(exc: RuntimeError) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in RETRYABLE_TRANSPORT_ERROR_MARKERS)


def clear_existing_evaluation_results(results_dir: Path) -> list[Path]:
    """Remove only replaceable Evaluation 10 aggregate files after opt-in.

    LLM run JSONs and their mode checkpoints live under ``llm/`` and are never
    considered here, so an evaluate-only rerun cannot repeat Bedrock inference.
    """
    removed: list[Path] = []
    for filename in EVALUATION_RESULT_FILENAMES:
        path = results_dir / filename
        if not path.exists():
            continue
        if not path.is_file():
            raise ValueError(f"refusing to replace non-file Evaluation 10 result: {path}")
        path.unlink()
        removed.append(path)
    return removed


def resume_extract(
    *, output_dir: Path, results_dir: Path, runs: int
) -> list[Path]:
    """Generate only missing run files, preserving completed LLM artifacts.

    A transient Bedrock transport timeout retries the extraction once.
    Each retry recomputes the missing runs, so final JSONs and per-mode
    checkpoints saved before the timeout are reused rather than overwritten.
    """
    preparation = verify_preparation(output_dir)
    params = preparation["parameters"]
    paths = [
        llm_patterns_path(output_dir, preparation, results_dir, run)
        for run in range(1, runs + 1)
    ]
    for attempt in range(1, EXTRACT_TRANSPORT_MAX_ATTEMPTS + 1):
        missing_run_ids = _missing_run_ids(paths)
        if not missing_run_ids:
            return paths
        try:
            pattern_extractor.main(
                days=preparation["split"]["train_days"],
                input_modes_dir=output_dir / "network",
                output_dir=paths[0].parent,
                runs=runs,
                run_ids=missing_run_ids,
                n_states=params["n_states"],
                hamming_threshold=params["hamming_threshold"],
            )
        except RuntimeError as exc:
            if (
                not _is_retryable_transport_error(exc)
                or attempt == EXTRACT_TRANSPORT_MAX_ATTEMPTS
            ):
                raise
            delay_sec = 2**attempt
            print(
                "Bedrock接続が一時的に失敗しました。"
                f"保存済みcheckpointを再利用して{delay_sec}秒後に再試行します "
                f"({attempt + 1}/{EXTRACT_TRANSPORT_MAX_ATTEMPTS})。"
            )
            time.sleep(delay_sec)

    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(
            "LLM extractor did not produce expected output: "
            + ", ".join(map(str, missing))
        )
    return paths


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot = _resolve(args.snapshot)
    output_dir = _resolve(args.output_dir or current_model_output_root() / FORMAL_OUTPUT_NAMESPACE / snapshot.name)
    results_dir = _resolve(
        args.results_dir
        or current_model_results_root() / FORMAL_OUTPUT_NAMESPACE / snapshot.name
    )
    eval7_manifest = _resolve(args.eval7_best_condition_manifest)
    try:
        condition = load_evaluation7_best_condition_manifest(eval7_manifest)
    except (FileNotFoundError, ValueError) as exc:
        print(f"invalid Evaluation 7 best-condition manifest: {exc}", file=sys.stderr)
        return 2
    if args.n_states is not None and args.n_states != condition.n_states:
        print("--n-states conflicts with the Evaluation 7 best-condition manifest", file=sys.stderr)
        return 2
    if args.hamming_threshold is not None and args.hamming_threshold != condition.hamming_threshold:
        print("--hamming-threshold conflicts with the Evaluation 7 best-condition manifest", file=sys.stderr)
        return 2
    if args.runs < 1:
        print("--runs must be >= 1", file=sys.stderr)
        return 2
    if args.runs != FORMAL_RUNS:
        print(f"formal Evaluation 10 requires --runs {FORMAL_RUNS}", file=sys.stderr)
        return 2
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
    print(f"Evaluation 7 condition: {eval7_manifest} (K={condition.n_states}, h={condition.hamming_threshold})")
    print(f"LLM runs: {args.runs}")
    print(f"stages: {', '.join(stages)}")
    if args.dry_run:
        try:
            plan = prepare(
                snapshot_dir=snapshot,
                output_dir=output_dir,
                split_at=args.split_at,
                train_ratio=args.train_ratio,
                n_states=condition.n_states,
                hamming_threshold=condition.hamming_threshold,
                smoothing_window_sec=args.smoothing_window_sec,
                sampling_seconds=args.sampling_seconds,
                min_sequence_length=args.min_sequence_length,
                max_sequence_length=args.max_sequence_length,
                min_train_occurrences=args.min_train_occurrences,
                top_k_per_mode=args.top_k_per_mode,
                evaluation7_manifest=eval7_manifest,
                write_artifacts=False,
            )
        except (FileNotFoundError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps({
            "split": plan["split"],
            "counts": plan["counts"],
            "network": plan["network"],
            "dry_run_estimate": {**plan["dry_run_estimate"], "total_prompt_tokens_for_runs_estimate": plan["dry_run_estimate"]["prompt_tokens_per_run_estimate"] * args.runs},
            "api_calls": 0,
            "test_prompted_to_llm": False,
        }, ensure_ascii=False, indent=2))
        return 0
    try:
        for stage in stages:
            if stage == "prepare":
                prepare(
                    snapshot_dir=snapshot,
                    output_dir=output_dir,
                    split_at=args.split_at,
                    train_ratio=args.train_ratio,
                    n_states=condition.n_states,
                    hamming_threshold=condition.hamming_threshold,
                    smoothing_window_sec=args.smoothing_window_sec,
                    sampling_seconds=args.sampling_seconds,
                    min_sequence_length=args.min_sequence_length,
                    max_sequence_length=args.max_sequence_length,
                    min_train_occurrences=args.min_train_occurrences,
                    top_k_per_mode=args.top_k_per_mode,
                    evaluation7_manifest=eval7_manifest,
                )
            elif stage == "extract":
                resume_extract(
                    output_dir=output_dir,
                    results_dir=results_dir,
                    runs=args.runs,
                )
            elif stage == "evaluate":
                if args.overwrite_results:
                    removed = clear_existing_evaluation_results(results_dir)
                    if removed:
                        print(
                            "Replacing existing Evaluation 10 aggregate files: "
                            + ", ".join(str(path) for path in removed)
                        )
                evaluate(
                    output_dir=output_dir,
                    results_dir=results_dir,
                    method=args.method,
                    llm_patterns=_resolve(args.llm_patterns) if args.llm_patterns else None,
                    runs=args.runs,
                )
    except (FileNotFoundError, FileExistsError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
