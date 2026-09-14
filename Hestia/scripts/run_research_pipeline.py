#!/usr/bin/env python3
"""Run the existing research preprocessing contract without writing its repository."""

from __future__ import annotations

import argparse
import csv
import json
import os
import resource
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

SIMPLE_STATES = {"ON", "OFF", "OPEN", "CLOSE", "PRESENT", "ABSENT"}
OTHER_STATES = {"Other", "その他"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--labeled-casas", type=Path, required=True)
    parser.add_argument("--sensor-map", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--n-states", type=int, default=15)
    parser.add_argument("--hamming-threshold", type=int, default=0)
    parser.add_argument("--smoothing-window-sec", type=int, default=5)
    parser.add_argument("--summary-json", type=Path, required=True)
    return parser.parse_args()


def run_command(command: list[str], *, cwd: Path, env: dict[str, str]) -> tuple[str, float]:
    started = time.perf_counter()
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"research command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result.stdout + result.stderr, time.perf_counter() - started


def classify_input(path: Path) -> dict[str, int]:
    total = 0
    sensor = 0
    boundary = 0
    malformed = 0
    unsupported = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        total += 1
        parts = raw_line.split()
        if len(parts) < 4:
            malformed += 1
        elif parts[3].upper() in SIMPLE_STATES:
            sensor += 1
        elif len(parts) >= 6 and parts[-1].lower() in {"begin", "end"}:
            boundary += 1
        else:
            unsupported += 1
    return {
        "input_lines": total,
        "converted_sensor_events": sensor,
        "excluded_activity_boundaries": boundary,
        "excluded_malformed": malformed,
        "excluded_unsupported_state": unsupported,
    }


def load_state_series(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def parse_adl_intervals(path: Path) -> list[tuple[datetime, datetime, str]]:
    stacks: dict[str, list[datetime]] = {}
    intervals: list[tuple[datetime, datetime, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        parts = raw_line.split()
        if len(parts) < 6 or parts[-1].lower() not in {"begin", "end"}:
            continue
        timestamp = datetime.fromisoformat(f"{parts[0]} {parts[1]}").replace(tzinfo=None)
        label = "_".join(parts[4:-1])
        if parts[-1].lower() == "begin":
            stacks.setdefault(label, []).append(timestamp)
        elif stacks.get(label):
            start = stacks[label].pop()
            if timestamp > start:
                intervals.append((start, timestamp, label))
    return sorted(intervals)


def state_series_metrics(
    rows: list[dict[str, str]], adl_intervals: list[tuple[datetime, datetime, str]]
) -> dict[str, Any]:
    other_seconds = 0.0
    total_seconds = 0.0
    state_counts: Counter[str] = Counter()
    parsed: list[tuple[datetime, datetime, str]] = []
    for row in rows:
        start = datetime.fromisoformat(row["start_time"])
        end = datetime.fromisoformat(row["end_time"])
        state_id = row["state_id"]
        seconds = max(0.0, (end - start).total_seconds())
        total_seconds += seconds
        state_counts[state_id] += 1
        if state_id in OTHER_STATES:
            other_seconds += seconds
        parsed.append((start, end, state_id))
    adl_changes = 0
    by_label: Counter[str] = Counter()
    for adl_start, adl_end, label in adl_intervals:
        changes = sum(1 for state_start, _, _ in parsed[1:] if adl_start < state_start < adl_end)
        adl_changes += changes
        by_label[label] += changes
    return {
        "compressed_state_intervals": len(rows),
        "state_transitions": max(0, len(rows) - 1),
        "mapped_state_ids": len(set(state_counts) - OTHER_STATES),
        "other_interval_count": sum(state_counts[state] for state in OTHER_STATES),
        "other_duration_ratio": other_seconds / total_seconds if total_seconds else 0.0,
        "mapping_unmatched_duration_ratio": other_seconds / total_seconds if total_seconds else 0.0,
        "adl_intervals": len(adl_intervals),
        "adl_internal_state_changes": adl_changes,
        "adl_internal_state_changes_by_label": dict(sorted(by_label.items())),
    }


def main() -> None:
    args = parse_args()
    if args.days <= 0:
        raise ValueError("--days must be positive")
    args.work_dir.mkdir(parents=True, exist_ok=True)
    python = args.research_root / ".venv/bin/python"
    if not python.is_file():
        raise FileNotFoundError(f"research Python environment not found: {python}")
    converted = args.work_dir / f"{args.labeled_casas.stem}_converted.csv"
    state_series = args.work_dir / f"{args.labeled_casas.stem}_state_series.csv"
    environment = dict(os.environ)
    mpl_dir = args.work_dir / "matplotlib"
    mpl_dir.mkdir(exist_ok=True)
    environment["MPLCONFIGDIR"] = str(mpl_dir)

    before_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    build_output, build_seconds = run_command(
        [
            str(python),
            str(args.research_root / "scripts/run_build_network_from_labeled_casas.py"),
            "--labeled-casas",
            str(args.labeled_casas),
            "--sensor-map",
            str(args.sensor_map),
            "--keep-converted-csv",
            str(converted),
            "--days",
            str(args.days),
            "--n-states",
            str(args.n_states),
            "--hamming-threshold",
            str(args.hamming_threshold),
            "--smoothing-window-sec",
            str(args.smoothing_window_sec),
        ],
        cwd=args.work_dir,
        env=environment,
    )
    parameter_suffix = f"{converted.stem}_{args.n_states}_{args.hamming_threshold}_{args.days}days"
    state_table = args.work_dir / "state" / f"{parameter_suffix}.txt"
    network_json = args.work_dir / "picture" / parameter_suffix / "state_transition_all.json"
    series_output, series_seconds = run_command(
        [
            str(python),
            str(args.research_root / "scripts/evaluate_adl_labels.py"),
            "--labeled-casas",
            str(args.labeled_casas),
            "--state-table",
            str(state_table),
            "--sensor-map",
            str(args.sensor_map),
            "--hamming-threshold",
            str(args.hamming_threshold),
            "--write-state-series",
            str(state_series),
            "--state-series-preprocessing",
            "network-equivalent",
            "--smoothing-window-sec",
            str(args.smoothing_window_sec),
            "--state-series-days",
            str(args.days),
            "--state-series-only",
        ],
        cwd=args.work_dir,
        env=environment,
    )
    after_usage = resource.getrusage(resource.RUSAGE_CHILDREN)

    input_metrics = classify_input(args.labeled_casas)
    sensor_map = json.loads(args.sensor_map.read_text(encoding="utf-8"))
    raw_sensors = {
        line.split()[2]
        for line in args.labeled_casas.read_text(encoding="utf-8").splitlines()
        if len(line.split()) >= 4 and line.split()[3].upper() in SIMPLE_STATES
    }
    network = json.loads(network_json.read_text(encoding="utf-8"))
    state_rows = load_state_series(state_series)
    adl_intervals = parse_adl_intervals(args.labeled_casas)
    mode_event_counts: Counter[str] = Counter()
    with converted.open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream):
            hour = datetime.fromisoformat(f"{row[0]} {row[1]}").hour
            mode = (
                "Midnight"
                if hour < 6
                else "Morning"
                if hour < 10
                else "Daytime"
                if hour < 18
                else "Night"
            )
            mode_event_counts[mode] += 1
    all_output = build_output + "\n" + series_output
    warnings = [line.strip() for line in all_output.splitlines() if "warning" in line.lower()]
    summary = {
        "contract": {
            "sample_and_hold_seconds": 1,
            "delayed_off_seconds": args.smoothing_window_sec,
            "representative_states_k": args.n_states,
            "hamming_threshold": args.hamming_threshold,
        },
        **input_metrics,
        "excluded_events_total": (
            input_metrics["input_lines"] - input_metrics["converted_sensor_events"]
        ),
        "used_raw_sensor_count": len(raw_sensors),
        "mapped_sensor_name_count": len({sensor_map.get(sensor, sensor) for sensor in raw_sensors}),
        "unmapped_sensor_count": len(raw_sensors - set(sensor_map)),
        "sample_hold_rows": args.days * 24 * 60 * 60,
        **state_series_metrics(state_rows, adl_intervals),
        "representative_state_count": sum(
            1 for node in network["nodes"] if node["state_id"] not in OTHER_STATES
        ),
        "network_node_count": len(network["nodes"]),
        "network_edge_count": len(network["edges"]),
        "time_mode_event_counts": dict(sorted(mode_event_counts.items())),
        "warning_count": len(warnings),
        "warnings": warnings,
        "errors": [],
        "build_runtime_seconds": build_seconds,
        "state_series_runtime_seconds": series_seconds,
        "total_runtime_seconds": build_seconds + series_seconds,
        "child_max_rss_bytes": (
            int(max(before_usage.ru_maxrss, after_usage.ru_maxrss))
            if sys.platform == "darwin"
            else int(max(before_usage.ru_maxrss, after_usage.ru_maxrss) * 1024)
        ),
        "converted_csv": str(converted),
        "state_table": str(state_table),
        "state_series": str(state_series),
        "network_json": str(network_json),
    }
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
