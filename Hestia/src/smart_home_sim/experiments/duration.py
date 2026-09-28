"""Paired train-duration sensitivity built from one shared 35-day simulation."""

from __future__ import annotations

import csv
import shutil
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from smart_home_sim.experiments.artifacts import (
    file_hash,
    generate,
    read_json,
    select_runs,
    tree_hashes,
    verify_files,
    write_json,
)
from smart_home_sim.experiments.evaluation import SUMMARY_METRICS, score_runs, summary_metric_value
from smart_home_sim.experiments.plan import ExperimentPlan

DEFAULT_TRAIN_DAYS = (3, 7, 14, 28)
BASELINE_TRAIN_DAYS = 14
DURATION_PROTOCOL = "evaluation9_duration_v2"
PRIMARY_DURATION_METRICS = (
    "adl_macro_f1",
    "f1",
    "test_target_episode_coverage",
    "test_visible_catalog_recall",
)


def validate_train_days(plan: ExperimentPlan, train_days: list[int]) -> list[int]:
    """Validate deterministic trailing windows against the raw plan."""
    values = sorted(train_days)
    if not values or any(value < 1 for value in values):
        raise ValueError("train_days must contain positive integers")
    if len(values) != len(set(values)):
        raise ValueError("train_days must be unique")
    if values[-1] != plan.train_days:
        raise ValueError("raw plan train_days must equal the longest duration window")
    if BASELINE_TRAIN_DAYS not in values:
        raise ValueError(
            f"duration sensitivity must include the {BASELINE_TRAIN_DAYS}-day baseline"
        )
    return values


def _timestamp(line: str, timezone: Any) -> datetime:
    parts = line.split()
    if len(parts) != 4:
        raise ValueError("detector input must contain exactly four observable fields")
    return datetime.fromisoformat(f"{parts[0]}T{parts[1]}").replace(tzinfo=timezone)


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _window_payload(plan: ExperimentPlan, train_days: int) -> ExperimentPlan:
    payload = plan.model_dump(mode="json")
    payload["start_datetime"] = (
        plan.start_datetime + timedelta(days=plan.train_days - train_days)
    ).isoformat()
    payload["train_days"] = train_days
    return ExperimentPlan.model_validate(payload)


def _filter_truth(source: Path, target: Path, start: datetime, end: datetime) -> None:
    rows = [
        row
        for row in read_json(source)
        if row.get("start")
        and row.get("end")
        and datetime.fromisoformat(row["start"]) >= start
        and datetime.fromisoformat(row["end"]) <= end
    ]
    write_json(target, rows)


def _materialize_run(raw_run: Path, run: Path, plan: ExperimentPlan) -> None:
    raw_marker = read_json(raw_run / "generated.json")
    verify_files(raw_run, raw_marker["files"])
    marker = run / "generated.json"
    source_identity = {
        "raw_generated_sha256": file_hash(raw_run / "generated.json"),
        "duration_adapter_sha256": file_hash(Path(__file__)),
        "window_start": plan.start_datetime.isoformat(),
        "train_days": plan.train_days,
        "test_days": plan.test_days,
    }
    if marker.is_file():
        previous = read_json(marker)
        if previous.get("duration_source") != source_identity:
            raise ValueError(f"duration window source changed: {run}")
        verify_files(run, previous["files"])
        return
    if run.exists() and any(run.iterdir()):
        raise ValueError(f"incomplete duration window at {run}; use a new output")

    raw_settings = read_json(raw_run / "run.json")
    start = plan.start_datetime
    split = start + timedelta(days=plan.train_days)
    end = split + timedelta(days=plan.test_days)
    settings = {**raw_settings, "plan": plan.model_dump(mode="json")}
    write_json(run / "run.json", settings)
    for relative in ("scenario.json", "input/sensor_map.json"):
        _copy(raw_run / relative, run / relative)

    lines = (raw_run / "input/sensors.txt").read_text(encoding="utf-8").splitlines()
    selected = [line for line in lines if start <= _timestamp(line, start.tzinfo) < end]
    training = [line for line in selected if _timestamp(line, start.tzinfo) < split]
    if not selected or not training:
        raise ValueError(f"empty duration slice for {run}")
    (run / "input").mkdir(parents=True, exist_ok=True)
    (run / "input/sensors.txt").write_text("\n".join(selected) + "\n", encoding="utf-8")
    (run / "input/train.txt").write_text("\n".join(training) + "\n", encoding="utf-8")
    _filter_truth(raw_run / "truth/activities.json", run / "truth/activities.json", start, end)
    _filter_truth(
        raw_run / "truth/target_episodes.json",
        run / "truth/target_episodes.json",
        start,
        end,
    )
    motifs = read_json(raw_run / "truth/motifs.json")
    motifs.update(
        {
            "split": split.isoformat(timespec="microseconds"),
            "duration_window_start": start.isoformat(timespec="microseconds"),
            "shared_test_start": split.isoformat(timespec="microseconds"),
            "raw_generated_sha256": source_identity["raw_generated_sha256"],
        }
    )
    write_json(run / "truth/motifs.json", motifs)
    write_json(run / "duration_source.json", source_identity)
    write_json(marker, {"files": tree_hashes(run), "duration_source": source_identity})


