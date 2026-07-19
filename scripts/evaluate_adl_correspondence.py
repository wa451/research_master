#!/usr/bin/env python3
"""Evaluation 5: pattern-level ADL groundedness/uselessness."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any

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
    MethodPattern,
    build_transition_probability_baseline_patterns,
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
    load_state_low_information_map,
    parse_sequence,
    train_pattern_adl_assignments,
    validate_state_attribute_coverage,
    write_pattern_groundedness_outputs,
)


BASE_METHOD_ORDER = ["frequency", "rule_light", "rule_medium", "rule_strong", "proposed"]
STATIC_BASE_METHODS = ["frequency", "rule_light", "rule_medium", "rule_strong"]
FP_GROWTH_METHODS = ["fp_growth", "fp_growth_filtered"]
TRANSITION_METHOD = "transition_probability"
PATTERN_CACHE_COLUMNS = [
    "method",
    "pattern_id",
    "pattern_name",
    "sequence",
    "count",
    "pattern_source",
    "time_band",
    "support_transactions",
    "support_ratio",
    "train_occurrence_count",
    "median_duration_seconds",
    "p90_duration_seconds",
    "is_fp_filtered_out",
    "fp_filter_reason",
    "transition_joint_probability",
    "transition_min_step_probability",
]


def default_output_dir() -> Path:
    return ROOT_DIR / "results" / "5_pattern_quality_fixed"


def default_baseline_cache_dir() -> Path:
    return ROOT_DIR / "output" / "5_adl_correspondence_baselines_fixed"


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
        description="Evaluation 5: useful non-redundant, fragmentation, and contextless-useless rates"
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
    state_attribute_group = parser.add_mutually_exclusive_group(required=True)
    state_attribute_group.add_argument(
        "--state-definition",
        type=Path,
        help=(
            "Representative-state TSV used to resolve state IDs and active sensors "
            "for low-information checks"
        ),
    )
    state_attribute_group.add_argument(
        "--state-network-json",
        type=Path,
        help=(
            "State-transition network JSON with nodes[].state_id and "
            "nodes[].active_sensors, used instead of --state-definition"
        ),
    )
    parser.add_argument("--patterns-frequency", type=Path, default=paths["frequency"])
    parser.add_argument("--patterns-rule-light", type=Path, default=paths["rule_light"])
    parser.add_argument("--patterns-rule-medium", type=Path, default=paths["rule_medium"])
    parser.add_argument("--patterns-rule-strong", type=Path, default=paths["rule_strong"])
    parser.add_argument("--patterns-proposed", type=Path, default=paths["proposed"])
    parser.add_argument(
        "--patterns-proposed-template",
        type=str,
        default=None,
        help=(
            "Optional proposed pattern path template for multi-run evaluation. "
            "Use {run}, e.g. output/aruba_15_0_154days/llm_sequences_modes_15_0_154days_{run}.json"
        ),
    )
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
        "--enable-transition-baseline",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate transition_probability baseline from train state-series transitions.",
    )
    parser.add_argument("--transition-top-k", type=int, default=50)
    parser.add_argument("--transition-min-prob", type=float, default=0.0)
    parser.add_argument("--transition-min-len", type=int, default=2)
    parser.add_argument("--transition-max-len", type=int, default=4)
    parser.add_argument(
        "--baseline-cache-dir",
        type=Path,
        default=default_baseline_cache_dir(),
        help="Directory used to cache generated FP-Growth and transition_probability baseline pattern CSVs.",
    )
    parser.add_argument(
        "--use-baseline-cache",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reuse cached generated baseline pattern CSVs when the input/config hash matches.",
    )
    parser.add_argument("--fragmentation-containment-threshold", type=float, default=0.7)
    parser.add_argument("--low-information-threshold", type=float, default=0.5)
    parser.add_argument(
        "--other-state-labels",
        nargs="+",
        default=sorted(DEFAULT_OTHER_STATE_LABELS),
        help="State labels treated as other/noise for structural and low-information checks",
    )
    parser.add_argument(
        "--exclude-other-adl-from-any",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exclude Other_ADL from any ADL overlap used by contextless-useless ADL support checks.",
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
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of proposed LLM runs to evaluate and average. Default keeps single-run behavior.",
    )
    parser.add_argument(
        "--skip-missing-runs",
        action="store_true",
        help="Skip missing proposed run files instead of stopping. Skipped files are recorded in summary JSON.",
    )
    return parser.parse_args()


def path_for_run(base_path: Path, run: int, template: str | None) -> Path:
    """Resolve one proposed-method JSON path while preserving the historical run-1 default."""
    if template:
        return Path(template.format(run=run))
    if run == 1:
        return base_path

    stem = base_path.stem
    suffix = base_path.suffix
    prefix, sep, last = stem.rpartition("_")
    if sep and last.isdigit():
        return base_path.with_name(f"{prefix}_{run}{suffix}")
    return base_path.with_name(f"{stem}_{run}{suffix}")


def method_paths_from_args(args: argparse.Namespace, proposed_path: Path | None = None) -> dict[str, Path]:
    return {
        "frequency": args.patterns_frequency,
        "rule_light": args.patterns_rule_light,
        "rule_medium": args.patterns_rule_medium,
        "rule_strong": args.patterns_rule_strong,
        "proposed": proposed_path or args.patterns_proposed,
    }


def parse_optional_datetime(value: str | None):
    if value in (None, ""):
        return None
    return parse_timestamp(value)


def _empty_to_none(value: Any) -> Any:
    return None if value in (None, "") else value


def _to_int(value: Any) -> int | None:
    value = _empty_to_none(value)
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    value = _empty_to_none(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cache_cell(value: Any) -> str:
    return "" if value is None else str(value)


def write_pattern_cache(path: Path, patterns: list[MethodPattern]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PATTERN_CACHE_COLUMNS)
        writer.writeheader()
        for pattern in patterns:
            writer.writerow(
                {
                    "method": pattern.method,
                    "pattern_id": pattern.pattern_id,
                    "pattern_name": pattern.pattern_name,
                    "sequence": " -> ".join(pattern.sequence),
                    "count": _cache_cell(pattern.count),
                    "pattern_source": pattern.pattern_source,
                    "time_band": pattern.time_band,
                    "support_transactions": _cache_cell(pattern.support_transactions),
                    "support_ratio": _cache_cell(pattern.support_ratio),
                    "train_occurrence_count": _cache_cell(pattern.train_occurrence_count),
                    "median_duration_seconds": _cache_cell(pattern.median_duration_seconds),
                    "p90_duration_seconds": _cache_cell(pattern.p90_duration_seconds),
                    "is_fp_filtered_out": _cache_cell(pattern.is_fp_filtered_out),
                    "fp_filter_reason": pattern.fp_filter_reason,
                    "transition_joint_probability": _cache_cell(pattern.transition_joint_probability),
                    "transition_min_step_probability": _cache_cell(pattern.transition_min_step_probability),
                }
            )


def load_pattern_cache(path: Path, method: str) -> list[MethodPattern]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    patterns: list[MethodPattern] = []
    for index, row in enumerate(rows, start=1):
        sequence = parse_sequence(row.get("sequence"))
        if len(sequence) < 2:
            continue
        patterns.append(
            MethodPattern(
                method=method,
                pattern_id=str(row.get("pattern_id") or f"{method[:2].upper()}{index:03d}"),
                pattern_name=str(row.get("pattern_name") or " -> ".join(sequence)),
                sequence=sequence,
                count=_to_int(row.get("count")),
                pattern_source=str(row.get("pattern_source") or ""),
                time_band=str(row.get("time_band") or ""),
                support_transactions=_to_int(row.get("support_transactions")),
                support_ratio=_to_float(row.get("support_ratio")),
                train_occurrence_count=_to_int(row.get("train_occurrence_count")),
                median_duration_seconds=_to_float(row.get("median_duration_seconds")),
                p90_duration_seconds=_to_float(row.get("p90_duration_seconds")),
                is_fp_filtered_out=_to_int(row.get("is_fp_filtered_out")),
                fp_filter_reason=str(row.get("fp_filter_reason") or ""),
                transition_joint_probability=_to_float(row.get("transition_joint_probability")),
                transition_min_step_probability=_to_float(row.get("transition_min_step_probability")),
            )
        )
    return patterns


def baseline_cache_key(args: argparse.Namespace, train_period, baseline_kind: str) -> str:
    state_stat = args.state_series.stat()
    payload: dict[str, Any] = {
        "baseline_kind": baseline_kind,
        "state_series_path": str(args.state_series.resolve()),
        "state_series_size": state_stat.st_size,
        "state_series_mtime_ns": state_stat.st_mtime_ns,
        "train_start": train_period[0].isoformat(sep=" "),
        "train_end": train_period[1].isoformat(sep=" "),
        "match_version": "evaluation5_baseline_cache_v1",
    }
    if baseline_kind == "fp_growth":
        payload.update(
            {
                "fp_min_support": args.fp_min_support,
                "fp_top_k": args.fp_top_k,
                "fp_min_len": args.fp_min_len,
                "fp_max_len": args.fp_max_len,
                "fp_max_median_duration_seconds": args.fp_max_median_duration_seconds,
                "fp_max_p90_duration_seconds": args.fp_max_p90_duration_seconds,
                "other_state_labels": sorted(args.other_state_labels),
            }
        )
    elif baseline_kind == "transition_probability":
        payload.update(
            {
                "transition_top_k": args.transition_top_k,
                "transition_min_prob": args.transition_min_prob,
                "transition_min_len": args.transition_min_len,
                "transition_max_len": args.transition_max_len,
            }
        )
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def baseline_cache_path(args: argparse.Namespace, method: str, baseline_kind: str, train_period) -> Path:
    key = baseline_cache_key(args, train_period, baseline_kind)
    return args.baseline_cache_dir / f"evaluation5_{method}_{key}.csv"


def load_or_build_fp_growth_baselines(
    args: argparse.Namespace,
    train_state_intervals,
    train_period,
) -> tuple[dict[str, list[MethodPattern]], list[str]]:
    cache_paths = {
        method: baseline_cache_path(args, method, "fp_growth", train_period)
        for method in FP_GROWTH_METHODS
    }
    if args.use_baseline_cache and all(path.exists() for path in cache_paths.values()):
        patterns_by_method = {
            method: load_pattern_cache(path, method)
            for method, path in cache_paths.items()
        }
        notes = [
            f"{method}: loaded cached baseline patterns: {path}"
            for method, path in cache_paths.items()
        ]
        return patterns_by_method, notes

    patterns_by_method, notes = build_fp_growth_baseline_patterns(
        state_intervals=train_state_intervals,
        min_support=args.fp_min_support,
        top_k=args.fp_top_k,
        min_len=args.fp_min_len,
        max_len=args.fp_max_len,
        other_state_labels=set(args.other_state_labels),
        max_median_duration_seconds=args.fp_max_median_duration_seconds,
        max_p90_duration_seconds=args.fp_max_p90_duration_seconds,
    )
    if args.use_baseline_cache:
        for method in FP_GROWTH_METHODS:
            write_pattern_cache(cache_paths[method], patterns_by_method.get(method, []))
            notes.append(f"{method}: saved baseline pattern cache: {cache_paths[method]}")
    return patterns_by_method, notes


def load_or_build_transition_baseline(
    args: argparse.Namespace,
    train_state_intervals,
    train_period,
) -> tuple[list[MethodPattern], list[str]]:
    cache_path = baseline_cache_path(args, TRANSITION_METHOD, "transition_probability", train_period)
    if args.use_baseline_cache and cache_path.exists():
        return load_pattern_cache(cache_path, TRANSITION_METHOD), [
            f"{TRANSITION_METHOD}: loaded cached baseline patterns: {cache_path}"
        ]

    patterns, notes = build_transition_probability_baseline_patterns(
        state_intervals=train_state_intervals,
        top_k=args.transition_top_k,
        min_prob=args.transition_min_prob,
        min_len=args.transition_min_len,
        max_len=args.transition_max_len,
    )
    if args.use_baseline_cache:
        write_pattern_cache(cache_path, patterns)
        notes.append(f"{TRANSITION_METHOD}: saved baseline pattern cache: {cache_path}")
    return patterns, notes


def aggregate_run_summaries(summary_rows_by_run: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    count_names = [
        "output_record_count",
        "unique_sequence_count",
        "num_evaluable_patterns",
        "num_excluded_patterns",
        "num_adl_grounded",
        "num_low_information",
        "num_contextless_useless",
        "num_fragmented",
        "num_useful_non_redundant",
        "num_comparable_fragment_pairs",
        "num_comparable_fragment_children",
    ]
    metric_names = [
        "useful_non_redundant_pattern_rate",
        "contextless_useless_rate",
    ]
    rows_by_method: dict[str, list[dict]] = {}
    for row in summary_rows_by_run:
        rows_by_method.setdefault(str(row["method"]), []).append(row)

    if not summary_rows_by_run:
        return [], {}

    has_multiple_runs = len({int(row.get("run", 1)) for row in summary_rows_by_run}) > 1
    summary_rows: list[dict] = []
    summary_by_method: dict[str, dict] = {}
    for method, rows in rows_by_method.items():
        if not has_multiple_runs:
            summary = {
                key: value
                for key, value in rows[0].items()
                if key != "run"
            }
            if summary.get("fragmentation_rate") in (None, ""):
                summary["fragmentation_rate"] = 0.0
            summary["fragmentation_status"] = "evaluated"
            summary["fragmentation_rate_num_valid_runs"] = 1
            summary["fragmentation_rate_num_na_runs"] = 0
        else:
            summary = {"method": method, "num_runs": len(rows)}
            for count_name in count_names:
                values = [
                    float(row[count_name])
                    for row in rows
                    if row.get(count_name) not in (None, "")
                ]
                if values:
                    summary[count_name] = statistics.mean(values)
            for metric in metric_names:
                values = [float(row.get(metric, 0.0)) for row in rows]
                summary[metric] = statistics.mean(values) if values else 0.0
                summary[f"{metric}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
            fragmentation_values = [
                float(row.get("fragmentation_rate") or 0.0)
                for row in rows
            ]
            summary["fragmentation_rate"] = statistics.mean(fragmentation_values)
            summary["fragmentation_rate_std"] = (
                statistics.stdev(fragmentation_values)
                if len(fragmentation_values) > 1
                else 0.0
            )
            summary["fragmentation_rate_num_valid_runs"] = len(fragmentation_values)
            summary["fragmentation_rate_num_na_runs"] = 0
            summary["fragmentation_status"] = "evaluated"

            length_counts_by_run: list[dict[str, float]] = []
            for row in rows:
                raw_distribution = row.get("sequence_length_distribution_json")
                if not raw_distribution:
                    continue
                parsed = json.loads(str(raw_distribution))
                length_counts_by_run.append(
                    {str(key): float(value) for key, value in parsed.items()}
                )
            if length_counts_by_run:
                all_lengths = sorted(
                    {length for counts in length_counts_by_run for length in counts},
                    key=int,
                )
                mean_distribution = {
                    length: statistics.mean(
                        counts.get(length, 0.0) for counts in length_counts_by_run
                    )
                    for length in all_lengths
                }
                summary["sequence_length_distribution_json"] = json.dumps(
                    mean_distribution,
                    ensure_ascii=False,
                    sort_keys=True,
                )
        summary_rows.append(summary)
        summary_by_method[method] = summary

    return sorted(summary_rows, key=lambda row: row["method"]), summary_by_method


def evaluate_one_run(
    args: argparse.Namespace,
    *,
    run: int,
    proposed_path: Path,
    include_static_baselines: bool,
    train_state_intervals,
    test_state_intervals,
    train_labels,
    test_labels,
    train_period,
    state_low_information_map: dict[str, bool],
) -> dict:
    patterns_by_method = {}
    skipped_methods = []
    notes = []
    method_paths = method_paths_from_args(args, proposed_path)
    method_order = list(BASE_METHOD_ORDER) if include_static_baselines else ["proposed"]
    if include_static_baselines and not args.no_auto_generate_baselines:
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

    methods_to_load = BASE_METHOD_ORDER if include_static_baselines else ["proposed"]
    for method in methods_to_load:
        patterns, method_notes = load_method_patterns(method_paths[method], method)
        notes.extend(method_notes)
        if not patterns:
            skipped_methods.append({"run": run, "method": method, "reason": "; ".join(method_notes) or "no valid patterns"})
            print(f"[WARN] run={run} skipped {method}: {skipped_methods[-1]['reason']}", file=sys.stderr)
            continue
        patterns_by_method[method] = patterns
        print(f"run={run} {method}: patterns={len(patterns)}")

    if include_static_baselines and args.enable_fp_growth_baseline:
        try:
            fp_patterns_by_method, fp_notes = load_or_build_fp_growth_baselines(
                args,
                train_state_intervals,
                train_period,
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
                    skipped_methods.append({"run": run, "method": method, "reason": reason})
                    print(f"[WARN] run={run} skipped {method}: {reason}", file=sys.stderr)
                    continue
                patterns_by_method[method] = patterns
                print(f"run={run} {method}: patterns={len(patterns)}")
        except Exception as exc:
            for method in FP_GROWTH_METHODS:
                skipped_methods.append({"run": run, "method": method, "reason": f"FP-Growth baseline generation failed: {exc}"})
                print(f"[WARN] run={run} skipped {method}: {skipped_methods[-1]['reason']}", file=sys.stderr)

    if include_static_baselines and args.enable_transition_baseline:
        try:
            transition_patterns, transition_notes = load_or_build_transition_baseline(
                args,
                train_state_intervals,
                train_period,
            )
            notes.extend(transition_notes)
            for note in transition_notes:
                print(note)
            insertion_index = method_order.index("proposed") if "proposed" in method_order else len(method_order)
            if TRANSITION_METHOD not in method_order:
                method_order.insert(insertion_index, TRANSITION_METHOD)
            if transition_patterns:
                patterns_by_method[TRANSITION_METHOD] = transition_patterns
                print(f"run={run} {TRANSITION_METHOD}: patterns={len(transition_patterns)}")
            else:
                reason = "no valid transition_probability patterns after transition settings"
                skipped_methods.append({"run": run, "method": TRANSITION_METHOD, "reason": reason})
                print(f"[WARN] run={run} skipped {TRANSITION_METHOD}: {reason}", file=sys.stderr)
        except Exception as exc:
            skipped_methods.append(
                {"run": run, "method": TRANSITION_METHOD, "reason": f"transition_probability baseline generation failed: {exc}"}
            )
            print(f"[WARN] run={run} skipped transition_probability: {skipped_methods[-1]['reason']}", file=sys.stderr)

    patterns_by_method = {
        method: patterns_by_method[method]
        for method in method_order
        if method in patterns_by_method
    }

    if not patterns_by_method:
        raise RuntimeError(f"No valid pattern files were loaded for run={run}.")

    validate_state_attribute_coverage(
        [
            state_id
            for patterns in patterns_by_method.values()
            for pattern in patterns
            for state_id in pattern.sequence
        ],
        state_low_information_map,
        other_state_labels=set(args.other_state_labels),
    )

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
            f"run={run} {method}: train_occurrences={len(train_occurrences_by_method.get(method, []))} "
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
        fragmentation_containment_threshold=args.fragmentation_containment_threshold,
        low_information_threshold=args.low_information_threshold,
        state_low_information_map=state_low_information_map,
    )
    detail_rows = [{"run": run, **row} for row in detail_rows]
    summary_rows = [{"run": run, **row} for row in summary_rows]

    return {
        "run": run,
        "method_paths": method_paths,
        "patterns_by_method": patterns_by_method,
        "train_occurrences_by_method": train_occurrences_by_method,
        "test_occurrences_by_method": test_occurrences_by_method,
        "detail_rows": detail_rows,
        "summary_rows": summary_rows,
        "summary_by_method": summary_by_method,
        "skipped_methods": skipped_methods,
        "notes": notes,
    }


def main() -> None:
    args = parse_args()
    if args.runs < 1:
        raise ValueError("--runs must be >= 1")
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
    state_low_information_map = load_state_low_information_map(
        state_definition_path=args.state_definition,
        state_network_json_path=args.state_network_json,
        other_state_labels=set(args.other_state_labels),
    )
    validate_state_attribute_coverage(
        [interval.state_id for interval in state_intervals],
        state_low_information_map,
        other_state_labels=set(args.other_state_labels),
    )
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

    run_results = []
    detail_rows = []
    summary_rows_by_run = []
    skipped_methods = []
    skipped_runs = []
    notes = []
    pattern_paths_by_run = {}

    for run in range(1, args.runs + 1):
        proposed_path = path_for_run(args.patterns_proposed, run, args.patterns_proposed_template)
        if not proposed_path.exists():
            skipped = {
                "run": run,
                "path": str(proposed_path),
                "reason": "proposed pattern file does not exist",
            }
            if args.skip_missing_runs:
                skipped_runs.append(skipped)
                print(f"[WARN] skipped run={run}: {skipped['reason']}: {proposed_path}", file=sys.stderr)
                continue
            raise FileNotFoundError(f"run={run} proposed pattern file does not exist: {proposed_path}")

        print(f"=== Evaluation 5 run {run}/{args.runs}: {proposed_path} ===")
        include_static_baselines = not run_results
        run_result = evaluate_one_run(
            args,
            run=run,
            proposed_path=proposed_path,
            include_static_baselines=include_static_baselines,
            train_state_intervals=train_state_intervals,
            test_state_intervals=test_state_intervals,
            train_labels=train_labels,
            test_labels=test_labels,
            train_period=train_period,
            state_low_information_map=state_low_information_map,
        )
        run_results.append(run_result)
        output_detail_rows = run_result["detail_rows"]
        if args.runs == 1 and not args.skip_missing_runs:
            output_detail_rows = [
                {key: value for key, value in row.items() if key != "run"}
                for row in output_detail_rows
            ]
        detail_rows.extend(output_detail_rows)
        summary_rows_by_run.extend(run_result["summary_rows"])
        skipped_methods.extend(run_result["skipped_methods"])
        notes.extend(run_result["notes"])
        pattern_paths_by_run[str(run)] = {
            method: str(path) for method, path in run_result["method_paths"].items()
        }

    if not run_results:
        raise RuntimeError("No Evaluation 5 runs were evaluated.")

    summary_rows, summary_by_method = aggregate_run_summaries(summary_rows_by_run)
    first_result = run_results[0]
    patterns_by_method = first_result["patterns_by_method"]
    train_occurrences_by_method = first_result["train_occurrences_by_method"]
    test_occurrences_by_method = first_result["test_occurrences_by_method"]
    method_paths = method_paths_from_args(args)

    summary = {
        "rq": "Can the proposed method extract useful non-redundant ADL-grounded patterns and reduce fragmented subsequences?",
        "labeled_casas_path": str(args.labeled_casas),
        "state_series_path": str(args.state_series),
        "state_attributes": {
            "source_type": (
                "state_definition"
                if args.state_definition is not None
                else "state_network_json"
            ),
            "path": str(args.state_definition or args.state_network_json),
            "num_resolved_states": len(state_low_information_map),
            "low_information_state_ids": sorted(
                state_id
                for state_id, is_low_information in state_low_information_map.items()
                if is_low_information
            ),
            "unresolved_state_policy": "error",
        },
        "pattern_paths": {method: str(path) for method, path in method_paths.items()},
        "pattern_paths_by_run": pattern_paths_by_run,
        "methods": list(patterns_by_method),
        "skipped_methods": skipped_methods,
        "runs_requested": args.runs,
        "runs_completed": [result["run"] for result in run_results],
        "skip_missing_runs": args.skip_missing_runs,
        "skipped_runs": skipped_runs,
        "baseline_run_policy": {
            "static_baseline_methods": STATIC_BASE_METHODS
            + (FP_GROWTH_METHODS if args.enable_fp_growth_baseline else [])
            + ([TRANSITION_METHOD] if args.enable_transition_baseline else []),
            "description": (
                "Run-independent baselines are generated/evaluated only on the first completed run. "
                "Additional runs evaluate proposed patterns only; summary num_runs shows this difference."
            ),
            "use_baseline_cache": args.use_baseline_cache,
            "baseline_cache_dir": str(args.baseline_cache_dir),
            "cache_scope": (
                "FP-Growth and transition_probability generated pattern CSVs are keyed by state_series "
                "file signature, train period, and baseline CLI settings."
            ),
        },
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
            "transition_top_k": args.transition_top_k,
            "transition_min_prob": args.transition_min_prob,
            "transition_min_len": args.transition_min_len,
            "transition_max_len": args.transition_max_len,
            "fragmentation_containment_threshold": args.fragmentation_containment_threshold,
            "low_information_threshold": args.low_information_threshold,
        },
        "deprecated_ignored_thresholds": {
            "assigned_adl_relative_threshold": args.assigned_adl_relative_threshold,
            "assigned_adl_min_purity": args.assigned_adl_min_purity,
        },
        "primary_metrics": {
            "useful_non_redundant_pattern_rate": (
                "useful non-redundant patterns / evaluable patterns. A pattern is useful non-redundant "
                "when it is ADL-grounded and neither contextless useless nor fragmented."
            ),
            "fragmentation_rate": (
                "num fragmented patterns / num_evaluable_patterns, including zero "
                "when no comparable child-parent pair exists"
            ),
            "contextless_useless_rate": "num contextless useless patterns / num_evaluable_patterns",
        },
        "contextless_useless_definition": {
            "structural_useless": [
                "contains A -> A",
                "contains A -> Other -> A",
                "contains A -> B -> A -> B",
            ],
            "low_information": (
                "ratio of Other/unknown/その他/no-active-sensors states in sequence > "
                f"{args.low_information_threshold:g}"
            ),
            "adl_unsupported": (
                f"any_adl_hit_rate_test < {args.useless_hit_threshold:g} and "
                f"any_adl_purity_test < {args.useless_purity_threshold:g}"
            ),
        },
        "fragmentation_definition": {
            "containment_threshold": args.fragmentation_containment_threshold,
            "occurrence_containment": (
                "number of p occurrences contained in q occurrence intervals / number of p occurrences"
            ),
            "time_band_policy": (
                "sequence x time_band records are occurrence-matched and fragmentation-checked "
                "within the same time band; both occurrence start and end-epsilon must belong "
                "to the requested band"
            ),
            "comparable_pair": (
                "unique ordered child-parent pattern-ID pair in the same method/run/time_band "
                "where child is a proper contiguous subsequence of parent"
            ),
            "zero_pair_policy": (
                "fragmentation_rate is zero because num_fragmented is zero and the denominator "
                "remains num_evaluable_patterns; comparable pair and child counts remain "
                "diagnostic and zero pairs must not be interpreted as demonstrated suppression"
            ),
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
        "transition_probability_baseline": {
            "enabled": args.enable_transition_baseline,
            "source": "train state-series transitions",
            "top_k": args.transition_top_k,
            "min_prob": args.transition_min_prob,
            "min_len": args.transition_min_len,
            "max_len": args.transition_max_len,
            "ranking": "joint transition probability descending, then minimum step probability, length, sequence",
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
        "summary_by_method_by_run": summary_rows_by_run,
        "patterns_by_method_by_run": {
            str(result["run"]): {
                method: len(patterns) for method, patterns in result["patterns_by_method"].items()
            }
            for result in run_results
        },
        "train_occurrences_by_method_by_run": {
            str(result["run"]): {
                method: len(occurrences)
                for method, occurrences in result["train_occurrences_by_method"].items()
            }
            for result in run_results
        },
        "test_occurrences_by_method_by_run": {
            str(result["run"]): {
                method: len(occurrences)
                for method, occurrences in result["test_occurrences_by_method"].items()
            }
            for result in run_results
        },
        "notes": notes,
    }

    write_pattern_groundedness_outputs(
        output_dir=args.output_dir,
        pattern_detail_rows=detail_rows,
        summary_rows=summary_rows,
        summary_by_run_rows=summary_rows_by_run if args.runs > 1 or skipped_runs else None,
        summary=summary,
    )

    print(f"Evaluation 5 pattern-level outputs saved to: {args.output_dir}")
    if skipped_methods:
        skipped_names = ", ".join(f"run={item.get('run')}:{item['method']}" for item in skipped_methods)
        print(f"Skipped methods: {skipped_names}")
    if skipped_runs:
        skipped_names = ", ".join(str(item["run"]) for item in skipped_runs)
        print(f"Skipped runs: {skipped_names}")


if __name__ == "__main__":
    main()
