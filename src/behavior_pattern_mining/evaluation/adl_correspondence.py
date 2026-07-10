"""Compare multiple pattern-extraction methods against labeled CASAS ADLs.

This module is a post-hoc evaluation layer. It reuses the single-method ADL
evaluation primitives and only adds method-aware pattern loading, aggregation,
and output writing.
"""

from __future__ import annotations

import ast
import csv
import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

from src.behavior_pattern_mining.evaluation.adl import (
    ADLInterval,
    PatternADLMapping,
    PatternOccurrence,
    PatternRecord,
    PredictionInterval,
    StateInterval,
    assign_patterns_to_adl,
    boundary_rows,
    build_predictions,
    compute_interval_hit_evaluation,
    duration_seconds,
    filter_predictions_by_duration,
    find_pattern_occurrences,
    greedy_match_by_category,
    macro_micro_average,
    merge_prediction_intervals,
    merged_to_prediction_intervals,
    metrics_rows_from_counts,
    sequence_text,
    write_csv_rows,
)


METHOD_ID_PREFIX = {
    "frequency": "F",
    "rule_light": "RL",
    "rule_medium": "RM",
    "rule_strong": "RS",
    "fp_growth": "FPG",
    "fp_growth_filtered": "FPGF",
    "transition_probability": "TP",
    "proposed": "P",
}

COMPARISON_CATEGORIES = [
    "Sleep",
    "Wake-up",
    "Toileting",
    "Hygiene",
    "Meal",
    "Outing",
    "Relax",
    "Housework",
    "Work",
    "Other_ADL",
]

EVALUATION5_ADL_CATEGORY_MAP = {
    "Sleeping": ("Sleep",),
    "Bed_to_Toilet": ("Wake-up", "Toileting"),
    "Bathroom": ("Wake-up", "Hygiene"),
    "Personal_Hygiene": ("Wake-up", "Hygiene"),
    "Bathing": ("Hygiene",),
    "Toileting": ("Toileting",),
    "Meal_Preparation": ("Meal",),
    "Eating": ("Meal",),
    "Wash_Dishes": ("Meal", "Housework"),
    "Leave_Home": ("Outing",),
    "Enter_Home": ("Outing",),
    "Relax": ("Relax",),
    "Housekeeping": ("Housework",),
    "Work": ("Work",),
    "__unknown__": ("Other_ADL",),
}

DEFAULT_OTHER_STATE_LABELS = {"その他", "Other", "other", "OTHER", "Other_ADL", "unknown", "Unknown"}


@dataclass(frozen=True)
class MethodPattern:
    method: str
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]
    count: int | None = None
    pattern_source: str = ""
    time_band: str = ""
    support_transactions: int | None = None
    support_ratio: float | None = None
    train_occurrence_count: int | None = None
    median_duration_seconds: float | None = None
    p90_duration_seconds: float | None = None
    is_fp_filtered_out: int | None = None
    fp_filter_reason: str = ""
    transition_joint_probability: float | None = None
    transition_min_step_probability: float | None = None


@dataclass(frozen=True)
class MethodOccurrence:
    method: str
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]
    occurrence_id: str
    start_time: Any
    end_time: Any


@dataclass(frozen=True)
class MethodMapping:
    method: str
    pattern_id: str
    pattern_name: str
    sequence: tuple[str, ...]
    support: int
    assigned_adl: str
    adl_confidence: float
    total_duration_seconds: float
    input_count: int | None = None


def parse_sequence(value: Any) -> tuple[str, ...]:
    """Normalize common sequence encodings to a tuple of state IDs."""
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


