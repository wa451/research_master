"""ADL evaluation against labeled CASAS intervals.

This module is intentionally independent from the existing LLM extraction and
network-building pipeline. It consumes existing outputs and computes a
post-hoc evaluation against labeled CASAS activity intervals.
"""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from src.behavior_pattern_mining.states.state_mapping import (
    load_event_log,
    load_state_mapping,
    map_vector_to_state,
)


ADL_CATEGORY_MAP = {
    "Sleeping": "Sleep",
    "Bed_to_Toilet": "Wake-up",
    "Bathroom": "Wake-up",
    "Personal_Hygiene": "Wake-up",
    "Bathing": "Wake-up",
    "Toileting": "Wake-up",
    "Meal_Preparation": "Meal",
    "Eating": "Meal",
    "Wash_Dishes": "Meal",
    "Leave_Home": "Outing",
    "Enter_Home": "Outing",
    "Relax": "Relax",
    "Housekeeping": "Housework",
    "Work": "Work",
}

WAKE_UP_CANDIDATE_LABELS = {
    "Bed_to_Toilet",
    "Bathroom",
    "Personal_Hygiene",
    "Bathing",
    "Toileting",
    "Meal_Preparation",
}


@dataclass(frozen=True)
class ADLInterval:
    start_time: datetime
    end_time: datetime
    raw_label: str
    adl_category: str


@dataclass(frozen=True)
class StateInterval:
    start_time: datetime
    end_time: datetime
    state_id: str


@dataclass(frozen=True)
class PatternRecord:
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]


@dataclass(frozen=True)
class PatternOccurrence:
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]
    start_time: datetime
    end_time: datetime


@dataclass(frozen=True)
class PatternADLMapping:
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]
    support: int
    assigned_adl: str
    confidence: float
    total_duration_seconds: float


@dataclass(frozen=True)
class PredictionInterval:
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]
    start_time: datetime
    end_time: datetime
    assigned_adl: str


@dataclass(frozen=True)
class MatchRecord:
    category: str
    prediction_index: int
    truth_index: int
    temporal_iou: float
    start_error_minutes: float
    end_error_minutes: float
    abs_start_error_minutes: float
    abs_end_error_minutes: float


def parse_timestamp(date_text: str, time_text: str | None = None) -> datetime:
    """Parse timestamps used by CASAS text files and generated CSV files."""
    if time_text is None:
        text = date_text.strip()
    else:
        text = f"{date_text.strip()} {time_text.strip()}"
    return datetime.fromisoformat(text)


def normalize_label(label: str) -> str:
    return label.strip().replace(" ", "_")


def adl_category_for_label(raw_label: str) -> str:
    return ADL_CATEGORY_MAP.get(normalize_label(raw_label), "Other")


def parse_labeled_casas_intervals(
    path: Path,
    wake_window_minutes: float = 30.0,
) -> list[ADLInterval]:
    """Read a labeled CASAS file and convert begin/end annotations to intervals."""
    active_by_label: dict[str, list[datetime]] = defaultdict(list)
    intervals: list[ADLInterval] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 6:
            continue

        marker = parts[-1].lower()
        if marker not in {"begin", "end"}:
            continue

        timestamp = parse_timestamp(parts[0], parts[1])
        label = normalize_label(" ".join(parts[4:-1]))
        if not label:
            continue

        if marker == "begin":
            active_by_label[label].append(timestamp)
            continue

        if not active_by_label[label]:
            continue
        start_time = active_by_label[label].pop()
        if timestamp <= start_time:
            continue
        intervals.append(
            ADLInterval(
                start_time=start_time,
                end_time=timestamp,
                raw_label=label,
                adl_category=adl_category_for_label(label),
            )
        )

    intervals.sort(key=lambda item: (item.start_time, item.end_time, item.raw_label))
    return apply_wake_up_rule(intervals, wake_window_minutes=wake_window_minutes)


