#!/usr/bin/env python3
"""Compare a generated HESTIA-style sample with a real Aruba window."""

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
    parser.add_argument("--real-events", type=Path, required=True)
    parser.add_argument("--real-labeled", type=Path, required=True)
    parser.add_argument("--synthetic-casas", type=Path, required=True)
    parser.add_argument("--synthetic-events", type=Path, required=True)
    parser.add_argument("--real-network", type=Path, required=True)
    parser.add_argument("--synthetic-network", type=Path, required=True)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    return parser.parse_args()


def parse_timestamp(date_text: str, time_text: str) -> datetime:
    return datetime.fromisoformat(f"{date_text} {time_text}")


def load_real_events(path: Path, days: int) -> tuple[list[SensorEvent], date, date]:
    events: list[SensorEvent] = []
    first_date: date | None = None
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream):
            timestamp = parse_timestamp(row[0], row[1])
            if first_date is None:
                first_date = timestamp.date()
            end_date = first_date + timedelta(days=days)
            if timestamp.date() >= end_date:
                break
            events.append(SensorEvent(timestamp, row[2], row[3].upper()))
    if first_date is None:
        raise ValueError("real event file is empty")
    return events, first_date, first_date + timedelta(days=days)


def load_synthetic_events(path: Path) -> list[SensorEvent]:
    events: list[SensorEvent] = []
    with path.open(encoding="utf-8") as stream:
        for raw_line in stream:
            parts = raw_line.split()
            if len(parts) < 4 or parts[3] not in {"ON", "OFF", "OPEN", "CLOSE"}:
                continue
            events.append(SensorEvent(parse_timestamp(parts[0], parts[1]), parts[2], parts[3]))
    if not events:
        raise ValueError("synthetic CASAS file contains no supported sensor events")
    return events


