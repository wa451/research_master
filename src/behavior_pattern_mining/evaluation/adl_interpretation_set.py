"""Set-based evaluation of LLM ADL interpretation labels."""

from __future__ import annotations

import ast
import csv
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from src.behavior_pattern_mining.evaluation.adl import (
    ADLInterval,
    adl_category_set_for_label,
    interval_overlap_seconds,
    lookup_adl_category_set,
    parse_timestamp,
    sequence_text,
)


ALLOWED_LABELS = [
    "Sleep",
    "Wake-up",
    "Meal",
    "Relax",
    "Outing",
    "Hygiene",
    "Housework",
    "Other",
    "Noise",
    "Ambiguous",
]

ALLOWED_LABEL_SET = set(ALLOWED_LABELS)

LABEL_ALIASES = {
    "sleep": "Sleep",
    "sleeping": "Sleep",
    "bed": "Sleep",
    "wake-up": "Wake-up",
    "wakeup": "Wake-up",
    "wake_up": "Wake-up",
    "wake up": "Wake-up",
    "morning routine": "Wake-up",
    "meal": "Meal",
    "meal preparation": "Meal",
    "meal_preparation": "Meal",
    "cooking": "Meal",
    "eating": "Meal",
    "wash dishes": "Meal",
    "wash_dishes": "Meal",
    "relax": "Relax",
    "rest": "Relax",
    "resting": "Relax",
    "leisure": "Relax",
    "outing": "Outing",
    "leave home": "Outing",
    "leave_home": "Outing",
    "enter home": "Outing",
    "enter_home": "Outing",
    "outside": "Outing",
    "hygiene": "Hygiene",
    "bathroom": "Hygiene",
    "toilet": "Hygiene",
    "toileting": "Hygiene",
    "personal hygiene": "Hygiene",
    "personal_hygiene": "Hygiene",
    "bath": "Hygiene",
    "bathing": "Hygiene",
    "housework": "Housework",
    "cleaning": "Housework",
    "housekeeping": "Housework",
    "laundry": "Housework",
    "other": "Other",
    "other_adl": "Other",
    "noise": "Noise",
    "noisy": "Noise",
    "ambiguous": "Ambiguous",
    "unclear": "Ambiguous",
    "unknown": "Ambiguous",
    "unmapped": "Ambiguous",
}


@dataclass(frozen=True)
class InterpretationPattern:
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]
    pred_adl_labels: tuple[str, ...]
    group_pattern_id: str = ""
    time_band: str = "All"


@dataclass(frozen=True)
class PatternOccurrenceInterval:
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]
    start_time: Any
    end_time: Any
    time_band: str = "All"


def normalize_adl_label(value: Any, unknown_label: str = "Other") -> str:
    text = str(value).strip()
    if not text:
        return unknown_label
    if text in ALLOWED_LABEL_SET:
        return text

    key = (
        text.replace("-", " ")
        .replace("_", " ")
        .replace("/", " ")
        .strip()
        .lower()
    )
    canonical = LABEL_ALIASES.get(key)
    if canonical:
        return canonical

    compact_key = key.replace(" ", "_")
    canonical = LABEL_ALIASES.get(compact_key)
    if canonical:
        return canonical
    return unknown_label


def normalize_adl_label_set_value(value: Any, unknown_label: str = "Other") -> tuple[str, ...]:
    """Normalize one raw label-like value to one or more evaluation-6 labels."""
    text = str(value).strip()
    if not text:
        return (unknown_label,)
    if text in ALLOWED_LABEL_SET:
        return (text,)

    if lookup_adl_category_set(text):
        return tuple(
            label for label in adl_category_set_for_label(text)
            if label in ALLOWED_LABEL_SET
        ) or (unknown_label,)

    return (normalize_adl_label(text, unknown_label=unknown_label),)


def parse_label_values(raw_value: Any) -> list[Any]:
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        return raw_value
    if isinstance(raw_value, tuple):
        return list(raw_value)
    if not isinstance(raw_value, str):
        return [raw_value]

    text = raw_value.strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(text)
            except (ValueError, SyntaxError, json.JSONDecodeError):
                continue
            return parse_label_values(parsed)

    for delimiter in (";", "|", ",", "、", "/"):
        if delimiter in text:
            return [part.strip() for part in text.split(delimiter) if part.strip()]
    return [text]


def normalize_label_set(
    raw_value: Any,
    missing_label: str = "Ambiguous",
    unknown_label: str = "Other",
) -> tuple[str, ...]:
    values = parse_label_values(raw_value)
    if not values:
        return (missing_label,)

    normalized = []
    seen = set()
    for value in values:
        for label in normalize_adl_label_set_value(value, unknown_label=unknown_label):
            if label in seen:
                continue
            seen.add(label)
            normalized.append(label)
    return tuple(sorted(normalized)) if normalized else (missing_label,)


