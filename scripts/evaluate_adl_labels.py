#!/usr/bin/env python3
"""Evaluate extracted state-sequence patterns against labeled CASAS ADLs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(ROOT_DIR_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR_FOR_IMPORTS))

from experiment_config import (
    DATASET_NAME,
    DAYS,
    HAMMING_THRESHOLD,
    N_STATES,
    ROOT_DIR,
    SMOOTHING_WINDOW_SEC,
)
from src.behavior_pattern_mining.evaluation.adl import (
    ADL_CATEGORY_MAP,
    assign_patterns_to_adl,
    boundary_rows,
    build_predictions,
    build_network_equivalent_state_series_from_labeled_casas,
    build_state_series_from_event_log,
    build_state_series_from_labeled_casas,
    compute_interval_hit_evaluation,
    filter_predictions_by_duration,
    filter_intervals_by_period,
    find_pattern_occurrences,
    greedy_match_by_category,
    load_min_duration_config,
    load_patterns,
    load_state_series_csv,
    macro_micro_average,
    merge_prediction_intervals,
    merged_to_prediction_intervals,
    metrics_rows_from_counts,
    parse_labeled_casas_intervals,
    parse_timestamp,
    split_time_from_ratio,
    write_evaluation_outputs,
    write_state_series_csv,
)


def default_output_dir() -> Path:
    return ROOT_DIR / "results" / "4_adl_detect"


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
        default=None,
        help="Optional unlabeled event log used to rebuild representative-state intervals. If omitted, --labeled-casas is used.",
    )
    parser.add_argument(
        "--state-table",
        type=Path,
        default=ROOT_DIR / "state" / f"{DATASET_NAME}_{param_suffix}.txt",
        help="Representative state table TSV",
    )
    parser.add_argument(
        "--sensor-map",
        type=Path,
        default=ROOT_DIR / "configs" / "aruba_sensor_map.json",
        help="JSON map from labeled CASAS sensor IDs to representative-state sensor names",
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
        help="Hamming threshold used when rebuilding state intervals",
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
    parser.add_argument(
        "--state-series-preprocessing",
        choices=["event-driven", "network-equivalent"],
        default="event-driven",
        help=(
            "Preprocessing used when rebuilding state intervals. "
            "network-equivalent applies 1-second Sample-and-Hold, delayed-OFF "
            "smoothing, fixed representative-state mapping, and compression."
        ),
    )
    parser.add_argument(
        "--smoothing-window-sec",
        type=int,
        default=SMOOTHING_WINDOW_SEC,
        help="Delayed-OFF rolling window used by network-equivalent preprocessing",
    )
    parser.add_argument(
        "--state-series-days",
        type=int,
        default=None,
        help=(
            "Calendar days exported by network-equivalent preprocessing. "
            "Omit to use the complete labeled-data date range."
        ),
    )
    parser.add_argument(
        "--state-series-only",
        action="store_true",
        help=(
            "Build/write the state-series CSV and exit before pattern/ADL evaluation. "
            "--write-state-series is required."
        ),
    )
    parser.add_argument(
        "--merge-gap-minutes",
        type=float,
        default=5.0,
        help="Merge predictions with the same ADL when the time gap is within this many minutes. Use 0 to disable merging.",
    )
    parser.add_argument(
        "--min-duration-config",
        type=Path,
        default=None,
        help="Optional JSON mapping ADL category to minimum prediction duration in seconds after merge.",
    )
    parser.add_argument(
        "--hit-tolerance-minutes",
        type=float,
        default=10.0,
        help="Tolerance window before/after each true ADL interval for interval-hit evaluation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.state_series_only and args.write_state_series is None:
        raise ValueError("--state-series-only requires --write-state-series")

    if args.state_series is not None:
        state_intervals = load_state_series_csv(args.state_series)
        state_series_source = str(args.state_series)
    elif args.event_log is None:
        if args.state_series_preprocessing == "network-equivalent":
            state_intervals = build_network_equivalent_state_series_from_labeled_casas(
                labeled_casas_path=args.labeled_casas,
                state_table_path=args.state_table,
                hamming_threshold=args.hamming_threshold,
                smoothing_window_sec=args.smoothing_window_sec,
                sensor_map_path=args.sensor_map if args.sensor_map.exists() else None,
                duration_days=args.state_series_days,
            )
            state_series_source = (
                f"{args.labeled_casas} + {args.state_table} "
                f"(network-equivalent, smoothing={args.smoothing_window_sec}s, "
                f"days={args.state_series_days or 'all'})"
            )
        else:
            state_intervals = build_state_series_from_labeled_casas(
                labeled_casas_path=args.labeled_casas,
                state_table_path=args.state_table,
                hamming_threshold=args.hamming_threshold,
                sensor_map_path=args.sensor_map if args.sensor_map.exists() else None,
            )
            state_series_source = f"{args.labeled_casas} + {args.state_table}"
    else:
        if args.state_series_preprocessing == "network-equivalent":
            raise ValueError(
                "--state-series-preprocessing network-equivalent currently requires "
                "--labeled-casas and cannot be combined with --event-log."
            )
        state_intervals = build_state_series_from_event_log(
            event_log_path=args.event_log,
            state_table_path=args.state_table,
            hamming_threshold=args.hamming_threshold,
        )
        state_series_source = f"{args.event_log} + {args.state_table}"

    if args.write_state_series is not None:
        write_state_series_csv(state_intervals, args.write_state_series)
    if args.state_series_only:
        print(
            f"State-series only: wrote {len(state_intervals)} compressed intervals "
            f"to {args.write_state_series}"
        )
        return

    labels = parse_labeled_casas_intervals(
        args.labeled_casas,
        wake_window_minutes=args.wake_window_minutes,
    )
    patterns = load_patterns(args.patterns)

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
    raw_predictions = build_predictions(eval_occurrences, mappings)
    merged_predictions = merge_prediction_intervals(raw_predictions, merge_gap_minutes=args.merge_gap_minutes)
    min_duration_by_adl = load_min_duration_config(args.min_duration_config)
    filtered_predictions, removed_by_duration_filter = filter_predictions_by_duration(
        merged_predictions,
        min_duration_by_adl,
    )
    predictions = merged_to_prediction_intervals(filtered_predictions)
    hit_metric_rows, hit_detail_rows = compute_interval_hit_evaluation(
        filtered_predictions,
        eval_labels,
        hit_tolerance_minutes=args.hit_tolerance_minutes,
    )

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
        "state_series_preprocessing": args.state_series_preprocessing,
        "smoothing_window_sec": (
            args.smoothing_window_sec
            if args.state_series_preprocessing == "network-equivalent"
            else None
        ),
        "state_series_days": args.state_series_days,
        "patterns_path": str(args.patterns),
        "state_table_path": str(args.state_table),
        "event_log_path": str(args.event_log) if args.event_log else None,
        "sensor_map_path": str(args.sensor_map) if args.sensor_map else None,
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
        "prediction_postprocess": {
            "merge_gap_minutes": args.merge_gap_minutes,
            "min_duration_config_path": str(args.min_duration_config) if args.min_duration_config else None,
            "min_duration_by_adl_seconds": min_duration_by_adl,
            "hit_tolerance_minutes": args.hit_tolerance_minutes,
            "num_predictions_before_merge": len(raw_predictions),
            "num_predictions_after_merge": len(merged_predictions),
            "num_predictions_after_duration_filter": len(filtered_predictions),
            "removed_by_duration_filter": removed_by_duration_filter,
        },
        "interval_hit_evaluation": {
            hit_type: {
                row["adl_category"]: {
                    "true_intervals": row["true_intervals"],
                    "hit_intervals": row["hit_intervals"],
                    "missed_intervals": row["missed_intervals"],
                    "hit_rate": row["hit_rate"],
                    "prediction_intervals": row["prediction_intervals"],
                    "matched_prediction_intervals": row["matched_prediction_intervals"],
                    "unmatched_prediction_intervals": row["unmatched_prediction_intervals"],
                    "prediction_hit_precision": row["prediction_hit_precision"],
                }
                for row in hit_metric_rows
                if row["hit_type"] == hit_type
            }
            for hit_type in sorted({row["hit_type"] for row in hit_metric_rows})
        },
    }

    write_evaluation_outputs(
        output_dir=args.output_dir,
        occurrences=eval_occurrences,
        mappings=mappings,
        metrics_by_threshold=metrics_by_threshold,
        boundary_by_threshold=boundary_by_threshold,
        summary=summary,
        merged_predictions=merged_predictions,
        filtered_predictions=filtered_predictions,
        hit_metric_rows=hit_metric_rows,
        hit_detail_rows=hit_detail_rows,
    )

    print(f"ADL evaluation outputs saved to: {args.output_dir}")
    print(
        "Patterns: "
        f"{len(patterns)} / occurrences: {len(eval_occurrences)} / "
        f"raw predictions: {len(raw_predictions)} / "
        f"merged: {len(merged_predictions)} / "
        f"filtered: {len(filtered_predictions)}"
    )


if __name__ == "__main__":
    main()
