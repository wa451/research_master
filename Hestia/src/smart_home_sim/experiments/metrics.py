"""Exact sequence recovery and household-level, multi-label ADL time scores.

Canonical ground truth is selected only from training target episodes after the
observable log has been mapped into the training-derived representative-state
space. Held-out truth is used only for scoring and fragmentation containment.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from itertools import pairwise
from pathlib import Path
from typing import Any

from smart_home_sim.experiments.artifacts import read_json
from smart_home_sim.experiments.scenarios import TARGET_ACTIVITIES

LABELS = frozenset(
    {
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
    }
)
SequenceKey = tuple[str, tuple[str, ...]]
Span = tuple[datetime, datetime]


@dataclass(frozen=True)
class State:
    start: datetime
    end: datetime
    state: str


@dataclass(frozen=True)
class Occurrence:
    start: datetime
    end: datetime
    mode: str
    sequence: tuple[str, ...]

    @property
    def key(self) -> SequenceKey:
        return self.mode, self.sequence


def mode_at(time: datetime) -> str:
    return (
        "Midnight"
        if time.hour < 6
        else "Morning"
        if time.hour < 10
        else ("Daytime" if time.hour < 18 else "Night")
    )


def valid_sequence(sequence: tuple[str, ...]) -> bool:
    return (
        2 <= len(sequence) <= 4
        and not set(sequence) & {"Other", "その他"}
        and all(a != b for a, b in pairwise(sequence))
        and not (len(sequence) == 4 and sequence[:2] == sequence[2:])
    )


def load_series(path: Path, timezone: tzinfo | None) -> list[State]:
    states = []
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            start = datetime.fromisoformat(row["start_time"])
            end = datetime.fromisoformat(row["end_time"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone)
            if start.utcoffset() is None or end.utcoffset() is None or end <= start:
                raise ValueError("invalid state interval")
            if states and states[-1].end > start:
                raise ValueError("state intervals must be ordered and non-overlapping")
            states.append(State(start, end, row["state_id"]))
    return states


def occurrences(series: list[State], start: datetime, end: datetime) -> list[Occurrence]:
    blocks: dict[tuple[datetime, str], list[State]] = defaultdict(list)
    for item in series:
        left, right = max(item.start, start), min(item.end, end)
        while left < right:
            midnight = left.replace(hour=0, minute=0, second=0, microsecond=0)
            hour = 6 if left.hour < 6 else 10 if left.hour < 10 else 18 if left.hour < 18 else 24
            stop = min(right, midnight + timedelta(hours=hour))
            block = blocks[midnight, mode_at(left)]
            if block and block[-1].state == item.state and block[-1].end == left:
                block[-1] = State(block[-1].start, stop, item.state)
            else:
                block.append(State(left, stop, item.state))
            left = stop
    result = []
    for (_, mode), block in sorted(blocks.items()):
        for index in range(len(block)):
            for length in (2, 3, 4):
                selected = block[index : index + length]
                sequence = tuple(item.state for item in selected)
                if len(selected) != length or not valid_sequence(sequence):
                    continue
                if any(a.end != b.start for a, b in pairwise(selected)):
                    continue
                result.append(Occurrence(selected[0].start, selected[-1].end, mode, sequence))
    return result


def catalog_from_training(
    items: list[Occurrence],
    activities: list[dict[str, Any]],
    split: datetime,
    min_support: int,
    target_activity_ids: Collection[str] = TARGET_ACTIVITIES,
) -> tuple[dict[SequenceKey, dict[str, Any]], dict[str, int]]:
    support: Counter[SequenceKey] = Counter()
    labels: dict[SequenceKey, set[str]] = defaultdict(set)
    diagnostics: Counter[str] = Counter()
    for activity in activities:
        if not activity.get("start") or not activity.get("end"):
            continue
        left, right = (
            datetime.fromisoformat(activity["start"]),
            datetime.fromisoformat(activity["end"]),
        )
        if (
            activity["activity_id"] not in target_activity_ids
            or right > split
            or not activity["complete"]
        ):
            continue
        diagnostics["complete_target_episodes"] += 1
        keys = {item.key for item in items if left <= item.start and item.end <= right}
        if keys:
            diagnostics["episodes_with_representable_sequence"] += 1
        for key in keys:
            support[key] += 1
            labels[key].add(activity["label"])
    catalog = {
        key: {"train_episode_support": count, "labels": sorted(labels[key])}
        for key, count in sorted(support.items())
        if count >= min_support
    }
    return catalog, dict(diagnostics)


def _episode_state_blocks(
    series: list[State], start: datetime, end: datetime
) -> list[tuple[str, tuple[str, ...]]]:
    blocks: list[tuple[str, list[str]]] = []
    previous_end: datetime | None = None
    previous_day = None
    for item in series:
        left, right = max(start, item.start), min(end, item.end)
        while left < right:
            midnight = left.replace(hour=0, minute=0, second=0, microsecond=0)
            boundary_hour = (
                6 if left.hour < 6 else 10 if left.hour < 10 else 18 if left.hour < 18 else 24
            )
            stop = min(right, midnight + timedelta(hours=boundary_hour))
            mode = mode_at(left)
            day = left.date()
            is_barrier = item.state in {"Other", "その他"}
            contiguous = previous_end == left and previous_day == day
            if is_barrier:
                previous_end = None
                previous_day = None
            else:
                if not blocks or blocks[-1][0] != mode or not contiguous:
                    blocks.append((mode, [item.state]))
                elif blocks[-1][1][-1] != item.state:
                    blocks[-1][1].append(item.state)
                previous_end = stop
                previous_day = day
            left = stop
    return [(mode, tuple(states)) for mode, states in blocks if states]


def project_target_episodes(
    series: list[State], target_episodes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    projected = []
    for episode in target_episodes:
        blocks: list[tuple[str, tuple[str, ...]]] = []
        if episode.get("generated") is not False and episode.get("start") and episode.get("end"):
            left = datetime.fromisoformat(episode["start"])
            right = datetime.fromisoformat(episode["end"])
            if right > left:
                blocks = _episode_state_blocks(series, left, right)
        serialized = [{"time_band": mode, "sequence": list(sequence)} for mode, sequence in blocks]
        projected.append(
            {
                **episode,
                "representative_state_sequence": (list(blocks[0][1]) if len(blocks) == 1 else None),
                "representative_state_sequences": serialized,
            }
        )
    return projected


def _subsequences(sequence: tuple[str, ...], *, proper: bool = False) -> set[tuple[str, ...]]:
    maximum = min(4, len(sequence) - 1 if proper else len(sequence))
    return {
        candidate
        for length in range(2, maximum + 1)
        for index in range(len(sequence) - length + 1)
        if valid_sequence(candidate := sequence[index : index + length])
    }


def _episode_keys(episode: dict[str, Any]) -> set[SequenceKey]:
    return {
        (block["time_band"], sequence)
        for block in episode["representative_state_sequences"]
        for sequence in _subsequences(tuple(block["sequence"]))
    }


def build_gold_catalog(
    projected: list[dict[str, Any]],
    split: datetime,
    end: datetime,
    min_support: int,
) -> list[dict[str, Any]]:
    train = [
        episode
        for episode in projected
        if episode.get("complete")
        and episode.get("start")
        and episode.get("end")
        and datetime.fromisoformat(episode["end"]) <= split
    ]
    test = [
        episode
        for episode in projected
        if episode.get("complete")
        and episode.get("start")
        and episode.get("end")
        and datetime.fromisoformat(episode["start"]) >= split
        and datetime.fromisoformat(episode["end"]) <= end
    ]
    support: Counter[tuple[str, str, tuple[str, ...]]] = Counter()
    metadata: dict[str, dict[str, Any]] = {}
    for episode in train:
        target_id = episode["target_id"]
        metadata.setdefault(target_id, episode)
        for mode, sequence in _episode_keys(episode):
            support[target_id, mode, sequence] += 1

    canonical_candidates = []
    grouped: dict[tuple[str, str], list[tuple[tuple[str, ...], int]]] = defaultdict(list)
    for (target_id, mode, sequence), count in support.items():
        if count >= min_support:
            grouped[target_id, mode].append((sequence, count))
    for (target_id, mode), candidates in sorted(grouped.items()):
        maximum_support = max(count for _, count in candidates)
        maximum_length = max(
            len(sequence) for sequence, count in candidates if count == maximum_support
        )
        for sequence, count in sorted(candidates):
            if count == maximum_support and len(sequence) == maximum_length:
                canonical_candidates.append((target_id, mode, sequence, count))

    canonical_rows = []
    canonical_ids: dict[tuple[str, str, tuple[str, ...]], str] = {}
    for index, (target_id, mode, sequence, count) in enumerate(
        sorted(canonical_candidates), start=1
    ):
        gold_id = f"G-C-{index:04d}"
        canonical_ids[target_id, mode, sequence] = gold_id
        info = metadata[target_id]
        key = mode, sequence
        canonical_rows.append(
            {
                "gold_pattern_id": gold_id,
                "target_id": target_id,
                "activity_id": info["activity_id"],
                "activity": info.get("label"),
                "resident_id": info["resident_id"],
                "time_band": mode,
                "representative_state_sequence": list(sequence),
                "is_canonical": True,
                "canonical_parent": True,
                "parent_gold_pattern": None,
                "parent_gold_pattern_ids": [],
                "train_episode_support": count,
                "test_episode_count": sum(
                    key in _episode_keys(episode)
                    for episode in test
                    if episode["target_id"] == target_id
                ),
            }
        )

    global_canonical_keys = {
        (row["time_band"], tuple(row["representative_state_sequence"])) for row in canonical_rows
    }
    fragments: dict[tuple[str, str, tuple[str, ...]], set[str]] = defaultdict(set)
    for target_id, mode, sequence, _ in canonical_candidates:
        parent_id = canonical_ids[target_id, mode, sequence]
        for fragment in _subsequences(sequence, proper=True):
            if (mode, fragment) not in global_canonical_keys:
                fragments[target_id, mode, fragment].add(parent_id)
    fragment_rows = []
    for index, ((target_id, mode, sequence), parent_ids) in enumerate(
        sorted(fragments.items()), start=1
    ):
        info = metadata[target_id]
        key = mode, sequence
        ordered_parents = sorted(parent_ids)
        fragment_rows.append(
            {
                "gold_pattern_id": f"G-F-{index:04d}",
                "target_id": target_id,
                "activity_id": info["activity_id"],
                "activity": info.get("label"),
                "resident_id": info["resident_id"],
                "time_band": mode,
                "representative_state_sequence": list(sequence),
                "is_canonical": False,
                "canonical_parent": False,
                "parent_gold_pattern": ordered_parents[0],
                "parent_gold_pattern_ids": ordered_parents,
                "train_episode_support": support[target_id, mode, sequence],
                "test_episode_count": sum(
                    key in _episode_keys(episode)
                    for episode in test
                    if episode["target_id"] == target_id
                ),
            }
        )
    return [*canonical_rows, *fragment_rows]


def exact_pattern_scores(gold: set[SequenceKey], predicted: set[SequenceKey]) -> dict[str, Any]:
    tp = len(gold & predicted)
    fp = len(predicted - gold)
    fn = len(gold - predicted)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "num_gold_patterns": len(gold),
        "num_extracted_patterns": len(predicted),
    }


def _occurrence_containment(
    child_occurrences: list[Occurrence], parent_spans: list[Span]
) -> float | None:
    if not child_occurrences:
        return None
    parents = merge_spans(parent_spans)
    contained = sum(
        any(left <= child.start and child.end <= right for left, right in parents)
        for child in child_occurrences
    )
    return contained / len(child_occurrences)


def parse_predictions(payload: Any, *, require_labels: bool) -> dict[SequenceKey, set[str]]:
    if not isinstance(payload, list):
        raise ValueError("predictions must be a JSON list (empty list is a valid completed result)")
    predictions: dict[SequenceKey, set[str]] = defaultdict(set)
    for record in payload:
        if not isinstance(record, dict):
            raise ValueError("prediction must be an object")
        sequence = record.get("sequence", record.get("遷移のパターン"))
        if (
            not isinstance(sequence, list)
            or not all(isinstance(item, str) for item in sequence)
            or not 2 <= len(sequence) <= 4
        ):
            raise ValueError("prediction sequence must contain 2-4 state IDs")
        interpretations = record.get("time_band_interpretations")
        if interpretations is None:
            interpretations = {record.get("mode", "all"): record}
        if not isinstance(interpretations, dict) or not interpretations:
            raise ValueError("time_band_interpretations must be a non-empty object")
        for mode, interpretation in interpretations.items():
            if mode not in {"all", "Midnight", "Morning", "Daytime", "Night"}:
                raise ValueError(f"unknown prediction mode: {mode}")
            if not isinstance(interpretation, dict):
                raise ValueError("interpretation must be an object")
            labels = interpretation.get("ADL系列ラベル", interpretation.get("labels", []))
            if (
                not isinstance(labels, list)
                or not all(isinstance(label, str) for label in labels)
                or set(labels) - LABELS
                or (require_labels and not labels)
            ):
                raise ValueError(
                    "ADL labels must use the documented vocabulary and cannot be missing"
                )
            modes = ["Midnight", "Morning", "Daytime", "Night"] if mode == "all" else [mode]
            for band in modes:
                predictions[band, tuple(sequence)].update(labels)
    return dict(predictions)


def merge_spans(spans: list[Span]) -> list[Span]:
    merged: list[Span] = []
    for start, end in sorted(spans):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def seconds(spans: list[Span]) -> float:
    return sum((end - start).total_seconds() for start, end in merge_spans(spans))


def intersections(first: list[Span], second: list[Span]) -> list[Span]:
    left, right = merge_spans(first), merge_spans(second)
    result = []
    a = b = 0
    while a < len(left) and b < len(right):
        start, end = max(left[a][0], right[b][0]), min(left[a][1], right[b][1])
        if start < end:
            result.append((start, end))
        if left[a][1] <= right[b][1]:
            a += 1
        else:
            b += 1
    return result


def ratios(tp: float, predicted: float, actual: float) -> dict[str, float | None]:
    return {
        "precision": tp / predicted if predicted else None,
        "recall": tp / actual if actual else None,
        "f1": 2 * tp / (predicted + actual) if predicted + actual else None,
    }


def adl_scores(
    predictions: dict[SequenceKey, set[str]],
    items: list[Occurrence],
    activities: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    truth: dict[str, list[Span]] = defaultdict(list)
    guessed: dict[str, list[Span]] = defaultdict(list)
    for activity in activities:
        left = max(start, datetime.fromisoformat(activity["start"]))
        right = min(end, datetime.fromisoformat(activity["end"]))
        if left < right:
            truth[activity["label"]].append((left, right))
    domain = merge_spans([span for spans in truth.values() for span in spans])
    for item in items:
        for label in predictions.get(item.key, set()):
            guessed[label].append((item.start, item.end))
    rows = {}
    totals = [0.0, 0.0, 0.0]
    for label in sorted(set(truth) | set(guessed)):
        actual = seconds(truth[label])
        # 無活動の待ち時間はADL正解がないため、意味評価の採点領域から除く。
        predicted = seconds(intersections(guessed[label], domain))
        tp = seconds(intersections(truth[label], guessed[label]))
        rows[label] = {
            "true_positive_seconds": tp,
            "predicted_seconds": predicted,
            "truth_seconds": actual,
            **ratios(tp, predicted, actual),
        }
        totals = [a + b for a, b in zip(totals, [tp, predicted, actual], strict=True)]
    f1s = [row["f1"] for row in rows.values() if row["f1"] is not None]
    return {
        "per_label": rows,
        "micro": ratios(*totals),
        "macro_f1": sum(f1s) / len(f1s) if f1s else None,
        "annotated_seconds": seconds(domain),
        "annotated_fraction": seconds(domain) / (end - start).total_seconds(),
        "prediction_seconds_outside_annotations": seconds(
            [span for spans in guessed.values() for span in spans]
        )
        - seconds(intersections([span for spans in guessed.values() for span in spans], domain)),
    }


def evaluate_payload(run: Path, payload: Any, *, semantic: bool) -> dict[str, Any]:
    settings = read_json(run / "run.json")["plan"]
    start = datetime.fromisoformat(settings["start_datetime"])
    split = start + timedelta(days=settings["train_days"])
    end = split + timedelta(days=settings["test_days"])
    series = load_series(run / "analysis/state_series.csv", start.tzinfo)
    activities = read_json(run / "truth/activities.json")
    target_path = run / "truth/target_episodes.json"
    target_episodes = (
        read_json(target_path)
        if target_path.is_file()
        else [
            {
                **activity,
                "target_id": f"{activity['resident_id']}_{activity['activity_id']}",
                "target_episode_id": f"legacy_{index:05d}",
                "generated": True,
                "time_band": mode_at(datetime.fromisoformat(activity["start"])),
                "configured_time_band": mode_at(datetime.fromisoformat(activity["start"])),
                "actual_behavior_path": [],
            }
            for index, activity in enumerate(activities, start=1)
            if activity["activity_id"] in TARGET_ACTIVITIES
        ]
    )
    projected_episodes = project_target_episodes(series, target_episodes)
    train = occurrences(series, start, split)
    test = occurrences(series, split, end)
    catalog, diagnostics = catalog_from_training(
        train,
        target_episodes,
        split,
        settings["min_train_support"],
        {episode["activity_id"] for episode in target_episodes},
    )
    gold_catalog = build_gold_catalog(projected_episodes, split, end, settings["min_train_support"])
    predicted = parse_predictions(payload, require_labels=semantic)
    actual_keys, prediction_keys = set(catalog), set(predicted)
    gold_keys = {
        (row["time_band"], tuple(row["representative_state_sequence"]))
        for row in gold_catalog
        if row["is_canonical"]
    }
    primary_scores = exact_pattern_scores(gold_keys, prediction_keys)
    test_keys = {item.key for item in test}
    visible_keys = actual_keys & test_keys
    episodes = [
        episode
        for episode in target_episodes
        if episode.get("complete")
        and episode.get("start")
        and episode.get("end")
        and datetime.fromisoformat(episode["start"]) >= split
        and datetime.fromisoformat(episode["end"]) <= end
    ]
    observable = recovered = 0
    for episode in episodes:
        left, right = (
            datetime.fromisoformat(episode["start"]),
            datetime.fromisoformat(episode["end"]),
        )
        keys = {item.key for item in test if left <= item.start and item.end <= right}
        observable += bool(keys & actual_keys)
        recovered += bool(keys & actual_keys & prediction_keys)

    potential_keys = {
        (row["time_band"], tuple(row["representative_state_sequence"]))
        for row in gold_catalog
        if not row["is_canonical"]
    }
    test_occurrences: dict[SequenceKey, list[Occurrence]] = defaultdict(list)
    for item in test:
        test_occurrences[item.key].append(item)
    fragment_details = []
    redundant_keys: set[SequenceKey] = set()
    threshold = settings.get("fragmentation_containment_threshold", 0.7)
    for key in sorted(potential_keys):
        relevant_rows = [
            row
            for row in gold_catalog
            if not row["is_canonical"]
            and row["time_band"] == key[0]
            and tuple(row["representative_state_sequence"]) == key[1]
        ]
        target_ids = {row["target_id"] for row in relevant_rows}
        parent_spans = [
            (datetime.fromisoformat(episode["start"]), datetime.fromisoformat(episode["end"]))
            for episode in episodes
            if episode["target_id"] in target_ids
        ]
        containment = _occurrence_containment(test_occurrences.get(key, []), parent_spans)
        emitted = key in prediction_keys
        redundant = emitted and containment is not None and containment >= threshold
        if redundant:
            redundant_keys.add(key)
        fragment_details.append(
            {
                "time_band": key[0],
                "representative_state_sequence": list(key[1]),
                "parent_gold_pattern_ids": sorted(
                    {
                        parent_id
                        for row in relevant_rows
                        for parent_id in row["parent_gold_pattern_ids"]
                    }
                ),
                "emitted": emitted,
                "test_occurrence_count": len(test_occurrences.get(key, [])),
                "occurrence_containment": containment,
                "is_redundant_fragment": redundant,
            }
        )
    evaluable_prediction_keys = prediction_keys & test_keys
    num_potential_fragments = len(potential_keys)
    num_emitted_fragments = len(redundant_keys)
    fragmentation = {
        "num_potential_fragments": num_potential_fragments,
        "num_emitted_potential_fragments": len(potential_keys & prediction_keys),
        "num_emitted_fragments": num_emitted_fragments,
        "fragmentation_rate": (
            num_emitted_fragments / num_potential_fragments if num_potential_fragments else None
        ),
        "fragmentation_status": (
            "evaluated" if num_potential_fragments else "not_applicable_no_potential_fragments"
        ),
        "fragmentation_containment_threshold": threshold,
        "num_evaluable_extracted_patterns": len(evaluable_prediction_keys),
        "num_fragmented_extracted_patterns": num_emitted_fragments,
        "extracted_fragment_rate_diagnostic": (
            num_emitted_fragments / len(evaluable_prediction_keys)
            if evaluable_prediction_keys
            else None
        ),
        "fragment_details": fragment_details,
    }
    other = sum(
        (min(item.end, end) - max(item.start, split)).total_seconds()
        for item in series
        if item.state in {"Other", "その他"} and item.start < end and item.end > split
    )
    train_other = sum(
        (min(item.end, split) - max(item.start, start)).total_seconds()
        for item in series
        if item.state in {"Other", "その他"} and item.start < split and item.end > start
    )
    catalog_rows = [
        {"mode": mode, "sequence": list(sequence), **data}
        for (mode, sequence), data in sorted(catalog.items())
    ]
    return {
        **primary_scores,
        **{key: value for key, value in fragmentation.items() if key != "fragment_details"},
        "fragment_details": fragment_details,
        "gold_catalog": gold_catalog,
        "projected_target_episodes": projected_episodes,
        "catalog": catalog_rows,
        "training_truth_diagnostics": diagnostics,
        "pattern_count": len(prediction_keys),
        "catalog_count": len(actual_keys),
        "catalog_recall": len(actual_keys & prediction_keys) / len(actual_keys)
        if actual_keys
        else None,
        "catalog_precision_diagnostic": (
            len(actual_keys & prediction_keys) / len(prediction_keys) if prediction_keys else None
        ),
        "out_of_catalog_count": len(prediction_keys - actual_keys),
        "test_supported_pattern_fraction": (
            len(prediction_keys & test_keys) / len(prediction_keys) if prediction_keys else None
        ),
        "test_visible_catalog_count": len(visible_keys),
        "test_visible_catalog_recall": (
            len(visible_keys & prediction_keys) / len(visible_keys) if visible_keys else None
        ),
        "test_target_episodes": len(episodes),
        "test_observable_target_episodes": observable,
        "test_recovered_target_episodes": recovered,
        "test_target_episode_coverage": recovered / len(episodes) if episodes else None,
        "test_other_duration_ratio": other / (end - split).total_seconds(),
        "train_other_duration_ratio": train_other / (split - start).total_seconds(),
        "adl": adl_scores(predicted, test, activities, split, end) if semantic else None,
    }