def parse_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if not isinstance(value, str):
        return ()

    text = value.strip()
    if not text:
        return ()
    if text.startswith("[") and text.endswith("]"):
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(text)
            except (ValueError, SyntaxError, json.JSONDecodeError):
                continue
            sequence = parse_sequence(parsed)
            if sequence:
                return sequence
    for delimiter in ("->", "→", "|", ","):
        if delimiter in text:
            return tuple(part.strip() for part in text.split(delimiter) if part.strip())
    return (text,)


def time_band_for_timestamp(timestamp: Any) -> str:
    hour = timestamp.hour
    if 6 <= hour < 10:
        return "Morning"
    if 10 <= hour < 18:
        return "Daytime"
    if 18 <= hour < 24:
        return "Night"
    return "Midnight"


def _flat_interpretation_pattern(
    item: dict[str, Any],
    index: int,
    missing_label: str,
    unknown_label: str,
    pattern_id: str | None = None,
    group_pattern_id: str | None = None,
    time_band: str = "All",
    fallback_sequence: tuple[str, ...] | None = None,
) -> InterpretationPattern | None:
    sequence = parse_sequence(
        item.get("遷移のパターン")
        or item.get("遷移のシーケンス")
        or item.get("sequence")
        or item.get("states")
        or item.get("系列")
    )
    if not sequence and fallback_sequence:
        sequence = fallback_sequence
    if len(sequence) < 2:
        return None
    resolved_pattern_id = str(pattern_id or item.get("pattern_id") or item.get("id") or f"P{index}").strip()
    resolved_group_pattern_id = str(group_pattern_id or resolved_pattern_id).strip()
    pattern_name = str(
        item.get("パターン名")
        or item.get("pattern_name")
        or item.get("name")
        or resolved_pattern_id
    )
    adl_labels = normalize_label_set(
        item.get("ADL系列ラベル")
        or item.get("adl_sequence_labels")
        or item.get("adl_labels")
        or item.get("ADLラベル"),
        missing_label=missing_label,
        unknown_label=unknown_label,
    )
    return InterpretationPattern(
        pattern_id=resolved_pattern_id,
        group_pattern_id=resolved_group_pattern_id,
        pattern_name=pattern_name,
        sequence=sequence,
        pred_adl_labels=adl_labels,
        time_band=time_band,
    )


def load_interpretation_patterns(
    path: Path,
    missing_label: str = "Ambiguous",
    unknown_label: str = "Other",
) -> list[InterpretationPattern]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as f:
            payload: Any = list(csv.DictReader(f))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = (
                payload.get("patterns")
                or payload.get("sequences")
                or payload.get("results")
                or payload.get("items")
                or []
            )
    if not isinstance(payload, list):
        raise ValueError(f"Pattern file must be list-like: {path}")

    patterns = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        interpretations = item.get("time_band_interpretations")
        if isinstance(interpretations, dict):
            group_pattern_id = str(item.get("pattern_id") or item.get("id") or f"P{index:03d}").strip()
            group_sequence = parse_sequence(
                item.get("sequence")
                or item.get("遷移のパターン")
                or item.get("遷移のシーケンス")
            )
            for time_band, interpretation in interpretations.items():
                if not isinstance(interpretation, dict):
                    continue
                pattern = _flat_interpretation_pattern(
                    interpretation,
                    index,
                    missing_label=missing_label,
                    unknown_label=unknown_label,
                    pattern_id=f"{group_pattern_id}_{time_band}",
                    group_pattern_id=group_pattern_id,
                    time_band=str(time_band),
                    fallback_sequence=group_sequence,
                )
                if pattern is not None:
                    patterns.append(pattern)
            continue

        pattern = _flat_interpretation_pattern(
            item,
            index,
            missing_label=missing_label,
            unknown_label=unknown_label,
        )
        if pattern is not None:
            patterns.append(pattern)
    return patterns


def load_pattern_occurrences(path: Path, occurrence_method: str | None = None) -> list[PatternOccurrenceInterval]:
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    occurrences = []
    for row in rows:
        if occurrence_method and row.get("method") and row.get("method") != occurrence_method:
            continue
        pattern_id = row.get("pattern_id") or row.get("id")
        if not pattern_id:
            continue
        start_text = row.get("start_time") or row.get("start")
        end_text = row.get("end_time") or row.get("end")
        if not start_text or not end_text:
            continue
        occurrences.append(
            PatternOccurrenceInterval(
                pattern_id=pattern_id.strip(),
                pattern_name=(row.get("pattern_name") or "").strip(),
                sequence=parse_sequence(row.get("sequence")),
                start_time=parse_timestamp(start_text),
                end_time=parse_timestamp(end_text),
                time_band=(row.get("time_band") or "").strip() or time_band_for_timestamp(parse_timestamp(start_text)),
            )
        )
    return occurrences


