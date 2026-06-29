#!/usr/bin/env python3
"""Evaluate extracted state-sequence patterns against labeled CASAS ADLs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(ROOT_DIR_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR_FOR_IMPORTS))

from experiment_config import DATASET_NAME, DAYS, HAMMING_THRESHOLD, N_STATES, ROOT_DIR
from src.behavior_pattern_mining.evaluation.adl import (
    ADL_CATEGORY_MAP,
    assign_patterns_to_adl,
    boundary_rows,
    build_predictions,
    build_state_series_from_event_log,
    filter_intervals_by_period,
    find_pattern_occurrences,
    greedy_match_by_category,
    load_patterns,
    load_state_series_csv,
    macro_micro_average,
    metrics_rows_from_counts,
    parse_labeled_casas_intervals,
    parse_timestamp,
    split_time_from_ratio,
    write_evaluation_outputs,
    write_state_series_csv,
)


def default_output_dir() -> Path:
    return ROOT_DIR / "results" / "adl_evaluation"


def parse_args() -> argparse.Namespace:
    param_suffix = f"{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"
    parser = argparse.ArgumentParser(description="ADL evaluation using labeled CASAS data")
    parser.add_argument(
        "--labeled-casas",
        type=Path,
        default=ROOT_DIR / "new_labeled_data" / f"{DATASET_NAME}.txt",
        help="CASAS labeled text file with activity begin/end annotations",
    )
    parser.add_argument(
        "--state-series",
        type=Path,
        default=None,
        help="Optional CSV with start_time,end_time,state_id or timestamp,state_id",
    )
    parser.add_argument(
        "--event-log",
        type=Path,
        default=ROOT_DIR / "data" / f"{DATASET_NAME}.csv",
        help="Event log used to rebuild representative-state intervals when --state-series is omitted",
    )
    parser.add_argument(
        "--state-table",
        type=Path,
        default=ROOT_DIR / "state" / f"{DATASET_NAME}_{param_suffix}.txt",
        help="Representative state table TSV",
    )
    parser.add_argument(
        "--patterns",
        type=Path,
        default=ROOT_DIR / "output" / f"{DATASET_NAME}_{param_suffix}" / f"llm_sequences_modes_{param_suffix}_1.json",
        help="LLM pattern JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir(),
        help="Directory for ADL evaluation outputs",
    )
    parser.add_argument(
        "--iou-thresholds",
        type=float,
        nargs="+",
        default=[0.3, 0.5],
        help="Temporal IoU thresholds",
    )
    parser.add_argument(
        "--wake-window-minutes",
        type=float,
        default=30.0,
        help="Minutes after Sleeping end treated as Wake-up context",
    )
    parser.add_argument(
        "--match-mode",
        choices=["exact", "skip-other"],
        default="exact",
        help="State sequence matching mode",
    )
    parser.add_argument(
        "--max-skip-duration-minutes",
        type=float,
        default=1.0,
        help="Maximum duration of one ignored その他 interval in skip-other mode",
    )
    parser.add_argument(
        "--hamming-threshold",
        type=int,
        default=HAMMING_THRESHOLD,
        help="Hamming threshold used when rebuilding state intervals from --event-log",
    )
    parser.add_argument(
        "--split-date",
        type=str,
        default=None,
        help="Optional split timestamp. Mapping is learned before this time and evaluated after it.",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=None,
        help="Optional time-ratio split when --split-date is omitted.",
    )
    parser.add_argument(
        "--write-state-series",
        type=Path,
        default=None,
        help="Optional path to save rebuilt state intervals as CSV",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    labels = parse_labeled_casas_intervals(
        args.labeled_casas,
        wake_window_minutes=args.wake_window_minutes,
    )
    patterns = load_patterns(args.patterns)

    if args.state_series is not None:
        state_intervals = load_state_series_csv(args.state_series)
        state_series_source = str(args.state_series)
    else:
        state_intervals = build_state_series_from_event_log(
            event_log_path=args.event_log,
            state_table_path=args.state_table,
            hamming_threshold=args.hamming_threshold,
        )
        state_series_source = f"{args.event_log} + {args.state_table}"

    if args.write_state_series is not None:
        write_state_series_csv(state_intervals, args.write_state_series)

    split_time = parse_timestamp(args.split_date) if args.split_date else split_time_from_ratio(labels, args.train_ratio)

    if split_time is None:
        mapping_labels = labels
        mapping_state_intervals = state_intervals
        eval_labels = labels
        eval_state_intervals = state_intervals
    else:
        mapping_labels = filter_intervals_by_period(labels, start_time=None, end_time=split_time)
        mapping_state_intervals = filter_intervals_by_period(state_intervals, start_time=None, end_time=split_time)
        eval_labels = filter_intervals_by_period(labels, start_time=split_time, end_time=None)
        eval_state_intervals = filter_intervals_by_period(state_intervals, start_time=split_time, end_time=None)

    mapping_occurrences = find_pattern_occurrences(
        patterns,
        mapping_state_intervals,
        match_mode=args.match_mode,
        max_skip_duration_minutes=args.max_skip_duration_minutes,
    )
    mappings = assign_patterns_to_adl(patterns, mapping_occurrences, mapping_labels)

    eval_occurrences = find_pattern_occurrences(
        patterns,
        eval_state_intervals,
        match_mode=args.match_mode,
        max_skip_duration_minutes=args.max_skip_duration_minutes,
    )
    predictions = build_predictions(eval_occurrences, mappings)

    metrics_by_threshold = {}
    boundary_by_threshold = {}
    averages_by_threshold = {}
    for threshold in args.iou_thresholds:
        matches, counts = greedy_match_by_category(predictions, eval_labels, iou_threshold=threshold)
        metric_rows = metrics_rows_from_counts(counts)
        metrics_by_threshold[threshold] = metric_rows
        boundary_by_threshold[threshold] = boundary_rows(matches)
        averages_by_threshold[str(threshold)] = macro_micro_average(metric_rows)

    summary = {
        "labeled_casas_path": str(args.labeled_casas),
        "state_series_source": state_series_source,
        "patterns_path": str(args.patterns),
        "state_table_path": str(args.state_table),
        "event_log_path": str(args.event_log),
        "output_dir": str(args.output_dir),
        "match_mode": args.match_mode,
        "max_skip_duration_minutes": args.max_skip_duration_minutes,
        "wake_window_minutes": args.wake_window_minutes,
        "iou_thresholds": args.iou_thresholds,
        "split_time": split_time.isoformat(sep=" ") if split_time else None,
        "num_adl_intervals": len(labels),
        "num_patterns": len(patterns),
        "num_mapping_occurrences": len(mapping_occurrences),
        "num_eval_occurrences": len(eval_occurrences),
        "num_predictions": len(predictions),
        "adl_category_map": ADL_CATEGORY_MAP,
        "averages_by_iou_threshold": averages_by_threshold,
    }

    write_evaluation_outputs(
        output_dir=args.output_dir,
        occurrences=eval_occurrences,
        mappings=mappings,
        metrics_by_threshold=metrics_by_threshold,
        boundary_by_threshold=boundary_by_threshold,
        summary=summary,
    )

    print(f"ADL evaluation outputs saved to: {args.output_dir}")
    print(f"Patterns: {len(patterns)} / occurrences: {len(eval_occurrences)} / predictions: {len(predictions)}")


if __name__ == "__main__":
    main()
