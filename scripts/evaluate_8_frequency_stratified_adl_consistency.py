#!/usr/bin/env python3
"""Evaluation 8: frequency-stratified analysis of Evaluation 6 ADL set metrics."""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

ROOT_DIR_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(ROOT_DIR_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR_FOR_IMPORTS))

from experiment_config import ROOT_DIR
from scripts.evaluate_6_compare_adl_interpretation_set import (
    evaluate_method,
    load_truth_intervals,
    path_for_run,
)
from src.behavior_pattern_mining.evaluation.adl import (
    PatternRecord,
    find_pattern_occurrences,
    load_state_series_csv,
    write_csv_rows,
)
from src.behavior_pattern_mining.evaluation.adl_interpretation_set import (
    parse_sequence,
    time_band_for_timestamp,
)


FREQUENCY_BANDS = ("Low", "Middle", "High")
DEFAULT_FIXED_FREQUENCY_BIN_EDGES = (0, 1, 10, 100, 1000, 10000)
COMPARISON_SCOPES = {"comparison_14days", "comparison_30days"}
DETAIL_FIELDNAMES = [
    "run",
    "method",
    "eval_pattern_id",
    "group_pattern_id",
    "sequence",
    "time_band",
    "pattern_name",
    "num_occurrences",
    "frequency_band",
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
    "frequency_band",
    "num_runs",
    "num_patterns",
    "min_occurrences",
    "max_occurrences",
    "mean_occurrences",
    "median_occurrences",
    "mean_exact_set_match",
    "mean_jaccard",
    "mean_multilabel_precision",
    "mean_multilabel_recall",
    "mean_multilabel_f1",
    "weighted_jaccard",
    "weighted_multilabel_precision",
    "weighted_multilabel_recall",
    "weighted_multilabel_f1",
]
METHOD_SUMMARY_FIELDNAMES = ["method", *SUMMARY_FIELDNAMES]
OCCURRENCE_WEIGHTED_FIELDNAMES = [
    "method",
    "num_runs",
    "num_patterns",
    "total_occurrences",
    "weighted_jaccard",
    "weighted_multilabel_precision",
    "weighted_multilabel_recall",
    "weighted_multilabel_f1",
]
METRIC_COLUMNS = (
    "exact_set_match",
    "jaccard",
    "multilabel_precision",
    "multilabel_recall",
    "multilabel_f1",
)