def apply_wake_up_rule(
    intervals: Sequence[ADLInterval],
    wake_window_minutes: float,
) -> list[ADLInterval]:
    """Re-label selected post-sleep activities as Wake-up within a time window."""
    wake_window = timedelta(minutes=wake_window_minutes)
    sleep_end_times = [item.end_time for item in intervals if item.raw_label == "Sleeping"]
    adjusted: list[ADLInterval] = []

    for interval in intervals:
        category = interval.adl_category
        if interval.raw_label in WAKE_UP_CANDIDATE_LABELS:
            nearest_sleep_end = max(
                (end for end in sleep_end_times if end <= interval.start_time),
                default=None,
            )
            if nearest_sleep_end is not None and interval.start_time - nearest_sleep_end <= wake_window:
                category = "Wake-up"
        adjusted.append(
            ADLInterval(
                start_time=interval.start_time,
                end_time=interval.end_time,
                raw_label=interval.raw_label,
                adl_category=category,
            )
        )
    return adjusted


def load_state_series_csv(path: Path) -> list[StateInterval]:
    """Load state intervals from CSV.

    Supported columns:
    - start_time,end_time,state_id
    - start,end,state_id
    - timestamp,state_id (converted to adjacent intervals)
    """
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return []

    columns = set(rows[0].keys())
    state_col = "state_id" if "state_id" in columns else "state"

    if {"start_time", "end_time", state_col}.issubset(columns):
        start_col, end_col = "start_time", "end_time"
    elif {"start", "end", state_col}.issubset(columns):
        start_col, end_col = "start", "end"
    elif {"timestamp", state_col}.issubset(columns):
        parsed = [
            (parse_timestamp(row["timestamp"]), row[state_col])
            for row in rows
            if row.get("timestamp") and row.get(state_col)
        ]
        parsed.sort(key=lambda item: item[0])
        return [
            StateInterval(start_time=ts, end_time=parsed[index + 1][0], state_id=state_id)
            for index, (ts, state_id) in enumerate(parsed[:-1])
            if parsed[index + 1][0] > ts
        ]
    else:
        raise ValueError(
            f"Unsupported state series CSV columns: {sorted(columns)}. "
            "Expected start_time/end_time/state_id or timestamp/state_id."
        )

    intervals = []
    for row in rows:
        if not row.get(start_col) or not row.get(end_col) or not row.get(state_col):
            continue
        start_time = parse_timestamp(row[start_col])
        end_time = parse_timestamp(row[end_col])
        if end_time <= start_time:
            continue
        intervals.append(
            StateInterval(
                start_time=start_time,
                end_time=end_time,
                state_id=row[state_col].strip(),
            )
        )
    intervals.sort(key=lambda item: (item.start_time, item.end_time))
    return intervals


def build_state_series_from_event_log(
    event_log_path: Path,
    state_table_path: Path,
    hamming_threshold: int,
) -> list[StateInterval]:
    """Map an existing event log and state table to timestamped state intervals."""
    events = load_event_log(event_log_path)
    sensor_cols, state_mapping = load_state_mapping(state_table_path)
    current_sensor_state = {sensor: 0 for sensor in sensor_cols}

    intervals: list[StateInterval] = []
    current_label: str | None = None
    current_start: datetime | None = None
    last_timestamp: datetime | None = None

    for _, row in events.iterrows():
        timestamp = row["timestamp"].to_pydatetime()
        sensor = str(row["sensor"]).strip()
        value = str(row["value"]).strip().upper()
        if sensor not in current_sensor_state:
            continue

        if value in {"ON", "OPEN", "PRESENT", "1", "TRUE"}:
            current_sensor_state[sensor] = 1
        elif value in {"OFF", "CLOSE", "ABSENT", "0", "FALSE"}:
            current_sensor_state[sensor] = 0
        else:
            continue

        vector = tuple(current_sensor_state[sensor_name] for sensor_name in sensor_cols)
        state_id = map_vector_to_state(vector, state_mapping, hamming_threshold=hamming_threshold)

        if current_label is None:
            current_label = state_id
            current_start = timestamp
        elif state_id != current_label:
            if current_start is not None and timestamp > current_start:
                intervals.append(
                    StateInterval(
                        start_time=current_start,
                        end_time=timestamp,
                        state_id=current_label,
                    )
                )
            current_label = state_id
            current_start = timestamp

        last_timestamp = timestamp

    if current_label is not None and current_start is not None and last_timestamp is not None:
        if last_timestamp > current_start:
            intervals.append(
                StateInterval(
                    start_time=current_start,
                    end_time=last_timestamp,
                    state_id=current_label,
                )
            )

    return intervals


