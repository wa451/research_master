#!/usr/bin/env python3
"""Create reviewer-response tables, figures, and blind human-evaluation data.

This is intentionally a scorer/aggregator only.  It has no LLM client and
requires a new output directory, protecting both legacy and source artifacts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.behavior_pattern_mining.evaluation.reviewer_response import (
    extract_human_pattern, format_mean_sd, load_state_context, make_blind_sample,
    mean_sd, read_csv, reviewer_eval5_rows, strict_common_run_rows, write_csv,
)


MODEL_ROOT = ROOT / "results" / "gpt-5.6-sol"


def require(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"required existing artifact is missing: {path}")
    return path


def table_markdown(rows: list[dict], columns: list[str]) -> str:
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines) + "\n"


def save_figure(path: Path, dataframe: pd.DataFrame, *, x: str, y: str, hue: str | None, title: str) -> None:
    figure, axis = plt.subplots(figsize=(7, 4.5))
    if hue:
        for name, group in dataframe.groupby(hue, dropna=False):
            axis.plot(group[x], group[y], marker="o", label=str(name))
        axis.legend(title=hue)
    else:
        axis.bar(dataframe[x].astype(str), dataframe[y])
    axis.set_title(title)
    axis.set_xlabel(x)
    axis.set_ylabel(y)
    axis.set_ylim(bottom=0)
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--human-sample-size", type=int, default=80)
    parser.add_argument("--random-seed", type=int, default=20260929)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite reviewer-response output: {output}")
    output.mkdir(parents=True, exist_ok=False)
    tables, figures, human = (output / name for name in ("tables", "figures", "human_evaluation"))
    for directory in (tables, figures, human):
        directory.mkdir()

    sources: dict[str, str] = {}
    statuses: dict[str, dict[str, str]] = {}

    # Eval 5: only change reviewer interpretation of no-comparable-pair runs.
    e5_details = require(MODEL_ROOT / "5_pattern_quality_individual_fixed/evaluation5_pattern_details.csv")
    e5_rows = reviewer_eval5_rows(read_csv(e5_details))
    write_csv(output / "evaluation5_reviewer_by_run.csv", e5_rows)
    e5_summary = []
    for method in sorted({row["method"] for row in e5_rows}):
        rows = [row for row in e5_rows if row["method"] == method]
        mean, sd = mean_sd([row["fragmentation_rate"] for row in rows])
        support_mean, support_sd = mean_sd([row["test_supported_rate"] for row in rows])
        redundancy_mean, redundancy_sd = mean_sd([row["redundancy_rate"] for row in rows])
        pattern_mean, pattern_sd = mean_sd([float(row["pattern_count"]) for row in rows])
        e5_summary.append({"method": method, "runs": len(rows), "pattern_count": format_mean_sd(pattern_mean, pattern_sd), "test_supported_rate": format_mean_sd(support_mean, support_sd), "redundancy_rate": format_mean_sd(redundancy_mean, redundancy_sd), "fragmentation": format_mean_sd(mean, sd), "n_a_runs": sum(row["fragmentation_status"] == "N/A" for row in rows)})
    write_csv(tables / "table_eval5_pattern_quality.csv", e5_summary)
    sources["eval5"] = str(e5_details)
    statuses["eval5"] = {"status": "COMPLETE", "note": "reviewer fragmentation policy applied without regenerating patterns"}

    # Eval 6 full.
    e6_full = require(MODEL_ROOT / "6_adl_match_individual_holdout_test_direct_time_split/evaluation6_method_comparison.csv")
    full_rows = []
    for row in read_csv(e6_full):
        full_rows.append({"method": row["method"], "precision": format_mean_sd(float(row["mean_multilabel_precision"]), float(row["std_multilabel_precision"])), "recall": format_mean_sd(float(row["mean_multilabel_recall"]), float(row["std_multilabel_recall"])), "f1": format_mean_sd(float(row["mean_multilabel_f1"]), float(row["std_multilabel_f1"])), "jaccard": format_mean_sd(float(row["mean_jaccard"]), float(row["std_jaccard"])), "exact": format_mean_sd(float(row["mean_exact_set_match"]), float(row["std_exact_set_match"])), "runs": row["num_runs"]})
    write_csv(tables / "table_eval6_full_pipeline.csv", full_rows)
    sources["eval6_full"] = str(e6_full)
    statuses["eval6_full"] = {"status": "COMPLETE", "note": "existing Day155-220 holdout summary"}

    # Eval 6 strict: paired only; no CI from five run means.
    e6_strict = require(MODEL_ROOT / "6_strict_ablation/aruba_individual_10_2_14days_holdout_test/evaluation/evaluation6_strict_ablation_by_run.csv")
    strict_rows = strict_common_run_rows(read_csv(e6_strict))
    if not strict_rows:
        raise ValueError("strict ablation has no common completed runs")
    write_csv(output / "evaluation6_strict_paired_by_run.csv", strict_rows)
    strict_summary = []
    for method in ("proposed", "llm_only"):
        entry = {"method": method, "common_runs": len(strict_rows)}
        for metric in ("precision", "recall", "f1", "jaccard", "exact"):
            entry[metric] = format_mean_sd(*mean_sd([row[f"{method}_{metric}"] for row in strict_rows]))
        strict_summary.append(entry)
    delta_mean, delta_sd = mean_sd([row["delta_f1"] for row in strict_rows])
    for row in strict_summary:
        row["paired_delta_f1"] = format_mean_sd(delta_mean, delta_sd) if row["method"] == "proposed" else ""
        row["paired_ci"] = "N/A: only five run-level aggregates; no episode-level resampling unit available"
    write_csv(tables / "table_eval6_strict_ablation.csv", strict_summary)
    sources["eval6_strict"] = str(e6_strict)
    statuses["eval6_strict"] = {"status": "COMPLETE", "note": f"common completed runs: {[row['run'] for row in strict_rows]}"}

    # Eval 7 requires validation only and exact best-condition manifest.
    e7_csv = require(MODEL_ROOT / "7_param_search_14d_5runs_individual_holdout/evaluation7_condition_summary.csv")
    e7_manifest = require(MODEL_ROOT / "7_param_search_14d_5runs_individual_holdout/evaluation7_best_condition_manifest.json")
    manifest = json.loads(e7_manifest.read_text(encoding="utf-8"))
    if manifest.get("evaluation_role") not in (None, "validation") and manifest.get("selection_role") not in (None, "validation"):
        raise ValueError("Eval7 best condition was not selected on validation")
    e7_rows = []
    for row in read_csv(e7_csv):
        e7_rows.append({"K": row.get("n_states"), "h": row.get("hamming_threshold"), "precision": format_mean_sd(float(row["mean_multilabel_precision"]), float(row["std_multilabel_precision"])), "recall": format_mean_sd(float(row["mean_multilabel_recall"]), float(row["std_multilabel_recall"])), "f1": format_mean_sd(float(row["mean_multilabel_f1"]), float(row["std_multilabel_f1"])), "jaccard": format_mean_sd(float(row["mean_jaccard"]), float(row["std_jaccard"])), "runs": row["num_runs"]})
    write_csv(tables / "table_eval7_sensitivity.csv", e7_rows)
    e7_frame = pd.read_csv(e7_csv)
    pivot = e7_frame.pivot(index="n_states", columns="hamming_threshold", values="mean_multilabel_f1")
    figure, axis = plt.subplots(figsize=(6, 4.5)); image = axis.imshow(pivot.values, aspect="auto", vmin=0, vmax=1); axis.set_xticks(range(len(pivot.columns)), pivot.columns); axis.set_yticks(range(len(pivot.index)), pivot.index); axis.set_xlabel("hamming_threshold"); axis.set_ylabel("n_states"); figure.colorbar(image, ax=axis, label="validation F1"); figure.tight_layout(); figure.savefig(figures / "eval7_sensitivity_heatmap.png", dpi=180); plt.close(figure)
    sources["eval7"] = str(e7_csv); statuses["eval7"] = {"status": "COMPLETE", "note": "validation summary and best-condition manifest"}

    # Eval 8: preserve pre-established common fixed frequency bands.
    e8_csv = require(MODEL_ROOT / "8_vs_llm_own_id_fixed/fixed/evaluation8_by_frequency_band_by_method.csv")
    e8_rows = []
    for row in read_csv(e8_csv):
        e8_rows.append({"method": row["method"], "frequency_band": row["frequency_band"], "f1": format_mean_sd(float(row["mean_multilabel_f1"]) if row["mean_multilabel_f1"] else None, float(row["std_multilabel_f1"]) if row["std_multilabel_f1"] else None), "precision": format_mean_sd(float(row["mean_multilabel_precision"]) if row["mean_multilabel_precision"] else None, float(row["std_multilabel_precision"]) if row["std_multilabel_precision"] else None), "recall": format_mean_sd(float(row["mean_multilabel_recall"]) if row["mean_multilabel_recall"] else None, float(row["std_multilabel_recall"]) if row["std_multilabel_recall"] else None), "jaccard": format_mean_sd(float(row["mean_jaccard"]) if row["mean_jaccard"] else None, float(row["std_jaccard"]) if row["std_jaccard"] else None), "runs_with_patterns": row["num_runs_with_patterns"]})
    write_csv(tables / "table_eval8_frequency.csv", e8_rows)
    e8_frame = pd.read_csv(e8_csv).dropna(subset=["mean_multilabel_f1"])
    save_figure(figures / "eval8_frequency_f1.png", e8_frame, x="frequency_band", y="mean_multilabel_f1", hue="method", title="Evaluation 8: frequency-stratified F1")
    sources["eval8"] = str(e8_csv); statuses["eval8"] = {"status": "COMPLETE", "note": "existing fixed common frequency bins reused"}

    # Eval 9: duration robustness completed; report the formally comparable 14-day window.
    e9_csv = require(MODEL_ROOT / "9_hestia/duration/evaluation9_duration_summary.csv")
    e9_all = pd.read_csv(e9_csv)
    e9 = e9_all[(e9_all["train_days"] == 14) & (e9_all["method"] == "llm")].copy()
    if e9.empty:
        statuses["eval9"] = {"status": "NOT RUN", "note": "no completed 14-day LLM Hestia rows"}
        e9_rows = []
    else:
        e9_rows = [{"condition": row["condition"], "f1": format_mean_sd(row["f1_mean"], row["f1_std"]), "jaccard": "N/A: source evaluator reports sequence F1, not ADL Jaccard", "episode_coverage": format_mean_sd(row["test_target_episode_coverage_mean"], row["test_target_episode_coverage_std"]), "fragmentation": format_mean_sd(row["fragmentation_rate_mean"], row["fragmentation_rate_std"]), "seeds": int(row["complete_seeds"])} for _, row in e9.iterrows()]
        statuses["eval9"] = {"status": "COMPLETE", "note": "completed duration experiment, train_days=14, three seeds"}
        save_figure(figures / "eval9_hestia_f1.png", e9, x="condition", y="f1_mean", hue=None, title="Evaluation 9: Hestia F1")
    write_csv(tables / "table_eval9_robustness.csv", e9_rows); sources["eval9"] = str(e9_csv)

    # Eval 10 is an unlabeled recurrence diagnostic, never presented as ADL F1.
    e10_json = require(MODEL_ROOT / "10_real_home_temporal_generalization/2026-08-19_2026-09-19/evaluation10_summary.json")
    e10 = json.loads(e10_json.read_text(encoding="utf-8")); runs = e10["run_summary"]
    e10_overall = e10["summary"][0]
    bands = read_csv(Path(e10["outputs"]["by_time_band_csv"]))
    lengths = read_csv(Path(e10["outputs"]["by_pattern_length_csv"]))
    e10_rows = [{"scope": "overall", "extracted": e10_overall["pattern_count_mean"], "recurrent": e10_overall["supported_pattern_count_mean"], "frr": e10_overall["test_supported_pattern_fraction_mean"], "mean_test_support": e10_overall["test_occurrences_total_mean"]}]
    for group_name, group_rows in (("time_band", bands), ("sequence_length", lengths)):
        grouped: dict[str, list[dict[str, str]]] = {}
        for row in group_rows:
            grouped.setdefault(row["group"], []).append(row)
        for group, values in sorted(grouped.items()):
            extracted, _ = mean_sd([float(row["pattern_count"]) for row in values])
            recurrent_count, _ = mean_sd([float(row["recurrent_pattern_count"]) for row in values])
            recurrence, _ = mean_sd([float(row["future_recurrence_rate"]) for row in values])
            support, _ = mean_sd([float(row["mean_test_support_count"]) for row in values])
            scope = group if group_name == "time_band" else f"length_{group}"
            e10_rows.append({"scope": scope, "extracted": extracted, "recurrent": recurrent_count, "frr": recurrence, "mean_test_support": support})
    write_csv(tables / "table_eval10_real_home.csv", e10_rows)
    if bands:
        band_frame = pd.DataFrame(bands).assign(future_recurrence_rate=lambda frame: pd.to_numeric(frame["future_recurrence_rate"]))
        band_frame = band_frame.groupby("group", as_index=False)["future_recurrence_rate"].mean()
        save_figure(figures / "eval10_time_band_frr.png", band_frame, x="group", y="future_recurrence_rate", hue=None, title="Evaluation 10: future recurrence")
    sources["eval10"] = str(e10_json); statuses["eval10"] = {"status": "COMPLETE", "note": "chronological recurrence only; complete_real_home_adl_ground_truth=false"}

    # There is no compatible completed structural-constraint artifact for the
    # formal full/strict Eval6 inputs.  Do not relabel old ADL groundedness or
    # infer a thresholded score here.
    structural_rows = [{
        "scope": "full_pipeline_proposed",
        "metric_name": "structural_validity_or_constraint_compliance",
        "status": "NOT RUN",
        "reason": "no existing formal constraint-check artifact for the Eval6 full-pipeline input",
    }, {
        "scope": "strict_ablation",
        "metric_name": "structural_validity",
        "status": "NOT RUN",
        "reason": "strict prompt does not use the legacy 20% threshold; no compatible existing constraint-check artifact",
    }]
    write_csv(tables / "table_structural_validity.csv", structural_rows)
    statuses["structural_validity"] = {"status": "NOT RUN", "note": "existing artifacts do not support a comparable structural-constraint score"}

    # Blind human evaluation: full-pipeline direct/proposed only, labels kept in a separate key.
    context = load_state_context(require(ROOT / "state/aruba_individual_10_2_14days.txt"))
    human_records = []
    source_specs = [("proposed", MODEL_ROOT / "aruba_individual_10_2_14days"), ("llm_only", MODEL_ROOT / "llm_direct_aruba_individual_10_2_14days_time_split")]
    for method, directory in source_specs:
        for run in range(1, 6):
            path = directory / (f"llm_sequences_modes_10_2_14days_{run}.json" if method == "proposed" else f"{run}.json")
            if not path.exists():
                continue
            for index, item in enumerate(json.loads(path.read_text(encoding="utf-8")), start=1):
                record = extract_human_pattern(item, method, run, index, context)
                if record:
                    human_records.append(record)
    public_items, blind_key = make_blind_sample(human_records, args.human_sample_size, args.random_seed)
    write_csv(human / "human_evaluation_items.csv", public_items)
    (human / "human_evaluation_items.json").write_text(json.dumps(public_items, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(human / "human_evaluation_blind_key_internal.csv", blind_key)
    ratings = [{"anonymous_id": row["anonymous_id"], "rater_id": "", "adl_correctness": "", "rationale_faithfulness": "", "relevance": "", "interpretability": "", "usefulness": "", "invalid_or_cannot_judge": "", "comment": ""} for row in public_items]
    write_csv(human / "human_evaluation_ratings_template.csv", ratings)
    (human / "human_evaluation_instructions.md").write_text("# Human Evaluation\n\nRate each item from 1 (strongly disagree) to 5 (strongly agree): ADL correctness, rationale faithfulness, relevance, interpretability, and usefulness. Select `invalid_or_cannot_judge` when the provided context is insufficient. Method and run identity are intentionally withheld.\n", encoding="utf-8")

    for file in tables.glob("*.csv"):
        rows = read_csv(file)
        if rows:
            (file.with_suffix(".md")).write_text(table_markdown(rows, list(rows[0])), encoding="utf-8")
    summary = {"protocol": "reviewer_response_read_only_v1", "llm_api_called": False, "common_adl_labels": __import__("src.behavior_pattern_mining.evaluation.adl_interpretation_set", fromlist=["ALLOWED_LABELS"]).ALLOWED_LABELS, "sources": sources, "status": statuses, "human_evaluation": {"status": "pending_human_rating", "sample_count": len(public_items), "random_seed": args.random_seed, "method_labels_hidden": True, "rating_template": str(human / "human_evaluation_ratings_template.csv")}, "eval6_strict": {"common_runs": [row["run"] for row in strict_rows], "mean_paired_delta_f1": delta_mean, "sd_paired_delta_f1": delta_sd, "ci": "N/A: no episode-level resampling unit in existing output"}, "structural_validity": {"legacy_term_not_used": "Groundedness", "status": "NOT RUN"}, "eval10": {"complete_real_home_adl_ground_truth": False}}
    (output / "reviewer_response_evaluation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report = ["# Reviewer-response Evaluation Summary", "", "This aggregation read existing artifacts only; no LLM API was called.", "", "## Status"] + [f"- {name}: {value['status']} - {value['note']}" for name, value in statuses.items()] + ["", "## Human evaluation", f"- status: pending_human_rating", f"- blind sample count: {len(public_items)}", "- method/run labels are held only in `human_evaluation_blind_key_internal.csv`."]
    (output / "reviewer_response_evaluation_summary.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
