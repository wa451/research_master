"""Offline frequency control and missing-aware, seed-level result aggregation."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from smart_home_sim.experiments.artifacts import (
    file_hash,
    read_json,
    verify_files,
    write_json,
)
from smart_home_sim.experiments.metrics import evaluate_payload, load_series, occurrences
from smart_home_sim.experiments.research import llm_output, verify_prepared

REQUIRED_RUN_METRICS = (
    "TP",
    "FP",
    "FN",
    "precision",
    "recall",
    "f1",
    "num_gold_patterns",
    "num_extracted_patterns",
    "num_potential_fragments",
    "num_emitted_fragments",
    "fragmentation_rate",
)


def unscored_metrics() -> dict[str, Any]:
    return {
        **dict.fromkeys(REQUIRED_RUN_METRICS),
        "fragmentation_status": "not_evaluated",
    }


def frequency_baseline(run: Path) -> None:
    verify_prepared(run)
    plan = read_json(run / "run.json")["plan"]
    start = datetime.fromisoformat(plan["start_datetime"])
    split = start + timedelta(days=plan["train_days"])
    series = load_series(run / "analysis/state_series.csv", start.tzinfo)
    counts = Counter(item.key for item in occurrences(series, start, split))
    selected = sorted(
        (key for key, count in counts.items() if count >= plan["min_train_support"]),
        key=lambda key: (-counts[key], key),
    )[: plan["baseline_top_k"]]
    payload = [
        {
            "sequence": list(sequence),
            "mode": mode,
            "train_support": counts[mode, sequence],
            "labels": [],
        }
        for mode, sequence in selected
    ]
    path = run / "predictions/frequency.json"
    if path.exists() and read_json(path) != payload:
        raise ValueError(f"existing baseline differs: {path}")
    write_json(path, payload)


def score_runs(runs: list[Path], method: str) -> list[dict[str, Any]]:
    rows = []
    for run in runs:
        settings = read_json(run / "run.json")
        count = settings["plan"]["llm_runs"] if method == "llm" else 1
        for index in range(1, count + 1):
            row: dict[str, Any] = {
                "condition": settings["condition"]["id"],
                "seed": settings["seed"],
                "method": method,
                "run_id": index,
                "evaluation_protocol": "hestia_noise_free_v2",
                "evaluation_sources": {
                    name: file_hash(Path(__file__).with_name(name))
                    for name in ("metrics.py", "evaluation.py")
                },
            }
            path = llm_output(run, index) if method == "llm" else run / "predictions/frequency.json"
            marker = run / f"predictions/llm/complete_{index}.json"
            if not path.exists() or (method == "llm" and not marker.exists()):
                row.update(
                    status="missing",
                    reason="no completed prediction artifact",
                    metrics=unscored_metrics(),
                )
            else:
                try:
                    verify_prepared(run)
                    if method == "llm":
                        verify_files(run, read_json(marker)["files"])
                    metrics = evaluate_payload(run, read_json(path), semantic=method == "llm")
                    write_json(
                        run / "evaluation/gold_catalog.json",
                        {
                            "gold_catalog": metrics["gold_catalog"],
                            "projected_target_episodes": metrics["projected_target_episodes"],
                        },
                    )
                    row.update(
                        status="complete", prediction_sha256=file_hash(path), metrics=metrics
                    )
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    row.update(status="invalid", reason=str(exc), metrics=unscored_metrics())
            write_json(run / "evaluation" / f"{method}_{index}.json", row)
            rows.append(row)
    return rows


SUMMARY_METRICS = (
    "TP",
    "FP",
    "FN",
    "precision",
    "recall",
    "f1",
    "num_gold_patterns",
    "num_extracted_patterns",
    "num_potential_fragments",
    "num_emitted_fragments",
    "fragmentation_rate",
    "extracted_fragment_rate_diagnostic",
    "catalog_recall",
    "test_visible_catalog_recall",
    "test_target_episode_coverage",
    "test_supported_pattern_fraction",
    "test_other_duration_ratio",
    "train_other_duration_ratio",
    "adl_macro_f1",
)


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["condition"], row["method"]].append(row)
    summaries = []
    for (condition, method), items in sorted(groups.items()):
        by_seed: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            by_seed[item["seed"]].append(item)
        # LLM反復を独立住宅として数えない。欠落反復のあるseedは主集計から除外。
        complete_seeds = {
            seed: values
            for seed, values in by_seed.items()
            if all(value["status"] == "complete" for value in values)
        }
        summary: dict[str, Any] = {
            "condition": condition,
            "method": method,
            "expected_runs": len(items),
            "complete_runs": sum(item["status"] == "complete" for item in items),
            "missing_runs": sum(item["status"] == "missing" for item in items),
            "invalid_runs": sum(item["status"] == "invalid" for item in items),
            "expected_seeds": len(by_seed),
            "complete_seeds": len(complete_seeds),
        }
        fragmentation_statuses = {
            item["metrics"]["fragmentation_status"]
            for item in items
            if item["status"] == "complete"
        }
        summary["fragmentation_status"] = (
            next(iter(fragmentation_statuses))
            if len(fragmentation_statuses) == 1
            else "mixed"
            if fragmentation_statuses
            else "no_complete_runs"
        )
        for metric in SUMMARY_METRICS:
            seed_means = []
            for values in complete_seeds.values():
                scores = []
                for value in values:
                    metrics = value["metrics"]
                    score = (
                        (metrics["adl"] or {}).get("macro_f1")
                        if metric == "adl_macro_f1"
                        else metrics[metric]
                    )
                    if score is not None:
                        scores.append(score)
                if len(scores) == len(values):
                    seed_means.append(mean(scores))
            summary[f"{metric}_mean"] = mean(seed_means) if seed_means else None
            summary[f"{metric}_std"] = stdev(seed_means) if len(seed_means) > 1 else None
            summary[f"{metric}_n_seeds"] = len(seed_means)
        summaries.append(summary)
    return summaries


def write_summary(output: Path, rows: list[dict[str, Any]]) -> None:
    summaries = aggregate(rows)
    write_json(output.with_suffix(".json"), {"runs": rows, "summary": summaries})
    output.parent.mkdir(parents=True, exist_ok=True)
    detail_fields = [
        "condition",
        "seed",
        "method",
        "run_id",
        "status",
        "complete",
        "missing",
        "invalid",
        "reason",
        *SUMMARY_METRICS,
        "num_emitted_potential_fragments",
        "fragmentation_status",
        "num_evaluable_extracted_patterns",
        "num_fragmented_extracted_patterns",
    ]
    with (
        output.with_name(f"{output.name}_runs")
        .with_suffix(".csv")
        .open("w", encoding="utf-8", newline="") as stream
    ):
        writer = csv.DictWriter(stream, fieldnames=detail_fields)
        writer.writeheader()
        for row in rows:
            metrics = row.get("metrics", {})
            writer.writerow(
                {
                    "condition": row["condition"],
                    "seed": row["seed"],
                    "method": row["method"],
                    "run_id": row["run_id"],
                    "status": row["status"],
                    "complete": int(row["status"] == "complete"),
                    "missing": int(row["status"] == "missing"),
                    "invalid": int(row["status"] == "invalid"),
                    "reason": row.get("reason"),
                    **{field: metrics.get(field) for field in detail_fields if field in metrics},
                }
            )
    if summaries:
        with output.with_suffix(".csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(summaries[0]))
            writer.writeheader()
            writer.writerows(summaries)
