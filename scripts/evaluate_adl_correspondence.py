#!/usr/bin/env python3
"""Evaluation 5: pattern-level ADL groundedness/uselessness."""

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
    FREQUENCY_MAX_SEQUENCE_LENGTH,
    FREQUENCY_MIN_SEQUENCE_LENGTH,
    FREQUENCY_TOP_K,
    HAMMING_THRESHOLD,
    N_STATES,
    ROOT_DIR,
)
from src.behavior_pattern_mining.evaluation.adl import (
    load_state_series_csv,
    parse_labeled_casas_intervals,
    parse_timestamp,
)
from src.behavior_pattern_mining.evaluation.adl_correspondence import (
    DEFAULT_OTHER_STATE_LABELS,
    EVALUATION5_ADL_CATEGORY_MAP,
    build_fp_growth_baseline_patterns,
    clip_adl_intervals,
    clip_state_intervals,
    compute_time_split_periods,
    ensure_baseline_pattern_files,
    evaluate_pattern_groundedness,
    expand_adl_intervals_for_evaluation5,
    find_occurrences_by_method,
    label_counts,
    load_method_patterns,
    train_pattern_adl_assignments,
    write_pattern_groundedness_outputs,
)


BASE_METHOD_ORDER = ["frequency", "rule_light", "rule_medium", "rule_strong", "proposed"]


def default_output_dir() -> Path:
    return ROOT_DIR / "results" / "5_adl_correspondence"


def default_paths() -> dict[str, Path]:
    param_suffix = f"{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"
    output_dir = ROOT_DIR / "output" / f"{DATASET_NAME}_{param_suffix}"
    return {
        "frequency": output_dir / f"state_sequence_counts_{param_suffix}.json",
        "rule_light": ROOT_DIR / "output" / "5_rule_filter" / "frequency_rule_light.csv",
        "rule_medium": ROOT_DIR / "output" / "5_rule_filter" / "frequency_rule_medium.csv",
        "rule_strong": ROOT_DIR / "output" / "5_rule_filter" / "frequency_rule_strong.csv",
        "proposed": output_dir / f"llm_sequences_modes_{param_suffix}_1.json",
    }


def parse_args() -> argparse.Namespace:
    paths = default_paths()
    parser = argparse.ArgumentParser(
        description="Evaluation 5: pattern-level ADL-grounded and Useless rates"
    )
    parser.add_argument(
        "--labeled-casas",
        type=Path,
        required=True,
        help="CASAS labeled text file with activity begin/end annotations",
    )
    parser.add_argument(
        "--state-series",
        type=Path,
        required=True,
        help="CSV with start_time,end_time,state_id or timestamp,state_id",
    )
    parser.add_argument("--patterns-frequency", type=Path, default=paths["frequency"])
    parser.add_argument("--patterns-rule-light", type=Path, default=paths["rule_light"])
    parser.add_argument("--patterns-rule-medium", type=Path, default=paths["rule_medium"])
    parser.add_argument("--patterns-rule-strong", type=Path, default=paths["rule_strong"])
    parser.add_argument("--patterns-proposed", type=Path, default=paths["proposed"])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir(),
        help="Directory for Evaluation 5 outputs",
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
        default=2.0,
        help="Maximum duration of one ignored その他 interval in skip-other mode",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.7,
        help="Chronological train split ratio when explicit dates are omitted",
    )
    parser.add_argument("--train-start-date", default=None)
    parser.add_argument("--train-end-date", default=None)
    parser.add_argument("--test-start-date", default=None)
    parser.add_argument("--test-end-date", default=None)
    parser.add_argument(
        "--min-overlap-seconds",
        type=float,
        default=1.0,
        help="Minimum overlap seconds required for one occurrence-level ADL hit",
    )
    parser.add_argument("--grounded-hit-threshold", type=float, default=0.3)
    parser.add_argument("--grounded-purity-threshold", type=float, default=0.3)
    parser.add_argument("--useless-hit-threshold", type=float, default=0.1)
    parser.add_argument("--useless-purity-threshold", type=float, default=0.1)
    parser.add_argument(
        "--assigned-adl-purity-threshold",
        type=float,
        default=0.10,
        help="Train overlap purity threshold for assigning ADL categories to a pattern",
    )
    parser.add_argument(
        "--assigned-adl-max-categories",
        type=int,
        default=3,
        help="Maximum number of train-assigned ADL categories per pattern",
    )
    parser.add_argument(
        "--assigned-adl-relative-threshold",
        type=float,
        default=0.5,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--assigned-adl-min-purity",
        type=float,
        default=0.05,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--enable-fp-growth-baseline",
        action="store_true",
        help="Generate fp_growth and fp_growth_filtered baselines from train state-series transactions.",
    )
    parser.add_argument("--fp-min-support", type=float, default=0.05)
    parser.add_argument("--fp-top-k", type=int, default=50)
    parser.add_argument("--fp-min-len", type=int, default=2)
    parser.add_argument("--fp-max-len", type=int, default=4)
    parser.add_argument("--fp-max-median-duration-seconds", type=float, default=1800.0)
    parser.add_argument("--fp-max-p90-duration-seconds", type=float, default=3600.0)
    parser.add_argument(
        "--other-state-labels",
        nargs="+",
        default=sorted(DEFAULT_OTHER_STATE_LABELS),
        help="State labels treated as other/noise for Useless-B A->Other->A detection",
    )
    parser.add_argument(
        "--exclude-other-adl-from-any",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exclude Other_ADL from any_adl_hit_rate/purity used by Useless-A",
    )
    parser.add_argument(
        "--include-no-test-support-in-denominator",
        action="store_true",
        help="Include train-supported patterns with no test occurrence in summary denominators",
    )
    parser.add_argument(
        "--no-auto-generate-baselines",
        action="store_true",
        help="Do not generate missing frequency/rule baselines from --state-series.",
    )
    return parser.parse_args()


