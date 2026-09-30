#!/usr/bin/env python3
"""Score Evaluation 6 Strict Ablation artifacts using only paired completed runs."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from experiment_config import DATASET_NAME, current_model_output_root, current_model_results_root
from src.behavior_pattern_mining.evaluation.adl import (
    load_state_series_csv,
    parse_labeled_casas_intervals,
)
from src.behavior_pattern_mining.evaluation.adl_interpretation_set import load_adl_intervals_csv
from src.behavior_pattern_mining.evaluation.period_splits import clip_intervals, resolve_split
from src.behavior_pattern_mining.evaluation.strict_ablation import (
    ABLATION_FACTOR,
    COMPARISON_TYPE,
    completed_run_ids,
    load_strict_condition,
    selection_manifest_provenance,
    strict_ablation_paths,
)


def _load_full_scorer():
    path = ROOT_DIR / "scripts" / "evaluate_6_compare_adl_interpretation_set.py"
    spec = importlib.util.spec_from_file_location("evaluation6_full_scorer", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--best-condition-manifest", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--n-states", type=int, default=None, help="Validation-only override; must match the manifest.")
    parser.add_argument("--hamming-threshold", type=int, default=None, help="Validation-only override; must match the manifest.")
    return parser.parse_args()


def _write_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    condition = load_strict_condition(args.best_condition_manifest)
    if args.runs < 1:
        raise ValueError("--runs must be >= 1")
    if args.n_states is not None and args.n_states != condition.n_states:
        raise ValueError("--n-states conflicts with --best-condition-manifest")
    if args.hamming_threshold is not None and args.hamming_threshold != condition.hamming_threshold:
        raise ValueError("--hamming-threshold conflicts with --best-condition-manifest")
    paths = strict_ablation_paths(
        project_root=ROOT_DIR, results_root=current_model_results_root(), output_root=current_model_output_root(),
        dataset=DATASET_NAME, condition=condition,
    )
    if not paths.state_series.exists():
        raise FileNotFoundError(f"state series is missing: {paths.state_series}")
    requested = list(range(1, args.runs + 1))
    proposed_successful = completed_run_ids(paths.proposed_dir, requested)
    llm_only_successful = completed_run_ids(paths.llm_only_dir, requested)
    common_runs = sorted(set(proposed_successful) & set(llm_only_successful))
    if not common_runs:
        raise RuntimeError("strict ablation has no common completed runs")

    scorer = _load_full_scorer()
    state_intervals = load_state_series_csv(paths.state_series)
    adl_path = current_model_output_root() / "adl_label_intervals.csv"
    adl_intervals = (
        load_adl_intervals_csv(adl_path)
        if adl_path.exists()
        else parse_labeled_casas_intervals(ROOT_DIR / "new_labeled_data" / f"{DATASET_NAME}.txt")
    )
    split = resolve_split(
        [*state_intervals, *adl_intervals], split_mode="holdout", generation_days=condition.generation_days,
        validation_start_day=condition.validation_start_day, validation_end_day=condition.validation_end_day,
        test_start_day=condition.test_start_day, test_end_day=condition.test_end_day,
    )
    start, end = split.scoring_period("test")
    scorer_args = argparse.Namespace(
        match_mode="exact", max_skip_duration_minutes=1.0, min_overlap_ratio_for_true_label=0.10,
        no_overlap_label="Ambiguous", missing_pred_label="Ambiguous", unknown_pred_label="Other",
    )
    run_rows: list[dict] = []
    paired_rows: list[dict] = []
    detail_rows: list[dict] = []
    for run_id in common_runs:
        per_method: dict[str, dict] = {}
        for method, directory in (("proposed_strict", paths.proposed_dir), ("llm_only_strict", paths.llm_only_dir)):
            detail, summary = scorer.evaluate_method(
                method=method, patterns_path=directory / f"run_{run_id}.json",
                state_intervals=clip_intervals(state_intervals, start, end),
                adl_intervals=clip_intervals(adl_intervals, start, end), args=scorer_args,
            )
            summary = {"run": run_id, **summary}
            run_rows.append(summary)
            detail_rows.extend([{"run": run_id, **row} for row in detail])
            per_method[method] = summary
        paired_rows.append({
            "run": run_id, "method": "paired_difference",
            "proposed_minus_llm_only_multilabel_f1": (
                per_method["proposed_strict"]["mean_multilabel_f1"]
                - per_method["llm_only_strict"]["mean_multilabel_f1"]
            ),
        })
    metric_rows = [row for row in run_rows if row["method"] != "paired_difference"]
    summary_rows = scorer.summarize_runs(metric_rows)
    output_dir = paths.root / "evaluation"
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_rows(output_dir / "evaluation6_strict_ablation_by_run.csv", metric_rows)
    _write_rows(output_dir / "evaluation6_strict_ablation_paired_f1.csv", paired_rows)
    _write_rows(output_dir / "evaluation6_strict_ablation_summary.csv", summary_rows)
    _write_rows(output_dir / "evaluation6_strict_ablation_details.csv", detail_rows)
    payload = {
        "comparison_type": COMPARISON_TYPE,
        "ablation_factor": ABLATION_FACTOR,
        "best_condition_manifest": str(args.best_condition_manifest),
        "selection_manifest": selection_manifest_provenance(args.best_condition_manifest),
        "requested_runs": requested,
        "successful_runs": {"proposed": proposed_successful, "llm_only": llm_only_successful},
        "common_completed_runs": common_runs,
        "generation_days": condition.generation_days,
        "validation_start_day": condition.validation_start_day,
        "validation_end_day": condition.validation_end_day,
        "test_start_day": condition.test_start_day,
        "test_end_day": condition.test_end_day,
        "n_states": condition.n_states,
        "hamming_threshold": condition.hamming_threshold,
        "sensor_representation": condition.sensor_representation,
        "state_series": str(paths.state_series),
        "methods": {row["method"]: row for row in summary_rows},
    }
    (output_dir / "evaluation6_strict_ablation_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Strict ablation evaluation saved to: {output_dir}")


if __name__ == "__main__":
    main()