def load_adl_intervals_csv(path: Path) -> list[ADLInterval]:
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    intervals = []
    for row in rows:
        start_text = row.get("start_time") or row.get("start")
        end_text = row.get("end_time") or row.get("end")
        category = row.get("adl_category") or row.get("category") or row.get("raw_label")
        if not start_text or not end_text or not category:
            continue
        intervals.append(
            ADLInterval(
                start_time=parse_timestamp(start_text),
                end_time=parse_timestamp(end_text),
                raw_label=row.get("raw_label") or category,
                adl_category=normalize_adl_label(category, unknown_label="Other"),
            )
        )
    return intervals


def overlap_by_pattern_and_label(
    patterns: Sequence[InterpretationPattern],
    occurrences: Sequence[PatternOccurrenceInterval],
    adl_intervals: Sequence[ADLInterval],
) -> dict[str, dict[str, float]]:
    occurrences_by_pattern: dict[str, list[PatternOccurrenceInterval]] = defaultdict(list)
    for pattern in patterns:
        group_pattern_id = pattern.group_pattern_id or pattern.pattern_id
        for occurrence in occurrences:
            id_matches = occurrence.pattern_id in {pattern.pattern_id, group_pattern_id}
            sequence_matches = bool(occurrence.sequence) and occurrence.sequence == pattern.sequence
            if not (id_matches or sequence_matches):
                continue
            if pattern.time_band != "All" and time_band_for_timestamp(occurrence.start_time) != pattern.time_band:
                continue
            occurrences_by_pattern[pattern.pattern_id].append(occurrence)

    labels = sorted(adl_intervals, key=lambda item: item.start_time)
    overlaps: dict[str, dict[str, float]] = {}
    for pattern in patterns:
        label_seconds: dict[str, float] = defaultdict(float)
        label_cursor = 0
        for occurrence in sorted(occurrences_by_pattern.get(pattern.pattern_id, []), key=lambda item: item.start_time):
            while label_cursor < len(labels) and labels[label_cursor].end_time <= occurrence.start_time:
                label_cursor += 1
            for label in labels[label_cursor:]:
                if label.start_time >= occurrence.end_time:
                    break
                overlap = interval_overlap_seconds(
                    occurrence.start_time,
                    occurrence.end_time,
                    label.start_time,
                    label.end_time,
                )
                if overlap > 0:
                    for category in adl_category_set_for_label(label.raw_label, label.adl_category):
                        normalized_category = normalize_adl_label(category, unknown_label="Other")
                        if normalized_category in ALLOWED_LABEL_SET:
                            label_seconds[normalized_category] += overlap
        overlaps[pattern.pattern_id] = dict(sorted(label_seconds.items()))
    return overlaps


def relevant_occurrences_for_pattern(
    pattern: InterpretationPattern,
    occurrences: Sequence[PatternOccurrenceInterval],
) -> list[PatternOccurrenceInterval]:
    """Return the representative-state occurrences used by one evaluation record.

    For proposed patterns, ``sequence × time_band`` is the evaluation unit.
    Thus an identical sequence in another time band is deliberately excluded
    from both overlap calculation and ``num_occurrences``.
    """
    group_pattern_id = pattern.group_pattern_id or pattern.pattern_id
    relevant = []
    for occurrence in occurrences:
        id_matches = occurrence.pattern_id in {pattern.pattern_id, group_pattern_id}
        sequence_matches = bool(occurrence.sequence) and occurrence.sequence == pattern.sequence
        if not (id_matches or sequence_matches):
            continue
        if pattern.time_band != "All" and time_band_for_timestamp(occurrence.start_time) != pattern.time_band:
            continue
        relevant.append(occurrence)
    return relevant


def true_label_set_from_overlap(
    overlap_seconds_by_label: dict[str, float],
    min_overlap_ratio: float,
    no_overlap_label: str = "Ambiguous",
) -> tuple[tuple[str, ...], float]:
    total = sum(overlap_seconds_by_label.values())
    if total <= 0:
        return (no_overlap_label,), 0.0

    labels = [
        label
        for label, seconds in sorted(overlap_seconds_by_label.items())
        if seconds / total >= min_overlap_ratio
    ]
    return tuple(labels) if labels else (no_overlap_label,), total


