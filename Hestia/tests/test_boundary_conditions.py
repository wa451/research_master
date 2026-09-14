from __future__ import annotations

import csv
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from smart_home_sim.engine import SimulationEngine
from smart_home_sim.errors import OutputValidationError
from smart_home_sim.events import EVENT_COLUMNS
from smart_home_sim.schema import Scenario
from smart_home_sim.validation import validate_generated_events


def daily(activity_ids: list[str]) -> dict[str, list[str]]:
    return {
        weekday: list(activity_ids)
        for weekday in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )
    }


def read_events(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_opposing_residents_share_one_door_without_deadlock(
    tmp_path: Path, minimal_scenario_data: dict[str, Any]
) -> None:
    data = deepcopy(minimal_scenario_data)
    data["rooms"][0]["capacity"] = 1
    data["rooms"][1]["capacity"] = 1
    stay = next(item for item in data["activities"] if item["id"] == "stay_home")
    stay["base_duration_minutes"] = 5
    stay["variation_fraction"] = 0
    stay["secondary_activities"] = []
    go_outside = next(item for item in data["activities"] if item["id"] == "go_outside")
    go_outside["base_duration_minutes"] = 5
    data["residents"][0]["id"] = "a_home"
    data["residents"][0]["weekly_routine"] = daily(["go_outside"])
    data["residents"].append(
        {
            "id": "b_outside",
            "name": "Outside resident",
            "initial_room_id": "outside",
            "weekly_routine": daily(["stay_home"]),
        }
    )
    scenario = Scenario.model_validate(data)

    result = SimulationEngine(scenario, days=1, seed=1).run(tmp_path / "opposing")
    doors = [
        row for row in read_events(result.output_dir / "events.csv") if row["device_id"] == "D1"
    ]

    assert [row["state"] for row in doors] == ["CLOSE", "OPEN", "CLOSE", "OPEN", "CLOSE"]
    assert {row["resident_id"] for row in doors[1:]} == {"a_home", "b_outside"}


def test_full_room_waits_until_capacity_is_released(
    tmp_path: Path, minimal_scenario_data: dict[str, Any]
) -> None:
    data = deepcopy(minimal_scenario_data)
    data["rooms"][0]["capacity"] = 1
    data["rooms"][1]["capacity"] = 1
    data["rooms"][0]["devices"].append({"id": "D2", "type": "DoorSensor", "name": "Annex door"})
    data["rooms"].append(
        {
            "id": "annex",
            "name": "Annex",
            "capacity": 1,
            "devices": [{"id": "MA", "type": "MotionSensor", "name": "Annex motion"}],
        }
    )
    data["connections"].append(
        {
            "source": "home",
            "target": "annex",
            "travel_seconds": 1,
            "door_sensor_id": "D2",
        }
    )
    stay = next(item for item in data["activities"] if item["id"] == "stay_home")
    stay["base_duration_minutes"] = 1
    stay["variation_fraction"] = 0
    stay["secondary_activities"] = []
    data["activities"].extend(
        [
            {
                "id": "move_annex",
                "name": "Move to annex",
                "room_id": "annex",
                "base_duration_minutes": 5,
                "adl_label": "Work",
            },
            {
                "id": "visit_home",
                "name": "Visit home",
                "room_id": "home",
                "base_duration_minutes": 5,
                "adl_label": "Enter_Home",
            },
        ]
    )
    data["residents"][0]["id"] = "host"
    data["residents"][0]["weekly_routine"] = daily(["stay_home", "move_annex"])
    data["residents"].append(
        {
            "id": "visitor",
            "name": "Visitor",
            "initial_room_id": "outside",
            "weekly_routine": daily(["visit_home"]),
        }
    )
    scenario = Scenario.model_validate(data)

    result = SimulationEngine(scenario, days=1, seed=1).run(tmp_path / "capacity")
    visit_start = next(
        row
        for row in read_events(result.output_dir / "events.csv")
        if row["activity_id"] == "visit_home" and row["state"] == "START"
    )

    assert datetime.fromisoformat(visit_start["timestamp"]) >= scenario.start_datetime.replace(
        minute=1
    )


def test_long_secondary_activity_is_nested_and_returns_to_primary_room(
    tmp_path: Path, minimal_scenario_data: dict[str, Any]
) -> None:
    data = deepcopy(minimal_scenario_data)
    stay = next(item for item in data["activities"] if item["id"] == "stay_home")
    stay.update(
        {
            "base_duration_minutes": 12,
            "variation_fraction": 0,
            "secondary_activities": [
                {
                    "activity_id": "quick_break",
                    "probability": 1,
                    "block_minutes": 1,
                    "preserve_primary_devices": False,
                }
            ],
        }
    )
    quick = next(item for item in data["activities"] if item["id"] == "quick_break")
    quick["base_duration_minutes"] = 10
    data["residents"][0]["weekly_routine"] = daily(["stay_home"])
    scenario = Scenario.model_validate(data)

    result = SimulationEngine(scenario, days=1, seed=1).run(tmp_path / "secondary")
    rows = read_events(result.output_dir / "events.csv")
    quick_rows = [row for row in rows if row["activity_id"] == "quick_break"]
    boundaries = [row for row in quick_rows if row["device_type"] == "ActivityBoundary"]
    resumed_home = [
        row
        for row in rows
        if row["event_source"] == "room_entry"
        and row["resident_id"] == "r1"
        and row["room_id"] == "home"
    ]

    assert [row["state"] for row in boundaries] == ["START", "END"]
    assert (
        datetime.fromisoformat(boundaries[1]["timestamp"])
        - datetime.fromisoformat(boundaries[0]["timestamp"])
    ).total_seconds() == 600
    assert resumed_home


def test_empty_routine_and_nonpositive_days_are_handled(
    tmp_path: Path, minimal_scenario_data: dict[str, Any]
) -> None:
    data = deepcopy(minimal_scenario_data)
    data["residents"][0]["weekly_routine"] = daily([])
    scenario = Scenario.model_validate(data)
    result = SimulationEngine(scenario, days=1, seed=1).run(tmp_path / "empty")
    rows = read_events(result.output_dir / "events.csv")

    assert rows
    assert not [row for row in rows if row["device_type"] == "ActivityBoundary"]
    with pytest.raises(ValueError, match="greater than zero"):
        SimulationEngine(scenario, days=0, seed=1)
    with pytest.raises(ValueError, match="greater than zero"):
        SimulationEngine(scenario, days=-1, seed=1)


def test_initially_on_device_is_on_after_final_activity(
    tmp_path: Path, minimal_scenario_data: dict[str, Any]
) -> None:
    data = deepcopy(minimal_scenario_data)
    light = next(item for item in data["rooms"][0]["devices"] if item["id"] == "L1")
    light["initial_state"] = "ON"
    light["initial_attributes"] = {"brightness": 10, "color_temperature": 2700}
    stay = next(item for item in data["activities"] if item["id"] == "stay_home")
    stay["variation_fraction"] = 0
    stay["secondary_activities"] = []
    data["residents"][0]["weekly_routine"] = daily(["stay_home"])
    scenario = Scenario.model_validate(data)

    result = SimulationEngine(scenario, days=1, seed=1).run(tmp_path / "initial-on")
    lights = [
        row for row in read_events(result.output_dir / "events.csv") if row["device_id"] == "L1"
    ]

    assert lights[-1]["state"] == "ON"
    assert '"brightness":10' in lights[-1]["value"]


def test_invalid_action_reference_and_initially_open_connected_door_are_rejected(
    minimal_scenario_data: dict[str, Any],
) -> None:
    missing = deepcopy(minimal_scenario_data)
    missing["activities"][1]["device_actions"][0]["device_id"] = "missing"
    with pytest.raises(ValidationError, match="unknown device 'missing'"):
        Scenario.model_validate(missing)

    open_door = deepcopy(minimal_scenario_data)
    door = next(item for item in open_door["rooms"][0]["devices"] if item["id"] == "D1")
    door["initial_state"] = "OPEN"
    with pytest.raises(ValidationError, match=r"connected door.*closed"):
        Scenario.model_validate(open_door)


def test_semantic_validator_detects_motion_occupancy_corruption(
    tmp_path: Path, minimal_scenario_data: dict[str, Any]
) -> None:
    scenario = Scenario.model_validate(deepcopy(minimal_scenario_data))
    result = SimulationEngine(scenario, days=1, seed=1).run(tmp_path / "valid")
    rows = read_events(result.output_dir / "events.csv")
    target = next(
        row
        for row in rows
        if row["device_id"] == "M1" and row["event_source"] == "room_exit" and row["state"] == "OFF"
    )
    target["state"] = "OPEN"
    target["value"] = "OPEN"
    corrupted = tmp_path / "corrupted.csv"
    with corrupted.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=EVENT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(OutputValidationError, match=r"motion 'M1'.*occupancy requires OFF"):
        validate_generated_events(corrupted, scenario)


def test_all_motion_sensors_in_one_room_follow_occupancy(
    tmp_path: Path, minimal_scenario_data: dict[str, Any]
) -> None:
    data = deepcopy(minimal_scenario_data)
    data["rooms"][0]["devices"].append(
        {"id": "M1_SECOND", "type": "MotionSensor", "name": "Second motion"}
    )
    scenario = Scenario.model_validate(data)
    result = SimulationEngine(scenario, days=1, seed=1).run(tmp_path / "two-motion")
    rows = read_events(result.output_dir / "events.csv")

    for sensor_id in ("M1", "M1_SECOND"):
        states = [row["state"] for row in rows if row["device_id"] == sensor_id]
        assert states[:2] == ["ON", "OFF"]
