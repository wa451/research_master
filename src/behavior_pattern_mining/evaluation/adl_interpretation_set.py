"""Set-based evaluation of LLM ADL interpretation labels."""

from __future__ import annotations

import ast
import csv
import json
import statistics
import warnings
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Sequence

from src.behavior_pattern_mining.evaluation.adl import (
    ADLInterval,
    adl_category_set_for_label,
    interval_overlap_seconds,
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
    "Toileting",
    "Housework",
    "Work",
    "Other",
]

ALLOWED_LABEL_SET = set(ALLOWED_LABELS)

LABEL_ALIASES = {
    "sleep": "Sleep",
    "wake-up": "Wake-up",
    "wakeup": "Wake-up",
    "wake_up": "Wake-up",
    "wake up": "Wake-up",
    "meal": "Meal",
    "relax": "Relax",
    "outing": "Outing",
    "hygiene": "Hygiene",
    "toileting": "Toileting",
    "housework": "Housework",
    "work": "Work",
    "other": "Other",
}


@dataclass(frozen=True)
class InterpretationPattern:
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]
    pred_adl_labels: tuple[str, ...]
    group_pattern_id: str = ""
    time_band: str = "All"
    raw_pred_adl_labels: tuple[str, ...] = ()
    unknown_pred_adl_labels: tuple[str, ...] = ()
    prediction_status: str = "valid"


@dataclass(frozen=True)
class PatternOccurrenceInterval:
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]
    start_time: Any
    end_time: Any
    time_band: str = "All"


@dataclass(frozen=True)
class PredictionLabelNormalization:
    raw_labels: tuple[str, ...]
    normalized_labels: tuple[str, ...]
    unknown_labels: tuple[str, ...]
    status: str


def normalize_adl_label(value: Any, unknown_label: str | None = None) -> str | None:
    """Return one canonical evaluation label, or ``None`` when it is unknown.

    ``unknown_label`` remains in the signature for source compatibility with
    older callers, but unknown values are never coerced to ``Other``.
    """
    text = str(value).strip()
    if not text:
        return None
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
    return None


def normalize_adl_label_set_value(
    value: Any,
    unknown_label: str | None = None,
) -> tuple[str, ...]:
    """Normalize one LLM prediction only within the allowed 10-label vocabulary."""
    text = str(value).strip()
    if not text:
        return ()
    if text in ALLOWED_LABEL_SET:
        return (text,)

    normalized = normalize_adl_label(text)
    return (normalized,) if normalized else ()


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
    missing_label: str | None = None,
    unknown_label: str | None = None,
) -> tuple[str, ...]:
    """Compatibility wrapper returning only recognized ADL labels."""
    return normalize_prediction_labels(raw_value).normalized_labels


