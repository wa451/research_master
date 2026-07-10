#!/usr/bin/env python3
"""Compare evaluation 6 between proposed LLM patterns and direct-log baseline."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT_DIR_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(ROOT_DIR_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR_FOR_IMPORTS))

from experiment_config import DATASET_NAME, HAMMING_THRESHOLD, N_STATES, ROOT_DIR
from src.behavior_pattern_mining.evaluation.adl import (
    PatternRecord,
    find_pattern_occurrences,
    load_state_series_csv,
    parse_labeled_casas_intervals,
    write_csv_rows,
)
from src.behavior_pattern_mining.evaluation.adl_interpretation_set import (
    ALLOWED_LABELS,
    InterpretationPattern,
    PatternOccurrenceInterval,
    aggregate_by_label,
    aggregate_by_time_band,
    evaluate_interpretation_sets,
    load_adl_intervals_csv,
    load_interpretation_patterns,
    time_band_for_timestamp,
)


EVAL6_DAYS = 30

DETAIL_FIELDNAMES = [
    "run",
    "method",
    "eval_pattern_id",
    "group_pattern_id",
    "sequence",
    "time_band",
    "pattern_name",
    "pattern_id",
    "num_occurrences",
    "pred_adl_labels",
    "true_adl_labels",
    "intersection_labels",
    "union_labels",
    "exact_set_match",
    "jaccard",
    "multilabel_precision",
    "multilabel_recall",
    "multilabel_f1",
    "total_overlap_seconds",
    "true_label_overlap_detail",
]

SUMMARY_FIELDNAMES = [
    "run",
    "method",
    "num_patterns",
    "num_pattern_occurrences",
    "mean_exact_set_match",
    "mean_jaccard",
    "mean_multilabel_precision",
    "mean_multilabel_recall",
    "mean_multilabel_f1",
]

MEAN_SUMMARY_FIELDNAMES = [
    "method",
    "num_runs",
    "avg_num_patterns",
    "avg_num_pattern_occurrences",
    "mean_exact_set_match",
    "std_exact_set_match",
    "mean_jaccard",
    "std_jaccard",
    "mean_multilabel_precision",
    "std_multilabel_precision",
    "mean_multilabel_recall",
    "std_multilabel_recall",
    "mean_multilabel_f1",
    "std_multilabel_f1",
]


def default_output_root() -> Path:
    return ROOT_DIR / "results" / "6_adl_interpretation_set_comparison"


def condition_suffix(days: int, n_states: int | None, hamming_threshold: int | None) -> str:
    resolved_n_states = n_states if n_states is not None else N_STATES
    resolved_hamming = hamming_threshold if hamming_threshold is not None else HAMMING_THRESHOLD
    return f"{resolved_n_states}_{resolved_hamming}_{days}days"


def resolve_output_dir(output_dir: Path | None, suffix: str) -> Path:
    """Resolve the final condition-specific result directory.

    Passing results/6_adl_interpretation_set_comparison writes into its
    {K}_{hamming}_{days}days child. Passing the condition directory itself
    remains supported for backward compatibility.
    """
    output_root = default_output_root()
    if output_dir is None:
        return output_root / suffix

    if output_dir.name == suffix:
        return output_dir
    if output_dir == output_root or output_dir.name == output_root.name:
        return output_dir / suffix
    return output_dir


def parse_args() -> argparse.Namespace:
    param_suffix = f"{N_STATES}_{HAMMING_THRESHOLD}_{EVAL6_DAYS}days"
    parser = argparse.ArgumentParser(
        description="Compare evaluation 6 set metrics for proposed and direct-log LLM outputs"
    )
    parser.add_argument(
        "--patterns-proposed",
        type=Path,
        default=ROOT_DIR / "output" / f"{DATASET_NAME}_{param_suffix}" / f"llm_sequences_modes_{param_suffix}_1.json",
        help="Proposed-method LLM pattern JSON containing ADL系列ラベル",
    )
    parser.add_argument(
        "--patterns-proposed-template",
        type=str,
        default=None,
        help=(
            "Optional proposed pattern path template for multi-run evaluation. "
            "Use {run}, e.g. output/aruba_15_1_30days/llm_sequences_modes_15_1_30days_{run}.json"
        ),
    )
    parser.add_argument(
        "--patterns-direct",
        type=Path,
        default=ROOT_DIR
        / "output"
        / f"llm_direct_{N_STATES}_{HAMMING_THRESHOLD}_{EVAL6_DAYS}days"
        / "1.json",
        help="Direct-log baseline LLM pattern JSON containing ADL系列ラベル",
    )
    parser.add_argument(
        "--patterns-direct-template",
        type=str,
        default=None,
        help=(
            "Optional direct-baseline pattern path template for multi-run evaluation. "
            "Use {run}, e.g. output/llm_direct_15_1_30days/{run}.json"
        ),
    )
    parser.add_argument(
        "--state-series",
        type=Path,
        default=ROOT_DIR / "output" / f"6_adl_evaluation_{EVAL6_DAYS}" / "state_series.csv",
        help="State interval CSV used to search occurrences for both methods",
    )
    parser.add_argument(
        "--adl-intervals",
        type=Path,
        default=ROOT_DIR / "output" / "adl_label_intervals.csv",
        help="ADL truth interval CSV",
    )
    parser.add_argument(
        "--labeled-casas",
        type=Path,
        default=None,
        help="Optional labeled CASAS file used when --adl-intervals does not exist",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output root or condition directory for evaluation 6 method comparison. "
            "When omitted, or when results/6_adl_interpretation_set_comparison is passed, "
            "outputs are written to results/6_adl_interpretation_set_comparison/{K}_{hamming}_{days}days."
        ),
    )
    parser.add_argument(
        "--min-overlap-ratio-for-true-label",
        type=float,
        default=0.10,
        help="Minimum share of total ADL overlap required for a true ADL set label",
    )
    parser.add_argument(
        "--no-overlap-label",
        choices=["Other", "Ambiguous"],
        default="Ambiguous",
        help="True label used when a pattern has no ADL overlap",
    )
    parser.add_argument(
        "--missing-pred-label",
        choices=["Other", "Ambiguous"],
        default="Ambiguous",
        help="Predicted label used when a pattern has no ADL系列ラベル",
    )
    parser.add_argument(
        "--unknown-pred-label",
        choices=["Other", "Ambiguous"],
        default="Other",
        help="Predicted label used when an LLM label cannot be normalized",
    )
    parser.add_argument(
        "--wake-window-minutes",
        type=float,
        default=30.0,
        help="Wake-up relabel window used only when --labeled-casas is used",
    )
    parser.add_argument(
        "--match-mode",
        choices=["exact", "skip-other"],
        default="exact",
        help="Pattern occurrence search mode used for both methods",
    )
    parser.add_argument(
        "--max-skip-duration-minutes",
        type=float,
        default=1.0,
        help="Maximum duration for one skipped その他 state when --match-mode skip-other",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=EVAL6_DAYS,
        help="Number of days used for this evaluation condition. Stored in the summary JSON.",
    )
    parser.add_argument(
        "--n-states",
        type=int,
        default=None,
        help="Representative-state count K for this evaluation condition. Stored in the summary JSON.",
    )
    parser.add_argument(
        "--hamming-threshold",
        type=int,
        default=None,
        help="Hamming distance threshold for this evaluation condition. Stored in the summary JSON.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of LLM runs to evaluate and average. Default keeps the historical single-run behavior.",
    )
    parser.add_argument(
        "--skip-missing-runs",
        action="store_true",
        help="Skip missing method/run pattern files instead of stopping. Skipped files are recorded in the summary JSON.",
    )
    return parser.parse_args()


def path_for_run(base_path: Path, run: int, template: str | None) -> Path:
    """Resolve a pattern file for one run while preserving old single-run defaults."""
    if template:
        return Path(template.format(run=run))
    if run == 1:
        return base_path

    stem = base_path.stem
    suffix = base_path.suffix
    if stem.isdigit():
        return base_path.with_name(f"{run}{suffix}")

    prefix, sep, last = stem.rpartition("_")
    if sep and last.isdigit():
        return base_path.with_name(f"{prefix}_{run}{suffix}")
    return base_path.with_name(f"{stem}_{run}{suffix}")


def pattern_records_from_interpretation_patterns(
    patterns: list[InterpretationPattern],
) -> list[PatternRecord]:
    return [
        PatternRecord(
            pattern_id=pattern.pattern_id,
            pattern_name=pattern.pattern_name,
            sequence=pattern.sequence,
        )
        for pattern in patterns
    ]


def occurrence_intervals_from_matches(matches) -> list[PatternOccurrenceInterval]:
    return [
        PatternOccurrenceInterval(
            pattern_id=match.pattern_id,
            pattern_name=match.pattern_name,
            sequence=match.sequence,
            start_time=match.start_time,
            end_time=match.end_time,
            time_band=time_band_for_timestamp(match.start_time),
        )
        for match in matches
    ]


def count_relevant_occurrences(
    patterns: list[InterpretationPattern],
    occurrences: list[PatternOccurrenceInterval],
) -> int:
    pattern_by_id = {pattern.pattern_id: pattern for pattern in patterns}
    count = 0
    for occurrence in occurrences:
        pattern = pattern_by_id.get(occurrence.pattern_id)
        if pattern is None:
            continue
        if pattern.time_band == "All" or time_band_for_timestamp(occurrence.start_time) == pattern.time_band:
            count += 1
    return count


def evaluate_method(
    method: str,
    patterns_path: Path,
    state_intervals,
    adl_intervals,
    args: argparse.Namespace,
) -> tuple[list[dict], dict]:
    if not patterns_path.exists():
        raise FileNotFoundError(f"{method} pattern file does not exist: {patterns_path}")

    patterns = load_interpretation_patterns(
        patterns_path,
        missing_label=args.missing_pred_label,
        unknown_label=args.unknown_pred_label,
    )
    matches = find_pattern_occurrences(
        pattern_records_from_interpretation_patterns(patterns),
        state_intervals,
        match_mode=args.match_mode,
        max_skip_duration_minutes=args.max_skip_duration_minutes,
    )
    occurrences = occurrence_intervals_from_matches(matches)
    detail_rows, summary_metrics = evaluate_interpretation_sets(
        patterns=patterns,
        occurrences=occurrences,
        adl_intervals=adl_intervals,
        min_overlap_ratio_for_true_label=args.min_overlap_ratio_for_true_label,
        no_overlap_label=args.no_overlap_label,
    )
    detail_rows = [{"method": method, **row} for row in detail_rows]
    summary_metrics = {
        "method": method,
        "num_pattern_occurrences": count_relevant_occurrences(patterns, occurrences),
        **summary_metrics,
    }
    return detail_rows, summary_metrics


def add_method_to_label_rows(method: str, rows: list[dict]) -> list[dict]:
    return [{"method": method, **row} for row in rows]


def add_run_to_rows(run: int, rows: list[dict]) -> list[dict]:
    return [{"run": run, **row} for row in rows]


def mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def std(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def summarize_runs(summary_rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in summary_rows:
        grouped.setdefault(str(row["method"]), []).append(row)

    averaged_rows: list[dict] = []
    for method, rows in sorted(grouped.items()):
        exact = [float(row["mean_exact_set_match"]) for row in rows]
        jaccard = [float(row["mean_jaccard"]) for row in rows]
        precision = [float(row["mean_multilabel_precision"]) for row in rows]
        recall = [float(row["mean_multilabel_recall"]) for row in rows]
        f1 = [float(row["mean_multilabel_f1"]) for row in rows]
        averaged_rows.append(
            {
                "method": method,
                "num_runs": len(rows),
                "avg_num_patterns": mean([float(row["num_patterns"]) for row in rows]),
                "avg_num_pattern_occurrences": mean([float(row["num_pattern_occurrences"]) for row in rows]),
                "mean_exact_set_match": mean(exact),
                "std_exact_set_match": std(exact),
                "mean_jaccard": mean(jaccard),
                "std_jaccard": std(jaccard),
                "mean_multilabel_precision": mean(precision),
                "std_multilabel_precision": std(precision),
                "mean_multilabel_recall": mean(recall),
                "std_multilabel_recall": std(recall),
                "mean_multilabel_f1": mean(f1),
                "std_multilabel_f1": std(f1),
            }
        )
    return averaged_rows


def load_truth_intervals(args: argparse.Namespace):
    if args.labeled_casas is not None and args.labeled_casas.exists():
        return (
            parse_labeled_casas_intervals(
                args.labeled_casas,
                wake_window_minutes=args.wake_window_minutes,
            ),
            str(args.labeled_casas),
        )
    if args.adl_intervals.exists():
        return load_adl_intervals_csv(args.adl_intervals), str(args.adl_intervals)
    raise FileNotFoundError(
        f"--adl-intervals does not exist: {args.adl_intervals}. "
        "Provide --labeled-casas as a fallback."
    )


def main() -> None:
    args = parse_args()
    if args.runs < 1:
        raise ValueError("--runs must be >= 1")
    output_suffix = condition_suffix(
        args.days,
        args.n_states,
        args.hamming_threshold,
    )
    args.output_dir = resolve_output_dir(args.output_dir, output_suffix)
    if not args.state_series.exists():
        raise FileNotFoundError(f"--state-series does not exist: {args.state_series}")

    state_intervals = load_state_series_csv(args.state_series)
    adl_intervals, adl_source = load_truth_intervals(args)

    all_detail_rows: list[dict] = []
    run_summary_rows: list[dict] = []
    skipped_runs: list[dict] = []

    for run in range(1, args.runs + 1):
        method_specs = [
            (
                "proposed",
                path_for_run(args.patterns_proposed, run, args.patterns_proposed_template),
            ),
            (
                "direct_log_baseline",
                path_for_run(args.patterns_direct, run, args.patterns_direct_template),
            ),
        ]
        for method, patterns_path in method_specs:
            if not patterns_path.exists():
                skipped = {
                    "run": run,
                    "method": method,
                    "patterns_path": str(patterns_path),
                    "reason": "pattern_file_missing",
                }
                if args.skip_missing_runs:
                    skipped_runs.append(skipped)
                    continue
                raise FileNotFoundError(
                    f"{method} run {run} pattern file does not exist: {patterns_path}. "
                    "Use --skip-missing-runs to skip missing files."
                )

            detail_rows, summary_metrics = evaluate_method(
                method=method,
                patterns_path=patterns_path,
                state_intervals=state_intervals,
                adl_intervals=adl_intervals,
                args=args,
            )
            detail_rows = add_run_to_rows(run, detail_rows)
            summary_metrics = {"run": run, **summary_metrics}
            all_detail_rows.extend(detail_rows)
            run_summary_rows.append(summary_metrics)

    summary_rows = summarize_runs(run_summary_rows)
    pred_label_rows = []
    true_label_rows = []
    time_band_rows = []
    for method in sorted({row["method"] for row in all_detail_rows}):
        method_detail_rows = [row for row in all_detail_rows if row["method"] == method]
        pred_label_rows.extend(
            add_method_to_label_rows(
                method,
                aggregate_by_label(method_detail_rows, "pred_adl_labels", "pred_label"),
            )
        )
        true_label_rows.extend(
            add_method_to_label_rows(
                method,
                aggregate_by_label(method_detail_rows, "true_adl_labels", "true_label"),
            )
        )
        time_band_rows.extend(
            add_method_to_label_rows(
                method,
                aggregate_by_time_band(method_detail_rows),
            )
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_rows(
        args.output_dir / "evaluation6_method_comparison.csv",
        summary_rows,
        MEAN_SUMMARY_FIELDNAMES,
    )
    write_csv_rows(
        args.output_dir / "evaluation6_method_comparison_by_run.csv",
        run_summary_rows,
        SUMMARY_FIELDNAMES,
    )
    write_csv_rows(
        args.output_dir / "evaluation6_pattern_set_details_by_method.csv",
        all_detail_rows,
        DETAIL_FIELDNAMES,
    )
    write_csv_rows(
        args.output_dir / "evaluation6_by_pred_label_by_method.csv",
        pred_label_rows,
        ["method", "pred_label", "num_patterns", "mean_jaccard", "mean_multilabel_precision", "mean_multilabel_recall", "mean_multilabel_f1"],
    )
    write_csv_rows(
        args.output_dir / "evaluation6_by_true_label_by_method.csv",
        true_label_rows,
        ["method", "true_label", "num_patterns", "mean_jaccard", "mean_multilabel_precision", "mean_multilabel_recall", "mean_multilabel_f1"],
    )
    write_csv_rows(
        args.output_dir / "evaluation6_by_time_band_by_method.csv",
        time_band_rows,
        [
            "method",
            "time_band",
            "num_patterns",
            "mean_exact_set_match",
            "mean_jaccard",
            "mean_multilabel_precision",
            "mean_multilabel_recall",
            "mean_multilabel_f1",
        ],
    )

    summary_payload = {
        "patterns_proposed": str(args.patterns_proposed),
        "patterns_proposed_template": args.patterns_proposed_template,
        "patterns_direct": str(args.patterns_direct),
        "patterns_direct_template": args.patterns_direct_template,
        "runs_requested": args.runs,
        "skip_missing_runs": args.skip_missing_runs,
        "skipped_runs": skipped_runs,
        "days": args.days,
        "n_states": args.n_states,
        "hamming_threshold": args.hamming_threshold,
        "state_series": str(args.state_series),
        "adl_intervals": adl_source,
        "allowed_labels": ALLOWED_LABELS,
        "min_overlap_ratio_for_true_label": args.min_overlap_ratio_for_true_label,
        "no_overlap_label": args.no_overlap_label,
        "missing_pred_label": args.missing_pred_label,
        "unknown_pred_label": args.unknown_pred_label,
        "match_mode": args.match_mode,
        "max_skip_duration_minutes": args.max_skip_duration_minutes,
        "evaluation_type": "set_only_method_comparison",
        "order_sensitive": False,
        "time_band_aware": True,
        "methods": {row["method"]: row for row in summary_rows},
        "method_runs": run_summary_rows,
        "by_time_band": time_band_rows,
    }
    (args.output_dir / "evaluation6_comparison_summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Evaluation 6 comparison outputs saved to: {args.output_dir}")
    for row in summary_rows:
        print(
            f"{row['method']}: runs={row['num_runs']}, "
            f"avg_patterns={row['avg_num_patterns']:.3f}, "
            f"avg_occurrences={row['avg_num_pattern_occurrences']:.3f}, "
            f"mean_jaccard={row['mean_jaccard']:.6f}, "
            f"mean_f1={row['mean_multilabel_f1']:.6f}"
        )
    if skipped_runs:
        print(f"Skipped method/runs: {len(skipped_runs)}")


if __name__ == "__main__":
    main()
