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
from dataclasses import replace
from datetime import timedelta
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
    occurrence_is_within_time_band,
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
    "num_occurrences_before_fix",
    "num_occurrences_corrected",
    "num_occurrences",
    "num_occurrences_difference",
    "fallback_used",
    "duplicate_occurrences_removed",
    "own_id_duplicate_occurrences_removed",
    "cross_id_shared_physical_occurrences",
    "cross_id_occurrences_removed",
    "num_boundary_crossing_occurrences",
    "num_boundary_crossing_occurrences_excluded",
    "boundary_crossing_occurrence_rate",
    "frequency_band",
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
SUMMARY_FIELDNAMES = [
    "frequency_band",
    "num_runs",
    "num_runs_with_patterns",
    "num_patterns",
    "std_num_patterns",
    "num_evaluable_patterns",
    "std_num_evaluable_patterns",
    "num_conditional_evaluable_patterns",
    "std_num_conditional_evaluable_patterns",
    "num_end_to_end_evaluable_patterns",
    "std_num_end_to_end_evaluable_patterns",
    "num_no_occurrence",
    "std_num_no_occurrence",
    "num_no_adl_overlap",
    "std_num_no_adl_overlap",
    "num_prediction_missing",
    "std_num_prediction_missing",
    "num_prediction_unknown",
    "std_num_prediction_unknown",
    "occurrence_coverage",
    "std_occurrence_coverage",
    "truth_coverage",
    "std_truth_coverage",
    "no_occurrence_rate",
    "std_no_occurrence_rate",
    "no_adl_overlap_rate",
    "std_no_adl_overlap_rate",
    "missing_prediction_rate",
    "std_missing_prediction_rate",
    "unknown_label_rate",
    "std_unknown_label_rate",
    "num_boundary_crossing_occurrences",
    "std_num_boundary_crossing_occurrences",
    "boundary_crossing_occurrence_rate",
    "std_boundary_crossing_occurrence_rate",
    "total_occurrences",
    "std_total_occurrences",
    "min_occurrences",
    "max_occurrences",
    "mean_occurrences",
    "std_mean_occurrences",
    "median_occurrences",
    "std_median_occurrences",
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
    "conditional_mean_exact_set_match",
    "conditional_std_exact_set_match",
    "conditional_mean_jaccard",
    "conditional_std_jaccard",
    "conditional_mean_multilabel_precision",
    "conditional_std_multilabel_precision",
    "conditional_mean_multilabel_recall",
    "conditional_std_multilabel_recall",
    "conditional_mean_multilabel_f1",
    "conditional_std_multilabel_f1",
    "end_to_end_mean_exact_set_match",
    "end_to_end_std_exact_set_match",
    "end_to_end_mean_jaccard",
    "end_to_end_std_jaccard",
    "end_to_end_mean_multilabel_precision",
    "end_to_end_std_multilabel_precision",
    "end_to_end_mean_multilabel_recall",
    "end_to_end_std_multilabel_recall",
    "end_to_end_mean_multilabel_f1",
    "end_to_end_std_multilabel_f1",
    "weighted_jaccard",
    "std_weighted_jaccard",
    "weighted_multilabel_precision",
    "std_weighted_multilabel_precision",
    "weighted_multilabel_recall",
    "std_weighted_multilabel_recall",
    "weighted_multilabel_f1",
    "std_weighted_multilabel_f1",
]
METHOD_SUMMARY_FIELDNAMES = ["method", *SUMMARY_FIELDNAMES]
RUN_BAND_FIELDNAMES = [
    "method",
    "run",
    "frequency_band",
    "num_runs",
    "num_runs_with_patterns",
    "evaluation_status",
    "num_patterns",
    "num_evaluable_patterns",
    "num_conditional_evaluable_patterns",
    "num_end_to_end_evaluable_patterns",
    "num_no_occurrence",
    "num_no_adl_overlap",
    "num_prediction_missing",
    "num_prediction_unknown",
    "occurrence_coverage",
    "truth_coverage",
    "no_occurrence_rate",
    "no_adl_overlap_rate",
    "missing_prediction_rate",
    "unknown_label_rate",
    "num_boundary_crossing_occurrences",
    "boundary_crossing_occurrence_rate",
    "total_occurrences",
    "min_occurrences",
    "max_occurrences",
    "mean_occurrences",
    "median_occurrences",
    "mean_exact_set_match",
    "mean_jaccard",
    "mean_multilabel_precision",
    "mean_multilabel_recall",
    "mean_multilabel_f1",
    "conditional_mean_exact_set_match",
    "conditional_mean_jaccard",
    "conditional_mean_multilabel_precision",
    "conditional_mean_multilabel_recall",
    "conditional_mean_multilabel_f1",
    "end_to_end_mean_exact_set_match",
    "end_to_end_mean_jaccard",
    "end_to_end_mean_multilabel_precision",
    "end_to_end_mean_multilabel_recall",
    "end_to_end_mean_multilabel_f1",
    "weighted_jaccard",
    "weighted_multilabel_precision",
    "weighted_multilabel_recall",
    "weighted_multilabel_f1",
]
OCCURRENCE_WEIGHTED_FIELDNAMES = [
    "method",
    "num_runs",
    "num_patterns",
    "std_num_patterns",
    "total_occurrences",
    "std_total_occurrences",
    "weighted_jaccard",
    "std_weighted_jaccard",
    "weighted_multilabel_precision",
    "std_weighted_multilabel_precision",
    "weighted_multilabel_recall",
    "std_weighted_multilabel_recall",
    "weighted_multilabel_f1",
    "std_weighted_multilabel_f1",
]
METRIC_COLUMNS = (
    "exact_set_match",
    "jaccard",
    "multilabel_precision",
    "multilabel_recall",
    "multilabel_f1",
)