def method_paths_from_args(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "frequency": args.patterns_frequency,
        "rule_light": args.patterns_rule_light,
        "rule_medium": args.patterns_rule_medium,
        "rule_strong": args.patterns_rule_strong,
        "proposed": args.patterns_proposed,
    }


def parse_optional_datetime(value: str | None):
    if value in (None, ""):
        return None
    return parse_timestamp(value)


def main() -> None:
    args = parse_args()
    if not args.labeled_casas.exists():
        raise FileNotFoundError(f"--labeled-casas does not exist: {args.labeled_casas}")
    if not args.state_series.exists():
        raise FileNotFoundError(f"--state-series does not exist: {args.state_series}")

    raw_labels = parse_labeled_casas_intervals(
        args.labeled_casas,
        wake_window_minutes=args.wake_window_minutes,
    )
    labels = expand_adl_intervals_for_evaluation5(raw_labels)
    state_intervals = load_state_series_csv(args.state_series)
    train_period, test_period = compute_time_split_periods(
        labels=labels,
        state_intervals=state_intervals,
        train_ratio=args.train_ratio,
        train_start_date=parse_optional_datetime(args.train_start_date),
        train_end_date=parse_optional_datetime(args.train_end_date),
        test_start_date=parse_optional_datetime(args.test_start_date),
        test_end_date=parse_optional_datetime(args.test_end_date),
    )
    train_labels = clip_adl_intervals(labels, *train_period)
    test_labels = clip_adl_intervals(labels, *test_period)
    train_state_intervals = clip_state_intervals(state_intervals, *train_period)
    test_state_intervals = clip_state_intervals(state_intervals, *test_period)

    print(f"ADL label intervals: {len(raw_labels)} raw / {len(labels)} expanded")
    print(f"State intervals: {len(state_intervals)}")
    print(f"Train period: {train_period[0]} - {train_period[1]}")
    print(f"Test period: {test_period[0]} - {test_period[1]}")
    print(f"Train ADL/state intervals: {len(train_labels)} / {len(train_state_intervals)}")
    print(f"Test ADL/state intervals: {len(test_labels)} / {len(test_state_intervals)}")

    patterns_by_method = {}
    skipped_methods = []
    notes = []
    method_paths = method_paths_from_args(args)
    method_order = list(BASE_METHOD_ORDER)
    if not args.no_auto_generate_baselines:
        generated_notes = ensure_baseline_pattern_files(
            method_paths=method_paths,
            state_intervals=train_state_intervals,
            min_length=FREQUENCY_MIN_SEQUENCE_LENGTH,
            max_length=FREQUENCY_MAX_SEQUENCE_LENGTH,
            top_k=FREQUENCY_TOP_K,
        )
        notes.extend(generated_notes)
        for note in generated_notes:
            print(note)

    for method in BASE_METHOD_ORDER:
        patterns, method_notes = load_method_patterns(method_paths[method], method)
        notes.extend(method_notes)
        if not patterns:
            skipped_methods.append({"method": method, "reason": "; ".join(method_notes) or "no valid patterns"})
            print(f"[WARN] skipped {method}: {skipped_methods[-1]['reason']}", file=sys.stderr)
            continue
        patterns_by_method[method] = patterns
        print(f"{method}: patterns={len(patterns)}")

    if args.enable_fp_growth_baseline:
        try:
            fp_patterns_by_method, fp_notes = build_fp_growth_baseline_patterns(
                state_intervals=train_state_intervals,
                min_support=args.fp_min_support,
                top_k=args.fp_top_k,
                min_len=args.fp_min_len,
                max_len=args.fp_max_len,
                other_state_labels=set(args.other_state_labels),
                max_median_duration_seconds=args.fp_max_median_duration_seconds,
                max_p90_duration_seconds=args.fp_max_p90_duration_seconds,
            )
            notes.extend(fp_notes)
            for note in fp_notes:
                print(note)
            insertion_index = method_order.index("proposed") if "proposed" in method_order else len(method_order)
            for method in ["fp_growth", "fp_growth_filtered"]:
                if method not in method_order:
                    method_order.insert(insertion_index, method)
                    insertion_index += 1
                patterns = fp_patterns_by_method.get(method, [])
                if not patterns:
                    reason = "no valid FP-Growth patterns after support/filter settings"
                    skipped_methods.append({"method": method, "reason": reason})
                    print(f"[WARN] skipped {method}: {reason}", file=sys.stderr)
                    continue
                patterns_by_method[method] = patterns
                print(f"{method}: patterns={len(patterns)}")
        except Exception as exc:
            for method in ["fp_growth", "fp_growth_filtered"]:
                skipped_methods.append({"method": method, "reason": f"FP-Growth baseline generation failed: {exc}"})
                print(f"[WARN] skipped {method}: {skipped_methods[-1]['reason']}", file=sys.stderr)

    patterns_by_method = {
        method: patterns_by_method[method]
        for method in method_order
        if method in patterns_by_method
    }

    if not patterns_by_method:
        raise RuntimeError("No valid pattern files were loaded.")

    train_occurrences_by_method = find_occurrences_by_method(
        patterns_by_method=patterns_by_method,
        state_intervals=train_state_intervals,
        match_mode=args.match_mode,
        max_skip_duration_minutes=args.max_skip_duration_minutes,
    )
    test_occurrences_by_method = find_occurrences_by_method(
        patterns_by_method=patterns_by_method,
        state_intervals=test_state_intervals,
        match_mode=args.match_mode,
        max_skip_duration_minutes=args.max_skip_duration_minutes,
    )
    for method in patterns_by_method:
        print(
            f"{method}: train_occurrences={len(train_occurrences_by_method.get(method, []))} "
            f"test_occurrences={len(test_occurrences_by_method.get(method, []))}"
        )

    train_assignments = train_pattern_adl_assignments(
        patterns_by_method=patterns_by_method,
        train_occurrences_by_method=train_occurrences_by_method,
        train_labels=train_labels,
        assigned_adl_purity_threshold=args.assigned_adl_purity_threshold,
        assigned_adl_max_categories=args.assigned_adl_max_categories,
    )
    detail_rows, summary_rows, summary_by_method = evaluate_pattern_groundedness(
        patterns_by_method=patterns_by_method,
        train_assignments=train_assignments,
        test_occurrences_by_method=test_occurrences_by_method,
        test_labels=test_labels,
        min_overlap_seconds=args.min_overlap_seconds,
        grounded_hit_threshold=args.grounded_hit_threshold,
        grounded_purity_threshold=args.grounded_purity_threshold,
        useless_hit_threshold=args.useless_hit_threshold,
        useless_purity_threshold=args.useless_purity_threshold,
        include_no_test_support_in_denominator=args.include_no_test_support_in_denominator,
        exclude_other_adl_from_any=args.exclude_other_adl_from_any,
        other_state_labels=set(args.other_state_labels),
    )

    summary = {
        "rq": "Can the proposed method reduce useless patterns compared with frequency and rule-filtered baselines?",
        "labeled_casas_path": str(args.labeled_casas),
        "state_series_path": str(args.state_series),
        "pattern_paths": {method: str(path) for method, path in method_paths.items()},
        "methods": list(patterns_by_method),
        "skipped_methods": skipped_methods,
        "train_ratio": args.train_ratio,
        "train_period": {
            "start": train_period[0].isoformat(sep=" "),
            "end": train_period[1].isoformat(sep=" "),
        },
        "test_period": {
            "start": test_period[0].isoformat(sep=" "),
            "end": test_period[1].isoformat(sep=" "),
        },
        "thresholds": {
            "grounded_hit_threshold": args.grounded_hit_threshold,
            "grounded_purity_threshold": args.grounded_purity_threshold,
            "useless_hit_threshold": args.useless_hit_threshold,
            "useless_purity_threshold": args.useless_purity_threshold,
            "min_overlap_seconds": args.min_overlap_seconds,
            "assigned_adl_purity_threshold": args.assigned_adl_purity_threshold,
            "assigned_adl_max_categories": args.assigned_adl_max_categories,
            "fp_min_support": args.fp_min_support,
            "fp_top_k": args.fp_top_k,
            "fp_min_len": args.fp_min_len,
            "fp_max_len": args.fp_max_len,
            "fp_max_median_duration_seconds": args.fp_max_median_duration_seconds,
            "fp_max_p90_duration_seconds": args.fp_max_p90_duration_seconds,
        },
        "deprecated_ignored_thresholds": {
            "assigned_adl_relative_threshold": args.assigned_adl_relative_threshold,
            "assigned_adl_min_purity": args.assigned_adl_min_purity,
        },
        "definition": {
            "adl_grounded": (
                "assigned_adl_hit_rate >= grounded_hit_threshold or assigned_adl_purity >= "
                "grounded_purity_threshold on test data using the train-assigned ADL set"
            ),
            "useless": "useless_a OR useless_b OR useless_c",
            "useless_a": (
                "any_adl_hit_rate < useless_hit_threshold and any_adl_purity < "
                "useless_purity_threshold on test data"
            ),
            "useless_b": "the sequence contains A -> Other -> A",
            "useless_c": "the sequence contains A -> B -> A -> B",
        },
        "useless_definition": {
            "useless": "useless_a OR useless_b OR useless_c",
            "useless_a": (
                f"any_adl_hit_rate < {args.useless_hit_threshold} and any_adl_purity < "
                f"{args.useless_purity_threshold} on test data"
            ),
            "useless_b": "the sequence contains A -> Other -> A",
            "useless_c": "the sequence contains A -> B -> A -> B",
        },
        "multi_label_adl_mapping": True,
        "assigned_adl_set_definition": {
            "method": "purity_threshold",
            "purity_threshold": args.assigned_adl_purity_threshold,
            "max_categories": args.assigned_adl_max_categories,
            "description": (
                f"ADL categories whose train overlap purity is at least "
                f"{args.assigned_adl_purity_threshold:.2f} are assigned. The max-overlap ADL is "
                f"always included if overlap > 0. At most {args.assigned_adl_max_categories} "
                "categories are kept by overlap duration."
            ),
            "other_adl_policy": (
                "Other_ADL is excluded when any non-Other_ADL overlap exists. Other_ADL may be "
                "assigned only when it is the only overlapping category."
            ),
        },
        "other_state_labels": list(args.other_state_labels),
        "exclude_other_adl_from_any": args.exclude_other_adl_from_any,
        "fp_growth_baseline": {
            "enabled": args.enable_fp_growth_baseline,
            "transaction_definition": "date-by-time-period transaction; contiguous state n-grams are items",
            "filter_definition": {
                "structural": [
                    "contains self transition A->A",
                    "contains A->Other->A",
                    "contains A->B->A->B",
                ],
                "temporal": [
                    "median_duration_seconds > fp_max_median_duration_seconds",
                    "p90_duration_seconds > fp_max_p90_duration_seconds",
                ],
            },
        },
        "include_no_test_support_in_denominator": args.include_no_test_support_in_denominator,
        "wake_window_minutes": args.wake_window_minutes,
        "match_mode": args.match_mode,
        "max_skip_duration_minutes": args.max_skip_duration_minutes,
        "adl_category_map": {key: list(value) for key, value in EVALUATION5_ADL_CATEGORY_MAP.items()},
        "num_raw_adl_intervals": len(raw_labels),
        "num_adl_intervals": len(labels),
        "num_state_intervals": len(state_intervals),
        "num_train_adl_intervals": len(train_labels),
        "num_test_adl_intervals": len(test_labels),
        "num_train_state_intervals": len(train_state_intervals),
        "num_test_state_intervals": len(test_state_intervals),
        "truth_intervals_by_category": label_counts(labels),
        "train_truth_intervals_by_category": label_counts(train_labels),
        "test_truth_intervals_by_category": label_counts(test_labels),
        "patterns_by_method": {method: len(patterns) for method, patterns in patterns_by_method.items()},
        "train_occurrences_by_method": {
            method: len(occurrences) for method, occurrences in train_occurrences_by_method.items()
        },
        "test_occurrences_by_method": {
            method: len(occurrences) for method, occurrences in test_occurrences_by_method.items()
        },
        "summary_by_method": summary_by_method,
        "notes": notes,
    }

    write_pattern_groundedness_outputs(
        output_dir=args.output_dir,
        pattern_detail_rows=detail_rows,
        summary_rows=summary_rows,
        summary=summary,
    )

    print(f"Evaluation 5 pattern-level outputs saved to: {args.output_dir}")
    if skipped_methods:
        skipped_names = ", ".join(item["method"] for item in skipped_methods)
        print(f"Skipped methods: {skipped_names}")


if __name__ == "__main__":
    main()
