#!/usr/bin/env python3
"""Freeze and audit existing Evaluation 5--10 results without executing an LLM.

This is intentionally a read-only consumer of experiment artifacts.  It creates
new checksum manifests, hard-link snapshots (where the filesystem permits it),
tables, figures, and audit reports under ``results/``.  It never invokes an
evaluation CLI and never writes to an existing experiment directory.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
SNAPSHOT_ROOT = RESULTS / "final_evaluation_snapshot"
COMPARISON_ROOT = RESULTS / "model_comparison"
TARGET_RESULT_NAMES = {"gpt-5.6-sol", "claude-fable-5"}
METRICS = ("mean_multilabel_precision", "mean_multilabel_recall", "mean_multilabel_f1", "mean_jaccard", "mean_exact_set_match")


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in rows for key in row)) or ["status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def numeric(value: Any) -> float | None:
    if value in (None, "", "N/A", "NA", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def mean_sd(values: Iterable[Any]) -> tuple[float | None, float | None]:
    cleaned = [value for value in (numeric(item) for item in values) if value is not None]
    if not cleaned:
        return None, None
    return statistics.fmean(cleaned), statistics.stdev(cleaned) if len(cleaned) > 1 else 0.0


def git_info() -> dict[str, Any]:
    def output(*args: str) -> str:
        return subprocess.check_output(args, cwd=ROOT, text=True).strip()
    status = output("git", "status", "--short")
    return {
        "commit": output("git", "rev-parse", "HEAD"),
        "branch": output("git", "branch", "--show-current"),
        "dirty": bool(status),
        "status_short": status.splitlines(),
    }


def model_roots() -> dict[str, dict[str, Any]]:
    """Discover target namespace and identity from Evaluation 5 metadata."""
    discovered: dict[str, dict[str, Any]] = {}
    for candidate in RESULTS.iterdir():
        summary = candidate / "5_pattern_quality_individual_fixed" / "evaluation5_summary.json"
        if not summary.is_file():
            continue
        payload = load_json(summary)
        identity = payload.get("model", {})
        name = identity.get("result_name")
        if name in TARGET_RESULT_NAMES:
            discovered[str(name)] = {"root": candidate, "identity": identity, "identity_source": summary}
    if set(discovered) != TARGET_RESULT_NAMES:
        raise RuntimeError(f"Could not discover both requested models from metadata: {sorted(discovered)}")
    return discovered


def first(parent: Path, pattern: str) -> Path | None:
    paths = sorted(parent.glob(pattern))
    return paths[0] if paths else None


def discover_evaluations(root: Path) -> dict[str, list[Path]]:
    """Find actual summary/manifest roots; do not assume one Eval9 experiment."""
    strict = sorted(root.glob("6_strict_ablation/*/evaluation/evaluation6_strict_ablation_summary.json"))
    eval9 = sorted(root.glob("9_hestia/**/evaluation9*_summary.json"))
    return {
        "eval5": [root / "5_pattern_quality_individual_fixed" / "evaluation5_summary.json"],
        "eval6_full": [root / "6_adl_match_individual_holdout_test_direct_time_split" / "evaluation6_comparison_summary.json"],
        "eval6_strict": strict,
        "eval7": [root / "7_param_search_14d_5runs_individual_holdout" / "evaluation7_summary.json"],
        "eval8_fixed": [root / "8_vs_llm_own_id_fixed" / "fixed" / "evaluation8_summary.json"],
        "eval8_tertile": [root / "8_vs_llm_own_id_fixed" / "tertile" / "evaluation8_summary.json"],
        "eval9": eval9,
        "eval10": sorted(root.glob("10_real_home_temporal_generalization/**/evaluation10_summary.json")),
    }


def strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, dict):
        for value in obj.values():
            yield from strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from strings(value)
    elif isinstance(obj, str):
        yield obj


def source_files(summary: Path) -> set[Path]:
    """Collect summary trees plus existing artifact references, excluding source data."""
    files = {path for path in summary.parent.rglob("*") if path.is_file()}
    try:
        payload = load_json(summary)
    except (json.JSONDecodeError, OSError):
        return files
    for value in strings(payload):
        path = Path(value)
        if path.is_file() and (str(path).startswith(str(RESULTS)) or str(path).startswith(str(ROOT / "output")) or str(path).startswith(str(ROOT / "state"))):
            files.add(path)
    return files


def hardlink_snapshot(model_name: str, evaluations: dict[str, list[Path]], info: dict[str, Any]) -> dict[str, Any]:
    snapshot_dir = SNAPSHOT_ROOT / model_name
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    git = git_info()
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "snapshot_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": info["identity"],
        "model_identity_source": rel(info["identity_source"]),
        "git": git,
        "evaluations": {},
        "snapshot_method": "hard_link_when_possible; checksum_manifest_for_all_files",
    }
    checksums: list[dict[str, Any]] = []
    for evaluation, summaries in evaluations.items():
        existing = [path for path in summaries if path.is_file()]
        entry: dict[str, Any] = {"status": "available" if existing else "missing", "summary_paths": [rel(path) for path in existing], "manifest_paths": [], "raw_output_directories": [], "run_metadata": [], "files": []}
        seen: set[Path] = set()
        for summary in existing:
            payload = load_json(summary)
            entry["run_metadata"].append({
                "summary_path": rel(summary),
                "runs_requested": payload.get("runs_requested") or payload.get("requested_runs"),
                "runs_completed": payload.get("runs_completed") or payload.get("common_completed_runs"),
                "model": payload.get("model"),
            })
            for source_manifest in summary.parent.glob("*manifest*.json"):
                entry["manifest_paths"].append(rel(source_manifest))
            for source in sorted(source_files(summary)):
                if source in seen:
                    continue
                seen.add(source)
                record = {"source_path": rel(source), "bytes": source.stat().st_size, "sha256": sha256(source)}
                entry["files"].append(record)
                checksums.append({"evaluation": evaluation, **record})
                if str(source).startswith(str(ROOT / "output")):
                    entry["raw_output_directories"].append(rel(source.parent))
                # A hard link is a recoverable snapshot if source filenames are removed.
                target = snapshot_dir / "artifacts" / evaluation / rel(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    try:
                        os.link(source, target)
                    except OSError:
                        # Leave checksum-only evidence when cross-device hardlinks are unavailable.
                        record["hardlink"] = "unavailable"
                    else:
                        record["hardlink"] = rel(target)
        entry["raw_output_directories"] = sorted(set(entry["raw_output_directories"]))
        entry["file_count"] = len(entry["files"])
        entry["total_bytes"] = sum(item["bytes"] for item in entry["files"])
        manifest["evaluations"][evaluation] = entry
    write_json(snapshot_dir / "snapshot_manifest.json", manifest)
    write_json(snapshot_dir / "checksum_manifest.json", {"schema_version": 1, "files": checksums})
    return manifest


def summary_rows_from_eval6(path: Path, model: str) -> list[dict[str, Any]]:
    rows = read_csv(path.parent / "evaluation6_method_comparison.csv")
    return [{"model": model, "method": {"proposed": "Proposed", "direct_log_baseline": "LLM-only"}.get(row["method"], row["method"]), **row} for row in rows]


def strict_rows(path: Path, model: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summary = read_csv(path.parent / "evaluation6_strict_ablation_summary.csv")
    by_run = read_csv(path.parent / "evaluation6_strict_ablation_by_run.csv")
    return ([{"model": model, **row} for row in summary], [{"model": model, **row} for row in by_run])


def eval5_rows(path: Path, model: str) -> list[dict[str, Any]]:
    return [{"model": model, **row} for row in read_csv(path.parent / "evaluation5_summary_by_method.csv")]


def eval7_rows(path: Path, model: str) -> list[dict[str, Any]]:
    csv_path = path.parent / "evaluation7_condition_summary.csv"
    return [{"model": model, **row} for row in read_csv(csv_path)] if csv_path.is_file() else []


def eval8_rows(path: Path, model: str) -> list[dict[str, Any]]:
    csv_path = path.parent / "evaluation8_by_frequency_band_by_method.csv"
    return [{"model": model, "mode": path.parent.name, **row} for row in read_csv(csv_path)] if csv_path.is_file() else []


def eval9_rows(paths: list[Path], model: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for path in paths:
        run_csv = next(iter(sorted(path.parent.glob("*summary_runs.csv"))), None)
        if run_csv:
            # Some Hestia rows deliberately leave their model column blank for
            # non-LLM baselines.  Namespace/summary metadata is authoritative.
            output.extend({**row, "model": model, "experiment": path.parent.name} for row in read_csv(run_csv))
    return output


def eval10_rows(path: Path, model: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    root = path.parent
    return (
        [{"model": model, **row} for row in read_csv(root / "evaluation10_summary_by_run.csv")],
        [{"model": model, **row} for row in read_csv(root / "evaluation10_by_time_band.csv")],
        [{"model": model, **row} for row in read_csv(root / "evaluation10_by_pattern_length.csv")],
    )


def metric_table(rows: list[dict[str, Any]], metrics: tuple[str, ...] = METRICS) -> list[dict[str, Any]]:
    table: list[dict[str, Any]] = []
    for row in rows:
        record = {key: row.get(key) for key in ("model", "method", "representation", "frequency_band", "condition", "seed", "experiment", "run") if key in row}
        for metric in metrics:
            value = row.get(metric)
            record[metric] = value
        table.append(record)
    return table


def aggregate_eval9(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("method") == "llm" and str(row.get("complete")) == "1":
            groups[(row["model"], row["experiment"], row.get("train_days", ""), row.get("test_days", ""), row["condition"])].append(row)
    output = []
    for (model, experiment, train_days, test_days, condition), values in sorted(groups.items()):
        record: dict[str, Any] = {"model": model, "experiment": experiment, "train_days": train_days, "test_days": test_days, "condition": condition, "completed_rows": len(values), "seeds": ";".join(sorted({str(row.get("seed", "")) for row in values}))}
        for metric in ("precision", "recall", "f1", "test_target_episode_coverage", "fragmentation_rate"):
            average, sd = mean_sd(row.get(metric) for row in values)
            record[f"{metric}_mean"] = average
            record[f"{metric}_sd"] = sd
        jaccard = []
        for row in values:
            tp, fp, fn = numeric(row.get("TP")), numeric(row.get("FP")), numeric(row.get("FN"))
            jaccard.append(tp / (tp + fp + fn) if tp is not None and fp is not None and fn is not None and tp + fp + fn else None)
        record["jaccard_mean"], record["jaccard_sd"] = mean_sd(jaccard)
        output.append(record)
    return output


def aggregate_eval10(rows: list[dict[str, Any]], group_key: str) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["model"], row.get(group_key, ""))].append(row)
    output = []
    for (model, group), values in sorted(groups.items()):
        record = {"model": model, group_key: group, "runs": len(values)}
        for metric in (
            "pattern_count", "supported_pattern_count", "test_supported_pattern_fraction",
            "mean_test_day_recurrence", "train_occurrences_total", "test_occurrences_total",
            "test_transition_coverage", "recurrent_pattern_count", "future_recurrence_rate",
            "mean_test_support_count",
        ):
            average, sd = mean_sd(row.get(metric) for row in values)
            record[f"{metric}_mean"] = average
            record[f"{metric}_sd"] = sd
        output.append(record)
    return output


def severity(checks: list[dict[str, Any]], level: str, check: str, evidence: str) -> None:
    checks.append({"severity": level, "check": check, "evidence": evidence})


def audit(model_data: dict[str, dict[str, Any]], artifacts: dict[str, dict[str, list[Path]]], all_rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    expected_id = {name: data["identity"].get("model_id") for name, data in model_data.items()}
    for name, data in model_data.items():
        # Examine only files included in the frozen Evaluation 5--10 snapshot;
        # unrelated API smoke tests in the same namespace are not evidence of a
        # mixed final evaluation artifact.
        foreign = []
        final_files = set()
        for summaries in artifacts[name].values():
            for summary in summaries:
                if summary.is_file():
                    final_files.update(source_files(summary))
        for metadata in sorted(path for path in final_files if "metadata" in path.name and path.suffix == ".json"):
            try:
                text = metadata.read_text(encoding="utf-8")
            except OSError:
                continue
            for other_name, other_id in expected_id.items():
                if other_name != name and other_id and other_id in text:
                    foreign.append(rel(metadata))
        severity(checks, "CRITICAL" if foreign else "INFO", "model identity isolation", f"{name}: foreign model IDs in metadata={foreign}")
        for evaluation, paths in artifacts[name].items():
            severity(checks, "WARNING" if not [path for path in paths if path.is_file()] else "INFO", "artifact presence", f"{name}/{evaluation}: {len([path for path in paths if path.is_file()])} summary artifact(s)")

    # Eval6 strict must use paired 1..5 runs. Verify manifests and rows independently.
    for name, paths in artifacts.items():
        strict = paths["eval6_strict"]
        if strict:
            base = strict[0].parent.parent
            manifest = load_json(base / "manifest.json")
            rows = read_csv(strict[0].parent / "evaluation6_strict_ablation_by_run.csv")
            methods = defaultdict(set)
            for row in rows:
                methods[row["method"]].add(row["run"])
            common = methods.get("proposed_strict", set()) & methods.get("llm_only_strict", set())
            fields = ("source_log", "n_states", "hamming_threshold", "generation_days", "sensor_representation", "prompt_sha256", "state_table_sha256")
            missing = [field for field in fields if manifest.get(field) in (None, "")]
            severity(checks, "ERROR" if common != {"1", "2", "3", "4", "5"} else "INFO", "Eval6 Strict common completed runs", f"{name}: common={sorted(common)}")
            severity(checks, "ERROR" if missing else "INFO", "Eval6 Strict fixed-contract fields", f"{name}: missing={missing}")

    # Eval7 formal source records must not score test days; absence is not silently repaired.
    for name, paths in artifacts.items():
        path = paths["eval7"][0] if paths["eval7"] else None
        if not path or not path.is_file():
            severity(checks, "WARNING", "Eval7 completeness/leakage", f"{name}: formal Evaluation 7 summary absent")
            continue
        payload = load_json(path)
        leakage = (payload.get("evaluation_role") != "validation" or payload.get("validation_start_day") != 15 or payload.get("validation_end_day") != 154 or payload.get("test_start_day") != 155 or payload.get("test_end_day") != 220)
        severity(checks, "CRITICAL" if leakage else "INFO", "Eval7 holdout isolation", f"{name}: role={payload.get('evaluation_role')}, validation={payload.get('validation_start_day')}--{payload.get('validation_end_day')}, test={payload.get('test_start_day')}--{payload.get('test_end_day')}")

    # Recompute run-level means and SDs rather than trusting summary values.
    for name, paths in artifacts.items():
        full = paths["eval6_full"][0]
        if full.is_file():
            summary_rows = {row["method"]: row for row in read_csv(full.parent / "evaluation6_method_comparison.csv")}
            run_rows = read_csv(full.parent / "evaluation6_method_comparison_by_run.csv")
            mismatches = []
            for method, summary in summary_rows.items():
                method_rows = [row for row in run_rows if row.get("method") == method]
                for metric in METRICS:
                    average, sd = mean_sd(row.get(metric) for row in method_rows)
                    stored, stored_sd = numeric(summary.get(metric)), numeric(summary.get(metric.replace("mean_", "std_", 1)))
                    if average is None or stored is None or abs(average - stored) > 1e-12 or (sd is not None and stored_sd is not None and abs(sd - stored_sd) > 1e-12):
                        mismatches.append(f"{method}/{metric}")
            severity(checks, "ERROR" if mismatches else "INFO", "Eval6 Full mean/SD recomputation", f"{name}: mismatches={mismatches}")
        strict = paths["eval6_strict"]
        if strict:
            base = strict[0].parent
            summary_rows = {row["method"]: row for row in read_csv(base / "evaluation6_strict_ablation_summary.csv")}
            run_rows = read_csv(base / "evaluation6_strict_ablation_by_run.csv")
            mismatches = []
            for method, summary in summary_rows.items():
                method_rows = [row for row in run_rows if row.get("method") == method]
                for metric in METRICS:
                    average, sd = mean_sd(row.get(metric) for row in method_rows)
                    stored, stored_sd = numeric(summary.get(metric)), numeric(summary.get(metric.replace("mean_", "std_", 1)))
                    if average is None or stored is None or abs(average - stored) > 1e-12 or (sd is not None and stored_sd is not None and abs(sd - stored_sd) > 1e-12):
                        mismatches.append(f"{method}/{metric}")
            severity(checks, "ERROR" if mismatches else "INFO", "Eval6 Strict mean/SD recomputation", f"{name}: mismatches={mismatches}")
        eval10 = paths["eval10"]
        if eval10:
            payload = load_json(eval10[0])
            summary = payload.get("summary", [{}])[0]
            raw = payload.get("run_summary", [])
            mismatches = []
            for metric in ("pattern_count", "supported_pattern_count", "test_supported_pattern_fraction", "mean_test_day_recurrence", "train_occurrences_total", "test_occurrences_total", "test_transition_coverage"):
                average, sd = mean_sd(row.get(metric) for row in raw if row.get("status") == "complete")
                stored, stored_sd = numeric(summary.get(f"{metric}_mean")), numeric(summary.get(f"{metric}_sd"))
                if average is None or stored is None or abs(average - stored) > 1e-12 or (sd is not None and stored_sd is not None and abs(sd - stored_sd) > 1e-12):
                    mismatches.append(metric)
            severity(checks, "ERROR" if mismatches else "INFO", "Eval10 mean/SD recomputation", f"{name}: mismatches={mismatches}")

    # Bounds, duplicates, all-zero and N/A observations on actual run tables.
    bounded = ("precision", "recall", "f1", "jaccard", "mean_multilabel_precision", "mean_multilabel_recall", "mean_multilabel_f1", "mean_jaccard", "mean_exact_set_match", "future_recurrence_rate", "test_supported_pattern_fraction")
    for name, rows in all_rows.items():
        invalid = []
        for row in rows:
            for field in bounded:
                value = numeric(row.get(field))
                if value is not None and not 0 <= value <= 1:
                    invalid.append(f"{field}={value}")
        severity(checks, "ERROR" if invalid else "INFO", "metric range", f"{name}: invalid={invalid[:10]}")
    for row in all_rows.get("eval10_runs", []):
        extracted, recurrent = numeric(row.get("pattern_count")), numeric(row.get("supported_pattern_count"))
        if extracted is not None and recurrent is not None and recurrent > extracted:
            severity(checks, "ERROR", "Eval10 recurrent <= extracted", f"{row['model']} run={row['run']}: {recurrent}>{extracted}")
    # Eval9 fragmentation keeps N/A separately in raw rows.
    for name, paths in artifacts.items():
        rows = [row for row in all_rows.get("eval9", []) if row["model"] == name and row.get("method") == "llm"]
        statuses = sorted(set(row.get("fragmentation_status", "") for row in rows))
        severity(checks, "WARNING" if "" in statuses else "INFO", "Eval9 fragmentation N/A retention", f"{name}: statuses={statuses}")
        duplicate = []
        groups: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
        for row in rows:
            if row.get("method") == "llm":
                groups[(row.get("experiment", ""), row.get("train_days", ""), row.get("condition", ""), row.get("seed", ""))].append(row.get("run_id", ""))
        for key, run_ids in groups.items():
            if len(run_ids) != len(set(run_ids)):
                duplicate.append(str(key))
        severity(checks, "ERROR" if duplicate else "INFO", "Eval9 duplicate condition/seed/run records", f"{name}: duplicates={duplicate}")
    return checks


def markdown_table(rows: list[dict[str, Any]], columns: list[str], limit: int | None = None) -> str:
    shown = rows[:limit] if limit else rows
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for row in shown:
        values = []
        for key in columns:
            value = row.get(key, "")
            if isinstance(value, float):
                value = f"{value:.6f}"
            values.append(str(value).replace("|", "\\|"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def figures(base: Path, strict: list[dict[str, Any]], eval7: list[dict[str, Any]], eval9: list[dict[str, Any]], time_bands: list[dict[str, Any]]) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    figure_dir = base / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    created = []
    # Eval6 strict proposed vs LLM-only.
    fig, ax = plt.subplots(figsize=(8, 4.5))
    labels = [f"{row['model']}\n{row['method']}" for row in strict]
    vals = [numeric(row.get("mean_multilabel_f1")) or 0 for row in strict]
    errs = [numeric(row.get("std_multilabel_f1")) or 0 for row in strict]
    ax.bar(labels, vals, yerr=errs, capsize=3)
    ax.set_ylim(0, 1); ax.set_ylabel("F1 (mean ± SD)"); ax.set_title("Evaluation 6 Strict")
    fig.tight_layout(); path = figure_dir / "eval6_strict_f1.png"; fig.savefig(path, dpi=160); plt.close(fig); created.append(path.name)
    # Eval7 sensitivity only if present.
    if eval7:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for model in sorted({row["model"] for row in eval7}):
            rows = [row for row in eval7 if row["model"] == model]
            ax.scatter([float(row["n_states"]) for row in rows], [numeric(row.get("mean_multilabel_f1")) or 0 for row in rows], label=model)
        ax.set_ylim(0, 1); ax.set_xlabel("K"); ax.set_ylabel("Validation F1"); ax.legend(); ax.set_title("Evaluation 7 sensitivity")
        fig.tight_layout(); path = figure_dir / "eval7_sensitivity.png"; fig.savefig(path, dpi=160); plt.close(fig); created.append(path.name)
    # Eval9 matched duration experiment by condition.
    duration = [row for row in eval9 if row.get("experiment") == "duration"]
    if duration:
        fig, ax = plt.subplots(figsize=(11, 5))
        conditions = sorted({row["condition"] for row in duration})
        models = sorted({row["model"] for row in duration})
        width = 0.38
        for index, model in enumerate(models):
            vals = []
            for condition in conditions:
                values = [numeric(row.get("f1")) for row in duration if row["model"] == model and row["condition"] == condition and row.get("method") == "llm" and row.get("complete") == "1"]
                vals.append(mean_sd(values)[0] or 0)
            ax.bar([item + (index - .5) * width for item in range(len(conditions))], vals, width, label=model)
        ax.set_ylim(0, 1); ax.set_xticks(range(len(conditions)), conditions, rotation=35, ha="right"); ax.set_ylabel("F1"); ax.legend(); ax.set_title("Evaluation 9 duration sensitivity")
        fig.tight_layout(); path = figure_dir / "eval9_duration_f1.png"; fig.savefig(path, dpi=160); plt.close(fig); created.append(path.name)
    if time_bands:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        groups = sorted({row.get("group") for row in time_bands})
        models = sorted({row["model"] for row in time_bands})
        width = .38
        for index, model in enumerate(models):
            vals = [mean_sd(row.get("future_recurrence_rate") for row in time_bands if row["model"] == model and row.get("group") == group)[0] or 0 for group in groups]
            ax.bar([item + (index - .5) * width for item in range(len(groups))], vals, width, label=model)
        ax.set_ylim(0, 1); ax.set_xticks(range(len(groups)), groups); ax.set_ylabel("FRR"); ax.legend(); ax.set_title("Evaluation 10 by time band")
        fig.tight_layout(); path = figure_dir / "eval10_time_band_frr.png"; fig.savefig(path, dpi=160); plt.close(fig); created.append(path.name)
    return created


def main() -> None:
    models = model_roots()
    artifacts = {name: discover_evaluations(data["root"]) for name, data in models.items()}
    snapshot_manifests = {name: hardlink_snapshot(name, artifacts[name], data) for name, data in models.items()}
    comparison = COMPARISON_ROOT / "gpt-5.6-sol_vs_claude-fable-5"
    tables = comparison / "tables"
    tables.mkdir(parents=True, exist_ok=True)

    e5: list[dict[str, Any]] = []; e6: list[dict[str, Any]] = []; strict: list[dict[str, Any]] = []; strict_runs: list[dict[str, Any]] = []; e7: list[dict[str, Any]] = []; e8: list[dict[str, Any]] = []; e9: list[dict[str, Any]] = []; e10runs: list[dict[str, Any]] = []; bands: list[dict[str, Any]] = []; lengths: list[dict[str, Any]] = []
    for name, paths in artifacts.items():
        if paths["eval5"][0].is_file(): e5 += eval5_rows(paths["eval5"][0], name)
        if paths["eval6_full"][0].is_file(): e6 += summary_rows_from_eval6(paths["eval6_full"][0], name)
        for path in paths["eval6_strict"]:
            a, b = strict_rows(path, name); strict += a; strict_runs += b
        if paths["eval7"][0].is_file(): e7 += eval7_rows(paths["eval7"][0], name)
        for path in paths["eval8_fixed"] + paths["eval8_tertile"]:
            if path.is_file(): e8 += eval8_rows(path, name)
        e9 += eval9_rows(paths["eval9"], name)
        for path in paths["eval10"]:
            a, b, c = eval10_rows(path, name); e10runs += a; bands += b; lengths += c

    e9agg = aggregate_eval9(e9); e10agg = aggregate_eval10(e10runs, "method"); bandagg = aggregate_eval10(bands, "group"); lengthagg = aggregate_eval10(lengths, "group")
    strict_delta: list[dict[str, Any]] = []
    for name, paths in artifacts.items():
        for path in paths["eval6_strict"]:
            paired = read_csv(path.parent / "evaluation6_strict_ablation_paired_f1.csv")
            avg, sd = mean_sd(row.get("proposed_minus_llm_only_multilabel_f1") for row in paired)
            strict_delta.append({"model": name, "paired_runs": len(paired), "mean_paired_delta_f1": avg, "sd_paired_delta_f1": sd})
    outputs = {
        "table_model_comparison_eval5.csv": e5,
        "table_model_comparison_eval6_full.csv": e6,
        "table_model_comparison_eval6_strict.csv": strict,
        "table_model_comparison_eval6_strict_by_run.csv": strict_runs,
        "table_model_comparison_eval7.csv": e7,
        "table_model_comparison_eval8.csv": e8,
        "table_model_comparison_eval9.csv": e9agg,
        "table_model_comparison_eval9_runs.csv": e9,
        "table_model_comparison_eval10.csv": e10agg,
        "table_model_comparison_eval10_by_run.csv": e10runs,
        "table_model_comparison_eval10_time_band.csv": bandagg,
        "table_model_comparison_eval10_length.csv": lengthagg,
    }
    for filename, rows in outputs.items():
        write_csv(tables / filename, rows)
        columns = list(dict.fromkeys(key for row in rows for key in row))
        (tables / f"{Path(filename).stem}.md").write_text(
            f"# {Path(filename).stem}\n\n" + markdown_table(rows, columns) + "\n",
            encoding="utf-8",
        )
    overview = []
    for row in e6 + strict:
        overview.append({"evaluation": "Eval6 Full" if row in e6 else "Eval6 Strict", "model": row["model"], "method": row["method"], "F1_mean": row.get("mean_multilabel_f1"), "F1_sd": row.get("std_multilabel_f1")})
    for row in e9agg:
        overview.append({"evaluation": "Eval9", "model": row["model"], "method": row["condition"], "F1_mean": row.get("f1_mean"), "F1_sd": row.get("f1_sd")})
    for row in e10agg:
        overview.append({"evaluation": "Eval10", "model": row["model"], "method": row["method"], "FRR_mean": row.get("mean_test_day_recurrence_mean"), "FRR_sd": row.get("mean_test_day_recurrence_sd")})
    write_csv(tables / "table_model_comparison_overview.csv", overview)
    write_csv(tables / "table_model_comparison_eval6_strict_delta_f1.csv", strict_delta)
    (tables / "table_model_comparison_overview.md").write_text(
        "# table_model_comparison_overview\n\n" + markdown_table(overview, list(dict.fromkeys(key for row in overview for key in row))) + "\n",
        encoding="utf-8",
    )
    (tables / "table_model_comparison_eval6_strict_delta_f1.md").write_text(
        "# table_model_comparison_eval6_strict_delta_f1\n\n" + markdown_table(strict_delta, list(dict.fromkeys(key for row in strict_delta for key in row))) + "\n",
        encoding="utf-8",
    )

    all_rows = {"eval6_full": e6, "eval6_strict": strict_runs, "eval7": e7, "eval8": e8, "eval9": e9, "eval10_runs": e10runs}
    checks = audit(models, artifacts, all_rows)
    write_json(comparison / "sanity_check" / "sanity_check_report.json", {"checks": checks})
    (comparison / "sanity_check" / "sanity_check_report.md").write_text("# Sanity check\n\n" + markdown_table(checks, ["severity", "check", "evidence"]) + "\n", encoding="utf-8")
    # Comparability is evidence-driven; a missing Eval7 prevents identical K/h provenance for Fable.
    comparable = [
        {"item": "model identity", "gpt-5.6-sol": models["gpt-5.6-sol"]["identity"].get("model_id"), "claude-fable-5": models["claude-fable-5"]["identity"].get("model_id"), "comparable": "Different models by design"},
        {"item": "Eval6 Full/Strict source representation", "gpt-5.6-sol": "individual, K=10 h=2", "claude-fable-5": "individual, K=10 h=2", "comparable": "Matched condition"},
        {"item": "Eval7 formal search", "gpt-5.6-sol": "28 conditions x 5 runs present", "claude-fable-5": "formal summary absent", "comparable": "No"},
        {"item": "Eval9 duration", "gpt-5.6-sol": "duration summary present", "claude-fable-5": "duration summary present", "comparable": "Matched condition rows only"},
        {"item": "Eval10 K/h provenance", "gpt-5.6-sol": "own Eval7 best manifest", "claude-fable-5": "artifact metadata required GPT Eval7 manifest", "comparable": "Condition matched; not per-model optimized"},
    ]
    write_csv(comparison / "comparison" / "comparability_audit.csv", comparable)
    (comparison / "comparison" / "comparability_audit.md").parent.mkdir(parents=True, exist_ok=True)
    (comparison / "comparison" / "comparability_audit.md").write_text("# Cross-model comparability\n\n" + markdown_table(comparable, ["item", "gpt-5.6-sol", "claude-fable-5", "comparable"]) + "\n", encoding="utf-8")
    reviewer_mapping = [
        {"reviewer_concern": "Strict ablation", "evidence": "Eval6 strict paired run CSV and fixed-contract manifest", "gpt-5.6-sol": "complete (5 paired runs)", "claude-fable-5": "complete (5 paired runs)"},
        {"reviewer_concern": "Parameter dependency", "evidence": "Eval7 formal condition summary", "gpt-5.6-sol": "complete (28 conditions x 5 runs)", "claude-fable-5": "pending: formal artifact absent"},
        {"reviewer_concern": "Generalization / robustness", "evidence": "Eval9 condition/seed summaries", "gpt-5.6-sol": "duration experiment available", "claude-fable-5": "full and duration experiments available"},
        {"reviewer_concern": "Real-home temporal generalization", "evidence": "Eval10 chronological 70/30 summary", "gpt-5.6-sol": "complete (5 runs)", "claude-fable-5": "complete (5 runs)"},
        {"reviewer_concern": "Fragmentation", "evidence": "Eval5 and Eval9 fragmentation fields", "gpt-5.6-sol": "available", "claude-fable-5": "available"},
        {"reviewer_concern": "Explanation validation", "evidence": "Human Evaluation artifact", "gpt-5.6-sol": "pending", "claude-fable-5": "pending"},
    ]
    write_csv(comparison / "comparison" / "reviewer_mapping.csv", reviewer_mapping)
    (comparison / "comparison" / "reviewer_mapping.md").write_text("# Reviewer-concern mapping\n\n" + markdown_table(reviewer_mapping, ["reviewer_concern", "evidence", "gpt-5.6-sol", "claude-fable-5"]) + "\n", encoding="utf-8")
    figure_names = figures(comparison, strict, e7, e9, bands)
    if not figure_names:
        severity(checks, "WARNING", "figures", "No matplotlib-capable local runtime was available; source CSV tables were written, no API call was attempted.")
        write_json(comparison / "sanity_check" / "sanity_check_report.json", {"checks": checks})
        (comparison / "sanity_check" / "sanity_check_report.md").write_text("# Sanity check\n\n" + markdown_table(checks, ["severity", "check", "evidence"]) + "\n", encoding="utf-8")
    summary = {"models": {name: {"identity": data["identity"], "result_path": rel(data["root"])} for name, data in models.items()}, "snapshot_manifests": {name: rel(SNAPSHOT_ROOT / name / "snapshot_manifest.json") for name in models}, "tables": sorted(outputs), "figures": figure_names, "sanity_check": rel(comparison / "sanity_check" / "sanity_check_report.json"), "comparability": rel(comparison / "comparison" / "comparability_audit.csv")}
    write_json(comparison / "comparison" / "model_comparison_summary.json", summary)
    md = ["# GPT-5.6 Sol vs Claude Fable 5: artifact-only comparison", "", "This report was generated from existing manifests, summaries, run CSVs, and scorer metadata. No model/API call or pattern generation was performed.", "", "## Evaluation 6 Full", "", markdown_table(e6, ["model", "method", "mean_multilabel_precision", "mean_multilabel_recall", "mean_multilabel_f1", "mean_jaccard", "mean_exact_set_match"]), "", "## Evaluation 6 Strict", "", markdown_table(strict, ["model", "method", "mean_multilabel_precision", "mean_multilabel_recall", "mean_multilabel_f1", "mean_jaccard", "mean_exact_set_match"]), "", "### Paired Delta F1", "", markdown_table(strict_delta, ["model", "paired_runs", "mean_paired_delta_f1", "sd_paired_delta_f1"]), "", "## Evaluation 9 (condition × duration mean ± SD source table)", "", markdown_table(e9agg, ["model", "experiment", "train_days", "test_days", "condition", "f1_mean", "f1_sd", "jaccard_mean", "test_target_episode_coverage_mean", "fragmentation_rate_mean"]), "", "## Evaluation 10", "", markdown_table(e10agg, ["model", "method", "pattern_count_mean", "supported_pattern_count_mean", "test_supported_pattern_fraction_mean", "mean_test_day_recurrence_mean"]), "", "## Completeness caveat", "", "Claude Fable 5 has no discovered formal Evaluation 7 summary. It is therefore not complete for Evaluation 5--10 and its model-specific parameter-selection comparison cannot be claimed."]
    (comparison / "comparison" / "model_comparison_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"comparison": str(comparison), "figures": figure_names, "checks": len(checks)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