def generate_duration(
    plan: ExperimentPlan, output: Path, train_days: list[int] | None = None
) -> list[Path]:
    """Generate raw logs once and materialize hashed trailing analysis windows."""
    values = validate_train_days(plan, train_days or list(DEFAULT_TRAIN_DAYS))
    output = output.resolve()
    manifest_path = output / "duration.json"
    manifest = {
        "protocol": DURATION_PROTOCOL,
        "train_days": values,
        "test_days": plan.test_days,
        "raw_plan": plan.model_dump(mode="json"),
        "shared_test_start": (plan.start_datetime + timedelta(days=plan.train_days)).isoformat(),
        "canonical_gold_varies_by_train_days": True,
        "duration_adapter_sha256": file_hash(Path(__file__)),
    }
    if manifest_path.exists() and read_json(manifest_path) != manifest:
        raise ValueError("duration plan differs from snapshot; use a new output directory")
    if output.exists() and not manifest_path.exists() and any(output.iterdir()):
        raise ValueError(f"output must be empty: {output}")
    write_json(manifest_path, manifest)
    raw = output / "raw"
    raw_runs = generate(plan, raw)
    result = []
    for days in values:
        window_plan = _window_payload(plan, days)
        experiment = output / "windows" / f"train_{days}d"
        snapshot = experiment / "experiment.json"
        window_payload = window_plan.model_dump(mode="json")
        if snapshot.is_file() and read_json(snapshot) != window_payload:
            raise ValueError(f"duration window plan changed: {experiment}")
        if not snapshot.exists() and experiment.exists() and any(experiment.iterdir()):
            raise ValueError(f"incomplete duration experiment: {experiment}")
        write_json(snapshot, window_payload)
        for raw_run in raw_runs:
            relative = raw_run.relative_to(raw / "runs")
            run = experiment / "runs" / relative
            _materialize_run(raw_run, run, window_plan)
            result.append(run)
    return result


def duration_experiments(output: Path) -> list[tuple[int, Path]]:
    manifest = read_json(output / "duration.json")
    return [(days, output / "windows" / f"train_{days}d") for days in manifest["train_days"]]


def duration_runs(output: Path) -> list[tuple[int, Path]]:
    return [
        (days, run)
        for days, experiment in duration_experiments(output)
        for run in select_runs(experiment)
    ]


def _model(
    row: dict[str, Any],
    run_by_key: dict[tuple[int, str, int], Path],
    artifact_run_by_key: dict[tuple[int, str, int], Path] | None = None,
) -> str | None:
    if row["method"] != "llm":
        return None
    path = run_by_key[row["train_days"], row["condition"], row["seed"]]
    key = row["train_days"], row["condition"], row["seed"]
    artifact_path = (artifact_run_by_key or {}).get(key, path)
    metadata = artifact_path / "predictions/llm/model_metadata.json"
    if metadata.is_file():
        return read_json(metadata).get("model_id")
    settings = path / "analysis/llm_settings.json"
    return read_json(settings)["model"] if settings.is_file() else None


def _seed_metric_values(items: list[dict[str, Any]], metric: str) -> dict[int, float]:
    by_seed: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_seed[item["seed"]].append(item)
    result = {}
    for seed, values in by_seed.items():
        if not values or any(value["status"] != "complete" for value in values):
            continue
        scores = [summary_metric_value(value["metrics"], metric) for value in values]
        if all(score is not None for score in scores):
            result[seed] = mean(scores)
    return result


