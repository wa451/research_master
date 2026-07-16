#!/usr/bin/env python3
"""Evaluation 7: proposed-method ADL interpretation sensitivity over K/hamming."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT_DIR_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(ROOT_DIR_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR_FOR_IMPORTS))

from experiment_config import DATASET_NAME, ROOT_DIR
from scripts.evaluate_6_compare_adl_interpretation_set import (
    DETAIL_FIELDNAMES as EVAL6_DETAIL_FIELDNAMES,
    evaluate_method,
    load_truth_intervals,
    path_for_run,
)
from src.behavior_pattern_mining.evaluation.adl import (
    load_state_series_csv,
    write_csv_rows,
)
from src.behavior_pattern_mining.evaluation.adl_interpretation_set import (
    ALLOWED_LABELS,
    aggregate_by_label,
    aggregate_by_time_band,
)
from src.behavior_pattern_mining.evaluation.evaluation7_staged import (
    condition_pairs_from_file,
)


DEFAULT_DAYS = 30

DETAIL_FIELDNAMES = [
    "condition_id",
    "n_states",
    "hamming_threshold",
    "days",
    "patterns_path",
    "state_series",
    *EVAL6_DETAIL_FIELDNAMES,
]

RUN_SUMMARY_FIELDNAMES = [
    "condition_id",
    "n_states",
    "hamming_threshold",
    "days",
    "run",
    "method",
    "patterns_path",
    "state_series",
    "num_patterns",
    "num_pattern_occurrences",
    "mean_accuracy",
    "mean_exact_set_match",
    "mean_jaccard",
    "mean_multilabel_precision",
    "mean_multilabel_recall",
    "mean_multilabel_f1",
]

CONDITION_SUMMARY_FIELDNAMES = [
    "rank",
    "condition_id",
    "n_states",
    "hamming_threshold",
    "days",
    "num_runs",
    "avg_num_patterns",
    "avg_num_pattern_occurrences",
    "mean_accuracy",
    "std_accuracy",
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
    "selection_metric",
    "selection_metric_value",
]

LABEL_FIELDNAMES = [
    "condition_id",
    "n_states",
    "hamming_threshold",
    "days",
    "method",
    "label",
    "num_patterns",
    "mean_jaccard",
    "mean_multilabel_precision",
    "mean_multilabel_recall",
    "mean_multilabel_f1",
]

TIME_BAND_FIELDNAMES = [
    "condition_id",
    "n_states",
    "hamming_threshold",
    "days",
    "method",
    "time_band",
    "num_patterns",
    "mean_accuracy",
    "mean_exact_set_match",
    "mean_jaccard",
    "mean_multilabel_precision",
    "mean_multilabel_recall",
    "mean_multilabel_f1",
]

SELECTION_METRICS = {
    "mean_multilabel_f1",
    "mean_jaccard",
    "mean_accuracy",
    "mean_exact_set_match",
    "mean_multilabel_precision",
    "mean_multilabel_recall",
}


def parse_int_list(raw_values: list[str]) -> list[int]:
    values: list[int] = []
    for raw_value in raw_values:
        for token in raw_value.replace(",", " ").split():
            values.append(int(token))
    if not values:
        raise argparse.ArgumentTypeError("at least one integer is required")
    return values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluation 7: proposed-method ADL label sensitivity over K and hamming"
    )
    parser.add_argument(
        "--n-states-list",
        nargs="+",
        default=["15"],
        help="Representative-state counts K. Accepts space or comma separated values, e.g. 10 15 20 or 10,15,20.",
    )
    parser.add_argument(
        "--hamming-thresholds",
        nargs="+",
        default=["1"],
        help="Hamming thresholds. Accepts space or comma separated values, e.g. 0 1 2 or 0,1,2.",
    )
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    run_group = parser.add_mutually_exclusive_group()
    run_group.add_argument("--runs", type=int, default=1)
    run_group.add_argument(
        "--run-ids",
        nargs="+",
        default=None,
        help="Explicit run IDs to evaluate, e.g. 2 3 4. Cannot be combined with --runs.",
    )
    parser.add_argument("--dataset", default=DATASET_NAME)
    parser.add_argument(
        "--conditions-file",
        type=Path,
        default=None,
        help=(
            "Optional CSV containing n_states and hamming_threshold columns. "
            "When set, these exact condition pairs replace the Cartesian parameter grid."
        ),
    )
    parser.add_argument(
        "--condition-summary-copy",
        type=Path,
        default=None,
        help=(
            "Optional path that receives the same rows and columns as "
            "evaluation7_condition_summary.csv."
        ),
    )
    parser.add_argument(
        "--patterns-template",
        default=None,
        help=(
            "Optional proposed-pattern path template. Available fields: "
            "{dataset}, {n_states}, {hamming_threshold}, {hamming}, {days}, {run}, {suffix}."
        ),
    )
    parser.add_argument(
        "--state-series-template",
        default=None,
        help=(
            "Optional state-series path template. Available fields: "
            "{dataset}, {n_states}, {hamming_threshold}, {hamming}, {days}, {suffix}."
        ),
    )
    parser.add_argument(
        "--adl-intervals",
        type=Path,
        default=ROOT_DIR / "output" / "adl_label_intervals.csv",
        help="ADL truth interval CSV. Used only when --labeled-casas is absent or missing.",
    )
    parser.add_argument(
        "--labeled-casas",
        type=Path,
        default=ROOT_DIR / "new_labeled_data" / f"{DATASET_NAME}.txt",
        help="CASAS labeled text file used to build ADL truth intervals.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT_DIR / "results" / "7_param_search",
    )
    parser.add_argument("--min-overlap-ratio-for-true-label", type=float, default=0.10)
    parser.add_argument("--no-overlap-label", choices=["Other", "Ambiguous"], default="Ambiguous")
    parser.add_argument("--missing-pred-label", choices=["Other", "Ambiguous"], default="Ambiguous")
    parser.add_argument("--unknown-pred-label", choices=["Other", "Ambiguous"], default="Other")
    parser.add_argument("--wake-window-minutes", type=float, default=30.0)
    parser.add_argument("--match-mode", choices=["exact", "skip-other"], default="exact")
    parser.add_argument("--max-skip-duration-minutes", type=float, default=1.0)
    parser.add_argument(
        "--selection-metric",
        choices=sorted(SELECTION_METRICS),
        default="mean_multilabel_f1",
        help="Metric used to choose the best condition.",
    )
    parser.add_argument(
        "--skip-missing-runs",
        action="store_true",
        help="Skip missing run pattern files instead of stopping.",
    )
    parser.add_argument(
        "--skip-missing-conditions",
        action="store_true",
        help="Skip conditions whose state-series or all pattern files are missing.",
    )
    args = parser.parse_args()
    args.n_states_list = parse_int_list(args.n_states_list)
    args.hamming_thresholds = parse_int_list(args.hamming_thresholds)
    args.run_ids = parse_int_list(args.run_ids) if args.run_ids else None
    return args


def condition_id(n_states: int, hamming_threshold: int, days: int) -> str:
    return f"{n_states}_{hamming_threshold}_{days}days"


def template_context(
    dataset: str,
    n_states: int,
    hamming_threshold: int,
    days: int,
    run: int | None = None,
) -> dict[str, Any]:
    suffix = condition_id(n_states, hamming_threshold, days)
    context: dict[str, Any] = {
        "dataset": dataset,
        "n_states": n_states,
        "hamming_threshold": hamming_threshold,
        "hamming": hamming_threshold,
        "days": days,
        "suffix": suffix,
    }
    if run is not None:
        context["run"] = run
    return context


def default_pattern_path(dataset: str, n_states: int, hamming_threshold: int, days: int) -> Path:
    suffix = condition_id(n_states, hamming_threshold, days)
    return ROOT_DIR / "output" / f"{dataset}_{suffix}" / f"llm_sequences_modes_{suffix}_1.json"


def default_state_series_path(n_states: int, hamming_threshold: int, days: int) -> Path:
    if n_states == 15 and hamming_threshold == 1 and days == 30:
        return ROOT_DIR / "output" / "6_adl_evaluation_30" / "state_series.csv"
    return ROOT_DIR / "output" / f"6_adl_evaluation_{condition_id(n_states, hamming_threshold, days)}" / "state_series.csv"


def resolve_pattern_path(args: argparse.Namespace, n_states: int, hamming_threshold: int, run: int) -> Path:
    if args.patterns_template:
        return Path(
            args.patterns_template.format(
                **template_context(args.dataset, n_states, hamming_threshold, args.days, run=run)
            )
        )
    return path_for_run(
        default_pattern_path(args.dataset, n_states, hamming_threshold, args.days),
        run,
        template=None,
    )


def resolve_state_series_path(args: argparse.Namespace, n_states: int, hamming_threshold: int) -> Path:
    if args.state_series_template:
        return Path(
            args.state_series_template.format(
                **template_context(args.dataset, n_states, hamming_threshold, args.days)
            )
        )
    return default_state_series_path(n_states, hamming_threshold, args.days)


def mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def std(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def condition_summary_from_runs(
    run_rows: list[dict],
    selection_metric: str,
) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in run_rows:
        grouped.setdefault(str(row["condition_id"]), []).append(row)

    summary_rows: list[dict] = []
    for cond_id, rows in grouped.items():
        first = rows[0]
        exact = [float(row["mean_exact_set_match"]) for row in rows]
        jaccard = [float(row["mean_jaccard"]) for row in rows]
        precision = [float(row["mean_multilabel_precision"]) for row in rows]
        recall = [float(row["mean_multilabel_recall"]) for row in rows]
        f1 = [float(row["mean_multilabel_f1"]) for row in rows]
        row = {
            "rank": "",
            "condition_id": cond_id,
            "n_states": int(first["n_states"]),
            "hamming_threshold": int(first["hamming_threshold"]),
            "days": int(first["days"]),
            "num_runs": len(rows),
            "avg_num_patterns": mean([float(row["num_patterns"]) for row in rows]),
            "avg_num_pattern_occurrences": mean([float(row["num_pattern_occurrences"]) for row in rows]),
            "mean_accuracy": mean(exact),
            "std_accuracy": std(exact),
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
            "selection_metric": selection_metric,
        }
        row["selection_metric_value"] = row[selection_metric]
        summary_rows.append(row)

    summary_rows.sort(
        key=lambda row: (
            -float(row["selection_metric_value"]),
            -float(row["mean_jaccard"]),
            -float(row["mean_accuracy"]),
            int(row["n_states"]),
            int(row["hamming_threshold"]),
        )
    )
    for rank, row in enumerate(summary_rows, start=1):
        row["rank"] = rank
    return summary_rows


def add_condition_to_rows(
    rows: list[dict],
    *,
    n_states: int,
    hamming_threshold: int,
    days: int,
    state_series_path: Path,
    patterns_path: Path,
) -> list[dict]:
    cond_id = condition_id(n_states, hamming_threshold, days)
    return [
        {
            "condition_id": cond_id,
            "n_states": n_states,
            "hamming_threshold": hamming_threshold,
            "days": days,
            "patterns_path": str(patterns_path),
            "state_series": str(state_series_path),
            **row,
        }
        for row in rows
    ]


def condition_label_rows(detail_rows: list[dict], label_column: str, label_name: str) -> list[dict]:
    output_rows: list[dict] = []
    grouped: dict[tuple[str, str, int, int, int], list[dict]] = {}
    for row in detail_rows:
        key = (
            str(row["condition_id"]),
            str(row.get("method") or "proposed"),
            int(row["n_states"]),
            int(row["hamming_threshold"]),
            int(row["days"]),
        )
        grouped.setdefault(key, []).append(row)

    for (cond_id, method, n_states, hamming_threshold, days), rows in sorted(grouped.items()):
        aggregates = aggregate_by_label(rows, label_column, label_name)
        for aggregate in aggregates:
            output_rows.append(
                {
                    "condition_id": cond_id,
                    "n_states": n_states,
                    "hamming_threshold": hamming_threshold,
                    "days": days,
                    "method": method,
                    "label": aggregate[label_name],
                    "num_patterns": aggregate["num_patterns"],
                    "mean_jaccard": aggregate["mean_jaccard"],
                    "mean_multilabel_precision": aggregate["mean_multilabel_precision"],
                    "mean_multilabel_recall": aggregate["mean_multilabel_recall"],
                    "mean_multilabel_f1": aggregate["mean_multilabel_f1"],
                }
            )
    return output_rows


def condition_time_band_rows(detail_rows: list[dict]) -> list[dict]:
    output_rows: list[dict] = []
    grouped: dict[tuple[str, str, int, int, int], list[dict]] = {}
    for row in detail_rows:
        key = (
            str(row["condition_id"]),
            str(row.get("method") or "proposed"),
            int(row["n_states"]),
            int(row["hamming_threshold"]),
            int(row["days"]),
        )
        grouped.setdefault(key, []).append(row)

    for (cond_id, method, n_states, hamming_threshold, days), rows in sorted(grouped.items()):
        for aggregate in aggregate_by_time_band(rows):
            output_rows.append(
                {
                    "condition_id": cond_id,
                    "n_states": n_states,
                    "hamming_threshold": hamming_threshold,
                    "days": days,
                    "method": method,
                    "time_band": aggregate["time_band"],
                    "num_patterns": aggregate["num_patterns"],
                    "mean_accuracy": aggregate["mean_exact_set_match"],
                    "mean_exact_set_match": aggregate["mean_exact_set_match"],
                    "mean_jaccard": aggregate["mean_jaccard"],
                    "mean_multilabel_precision": aggregate["mean_multilabel_precision"],
                    "mean_multilabel_recall": aggregate["mean_multilabel_recall"],
                    "mean_multilabel_f1": aggregate["mean_multilabel_f1"],
                }
            )
    return output_rows


def evaluate_conditions(args: argparse.Namespace) -> dict[str, Any]:
    run_ids = args.run_ids or list(range(1, args.runs + 1))
    if not run_ids or any(run < 1 for run in run_ids):
        raise ValueError("requested run IDs must all be >= 1")
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("requested run IDs must be unique")

    if args.conditions_file:
        condition_pairs = condition_pairs_from_file(
            args.conditions_file,
            expected_days=args.days,
        )
    else:
        condition_pairs = [
            (n_states, hamming_threshold)
            for n_states in args.n_states_list
            for hamming_threshold in args.hamming_thresholds
        ]

    adl_intervals, adl_source = load_truth_intervals(args)
    all_detail_rows: list[dict] = []
    run_summary_rows: list[dict] = []
    skipped_conditions: list[dict] = []
    skipped_runs: list[dict] = []

    for n_states, hamming_threshold in condition_pairs:
        cond_id = condition_id(n_states, hamming_threshold, args.days)
        state_series_path = resolve_state_series_path(args, n_states, hamming_threshold)
        if not state_series_path.exists():
            skipped = {
                "condition_id": cond_id,
                "n_states": n_states,
                "hamming_threshold": hamming_threshold,
                "days": args.days,
                "state_series": str(state_series_path),
                "reason": "state_series_missing",
            }
            if args.skip_missing_conditions:
                skipped_conditions.append(skipped)
                continue
            raise FileNotFoundError(
                f"state-series does not exist for condition {cond_id}: {state_series_path}. "
                "Use --skip-missing-conditions to skip missing conditions."
            )

        state_intervals = load_state_series_csv(state_series_path)
        pattern_paths = [
            (run, resolve_pattern_path(args, n_states, hamming_threshold, run))
            for run in run_ids
        ]
        missing_pattern_paths = [
            (run, path) for run, path in pattern_paths
            if not path.exists()
        ]
        if missing_pattern_paths and not args.skip_missing_runs:
            run, path = missing_pattern_paths[0]
            skipped = {
                "condition_id": cond_id,
                "n_states": n_states,
                "hamming_threshold": hamming_threshold,
                "days": args.days,
                "run": run,
                "patterns_path": str(path),
                "reason": "condition_pattern_file_missing",
            }
            if args.skip_missing_conditions:
                skipped_conditions.append(skipped)
                continue
            raise FileNotFoundError(
                f"pattern file does not exist for condition {cond_id} run {run}: {path}. "
                "Use --skip-missing-runs or --skip-missing-conditions to skip missing files."
            )

        condition_had_run = False
        for run, patterns_path in pattern_paths:
            if not patterns_path.exists():
                skipped = {
                    "condition_id": cond_id,
                    "n_states": n_states,
                    "hamming_threshold": hamming_threshold,
                    "days": args.days,
                    "run": run,
                    "patterns_path": str(patterns_path),
                    "reason": "pattern_file_missing",
                }
                if args.skip_missing_runs:
                    skipped_runs.append(skipped)
                    continue
                raise FileNotFoundError(
                    f"pattern file does not exist for condition {cond_id} run {run}: {patterns_path}. "
                    "Use --skip-missing-runs or --skip-missing-conditions to skip missing files."
                )

            detail_rows, summary_metrics = evaluate_method(
                method="proposed",
                patterns_path=patterns_path,
                state_intervals=state_intervals,
                adl_intervals=adl_intervals,
                args=args,
            )
            condition_had_run = True
            detail_rows = [{"run": run, **row} for row in detail_rows]
            all_detail_rows.extend(
                add_condition_to_rows(
                    detail_rows,
                    n_states=n_states,
                    hamming_threshold=hamming_threshold,
                    days=args.days,
                    state_series_path=state_series_path,
                    patterns_path=patterns_path,
                )
            )
            run_summary = {
                "condition_id": cond_id,
                "n_states": n_states,
                "hamming_threshold": hamming_threshold,
                "days": args.days,
                "run": run,
                "patterns_path": str(patterns_path),
                "state_series": str(state_series_path),
                **summary_metrics,
            }
            run_summary["mean_accuracy"] = run_summary["mean_exact_set_match"]
            run_summary_rows.append(run_summary)

        if not condition_had_run and args.skip_missing_conditions:
            already_recorded = any(item["condition_id"] == cond_id for item in skipped_conditions)
            if not already_recorded:
                skipped_conditions.append(
                    {
                        "condition_id": cond_id,
                        "n_states": n_states,
                        "hamming_threshold": hamming_threshold,
                        "days": args.days,
                        "reason": "no_valid_runs",
                    }
                )

    if not run_summary_rows:
        skipped_preview = [*skipped_conditions, *skipped_runs][:10]
        details = "\n".join(
            f"- {item.get('condition_id', '')}: {item.get('reason', '')} "
            f"state_series={item.get('state_series', '')} "
            f"patterns_path={item.get('patterns_path', '')}"
            for item in skipped_preview
        )
        raise RuntimeError(
            "No valid Evaluation 7 conditions were evaluated. "
            "All requested K/hamming conditions were missing required inputs. "
            "Generate condition-specific proposed JSON and state_series.csv first, "
            "or include an existing condition such as hamming=1.\n"
            f"Skipped conditions/runs shown up to 10:\n{details}"
        )

    condition_summary_rows = condition_summary_from_runs(run_summary_rows, args.selection_metric)
    best_condition = condition_summary_rows[0] if condition_summary_rows else None
    pred_label_rows = condition_label_rows(all_detail_rows, "pred_adl_labels", "pred_label")
    true_label_rows = condition_label_rows(all_detail_rows, "true_adl_labels", "true_label")
    time_band_rows = condition_time_band_rows(all_detail_rows)

    return {
        "adl_source": adl_source,
        "condition_pairs": condition_pairs,
        "detail_rows": all_detail_rows,
        "run_summary_rows": run_summary_rows,
        "condition_summary_rows": condition_summary_rows,
        "pred_label_rows": pred_label_rows,
        "true_label_rows": true_label_rows,
        "time_band_rows": time_band_rows,
        "best_condition": best_condition,
        "skipped_conditions": skipped_conditions,
        "skipped_runs": skipped_runs,
    }


def write_outputs(args: argparse.Namespace, result: dict[str, Any]) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_rows(
        args.output_dir / "evaluation7_condition_summary.csv",
        result["condition_summary_rows"],
        CONDITION_SUMMARY_FIELDNAMES,
    )
    if args.condition_summary_copy is not None:
        write_csv_rows(
            args.condition_summary_copy,
            result["condition_summary_rows"],
            CONDITION_SUMMARY_FIELDNAMES,
        )
    write_csv_rows(
        args.output_dir / "evaluation7_condition_summary_by_run.csv",
        result["run_summary_rows"],
        RUN_SUMMARY_FIELDNAMES,
    )
    write_csv_rows(
        args.output_dir / "evaluation7_pattern_set_details.csv",
        result["detail_rows"],
        DETAIL_FIELDNAMES,
    )
    write_csv_rows(
        args.output_dir / "evaluation7_by_pred_label.csv",
        result["pred_label_rows"],
        LABEL_FIELDNAMES,
    )
    write_csv_rows(
        args.output_dir / "evaluation7_by_true_label.csv",
        result["true_label_rows"],
        LABEL_FIELDNAMES,
    )
    write_csv_rows(
        args.output_dir / "evaluation7_by_time_band.csv",
        result["time_band_rows"],
        TIME_BAND_FIELDNAMES,
    )

    summary_payload = {
        "evaluation": 7,
        "evaluation_type": "proposed_parameter_sensitivity_adl_interpretation_set",
        "order_sensitive": False,
        "time_band_aware": True,
        "dataset": args.dataset,
        "days": args.days,
        "n_states_list": sorted({pair[0] for pair in result["condition_pairs"]}),
        "hamming_thresholds": sorted({pair[1] for pair in result["condition_pairs"]}),
        "condition_pairs": [
            {"n_states": n_states, "hamming_threshold": hamming_threshold}
            for n_states, hamming_threshold in result["condition_pairs"]
        ],
        "runs_requested": len(args.run_ids) if args.run_ids else args.runs,
        "run_ids_requested": args.run_ids or list(range(1, args.runs + 1)),
        "conditions_file": str(args.conditions_file) if args.conditions_file else None,
        "condition_summary_copy": (
            str(args.condition_summary_copy) if args.condition_summary_copy else None
        ),
        "patterns_template": args.patterns_template,
        "state_series_template": args.state_series_template,
        "adl_intervals": result["adl_source"],
        "output_dir": str(args.output_dir),
        "allowed_labels": ALLOWED_LABELS,
        "min_overlap_ratio_for_true_label": args.min_overlap_ratio_for_true_label,
        "no_overlap_label": args.no_overlap_label,
        "missing_pred_label": args.missing_pred_label,
        "unknown_pred_label": args.unknown_pred_label,
        "match_mode": args.match_mode,
        "max_skip_duration_minutes": args.max_skip_duration_minutes,
        "selection_metric": args.selection_metric,
        "best_condition": result["best_condition"],
        "conditions": result["condition_summary_rows"],
        "skipped_conditions": result["skipped_conditions"],
        "skipped_runs": result["skipped_runs"],
        "output_files": {
            "condition_summary": "evaluation7_condition_summary.csv",
            "condition_summary_by_run": "evaluation7_condition_summary_by_run.csv",
            "pattern_details": "evaluation7_pattern_set_details.csv",
            "by_pred_label": "evaluation7_by_pred_label.csv",
            "by_true_label": "evaluation7_by_true_label.csv",
            "by_time_band": "evaluation7_by_time_band.csv",
            "summary": "evaluation7_summary.json",
        },
    }
    (args.output_dir / "evaluation7_summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    result = evaluate_conditions(args)
    write_outputs(args, result)

    print(f"Evaluation 7 outputs saved to: {args.output_dir}")
    if result["best_condition"]:
        best = result["best_condition"]
        print(
            "Best condition: "
            f"K={best['n_states']}, hamming={best['hamming_threshold']}, "
            f"{args.selection_metric}={float(best['selection_metric_value']):.6f}"
        )
    for row in result["condition_summary_rows"]:
        print(
            f"{row['condition_id']}: runs={row['num_runs']}, "
            f"accuracy={float(row['mean_accuracy']):.6f}, "
            f"jaccard={float(row['mean_jaccard']):.6f}, "
            f"f1={float(row['mean_multilabel_f1']):.6f}"
        )
    if result["skipped_conditions"]:
        print(f"Skipped conditions: {len(result['skipped_conditions'])}")
    if result["skipped_runs"]:
        print(f"Skipped runs: {len(result['skipped_runs'])}")


if __name__ == "__main__":
    main()