def default_output_dir(analysis_scope: str) -> Path:
    directory_name = (
        "8_vs_llm_own_id_fixed"
        if analysis_scope in COMPARISON_SCOPES
        else "8_proposed_own_id_fixed"
    )
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
        choices=["tertile", "fixed", "both"],
        default="tertile",
        help=(
            "Frequency stratification mode. tertile assigns near-equal record counts per method/run; "
            "fixed assigns numeric num_occurrences ranges; both writes each mode to its own subdirectory."
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
            "Representative-state interval CSV used to reconstruct strict own-pattern-ID "
            "counts for every comparison input. By default, it is read from the sibling "
            "Evaluation 6 summary JSON."
        ),
    )
    parser.add_argument(
        "--match-mode",
        choices=["exact", "skip-other"],
        default=None,
        help="Occurrence search mode used to reconstruct own-pattern-ID counts.",
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
        help=(
            "Half-open day span used by proposed_154days, starting at 00:00 on "
            "the first state-series date. Defaults to 154 for that scope."
        ),
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
        help="Deprecated compatibility option; no-overlap is now a truth status.",
    )
    parser.add_argument(
        "--missing-pred-label",
        choices=["Other", "Ambiguous"],
        default="Ambiguous",
        help="Deprecated compatibility option; missing prediction is now a status.",
    )
    parser.add_argument(
        "--unknown-pred-label",
        choices=["Other", "Ambiguous"],
        default="Other",
        help="Deprecated compatibility option; unknown prediction is now a status.",
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


def as_optional_float(
    value: Any,
    column: str,
    row_number: int,
) -> float | None:
    if value in {None, ""}:
        return None
    return as_float(value, column, row_number)


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


def occurrence_physical_key(occurrence: Any, run: int) -> tuple[Any, ...]:
    """Return the Evaluation 8 physical-occurrence identity.

    ``PatternOccurrence`` does not carry a run or time-band field, so the run is
    supplied by the caller and the time band is derived from the occurrence
    start time with the same boundary function used by Evaluation 6.
    """
    return (
        int(run),
        time_band_for_timestamp(occurrence.start_time),
        occurrence.start_time,
        occurrence.end_time,
        tuple(occurrence.sequence),
    )


def deduplicate_physical_occurrences(
    occurrences: Sequence[Any],
    run: int,
) -> tuple[list[Any], int]:
    """Deduplicate one evaluation row without using pattern ID in the key."""
    unique: list[Any] = []
    seen: set[tuple[Any, ...]] = set()
    for occurrence in occurrences:
        key = occurrence_physical_key(occurrence, run)
        if key in seen:
            continue
        seen.add(key)
        unique.append(occurrence)
    return unique, len(occurrences) - len(unique)


def attach_own_id_occurrences(
    rows: list[dict[str, Any]],
    state_intervals: Sequence[Any],
    match_mode: str,
    max_skip_duration_minutes: float,
) -> None:
    """Replace legacy counts with strict own-pattern-ID occurrence counts.

    Matching is performed independently for each method/run. A pattern record
    is searched under its own ``eval_pattern_id``; sequence equality is never a
    fallback for another ID. Occurrences are deduplicated within each row, then
    a physical key shared by multiple IDs is assigned to the lexically smallest
    ``eval_pattern_id`` so its unit weight is counted only once per method/run.
    """
    if max_skip_duration_minutes < 0:
        raise ValueError("--max-skip-duration-minutes must be >= 0")

    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("method") or "all"), int(row.get("run") or 1))].append(row)

    for (method, run), group_rows in grouped.items():
        records: list[PatternRecord] = []
        rows_by_pattern_id: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(group_rows, start=1):
            sequence = parse_sequence(row.get("sequence"))
            if len(sequence) < 2:
                raise ValueError(
                    f"{method} run {run} row {index} has no usable state sequence "
                    "for own-ID occurrence reconstruction"
                )
            eval_pattern_id = str(row.get("eval_pattern_id") or "").strip()
            if not eval_pattern_id:
                raise ValueError(
                    f"{method} run {run} row {index} has no eval_pattern_id; "
                    "strict own-ID occurrence reconstruction does not invent IDs "
                    "or fall back to sequence equality."
                )
            if eval_pattern_id in rows_by_pattern_id:
                raise ValueError(
                    f"Duplicate eval_pattern_id within {method} run {run}: "
                    f"{eval_pattern_id}"
                )
            rows_by_pattern_id[eval_pattern_id] = row
            records.append(
                PatternRecord(
                    pattern_id=eval_pattern_id,
                    pattern_name=str(row.get("pattern_name") or eval_pattern_id),
                    sequence=sequence,
                )
            )

        matches = find_pattern_occurrences(
            records,
            state_intervals,
            match_mode=match_mode,
            max_skip_duration_minutes=max_skip_duration_minutes,
        )
        matches_by_pattern_id: dict[str, list[Any]] = defaultdict(list)
        for match in matches:
            matches_by_pattern_id[str(match.pattern_id)].append(match)

        physical_keys_by_pattern_id: dict[str, set[tuple[Any, ...]]] = {}
        before_count_by_pattern_id: dict[str, int | None] = {}
        own_id_duplicates_by_pattern_id: dict[str, int] = {}
        boundary_crossing_by_pattern_id: dict[str, int] = {}
        boundary_candidates_by_pattern_id: dict[str, int] = {}
        for eval_pattern_id, row in rows_by_pattern_id.items():
            before_value = row.get("num_occurrences_before_fix", row.get("num_occurrences"))
            if before_value in {None, ""}:
                before_count: int | None = None
            else:
                before_count = as_occurrence_count(before_value, 0)
            before_count_by_pattern_id[eval_pattern_id] = before_count

            own_occurrences = matches_by_pattern_id.get(eval_pattern_id, [])
            time_band = str(row.get("time_band") or "All")
            if time_band == "All":
                assigned_occurrences = list(own_occurrences)
                boundary_crossing = [
                    occurrence
                    for occurrence in assigned_occurrences
                    if time_band_for_timestamp(occurrence.start_time)
                    != time_band_for_timestamp(
                        occurrence.end_time - timedelta(microseconds=1)
                    )
                ]
                own_occurrences = assigned_occurrences
            else:
                assigned_occurrences = [
                    occurrence
                    for occurrence in own_occurrences
                    if time_band_for_timestamp(occurrence.start_time) == time_band
                ]
                boundary_crossing = [
                    occurrence
                    for occurrence in assigned_occurrences
                    if not occurrence_is_within_time_band(
                        occurrence.start_time,
                        occurrence.end_time,
                        time_band,
                    )
                ]
                own_occurrences = [
                    occurrence
                    for occurrence in assigned_occurrences
                    if occurrence_is_within_time_band(
                        occurrence.start_time,
                        occurrence.end_time,
                        time_band,
                    )
                ]
            boundary_crossing_by_pattern_id[eval_pattern_id] = len(
                boundary_crossing
            )
            boundary_candidates_by_pattern_id[eval_pattern_id] = len(
                assigned_occurrences
            )
            unique_occurrences, duplicates_removed = deduplicate_physical_occurrences(
                own_occurrences,
                run,
            )
            physical_keys = {
                occurrence_physical_key(occurrence, run)
                for occurrence in unique_occurrences
            }
            physical_keys_by_pattern_id[eval_pattern_id] = physical_keys
            own_id_duplicates_by_pattern_id[eval_pattern_id] = duplicates_removed

        pattern_ids_by_physical_key: dict[tuple[Any, ...], set[str]] = defaultdict(set)
        for eval_pattern_id, physical_keys in physical_keys_by_pattern_id.items():
            for physical_key in physical_keys:
                pattern_ids_by_physical_key[physical_key].add(eval_pattern_id)

        # A physical interval shared by multiple IDs receives unit weight once.
        # Stable lexical ownership avoids dependence on input row order.
        owner_by_physical_key = {
            physical_key: min(pattern_ids)
            for physical_key, pattern_ids in pattern_ids_by_physical_key.items()
        }
        for eval_pattern_id, row in rows_by_pattern_id.items():
            physical_keys = physical_keys_by_pattern_id[eval_pattern_id]
            shared_keys = {
                physical_key
                for physical_key in physical_keys
                if len(pattern_ids_by_physical_key[physical_key]) > 1
            }
            owned_keys = {
                physical_key
                for physical_key in physical_keys
                if owner_by_physical_key[physical_key] == eval_pattern_id
            }
            cross_id_removed = len(physical_keys) - len(owned_keys)
            corrected_count = len(owned_keys)
            before_count = before_count_by_pattern_id[eval_pattern_id]
            own_id_duplicates_removed = own_id_duplicates_by_pattern_id[eval_pattern_id]

            row["num_occurrences_before_fix"] = (
                before_count if before_count is not None else ""
            )
            row["num_occurrences_corrected"] = corrected_count
            # Keep the historical column name as a compatibility alias for the
            # corrected formal count used by bands and weighting.
            row["num_occurrences"] = corrected_count
            row["num_occurrences_difference"] = (
                corrected_count - before_count if before_count is not None else ""
            )
            row["fallback_used"] = 0
            row["duplicate_occurrences_removed"] = (
                max(before_count - corrected_count, 0)
                if before_count is not None
                else own_id_duplicates_removed + cross_id_removed
            )
            row["own_id_duplicate_occurrences_removed"] = own_id_duplicates_removed
            row["cross_id_shared_physical_occurrences"] = len(shared_keys)
            row["cross_id_occurrences_removed"] = cross_id_removed
            boundary_crossing_count = boundary_crossing_by_pattern_id[
                eval_pattern_id
            ]
            boundary_candidate_count = boundary_candidates_by_pattern_id[
                eval_pattern_id
            ]
            row["num_boundary_crossing_occurrences"] = boundary_crossing_count
            row["num_boundary_crossing_occurrences_excluded"] = (
                boundary_crossing_count if str(row.get("time_band") or "All") != "All" else 0
            )
            row["boundary_crossing_occurrence_rate"] = (
                boundary_crossing_count / boundary_candidate_count
                if boundary_candidate_count
                else 0.0
            )
            row["_physical_occurrence_keys_before_ownership"] = physical_keys
            row["_physical_occurrence_keys"] = owned_keys


