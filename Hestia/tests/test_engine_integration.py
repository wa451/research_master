from __future__ import annotations

import csv
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from conftest import ROOT

from smart_home_sim.config import load_scenario
from smart_home_sim.engine import SimulationEngine
from smart_home_sim.schema import Scenario


def read_events(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_room_motion_door_and_output_invariants(tmp_path: Path) -> None:
    scenario = load_scenario(ROOT / "examples/aruba_single_resident.yaml")
    result = SimulationEngine(scenario, days=1, seed=42).run(tmp_path / "run")
    rows = read_events(result.output_dir / "events.csv")
    assert result.event_count == len(rows) > 0
    assert result.simple_event_count > 0
    assert result.state_count > 0
    assert (result.output_dir / "aruba.txt").stat().st_size > 0
    assert (result.output_dir / "sensor_map.csv").stat().st_size > 0
    assert result.validation["timestamps_sorted"] is True

    simple_rows = read_events(result.output_dir / "events_simple.csv")
    latest_simple_state: dict[str, str] = {}
    for row in simple_rows:
        assert latest_simple_state.get(row["device_id"]) != row["state"]
        latest_simple_state[row["device_id"]] = row["state"]

    door_rows = [row for row in rows if row["device_id"] == "D_BED_HALL"]
    assert [row["state"] for row in door_rows[:3]] == ["CLOSE", "OPEN", "CLOSE"]
    opened = datetime.fromisoformat(door_rows[1]["timestamp"])
    closed = datetime.fromisoformat(door_rows[2]["timestamp"])
    assert (closed - opened).total_seconds() == 4

    bedroom_motion = [row for row in rows if row["device_id"] == "M001"]
    assert bedroom_motion[0]["state"] == "ON"
    assert any(
        row["state"] == "OFF" and row["resident_id"] == "resident_1" for row in bedroom_motion
    )


def test_multi_resident_motion_and_preference_priority(tmp_path: Path) -> None:
    scenario = load_scenario(ROOT / "examples/two_residents.yaml")
    result = SimulationEngine(scenario, days=1, seed=123).run(tmp_path / "two")
    rows = read_events(result.output_dir / "events.csv")

    for row in rows:
        if row["device_id"] == "ML" and row["state"] == "OFF":
            assert json.loads(row["occupants"])["living"] == []

    prioritized = [
        row
        for row in rows
        if row["device_id"] == "AC"
        and row["state"] == "ON"
        and '"controlled_by":"alice"' in row["value"]
    ]
    assert prioritized
    assert all('"temperature":22' in row["value"] for row in prioritized)
    assert any(
        set(json.loads(row["occupants"])["living"]) == {"alice", "bob"} for row in prioritized
    )
    assert any(row["event_source"] == "secondary_activity_start" for row in rows)


def test_activity_crossing_midnight_is_clipped_without_time_reversal(
    tmp_path: Path, minimal_scenario_data: dict[str, Any]
) -> None:
    data = deepcopy(minimal_scenario_data)
    stay = next(activity for activity in data["activities"] if activity["id"] == "stay_home")
    stay["base_duration_minutes"] = 1500
    stay["variation_fraction"] = 0
    stay["secondary_activities"] = []
    for routine in data["residents"][0]["weekly_routine"].values():
        routine[:] = ["stay_home"]
    scenario = Scenario.model_validate(data)
    result = SimulationEngine(scenario, days=1, seed=1).run(tmp_path / "overnight")
    rows = read_events(result.output_dir / "events.csv")
    boundaries = [row for row in rows if row["device_type"] == "ActivityBoundary"]
    assert boundaries[-1]["state"] == "END"
    assert datetime.fromisoformat(boundaries[-1]["timestamp"]).date().isoformat() == "2025-01-07"
    timestamps = [datetime.fromisoformat(row["timestamp"]) for row in rows]
    assert timestamps == sorted(timestamps)