def default_output_dir(analysis_scope: str) -> Path:
    directory_name = "8_vs_llm" if analysis_scope in COMPARISON_SCOPES else "8_proposed"
    return ROOT_DIR / "results" / directory_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stratify Evaluation 6 ADL label set-consistency records by "
            "pattern occurrence frequency."
        )
    )
    parser.add_argument(
        "--evaluation6-details",
        type=Path,
        help="Evaluation 6 detail CSV, with or without the newer num_occurrences column.",
    )
    parser.add_argument(
        "--analysis-scope",
        choices=["comparison_14days", "comparison_30days", "proposed_154days"],
        default="comparison_14days",
        help=(
            "comparison_14days stratifies an existing proposed/direct 14-day Evaluation 6 detail CSV; "
            "comparison_30days remains available for previously generated 30-day details; "
            "proposed_154days evaluates only the proposed 154-day JSON before stratification."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for Evaluation 8 CSV and JSON outputs. Defaults by analysis scope.",
    )
    parser.add_argument(
        "--frequency-band-mode",
        choices=["tertile", "fixed"],
        default="tertile",
        help=(
            "Frequency stratification mode. tertile assigns near-equal record counts per method; "
            "fixed assigns numeric num_occurrences ranges."
        ),
    )
    parser.add_argument(
        "--fixed-frequency-bin-edges",
        default=",".join(str(edge) for edge in DEFAULT_FIXED_FREQUENCY_BIN_EDGES),
        help=(
            "Comma- or space-separated inclusive lower bounds for --frequency-band-mode fixed. "
            "Default: 0,1,10,100,1000,10000, producing 0, 1-9, ..., 10000+."
        ),
    )
    parser.add_argument(
        "--write-distribution-plots",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Write fixed-range distribution and metric PNG plots for proposed_154days. "
            "Default: enabled; use --no-write-distribution-plots to disable."
        ),
    )
    parser.add_argument(
        "--state-series",
        type=Path,
        default=None,
        help=(
            "Representative-state interval CSV used only when the Evaluation 6 details "
            "lack num_occurrences. By default, it is read from the sibling Evaluation 6 summary JSON."
        ),
    )
    parser.add_argument(
        "--match-mode",
        choices=["exact", "skip-other"],
        default=None,
        help="Occurrence search mode when num_occurrences must be reconstructed.",
    )
    parser.add_argument(
        "--max-skip-duration-minutes",
        type=float,
        default=None,
        help="Maximum skipped その他-state duration when reconstructing occurrence counts.",
    )
    parser.add_argument(
        "--patterns-proposed",
        type=Path,
        default=None,
        help="Proposed-method LLM pattern JSON. Required for --analysis-scope proposed_154days.",
    )
    parser.add_argument(
        "--patterns-proposed-template",
        type=str,
        default=None,
        help="Optional 154-day proposed JSON template containing {run}.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of proposed-method extraction runs for proposed_154days. Default: 5.",
    )
    parser.add_argument(
        "--n-states",
        type=int,
        default=None,
        help="Representative-state count recorded for this Evaluation 8 condition.",
    )
    parser.add_argument(
        "--hamming-threshold",
        type=int,
        default=None,
        help="Hamming threshold recorded for this Evaluation 8 condition.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Log-day count recorded for this Evaluation 8 condition.",
    )
    parser.add_argument(
        "--adl-intervals",
        type=Path,
        default=ROOT_DIR / "output" / "adl_label_intervals.csv",
        help="ADL truth interval CSV used only for --analysis-scope proposed_154days.",
    )
    parser.add_argument(
        "--labeled-casas",
        type=Path,
        default=None,
        help="Labeled CASAS input used for proposed_154days; takes precedence over --adl-intervals.",
    )
    parser.add_argument(
        "--min-overlap-ratio-for-true-label",
        type=float,
        default=0.10,
        help="Evaluation 6 true-label overlap threshold for proposed_154days.",
    )
    parser.add_argument(
        "--no-overlap-label",
        choices=["Other", "Ambiguous"],
        default="Ambiguous",
        help="Evaluation 6 true label for no overlap in proposed_154days.",
    )
    parser.add_argument(
        "--missing-pred-label",
        choices=["Other", "Ambiguous"],
        default="Ambiguous",
        help="Evaluation 6 fallback predicted label in proposed_154days.",
    )
    parser.add_argument(
        "--unknown-pred-label",
        choices=["Other", "Ambiguous"],
        default="Other",
        help="Evaluation 6 normalization fallback in proposed_154days.",
    )
    parser.add_argument(
        "--wake-window-minutes",
        type=float,
        default=30.0,
        help="Wake-up relabel window used for --labeled-casas in proposed_154days.",
    )
    return parser.parse_args()


def as_float(value: Any, column: str, row_number: int) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Row {row_number} has an invalid {column!r}: {value!r}") from exc


def as_occurrence_count(value: Any, row_number: int) -> int:
    numeric = as_float(value, "num_occurrences", row_number)
    if numeric < 0 or not numeric.is_integer():
        raise ValueError(f"Row {row_number} has an invalid num_occurrences: {value!r}")
    return int(numeric)


def parse_fixed_frequency_bin_edges(value: str) -> tuple[int, ...]:
    """Parse validated lower bounds for fixed occurrence-frequency ranges."""
    try:
        edges = tuple(int(item) for item in value.replace(",", " ").split())
    except ValueError as exc:
        raise ValueError("--fixed-frequency-bin-edges must contain integers") from exc
    if len(edges) < 2 or edges[0] != 0 or any(edge < 0 for edge in edges):
        raise ValueError("--fixed-frequency-bin-edges must start at 0 and contain at least two non-negative bounds")
    if any(later <= earlier for earlier, later in zip(edges, edges[1:])):
        raise ValueError("--fixed-frequency-bin-edges must be strictly increasing")
    return edges