def attach_reconstructed_occurrences(
    rows: list[dict[str, Any]],
    details_path: Path,
    args: argparse.Namespace,
) -> str:
    """Always reconstruct comparison counts from the state series."""
    summary = evaluation6_summary_payload(details_path)
    configured_state_series = getattr(args, "state_series", None) or summary.get("state_series")
    if not configured_state_series:
        raise ValueError(
            "Evaluation 8 requires the state series to reconstruct strict own-ID "
            "occurrence counts. Pass --state-series or provide it in the sibling "
            "Evaluation 6 summary JSON."
        )
    state_series_path = resolve_existing_path(configured_state_series, details_path)
    if not state_series_path.exists():
        raise FileNotFoundError(f"State series for num_occurrences does not exist: {state_series_path}")

    match_mode = getattr(args, "match_mode", None) or str(summary.get("match_mode") or "exact")
    configured_skip = getattr(args, "max_skip_duration_minutes", None)
    max_skip_duration = (
        configured_skip
        if configured_skip is not None
        else float(summary.get("max_skip_duration_minutes") or 1.0)
    )
    attach_own_id_occurrences(
        rows,
        load_state_series_csv(state_series_path),
        match_mode=match_mode,
        max_skip_duration_minutes=max_skip_duration,
    )
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
                row["num_occurrences_before_fix"] = as_occurrence_count(
                    row.get("num_occurrences"),
                    row_number,
                )
            for column in METRIC_COLUMNS:
                row[column] = as_optional_float(
                    row.get(column),
                    column,
                    row_number,
                )
            for scope in ("conditional", "end_to_end"):
                for column in METRIC_COLUMNS:
                    scoped_column = f"{scope}_{column}"
                    row[scoped_column] = as_optional_float(
                        row.get(scoped_column),
                        scoped_column,
                        row_number,
                    )
            rows.append(row)
    state_series = attach_reconstructed_occurrences(rows, path, args)
    return rows, f"strict_own_pattern_id_from_state_series:{state_series}"