def write_state_series_csv(intervals: Sequence[StateInterval], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["start_time", "end_time", "state_id"])
        writer.writeheader()
        for interval in intervals:
            writer.writerow(
                {
                    "start_time": interval.start_time.isoformat(sep=" "),
                    "end_time": interval.end_time.isoformat(sep=" "),
                    "state_id": interval.state_id,
                }
            )


def load_patterns(path: Path) -> list[PatternRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Pattern JSON must be a list: {path}")

    patterns: list[PatternRecord] = []
    for index, item in enumerate(payload, start=1):
        if isinstance(item, dict):
            sequence = item.get("遷移のシーケンス") or item.get("sequence")
            pattern_name = item.get("パターン名") or item.get("pattern_name") or f"P{index}"
        elif isinstance(item, list):
            sequence = item
            pattern_name = f"P{index}"
        else:
            continue

        if not isinstance(sequence, list) or not all(isinstance(state, str) for state in sequence):
            continue
        if len(sequence) < 2:
            continue
        patterns.append(
            PatternRecord(
                pattern_id=f"P{len(patterns) + 1}",
                pattern_name=str(pattern_name),
                sequence=tuple(sequence),
            )
        )
    return patterns


def duration_seconds(start_time: datetime, end_time: datetime) -> float:
    return max(0.0, (end_time - start_time).total_seconds())


def interval_overlap_seconds(
    start_a: datetime,
    end_a: datetime,
    start_b: datetime,
    end_b: datetime,
) -> float:
    return duration_seconds(max(start_a, start_b), min(end_a, end_b))


def temporal_iou(
    pred_start: datetime,
    pred_end: datetime,
    true_start: datetime,
    true_end: datetime,
) -> float:
    overlap = interval_overlap_seconds(pred_start, pred_end, true_start, true_end)
    union = duration_seconds(min(pred_start, true_start), max(pred_end, true_end))
    return overlap / union if union > 0 else 0.0


def find_pattern_occurrences(
    patterns: Sequence[PatternRecord],
    state_intervals: Sequence[StateInterval],
    match_mode: str = "exact",
    max_skip_duration_minutes: float = 1.0,
) -> list[PatternOccurrence]:
    if match_mode not in {"exact", "skip-other"}:
        raise ValueError("match_mode must be 'exact' or 'skip-other'")

    occurrences: list[PatternOccurrence] = []
    for pattern in patterns:
        if match_mode == "exact":
            occurrences.extend(find_exact_occurrences(pattern, state_intervals))
        else:
            occurrences.extend(
                find_skip_other_occurrences(
                    pattern,
                    state_intervals,
                    max_skip_duration=timedelta(minutes=max_skip_duration_minutes),
                )
            )
    return occurrences


def find_exact_occurrences(
    pattern: PatternRecord,
    state_intervals: Sequence[StateInterval],
) -> list[PatternOccurrence]:
    length = len(pattern.sequence)
    occurrences: list[PatternOccurrence] = []
    for start_index in range(0, len(state_intervals) - length + 1):
        window = state_intervals[start_index : start_index + length]
        if tuple(item.state_id for item in window) != pattern.sequence:
            continue
        occurrences.append(
            PatternOccurrence(
                pattern_id=pattern.pattern_id,
                pattern_name=pattern.pattern_name,
                sequence=pattern.sequence,
                start_time=window[0].start_time,
                end_time=window[-1].end_time,
            )
        )
    return occurrences


def find_skip_other_occurrences(
    pattern: PatternRecord,
    state_intervals: Sequence[StateInterval],
    max_skip_duration: timedelta,
) -> list[PatternOccurrence]:
    occurrences: list[PatternOccurrence] = []
    for start_index, first_interval in enumerate(state_intervals):
        if first_interval.state_id != pattern.sequence[0]:
            continue
        matched_indices = [start_index]
        seq_index = 1
        skip_count = 0
        cursor = start_index + 1
        while cursor < len(state_intervals) and seq_index < len(pattern.sequence):
            interval = state_intervals[cursor]
            if interval.state_id == pattern.sequence[seq_index]:
                matched_indices.append(cursor)
                seq_index += 1
                cursor += 1
                continue
            if (
                interval.state_id == "その他"
                and skip_count < 1
                and interval.end_time - interval.start_time <= max_skip_duration
            ):
                skip_count += 1
                cursor += 1
                continue
            break
        if seq_index == len(pattern.sequence):
            window = [state_intervals[index] for index in matched_indices]
            occurrences.append(
                PatternOccurrence(
                    pattern_id=pattern.pattern_id,
                    pattern_name=pattern.pattern_name,
                    sequence=pattern.sequence,
                    start_time=window[0].start_time,
                    end_time=window[-1].end_time,
                )
            )
    return occurrences


def assign_patterns_to_adl(
    patterns: Sequence[PatternRecord],
    occurrences: Sequence[PatternOccurrence],
    adl_intervals: Sequence[ADLInterval],
) -> list[PatternADLMapping]:
    occurrences_by_pattern: dict[str, list[PatternOccurrence]] = defaultdict(list)
    for occurrence in occurrences:
        occurrences_by_pattern[occurrence.pattern_id].append(occurrence)

    sorted_labels = sorted(adl_intervals, key=lambda item: item.start_time)
    mappings: list[PatternADLMapping] = []
    for pattern in patterns:
        pattern_occurrences = sorted(
            occurrences_by_pattern.get(pattern.pattern_id, []),
            key=lambda item: item.start_time,
        )
        total_duration = sum(
            duration_seconds(item.start_time, item.end_time)
            for item in pattern_occurrences
        )
        overlap_by_category: dict[str, float] = defaultdict(float)
        label_cursor = 0
        for occurrence in pattern_occurrences:
            while (
                label_cursor < len(sorted_labels)
                and sorted_labels[label_cursor].end_time <= occurrence.start_time
            ):
                label_cursor += 1
            for label in sorted_labels[label_cursor:]:
                if label.start_time >= occurrence.end_time:
                    break
                overlap_by_category[label.adl_category] += interval_overlap_seconds(
                    occurrence.start_time,
                    occurrence.end_time,
                    label.start_time,
                    label.end_time,
                )

        if overlap_by_category:
            assigned_adl, assigned_overlap = max(
                overlap_by_category.items(),
                key=lambda item: (item[1], item[0]),
            )
        else:
            assigned_adl, assigned_overlap = "Unmapped", 0.0

        confidence = assigned_overlap / total_duration if total_duration > 0 else 0.0
        mappings.append(
            PatternADLMapping(
                pattern_id=pattern.pattern_id,
                pattern_name=pattern.pattern_name,
                sequence=pattern.sequence,
                support=len(pattern_occurrences),
                assigned_adl=assigned_adl,
                confidence=confidence,
                total_duration_seconds=total_duration,
            )
        )
    return mappings


def build_predictions(
    occurrences: Sequence[PatternOccurrence],
    mappings: Sequence[PatternADLMapping],
) -> list[PredictionInterval]:
    mapping_by_pattern = {mapping.pattern_id: mapping for mapping in mappings}
    predictions: list[PredictionInterval] = []
    for occurrence in occurrences:
        mapping = mapping_by_pattern.get(occurrence.pattern_id)
        if mapping is None or mapping.assigned_adl == "Unmapped":
            continue
        predictions.append(
            PredictionInterval(
                pattern_id=occurrence.pattern_id,
                pattern_name=occurrence.pattern_name,
                sequence=occurrence.sequence,
                start_time=occurrence.start_time,
                end_time=occurrence.end_time,
                assigned_adl=mapping.assigned_adl,
            )
        )
    return predictions


def greedy_match_by_category(
    predictions: Sequence[PredictionInterval],
    truths: Sequence[ADLInterval],
    iou_threshold: float,
) -> tuple[list[MatchRecord], dict[str, dict[str, int]]]:
    categories = sorted(
        {prediction.assigned_adl for prediction in predictions}
        | {truth.adl_category for truth in truths}
    )
    matches: list[MatchRecord] = []
    counts = {
        category: {"tp": 0, "fp": 0, "fn": 0}
        for category in categories
    }

    for category in categories:
        pred_indices = [
            index for index, prediction in enumerate(predictions)
            if prediction.assigned_adl == category
        ]
        truth_indices = [
            index for index, truth in enumerate(truths)
            if truth.adl_category == category
        ]

        pred_indices.sort(key=lambda index: predictions[index].start_time)
        truth_indices.sort(key=lambda index: truths[index].start_time)

        candidate_pairs = []
        truth_cursor = 0
        for pred_index in pred_indices:
            prediction = predictions[pred_index]
            while (
                truth_cursor < len(truth_indices)
                and truths[truth_indices[truth_cursor]].end_time <= prediction.start_time
            ):
                truth_cursor += 1
            for truth_index in truth_indices[truth_cursor:]:
                truth = truths[truth_index]
                if truth.start_time >= prediction.end_time:
                    break
                iou = temporal_iou(
                    prediction.start_time,
                    prediction.end_time,
                    truth.start_time,
                    truth.end_time,
                )
                if iou >= iou_threshold:
                    candidate_pairs.append((iou, pred_index, truth_index))
        candidate_pairs.sort(reverse=True)

        used_predictions: set[int] = set()
        used_truths: set[int] = set()
        for iou, pred_index, truth_index in candidate_pairs:
            if pred_index in used_predictions or truth_index in used_truths:
                continue
            prediction = predictions[pred_index]
            truth = truths[truth_index]
            used_predictions.add(pred_index)
            used_truths.add(truth_index)
            matches.append(
                MatchRecord(
                    category=category,
                    prediction_index=pred_index,
                    truth_index=truth_index,
                    temporal_iou=iou,
                    start_error_minutes=(prediction.start_time - truth.start_time).total_seconds() / 60.0,
                    end_error_minutes=(prediction.end_time - truth.end_time).total_seconds() / 60.0,
                    abs_start_error_minutes=abs((prediction.start_time - truth.start_time).total_seconds() / 60.0),
                    abs_end_error_minutes=abs((prediction.end_time - truth.end_time).total_seconds() / 60.0),
                )
            )

        tp = len(used_predictions)
        fp = len(pred_indices) - tp
        fn = len(truth_indices) - len(used_truths)
        counts[category] = {"tp": tp, "fp": fp, "fn": fn}

    return matches, counts


def safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def metrics_rows_from_counts(counts: dict[str, dict[str, int]]) -> list[dict]:
    rows = []
    for category in sorted(counts):
        tp = counts[category]["tp"]
        fp = counts[category]["fp"]
        fn = counts[category]["fn"]
        precision = safe_divide(tp, tp + fp)
        recall = safe_divide(tp, tp + fn)
        f1 = safe_divide(2 * precision * recall, precision + recall)
        rows.append(
            {
                "adl_category": category,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
        )
    return rows


def boundary_rows(matches: Sequence[MatchRecord]) -> list[dict]:
    by_category: dict[str, list[MatchRecord]] = defaultdict(list)
    for match in matches:
        by_category[match.category].append(match)

    rows = []
    for category in sorted(by_category):
        records = by_category[category]
        rows.append(
            {
                "adl_category": category,
                "mean_start_error": statistics.fmean(r.start_error_minutes for r in records),
                "median_abs_start_error": statistics.median(r.abs_start_error_minutes for r in records),
                "mean_end_error": statistics.fmean(r.end_error_minutes for r in records),
                "median_abs_end_error": statistics.median(r.abs_end_error_minutes for r in records),
                "mean_iou": statistics.fmean(r.temporal_iou for r in records),
                "matched_count": len(records),
            }
        )
    return rows


def macro_micro_average(rows: Sequence[dict]) -> dict:
    if not rows:
        return {
            "macro_precision": 0.0,
            "macro_recall": 0.0,
            "macro_f1": 0.0,
            "micro_precision": 0.0,
            "micro_recall": 0.0,
            "micro_f1": 0.0,
        }
    macro_precision = statistics.fmean(row["precision"] for row in rows)
    macro_recall = statistics.fmean(row["recall"] for row in rows)
    macro_f1 = statistics.fmean(row["f1"] for row in rows)
    tp = sum(row["tp"] for row in rows)
    fp = sum(row["fp"] for row in rows)
    fn = sum(row["fn"] for row in rows)
    micro_precision = safe_divide(tp, tp + fp)
    micro_recall = safe_divide(tp, tp + fn)
    micro_f1 = safe_divide(2 * micro_precision * micro_recall, micro_precision + micro_recall)
    return {
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
        "micro_precision": micro_precision,
        "micro_recall": micro_recall,
        "micro_f1": micro_f1,
    }


def filter_intervals_by_period(
    intervals: Iterable,
    start_time: datetime | None,
    end_time: datetime | None,
) -> list:
    filtered = []
    for interval in intervals:
        if start_time is not None and interval.end_time <= start_time:
            continue
        if end_time is not None and interval.start_time >= end_time:
            continue
        filtered.append(interval)
    return filtered


def split_time_from_ratio(
    intervals: Sequence[ADLInterval],
    train_ratio: float | None,
) -> datetime | None:
    if train_ratio is None:
        return None
    if not intervals:
        return None
    if not 0.0 < train_ratio < 1.0:
        raise ValueError("--train-ratio must be between 0 and 1")
    start_time = min(interval.start_time for interval in intervals)
    end_time = max(interval.end_time for interval in intervals)
    return start_time + (end_time - start_time) * train_ratio


def sequence_text(sequence: Sequence[str]) -> str:
    return "->".join(sequence)


def write_csv_rows(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_evaluation_outputs(
    output_dir: Path,
    occurrences: Sequence[PatternOccurrence],
    mappings: Sequence[PatternADLMapping],
    metrics_by_threshold: dict[float, list[dict]],
    boundary_by_threshold: dict[float, list[dict]],
    summary: dict,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    write_csv_rows(
        output_dir / "pattern_occurrences.csv",
        [
            {
                "pattern_id": item.pattern_id,
                "pattern_name": item.pattern_name,
                "sequence": sequence_text(item.sequence),
                "start_time": item.start_time.isoformat(sep=" "),
                "end_time": item.end_time.isoformat(sep=" "),
            }
            for item in occurrences
        ],
        ["pattern_id", "pattern_name", "sequence", "start_time", "end_time"],
    )

    write_csv_rows(
        output_dir / "pattern_adl_mapping.csv",
        [
            {
                "pattern_id": item.pattern_id,
                "pattern_name": item.pattern_name,
                "sequence": sequence_text(item.sequence),
                "support": item.support,
                "assigned_adl": item.assigned_adl,
                "confidence": f"{item.confidence:.6f}",
                "total_duration_seconds": f"{item.total_duration_seconds:.3f}",
            }
            for item in mappings
        ],
        [
            "pattern_id",
            "pattern_name",
            "sequence",
            "support",
            "assigned_adl",
            "confidence",
            "total_duration_seconds",
        ],
    )

    for threshold, rows in metrics_by_threshold.items():
        suffix = str(threshold)
        write_csv_rows(
            output_dir / f"adl_metrics_iou_{suffix}.csv",
            rows,
            ["adl_category", "tp", "fp", "fn", "precision", "recall", "f1"],
        )
        write_csv_rows(
            output_dir / f"boundary_metrics_iou_{suffix}.csv",
            boundary_by_threshold.get(threshold, []),
            [
                "adl_category",
                "mean_start_error",
                "median_abs_start_error",
                "mean_end_error",
                "median_abs_end_error",
                "mean_iou",
                "matched_count",
            ],
        )

    (output_dir / "evaluation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
