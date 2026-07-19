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
from src.behavior_pattern_mining.evaluation.llm_usage import (
    LLM_USAGE_COMPARISON_FIELDNAMES,
    load_direct_usage_by_run,
    load_proposed_run_usage,
    summarize_usage,
)


EVAL6_DAYS = 14

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
    "num_matching_occurrences_before_time_band_filter",
    "num_time_band_assigned_occurrences",
    "num_boundary_crossing_occurrences",
    "num_boundary_crossing_occurrences_excluded",
    "occurrence_status",
    "truth_status",
    "prediction_status",
    "is_metric_evaluable",
    "is_end_to_end_evaluable",
    "raw_pred_adl_labels",
    "pred_adl_labels",
    "unknown_pred_adl_labels",
    "unknown_pred_label_count",
    "true_adl_labels",
    "intersection_labels",
    "union_labels",
    "exact_set_match",
    "jaccard",
    "multilabel_precision",
    "multilabel_recall",
    "multilabel_f1",
    "conditional_exact_set_match",
    "conditional_jaccard",
    "conditional_multilabel_precision",
    "conditional_multilabel_recall",
    "conditional_multilabel_f1",
    "end_to_end_exact_set_match",
    "end_to_end_jaccard",
    "end_to_end_multilabel_precision",
    "end_to_end_multilabel_recall",
    "end_to_end_multilabel_f1",
    "total_overlap_seconds",
    "true_label_overlap_detail",
]

STATUS_SUMMARY_FIELDNAMES = [
    "num_conditional_evaluable_patterns",
    "num_end_to_end_evaluable_patterns",
    "num_occurrence_matched",
    "num_no_occurrence",
    "num_truth_defined",
    "num_no_adl_overlap",
    "num_prediction_valid",
    "num_prediction_missing",
    "num_prediction_unknown",
    "unknown_pred_label_count",
    "occurrence_coverage",
    "truth_coverage",
    "no_occurrence_rate",
    "no_adl_overlap_rate",
    "missing_prediction_rate",
    "unknown_label_rate",
    "num_time_band_assigned_occurrences",
    "num_boundary_crossing_occurrences",
    "num_boundary_crossing_occurrences_excluded",
    "boundary_crossing_occurrence_rate",
]

EXPLICIT_METRIC_SUMMARY_FIELDNAMES = [
    f"{scope}_mean_{metric}"
    for scope in ("conditional", "end_to_end")
    for metric in (
        "exact_set_match",
        "jaccard",
        "multilabel_precision",
        "multilabel_recall",
        "multilabel_f1",
    )
]

AGGREGATE_SUMMARY_FIELDNAMES = [
    "num_patterns",
    *STATUS_SUMMARY_FIELDNAMES,
    "mean_exact_set_match",
    "mean_jaccard",
    "mean_multilabel_precision",
    "mean_multilabel_recall",
    "mean_multilabel_f1",
    *EXPLICIT_METRIC_SUMMARY_FIELDNAMES,
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
    *STATUS_SUMMARY_FIELDNAMES,
    *EXPLICIT_METRIC_SUMMARY_FIELDNAMES,
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
    *[
        field
        for name in STATUS_SUMMARY_FIELDNAMES
        for field in (
            f"avg_{name}" if name.startswith("num_") or name.endswith("_count") else f"mean_{name}",
            f"std_{name}",
        )
    ],
    *[
        field
        for scope in ("conditional", "end_to_end")
        for metric in (
            "exact_set_match",
            "jaccard",
            "multilabel_precision",
            "multilabel_recall",
            "multilabel_f1",
        )
        for field in (f"{scope}_mean_{metric}", f"{scope}_std_{metric}")
    ],
]


def default_output_root() -> Path:
    return ROOT_DIR / "results" / "6_adl_match"


def condition_suffix(days: int, n_states: int | None, hamming_threshold: int | None) -> str:
    resolved_n_states = n_states if n_states is not None else N_STATES
    resolved_hamming = hamming_threshold if hamming_threshold is not None else HAMMING_THRESHOLD
    return f"{resolved_n_states}_{resolved_hamming}_{days}days"