def fixed_frequency_band_labels(edges: Sequence[int]) -> tuple[str, ...]:
    labels = []
    for lower, upper in zip(edges, edges[1:]):
        labels.append(str(lower) if upper == lower + 1 else f"{lower}-{upper - 1}")
    labels.append(f"{edges[-1]}+")
    return tuple(labels)


def frequency_bands_for_mode(mode: str, fixed_edges: Sequence[int]) -> tuple[str, ...]:
    if mode == "tertile":
        return FREQUENCY_BANDS
    if mode == "fixed":
        return fixed_frequency_band_labels(fixed_edges)
    raise ValueError(f"Unsupported frequency band mode: {mode}")


def evaluation6_summary_payload(details_path: Path) -> dict[str, Any]:
    for filename in ("evaluation6_comparison_summary.json", "evaluation6_summary.json"):
        candidate = details_path.parent / filename
        if candidate.exists():
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
    return {}


def resolve_existing_path(value: str | Path, details_path: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    for candidate in (ROOT_DIR / path, details_path.parent / path):
        if candidate.exists():
            return candidate
    return ROOT_DIR / path


def attach_reconstructed_occurrences(
    rows: list[dict[str, Any]],
    details_path: Path,
    args: argparse.Namespace,
) -> str:
    summary = evaluation6_summary_payload(details_path)
    configured_state_series = args.state_series or summary.get("state_series")
    if not configured_state_series:
        raise ValueError(
            "The Evaluation 6 details lack num_occurrences and no sibling Evaluation 6 summary "
            "provides state_series. Pass --state-series to reconstruct the counts."
        )
    state_series_path = resolve_existing_path(configured_state_series, details_path)
    if not state_series_path.exists():
        raise FileNotFoundError(f"State series for num_occurrences does not exist: {state_series_path}")

    match_mode = args.match_mode or str(summary.get("match_mode") or "exact")
    max_skip_duration = (
        args.max_skip_duration_minutes
        if args.max_skip_duration_minutes is not None
        else float(summary.get("max_skip_duration_minutes") or 1.0)
    )
    if max_skip_duration < 0:
        raise ValueError("--max-skip-duration-minutes must be >= 0")

    records_by_key: dict[tuple[str, str, str], PatternRecord] = {}
    row_keys: list[tuple[str, str, str]] = []
    for index, row in enumerate(rows):
        sequence = parse_sequence(row.get("sequence"))
        if len(sequence) < 2:
            raise ValueError(f"Row {index + 2} has no usable state sequence for num_occurrences")
        eval_pattern_id = str(row.get("eval_pattern_id") or row.get("pattern_id") or f"row_{index + 1}")
        key = (str(row["method"]), eval_pattern_id, "->".join(sequence))
        row_keys.append(key)
        records_by_key.setdefault(
            key,
            PatternRecord(
                pattern_id="::".join(key),
                pattern_name=str(row.get("pattern_name") or eval_pattern_id),
                sequence=sequence,
            ),
        )

    matches = find_pattern_occurrences(
        list(records_by_key.values()),
        load_state_series_csv(state_series_path),
        match_mode=match_mode,
        max_skip_duration_minutes=max_skip_duration,
    )
    matches_by_pattern_id: dict[str, list[Any]] = defaultdict(list)
    for match in matches:
        matches_by_pattern_id[str(match.pattern_id)].append(match)

    for row, key in zip(rows, row_keys):
        relevant = matches_by_pattern_id.get(records_by_key[key].pattern_id, [])
        time_band = str(row.get("time_band") or "All")
        if time_band != "All":
            relevant = [match for match in relevant if time_band_for_timestamp(match.start_time) == time_band]
        row["num_occurrences"] = len(relevant)
    return str(state_series_path)


def load_details(path: Path, args: argparse.Namespace) -> tuple[list[dict[str, Any]], str]:
    if not path.exists():
        raise FileNotFoundError(f"--evaluation6-details does not exist: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        missing_metrics = [column for column in METRIC_COLUMNS if column not in fieldnames]
        if missing_metrics:
            raise ValueError(f"{path} is missing Evaluation 6 metric columns: {', '.join(missing_metrics)}")

        rows = []
        for row_number, raw_row in enumerate(reader, start=2):
            row = dict(raw_row)
            row["run"] = int(row.get("run") or 1)
            row["method"] = str(row.get("method") or "all")
            if "num_occurrences" in fieldnames:
                row["num_occurrences"] = as_occurrence_count(row.get("num_occurrences"), row_number)
            for column in METRIC_COLUMNS:
                row[column] = as_float(row.get(column), column, row_number)
            rows.append(row)
    if "num_occurrences" in fieldnames:
        return rows, "evaluation6_details"
    return rows, f"reconstructed_from_state_series:{attach_reconstructed_occurrences(rows, path, args)}"


def evaluate_proposed_154days(args: argparse.Namespace) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    if args.patterns_proposed is None:
        raise ValueError("--patterns-proposed is required for --analysis-scope proposed_154days")
    if args.state_series is None:
        raise ValueError("--state-series is required for --analysis-scope proposed_154days")
    if not args.state_series.exists():
        raise FileNotFoundError(f"--state-series does not exist: {args.state_series}")
    if args.runs < 1:
        raise ValueError("--runs must be >= 1")

    args.match_mode = args.match_mode or "exact"
    args.max_skip_duration_minutes = (
        args.max_skip_duration_minutes if args.max_skip_duration_minutes is not None else 1.0
    )

    state_intervals = load_state_series_csv(args.state_series)
    adl_intervals, adl_source = load_truth_intervals(args)
    detail_rows: list[dict[str, Any]] = []
    run_summaries = []
    pattern_paths = []
    for run in range(1, args.runs + 1):
        patterns_path = path_for_run(args.patterns_proposed, run, args.patterns_proposed_template)
        run_rows, evaluation6_summary = evaluate_method(
            method="proposed",
            patterns_path=patterns_path,
            state_intervals=state_intervals,
            adl_intervals=adl_intervals,
            args=args,
        )
        detail_rows.extend({"run": run, **row} for row in run_rows)
        run_summaries.append({"run": run, **evaluation6_summary})
        pattern_paths.append(str(patterns_path))
    return (
        detail_rows,
        "computed_from_proposed_154day_inputs",
        {
            "patterns_proposed": pattern_paths,
            "runs_requested": args.runs,
            "state_series": str(args.state_series),
            "adl_intervals": adl_source,
            "evaluation6_summaries_by_run": run_summaries,
        },
    )


def stable_record_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        float(row["num_occurrences"]),
        str(row.get("eval_pattern_id") or row.get("pattern_id") or ""),
        str(row.get("group_pattern_id") or ""),
        str(row.get("sequence") or ""),
        str(row.get("time_band") or ""),
        str(row.get("run") or ""),
    )


def assign_frequency_bands(
    rows: list[dict[str, Any]],
    mode: str = "tertile",
    fixed_edges: Sequence[int] = DEFAULT_FIXED_FREQUENCY_BIN_EDGES,
) -> None:
    """Assign near-equal tertiles independently within each method and run.

    Ties are resolved by stable identifiers, rather than splitting at a raw
    quantile value. This keeps every record assigned and makes reruns stable.
    """
    if mode == "fixed":
        labels = fixed_frequency_band_labels(fixed_edges)
        for row in rows:
            index = bisect.bisect_right(fixed_edges, int(row["num_occurrences"])) - 1
            row["frequency_band"] = labels[index]
        return
    if mode != "tertile":
        raise ValueError(f"Unsupported frequency band mode: {mode}")

    by_method_run: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_method_run[(str(row["method"]), int(row.get("run") or 1))].append(row)

    for method_rows in by_method_run.values():
        ordered = sorted(method_rows, key=stable_record_key)
        base, remainder = divmod(len(ordered), len(FREQUENCY_BANDS))
        counts = [base + (index < remainder) for index in range(len(FREQUENCY_BANDS))]
        start = 0
        for band, count in zip(FREQUENCY_BANDS, counts):
            for row in ordered[start : start + count]:
                row["frequency_band"] = band
            start += count


def mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def weighted_mean(rows: Sequence[dict[str, Any]], column: str) -> float:
    total_occurrences = sum(float(row["num_occurrences"]) for row in rows)
    if total_occurrences <= 0:
        return 0.0
    return sum(float(row[column]) * float(row["num_occurrences"]) for row in rows) / total_occurrences


def summarize_rows(rows: Sequence[dict[str, Any]], frequency_band: str) -> dict[str, Any]:
    occurrences = [float(row["num_occurrences"]) for row in rows]
    return {
        "frequency_band": frequency_band,
        "num_runs": 1,
        "num_patterns": len(rows),
        "min_occurrences": min(occurrences) if occurrences else 0.0,
        "max_occurrences": max(occurrences) if occurrences else 0.0,
        "mean_occurrences": mean(occurrences),
        "median_occurrences": statistics.median(occurrences) if occurrences else 0.0,
        "mean_exact_set_match": mean([float(row["exact_set_match"]) for row in rows]),
        "mean_jaccard": mean([float(row["jaccard"]) for row in rows]),
        "mean_multilabel_precision": mean([float(row["multilabel_precision"]) for row in rows]),
        "mean_multilabel_recall": mean([float(row["multilabel_recall"]) for row in rows]),
        "mean_multilabel_f1": mean([float(row["multilabel_f1"]) for row in rows]),
        "weighted_jaccard": weighted_mean(rows, "jaccard"),
        "weighted_multilabel_precision": weighted_mean(rows, "multilabel_precision"),
        "weighted_multilabel_recall": weighted_mean(rows, "multilabel_recall"),
        "weighted_multilabel_f1": weighted_mean(rows, "multilabel_f1"),
    }


def mean_run_summaries(run_summaries: Sequence[dict[str, Any]], frequency_band: str) -> dict[str, Any]:
    """Average independently computed per-run band summaries.

    This makes five extraction runs contribute equally, instead of allowing a
    run with more extracted patterns or occurrences to dominate the result.
    """
    numeric_columns = [column for column in SUMMARY_FIELDNAMES if column not in {"frequency_band", "num_runs"}]
    return {
        "frequency_band": frequency_band,
        "num_runs": len(run_summaries),
        **{column: mean([float(summary[column]) for summary in run_summaries]) for column in numeric_columns},
    }


def summaries_by_frequency_band(
    rows: Sequence[dict[str, Any]], frequency_bands: Sequence[str] = FREQUENCY_BANDS
) -> list[dict[str, Any]]:
    summaries = []
    for band in frequency_bands:
        run_groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if row.get("frequency_band") == band:
                run_groups[(str(row["method"]), int(row.get("run") or 1))].append(row)
        if run_groups:
            summaries.append(mean_run_summaries([summarize_rows(group, band) for group in run_groups.values()], band))
    return summaries


def summaries_by_method_and_frequency_band(
    rows: Sequence[dict[str, Any]], frequency_bands: Sequence[str] = FREQUENCY_BANDS
) -> list[dict[str, Any]]:
    result = []
    methods = sorted({str(row["method"]) for row in rows})
    for method in methods:
        method_rows = [row for row in rows if row["method"] == method]
        for band in frequency_bands:
            run_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for row in method_rows:
                if row.get("frequency_band") == band:
                    run_groups[int(row.get("run") or 1)].append(row)
            if run_groups:
                result.append(
                    {"method": method, **mean_run_summaries([summarize_rows(group, band) for group in run_groups.values()], band)}
                )
    return result


def occurrence_weighted_summaries(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for method in sorted({str(row["method"]) for row in rows}):
        method_rows = [row for row in rows if row["method"] == method]
        run_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in method_rows:
            run_groups[int(row.get("run") or 1)].append(row)
        per_run = []
        for run_rows in run_groups.values():
            per_run.append(
                {
                    "num_patterns": len(run_rows),
                    "total_occurrences": sum(float(row["num_occurrences"]) for row in run_rows),
                    "weighted_jaccard": weighted_mean(run_rows, "jaccard"),
                    "weighted_multilabel_precision": weighted_mean(run_rows, "multilabel_precision"),
                    "weighted_multilabel_recall": weighted_mean(run_rows, "multilabel_recall"),
                    "weighted_multilabel_f1": weighted_mean(run_rows, "multilabel_f1"),
                }
            )
        result.append(
            {
                "method": method,
                "num_runs": len(per_run),
                **{column: mean([float(summary[column]) for summary in per_run]) for column in OCCURRENCE_WEIGHTED_FIELDNAMES if column not in {"method", "num_runs"}},
            }
        )
    return result


def detail_output_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{column: row.get(column, "") for column in DETAIL_FIELDNAMES} for row in rows]


def write_fixed_range_plots(
    output_dir: Path,
    summaries: Sequence[dict[str, Any]],
    frequency_bands: Sequence[str],
    rows: Sequence[dict[str, Any]],
) -> list[str]:
    """Write proposed-only fixed-range charts without changing CSV aggregation."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    by_band = {str(row["frequency_band"]): row for row in summaries}
    labels = list(frequency_bands)
    run_ids = {int(row.get("run") or 1) for row in rows}
    mean_patterns = [
        sum(1 for row in rows if row.get("frequency_band") == label) / len(run_ids)
        if run_ids
        else 0.0
        for label in labels
    ]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(labels, mean_patterns, color="#4C78A8")
    ax.set_xlabel("num_occurrences range")
    ax.set_ylabel("mean patterns per run")
    ax.set_title("Evaluation 8: fixed-range pattern-frequency distribution")
    ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    distribution_path = output_dir / "evaluation8_frequency_distribution.png"
    fig.savefig(distribution_path, dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    for column, label, color in (
        ("mean_multilabel_precision", "Precision", "#E45756"),
        ("mean_multilabel_recall", "Recall", "#54A24B"),
        ("mean_multilabel_f1", "F1", "#B279A2"),
    ):
        values = [float(by_band.get(band, {}).get(column, 0.0)) for band in labels]
        ax.plot(labels, values, marker="o", label=label, color=color)
    ax.set_xlabel("num_occurrences range")
    ax.set_ylabel("mean score per run")
    ax.set_ylim(0, 1)
    ax.set_title("Evaluation 8: ADL consistency by fixed frequency range")
    ax.tick_params(axis="x", rotation=35)
    ax.legend()
    fig.tight_layout()
    metrics_path = output_dir / "evaluation8_frequency_band_metrics.png"
    fig.savefig(metrics_path, dpi=160)
    plt.close(fig)
    return [distribution_path.name, metrics_path.name]


def main() -> None:
    args = parse_args()
    if args.output_dir is None:
        args.output_dir = default_output_dir(args.analysis_scope)
    if args.analysis_scope in COMPARISON_SCOPES:
        if args.evaluation6_details is None:
            raise ValueError("--evaluation6-details is required for a comparison analysis scope")
        rows, occurrence_count_source = load_details(args.evaluation6_details, args)
        input_summary = {"evaluation6_details": str(args.evaluation6_details)}
    else:
        rows, occurrence_count_source, input_summary = evaluate_proposed_154days(args)
    fixed_edges = parse_fixed_frequency_bin_edges(
        getattr(args, "fixed_frequency_bin_edges", ",".join(map(str, DEFAULT_FIXED_FREQUENCY_BIN_EDGES)))
    )
    frequency_bands = frequency_bands_for_mode(args.frequency_band_mode, fixed_edges)
    assign_frequency_bands(rows, args.frequency_band_mode, fixed_edges)

    overall_by_band = summaries_by_frequency_band(rows, frequency_bands)
    by_method_band = summaries_by_method_and_frequency_band(rows, frequency_bands)
    weighted_summary = occurrence_weighted_summaries(rows)
    methods = sorted({str(row["method"]) for row in rows})
    runs_evaluated = sorted({int(row.get("run") or 1) for row in rows})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_rows(args.output_dir / "evaluation8_frequency_band_details.csv", detail_output_rows(rows), DETAIL_FIELDNAMES)
    write_csv_rows(args.output_dir / "evaluation8_by_frequency_band.csv", overall_by_band, SUMMARY_FIELDNAMES)
    output_files = [
        "evaluation8_frequency_band_details.csv",
        "evaluation8_by_frequency_band.csv",
    ]
    if args.analysis_scope in COMPARISON_SCOPES:
        write_csv_rows(
            args.output_dir / "evaluation8_by_frequency_band_by_method.csv",
            by_method_band,
            METHOD_SUMMARY_FIELDNAMES,
        )
        output_files.append("evaluation8_by_frequency_band_by_method.csv")
    write_csv_rows(
        args.output_dir / "evaluation8_occurrence_weighted_summary.csv",
        weighted_summary,
        OCCURRENCE_WEIGHTED_FIELDNAMES,
    )
    output_files.extend(["evaluation8_occurrence_weighted_summary.csv", "evaluation8_summary.json"])
    if (
        args.analysis_scope == "proposed_154days"
        and args.frequency_band_mode == "fixed"
        and getattr(args, "write_distribution_plots", True)
    ):
        output_files.extend(write_fixed_range_plots(args.output_dir, overall_by_band, frequency_bands, rows))

    summary = {
        "evaluation_type": "frequency_stratified_adl_consistency",
        "frequency_band_mode": (
            "tertile_by_num_occurrences"
            if args.frequency_band_mode == "tertile"
            else "fixed_ranges_by_num_occurrences"
        ),
        "fixed_frequency_bin_edges": list(fixed_edges) if args.frequency_band_mode == "fixed" else None,
        "frequency_bands": list(frequency_bands),
        "analysis_scope": args.analysis_scope,
        "n_states": getattr(args, "n_states", None),
        "hamming_threshold": getattr(args, "hamming_threshold", None),
        "days": getattr(args, "days", None),
        "evaluation6_details": str(args.evaluation6_details) if args.evaluation6_details else None,
        "input_summary": input_summary,
        "num_occurrences_source": occurrence_count_source,
        "output_dir": str(args.output_dir),
        "runs_evaluated": runs_evaluated,
        "num_methods": len(methods),
        "methods": methods,
        "overall_by_frequency_band": overall_by_band,
        "occurrence_weighted_summary": weighted_summary,
        "output_files": output_files,
    }
    if args.analysis_scope in COMPARISON_SCOPES:
        summary["by_method_frequency_band"] = by_method_band
    (args.output_dir / "evaluation8_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Evaluation 8 outputs saved to: {args.output_dir}")
    rows_to_print = by_method_band if args.analysis_scope in COMPARISON_SCOPES else overall_by_band
    for row in rows_to_print:
        method = row.get("method", "proposed")
        print(
            f"{method} {row['frequency_band']}: runs={row['num_runs']}, patterns={row['num_patterns']}, "
            f"precision={row['mean_multilabel_precision']:.6f}, "
            f"recall={row['mean_multilabel_recall']:.6f}, f1={row['mean_multilabel_f1']:.6f}"
        )


if __name__ == "__main__":
    main()