def clip_intervals_to_period(
    intervals: Sequence[Any],
    start_time: Any,
    end_time: Any,
) -> list[Any]:
    """Clip interval dataclasses to the half-open period ``[start, end)``."""
    clipped: list[Any] = []
    for interval in intervals:
        clipped_start = max(interval.start_time, start_time)
        clipped_end = min(interval.end_time, end_time)
        if clipped_end <= clipped_start:
            continue
        clipped.append(
            replace(
                interval,
                start_time=clipped_start,
                end_time=clipped_end,
            )
        )
    return clipped


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

    source_state_intervals = load_state_series_csv(args.state_series)
    if not source_state_intervals:
        raise ValueError("--state-series contains no intervals")
    days = int(args.days) if getattr(args, "days", None) is not None else 154
    if days < 1:
        raise ValueError("--days must be >= 1 for --analysis-scope proposed_154days")
    args.days = days
    period_start = min(interval.start_time for interval in source_state_intervals).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    period_end = period_start + timedelta(days=days)
    state_intervals = clip_intervals_to_period(
        source_state_intervals,
        period_start,
        period_end,
    )
    source_adl_intervals, adl_source = load_truth_intervals(args)
    adl_intervals = clip_intervals_to_period(
        source_adl_intervals,
        period_start,
        period_end,
    )
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
        detail_rows.extend(
            {
                "run": run,
                **row,
                "num_occurrences_before_fix": row.get("num_occurrences", ""),
            }
            for row in run_rows
        )
        run_summaries.append({"run": run, **evaluation6_summary})
        pattern_paths.append(str(patterns_path))
    attach_own_id_occurrences(
        detail_rows,
        state_intervals,
        match_mode=args.match_mode,
        max_skip_duration_minutes=args.max_skip_duration_minutes,
    )
    return (
        detail_rows,
        "strict_own_pattern_id_from_proposed_154day_state_series",
        {
            "patterns_proposed": pattern_paths,
            "runs_requested": args.runs,
            "state_series": str(args.state_series),
            "adl_intervals": adl_source,
            "effective_period_start": period_start.isoformat(sep=" "),
            "effective_period_end_exclusive": period_end.isoformat(sep=" "),
            "source_state_interval_count": len(source_state_intervals),
            "effective_state_interval_count": len(state_intervals),
            "source_adl_interval_count": len(source_adl_intervals),
            "effective_adl_interval_count": len(adl_intervals),
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


def std(values: Sequence[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def weighted_mean(
    rows: Sequence[dict[str, Any]],
    column: str,
) -> float | None:
    total_occurrences = sum(float(row["num_occurrences"]) for row in rows)
    if total_occurrences <= 0:
        return None
    return sum(float(row[column]) * float(row["num_occurrences"]) for row in rows) / total_occurrences


def row_is_conditional_evaluable(row: dict[str, Any]) -> bool:
    if "is_metric_evaluable" in row:
        return bool(int(row.get("is_metric_evaluable") or 0))
    return row.get("conditional_multilabel_f1", row.get("multilabel_f1")) not in {
        None,
        "",
    }


def row_is_end_to_end_evaluable(row: dict[str, Any]) -> bool:
    if "is_end_to_end_evaluable" in row:
        return bool(int(row.get("is_end_to_end_evaluable") or 0))
    return row.get("end_to_end_multilabel_f1", row.get("multilabel_f1")) not in {
        None,
        "",
    }


def scoped_metric_value(
    row: dict[str, Any],
    scope: str,
    metric: str,
) -> float:
    value = row.get(f"{scope}_{metric}")
    if value in {None, ""}:
        value = row.get(metric)
    return float(value)


def scoped_metric_mean(
    rows: Sequence[dict[str, Any]],
    scope: str,
    metric: str,
) -> float | None:
    if not rows:
        return None
    return mean([scoped_metric_value(row, scope, metric) for row in rows])


def summarize_rows(rows: Sequence[dict[str, Any]], frequency_band: str) -> dict[str, Any]:
    occurrences = [float(row["num_occurrences"]) for row in rows]
    if not rows:
        return {
            "frequency_band": frequency_band,
            "num_runs": 1,
            "num_runs_with_patterns": 0,
            "evaluation_status": "empty_band",
            "num_patterns": 0,
            "num_evaluable_patterns": 0,
            "num_conditional_evaluable_patterns": 0,
            "num_end_to_end_evaluable_patterns": 0,
            "num_no_occurrence": 0,
            "num_no_adl_overlap": 0,
            "num_prediction_missing": 0,
            "num_prediction_unknown": 0,
            "occurrence_coverage": 0.0,
            "truth_coverage": 0.0,
            "no_occurrence_rate": 0.0,
            "no_adl_overlap_rate": 0.0,
            "missing_prediction_rate": 0.0,
            "unknown_label_rate": 0.0,
            "num_boundary_crossing_occurrences": 0,
            "boundary_crossing_occurrence_rate": 0.0,
            "total_occurrences": 0.0,
            "min_occurrences": None,
            "max_occurrences": None,
            "mean_occurrences": None,
            "median_occurrences": None,
            "mean_exact_set_match": None,
            "mean_jaccard": None,
            "mean_multilabel_precision": None,
            "mean_multilabel_recall": None,
            "mean_multilabel_f1": None,
            "conditional_mean_exact_set_match": None,
            "conditional_mean_jaccard": None,
            "conditional_mean_multilabel_precision": None,
            "conditional_mean_multilabel_recall": None,
            "conditional_mean_multilabel_f1": None,
            "end_to_end_mean_exact_set_match": None,
            "end_to_end_mean_jaccard": None,
            "end_to_end_mean_multilabel_precision": None,
            "end_to_end_mean_multilabel_recall": None,
            "end_to_end_mean_multilabel_f1": None,
            "weighted_jaccard": None,
            "weighted_multilabel_precision": None,
            "weighted_multilabel_recall": None,
            "weighted_multilabel_f1": None,
        }
    conditional_rows = [row for row in rows if row_is_conditional_evaluable(row)]
    end_to_end_rows = [row for row in rows if row_is_end_to_end_evaluable(row)]
    num_matched = sum(
        str(row.get("occurrence_status") or "matched") == "matched"
        for row in rows
    )
    num_no_occurrence = len(rows) - num_matched
    num_truth_defined = sum(
        str(row.get("truth_status") or "defined") == "defined"
        for row in rows
    )
    num_no_adl_overlap = sum(
        str(row.get("occurrence_status") or "matched") == "matched"
        and str(row.get("truth_status") or "defined") == "no_adl_overlap"
        for row in rows
    )
    num_prediction_missing = sum(
        row.get("prediction_status") == "missing" for row in rows
    )
    num_prediction_unknown = sum(
        row.get("prediction_status") == "unknown" for row in rows
    )
    boundary_crossing = sum(
        int(row.get("num_boundary_crossing_occurrences") or 0)
        for row in rows
    )
    boundary_candidates = sum(
        int(row.get("num_occurrences") or 0)
        + int(row.get("num_boundary_crossing_occurrences_excluded") or 0)
        for row in rows
    )
    end_metrics = {
        metric: scoped_metric_mean(end_to_end_rows, "end_to_end", metric)
        for metric in METRIC_COLUMNS
    }
    conditional_metrics = {
        metric: scoped_metric_mean(conditional_rows, "conditional", metric)
        for metric in METRIC_COLUMNS
    }
    return {
        "frequency_band": frequency_band,
        "num_runs": 1,
        "num_runs_with_patterns": 1,
        "evaluation_status": "evaluated",
        "num_patterns": len(rows),
        "num_evaluable_patterns": len(end_to_end_rows),
        "num_conditional_evaluable_patterns": len(conditional_rows),
        "num_end_to_end_evaluable_patterns": len(end_to_end_rows),
        "num_no_occurrence": num_no_occurrence,
        "num_no_adl_overlap": num_no_adl_overlap,
        "num_prediction_missing": num_prediction_missing,
        "num_prediction_unknown": num_prediction_unknown,
        "occurrence_coverage": num_matched / len(rows),
        "truth_coverage": (
            num_truth_defined / num_matched if num_matched else 0.0
        ),
        "no_occurrence_rate": num_no_occurrence / len(rows),
        "no_adl_overlap_rate": (
            num_no_adl_overlap / num_matched if num_matched else 0.0
        ),
        "missing_prediction_rate": num_prediction_missing / len(rows),
        "unknown_label_rate": num_prediction_unknown / len(rows),
        "num_boundary_crossing_occurrences": boundary_crossing,
        "boundary_crossing_occurrence_rate": (
            boundary_crossing / boundary_candidates
            if boundary_candidates
            else 0.0
        ),
        "total_occurrences": sum(occurrences),
        "min_occurrences": min(occurrences) if occurrences else 0.0,
        "max_occurrences": max(occurrences) if occurrences else 0.0,
        "mean_occurrences": mean(occurrences),
        "median_occurrences": statistics.median(occurrences) if occurrences else 0.0,
        "mean_exact_set_match": end_metrics["exact_set_match"],
        "mean_jaccard": end_metrics["jaccard"],
        "mean_multilabel_precision": end_metrics["multilabel_precision"],
        "mean_multilabel_recall": end_metrics["multilabel_recall"],
        "mean_multilabel_f1": end_metrics["multilabel_f1"],
        **{
            f"conditional_mean_{metric}": value
            for metric, value in conditional_metrics.items()
        },
        **{
            f"end_to_end_mean_{metric}": value
            for metric, value in end_metrics.items()
        },
        "weighted_jaccard": weighted_mean(end_to_end_rows, "jaccard"),
        "weighted_multilabel_precision": weighted_mean(
            end_to_end_rows,
            "multilabel_precision",
        ),
        "weighted_multilabel_recall": weighted_mean(
            end_to_end_rows,
            "multilabel_recall",
        ),
        "weighted_multilabel_f1": weighted_mean(
            end_to_end_rows,
            "multilabel_f1",
        ),
    }


def mean_run_summaries(
    run_summaries: Sequence[dict[str, Any]],
    frequency_band: str,
    total_num_runs: int | None = None,
) -> dict[str, Any]:
    """Average independently computed per-run band summaries.

    Count columns include zero for runs where a fixed range has no patterns.
    Distribution and ADL-consistency metrics are undefined for an empty range,
    so those columns average only runs that contain at least one pattern and
    ``num_runs_with_patterns`` makes that denominator explicit.
    """
    num_valid_runs = len(run_summaries)
    num_total_runs = total_num_runs if total_num_runs is not None else num_valid_runs
    if num_total_runs < 1:
        raise ValueError("mean_run_summaries requires at least one total run")
    if num_valid_runs > num_total_runs:
        raise ValueError("run_summaries cannot exceed total_num_runs")

    result: dict[str, Any] = {
        "frequency_band": frequency_band,
        "num_runs": num_total_runs,
        "num_runs_with_patterns": num_valid_runs,
        "min_occurrences": (
            min(float(summary["min_occurrences"]) for summary in run_summaries)
            if run_summaries
            else None
        ),
        "max_occurrences": (
            max(float(summary["max_occurrences"]) for summary in run_summaries)
            if run_summaries
            else None
        ),
    }
    count_columns = {
        "num_patterns": "std_num_patterns",
        "num_evaluable_patterns": "std_num_evaluable_patterns",
        "num_conditional_evaluable_patterns": "std_num_conditional_evaluable_patterns",
        "num_end_to_end_evaluable_patterns": "std_num_end_to_end_evaluable_patterns",
        "num_no_occurrence": "std_num_no_occurrence",
        "num_no_adl_overlap": "std_num_no_adl_overlap",
        "num_prediction_missing": "std_num_prediction_missing",
        "num_prediction_unknown": "std_num_prediction_unknown",
        "num_boundary_crossing_occurrences": "std_num_boundary_crossing_occurrences",
        "total_occurrences": "std_total_occurrences",
    }
    metric_columns = {
        "occurrence_coverage": "std_occurrence_coverage",
        "truth_coverage": "std_truth_coverage",
        "no_occurrence_rate": "std_no_occurrence_rate",
        "no_adl_overlap_rate": "std_no_adl_overlap_rate",
        "missing_prediction_rate": "std_missing_prediction_rate",
        "unknown_label_rate": "std_unknown_label_rate",
        "boundary_crossing_occurrence_rate": "std_boundary_crossing_occurrence_rate",
        "mean_occurrences": "std_mean_occurrences",
        "median_occurrences": "std_median_occurrences",
        "mean_exact_set_match": "std_exact_set_match",
        "mean_jaccard": "std_jaccard",
        "mean_multilabel_precision": "std_multilabel_precision",
        "mean_multilabel_recall": "std_multilabel_recall",
        "mean_multilabel_f1": "std_multilabel_f1",
        "conditional_mean_exact_set_match": "conditional_std_exact_set_match",
        "conditional_mean_jaccard": "conditional_std_jaccard",
        "conditional_mean_multilabel_precision": "conditional_std_multilabel_precision",
        "conditional_mean_multilabel_recall": "conditional_std_multilabel_recall",
        "conditional_mean_multilabel_f1": "conditional_std_multilabel_f1",
        "end_to_end_mean_exact_set_match": "end_to_end_std_exact_set_match",
        "end_to_end_mean_jaccard": "end_to_end_std_jaccard",
        "end_to_end_mean_multilabel_precision": "end_to_end_std_multilabel_precision",
        "end_to_end_mean_multilabel_recall": "end_to_end_std_multilabel_recall",
        "end_to_end_mean_multilabel_f1": "end_to_end_std_multilabel_f1",
        "weighted_jaccard": "std_weighted_jaccard",
        "weighted_multilabel_precision": "std_weighted_multilabel_precision",
        "weighted_multilabel_recall": "std_weighted_multilabel_recall",
        "weighted_multilabel_f1": "std_weighted_multilabel_f1",
    }
    for column, std_column in count_columns.items():
        values = [float(summary[column]) for summary in run_summaries]
        values.extend([0.0] * (num_total_runs - num_valid_runs))
        result[column] = mean(values)
        result[std_column] = std(values)
    for column, std_column in metric_columns.items():
        values = [
            float(summary[column])
            for summary in run_summaries
            if summary.get(column) not in {None, ""}
        ]
        result[column] = mean(values) if values else None
        result[std_column] = std(values) if values else None
    return result


def run_summaries_by_frequency_band(
    rows: Sequence[dict[str, Any]],
    frequency_bands: Sequence[str] = FREQUENCY_BANDS,
) -> list[dict[str, Any]]:
    """Return method/run/band summaries before cross-run aggregation."""
    result: list[dict[str, Any]] = []
    method_runs = sorted(
        {
            (
                str(row.get("method") or "all"),
                int(row.get("run") or 1),
            )
            for row in rows
        }
    )
    grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        band = str(row.get("frequency_band") or "")
        if band not in frequency_bands:
            continue
        grouped[
            (
                str(row.get("method") or "all"),
                int(row.get("run") or 1),
                band,
            )
        ].append(row)
    for method, run in method_runs:
        for band in frequency_bands:
            result.append(
                {
                    "method": method,
                    "run": run,
                    **summarize_rows(grouped.get((method, run, band), []), band),
                }
            )
    return result


def summaries_by_frequency_band(
    rows: Sequence[dict[str, Any]], frequency_bands: Sequence[str] = FREQUENCY_BANDS
) -> list[dict[str, Any]]:
    summaries = []
    all_method_runs = {
        (str(row["method"]), int(row.get("run") or 1))
        for row in rows
    }
    for band in frequency_bands:
        run_groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if row.get("frequency_band") == band:
                run_groups[(str(row["method"]), int(row.get("run") or 1))].append(row)
        summaries.append(
            mean_run_summaries(
                [summarize_rows(group, band) for group in run_groups.values()],
                band,
                total_num_runs=len(all_method_runs),
            )
        )
    return summaries


def summaries_by_method_and_frequency_band(
    rows: Sequence[dict[str, Any]], frequency_bands: Sequence[str] = FREQUENCY_BANDS
) -> list[dict[str, Any]]:
    result = []
    methods = sorted({str(row["method"]) for row in rows})
    for method in methods:
        method_rows = [row for row in rows if row["method"] == method]
        method_runs = {int(row.get("run") or 1) for row in method_rows}
        for band in frequency_bands:
            run_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for row in method_rows:
                if row.get("frequency_band") == band:
                    run_groups[int(row.get("run") or 1)].append(row)
            result.append(
                {
                    "method": method,
                    **mean_run_summaries(
                        [summarize_rows(group, band) for group in run_groups.values()],
                        band,
                        total_num_runs=len(method_runs),
                    ),
                }
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
            evaluable_rows = [
                row for row in run_rows if row_is_end_to_end_evaluable(row)
            ]
            per_run.append(
                {
                    "num_patterns": len(run_rows),
                    "total_occurrences": sum(float(row["num_occurrences"]) for row in run_rows),
                    "weighted_jaccard": weighted_mean(evaluable_rows, "jaccard"),
                    "weighted_multilabel_precision": weighted_mean(evaluable_rows, "multilabel_precision"),
                    "weighted_multilabel_recall": weighted_mean(evaluable_rows, "multilabel_recall"),
                    "weighted_multilabel_f1": weighted_mean(evaluable_rows, "multilabel_f1"),
                }
            )
        aggregated: dict[str, Any] = {
            "method": method,
            "num_runs": len(per_run),
        }
        for column in (
            "num_patterns",
            "total_occurrences",
            "weighted_jaccard",
            "weighted_multilabel_precision",
            "weighted_multilabel_recall",
            "weighted_multilabel_f1",
        ):
            values = [
                float(summary[column])
                for summary in per_run
                if summary.get(column) not in {None, ""}
            ]
            aggregated[column] = mean(values) if values else None
            aggregated[f"std_{column}"] = std(values) if values else None
        result.append(aggregated)
    return result


def occurrence_weight_validation(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Audit that every weighted denominator uses corrected unique counts."""
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("method") or "all"), int(row.get("run") or 1))].append(row)

    by_method_run: list[dict[str, Any]] = []
    for (method, run), run_rows in sorted(grouped.items()):
        corrected_total = sum(int(row["num_occurrences_corrected"]) for row in run_rows)
        weight_sum = sum(int(row["num_occurrences"]) for row in run_rows)
        cross_id_key_counts: dict[tuple[Any, ...], int] = defaultdict(int)
        owned_physical_keys: set[tuple[Any, ...]] = set()
        for row in run_rows:
            owned_physical_keys.update(row.get("_physical_occurrence_keys", set()))
            for physical_key in row.get(
                "_physical_occurrence_keys_before_ownership",
                row.get("_physical_occurrence_keys", set()),
            ):
                cross_id_key_counts[physical_key] += 1
        unique_physical_occurrence_total = len(cross_id_key_counts)
        before_values = [
            int(row["num_occurrences_before_fix"])
            for row in run_rows
            if row.get("num_occurrences_before_fix") not in {None, ""}
        ]
        by_method_run.append(
            {
                "method": method,
                "run": run,
                "num_patterns": len(run_rows),
                "num_occurrences_before_fix": (
                    sum(before_values) if len(before_values) == len(run_rows) else None
                ),
                "num_occurrences_corrected": corrected_total,
                "occurrence_weight_sum": weight_sum,
                "unique_physical_occurrence_total": unique_physical_occurrence_total,
                "num_occurrences_difference": (
                    corrected_total - sum(before_values)
                    if len(before_values) == len(run_rows)
                    else None
                ),
                "duplicate_occurrences_removed": sum(
                    int(row.get("duplicate_occurrences_removed") or 0)
                    for row in run_rows
                ),
                "own_id_duplicate_occurrences_removed": sum(
                    int(row.get("own_id_duplicate_occurrences_removed") or 0)
                    for row in run_rows
                ),
                "cross_id_shared_physical_occurrence_keys": sum(
                    1 for count in cross_id_key_counts.values() if count > 1
                ),
                "cross_id_extra_occurrence_assignments": sum(
                    count - 1
                    for count in cross_id_key_counts.values()
                    if count > 1
                ),
                "cross_id_occurrences_removed": sum(
                    int(row.get("cross_id_occurrences_removed") or 0)
                    for row in run_rows
                ),
                "fallback_used_count": sum(
                    int(row.get("fallback_used") or 0)
                    for row in run_rows
                ),
                "weight_sum_matches_corrected_occurrences": weight_sum == corrected_total,
                "weight_sum_matches_unique_physical_occurrences": (
                    not cross_id_key_counts
                    or weight_sum == unique_physical_occurrence_total == len(owned_physical_keys)
                ),
            }
        )
    return {
        "all_passed": all(
            row["weight_sum_matches_corrected_occurrences"]
            and row["weight_sum_matches_unique_physical_occurrences"]
            for row in by_method_run
        ),
        "by_method_run": by_method_run,
    }


def detail_output_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{column: row.get(column, "") for column in DETAIL_FIELDNAMES} for row in rows]


def write_fixed_range_plots(
    output_dir: Path,
    summaries: Sequence[dict[str, Any]],
    frequency_bands: Sequence[str],
) -> list[str]:
    """Write proposed-only fixed-range charts without changing CSV aggregation."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    by_band = {str(row["frequency_band"]): row for row in summaries}
    labels = list(frequency_bands)
    mean_patterns = [
        float(by_band.get(label, {}).get("num_patterns") or 0.0)
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
        values = [
            (
                float(by_band[band][column])
                if band in by_band and by_band[band].get(column) not in (None, "")
                else float("nan")
            )
            for band in labels
        ]
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


def write_mode_outputs(
    args: argparse.Namespace,
    source_rows: Sequence[dict[str, Any]],
    mode: str,
    fixed_edges: Sequence[int],
    output_dir: Path,
    occurrence_count_source: str,
    input_summary: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Aggregate and write one band mode from already evaluated pattern rows."""
    rows = [dict(row) for row in source_rows]
    for row in rows:
        corrected = int(row.get("num_occurrences_corrected", row["num_occurrences"]))
        before = row.get("num_occurrences_before_fix", corrected)
        row["num_occurrences_before_fix"] = before
        row["num_occurrences_corrected"] = corrected
        row["num_occurrences"] = corrected
        row.setdefault(
            "num_occurrences_difference",
            corrected - int(before) if before not in {None, ""} else "",
        )
        row.setdefault("fallback_used", 0)
        row.setdefault("duplicate_occurrences_removed", 0)
        row.setdefault("own_id_duplicate_occurrences_removed", 0)
        row.setdefault("cross_id_shared_physical_occurrences", 0)
        row.setdefault("cross_id_occurrences_removed", 0)
    frequency_bands = frequency_bands_for_mode(mode, fixed_edges)
    assign_frequency_bands(rows, mode, fixed_edges)
    overall_by_band = summaries_by_frequency_band(rows, frequency_bands)
    by_method_band = summaries_by_method_and_frequency_band(rows, frequency_bands)
    by_run_band = run_summaries_by_frequency_band(rows, frequency_bands)
    weighted_summary = occurrence_weighted_summaries(rows)
    weight_validation = occurrence_weight_validation(rows)
    methods = sorted({str(row["method"]) for row in rows})
    runs_evaluated = sorted({int(row.get("run") or 1) for row in rows})

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_rows(output_dir / "evaluation8_frequency_band_details.csv", detail_output_rows(rows), DETAIL_FIELDNAMES)
    write_csv_rows(output_dir / "evaluation8_by_frequency_band.csv", overall_by_band, SUMMARY_FIELDNAMES)
    write_csv_rows(
        output_dir / "evaluation8_by_frequency_band_by_run.csv",
        by_run_band,
        RUN_BAND_FIELDNAMES,
    )
    output_files = [
        "evaluation8_frequency_band_details.csv",
        "evaluation8_by_frequency_band.csv",
        "evaluation8_by_frequency_band_by_run.csv",
    ]
    if args.analysis_scope in COMPARISON_SCOPES:
        write_csv_rows(
            output_dir / "evaluation8_by_frequency_band_by_method.csv",
            by_method_band,
            METHOD_SUMMARY_FIELDNAMES,
        )
        output_files.append("evaluation8_by_frequency_band_by_method.csv")
    write_csv_rows(
        output_dir / "evaluation8_occurrence_weighted_summary.csv",
        weighted_summary,
        OCCURRENCE_WEIGHTED_FIELDNAMES,
    )
    output_files.extend(["evaluation8_occurrence_weighted_summary.csv", "evaluation8_summary.json"])
    if (
        args.analysis_scope == "proposed_154days"
        and mode == "fixed"
        and getattr(args, "write_distribution_plots", True)
    ):
        output_files.extend(
            write_fixed_range_plots(output_dir, overall_by_band, frequency_bands)
        )

    summary = {
        "evaluation_type": "frequency_stratified_adl_consistency",
        "frequency_band_mode": (
            "tertile_by_num_occurrences"
            if mode == "tertile"
            else "fixed_ranges_by_num_occurrences"
        ),
        "tertile_scope": "independent_within_method_and_run",
        "tertile_tie_policy": (
            "stable_identifier_split_for_near_equal_record_counts"
            if mode == "tertile"
            else None
        ),
        "occurrence_identity": [
            "run",
            "time_band_with_full_half_open_interval_containment",
            "start_time",
            "end_time",
            "state_sequence",
        ],
        "time_band_occurrence_policy": (
            "sequence_x_time_band records require the full half-open occurrence "
            "[start,end) to remain in the requested time band"
        ),
        "conditional_metric_denominator": (
            "occurrence_status=matched and truth_status=defined; prediction "
            "missing/unknown remain with zero score"
        ),
        "end_to_end_metric_denominator": (
            "all records except matched records with truth_status=no_adl_overlap; "
            "no_occurrence and prediction missing/unknown remain with zero score"
        ),
        "no_adl_overlap_end_to_end_policy": "excluded_truth_undefined",
        "legacy_mean_metric_alias": "end_to_end",
        "occurrence_id_policy": "strict_own_eval_pattern_id",
        "sequence_fallback_enabled": False,
        "cross_id_physical_occurrence_owner_policy": (
            "lexicographically_smallest_eval_pattern_id_within_method_and_run"
        ),
        "fixed_frequency_bin_edges": list(fixed_edges) if mode == "fixed" else None,
        "frequency_bands": list(frequency_bands),
        "analysis_scope": args.analysis_scope,
        "n_states": getattr(args, "n_states", None),
        "hamming_threshold": getattr(args, "hamming_threshold", None),
        "days": getattr(args, "days", None),
        "evaluation6_details": str(args.evaluation6_details) if args.evaluation6_details else None,
        "input_summary": input_summary,
        "num_occurrences_source": occurrence_count_source,
        "output_dir": str(output_dir),
        "runs_evaluated": runs_evaluated,
        "num_methods": len(methods),
        "methods": methods,
        "overall_by_frequency_band": overall_by_band,
        "by_run_frequency_band": by_run_band,
        "occurrence_weighted_summary": weighted_summary,
        "occurrence_weight_validation": weight_validation,
        "output_files": output_files,
    }
    if args.analysis_scope in COMPARISON_SCOPES:
        summary["by_method_frequency_band"] = by_method_band
    (output_dir / "evaluation8_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    rows_to_print = by_method_band if args.analysis_scope in COMPARISON_SCOPES else overall_by_band
    return summary, rows_to_print


def main() -> None:
    args = parse_args()
    if args.output_dir is None:
        args.output_dir = default_output_dir(args.analysis_scope)
    if args.analysis_scope in COMPARISON_SCOPES:
        if args.evaluation6_details is None:
            raise ValueError("--evaluation6-details is required for a comparison analysis scope")
        source_rows, occurrence_count_source = load_details(args.evaluation6_details, args)
        input_summary = {"evaluation6_details": str(args.evaluation6_details)}
    else:
        source_rows, occurrence_count_source, input_summary = evaluate_proposed_154days(args)
    fixed_edges = parse_fixed_frequency_bin_edges(
        getattr(args, "fixed_frequency_bin_edges", ",".join(map(str, DEFAULT_FIXED_FREQUENCY_BIN_EDGES)))
    )
    modes = ("tertile", "fixed") if args.frequency_band_mode == "both" else (args.frequency_band_mode,)

    for mode in modes:
        output_dir = args.output_dir / mode if args.frequency_band_mode == "both" else args.output_dir
        _, rows_to_print = write_mode_outputs(
            args,
            source_rows,
            mode,
            fixed_edges,
            output_dir,
            occurrence_count_source,
            input_summary,
        )

        print(f"Evaluation 8 ({mode}) outputs saved to: {output_dir}")
        for row in rows_to_print:
            method = row.get("method", "proposed")
            precision = row.get("mean_multilabel_precision")
            recall = row.get("mean_multilabel_recall")
            f1 = row.get("mean_multilabel_f1")
            precision_text = "N/A" if precision is None else f"{float(precision):.6f}"
            recall_text = "N/A" if recall is None else f"{float(recall):.6f}"
            f1_text = "N/A" if f1 is None else f"{float(f1):.6f}"
            print(
                f"{method} {row['frequency_band']}: runs={row['num_runs']}, patterns={row['num_patterns']}, "
                f"precision={precision_text}, recall={recall_text}, f1={f1_text}"
            )


if __name__ == "__main__":
    main()