def _first_present(item: dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _coerce_count(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _pattern_id(method: str, index: int) -> str:
    prefix = METHOD_ID_PREFIX.get(method, method[:2].upper())
    return f"{prefix}{index:03d}"


def _time_band_suffix(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in value.strip())
    return cleaned.strip("_") or "time_band"


def _make_method_pattern(
    method: str,
    pattern_id: str,
    pattern_name: str,
    sequence: Sequence[str],
    count: int | None = None,
    pattern_source: str = "",
    time_band: str = "",
) -> MethodPattern:
    return MethodPattern(
        method=method,
        pattern_id=pattern_id,
        pattern_name=pattern_name,
        sequence=tuple(sequence),
        count=count,
        pattern_source=pattern_source,
        time_band=time_band,
    )


def load_method_patterns(path: Path, method: str) -> tuple[list[MethodPattern], list[str]]:
    """Load one method's pattern output from JSON or CSV.

    Supported inputs include the existing ``state_sequence_counts_*.json`` and
    ``llm_sequences_modes_*.json`` formats, plus CSVs with sequence-like columns.
    Invalid or length-1 sequences are skipped with notes instead of stopping the
    whole evaluation.
    """
    notes: list[str] = []
    if not path.exists():
        return [], [f"{method}: skipped because file does not exist: {path}"]

    suffix = path.suffix.lower()
    if suffix == ".csv":
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
        return [], [f"{method}: skipped because pattern file is not a list-like structure: {path}"]

    patterns: list[MethodPattern] = []
    for raw_index, item in enumerate(payload, start=1):
        input_count: int | None = None
        pattern_name: str | None = None
        raw_sequence: Any = None

        if isinstance(item, dict):
            raw_sequence = _first_present(
                item,
                [
                    "sequence",
                    "遷移のパターン",
                    "遷移のシーケンス",
                    "states",
                    "state_sequence",
                    "pattern",
                    "系列",
                ],
            )
            pattern_name = _first_present(
                item,
                ["pattern_name", "name", "パターン名", "label", "description"],
            )
            existing_id = _first_present(item, ["pattern_id", "id"])
            input_count = _coerce_count(_first_present(item, ["count", "frequency", "support"]))
            time_band = str(_first_present(item, ["time_band", "mode", "時間帯"]) or "")
        else:
            raw_sequence = item
            existing_id = None
            time_band = ""

        sequence = parse_sequence(raw_sequence)
        if len(sequence) < 2:
            notes.append(f"{method}: skipped invalid sequence at row {raw_index}: {raw_sequence!r}")
            continue

        if pattern_name is None:
            pattern_name = sequence_text(sequence)

        time_band_interpretations = (
            item.get("time_band_interpretations")
            if isinstance(item, dict) and isinstance(item.get("time_band_interpretations"), dict)
            else None
        )
        if method == "proposed" and time_band_interpretations:
            for band_name, interpretation in time_band_interpretations.items():
                pattern_index = len(patterns) + 1
                base_id = str(existing_id).strip() if existing_id else _pattern_id(method, pattern_index)
                band_text = str(band_name)
                band_suffix = _time_band_suffix(band_text)
                band_pattern_name = pattern_name
                if isinstance(interpretation, dict):
                    band_pattern_name = _first_present(
                        interpretation,
                        ["pattern_name", "name", "パターン名", "label", "description"],
                    ) or pattern_name
                patterns.append(
                    _make_method_pattern(
                        method=method,
                        pattern_id=f"{base_id}_{band_suffix}",
                        pattern_name=str(band_pattern_name),
                        sequence=sequence,
                        count=input_count,
                        pattern_source="proposed_time_band",
                        time_band=band_text,
                    )
                )
            continue

        pattern_index = len(patterns) + 1
        pattern_id = str(existing_id).strip() if existing_id else _pattern_id(method, pattern_index)
        if not pattern_id:
            pattern_id = _pattern_id(method, pattern_index)
        patterns.append(
            _make_method_pattern(
                method=method,
                pattern_id=pattern_id,
                pattern_name=str(pattern_name),
                sequence=sequence,
                count=input_count,
                time_band=time_band,
            )
        )

    return patterns, notes


def ensure_baseline_pattern_files(
    method_paths: dict[str, Path],
    state_intervals: Sequence[StateInterval],
    min_length: int,
    max_length: int | None,
    top_k: int,
) -> list[str]:
    """Create missing frequency and rule-filtered baselines from state-series CSV."""
    notes: list[str] = []
    frequency_path = method_paths.get("frequency")
    if frequency_path is not None and not frequency_path.exists():
        frequency_payload = build_frequency_payload_from_state_intervals(
            state_intervals=state_intervals,
            min_length=min_length,
            max_length=max_length,
            top_k=top_k,
        )
        frequency_path.parent.mkdir(parents=True, exist_ok=True)
        frequency_path.write_text(
            json.dumps(frequency_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        notes.append(f"frequency: generated missing baseline from --state-series: {frequency_path}")

    frequency_patterns, frequency_notes = load_method_patterns(
        frequency_path,
        "frequency",
    ) if frequency_path is not None else ([], ["frequency: no path configured"])
    notes.extend(frequency_notes)

    rule_specs = {
        "rule_light": keep_rule_light,
        "rule_medium": keep_rule_medium,
        "rule_strong": keep_rule_strong,
    }
    for method, predicate in rule_specs.items():
        path = method_paths.get(method)
        if path is None or path.exists():
            continue
        filtered = [pattern for pattern in frequency_patterns if predicate(pattern.sequence)]
        write_rule_patterns_csv(path, filtered, method)
        notes.append(f"{method}: generated missing rule-filtered baseline from frequency baseline: {path}")

    return notes


def build_frequency_payload_from_state_intervals(
    state_intervals: Sequence[StateInterval],
    min_length: int,
    max_length: int | None,
    top_k: int,
) -> list[dict]:
    sequence = compressed_state_sequence(state_intervals)
    counts = count_contiguous_sequences(sequence, min_length=min_length, max_length=max_length)
    items = counts.most_common(None if top_k == 0 else top_k)
    return [
        {
            "rank": index,
            "sequence": list(states),
            "count": count,
        }
        for index, (states, count) in enumerate(items, start=1)
    ]


def compressed_state_sequence(state_intervals: Sequence[StateInterval]) -> list[str]:
    sequence: list[str] = []
    previous: str | None = None
    for interval in sorted(state_intervals, key=lambda item: (item.start_time, item.end_time)):
        state_id = interval.state_id
        if state_id == previous:
            continue
        sequence.append(state_id)
        previous = state_id
    return sequence


def count_contiguous_sequences(
    state_sequence: Sequence[str],
    min_length: int,
    max_length: int | None,
) -> Counter[tuple[str, ...]]:
    if min_length < 2:
        raise ValueError("min_length must be >= 2")
    upper = len(state_sequence) if max_length is None else min(max_length, len(state_sequence))
    counts: Counter[tuple[str, ...]] = Counter()
    for length in range(min_length, upper + 1):
        for start in range(0, len(state_sequence) - length + 1):
            counts[tuple(state_sequence[start : start + length])] += 1
    return counts


NOISE_STATES = {"", "その他", "Other", "Other_ADL", "Unmapped"}


def keep_rule_light(sequence: Sequence[str]) -> bool:
    """Remove only obvious noise states."""
    return len(sequence) >= 2 and not any(state in NOISE_STATES for state in sequence)


def keep_rule_medium(sequence: Sequence[str]) -> bool:
    """Remove obvious noise plus short backtracking/alternating patterns."""
    if not keep_rule_light(sequence):
        return False
    has_immediate_backtrack = any(sequence[index] == sequence[index + 2] for index in range(len(sequence) - 2))
    has_pair_alternation = any(
        tuple(sequence[index : index + 2]) == tuple(sequence[index + 2 : index + 4])
        for index in range(len(sequence) - 3)
    )
    return not has_immediate_backtrack and not has_pair_alternation


def keep_rule_strong(sequence: Sequence[str]) -> bool:
    """Keep only non-noise paths without repeated states."""
    return keep_rule_medium(sequence) and len(set(sequence)) == len(sequence)


def write_rule_patterns_csv(path: Path, patterns: Sequence[MethodPattern], method: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["pattern_id", "pattern_name", "sequence", "count", "rule_filter"],
        )
        writer.writeheader()
        for index, pattern in enumerate(patterns, start=1):
            writer.writerow(
                {
                    "pattern_id": _pattern_id(method, index),
                    "pattern_name": pattern.pattern_name,
                    "sequence": sequence_text(pattern.sequence),
                    "count": pattern.count if pattern.count is not None else "",
                    "rule_filter": method,
                }
            )


def _transaction_bucket(timestamp: datetime) -> str:
    hour = timestamp.hour
    if 6 <= hour < 10:
        period = "Morning"
    elif 10 <= hour < 18:
        period = "Daytime"
    elif 18 <= hour < 24:
        period = "Night"
    else:
        period = "Midnight"
    return f"{timestamp.date().isoformat()}_{period}"


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (percentile / 100.0) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = rank - lower
    return float(sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction)


def fp_growth_filter_reason(
    sequence: Sequence[str],
    median_duration_seconds: float,
    p90_duration_seconds: float,
    other_state_labels: set[str] | None = None,
    max_median_duration_seconds: float = 1800.0,
    max_p90_duration_seconds: float = 3600.0,
) -> str:
    reasons: list[str] = []
    other_labels = other_state_labels or set(DEFAULT_OTHER_STATE_LABELS)
    if any(sequence[index] == sequence[index + 1] for index in range(len(sequence) - 1)):
        reasons.append("self_transition")
    is_useless_b, _ = detect_other_state_round_trip(sequence, other_labels)
    if is_useless_b:
        reasons.append("other_round_trip")
    is_useless_c, _ = detect_alternating_loop(sequence)
    if is_useless_c:
        reasons.append("alternating_loop")
    if median_duration_seconds > max_median_duration_seconds:
        reasons.append(f"median_duration>{max_median_duration_seconds:g}")
    if p90_duration_seconds > max_p90_duration_seconds:
        reasons.append(f"p90_duration>{max_p90_duration_seconds:g}")
    return ";".join(reasons)


def build_fp_growth_baseline_patterns(
    state_intervals: Sequence[StateInterval],
    min_support: float,
    top_k: int,
    min_len: int,
    max_len: int,
    other_state_labels: set[str] | None = None,
    max_median_duration_seconds: float = 1800.0,
    max_p90_duration_seconds: float = 3600.0,
) -> tuple[dict[str, list[MethodPattern]], list[str]]:
    """Build FP-Growth-style baselines from train-period contiguous n-grams.

    Each contiguous state n-gram is treated as an item. Transactions are
    date-by-time-period buckets, and item support is the ratio of transactions
    containing the n-gram. This is equivalent to one-item frequent pattern
    mining over n-gram items and keeps the output as state sequences.
    """
    if min_len < 2:
        raise ValueError("--fp-min-len must be >= 2")
    if max_len < min_len:
        raise ValueError("--fp-max-len must be >= --fp-min-len")
    if not 0 < min_support <= 1:
        raise ValueError("--fp-min-support must be in the range (0, 1]")

    sorted_intervals = sorted(state_intervals, key=lambda item: (item.start_time, item.end_time))
    if not sorted_intervals:
        return {"fp_growth": [], "fp_growth_filtered": []}, ["fp_growth: skipped because train state series is empty"]

    transactions_by_item: dict[tuple[str, ...], set[str]] = defaultdict(set)
    occurrence_count_by_item: Counter[tuple[str, ...]] = Counter()
    durations_by_item: dict[tuple[str, ...], list[float]] = defaultdict(list)
    all_transactions: set[str] = set()

    upper = min(max_len, len(sorted_intervals))
    for start_index in range(len(sorted_intervals)):
        transaction_id = _transaction_bucket(sorted_intervals[start_index].start_time)
        all_transactions.add(transaction_id)
        for length in range(min_len, upper + 1):
            end_index = start_index + length - 1
            if end_index >= len(sorted_intervals):
                break
            sequence = tuple(item.state_id for item in sorted_intervals[start_index : end_index + 1])
            end_time = sorted_intervals[end_index].end_time
            transactions_by_item[sequence].add(transaction_id)
            occurrence_count_by_item[sequence] += 1
            durations_by_item[sequence].append(duration_seconds(sorted_intervals[start_index].start_time, end_time))

    num_transactions = len(all_transactions)
    if num_transactions == 0:
        return {"fp_growth": [], "fp_growth_filtered": []}, ["fp_growth: skipped because no transactions were created"]

    candidates: list[tuple[tuple[str, ...], int, float, int, float, float]] = []
    for sequence, transaction_ids in transactions_by_item.items():
        support_transactions = len(transaction_ids)
        support_ratio = support_transactions / num_transactions
        if support_ratio < min_support:
            continue
        durations = durations_by_item[sequence]
        candidates.append(
            (
                sequence,
                support_transactions,
                support_ratio,
                occurrence_count_by_item[sequence],
                statistics.median(durations) if durations else 0.0,
                _percentile(durations, 90),
            )
        )

    candidates.sort(key=lambda item: (-item[1], -item[2], -item[3], item[0]))
    selected = candidates[:top_k] if top_k > 0 else candidates

    fp_growth_patterns: list[MethodPattern] = []
    fp_growth_filtered_patterns: list[MethodPattern] = []
    for index, (
        sequence,
        support_transactions,
        support_ratio,
        train_occurrence_count,
        median_duration,
        p90_duration,
    ) in enumerate(selected, start=1):
        reason = fp_growth_filter_reason(
            sequence,
            median_duration,
            p90_duration,
            other_state_labels=other_state_labels,
            max_median_duration_seconds=max_median_duration_seconds,
            max_p90_duration_seconds=max_p90_duration_seconds,
        )
        base_pattern = MethodPattern(
            method="fp_growth",
            pattern_id=_pattern_id("fp_growth", index),
            pattern_name=sequence_text(sequence),
            sequence=sequence,
            count=train_occurrence_count,
            pattern_source="fp_growth_ngram_transaction",
            support_transactions=support_transactions,
            support_ratio=support_ratio,
            train_occurrence_count=train_occurrence_count,
            median_duration_seconds=median_duration,
            p90_duration_seconds=p90_duration,
            is_fp_filtered_out=int(bool(reason)),
            fp_filter_reason=reason,
        )
        fp_growth_patterns.append(base_pattern)
        if not reason:
            filtered_index = len(fp_growth_filtered_patterns) + 1
            fp_growth_filtered_patterns.append(
                MethodPattern(
                    method="fp_growth_filtered",
                    pattern_id=_pattern_id("fp_growth_filtered", filtered_index),
                    pattern_name=base_pattern.pattern_name,
                    sequence=base_pattern.sequence,
                    count=base_pattern.count,
                    pattern_source="fp_growth_ngram_transaction_filtered",
                    support_transactions=base_pattern.support_transactions,
                    support_ratio=base_pattern.support_ratio,
                    train_occurrence_count=base_pattern.train_occurrence_count,
                    median_duration_seconds=base_pattern.median_duration_seconds,
                    p90_duration_seconds=base_pattern.p90_duration_seconds,
                    is_fp_filtered_out=0,
                    fp_filter_reason="",
                )
            )

    notes = [
        (
            "fp_growth: generated from train date-by-time-period transactions "
            f"(transactions={num_transactions}, candidates={len(candidates)}, selected={len(fp_growth_patterns)})"
        ),
        f"fp_growth_filtered: kept {len(fp_growth_filtered_patterns)} / {len(fp_growth_patterns)} selected patterns",
    ]
    return {"fp_growth": fp_growth_patterns, "fp_growth_filtered": fp_growth_filtered_patterns}, notes


def build_transition_probability_baseline_patterns(
    state_intervals: Sequence[StateInterval],
    top_k: int = 50,
    min_prob: float = 0.0,
    min_len: int = 2,
    max_len: int = 4,
) -> tuple[list[MethodPattern], list[str]]:
    """Build transition-probability baseline paths from train-period state series."""
    if top_k < 0:
        raise ValueError("--transition-top-k must be >= 0")
    if min_len < 2:
        raise ValueError("--transition-min-len must be >= 2")
    if max_len < min_len:
        raise ValueError("--transition-max-len must be >= --transition-min-len")
    if not 0.0 <= min_prob <= 1.0:
        raise ValueError("--transition-min-prob must be in the range [0, 1]")

    state_sequence = compressed_state_sequence(state_intervals)
    if len(state_sequence) < min_len:
        return [], ["transition_probability: skipped because train state series is too short"]

    transition_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for src, dst in zip(state_sequence, state_sequence[1:]):
        transition_counts[src][dst] += 1

    adjacency: dict[str, list[tuple[str, float]]] = {}
    for src, counts in transition_counts.items():
        total = sum(counts.values())
        if total <= 0:
            continue
        candidates = [
            (dst, count / total)
            for dst, count in counts.items()
            if (count / total) >= min_prob
        ]
        candidates.sort(key=lambda item: (-item[1], item[0]))
        adjacency[src] = candidates

    unique_paths: dict[tuple[str, ...], tuple[float, float]] = {}

    def dfs(path: list[str], probabilities: list[float]) -> None:
        if min_len <= len(path) <= max_len:
            joint = 1.0
            for probability in probabilities:
                joint *= probability
            min_step = min(probabilities) if probabilities else 1.0
            key = tuple(path)
            existing = unique_paths.get(key)
            if existing is None or (joint, min_step) > existing:
                unique_paths[key] = (joint, min_step)
        if len(path) >= max_len:
            return
        for dst, probability in adjacency.get(path[-1], []):
            path.append(dst)
            probabilities.append(probability)
            dfs(path, probabilities)
            probabilities.pop()
            path.pop()

    for start_state in sorted(adjacency):
        dfs([start_state], [])

    if not unique_paths:
        return [], ["transition_probability: skipped because no paths satisfied transition settings"]

    occurrence_counts = count_contiguous_sequences(
        state_sequence,
        min_length=min_len,
        max_length=max_len,
    )
    sorted_paths = sorted(
        unique_paths.items(),
        key=lambda item: (-item[1][0], -item[1][1], -len(item[0]), item[0]),
    )
    selected = sorted_paths[:top_k] if top_k > 0 else sorted_paths

    patterns = [
        MethodPattern(
            method="transition_probability",
            pattern_id=_pattern_id("transition_probability", index),
            pattern_name=sequence_text(sequence),
            sequence=sequence,
            count=occurrence_counts.get(sequence, 0),
            pattern_source="train_transition_probability",
            train_occurrence_count=occurrence_counts.get(sequence, 0),
            transition_joint_probability=joint_probability,
            transition_min_step_probability=min_step_probability,
        )
        for index, (sequence, (joint_probability, min_step_probability)) in enumerate(selected, start=1)
    ]
    notes = [
        (
            "transition_probability: generated from train state-series transitions "
            f"(states={len(state_sequence)}, paths={len(unique_paths)}, selected={len(patterns)}, "
            f"min_prob={min_prob:g}, length={min_len}-{max_len})"
        )
    ]
    return patterns, notes


def to_pattern_records(patterns: Sequence[MethodPattern]) -> list[PatternRecord]:
    return [
        PatternRecord(
            pattern_id=item.pattern_id,
            pattern_name=item.pattern_name,
            sequence=item.sequence,
        )
        for item in patterns
    ]


def find_occurrences_by_method(
    patterns_by_method: dict[str, list[MethodPattern]],
    state_intervals: Sequence[StateInterval],
    match_mode: str,
    max_skip_duration_minutes: float,
) -> dict[str, list[MethodOccurrence]]:
    occurrences_by_method: dict[str, list[MethodOccurrence]] = {}
    for method, patterns in patterns_by_method.items():
        raw_occurrences = find_pattern_occurrences(
            to_pattern_records(patterns),
            state_intervals,
            match_mode=match_mode,
            max_skip_duration_minutes=max_skip_duration_minutes,
        )
        counts_by_pattern: Counter[str] = Counter()
        method_occurrences: list[MethodOccurrence] = []
        for occurrence in raw_occurrences:
            counts_by_pattern[occurrence.pattern_id] += 1
            method_occurrences.append(
                MethodOccurrence(
                    method=method,
                    pattern_id=occurrence.pattern_id,
                    pattern_name=occurrence.pattern_name,
                    sequence=occurrence.sequence,
                    occurrence_id=f"{occurrence.pattern_id}_{counts_by_pattern[occurrence.pattern_id]:04d}",
                    start_time=occurrence.start_time,
                    end_time=occurrence.end_time,
                )
            )
        occurrences_by_method[method] = method_occurrences
    return occurrences_by_method


def _plain_occurrences(occurrences: Sequence[MethodOccurrence]) -> list[PatternOccurrence]:
    return [
        PatternOccurrence(
            pattern_id=item.pattern_id,
            pattern_name=item.pattern_name,
            sequence=item.sequence,
            start_time=item.start_time,
            end_time=item.end_time,
        )
        for item in occurrences
    ]


def assign_mappings_by_method(
    patterns_by_method: dict[str, list[MethodPattern]],
    occurrences_by_method: dict[str, list[MethodOccurrence]],
    labels: Sequence[ADLInterval],
) -> dict[str, list[MethodMapping]]:
    mappings_by_method: dict[str, list[MethodMapping]] = {}
    for method, patterns in patterns_by_method.items():
        count_by_pattern = {pattern.pattern_id: pattern.count for pattern in patterns}
        raw_mappings = assign_patterns_to_adl(
            to_pattern_records(patterns),
            _plain_occurrences(occurrences_by_method.get(method, [])),
            labels,
        )
        mappings_by_method[method] = [
            MethodMapping(
                method=method,
                pattern_id=item.pattern_id,
                pattern_name=item.pattern_name,
                sequence=item.sequence,
                support=item.support,
                assigned_adl=item.assigned_adl,
                adl_confidence=item.confidence,
                total_duration_seconds=item.total_duration_seconds,
                input_count=count_by_pattern.get(item.pattern_id),
            )
            for item in raw_mappings
        ]
    return mappings_by_method


def _plain_mappings(mappings: Sequence[MethodMapping]) -> list[PatternADLMapping]:
    return [
        PatternADLMapping(
            pattern_id=item.pattern_id,
            pattern_name=item.pattern_name,
            sequence=item.sequence,
            support=item.support,
            assigned_adl=item.assigned_adl,
            confidence=item.adl_confidence,
            total_duration_seconds=item.total_duration_seconds,
        )
        for item in mappings
    ]


def build_predictions_by_method(
    occurrences_by_method: dict[str, list[MethodOccurrence]],
    mappings_by_method: dict[str, list[MethodMapping]],
) -> dict[str, list[PredictionInterval]]:
    predictions_by_method: dict[str, list[PredictionInterval]] = {}
    for method, occurrences in occurrences_by_method.items():
        predictions_by_method[method] = build_predictions(
            _plain_occurrences(occurrences),
            _plain_mappings(mappings_by_method.get(method, [])),
        )
    return predictions_by_method


def postprocess_predictions_by_method(
    predictions_by_method: dict[str, list[PredictionInterval]],
    labels: Sequence[ADLInterval],
    merge_gap_minutes: float,
    min_duration_by_adl: dict[str, float],
    hit_tolerance_minutes: float,
):
    """Apply ADL prediction post-processing independently for each method."""
    merged_by_method = {}
    filtered_by_method = {}
    postprocessed_by_method = {}
    removed_by_method = {}
    hit_metric_rows: list[dict] = []
    hit_detail_rows: list[dict] = []

    for method, predictions in predictions_by_method.items():
        merged = merge_prediction_intervals(predictions, merge_gap_minutes=merge_gap_minutes)
        filtered, removed = filter_predictions_by_duration(merged, min_duration_by_adl)
        postprocessed = merged_to_prediction_intervals(filtered)
        metric_rows, detail_rows = compute_interval_hit_evaluation(
            filtered,
            labels,
            hit_tolerance_minutes=hit_tolerance_minutes,
        )

        merged_by_method[method] = merged
        filtered_by_method[method] = filtered
        postprocessed_by_method[method] = postprocessed
        removed_by_method[method] = removed

        for row in metric_rows:
            hit_metric_rows.append({"method": method, **row})
        for row in detail_rows:
            hit_detail_rows.append({"method": method, **row})

    return (
        merged_by_method,
        filtered_by_method,
        postprocessed_by_method,
        removed_by_method,
        hit_metric_rows,
        hit_detail_rows,
    )


def weighted_f1(rows: Sequence[dict]) -> float:
    total_weight = sum(row["tp"] + row["fn"] for row in rows)
    if total_weight == 0:
        return 0.0
    return sum(row["f1"] * (row["tp"] + row["fn"]) for row in rows) / total_weight


def evaluate_methods(
    predictions_by_method: dict[str, list[PredictionInterval]],
    labels: Sequence[ADLInterval],
    iou_thresholds: Sequence[float],
) -> tuple[dict[float, list[dict]], dict[float, list[dict]], list[dict], dict[str, dict[str, float]]]:
    metrics_by_threshold: dict[float, list[dict]] = {}
    boundary_by_threshold: dict[float, list[dict]] = {}
    comparison_rows: list[dict] = []
    averages_by_method: dict[str, dict[str, float]] = defaultdict(dict)

    for threshold in iou_thresholds:
        threshold_metrics: list[dict] = []
        threshold_boundary: list[dict] = []
        for method, predictions in predictions_by_method.items():
            matches, counts = greedy_match_by_category(predictions, labels, iou_threshold=threshold)
            metric_rows = metrics_rows_from_counts(counts)
            averages = macro_micro_average(metric_rows)
            averages["weighted_f1"] = weighted_f1(metric_rows)

            for row in metric_rows:
                threshold_metrics.append(
                    {
                        "method": method,
                        "iou_threshold": threshold,
                        **row,
                    }
                )

            for row in boundary_rows(matches):
                threshold_boundary.append(
                    {
                        "method": method,
                        "iou_threshold": threshold,
                        **row,
                    }
                )

            by_category = {row["adl_category"]: row for row in metric_rows}
            comparison = {
                "method": method,
                "iou_threshold": threshold,
                "macro_precision": averages["macro_precision"],
                "macro_recall": averages["macro_recall"],
                "macro_f1": averages["macro_f1"],
                "micro_precision": averages["micro_precision"],
                "micro_recall": averages["micro_recall"],
                "micro_f1": averages["micro_f1"],
                "weighted_f1": averages["weighted_f1"],
            }
            categories = sorted(set(COMPARISON_CATEGORIES) | set(by_category))
            for category in categories:
                comparison[f"{category}_F1"] = by_category.get(category, {}).get("f1", 0.0)
            comparison_rows.append(comparison)

            key = str(threshold)
            averages_by_method[method][f"macro_f1_iou_{key}"] = averages["macro_f1"]
            averages_by_method[method][f"micro_f1_iou_{key}"] = averages["micro_f1"]
            averages_by_method[method][f"weighted_f1_iou_{key}"] = averages["weighted_f1"]

        metrics_by_threshold[threshold] = threshold_metrics
        boundary_by_threshold[threshold] = threshold_boundary

    return metrics_by_threshold, boundary_by_threshold, comparison_rows, dict(averages_by_method)


def label_counts(labels: Sequence[ADLInterval]) -> dict[str, int]:
    return dict(sorted(Counter(label.adl_category for label in labels).items()))


def _normalize_adl_categories(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if str(item))
    return (str(value),)


def expand_adl_intervals_for_evaluation5(
    labels: Sequence[ADLInterval],
    category_map: dict[str, Any] | None = None,
) -> list[ADLInterval]:
    """Expand one raw CASAS interval to one or more Evaluation 5 ADL categories."""
    mapping = category_map or EVALUATION5_ADL_CATEGORY_MAP
    unknown_categories = _normalize_adl_categories(mapping.get("__unknown__", ("Other_ADL",)))
    expanded: list[ADLInterval] = []

    for label in labels:
        categories = list(_normalize_adl_categories(mapping.get(label.raw_label)))
        if not categories:
            categories = list(unknown_categories)

        # Preserve contextual relabeling from parse_labeled_casas_intervals, such as
        # Meal_Preparation immediately after sleep being treated as Wake-up.
        if label.adl_category and label.adl_category != "Other_ADL" and label.adl_category not in categories:
            categories.append(label.adl_category)

        seen: set[str] = set()
        for category in categories:
            if not category or category in seen:
                continue
            seen.add(category)
            expanded.append(
                ADLInterval(
                    start_time=label.start_time,
                    end_time=label.end_time,
                    raw_label=label.raw_label,
                    adl_category=category,
                )
            )
    return expanded


def clip_adl_intervals(
    labels: Sequence[ADLInterval],
    start_time: datetime,
    end_time: datetime,
) -> list[ADLInterval]:
    clipped: list[ADLInterval] = []
    for item in labels:
        start = max(item.start_time, start_time)
        end = min(item.end_time, end_time)
        if start < end:
            clipped.append(
                ADLInterval(
                    start_time=start,
                    end_time=end,
                    raw_label=item.raw_label,
                    adl_category=item.adl_category,
                )
            )
    return clipped


def clip_state_intervals(
    state_intervals: Sequence[StateInterval],
    start_time: datetime,
    end_time: datetime,
) -> list[StateInterval]:
    clipped: list[StateInterval] = []
    for item in state_intervals:
        start = max(item.start_time, start_time)
        end = min(item.end_time, end_time)
        if start < end:
            clipped.append(
                StateInterval(
                    start_time=start,
                    end_time=end,
                    state_id=item.state_id,
                )
            )
    return clipped


def compute_time_split_periods(
    labels: Sequence[ADLInterval],
    state_intervals: Sequence[StateInterval],
    train_ratio: float,
    train_start_date: datetime | None = None,
    train_end_date: datetime | None = None,
    test_start_date: datetime | None = None,
    test_end_date: datetime | None = None,
) -> tuple[tuple[datetime, datetime], tuple[datetime, datetime]]:
    """Return chronological train/test periods, using explicit dates when provided."""
    starts = [item.start_time for item in labels] + [item.start_time for item in state_intervals]
    ends = [item.end_time for item in labels] + [item.end_time for item in state_intervals]
    if not starts or not ends:
        raise ValueError("Cannot split empty ADL/state intervals.")

    data_start = min(starts)
    data_end = max(ends)
    if data_start >= data_end:
        raise ValueError("Invalid data period: start must be before end.")

    if train_start_date or train_end_date or test_start_date or test_end_date:
        train_start = train_start_date or data_start
        train_end = train_end_date or test_start_date
        test_start = test_start_date or train_end
        test_end = test_end_date or data_end
        if train_end is None:
            raise ValueError("--train-end-date or --test-start-date is required when using partial explicit dates.")
    else:
        if not 0 < train_ratio < 1:
            raise ValueError("--train-ratio must be between 0 and 1.")
        boundary = data_start + (data_end - data_start) * train_ratio
        train_start = data_start
        train_end = boundary
        test_start = boundary
        test_end = data_end

    if not (train_start < train_end <= test_start < test_end or train_start < train_end == test_start < test_end):
        raise ValueError(
            "Invalid train/test periods. Expected train_start < train_end <= test_start < test_end."
        )
    return (train_start, train_end), (test_start, test_end)


def _overlap_segments(
    start_time: datetime,
    end_time: datetime,
    labels: Sequence[ADLInterval],
    category: str | None = None,
) -> list[tuple[datetime, datetime]]:
    segments: list[tuple[datetime, datetime]] = []
    for label in labels:
        if category is not None and label.adl_category != category:
            continue
        start = max(start_time, label.start_time)
        end = min(end_time, label.end_time)
        if start < end:
            segments.append((start, end))
    if not segments:
        return []

    segments.sort()
    merged = [segments[0]]
    for start, end in segments[1:]:
        previous_start, previous_end = merged[-1]
        if start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def _merge_segments(segments: Sequence[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not segments:
        return []
    sorted_segments = sorted(segments)
    merged = [sorted_segments[0]]
    for start, end in sorted_segments[1:]:
        previous_start, previous_end = merged[-1]
        if start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def _segments_duration_seconds(segments: Sequence[tuple[datetime, datetime]]) -> float:
    return sum(duration_seconds(start, end) for start, end in segments)


def occurrence_overlap_seconds(
    occurrence: MethodOccurrence,
    labels: Sequence[ADLInterval],
    category: str | None = None,
) -> float:
    return _segments_duration_seconds(
        _overlap_segments(occurrence.start_time, occurrence.end_time, labels, category=category)
    )


def detect_other_state_round_trip(
    sequence: Sequence[str],
    other_state_labels: set[str],
) -> tuple[bool, str]:
    for index in range(len(sequence) - 2):
        a, middle, c = sequence[index], sequence[index + 1], sequence[index + 2]
        if a == c and middle in other_state_labels:
            return True, f"other_round_trip: {a} -> {middle} -> {c}"
    return False, ""


def detect_alternating_loop(sequence: Sequence[str]) -> tuple[bool, str]:
    for index in range(len(sequence) - 3):
        a, b, c, d = sequence[index], sequence[index + 1], sequence[index + 2], sequence[index + 3]
        if a == c and b == d and a != b:
            return True, f"alternating_loop: {a} -> {b} -> {c} -> {d}"
    return False, ""


def detect_self_transition(sequence: Sequence[str]) -> tuple[bool, str]:
    for index in range(len(sequence) - 1):
        if sequence[index] == sequence[index + 1]:
            return True, f"self_transition: {sequence[index]} -> {sequence[index + 1]}"
    return False, ""


def is_low_information_sequence(
    sequence: Sequence[str],
    other_state_labels: set[str],
    low_information_threshold: float,
) -> tuple[bool, float]:
    if not sequence:
        return False, 0.0
    low_info_markers = {label.lower() for label in other_state_labels}
    low_info_markers.update(
        {
            "other",
            "unknown",
            "その他",
            "active_sensorsなし",
            "active_sensors:なし",
            "no_active_sensors",
            "active_sensors=[]",
        }
    )
    count = 0
    for state in sequence:
        state_text = str(state).strip()
        state_lower = state_text.lower()
        if state_text in other_state_labels or state_lower in low_info_markers:
            count += 1
            continue
        if "active_sensors" in state_lower and ("なし" in state_text or "[]" in state_text or "none" in state_lower):
            count += 1
    ratio = count / len(sequence)
    return ratio >= low_information_threshold, ratio


def is_contiguous_subsequence(shorter: Sequence[str], longer: Sequence[str]) -> bool:
    if len(shorter) >= len(longer) or not shorter:
        return False
    width = len(shorter)
    target = tuple(shorter)
    return any(tuple(longer[index : index + width]) == target for index in range(len(longer) - width + 1))


def occurrence_containment_rate(
    child_occurrences: Sequence[MethodOccurrence],
    parent_occurrences: Sequence[MethodOccurrence],
) -> float:
    if not child_occurrences:
        return 0.0
    contained = 0
    sorted_parents = sorted(parent_occurrences, key=lambda item: (item.start_time, item.end_time))
    for child in child_occurrences:
        if any(parent.start_time <= child.start_time and child.end_time <= parent.end_time for parent in sorted_parents):
            contained += 1
    return contained / len(child_occurrences)


def compute_fragmentation_by_method(
    patterns_by_method: dict[str, list[MethodPattern]],
    test_occurrences_by_method: dict[str, list[MethodOccurrence]],
    containment_threshold: float,
) -> dict[str, dict[str, dict[str, Any]]]:
    if not 0.0 <= containment_threshold <= 1.0:
        raise ValueError("fragmentation_containment_threshold must be in the range [0, 1]")

    result: dict[str, dict[str, dict[str, Any]]] = {}
    for method, patterns in patterns_by_method.items():
        occurrences_by_pattern: dict[str, list[MethodOccurrence]] = defaultdict(list)
        for occurrence in test_occurrences_by_method.get(method, []):
            occurrences_by_pattern[occurrence.pattern_id].append(occurrence)

        method_result = {
            pattern.pattern_id: {
                "is_fragmented": False,
                "fragment_parent_ids": [],
                "max_occurrence_containment": 0.0,
            }
            for pattern in patterns
        }
        for child in patterns:
            child_occurrences = occurrences_by_pattern.get(child.pattern_id, [])
            for parent in patterns:
                if child.pattern_id == parent.pattern_id:
                    continue
                if child.time_band != parent.time_band:
                    continue
                if not is_contiguous_subsequence(child.sequence, parent.sequence):
                    continue
                containment = occurrence_containment_rate(
                    child_occurrences,
                    occurrences_by_pattern.get(parent.pattern_id, []),
                )
                current = method_result[child.pattern_id]
                if containment > current["max_occurrence_containment"]:
                    current["max_occurrence_containment"] = containment
                if containment >= containment_threshold:
                    current["is_fragmented"] = True
                    current["fragment_parent_ids"].append(parent.pattern_id)
        for values in method_result.values():
            values["fragment_parent_ids"] = sorted(set(values["fragment_parent_ids"]))
        result[method] = method_result
    return result


def train_pattern_adl_assignments(
    patterns_by_method: dict[str, list[MethodPattern]],
    train_occurrences_by_method: dict[str, list[MethodOccurrence]],
    train_labels: Sequence[ADLInterval],
    assigned_adl_purity_threshold: float = 0.10,
    assigned_adl_max_categories: int = 3,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Assign pattern->ADL on train data only."""
    if assigned_adl_purity_threshold < 0:
        raise ValueError("assigned_adl_purity_threshold must be >= 0")
    if assigned_adl_max_categories < 1:
        raise ValueError("assigned_adl_max_categories must be >= 1")

    assignments: dict[str, dict[str, dict[str, Any]]] = {}
    sorted_labels = sorted(train_labels, key=lambda item: (item.start_time, item.end_time))
    for method, patterns in patterns_by_method.items():
        support_by_pattern: Counter[str] = Counter()
        duration_by_pattern: Counter[str] = Counter()
        overlap_by_pattern_category: dict[str, Counter[str]] = defaultdict(Counter)
        total_adl_overlap_by_pattern: Counter[str] = Counter()

        label_index = 0
        occurrences = sorted(
            train_occurrences_by_method.get(method, []),
            key=lambda item: (item.start_time, item.end_time),
        )
        for occurrence in occurrences:
            support_by_pattern[occurrence.pattern_id] += 1
            duration_by_pattern[occurrence.pattern_id] += duration_seconds(
                occurrence.start_time,
                occurrence.end_time,
            )
            while label_index < len(sorted_labels) and sorted_labels[label_index].end_time <= occurrence.start_time:
                label_index += 1
            scan_index = label_index
            any_segments: list[tuple[datetime, datetime]] = []
            while scan_index < len(sorted_labels) and sorted_labels[scan_index].start_time < occurrence.end_time:
                label = sorted_labels[scan_index]
                start = max(occurrence.start_time, label.start_time)
                end = min(occurrence.end_time, label.end_time)
                if start < end:
                    overlap_by_pattern_category[occurrence.pattern_id][label.adl_category] += duration_seconds(start, end)
                    any_segments.append((start, end))
                scan_index += 1
            total_adl_overlap_by_pattern[occurrence.pattern_id] += _segments_duration_seconds(
                _merge_segments(any_segments)
            )

        method_assignments: dict[str, dict[str, Any]] = {}
        for pattern in patterns:
            support = support_by_pattern[pattern.pattern_id]
            total_duration = float(duration_by_pattern[pattern.pattern_id])
            overlap_by_category = overlap_by_pattern_category.get(pattern.pattern_id, Counter())
            total_adl_overlap = float(total_adl_overlap_by_pattern[pattern.pattern_id])

            assigned_adl_set: list[str] = []
            assigned_overlap = 0.0
            if overlap_by_category:
                positive_non_other = {
                    category: float(overlap)
                    for category, overlap in overlap_by_category.items()
                    if category != "Other_ADL" and float(overlap) > 0
                }
                if positive_non_other:
                    max_category, _ = max(
                        positive_non_other.items(),
                        key=lambda item: (item[1], item[0]),
                    )
                    candidate_categories = {
                        category
                        for category, overlap in positive_non_other.items()
                        if total_duration and (float(overlap) / total_duration) >= assigned_adl_purity_threshold
                    }
                    candidate_categories.add(max_category)
                    assigned_adl_set = [
                        category
                        for category, _ in sorted(
                            (
                                (category, positive_non_other[category])
                                for category in candidate_categories
                            ),
                            key=lambda item: (-item[1], item[0]),
                        )[:assigned_adl_max_categories]
                    ]
                elif float(overlap_by_category.get("Other_ADL", 0.0)) > 0:
                    assigned_adl_set = ["Other_ADL"]
                assigned_overlap = min(
                    total_adl_overlap,
                    sum(float(overlap_by_category[category]) for category in assigned_adl_set),
                )
            method_assignments[pattern.pattern_id] = {
                "assigned_adl_train": "|".join(assigned_adl_set),
                "assigned_adl_set_train": assigned_adl_set,
                "train_overlap_by_adl": dict(sorted((key, float(value)) for key, value in overlap_by_category.items())),
                "train_support": support,
                "train_total_duration_seconds": total_duration,
                "train_total_adl_overlap_seconds": total_adl_overlap,
                "train_assigned_adl_overlap_seconds": float(assigned_overlap),
                "train_assigned_adl_purity": (float(assigned_overlap) / total_duration) if total_duration else 0.0,
            }
        assignments[method] = method_assignments
    return assignments


def evaluate_pattern_groundedness(
    patterns_by_method: dict[str, list[MethodPattern]],
    train_assignments: dict[str, dict[str, dict[str, Any]]],
    test_occurrences_by_method: dict[str, list[MethodOccurrence]],
    test_labels: Sequence[ADLInterval],
    min_overlap_seconds: float,
    grounded_hit_threshold: float,
    grounded_purity_threshold: float,
    useless_hit_threshold: float,
    useless_purity_threshold: float,
    include_no_test_support_in_denominator: bool = False,
    exclude_other_adl_from_any: bool = True,
    other_state_labels: set[str] | None = None,
    fragmentation_containment_threshold: float = 0.7,
    low_information_threshold: float = 0.5,
) -> tuple[list[dict], list[dict], dict[str, Any]]:
    """Compute pattern-level Evaluation 5 metrics on test data."""
    detail_rows: list[dict] = []
    summary_rows: list[dict] = []
    summary_by_method: dict[str, Any] = {}
    excluded_any_categories = {"Other_ADL"} if exclude_other_adl_from_any else set()
    other_labels = other_state_labels or set(DEFAULT_OTHER_STATE_LABELS)
    fragmentation_by_method = compute_fragmentation_by_method(
        patterns_by_method=patterns_by_method,
        test_occurrences_by_method=test_occurrences_by_method,
        containment_threshold=fragmentation_containment_threshold,
    )

    for method, patterns in patterns_by_method.items():
        support_by_pattern: Counter[str] = Counter()
        duration_by_pattern: Counter[str] = Counter()
        assigned_hit_by_pattern: Counter[str] = Counter()
        any_hit_by_pattern: Counter[str] = Counter()
        assigned_overlap_by_pattern: Counter[str] = Counter()
        any_overlap_by_pattern: Counter[str] = Counter()

        assigned_by_pattern = {
            pattern.pattern_id: set(
                train_assignments.get(method, {}).get(pattern.pattern_id, {}).get("assigned_adl_set_train", [])
            )
            for pattern in patterns
        }
        sorted_labels = sorted(test_labels, key=lambda item: (item.start_time, item.end_time))
        label_index = 0
        occurrences = sorted(
            test_occurrences_by_method.get(method, []),
            key=lambda item: (item.start_time, item.end_time),
        )
        for occurrence in occurrences:
            pattern_id = occurrence.pattern_id
            assigned_adl_set = assigned_by_pattern.get(pattern_id, set())
            support_by_pattern[pattern_id] += 1
            duration_by_pattern[pattern_id] += duration_seconds(occurrence.start_time, occurrence.end_time)

            any_segments: list[tuple[datetime, datetime]] = []
            assigned_segments: list[tuple[datetime, datetime]] = []
            while label_index < len(sorted_labels) and sorted_labels[label_index].end_time <= occurrence.start_time:
                label_index += 1
            scan_index = label_index
            while scan_index < len(sorted_labels) and sorted_labels[scan_index].start_time < occurrence.end_time:
                label = sorted_labels[scan_index]
                start = max(occurrence.start_time, label.start_time)
                end = min(occurrence.end_time, label.end_time)
                if start < end:
                    if label.adl_category not in excluded_any_categories:
                        any_segments.append((start, end))
                    if assigned_adl_set and label.adl_category in assigned_adl_set:
                        assigned_segments.append((start, end))
                scan_index += 1

            any_overlap = _segments_duration_seconds(_merge_segments(any_segments))
            assigned_overlap = _segments_duration_seconds(_merge_segments(assigned_segments))
            any_overlap_by_pattern[pattern_id] += any_overlap
            assigned_overlap_by_pattern[pattern_id] += assigned_overlap
            if any_overlap >= min_overlap_seconds:
                any_hit_by_pattern[pattern_id] += 1
            if assigned_overlap >= min_overlap_seconds:
                assigned_hit_by_pattern[pattern_id] += 1

        method_rows: list[dict] = []
        for pattern in patterns:
            assignment = train_assignments.get(method, {}).get(pattern.pattern_id, {})
            train_support = int(assignment.get("train_support", 0))
            assigned_adl_set = sorted(str(item) for item in assignment.get("assigned_adl_set_train", []))
            assigned_adl = "|".join(assigned_adl_set)
            test_support = support_by_pattern[pattern.pattern_id]
            test_duration = float(duration_by_pattern[pattern.pattern_id])
            assigned_hit_count = assigned_hit_by_pattern[pattern.pattern_id]
            any_hit_count = any_hit_by_pattern[pattern.pattern_id]
            assigned_overlap_seconds = float(assigned_overlap_by_pattern[pattern.pattern_id])
            any_overlap_seconds = float(any_overlap_by_pattern[pattern.pattern_id])

            assigned_hit_rate = assigned_hit_count / test_support if test_support else 0.0
            any_hit_rate = any_hit_count / test_support if test_support else 0.0
            assigned_purity = assigned_overlap_seconds / test_duration if test_duration else 0.0
            any_purity = any_overlap_seconds / test_duration if test_duration else 0.0

            if train_support == 0:
                status = "no_train_support"
            elif not assigned_adl_set:
                status = "no_assigned_adl"
            elif test_support == 0:
                status = "no_test_support"
            else:
                status = "evaluated"

            denominator_eligible = train_support > 0 and (
                test_support > 0 or include_no_test_support_in_denominator
            )
            is_adl_grounded = bool(
                denominator_eligible
                and assigned_adl_set
                and (
                    assigned_hit_rate >= grounded_hit_threshold
                    or assigned_purity >= grounded_purity_threshold
                )
            )
            is_useless_a = bool(
                denominator_eligible
                and test_support > 0
                and any_hit_rate < useless_hit_threshold
                and any_purity < useless_purity_threshold
            )
            is_structural_self, structural_self_reason = detect_self_transition(pattern.sequence)
            is_useless_b, useless_b_reason = detect_other_state_round_trip(pattern.sequence, other_labels)
            is_useless_c, useless_c_reason = detect_alternating_loop(pattern.sequence)
            is_structural_useless = bool(is_structural_self or is_useless_b or is_useless_c)
            is_low_information, low_information_ratio = is_low_information_sequence(
                pattern.sequence,
                other_labels,
                low_information_threshold=low_information_threshold,
            )
            is_adl_unsupported = bool(
                denominator_eligible
                and test_support > 0
                and any_hit_rate < useless_hit_threshold
                and any_purity < useless_purity_threshold
            )
            fragment_info = fragmentation_by_method.get(method, {}).get(
                pattern.pattern_id,
                {
                    "is_fragmented": False,
                    "fragment_parent_ids": [],
                    "max_occurrence_containment": 0.0,
                },
            )
            is_fragmented = bool(denominator_eligible and fragment_info["is_fragmented"])
            is_contextless_useless = bool(
                denominator_eligible
                and (is_structural_useless or is_low_information or is_adl_unsupported)
            )
            is_useful_non_redundant = bool(
                denominator_eligible
                and is_adl_grounded
                and not is_contextless_useless
                and not is_fragmented
            )
            useless_reasons: list[str] = []
            if is_useless_a:
                useless_reasons.append("useless_a: low_any_adl_overlap")
            if denominator_eligible and is_structural_self:
                useless_reasons.append("structural_useless: self_transition")
            if denominator_eligible and is_useless_b:
                useless_reasons.append("useless_b: other_round_trip")
            if denominator_eligible and is_useless_c:
                useless_reasons.append("useless_c: alternating_loop")
            is_useless = bool(denominator_eligible and (is_useless_a or is_useless_b or is_useless_c))

            row = {
                "method": method,
                "pattern_id": pattern.pattern_id,
                "pattern_name": pattern.pattern_name,
                "sequence": sequence_text(pattern.sequence),
                "time_band": pattern.time_band,
                "input_count": pattern.count if pattern.count is not None else "",
                "pattern_source": pattern.pattern_source,
                "support_transactions": pattern.support_transactions if pattern.support_transactions is not None else "",
                "support_ratio": f"{pattern.support_ratio:.6f}" if pattern.support_ratio is not None else "",
                "train_occurrence_count": (
                    pattern.train_occurrence_count if pattern.train_occurrence_count is not None else ""
                ),
                "median_duration_seconds": (
                    f"{pattern.median_duration_seconds:.3f}" if pattern.median_duration_seconds is not None else ""
                ),
                "p90_duration_seconds": (
                    f"{pattern.p90_duration_seconds:.3f}" if pattern.p90_duration_seconds is not None else ""
                ),
                "is_fp_filtered_out": (
                    pattern.is_fp_filtered_out if pattern.is_fp_filtered_out is not None else ""
                ),
                "fp_filter_reason": pattern.fp_filter_reason,
                "transition_joint_probability": (
                    f"{pattern.transition_joint_probability:.6f}"
                    if pattern.transition_joint_probability is not None
                    else ""
                ),
                "transition_min_step_probability": (
                    f"{pattern.transition_min_step_probability:.6f}"
                    if pattern.transition_min_step_probability is not None
                    else ""
                ),
                "train_support": train_support,
                "test_support": test_support,
                "assigned_adl_train": assigned_adl,
                "assigned_adl_set_train": assigned_adl,
                "train_overlap_by_adl_json": json.dumps(
                    assignment.get("train_overlap_by_adl", {}),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "train_total_duration_seconds": f"{float(assignment.get('train_total_duration_seconds', 0.0)):.3f}",
                "train_assigned_adl_overlap_seconds": f"{float(assignment.get('train_assigned_adl_overlap_seconds', 0.0)):.3f}",
                "train_assigned_adl_set_purity": f"{float(assignment.get('train_assigned_adl_purity', 0.0)):.6f}",
                "train_assigned_adl_purity": f"{float(assignment.get('train_assigned_adl_purity', 0.0)):.6f}",
                "assigned_adl_hit_rate_test": f"{assigned_hit_rate:.6f}",
                "assigned_adl_purity_test": f"{assigned_purity:.6f}",
                "any_adl_hit_rate_test": f"{any_hit_rate:.6f}",
                "any_adl_purity_test": f"{any_purity:.6f}",
                "is_adl_grounded": int(is_adl_grounded),
                "is_useless_a": int(is_useless_a),
                "is_useless_b": int(is_useless_b),
                "is_useless_c": int(is_useless_c),
                "is_useless": int(is_useless),
                "is_contextless_useless": int(is_contextless_useless),
                "is_structural_useless": int(is_structural_useless),
                "is_low_information": int(is_low_information),
                "low_information_ratio": f"{low_information_ratio:.6f}",
                "is_adl_unsupported": int(is_adl_unsupported),
                "is_fragmented": int(is_fragmented),
                "fragment_parent_ids": "|".join(fragment_info["fragment_parent_ids"]),
                "max_occurrence_containment": f"{float(fragment_info['max_occurrence_containment']):.6f}",
                "is_useful_non_redundant": int(is_useful_non_redundant),
                "useless_reason": "; ".join(useless_reasons),
                "structural_useless_reason": "; ".join(
                    reason
                    for reason in [structural_self_reason, useless_b_reason, useless_c_reason]
                    if reason
                ),
                "useless_b_reason": useless_b_reason,
                "useless_c_reason": useless_c_reason,
                "evaluation_status": status,
            }
            method_rows.append(row)
            detail_rows.append(row)

        denominator_rows = [
            row
            for row in method_rows
            if int(row["train_support"]) > 0
            and (int(row["test_support"]) > 0 or include_no_test_support_in_denominator)
        ]
        num_evaluable = len(denominator_rows)
        num_contextless_useless = sum(int(row["is_contextless_useless"]) for row in denominator_rows)
        num_fragmented = sum(int(row["is_fragmented"]) for row in denominator_rows)
        num_useful_non_redundant = sum(int(row["is_useful_non_redundant"]) for row in denominator_rows)

        summary = {
            "method": method,
            "useful_non_redundant_pattern_rate": (
                num_useful_non_redundant / num_evaluable
            ) if num_evaluable else 0.0,
            "contextless_useless_rate": (num_contextless_useless / num_evaluable) if num_evaluable else 0.0,
            "fragmentation_rate": (num_fragmented / num_evaluable) if num_evaluable else 0.0,
        }
        summary_rows.append(summary)
        summary_by_method[method] = summary

    return detail_rows, summary_rows, summary_by_method


def write_pattern_groundedness_outputs(
    output_dir: Path,
    pattern_detail_rows: Sequence[dict],
    summary_rows: Sequence[dict],
    summary: dict,
    summary_by_run_rows: Sequence[dict] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    include_run = any("run" in row for row in pattern_detail_rows)
    pattern_detail_fieldnames = [
        *(["run"] if include_run else []),
        "method",
        "pattern_id",
        "pattern_name",
        "sequence",
        "time_band",
        "input_count",
        "pattern_source",
        "support_transactions",
        "support_ratio",
        "train_occurrence_count",
        "median_duration_seconds",
        "p90_duration_seconds",
        "is_fp_filtered_out",
        "fp_filter_reason",
        "transition_joint_probability",
        "transition_min_step_probability",
        "train_support",
        "test_support",
        "assigned_adl_train",
        "assigned_adl_set_train",
        "train_overlap_by_adl_json",
        "train_total_duration_seconds",
        "train_assigned_adl_overlap_seconds",
        "train_assigned_adl_set_purity",
        "train_assigned_adl_purity",
        "is_contextless_useless",
        "is_structural_useless",
        "is_low_information",
        "is_adl_unsupported",
        "is_fragmented",
        "fragment_parent_ids",
        "max_occurrence_containment",
        "is_useful_non_redundant",
        "structural_useless_reason",
        "evaluation_status",
    ]
    write_csv_rows(
        output_dir / "evaluation5_pattern_details.csv",
        [{key: row.get(key, "") for key in pattern_detail_fieldnames} for row in pattern_detail_rows],
        pattern_detail_fieldnames,
    )
    write_csv_rows(
        output_dir / "evaluation5_summary_by_method.csv",
        [{key: row.get(key, "") for key in evaluation5_summary_fieldnames(summary_rows)} for row in summary_rows],
        evaluation5_summary_fieldnames(summary_rows),
    )
    if summary_by_run_rows is not None:
        by_run_fieldnames = [
            "run",
            "method",
            "useful_non_redundant_pattern_rate",
            "fragmentation_rate",
            "contextless_useless_rate",
        ]
        write_csv_rows(
            output_dir / "evaluation5_summary_by_method_by_run.csv",
            [{key: row.get(key, "") for key in by_run_fieldnames} for row in summary_by_run_rows],
            by_run_fieldnames,
        )
    (output_dir / "evaluation5_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def evaluation5_summary_fieldnames(summary_rows: Sequence[dict]) -> list[str]:
    metric_names = [
        "useful_non_redundant_pattern_rate",
        "fragmentation_rate",
        "contextless_useless_rate",
    ]
    fieldnames = ["method"]
    if any("num_runs" in row for row in summary_rows):
        fieldnames.append("num_runs")
    for metric in metric_names:
        fieldnames.append(metric)
        std_name = f"{metric}_std"
        if any(std_name in row for row in summary_rows):
            fieldnames.append(std_name)
    return fieldnames


def write_adl_correspondence_outputs(
    output_dir: Path,
    labels: Sequence[ADLInterval],
    occurrences_by_method: dict[str, list[MethodOccurrence]],
    mappings_by_method: dict[str, list[MethodMapping]],
    merged_predictions_by_method: dict[str, list] | None,
    filtered_predictions_by_method: dict[str, list] | None,
    metrics_by_threshold: dict[float, list[dict]],
    boundary_by_threshold: dict[float, list[dict]],
    comparison_rows: Sequence[dict],
    hit_metric_rows: Sequence[dict] | None,
    hit_detail_rows: Sequence[dict] | None,
    summary: dict,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    write_csv_rows(
        output_dir / "adl_label_intervals.csv",
        [
            {
                "start_time": item.start_time.isoformat(sep=" "),
                "end_time": item.end_time.isoformat(sep=" "),
                "raw_label": item.raw_label,
                "adl_category": item.adl_category,
            }
            for item in labels
        ],
        ["start_time", "end_time", "raw_label", "adl_category"],
    )

    occurrence_rows = []
    for occurrences in occurrences_by_method.values():
        for item in occurrences:
            occurrence_rows.append(
                {
                    "method": item.method,
                    "pattern_id": item.pattern_id,
                    "pattern_name": item.pattern_name,
                    "sequence": sequence_text(item.sequence),
                    "occurrence_id": item.occurrence_id,
                    "start_time": item.start_time.isoformat(sep=" "),
                    "end_time": item.end_time.isoformat(sep=" "),
                }
            )
    write_csv_rows(
        output_dir / "pattern_occurrences_by_method.csv",
        occurrence_rows,
        [
            "method",
            "pattern_id",
            "pattern_name",
            "sequence",
            "occurrence_id",
            "start_time",
            "end_time",
        ],
    )

    mapping_rows = []
    for mappings in mappings_by_method.values():
        for item in mappings:
            mapping_rows.append(
                {
                    "method": item.method,
                    "pattern_id": item.pattern_id,
                    "pattern_name": item.pattern_name,
                    "sequence": sequence_text(item.sequence),
                    "input_count": item.input_count if item.input_count is not None else "",
                    "support": item.support,
                    "assigned_adl": item.assigned_adl,
                    "adl_confidence": f"{item.adl_confidence:.6f}",
                    "total_duration_minutes": f"{item.total_duration_seconds / 60.0:.6f}",
                    "total_duration_seconds": f"{item.total_duration_seconds:.3f}",
                }
            )
    write_csv_rows(
        output_dir / "pattern_adl_mapping_by_method.csv",
        mapping_rows,
        [
            "method",
            "pattern_id",
            "pattern_name",
            "sequence",
            "input_count",
            "support",
            "assigned_adl",
            "adl_confidence",
            "total_duration_minutes",
            "total_duration_seconds",
        ],
    )

    if merged_predictions_by_method is not None:
        write_csv_rows(
            output_dir / "merged_predictions_by_method.csv",
            prediction_rows_by_method(merged_predictions_by_method, include_duration=False),
            [
                "method",
                "prediction_id",
                "predicted_adl",
                "start_time",
                "end_time",
                "num_merged_occurrences",
                "source_pattern_ids",
                "source_pattern_names",
            ],
        )

    if filtered_predictions_by_method is not None:
        write_csv_rows(
            output_dir / "filtered_predictions_by_method.csv",
            prediction_rows_by_method(filtered_predictions_by_method, include_duration=True),
            [
                "method",
                "prediction_id",
                "predicted_adl",
                "start_time",
                "end_time",
                "num_merged_occurrences",
                "source_pattern_ids",
                "source_pattern_names",
                "duration_seconds",
            ],
        )

    for threshold, rows in metrics_by_threshold.items():
        suffix = str(threshold)
        write_csv_rows(
            output_dir / f"adl_metrics_iou_{suffix}.csv",
            rows,
            [
                "method",
                "iou_threshold",
                "adl_category",
                "tp",
                "fp",
                "fn",
                "precision",
                "recall",
                "f1",
            ],
        )
        write_csv_rows(
            output_dir / f"adl_boundary_metrics_iou_{suffix}.csv",
            boundary_by_threshold.get(threshold, []),
            [
                "method",
                "iou_threshold",
                "adl_category",
                "mean_start_error",
                "median_abs_start_error",
                "mean_end_error",
                "median_abs_end_error",
                "mean_iou",
                "matched_count",
            ],
        )

    comparison_fieldnames = comparison_fieldnames_from_rows(comparison_rows)
    write_csv_rows(
        output_dir / "adl_method_comparison.csv",
        comparison_rows,
        comparison_fieldnames,
    )

    if hit_metric_rows is not None:
        write_csv_rows(
            output_dir / "adl_interval_hit_metrics_by_method.csv",
            hit_metric_rows,
            [
                "method",
                "hit_type",
                "adl_category",
                "true_intervals",
                "hit_intervals",
                "missed_intervals",
                "hit_rate",
                "prediction_intervals",
                "matched_prediction_intervals",
                "unmatched_prediction_intervals",
                "prediction_hit_precision",
            ],
        )

    if hit_detail_rows is not None:
        write_csv_rows(
            output_dir / "adl_interval_hit_details_by_method.csv",
            hit_detail_rows,
            [
                "method",
                "hit_type",
                "true_adl",
                "start_time",
                "end_time",
                "is_hit",
                "matched_prediction_count",
                "matched_prediction_ids",
            ],
        )

    (output_dir / "evaluation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def prediction_rows_by_method(predictions_by_method: dict[str, list], include_duration: bool) -> list[dict]:
    rows: list[dict] = []
    for method, predictions in predictions_by_method.items():
        for prediction in predictions:
            row = {
                "method": method,
                "prediction_id": prediction.prediction_id,
                "predicted_adl": prediction.assigned_adl,
                "start_time": prediction.start_time.isoformat(sep=" "),
                "end_time": prediction.end_time.isoformat(sep=" "),
                "num_merged_occurrences": prediction.num_merged_occurrences,
                "source_pattern_ids": "|".join(prediction.source_pattern_ids),
                "source_pattern_names": "|".join(prediction.source_pattern_names),
            }
            if include_duration:
                row["duration_seconds"] = f"{duration_seconds(prediction.start_time, prediction.end_time):.3f}"
            rows.append(row)
    return rows


def comparison_fieldnames_from_rows(rows: Sequence[dict]) -> list[str]:
    base = [
        "method",
        "iou_threshold",
        "Sleep_F1",
        "Wake-up_F1",
        "Meal_F1",
        "Outing_F1",
        "Relax_F1",
        "Housework_F1",
        "Work_F1",
        "Other_ADL_F1",
        "macro_precision",
        "macro_recall",
        "macro_f1",
        "micro_precision",
        "micro_recall",
        "micro_f1",
        "weighted_f1",
    ]
    extra = sorted({key for row in rows for key in row if key.endswith("_F1")} - set(base))
    return base + extra


def aggregate_macro_micro(
    averages_by_method: dict[str, dict[str, float]],
    metric_name: str,
) -> dict[str, dict[str, float]]:
    grouped: dict[str, dict[str, float]] = {}
    for method, values in averages_by_method.items():
        grouped[method] = {
            key: value
            for key, value in values.items()
            if key.startswith(metric_name)
        }
    return grouped


def mean_by_method_and_threshold(rows: Sequence[dict], key: str) -> dict[str, float]:
    values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        values[row["method"]].append(float(row.get(key, 0.0)))
    return {
        method: statistics.fmean(items) if items else 0.0
        for method, items in sorted(values.items())
    }
