#!/usr/bin/env python3
"""Build representative states and transition networks from labeled CASAS data."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from experiment_config import DATASET_NAME, ROOT_DIR as PROJECT_ROOT
from src.behavior_pattern_mining.evaluation.adl import DEFAULT_ARUBA_SENSOR_ID_MAP
from src.behavior_pattern_mining.visualization.state_transition_visualizer import (
    StateTransitionVisualizer,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build network/state artifacts from a labeled CASAS text file"
    )
    parser.add_argument(
        "--labeled-casas",
        type=Path,
        default=PROJECT_ROOT / "new_labeled_data" / f"{DATASET_NAME}.txt",
        help="Labeled CASAS txt file containing sensor events and activity begin/end labels",
    )
    parser.add_argument(
        "--sensor-map",
        type=Path,
        default=PROJECT_ROOT / "configs" / "aruba_sensor_map.json",
        help="JSON map from CASAS sensor IDs to representative-state sensor names",
    )
    parser.add_argument(
        "--keep-converted-csv",
        type=Path,
        default=None,
        help="Optional path to save the converted 4-column event CSV for inspection",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Number of days used to build representative states and transition networks",
    )
    parser.add_argument(
        "--n-states",
        type=int,
        default=None,
        help="Number of representative states K. Defaults to configs/default.yaml.",
    )
    parser.add_argument(
        "--hamming-threshold",
        type=int,
        default=None,
        help="Hamming distance threshold for state mapping. Defaults to configs/default.yaml.",
    )
    return parser.parse_args()


def load_sensor_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return dict(DEFAULT_ARUBA_SENSOR_ID_MAP)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Sensor map must be a JSON object: {path}")
    return {str(key).strip(): str(value).strip() for key, value in payload.items()}


def convert_labeled_casas_to_event_csv(
    labeled_casas_path: Path,
    output_csv_path: Path,
    sensor_map: dict[str, str],
) -> int:
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    with labeled_casas_path.open("r", encoding="utf-8") as src:
        with output_csv_path.open("w", encoding="utf-8", newline="") as dst:
            writer = csv.writer(dst)
            for raw_line in src:
                parts = raw_line.strip().split()
                if len(parts) < 4:
                    continue
                value = parts[3].upper()
                if value not in {"ON", "OFF", "OPEN", "CLOSE", "PRESENT", "ABSENT"}:
                    continue
                sensor = sensor_map.get(parts[2].strip(), parts[2].strip())
                writer.writerow([parts[0], parts[1], sensor, value])
                row_count += 1
    return row_count


def main() -> None:
    args = parse_args()
    if not args.labeled_casas.exists():
        raise FileNotFoundError(f"Labeled CASAS file not found: {args.labeled_casas}")

    sensor_map = load_sensor_map(args.sensor_map)

    if args.keep_converted_csv is not None:
        converted_csv = args.keep_converted_csv
        event_count = convert_labeled_casas_to_event_csv(args.labeled_casas, converted_csv, sensor_map)
        print(f"Converted labeled CASAS events: {event_count} -> {converted_csv}")
        visualizer_kwargs = {"data_duration_days": args.days}
        if args.n_states is not None:
            visualizer_kwargs["n_representative_states"] = args.n_states
        if args.hamming_threshold is not None:
            visualizer_kwargs["hamming_threshold"] = args.hamming_threshold
        visualizer = StateTransitionVisualizer(**visualizer_kwargs)
        visualizer.main(str(converted_csv), mode_split=True)
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        converted_csv = Path(tmpdir) / f"{DATASET_NAME}.csv"
        event_count = convert_labeled_casas_to_event_csv(args.labeled_casas, converted_csv, sensor_map)
        print(f"Converted labeled CASAS events: {event_count} -> {converted_csv}")
        visualizer_kwargs = {"data_duration_days": args.days}
        if args.n_states is not None:
            visualizer_kwargs["n_representative_states"] = args.n_states
        if args.hamming_threshold is not None:
            visualizer_kwargs["hamming_threshold"] = args.hamming_threshold
        visualizer = StateTransitionVisualizer(**visualizer_kwargs)
        visualizer.main(str(converted_csv), mode_split=True)


if __name__ == "__main__":
    main()