def set_metrics(pred_labels: Sequence[str], true_labels: Sequence[str]) -> dict[str, float | int | tuple[str, ...]]:
    pred_set = set(pred_labels)
    true_set = set(true_labels)
    intersection = pred_set & true_set
    union = pred_set | true_set
    precision = len(intersection) / len(pred_set) if pred_set else 0.0
    recall = len(intersection) / len(true_set) if true_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "intersection_labels": tuple(sorted(intersection)),
        "union_labels": tuple(sorted(union)),
        "exact_set_match": int(pred_set == true_set),
        "jaccard": len(intersection) / len(union) if union else 0.0,
        "multilabel_precision": precision,
        "multilabel_recall": recall,
        "multilabel_f1": f1,
    }


def evaluate_interpretation_sets(
    patterns: Sequence[InterpretationPattern],
    occurrences: Sequence[PatternOccurrenceInterval],
    adl_intervals: Sequence[ADLInterval],
    min_overlap_ratio_for_true_label: float,
    no_overlap_label: str = "Ambiguous",
) -> tuple[list[dict], dict]:
    overlaps = overlap_by_pattern_and_label(patterns, occurrences, adl_intervals)
    detail_rows = []
    for pattern in patterns:
        overlap_detail = overlaps.get(pattern.pattern_id, {})
        true_labels, total_overlap = true_label_set_from_overlap(
            overlap_detail,
            min_overlap_ratio=min_overlap_ratio_for_true_label,
            no_overlap_label=no_overlap_label,
        )
        metrics = set_metrics(pattern.pred_adl_labels, true_labels)
        detail_rows.append(
            {
                "pattern_id": pattern.pattern_id,
                "eval_pattern_id": pattern.pattern_id,
                "group_pattern_id": pattern.group_pattern_id or pattern.pattern_id,
                "time_band": pattern.time_band,
                "pattern_name": pattern.pattern_name,
                "sequence": sequence_text(pattern.sequence),
                "num_occurrences": len(relevant_occurrences_for_pattern(pattern, occurrences)),
                "pred_adl_labels": labels_text(pattern.pred_adl_labels),
                "true_adl_labels": labels_text(true_labels),
                "intersection_labels": labels_text(metrics["intersection_labels"]),
                "union_labels": labels_text(metrics["union_labels"]),
                "exact_set_match": metrics["exact_set_match"],
                "jaccard": metrics["jaccard"],
                "multilabel_precision": metrics["multilabel_precision"],
                "multilabel_recall": metrics["multilabel_recall"],
                "multilabel_f1": metrics["multilabel_f1"],
                "total_overlap_seconds": total_overlap,
                "true_label_overlap_detail": json.dumps(overlap_detail, ensure_ascii=False, sort_keys=True),
            }
        )
    return detail_rows, summary_from_details(detail_rows)


def labels_text(labels: Sequence[str]) -> str:
    return ";".join(labels)


def mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def summary_from_details(detail_rows: Sequence[dict]) -> dict:
    return {
        "num_patterns": len(detail_rows),
        "mean_exact_set_match": mean([float(row["exact_set_match"]) for row in detail_rows]),
        "mean_jaccard": mean([float(row["jaccard"]) for row in detail_rows]),
        "mean_multilabel_precision": mean([float(row["multilabel_precision"]) for row in detail_rows]),
        "mean_multilabel_recall": mean([float(row["multilabel_recall"]) for row in detail_rows]),
        "mean_multilabel_f1": mean([float(row["multilabel_f1"]) for row in detail_rows]),
    }


def aggregate_by_time_band(detail_rows: Sequence[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in detail_rows:
        grouped[str(row.get("time_band") or "All")].append(row)
    return [
        {
            "time_band": time_band,
            "num_patterns": len(rows),
            "mean_exact_set_match": mean([float(row["exact_set_match"]) for row in rows]),
            "mean_jaccard": mean([float(row["jaccard"]) for row in rows]),
            "mean_multilabel_precision": mean([float(row["multilabel_precision"]) for row in rows]),
            "mean_multilabel_recall": mean([float(row["multilabel_recall"]) for row in rows]),
            "mean_multilabel_f1": mean([float(row["multilabel_f1"]) for row in rows]),
        }
        for time_band, rows in sorted(grouped.items())
    ]


def aggregate_by_label(detail_rows: Sequence[dict], label_column: str, output_label_column: str) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in detail_rows:
        labels = [label for label in str(row[label_column]).split(";") if label]
        for label in labels:
            grouped[label].append(row)
    return [
        {
            output_label_column: label,
            "num_patterns": len(rows),
            "mean_jaccard": mean([float(row["jaccard"]) for row in rows]),
            "mean_multilabel_precision": mean([float(row["multilabel_precision"]) for row in rows]),
            "mean_multilabel_recall": mean([float(row["multilabel_recall"]) for row in rows]),
            "mean_multilabel_f1": mean([float(row["multilabel_f1"]) for row in rows]),
        }
        for label, rows in sorted(grouped.items())
    ]