def normalize_prediction_labels(raw_value: Any) -> PredictionLabelNormalization:
    values = parse_label_values(raw_value)
    if not values:
        return PredictionLabelNormalization((), (), (), "missing")

    raw_labels: list[str] = []
    normalized: list[str] = []
    unknown: list[str] = []
    seen_normalized: set[str] = set()
    seen_unknown: set[str] = set()
    for value in values:
        raw_label = str(value).strip()
        if not raw_label:
            continue
        raw_labels.append(raw_label)
        labels = normalize_adl_label_set_value(value)
        if not labels:
            if raw_label not in seen_unknown:
                seen_unknown.add(raw_label)
                unknown.append(raw_label)
            continue
        for label in labels:
            if label in seen_normalized:
                continue
            seen_normalized.add(label)
            normalized.append(label)
    if not raw_labels:
        return PredictionLabelNormalization((), (), (), "missing")
    status = "unknown" if unknown else "valid"
    return PredictionLabelNormalization(
        tuple(raw_labels),
        tuple(sorted(normalized)),
        tuple(unknown),
        status,
    )


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
    label_normalization = normalize_prediction_labels(
        item.get("ADL系列ラベル")
        or item.get("adl_sequence_labels")
        or item.get("adl_labels")
        or item.get("ADLラベル")
    )
    return InterpretationPattern(
        pattern_id=resolved_pattern_id,
        group_pattern_id=resolved_group_pattern_id,
        pattern_name=pattern_name,
        sequence=sequence,
        pred_adl_labels=label_normalization.normalized_labels,
        time_band=time_band,
        raw_pred_adl_labels=label_normalization.raw_labels,
        unknown_pred_adl_labels=label_normalization.unknown_labels,
        prediction_status=label_normalization.status,
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
    unknown_labels = sorted(
        {
            label
            for pattern in patterns
            for label in pattern.unknown_pred_adl_labels
        }
    )
    if unknown_labels:
        unknown_record_count = sum(
            pattern.prediction_status == "unknown"
            for pattern in patterns
        )
        warnings.warn(
            f"{path}: {unknown_record_count} pattern record(s) contain unknown "
            f"ADL label(s): {', '.join(unknown_labels)}",
            stacklevel=2,
        )
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
        normalized_category = normalize_adl_label(category)
        intervals.append(
            ADLInterval(
                start_time=parse_timestamp(start_text),
                end_time=parse_timestamp(end_text),
                raw_label=row.get("raw_label") or category,
                adl_category=normalized_category or "Other",
            )
        )
    return intervals


def occurrence_is_within_time_band(
    start_time: Any,
    end_time: Any,
    time_band: str,
) -> bool:
    """Return whether half-open ``[start_time, end_time)`` stays in one band."""
    normalized_band = str(time_band or "All").strip() or "All"
    if normalized_band == "All":
        return True
    if end_time <= start_time:
        return False
    return (
        time_band_for_timestamp(start_time) == normalized_band
        and time_band_for_timestamp(end_time - timedelta(microseconds=1))
        == normalized_band
    )


def occurrence_audit_for_pattern(
    pattern: InterpretationPattern,
    occurrences: Sequence[PatternOccurrenceInterval],
) -> dict[str, Any]:
    """Return accepted occurrences and time-band-boundary audit counts."""
    group_pattern_id = pattern.group_pattern_id or pattern.pattern_id
    id_matches = [
        occurrence
        for occurrence in occurrences
        if occurrence.pattern_id in {pattern.pattern_id, group_pattern_id}
    ]
    # Some legacy occurrence CSVs do not preserve the evaluation pattern ID.
    # Use sequence fallback only when no own/group-ID occurrence exists; mixing
    # both sources duplicates a physical occurrence when the same sequence is
    # expanded into multiple time-band evaluation records.
    if id_matches:
        matched_occurrences = id_matches
    else:
        matched_occurrences = [
            occurrence
            for occurrence in occurrences
            if bool(occurrence.sequence) and occurrence.sequence == pattern.sequence
        ]

    if pattern.time_band == "All":
        assigned_candidates = matched_occurrences
        boundary_crossing = [
            occurrence
            for occurrence in assigned_candidates
            if time_band_for_timestamp(occurrence.start_time)
            != time_band_for_timestamp(
                occurrence.end_time - timedelta(microseconds=1)
            )
        ]
        accepted = assigned_candidates
        excluded_crossing: list[PatternOccurrenceInterval] = []
    else:
        assigned_candidates = [
            occurrence
            for occurrence in matched_occurrences
            if time_band_for_timestamp(occurrence.start_time) == pattern.time_band
        ]
        boundary_crossing = [
            occurrence
            for occurrence in assigned_candidates
            if not occurrence_is_within_time_band(
                occurrence.start_time,
                occurrence.end_time,
                pattern.time_band,
            )
        ]
        crossing_ids = {id(occurrence) for occurrence in boundary_crossing}
        accepted = [
            occurrence
            for occurrence in assigned_candidates
            if id(occurrence) not in crossing_ids
        ]
        excluded_crossing = boundary_crossing

    return {
        "occurrences": accepted,
        "num_matching_occurrences_before_time_band_filter": len(
            matched_occurrences
        ),
        "num_time_band_assigned_occurrences": len(assigned_candidates),
        "num_boundary_crossing_occurrences": len(boundary_crossing),
        "num_boundary_crossing_occurrences_excluded": len(excluded_crossing),
    }


def overlap_by_pattern_and_label(
    patterns: Sequence[InterpretationPattern],
    occurrences: Sequence[PatternOccurrenceInterval],
    adl_intervals: Sequence[ADLInterval],
) -> dict[str, dict[str, float]]:
    occurrences_by_pattern: dict[str, list[PatternOccurrenceInterval]] = defaultdict(list)
    for pattern in patterns:
        occurrences_by_pattern[pattern.pattern_id].extend(
            occurrence_audit_for_pattern(pattern, occurrences)["occurrences"]
        )

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
                        normalized_category = normalize_adl_label(category)
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
    return list(occurrence_audit_for_pattern(pattern, occurrences)["occurrences"])


def true_label_set_from_overlap(
    overlap_seconds_by_label: dict[str, float],
    min_overlap_ratio: float,
    no_overlap_label: str | None = None,
) -> tuple[tuple[str, ...], float]:
    """Build a truth set; an empty tuple means no ADL overlap was available."""
    total = sum(overlap_seconds_by_label.values())
    if total <= 0:
        return (), 0.0

    labels = [
        label
        for label, seconds in sorted(overlap_seconds_by_label.items())
        if seconds / total >= min_overlap_ratio
    ]
    return tuple(labels), total


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


def zero_metrics(true_labels: Sequence[str] = ()) -> dict[str, float | int | tuple[str, ...]]:
    return {
        "intersection_labels": (),
        "union_labels": tuple(sorted(set(true_labels))),
        "exact_set_match": 0,
        "jaccard": 0.0,
        "multilabel_precision": 0.0,
        "multilabel_recall": 0.0,
        "multilabel_f1": 0.0,
    }


def _prefixed_metrics(prefix: str, metrics: dict[str, Any] | None) -> dict[str, Any]:
    return {
        f"{prefix}_exact_set_match": (
            metrics["exact_set_match"] if metrics is not None else None
        ),
        f"{prefix}_jaccard": metrics["jaccard"] if metrics is not None else None,
        f"{prefix}_multilabel_precision": (
            metrics["multilabel_precision"] if metrics is not None else None
        ),
        f"{prefix}_multilabel_recall": (
            metrics["multilabel_recall"] if metrics is not None else None
        ),
        f"{prefix}_multilabel_f1": (
            metrics["multilabel_f1"] if metrics is not None else None
        ),
    }


def evaluate_interpretation_sets(
    patterns: Sequence[InterpretationPattern],
    occurrences: Sequence[PatternOccurrenceInterval],
    adl_intervals: Sequence[ADLInterval],
    min_overlap_ratio_for_true_label: float,
    no_overlap_label: str | None = None,
) -> tuple[list[dict], dict]:
    overlaps = overlap_by_pattern_and_label(patterns, occurrences, adl_intervals)
    detail_rows = []
    for pattern in patterns:
        occurrence_audit = occurrence_audit_for_pattern(pattern, occurrences)
        relevant_occurrences = occurrence_audit["occurrences"]
        num_occurrences = len(relevant_occurrences)
        occurrence_status = "matched" if num_occurrences else "no_occurrence"
        overlap_detail = overlaps.get(pattern.pattern_id, {})
        true_labels, total_overlap = true_label_set_from_overlap(
            overlap_detail,
            min_overlap_ratio=min_overlap_ratio_for_true_label,
        )
        truth_status = (
            "defined"
            if occurrence_status == "matched" and total_overlap > 0
            else "no_adl_overlap"
        )
        is_metric_evaluable = (
            occurrence_status == "matched" and truth_status == "defined"
        )
        is_end_to_end_evaluable = not (
            occurrence_status == "matched"
            and truth_status == "no_adl_overlap"
        )

        if occurrence_status == "no_occurrence":
            conditional_metrics = None
            end_to_end_metrics = zero_metrics()
        elif truth_status == "no_adl_overlap":
            conditional_metrics = None
            end_to_end_metrics = None
        elif pattern.prediction_status in {"missing", "unknown"}:
            conditional_metrics = zero_metrics(true_labels)
            end_to_end_metrics = zero_metrics(true_labels)
        else:
            conditional_metrics = set_metrics(pattern.pred_adl_labels, true_labels)
            end_to_end_metrics = dict(conditional_metrics)

        display_metrics = end_to_end_metrics
        intersection_labels = (
            display_metrics["intersection_labels"]
            if display_metrics is not None
            else ()
        )
        union_labels = (
            display_metrics["union_labels"]
            if display_metrics is not None
            else ()
        )
        detail_rows.append(
            {
                "pattern_id": pattern.pattern_id,
                "eval_pattern_id": pattern.pattern_id,
                "group_pattern_id": pattern.group_pattern_id or pattern.pattern_id,
                "time_band": pattern.time_band,
                "pattern_name": pattern.pattern_name,
                "sequence": sequence_text(pattern.sequence),
                "num_occurrences": num_occurrences,
                "num_matching_occurrences_before_time_band_filter": occurrence_audit[
                    "num_matching_occurrences_before_time_band_filter"
                ],
                "num_time_band_assigned_occurrences": occurrence_audit[
                    "num_time_band_assigned_occurrences"
                ],
                "num_boundary_crossing_occurrences": occurrence_audit[
                    "num_boundary_crossing_occurrences"
                ],
                "num_boundary_crossing_occurrences_excluded": occurrence_audit[
                    "num_boundary_crossing_occurrences_excluded"
                ],
                "occurrence_status": occurrence_status,
                "truth_status": truth_status,
                "prediction_status": pattern.prediction_status,
                "is_metric_evaluable": int(is_metric_evaluable),
                "is_end_to_end_evaluable": int(is_end_to_end_evaluable),
                "raw_pred_adl_labels": labels_text(pattern.raw_pred_adl_labels),
                "pred_adl_labels": labels_text(pattern.pred_adl_labels),
                "unknown_pred_adl_labels": labels_text(
                    pattern.unknown_pred_adl_labels
                ),
                "unknown_pred_label_count": len(pattern.unknown_pred_adl_labels),
                "true_adl_labels": labels_text(true_labels),
                "intersection_labels": labels_text(intersection_labels),
                "union_labels": labels_text(union_labels),
                "exact_set_match": (
                    display_metrics["exact_set_match"]
                    if display_metrics is not None
                    else None
                ),
                "jaccard": (
                    display_metrics["jaccard"]
                    if display_metrics is not None
                    else None
                ),
                "multilabel_precision": (
                    display_metrics["multilabel_precision"]
                    if display_metrics is not None
                    else None
                ),
                "multilabel_recall": (
                    display_metrics["multilabel_recall"]
                    if display_metrics is not None
                    else None
                ),
                "multilabel_f1": (
                    display_metrics["multilabel_f1"]
                    if display_metrics is not None
                    else None
                ),
                **_prefixed_metrics("conditional", conditional_metrics),
                **_prefixed_metrics("end_to_end", end_to_end_metrics),
                "total_overlap_seconds": total_overlap,
                "true_label_overlap_detail": json.dumps(overlap_detail, ensure_ascii=False, sort_keys=True),
            }
        )
    return detail_rows, summary_from_details(detail_rows)


def labels_text(labels: Sequence[str]) -> str:
    return ";".join(labels)


def mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _metric_mean(rows: Sequence[dict], prefix: str, metric: str) -> float:
    column = f"{prefix}_{metric}"
    return mean(
        [
            float(row[column])
            for row in rows
            if row.get(column) not in {None, ""}
        ]
    )


def summary_from_details(detail_rows: Sequence[dict]) -> dict:
    num_patterns = len(detail_rows)
    num_matched = sum(row.get("occurrence_status") == "matched" for row in detail_rows)
    num_no_occurrence = num_patterns - num_matched
    num_truth_defined = sum(row.get("truth_status") == "defined" for row in detail_rows)
    num_no_adl_overlap = sum(
        row.get("occurrence_status") == "matched"
        and row.get("truth_status") == "no_adl_overlap"
        for row in detail_rows
    )
    num_prediction_valid = sum(
        row.get("prediction_status") == "valid" for row in detail_rows
    )
    num_prediction_missing = sum(
        row.get("prediction_status") == "missing" for row in detail_rows
    )
    num_prediction_unknown = sum(
        row.get("prediction_status") == "unknown" for row in detail_rows
    )
    num_conditional = sum(
        bool(int(row.get("is_metric_evaluable") or 0))
        for row in detail_rows
    )
    num_end_to_end = sum(
        bool(int(row.get("is_end_to_end_evaluable") or 0))
        for row in detail_rows
    )
    num_assigned_occurrences = sum(
        int(row.get("num_time_band_assigned_occurrences") or 0)
        for row in detail_rows
    )
    num_boundary_crossing = sum(
        int(row.get("num_boundary_crossing_occurrences") or 0)
        for row in detail_rows
    )
    num_boundary_excluded = sum(
        int(row.get("num_boundary_crossing_occurrences_excluded") or 0)
        for row in detail_rows
    )

    summary: dict[str, Any] = {
        "num_patterns": num_patterns,
        "num_conditional_evaluable_patterns": num_conditional,
        "num_end_to_end_evaluable_patterns": num_end_to_end,
        "num_occurrence_matched": num_matched,
        "num_no_occurrence": num_no_occurrence,
        "num_truth_defined": num_truth_defined,
        "num_no_adl_overlap": num_no_adl_overlap,
        "num_prediction_valid": num_prediction_valid,
        "num_prediction_missing": num_prediction_missing,
        "num_prediction_unknown": num_prediction_unknown,
        "unknown_pred_label_count": sum(
            int(row.get("unknown_pred_label_count") or 0)
            for row in detail_rows
        ),
        "occurrence_coverage": _rate(num_matched, num_patterns),
        "truth_coverage": _rate(num_truth_defined, num_matched),
        "no_occurrence_rate": _rate(num_no_occurrence, num_patterns),
        "no_adl_overlap_rate": _rate(num_no_adl_overlap, num_matched),
        "missing_prediction_rate": _rate(num_prediction_missing, num_patterns),
        "unknown_label_rate": _rate(num_prediction_unknown, num_patterns),
        "num_time_band_assigned_occurrences": num_assigned_occurrences,
        "num_boundary_crossing_occurrences": num_boundary_crossing,
        "num_boundary_crossing_occurrences_excluded": num_boundary_excluded,
        "boundary_crossing_occurrence_rate": _rate(
            num_boundary_crossing,
            num_assigned_occurrences,
        ),
    }
    metric_names = (
        "exact_set_match",
        "jaccard",
        "multilabel_precision",
        "multilabel_recall",
        "multilabel_f1",
    )
    for metric in metric_names:
        summary[f"conditional_mean_{metric}"] = _metric_mean(
            detail_rows,
            "conditional",
            metric,
        )
        summary[f"end_to_end_mean_{metric}"] = _metric_mean(
            detail_rows,
            "end_to_end",
            metric,
        )
        # Backward-compatible aliases continue to denote end-to-end metrics.
        summary[f"mean_{metric}"] = summary[f"end_to_end_mean_{metric}"]
    return summary


def aggregate_by_time_band(detail_rows: Sequence[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in detail_rows:
        grouped[str(row.get("time_band") or "All")].append(row)
    return [
        {"time_band": time_band, **summary_from_details(rows)}
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
            **summary_from_details(rows),
        }
        for label, rows in sorted(grouped.items())
    ]