def load_adl_intervals(
    path: Path,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[AdlInterval]:
    stacks: dict[str, list[datetime]] = defaultdict(list)
    intervals: list[AdlInterval] = []
    with path.open(encoding="utf-8") as stream:
        for raw_line in stream:
            parts = raw_line.split()
            if len(parts) < 6 or parts[-1].lower() not in {"begin", "end"}:
                continue
            timestamp = parse_timestamp(parts[0], parts[1])
            if end_date is not None and timestamp.date() >= end_date:
                break
            if start_date is not None and timestamp.date() < start_date:
                continue
            raw_label = "_".join(parts[4:-1])
            label = ADL_CATEGORY_MAP.get(raw_label, "Other_ADL")
            if parts[-1].lower() == "begin":
                stacks[label].append(timestamp)
            elif stacks[label]:
                started = stacks[label].pop()
                if timestamp > started:
                    intervals.append(AdlInterval(label, started, timestamp))
    return sorted(intervals, key=lambda item: (item.start, item.end, item.label))


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


def activation_durations(events: list[SensorEvent]) -> tuple[list[float], int]:
    active: dict[str, datetime] = {}
    durations: list[float] = []
    duplicate_states = 0
    previous: dict[str, str] = {}
    for event in events:
        if previous.get(event.sensor) == event.state:
            duplicate_states += 1
        previous[event.sensor] = event.state
        if event.state in {"ON", "OPEN"}:
            active.setdefault(event.sensor, event.timestamp)
        elif event.state in {"OFF", "CLOSE"} and event.sensor in active:
            durations.append((event.timestamp - active.pop(event.sensor)).total_seconds())
    return durations, duplicate_states


def normalized(counter: Counter[Any], keys: list[Any]) -> list[float]:
    total = sum(counter[key] for key in keys)
    if total == 0:
        return [0.0 for _ in keys]
    return [counter[key] / total for key in keys]


def js_divergence(first: list[float], second: list[float]) -> float:
    midpoint = [(left + right) / 2 for left, right in zip(first, second, strict=True)]

    def kl(values: list[float]) -> float:
        return sum(
            value * math.log2(value / middle)
            for value, middle in zip(values, midpoint, strict=True)
            if value > 0 and middle > 0
        )

    return (kl(first) + kl(second)) / 2


def histogram_wasserstein(first: list[float], second: list[float]) -> float:
    cumulative_first = 0.0
    cumulative_second = 0.0
    distance = 0.0
    for left, right in zip(first, second, strict=True):
        cumulative_first += left
        cumulative_second += right
        distance += abs(cumulative_first - cumulative_second)
    return distance


def coefficient_of_variation(values: list[float]) -> float:
    mean = statistics.fmean(values) if values else 0.0
    return statistics.pstdev(values) / mean if mean else 0.0


def event_summary(events: list[SensorEvent], days: int) -> dict[str, Any]:
    per_day = Counter(event.timestamp.date() for event in events)
    hourly = Counter(event.timestamp.hour for event in events)
    sensors = Counter(event.sensor for event in events)
    states = Counter(event.state for event in events)
    durations, duplicate_states = activation_durations(events)
    gaps = [
        (current.timestamp - previous.timestamp).total_seconds()
        for previous, current in pairwise(events)
        if current.timestamp >= previous.timestamp
    ]
    daily_values = [float(value) for _, value in sorted(per_day.items())]
    return {
        "events": len(events),
        "events_per_day": len(events) / days,
        "daily_cv": coefficient_of_variation(daily_values),
        "sensor_count": len(sensors),
        "sensor_concentration": max(sensors.values()) / len(events),
        "sensor_cv": coefficient_of_variation([float(value) for value in sensors.values()]),
        "active_ratio": (states["ON"] + states["OPEN"]) / max(1, sum(states.values())),
        "duplicate_state_ratio": duplicate_states / max(1, len(events)),
        "activation_duration_median_sec": quantile(durations, 0.5),
        "activation_duration_p95_sec": quantile(durations, 0.95),
        "inter_event_gap_median_sec": quantile(gaps, 0.5),
        "inter_event_gap_p95_sec": quantile(gaps, 0.95),
        "hourly": hourly,
        "sensors": sensors,
        "states": states,
        "per_day": per_day,
    }


def adl_summary(intervals: list[AdlInterval], days: int) -> dict[str, Any]:
    counts = Counter(interval.label for interval in intervals)
    durations: dict[str, list[float]] = defaultdict(list)
    starts: dict[str, list[float]] = defaultdict(list)
    for interval in intervals:
        durations[interval.label].append((interval.end - interval.start).total_seconds() / 60)
        starts[interval.label].append(
            interval.start.hour * 60 + interval.start.minute + interval.start.second / 60
        )
    all_durations = [value for values in durations.values() for value in values]
    regularity_values = [statistics.pstdev(values) for values in starts.values() if len(values) > 1]
    return {
        "count": len(intervals),
        "count_per_day": len(intervals) / days,
        "category_count": len(counts),
        "duration_median_min": quantile(all_durations, 0.5),
        "duration_p95_min": quantile(all_durations, 0.95),
        "start_time_sd_median_min": quantile(regularity_values, 0.5),
        "counts": counts,
        "durations": durations,
    }


def network_summary(path: Path) -> dict[str, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    nodes = payload["nodes"]
    edges = payload["edges"]
    edge_pairs = {(item["from"], item["to"]) for item in edges}
    reversible = sum(
        1 for source, target in edge_pairs if source != target and (target, source) in edge_pairs
    )
    entropies: list[float] = []
    outgoing: dict[str, list[float]] = defaultdict(list)
    for edge in edges:
        outgoing[edge["from"]].append(float(edge["probability"]))
    for probabilities in outgoing.values():
        entropies.append(-sum(value * math.log2(value) for value in probabilities if value > 0))
    duration_total = sum(float(node["avg_duration_minutes_per_day"]) for node in nodes)
    other_duration = sum(
        float(node["avg_duration_minutes_per_day"])
        for node in nodes
        if node["state_id"] in {"Other", "その他"}
    )
    node_count = len(nodes)
    return {
        "nodes": float(node_count),
        "edges": float(len(edges)),
        "density": len(edges) / max(1, node_count * (node_count - 1)),
        "self_edge_ratio": sum(1 for source, target in edge_pairs if source == target)
        / max(1, len(edge_pairs)),
        "reversible_edge_ratio": reversible / max(1, len(edge_pairs)),
        "mean_outgoing_entropy_bits": statistics.fmean(entropies) if entropies else 0.0,
        "other_duration_ratio": other_duration / duration_total if duration_total else 0.0,
    }


def synthetic_occupancy(path: Path) -> dict[str, float]:
    rows: list[tuple[datetime, dict[str, list[str]]]] = []
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            rows.append((datetime.fromisoformat(row["timestamp"]), json.loads(row["occupants"])))
    occupied_seconds: Counter[str] = Counter()
    for (timestamp, snapshot), (next_timestamp, _) in pairwise(rows):
        elapsed = max(0.0, (next_timestamp - timestamp).total_seconds())
        for room_id, residents in snapshot.items():
            occupied_seconds[room_id] += elapsed * len(residents)
    total = sum(occupied_seconds.values())
    return {
        room_id: seconds / total for room_id, seconds in sorted(occupied_seconds.items()) if total
    }


def format_value(value: float) -> str:
    return f"{value:.6g}"


def main() -> None:
    args = parse_args()
    if args.days <= 0:
        raise ValueError("--days must be positive")
    real_events, real_start, real_end = load_real_events(args.real_events, args.days)
    synthetic_events = load_synthetic_events(args.synthetic_casas)
    real_adls = load_adl_intervals(
        args.real_labeled,
        start_date=real_start,
        end_date=real_end,
    )
    synthetic_adls = load_adl_intervals(args.synthetic_casas)
    real = event_summary(real_events, args.days)
    synthetic = event_summary(synthetic_events, args.days)
    real_adl = adl_summary(real_adls, args.days)
    synthetic_adl = adl_summary(synthetic_adls, args.days)
    real_network = network_summary(args.real_network)
    synthetic_network = network_summary(args.synthetic_network)

    rows: list[dict[str, str]] = []

    def add(
        section: str, metric: str, real_value: float, synthetic_value: float, unit: str
    ) -> None:
        ratio = synthetic_value / real_value if real_value else math.nan
        rows.append(
            {
                "section": section,
                "metric": metric,
                "real": format_value(real_value),
                "synthetic": format_value(synthetic_value),
                "synthetic_to_real_ratio": "" if math.isnan(ratio) else format_value(ratio),
                "unit": unit,
            }
        )

    event_metrics = {
        "events": "count",
        "events_per_day": "events/day",
        "daily_cv": "ratio",
        "sensor_count": "count",
        "sensor_concentration": "ratio",
        "sensor_cv": "ratio",
        "active_ratio": "ratio",
        "duplicate_state_ratio": "ratio",
        "activation_duration_median_sec": "seconds",
        "activation_duration_p95_sec": "seconds",
        "inter_event_gap_median_sec": "seconds",
        "inter_event_gap_p95_sec": "seconds",
    }
    for metric, unit in event_metrics.items():
        add("events", metric, float(real[metric]), float(synthetic[metric]), unit)

    hourly_keys = list(range(24))
    real_hourly = normalized(real["hourly"], hourly_keys)
    synthetic_hourly = normalized(synthetic["hourly"], hourly_keys)
    add(
        "distribution",
        "hourly_jensen_shannon_divergence",
        0.0,
        js_divergence(real_hourly, synthetic_hourly),
        "bits (0=identical)",
    )
    add(
        "distribution",
        "hourly_histogram_wasserstein",
        0.0,
        histogram_wasserstein(real_hourly, synthetic_hourly),
        "hour-bin distance",
    )

    adl_metrics = {
        "count": "count",
        "count_per_day": "intervals/day",
        "category_count": "count",
        "duration_median_min": "minutes",
        "duration_p95_min": "minutes",
        "start_time_sd_median_min": "minutes",
    }
    for metric, unit in adl_metrics.items():
        add("adl", metric, float(real_adl[metric]), float(synthetic_adl[metric]), unit)
    for metric in real_network:
        unit = "count" if metric in {"nodes", "edges"} else "ratio/bits"
        add("network", metric, real_network[metric], synthetic_network[metric], unit)

    all_labels = sorted(set(real_adl["counts"]) | set(synthetic_adl["counts"]))
    for label in all_labels:
        add(
            "adl_count_by_label",
            label,
            float(real_adl["counts"][label]),
            float(synthetic_adl["counts"][label]),
            "count",
        )
        add(
            "adl_median_duration_by_label",
            label,
            quantile(real_adl["durations"].get(label, []), 0.5),
            quantile(synthetic_adl["durations"].get(label, []), 0.5),
            "minutes",
        )
    for hour in hourly_keys:
        add(
            "hourly_event_share",
            f"hour_{hour:02d}",
            real_hourly[hour],
            synthetic_hourly[hour],
            "share",
        )

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    occupancy = synthetic_occupancy(args.synthetic_events)
    event_rows = [row for row in rows if row["section"] == "events"]
    network_rows = [row for row in rows if row["section"] == "network"]
    markdown = [
        "# HESTIA生成データと実Arubaデータの品質比較",
        "",
        "## 比較条件",
        "",
        f"- 実データ: `{args.real_events}` の先頭{args.days}暦日 "
        f"({real_start.isoformat()}〜{(real_end - timedelta(days=1)).isoformat()})",
        f"- 生成データ: `{args.synthetic_casas}` ({args.days}日、固定seed)",
        "- 共通ネットワーク条件: 1秒Sample-and-Hold、5秒遅延OFF、K=15、h=0",
        "- LLM由来の品質指標ではなく、イベント・ADL・代表状態遷移の記述統計である。",
        "",
        "## 主要イベント統計",
        "",
        "| 指標 | 実Aruba | 生成 | 生成/実 | 単位 |",
        "|---|---:|---:|---:|---|",
    ]
    markdown.extend(
        f"| {row['metric']} | {row['real']} | {row['synthetic']} | "
        f"{row['synthetic_to_real_ratio'] or '-'} | {row['unit']} |"
        for row in event_rows
    )
    markdown.extend(
        [
            "",
            "## 遷移ネットワーク統計",
            "",
            "| 指標 | 実Aruba | 生成 | 生成/実 |",
            "|---|---:|---:|---:|",
        ]
    )
    markdown.extend(
        f"| {row['metric']} | {row['real']} | {row['synthetic']} | "
        f"{row['synthetic_to_real_ratio'] or '-'} |"
        for row in network_rows
    )
    markdown.extend(
        [
            "",
            "## 生成データの時間加重在室分布",
            "",
        ]
    )
    markdown.extend(f"- `{room}`: {share:.3%}" for room, share in occupancy.items())
    markdown.extend(
        [
            "",
            "## 結論",
            "",
            f"生成ログは{len(synthetic_events) / args.days:.1f}イベント/日で、実Arubaの"
            f"{len(real_events) / args.days:.1f}イベント/日より大幅に疎である。これは、"
            "生成側が完全な在室変化と扉通過を低チャタリングで記録する一方、実データには"
            "高頻度なモーション再発火が含まれるためである。",
            f"時間帯分布のJensen-Shannon divergenceは"
            f"{js_divergence(real_hourly, synthetic_hourly):.3f} bitsで、日課の時刻が"
            "固定的な生成データと実生活の分散には明瞭な差がある。",
            f"代表状態の`Other/その他`滞在比率は実{real_network['other_duration_ratio']:.2%}、"
            f"生成{synthetic_network['other_duration_ratio']:.2%}である。h=0では、生成側の"
            "長時間状態の多くが上位Kに入らない構成差が品質上の主要な制約になる。",
            "よって、生成ログはパイプライン機能・再現性・既知シナリオの教師データ検証には"
            "利用できるが、実Arubaの点過程を忠実に代替するデータとは扱えない。",
            "",
            "## 解釈上の制約",
            "",
            "- 実データの在室真値はないため、生成側の在室分布と実側のセンサー発火分布を"
            "同一概念として直接比較していない。",
            "- 7日窓は曜日を一巡するが季節差を表さず、推測統計の独立標本としては短い。",
            "- 実ArubaはセンサーIDを部屋カテゴリへ集約済み、生成側は個別センサーIDである。",
            "- 詳細な時間帯・ADL別数値は同時生成したCSVを参照する。",
        ]
    )
    args.output_md.write_text("\n".join(markdown) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