def _summary_row(
    items: list[dict[str, Any]], *, days: int, condition: str, method: str, model: str | None
) -> tuple[dict[str, Any], dict[str, dict[int, float]]]:
    row: dict[str, Any] = {
        "train_days": days,
        "test_days": items[0]["test_days"],
        "condition": condition,
        "method": method,
        "model": model,
        "expected_runs": len(items),
        "complete_runs": sum(item["status"] == "complete" for item in items),
        "missing_runs": sum(item["status"] == "missing" for item in items),
        "invalid_runs": sum(item["status"] == "invalid" for item in items),
        "expected_seeds": len({item["seed"] for item in items}),
    }
    by_seed: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_seed[item["seed"]].append(item)
    complete_seeds = sum(
        all(item["status"] == "complete" for item in seed_items) for seed_items in by_seed.values()
    )
    row["complete_seeds"] = complete_seeds
    row["_n_seeds"] = complete_seeds
    statuses = {
        item["metrics"].get("fragmentation_status")
        for item in items
        if item["status"] == "complete"
    }
    row["fragmentation_status"] = (
        next(iter(statuses)) if len(statuses) == 1 else "mixed" if statuses else "no_complete_runs"
    )
    seed_values = {}
    for metric in SUMMARY_METRICS:
        values = _seed_metric_values(items, metric)
        seed_values[metric] = values
        scores = list(values.values())
        row[f"{metric}_mean"] = mean(scores) if scores else None
        row[f"{metric}_std"] = stdev(scores) if len(scores) > 1 else None
        row[f"{metric}_n_seeds"] = len(scores)
    return row, seed_values


