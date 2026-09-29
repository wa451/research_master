"""Read-only reviewer-response aggregation for evaluations 5--10.

This module deliberately consumes already generated artifacts.  It never calls an
LLM and it refuses to reuse an existing reviewer-response output directory.
"""

from __future__ import annotations

import csv
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from src.behavior_pattern_mining.evaluation.adl_interpretation_set import (
    ALLOWED_LABELS,
    normalize_adl_label,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    values = list(rows)
    if not values:
        path.write_text("", encoding="utf-8")
        return
    keys = list(values[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(values)


def as_number(value: str | float | int | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def mean_sd(values: Iterable[float | None]) -> tuple[float | None, float | None]:
    cleaned = [value for value in values if value is not None and not math.isnan(value)]
    if not cleaned:
        return None, None
    return statistics.mean(cleaned), statistics.stdev(cleaned) if len(cleaned) > 1 else 0.0


def format_mean_sd(mean: float | None, sd: float | None) -> str:
    if mean is None:
        return "N/A"
    return f"{mean:.3f} ± {(sd or 0.0):.3f}"


def normalize_time_band(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {"morning": "Morning", "daytime": "Daytime", "night": "Night", "midnight": "Midnight"}
    return aliases.get(text, str(value or "All").strip() or "All")


def normalize_sequence(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.replace("->", ",").split(",") if part.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(part).strip() for part in value if str(part).strip())
    return ()


def pattern_identity(time_band: Any, sequence: Any) -> tuple[str, tuple[str, ...]]:
    return normalize_time_band(time_band), normalize_sequence(sequence)


def strict_common_run_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    """Return strict-ablation run pairs, refusing unpaired runs."""
    by_run: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        if row.get("method") in {"proposed_strict", "llm_only_strict"}:
            by_run[row["run"]][row["method"]] = row
    paired: list[dict[str, Any]] = []
    for run in sorted(by_run, key=int):
        pair = by_run[run]
        if set(pair) != {"proposed_strict", "llm_only_strict"}:
            continue
        proposed, direct = pair["proposed_strict"], pair["llm_only_strict"]
        result: dict[str, Any] = {"run": int(run)}
        for output, source in (("proposed", proposed), ("llm_only", direct)):
            for name, column in (("precision", "mean_multilabel_precision"), ("recall", "mean_multilabel_recall"), ("f1", "mean_multilabel_f1"), ("jaccard", "mean_jaccard"), ("exact", "mean_exact_set_match")):
                result[f"{output}_{name}"] = as_number(source.get(column))
        result["delta_f1"] = result["proposed_f1"] - result["llm_only_f1"]
        paired.append(result)
    return paired


def reviewer_eval5_rows(details: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    """Apply the reviewer policy: no comparable pair means N/A, never zero."""
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in details:
        grouped[(row["method"], row["run"])].append(row)
    output: list[dict[str, Any]] = []
    for (method, run), rows in sorted(grouped.items()):
        evaluable = [row for row in rows if row.get("evaluation_status") == "evaluated"]
        comparable = [row for row in evaluable if row.get("fragmentation_candidate_status") == "comparable"]
        fragmented = [row for row in evaluable if row.get("is_fragmented") == "1"]
        rate = len(fragmented) / len(evaluable) if evaluable and comparable else None
        identities: dict[tuple[str, tuple[str, ...]], int] = defaultdict(int)
        for row in rows:
            identities[pattern_identity(row.get("time_band"), row.get("sequence"))] += 1
        duplicate_records = sum(count - 1 for count in identities.values() if count > 1)
        test_supported = sum((as_number(row.get("test_support")) or 0.0) > 0 for row in rows)
        output.append({
            "method": method,
            "run": int(run),
            "pattern_count": len(rows),
            "evaluable_patterns": len(evaluable),
            "train_support_available": all(row.get("train_support") not in (None, "") for row in rows),
            "test_support_available": all(row.get("test_support") not in (None, "") for row in rows),
            "test_supported_patterns": test_supported,
            "test_supported_rate": test_supported / len(rows) if rows else None,
            "time_band_aware_identity": True,
            "redundancy_duplicates": duplicate_records,
            "redundancy_rate": duplicate_records / len(rows) if rows else None,
            "fragmented_patterns": len(fragmented),
            "comparable_pairs": len(comparable),
            "fragmentation_rate": rate,
            "fragmentation_status": "evaluated" if comparable else "N/A",
            "fragmentation_reason": "" if comparable else "no_comparable_pairs",
        })
    return output


def extract_human_pattern(item: dict[str, Any], method: str, run: int, index: int, state_context: dict[str, str]) -> dict[str, Any] | None:
    sequence = normalize_sequence(item.get("state_sequence") or item.get("sequence") or item.get("遷移のパターン"))
    if not sequence:
        return None
    labels = item.get("adl_sequence") or item.get("ADL系列ラベル") or []
    if not isinstance(labels, list):
        labels = [labels]
    canonical = [label for label in (normalize_adl_label(label) for label in labels) if label]
    return {
        "internal_method": method,
        "internal_run": run,
        "internal_index": index,
        "time_band": normalize_time_band(item.get("time_band") or item.get("time_period")),
        "state_sequence": " -> ".join(sequence),
        "sensor_state_context": " | ".join(f"{state}: {state_context.get(state, 'unresolved')}" for state in sequence),
        "pattern_name": item.get("pattern_name") or item.get("パターン名") or "",
        "adl_labels": "; ".join(canonical),
        "rationale": item.get("rationale") or item.get("解釈の根拠") or "",
    }


def load_state_context(path: Path) -> dict[str, str]:
    rows = read_csv(path) if path.suffix == ".csv" else []
    if rows:
        return {row.get("state_id", ""): row.get("active_sensors", "") for row in rows}
    with path.open(encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t")
        table = list(reader)
    if len(table) < 2:
        return {}
    headers = table[0][1:]
    return {row[0]: ", ".join(sensor for sensor, value in zip(headers, row[1:]) if value == "1") for row in table[1:] if row}


def make_blind_sample(records: list[dict[str, Any]], count: int, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministically sample methods/time bands as evenly as availability permits."""
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        key = (record["internal_method"], record["time_band"], record["state_sequence"])
        unique.setdefault(key, record)
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in unique.values():
        buckets[(record["internal_method"], record["time_band"])].append(record)
    rng = random.Random(seed)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    selected: list[dict[str, Any]] = []
    while len(selected) < min(count, len(unique)) and any(buckets.values()):
        for key in sorted(buckets):
            if buckets[key] and len(selected) < count:
                selected.append(buckets[key].pop())
    public, key_rows = [], []
    for number, record in enumerate(selected, start=1):
        anonymous_id = f"HE{number:03d}"
        public.append({key: record[key] for key in ("time_band", "state_sequence", "sensor_state_context", "pattern_name", "adl_labels", "rationale")} | {"anonymous_id": anonymous_id})
        key_rows.append({"anonymous_id": anonymous_id, "method": record["internal_method"], "run": record["internal_run"], "source_index": record["internal_index"]})
    return public, key_rows
