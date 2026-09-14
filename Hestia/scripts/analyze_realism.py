#!/usr/bin/env python3
"""Compare functional, realistic-calibrated, and aggregate Aruba statistics."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

ADL_CATEGORY_MAP = {
    "Sleeping": "Sleep",
    "Bed_to_Toilet": "Wake-up",
    "Bed_Toilet_Transition": "Wake-up",
    "Bathroom": "Wake-up",
    "Personal_Hygiene": "Wake-up",
    "Toileting": "Toileting",
    "Meal_Preparation": "Meal",
    "Eating": "Meal",
    "Wash_Dishes": "Meal",
    "Leave_Home": "Outing",
    "Enter_Home": "Outing",
    "Relax": "Relax",
    "Housekeeping": "Housework",
    "Work": "Work",
}
ACTIVE_STATES = {"ON", "OPEN", "PRESENT"}
INACTIVE_STATES = {"OFF", "CLOSE", "ABSENT"}
OTHER_STATES = {"Other", "その他"}


@dataclass(frozen=True, slots=True)
class SensorEvent:
    timestamp: datetime
    sensor: str
    state: str


@dataclass(frozen=True, slots=True)
class AdlInterval:
    label: str
    start: datetime
    end: datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--functional-dir", type=Path, required=True)
    parser.add_argument("--realistic-dir", type=Path, required=True)
    parser.add_argument("--functional-pipeline", type=Path, required=True)
    parser.add_argument("--realistic-pipeline", type=Path, required=True)
    parser.add_argument("--aruba-events", type=Path, required=True)
    parser.add_argument("--aruba-labeled", type=Path, required=True)
    parser.add_argument("--aruba-sensor-map", type=Path, required=True)
    parser.add_argument("--aruba-network", type=Path, required=True)
    parser.add_argument("--aruba-state-series", type=Path, required=True)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    return parser.parse_args()


def load_aruba_events(path: Path, days: int) -> tuple[list[SensorEvent], date, date]:
    events: list[SensorEvent] = []
    first_date: date | None = None
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream):
            timestamp = datetime.fromisoformat(f"{row[0]} {row[1]}")
            if first_date is None:
                first_date = timestamp.date()
            if timestamp.date() >= first_date + timedelta(days=days):
                break
            events.append(SensorEvent(timestamp, row[2], row[3].upper()))
    if first_date is None:
        raise ValueError("Aruba event file is empty")
    return events, first_date, first_date + timedelta(days=days)


def load_synthetic_events(path: Path) -> list[SensorEvent]:
    events: list[SensorEvent] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        parts = raw_line.split()
        if len(parts) >= 4 and parts[3].upper() in ACTIVE_STATES | INACTIVE_STATES:
            events.append(
                SensorEvent(
                    datetime.fromisoformat(f"{parts[0]} {parts[1]}"),
                    parts[2],
                    parts[3].upper(),
                )
            )
    return events


def load_adl_intervals(
    path: Path, *, start_date: date | None = None, end_date: date | None = None
) -> list[AdlInterval]:
    stacks: dict[str, list[datetime]] = defaultdict(list)
    intervals: list[AdlInterval] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        parts = raw_line.split()
        if len(parts) < 6 or parts[-1].lower() not in {"begin", "end"}:
            continue
        timestamp = datetime.fromisoformat(f"{parts[0]} {parts[1]}").replace(tzinfo=None)
        if start_date is not None and timestamp.date() < start_date:
            continue
        if end_date is not None and timestamp.date() >= end_date:
            break
        label = ADL_CATEGORY_MAP.get("_".join(parts[4:-1]), "Other_ADL")
        if parts[-1].lower() == "begin":
            stacks[label].append(timestamp)
        elif stacks[label]:
            start = stacks[label].pop()
            if timestamp > start:
                intervals.append(AdlInterval(label, start, timestamp))
    return sorted(intervals, key=lambda item: (item.start, item.end, item.label))


def load_state_series(
    path: Path, *, start_date: date | None = None, end_date: date | None = None
) -> list[tuple[datetime, datetime, str]]:
    intervals: list[tuple[datetime, datetime, str]] = []
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            start = datetime.fromisoformat(row["start_time"]).replace(tzinfo=None)
            end = datetime.fromisoformat(row["end_time"]).replace(tzinfo=None)
            if start_date is not None and end.date() < start_date:
                continue
            if end_date is not None and start.date() >= end_date:
                break
            intervals.append((start, end, row["state_id"]))
    return intervals


def coefficient_of_variation(values: list[float]) -> float:
    mean = statistics.fmean(values) if values else 0.0
    return statistics.pstdev(values) / mean if mean else 0.0


def quantile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def normalized(counter: Counter[Any], keys: list[Any]) -> list[float]:
    total = sum(counter[key] for key in keys)
    return [counter[key] / total if total else 0.0 for key in keys]


def js_divergence(first: list[float], second: list[float]) -> float:
    midpoint = [(left + right) / 2 for left, right in zip(first, second, strict=True)]

    def kl(values: list[float]) -> float:
        return sum(
            value * math.log2(value / middle)
            for value, middle in zip(values, midpoint, strict=True)
            if value > 0 and middle > 0
        )

    return (kl(first) + kl(second)) / 2


def wasserstein_1d(first: list[float], second: list[float], points: int = 256) -> float:
    if not first or not second:
        return math.nan
    return statistics.fmean(
        abs(quantile(first, index / (points - 1)) - quantile(second, index / (points - 1)))
        for index in range(points)
    )


def activation_metrics(events: list[SensorEvent]) -> tuple[list[float], list[float]]:
    active_since: dict[str, datetime] = {}
    last_active: dict[str, datetime] = {}
    durations: list[float] = []
    reactivation: list[float] = []
    for event in events:
        if event.state in ACTIVE_STATES:
            if event.sensor in last_active:
                reactivation.append(
                    max(0.0, (event.timestamp - last_active[event.sensor]).total_seconds())
                )
            last_active[event.sensor] = event.timestamp
            active_since.setdefault(event.sensor, event.timestamp)
        elif event.state in INACTIVE_STATES and event.sensor in active_since:
            durations.append((event.timestamp - active_since.pop(event.sensor)).total_seconds())
    return durations, reactivation


def event_stats(
    events: list[SensorEvent], days: int, room_by_sensor: dict[str, str]
) -> dict[str, Any]:
    per_day = Counter(event.timestamp.date() for event in events)
    hourly = Counter(event.timestamp.hour for event in events)
    sensors = Counter(event.sensor for event in events)
    rooms = Counter(room_by_sensor.get(event.sensor, event.sensor) for event in events)
    durations, reactivation = activation_metrics(events)
    gaps = [
        max(0.0, (current.timestamp - previous.timestamp).total_seconds())
        for previous, current in pairwise(events)
    ]
    active_room_path = [
        room_by_sensor.get(event.sensor, event.sensor)
        for event in events
        if event.state in ACTIVE_STATES
    ]
    return {
        "events": len(events),
        "events_per_day": len(events) / days,
        "sensor_count": len(sensors),
        "room_category_count": len(rooms),
        "daily_cv": coefficient_of_variation(
            [float(per_day.get(day, 0)) for day in sorted(per_day)]
        ),
        "activation_duration_median_sec": quantile(durations, 0.5),
        "activation_duration_p95_sec": quantile(durations, 0.95),
        "same_sensor_reactivation_median_sec": quantile(reactivation, 0.5),
        "room_transitions": sum(
            previous != current for previous, current in pairwise(active_room_path)
        ),
        "hourly": hourly,
        "sensors": sensors,
        "rooms": rooms,
        "per_day": per_day,
        "gaps": gaps,
        "durations": durations,
        "reactivation": reactivation,
    }


def adl_stats(intervals: list[AdlInterval], days: int) -> dict[str, Any]:
    counts = Counter(interval.label for interval in intervals)
    durations = [(interval.end - interval.start).total_seconds() / 60.0 for interval in intervals]
    durations_by_label: dict[str, list[float]] = defaultdict(list)
    starts: dict[str, list[float]] = defaultdict(list)
    for interval in intervals:
        durations_by_label[interval.label].append(
            (interval.end - interval.start).total_seconds() / 60.0
        )
        starts[interval.label].append(
            interval.start.hour * 60 + interval.start.minute + interval.start.second / 60.0
        )
    return {
        "adl_intervals": len(intervals),
        "adl_intervals_per_day": len(intervals) / days,
        "adl_category_count": len(counts),
        "adl_duration_median_min": quantile(durations, 0.5),
        "adl_duration_p95_min": quantile(durations, 0.95),
        "adl_start_time_sd_median_min": quantile(
            [statistics.pstdev(values) for values in starts.values() if len(values) > 1],
            0.5,
        ),
        "counts": counts,
        "durations": durations,
        "durations_by_label": durations_by_label,
    }


def full_event_metrics(directory: Path, days: int) -> dict[str, Any]:
    with (directory / "events.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    with (directory / "state_vectors.csv").open(encoding="utf-8", newline="") as stream:
        state_changes = max(0, sum(1 for _ in stream) - 1)
    within_adl = sum(
        row["device_type"] != "ActivityBoundary" and row["activity_id"] != "-" for row in rows
    )
    by_adl = Counter(
        ADL_CATEGORY_MAP.get(row["activity_label"], "Other_ADL")
        for row in rows
        if row["device_type"] != "ActivityBoundary" and row["activity_id"] != "-"
    )
    occupied_seconds: dict[str, float] = defaultdict(float)
    timed_rows = [
        (datetime.fromisoformat(row["timestamp"]), json.loads(row["occupants"])) for row in rows
    ]
    for (timestamp, occupants), (next_timestamp, _) in pairwise(timed_rows):
        elapsed = max(0.0, (next_timestamp - timestamp).total_seconds())
        for room, resident_ids in occupants.items():
            occupied_seconds[room] += elapsed * len(resident_ids)
    return {
        "raw_full_events": len(rows),
        "raw_full_events_per_day": len(rows) / days,
        "state_vector_changes": state_changes,
        "adl_internal_device_events": within_adl,
        "adl_internal_device_events_by_label": by_adl,
        "room_occupied_hours": {
            room: seconds / 3600.0 for room, seconds in sorted(occupied_seconds.items())
        },
    }


def network_metrics(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    total_duration = sum(float(node["avg_duration_minutes_per_day"]) for node in payload["nodes"])
    other_duration = sum(
        float(node["avg_duration_minutes_per_day"])
        for node in payload["nodes"]
        if node["state_id"] in OTHER_STATES
    )
    return {
        "representative_state_count": sum(
            node["state_id"] not in OTHER_STATES for node in payload["nodes"]
        ),
        "network_node_count": len(payload["nodes"]),
        "network_edge_count": len(payload["edges"]),
        "other_duration_ratio": other_duration / total_duration if total_duration else 0.0,
        "transition_probabilities": sorted(
            [float(edge["probability"]) for edge in payload["edges"]], reverse=True
        ),
    }


def state_series_summary(
    intervals: list[tuple[datetime, datetime, str]], adls: list[AdlInterval]
) -> dict[str, Any]:
    total = sum(max(0.0, (end - start).total_seconds()) for start, end, _ in intervals)
    other = sum(
        max(0.0, (end - start).total_seconds())
        for start, end, state in intervals
        if state in OTHER_STATES
    )
    changes = sum(1 for adl in adls for start, _, _ in intervals[1:] if adl.start < start < adl.end)
    return {
        "compressed_state_intervals": len(intervals),
        "state_transitions": max(0, len(intervals) - 1),
        "adl_internal_state_changes": changes,
        "other_duration_ratio": other / total if total else 0.0,
    }


def load_room_map(directory: Path) -> dict[str, str]:
    room_json = directory / "casas_sensor_map_room.json"
    if room_json.exists():
        return json.loads(room_json.read_text(encoding="utf-8"))
    with (directory / "sensor_map.csv").open(encoding="utf-8", newline="") as stream:
        return {
            row["sensor_id"]: row["room_id"]
            for row in csv.DictReader(stream)
            if row["device_type"] != "ActivityBoundary"
        }


def ranked_distribution(counter: Counter[Any]) -> list[float]:
    values = sorted(counter.values(), reverse=True)
    total = sum(values)
    return [value / total for value in values] if total else []


def padded(first: list[float], second: list[float]) -> tuple[list[float], list[float]]:
    size = max(len(first), len(second))
    return first + [0.0] * (size - len(first)), second + [0.0] * (size - len(second))


def fmt(value: float | int | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return f"{value:.9g}"


def main() -> None:
    args = parse_args()
    aruba_events, real_start, real_end = load_aruba_events(args.aruba_events, args.days)
    functional_events = load_synthetic_events(args.functional_dir / "casas_motion_door.txt")
    realistic_events = load_synthetic_events(args.realistic_dir / "casas_motion_door.txt")
    aruba_map = json.loads(args.aruba_sensor_map.read_text(encoding="utf-8"))
    event_summaries = {
        "functional": event_stats(functional_events, args.days, load_room_map(args.functional_dir)),
        "realistic": event_stats(realistic_events, args.days, load_room_map(args.realistic_dir)),
        "aruba": event_stats(aruba_events, args.days, aruba_map),
    }
    adls = {
        "functional": load_adl_intervals(args.functional_dir / "casas_motion_door.txt"),
        "realistic": load_adl_intervals(args.realistic_dir / "casas_motion_door.txt"),
        "aruba": load_adl_intervals(args.aruba_labeled, start_date=real_start, end_date=real_end),
    }
    adl_summaries = {key: adl_stats(value, args.days) for key, value in adls.items()}
    full_summaries = {
        "functional": full_event_metrics(args.functional_dir, args.days),
        "realistic": full_event_metrics(args.realistic_dir, args.days),
    }
    pipeline = {
        "functional": json.loads(args.functional_pipeline.read_text(encoding="utf-8")),
        "realistic": json.loads(args.realistic_pipeline.read_text(encoding="utf-8")),
    }
    networks = {
        "functional": network_metrics(Path(pipeline["functional"]["network_json"])),
        "realistic": network_metrics(Path(pipeline["realistic"]["network_json"])),
        "aruba": network_metrics(args.aruba_network),
    }
    aruba_series = load_state_series(
        args.aruba_state_series, start_date=real_start, end_date=real_end
    )
    aruba_series_summary = state_series_summary(aruba_series, adls["aruba"])
    aruba_observed_states = len(
        {state for _, _, state in aruba_series if state not in OTHER_STATES}
    )

    rows: list[dict[str, str]] = []

    def add(
        section: str,
        metric: str,
        functional: float | int | None,
        realistic: float | int | None,
        aruba: float | int | None,
        unit: str,
    ) -> None:
        ratio = math.nan
        if functional is not None and realistic is not None and float(functional) != 0:
            ratio = float(realistic) / float(functional)
        rows.append(
            {
                "section": section,
                "metric": metric,
                "functional": fmt(functional),
                "realistic_calibrated": fmt(realistic),
                "aruba": fmt(aruba),
                "realistic_to_functional_ratio": fmt(ratio),
                "unit": unit,
            }
        )

    for metric, unit in {
        "events": "events",
        "events_per_day": "events/day",
        "sensor_count": "sensors",
        "room_category_count": "rooms",
        "daily_cv": "ratio",
        "activation_duration_median_sec": "seconds",
        "activation_duration_p95_sec": "seconds",
        "same_sensor_reactivation_median_sec": "seconds",
        "room_transitions": "transitions",
    }.items():
        add(
            "research_sensor_events",
            metric,
            event_summaries["functional"][metric],
            event_summaries["realistic"][metric],
            event_summaries["aruba"][metric],
            unit,
        )
    for metric, unit in {
        "raw_full_events": "events",
        "raw_full_events_per_day": "events/day",
        "state_vector_changes": "changes",
        "adl_internal_device_events": "events",
    }.items():
        add(
            "full_log",
            metric,
            full_summaries["functional"][metric],
            full_summaries["realistic"][metric],
            None,
            unit,
        )
    for metric, unit in {
        "adl_intervals": "intervals",
        "adl_intervals_per_day": "intervals/day",
        "adl_category_count": "categories",
        "adl_duration_median_min": "minutes",
        "adl_duration_p95_min": "minutes",
        "adl_start_time_sd_median_min": "minutes",
    }.items():
        add(
            "adl",
            metric,
            adl_summaries["functional"][metric],
            adl_summaries["realistic"][metric],
            adl_summaries["aruba"][metric],
            unit,
        )
    for metric, unit in {
        "compressed_state_intervals": "intervals",
        "state_transitions": "transitions",
        "adl_internal_state_changes": "changes",
    }.items():
        add(
            "research_pipeline",
            metric,
            pipeline["functional"][metric],
            pipeline["realistic"][metric],
            aruba_series_summary[metric],
            unit,
        )
    add(
        "research_pipeline",
        "observed_mapped_representative_states",
        pipeline["functional"]["mapped_state_ids"],
        pipeline["realistic"]["mapped_state_ids"],
        aruba_observed_states,
        "states",
    )
    for metric, unit in {
        "representative_state_count": "states",
        "network_node_count": "nodes",
        "network_edge_count": "edges",
        "other_duration_ratio": "ratio",
    }.items():
        add(
            "research_network",
            metric,
            networks["functional"][metric],
            networks["realistic"][metric],
            networks["aruba"][metric],
            unit,
        )

    hours = list(range(24))
    for hour in hours:
        add(
            "hourly_event_count",
            f"hour_{hour:02d}",
            event_summaries["functional"]["hourly"][hour],
            event_summaries["realistic"]["hourly"][hour],
            event_summaries["aruba"]["hourly"][hour],
            "events",
        )
    room_keys = sorted(
        set(event_summaries["functional"]["rooms"])
        | set(event_summaries["realistic"]["rooms"])
        | set(event_summaries["aruba"]["rooms"])
    )
    for room in room_keys:
        add(
            "room_event_count",
            str(room),
            event_summaries["functional"]["rooms"][room],
            event_summaries["realistic"]["rooms"][room],
            event_summaries["aruba"]["rooms"][room],
            "events",
        )
    adl_keys = sorted(
        set(adl_summaries["functional"]["counts"])
        | set(adl_summaries["realistic"]["counts"])
        | set(adl_summaries["aruba"]["counts"])
    )
    for label in adl_keys:
        add(
            "adl_interval_count_by_label",
            str(label),
            adl_summaries["functional"]["counts"][label],
            adl_summaries["realistic"]["counts"][label],
            adl_summaries["aruba"]["counts"][label],
            "intervals",
        )
        add(
            "adl_median_duration_by_label",
            str(label),
            quantile(adl_summaries["functional"]["durations_by_label"].get(label, []), 0.5),
            quantile(adl_summaries["realistic"]["durations_by_label"].get(label, []), 0.5),
            quantile(adl_summaries["aruba"]["durations_by_label"].get(label, []), 0.5),
            "minutes",
        )
    daily_values = {
        key: [value for _, value in sorted(summary["per_day"].items())]
        for key, summary in event_summaries.items()
    }
    for index in range(args.days):
        add(
            "daily_event_count",
            f"day_{index + 1}",
            daily_values["functional"][index],
            daily_values["realistic"][index],
            daily_values["aruba"][index],
            "events",
        )
    for sensor in sorted(
        set(event_summaries["functional"]["sensors"])
        | set(event_summaries["realistic"]["sensors"])
        | set(event_summaries["aruba"]["sensors"])
    ):
        add(
            "sensor_event_count_by_id",
            str(sensor),
            event_summaries["functional"]["sensors"][sensor],
            event_summaries["realistic"]["sensors"][sensor],
            event_summaries["aruba"]["sensors"][sensor],
            "events",
        )
    for room in sorted(
        set(full_summaries["functional"]["room_occupied_hours"])
        | set(full_summaries["realistic"]["room_occupied_hours"])
    ):
        add(
            "synthetic_room_occupied_hours",
            room,
            full_summaries["functional"]["room_occupied_hours"].get(room, 0.0),
            full_summaries["realistic"]["room_occupied_hours"].get(room, 0.0),
            None,
            "resident-hours",
        )

    functional_hourly = normalized(event_summaries["functional"]["hourly"], hours)
    realistic_hourly = normalized(event_summaries["realistic"]["hourly"], hours)
    aruba_hourly = normalized(event_summaries["aruba"]["hourly"], hours)
    functional_rooms, aruba_rooms_for_functional = padded(
        ranked_distribution(event_summaries["functional"]["rooms"]),
        ranked_distribution(event_summaries["aruba"]["rooms"]),
    )
    realistic_rooms, aruba_rooms_for_realistic = padded(
        ranked_distribution(event_summaries["realistic"]["rooms"]),
        ranked_distribution(event_summaries["aruba"]["rooms"]),
    )
    functional_transitions, aruba_transitions_functional = padded(
        networks["functional"]["transition_probabilities"],
        networks["aruba"]["transition_probabilities"],
    )
    realistic_transitions, aruba_transitions_realistic = padded(
        networks["realistic"]["transition_probabilities"],
        networks["aruba"]["transition_probabilities"],
    )
    distances = {
        "hourly_js_bits": (
            js_divergence(functional_hourly, aruba_hourly),
            js_divergence(realistic_hourly, aruba_hourly),
        ),
        "room_rank_js_bits": (
            js_divergence(functional_rooms, aruba_rooms_for_functional),
            js_divergence(realistic_rooms, aruba_rooms_for_realistic),
        ),
        "inter_event_gap_wasserstein_sec": (
            wasserstein_1d(event_summaries["functional"]["gaps"], event_summaries["aruba"]["gaps"]),
            wasserstein_1d(event_summaries["realistic"]["gaps"], event_summaries["aruba"]["gaps"]),
        ),
        "adl_duration_wasserstein_min": (
            wasserstein_1d(
                adl_summaries["functional"]["durations"],
                adl_summaries["aruba"]["durations"],
            ),
            wasserstein_1d(
                adl_summaries["realistic"]["durations"],
                adl_summaries["aruba"]["durations"],
            ),
        ),
        "transition_probability_rank_l1": (
            sum(
                abs(left - right)
                for left, right in zip(
                    functional_transitions, aruba_transitions_functional, strict=True
                )
            ),
            sum(
                abs(left - right)
                for left, right in zip(
                    realistic_transitions, aruba_transitions_realistic, strict=True
                )
            ),
        ),
    }
    for metric, (functional_distance, realistic_distance) in distances.items():
        add(
            "distance_to_aruba",
            metric,
            functional_distance,
            realistic_distance,
            0.0,
            "distance (lower is closer)",
        )

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    key_metrics = {
        row["metric"]: row
        for row in rows
        if row["metric"]
        in {
            "raw_full_events_per_day",
            "events_per_day",
            "other_duration_ratio",
            "adl_internal_state_changes",
            "representative_state_count",
            "observed_mapped_representative_states",
            "state_transitions",
            "daily_cv",
        }
    }
    markdown = [
        "# functional / realistic_calibrated / Aruba 集計比較",
        "",
        "## 条件",
        "",
        f"- 比較期間: {args.days}日",
        "- 研究前処理: K=15、h=0、1秒Sample-and-Hold、5秒遅延OFF",
        "- Arubaは生系列のコピーではなく、集計統計と正式成果物だけを比較に使用した。",
        "",
        "## 主要指標",
        "",
        "| 指標 | functional | realistic_calibrated | Aruba | realistic/functional |",
        "|---|---:|---:|---:|---:|",
    ]
    for metric in (
        "raw_full_events_per_day",
        "events_per_day",
        "other_duration_ratio",
        "adl_internal_state_changes",
        "representative_state_count",
        "observed_mapped_representative_states",
        "state_transitions",
        "daily_cv",
    ):
        row = key_metrics[metric]
        markdown.append(
            f"| {metric} | {row['functional'] or '-'} | "
            f"{row['realistic_calibrated'] or '-'} | {row['aruba'] or '-'} | "
            f"{row['realistic_to_functional_ratio'] or '-'} |"
        )
    markdown.extend(
        [
            "",
            "## Arubaとの距離",
            "",
            "| 指標 | functional | realistic_calibrated | 改善 |",
            "|---|---:|---:|---:|",
        ]
    )
    for metric, (functional_distance, realistic_distance) in distances.items():
        markdown.append(
            f"| {metric} | {functional_distance:.6g} | {realistic_distance:.6g} | "
            f"{functional_distance - realistic_distance:.6g} |"
        )
    markdown.extend(
        [
            "",
            "## 解釈",
            "",
            "`realistic_calibrated`はゾーン移動と因果的なマイクロ行動により、"
            "functionalより状態変化と遷移を増やす。イベント数そのものへの一致は目的関数に"
            "していない。Arubaには短時間の再発火が非常に多く、合成側は意味的な移動単位を"
            "維持するため、密度差は残る。",
            "",
            "Other率は時間加重で計算した。Arubaの部屋真値はないため、合成の在室時間と"
            "Arubaのセンサー発火割合を同一概念として扱っていない。詳細な時間帯・部屋・ADL"
            "内訳はCSVを参照する。",
        ]
    )
    args.output_md.write_text("\n".join(markdown) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