def aggregate_duration(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
    overall: dict[tuple[int, str, str | None], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = row["train_days"], row["condition"], row["method"], row.get("model")
        grouped[key].append(row)
        overall[row["train_days"], row["method"], row.get("model")].append(row)
    summaries = []
    values_by_key: dict[tuple[int, str, str, str | None], dict[str, dict[int, float]]] = {}
    for (days, condition, method, model), items in sorted(grouped.items()):
        summary, values = _summary_row(
            items, days=days, condition=condition, method=method, model=model
        )
        summaries.append(summary)
        values_by_key[days, condition, method, model] = values
    for (days, method, model), items in sorted(overall.items()):
        summary, values = _summary_row(
            items, days=days, condition="overall", method=method, model=model
        )
        summaries.append(summary)
        values_by_key[days, "overall", method, model] = values

    for summary in summaries:
        key = (
            summary["train_days"],
            summary["condition"],
            summary["method"],
            summary["model"],
        )
        baseline_key = (BASELINE_TRAIN_DAYS, *key[1:])
        for metric in PRIMARY_DURATION_METRICS:
            current = values_by_key[key][metric]
            baseline = values_by_key.get(baseline_key, {}).get(metric, {})
            paired = [
                current[seed] - baseline[seed] for seed in sorted(current.keys() & baseline.keys())
            ]
            prefix = f"{metric}_delta_vs_{BASELINE_TRAIN_DAYS}d"
            summary[f"{prefix}_mean"] = mean(paired) if paired else None
            summary[f"{prefix}_std"] = stdev(paired) if len(paired) > 1 else None
            summary[f"{prefix}_n_seeds"] = len(paired)
    return sorted(
        summaries,
        key=lambda row: (
            row["condition"] != "overall",
            row["condition"],
            row["method"],
            row["train_days"],
        ),
    )


def _write_plot(output: Path, summaries: list[dict[str, Any]], metric: str) -> None:
    rows = [
        row for row in summaries if row["method"] == "llm" and row[f"{metric}_mean"] is not None
    ]
    if not rows:
        return
    width, height = 900, 560
    left, top, plot_width, plot_height = 80, 45, 760, 420
    days = sorted({row["train_days"] for row in rows})
    colors = ["#172326", "#147d78", "#d06a24", "#79589f", "#4e79a7", "#e15759", "#59a14f"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="28" font-family="Arial" font-size="20" font-weight="700">'
        f"{metric} by train duration</text>",
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" '
        f'y2="{top + plot_height}" stroke="#555"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#555"/>',
    ]
    for tick in range(6):
        value = tick / 5
        y = top + plot_height * (1 - value)
        parts.append(
            f'<text x="{left - 12}" y="{y + 5}" text-anchor="end" '
            f'font-family="Arial" font-size="12">{value:.1f}</text>'
        )
    for index, day in enumerate(days):
        x = left + (index / max(1, len(days) - 1)) * plot_width
        parts.append(
            f'<text x="{x}" y="{top + plot_height + 24}" text-anchor="middle" '
            f'font-family="Arial" font-size="13">{day}</text>'
        )
    conditions = sorted({row["condition"] for row in rows}, key=lambda value: value != "overall")
    for line_index, condition in enumerate(conditions):
        selected = {row["train_days"]: row for row in rows if row["condition"] == condition}
        points = []
        for index, day in enumerate(days):
            if day not in selected:
                continue
            x = left + (index / max(1, len(days) - 1)) * plot_width
            value = max(0.0, min(1.0, float(selected[day][f"{metric}_mean"])))
            y = top + plot_height * (1 - value)
            points.append((x, y, selected[day].get(f"{metric}_std")))
        color = colors[line_index % len(colors)]
        if points:
            parts.append(
                '<polyline fill="none" stroke="'
                + color
                + '" stroke-width="2.5" points="'
                + " ".join(f"{x},{y}" for x, y, _ in points)
                + '"/>'
            )
        for x, y, deviation in points:
            if deviation is not None:
                delta = float(deviation) * plot_height
                parts.append(
                    f'<line x1="{x}" y1="{max(top, y - delta)}" x2="{x}" '
                    f'y2="{min(top + plot_height, y + delta)}" stroke="{color}"/>'
                )
            parts.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>')
        legend_y = 490 + (line_index // 4) * 22
        legend_x = left + (line_index % 4) * 195
        parts.append(
            f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 20}" '
            f'y2="{legend_y}" stroke="{color}" stroke-width="3"/>'
            f'<text x="{legend_x + 27}" y="{legend_y + 5}" font-family="Arial" '
            f'font-size="12">{condition}</text>'
        )
    parts.append(
        f'<text x="{left + plot_width / 2}" y="545" text-anchor="middle" '
        'font-family="Arial" font-size="14">train_days (shared 7-day test)</text></svg>'
    )
    output.write_text("".join(parts), encoding="utf-8")


def write_duration_summary(output: Path, rows: list[dict[str, Any]]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    summaries = aggregate_duration(rows)
    write_json(
        output / "evaluation9_duration_summary.json",
        {
            "protocol": DURATION_PROTOCOL,
            "canonical_gold_varies_by_train_days": True,
            "baseline_train_days": BASELINE_TRAIN_DAYS,
            "runs": rows,
            "summary": summaries,
        },
    )
    run_fields = [
        "train_days",
        "test_days",
        "condition",
        "seed",
        "method",
        "model",
        "run_id",
        "status",
        "complete",
        "missing",
        "invalid",
        "reason",
        *SUMMARY_METRICS,
        "fragmentation_status",
    ]
    with (output / "evaluation9_duration_summary_runs.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=run_fields)
        writer.writeheader()
        for row in rows:
            metrics = row["metrics"]
            writer.writerow(
                {
                    **{
                        field: row.get(field)
                        for field in run_fields
                        if field not in SUMMARY_METRICS
                        and field not in {"complete", "missing", "invalid", "fragmentation_status"}
                    },
                    "complete": int(row["status"] == "complete"),
                    "missing": int(row["status"] == "missing"),
                    "invalid": int(row["status"] == "invalid"),
                    "fragmentation_status": metrics.get("fragmentation_status"),
                    **{
                        metric: summary_metric_value(metrics, metric)
                        for metric in SUMMARY_METRICS
                        if metric == "adl_macro_f1" or metric in metrics
                    },
                }
            )
    with (output / "evaluation9_duration_summary.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    for metric in ("adl_macro_f1", "test_target_episode_coverage", "f1"):
        _write_plot(output / f"evaluation9_duration_{metric}.svg", summaries, metric)


def score_duration(
    output: Path,
    results: Path,
    method: str,
    llm_results_root: Path | None = None,
) -> list[dict[str, Any]]:
    run_by_key = {
        (
            days,
            read_json(run / "run.json")["condition"]["id"],
            read_json(run / "run.json")["seed"],
        ): run
        for days, run in duration_runs(output)
    }
    rows = []
    artifact_run_by_key: dict[tuple[int, str, int], Path] = {}
    for days, experiment in duration_experiments(output):
        methods = ("frequency", "llm") if method == "both" else (method,)
        settings = read_json(experiment / "experiment.json")
        selected_runs = select_runs(experiment)
        artifact_runs = None
        if llm_results_root is not None:
            window_root = llm_results_root / "windows" / f"train_{days}d"
            artifact_runs = {
                run: window_root / run.relative_to(experiment) for run in selected_runs
            }
            for run, artifact_run in artifact_runs.items():
                run_settings = read_json(run / "run.json")
                artifact_run_by_key[
                    days,
                    run_settings["condition"]["id"],
                    run_settings["seed"],
                ] = artifact_run
        for selected in methods:
            current = score_runs(selected_runs, selected, artifact_runs)
            for row in current:
                row.update(train_days=days, test_days=settings["test_days"])
                row["model"] = _model(row, run_by_key, artifact_run_by_key)
            rows.extend(current)
    models = {row["model"] for row in rows if row["method"] == "llm" and row["model"] is not None}
    if len(models) > 1:
        raise ValueError(f"duration sensitivity requires one fixed LLM model, found: {models}")
    write_duration_summary(results, rows)
    return rows