def resolve_output_dir(output_dir: Path | None, suffix: str) -> Path:
    """Resolve the final condition-specific result directory.

    Passing results/6_adl_match writes into its
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
            "Use {run}, e.g. output/aruba_15_1_14days/llm_sequences_modes_15_1_14days_{run}.json"
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
            "Use {run}, e.g. output/llm_direct_15_1_14days/{run}.json"
        ),
    )
    parser.add_argument(
        "--proposed-metrics-template",
        type=str,
        default=None,
        help=(
            "Optional proposed-method metrics path template. Use {run}. "
            "By default, llm_modes_metrics_{K}_{hamming}_{days}days_run{run}.csv "
            "is read beside --patterns-proposed."
        ),
    )
    parser.add_argument(
        "--direct-metrics",
        type=Path,
        default=None,
        help=(
            "Optional direct-baseline metrics CSV. By default, "
            "llm_direct_metrics_{days}days.csv is read beside --patterns-direct."
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
            "When omitted, or when results/6_adl_match is passed, "
            "outputs are written to results/6_adl_match/{K}_{hamming}_{days}days."
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
        help="Deprecated compatibility option; no-overlap is now a truth status",
    )
    parser.add_argument(
        "--missing-pred-label",
        choices=["Other", "Ambiguous"],
        default="Ambiguous",
        help="Deprecated compatibility option; missing prediction is now a status",
    )
    parser.add_argument(
        "--unknown-pred-label",
        choices=["Other", "Ambiguous"],
        default="Other",
        help="Deprecated compatibility option; unknown prediction is now a status",
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


def proposed_metrics_path_for_run(
    patterns_path: Path,
    run: int,
    template: str | None,
    condition: str,
) -> Path:
    if template:
        return Path(template.format(run=run))
    return patterns_path.parent / f"llm_modes_metrics_{condition}_run{run}.csv"


def direct_metrics_path(patterns_path: Path, explicit_path: Path | None, days: int) -> Path:
    if explicit_path is not None:
        return explicit_path
    return patterns_path.parent / f"llm_direct_metrics_{days}days.csv"


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
        "num_pattern_occurrences": sum(
            int(row.get("num_occurrences") or 0)
            for row in detail_rows
        ),
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
        averaged: dict[str, float | int | str] = {
            "method": method,
            "num_runs": len(rows),
            "avg_num_patterns": mean([float(row["num_patterns"]) for row in rows]),
            "avg_num_pattern_occurrences": mean(
                [float(row["num_pattern_occurrences"]) for row in rows]
            ),
        }
        for metric in (
            "exact_set_match",
            "jaccard",
            "multilabel_precision",
            "multilabel_recall",
            "multilabel_f1",
        ):
            values = [float(row[f"mean_{metric}"]) for row in rows]
            averaged[f"mean_{metric}"] = mean(values)
            averaged[f"std_{metric}"] = std(values)
            for scope in ("conditional", "end_to_end"):
                scoped_values = [
                    float(row[f"{scope}_mean_{metric}"])
                    for row in rows
                ]
                averaged[f"{scope}_mean_{metric}"] = mean(scoped_values)
                averaged[f"{scope}_std_{metric}"] = std(scoped_values)

        for name in STATUS_SUMMARY_FIELDNAMES:
            values = [float(row[name]) for row in rows]
            if name.startswith("num_") or name.endswith("_count"):
                averaged[f"avg_{name}"] = mean(values)
            else:
                averaged[f"mean_{name}"] = mean(values)
            averaged[f"std_{name}"] = std(values)
        averaged_rows.append(averaged)
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
    evaluated_runs_by_method = {
        method: sorted(
            {
                int(row["run"])
                for row in run_summary_rows
                if row["method"] == method
            }
        )
        for method in ("proposed", "direct_log_baseline")
    }
    llm_usage_run_rows: list[dict] = []
    missing_llm_usage: list[dict] = []

    for run in evaluated_runs_by_method["proposed"]:
        patterns_path = path_for_run(
            args.patterns_proposed,
            run,
            args.patterns_proposed_template,
        )
        metrics_path = proposed_metrics_path_for_run(
            patterns_path,
            run,
            args.proposed_metrics_template,
            output_suffix,
        )
        usage, reason = load_proposed_run_usage(metrics_path, run)
        if usage is not None:
            llm_usage_run_rows.append(usage)
        else:
            missing_llm_usage.append(
                {
                    "method": "proposed",
                    "run": run,
                    "source_path": str(metrics_path),
                    "reason": reason,
                }
            )

    resolved_direct_metrics_path = direct_metrics_path(
        args.patterns_direct,
        args.direct_metrics,
        args.days,
    )
    direct_usage_rows, direct_missing_rows = load_direct_usage_by_run(
        resolved_direct_metrics_path,
        evaluated_runs_by_method["direct_log_baseline"],
    )
    llm_usage_run_rows.extend(direct_usage_rows)
    missing_llm_usage.extend(direct_missing_rows)
    llm_usage_summary_rows = [
        summarize_usage(
            method,
            evaluated_runs_by_method[method],
            llm_usage_run_rows,
        )
        for method in ("proposed", "direct_log_baseline")
    ]

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
        args.output_dir / "evaluation6_llm_usage_comparison.csv",
        llm_usage_summary_rows,
        LLM_USAGE_COMPARISON_FIELDNAMES,
    )
    write_csv_rows(
        args.output_dir / "evaluation6_pattern_set_details_by_method.csv",
        all_detail_rows,
        DETAIL_FIELDNAMES,
    )
    write_csv_rows(
        args.output_dir / "evaluation6_by_pred_label_by_method.csv",
        pred_label_rows,
        ["method", "pred_label", *AGGREGATE_SUMMARY_FIELDNAMES],
    )
    write_csv_rows(
        args.output_dir / "evaluation6_by_true_label_by_method.csv",
        true_label_rows,
        ["method", "true_label", *AGGREGATE_SUMMARY_FIELDNAMES],
    )
    write_csv_rows(
        args.output_dir / "evaluation6_by_time_band_by_method.csv",
        time_band_rows,
        ["method", "time_band", *AGGREGATE_SUMMARY_FIELDNAMES],
    )

    summary_payload = {
        "patterns_proposed": str(args.patterns_proposed),
        "patterns_proposed_template": args.patterns_proposed_template,
        "patterns_direct": str(args.patterns_direct),
        "patterns_direct_template": args.patterns_direct_template,
        "proposed_metrics_template": args.proposed_metrics_template,
        "direct_metrics": str(resolved_direct_metrics_path),
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
        "deprecated_compatibility_options_ignored": {
            "no_overlap_label": args.no_overlap_label,
            "missing_pred_label": args.missing_pred_label,
            "unknown_pred_label": args.unknown_pred_label,
        },
        "match_mode": args.match_mode,
        "max_skip_duration_minutes": args.max_skip_duration_minutes,
        "evaluation_type": "set_only_method_comparison",
        "order_sensitive": False,
        "time_band_aware": True,
        "time_band_occurrence_policy": (
            "sequence_x_time_band records require the full half-open occurrence "
            "[start,end) to remain in the requested time band"
        ),
        "conditional_metric_denominator": (
            "occurrence_status=matched and truth_status=defined; prediction "
            "missing/unknown remain in denominator with zero score"
        ),
        "end_to_end_metric_denominator": (
            "all records except matched records with truth_status=no_adl_overlap; "
            "no_occurrence and prediction missing/unknown remain with zero score"
        ),
        "no_adl_overlap_end_to_end_policy": "excluded_truth_undefined",
        "legacy_mean_metric_alias": "end_to_end",
        "methods": {row["method"]: row for row in summary_rows},
        "method_runs": run_summary_rows,
        "by_time_band": time_band_rows,
        "llm_usage_comparison": {
            "aggregation": (
                "Sum recorded successful API calls within each run, then average "
                "the run totals across runs with complete metrics."
            ),
            "duration_scope": "Gemini API response duration only",
            "run_rows": llm_usage_run_rows,
            "methods": {
                row["method"]: row
                for row in llm_usage_summary_rows
            },
            "missing_metrics": missing_llm_usage,
        },
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
        if float(row.get("avg_num_prediction_unknown") or 0) > 0:
            print(
                f"[WARN] {row['method']}: average unknown-label records per run="
                f"{float(row['avg_num_prediction_unknown']):.3f}, "
                f"unknown label rate={float(row['mean_unknown_label_rate']):.6f}",
                file=sys.stderr,
            )
    for row in llm_usage_summary_rows:
        print(
            f"{row['method']} usage: "
            f"complete_runs={row['num_runs_with_complete_metrics']}/"
            f"{row['num_runs_evaluated']}, "
            f"avg_total_tokens={row['avg_total_tokens_per_run']}, "
            f"avg_api_response_sec={row['avg_api_response_duration_sec_per_run']}"
        )
    if skipped_runs:
        print(f"Skipped method/runs: {len(skipped_runs)}")


if __name__ == "__main__":
    main()
