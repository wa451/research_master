from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from conftest import ROOT
from pydantic import ValidationError

from smart_home_sim.config import load_scenario
from smart_home_sim.schema import DeviceType, Scenario


def test_examples_validate_and_expose_all_required_device_types() -> None:
    first = load_scenario(ROOT / "examples/aruba_single_resident.yaml")
    second = load_scenario(ROOT / "examples/two_residents.yaml")
    observed = {
        device.type
        for scenario in (first, second)
        for room in scenario.rooms
        for device in room.devices
    }
    assert {
        DeviceType.MOTION_SENSOR,
        DeviceType.CONTACT_SENSOR,
        DeviceType.DOOR_SENSOR,
        DeviceType.LIGHT,
        DeviceType.AIR_CONDITIONER,
        DeviceType.TELEVISION,
        DeviceType.SMART_PLUG,
        DeviceType.COFFEE_MACHINE,
    } <= observed


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda data: data["connections"][0].update({"travel_seconds": -1}),
            "greater than or equal to 0",
        ),
        (
            lambda data: data["connections"][0].update({"target": "missing"}),
            "unknown room 'missing'",
        ),
        (
            lambda data: data["activities"][1]["secondary_activities"].append(
                {
                    "activity_id": "quick_break",
                    "probability": 0.8,
                    "block_minutes": 5,
                }
            ),
            "probabilities sum",
        ),
        (
            lambda data: data["residents"][0]["weekly_routine"].pop("sunday"),
            "missing weekly routines",
        ),
    ],
)
def test_invalid_scenario_reports_precise_context(
    minimal_scenario_data: dict[str, Any], mutator: Any, message: str
) -> None:
    data = deepcopy(minimal_scenario_data)
    mutator(data)
    with pytest.raises(ValidationError, match=message):
        Scenario.model_validate(data)


def test_unreachable_room_is_rejected(minimal_scenario_data: dict[str, Any]) -> None:
    data = deepcopy(minimal_scenario_data)
    data["rooms"].append({"id": "island", "name": "Island", "capacity": 1, "devices": []})
    with pytest.raises(ValidationError, match=r"unreachable rooms.*island"):
        Scenario.model_validate(data)


def test_naive_start_datetime_is_rejected(minimal_scenario_data: dict[str, Any]) -> None:
    data = deepcopy(minimal_scenario_data)
    data["start_datetime"] = "2025-01-06T00:00:00"
    with pytest.raises(ValidationError, match="explicit UTC offset"):
        Scenario.model_validate(data)


def test_one_door_sensor_cannot_describe_multiple_connections(
    minimal_scenario_data: dict[str, Any],
) -> None:
    data = deepcopy(minimal_scenario_data)
    data["rooms"].append({"id": "annex", "name": "Annex", "capacity": 1, "devices": []})
    data["connections"].append(
        {
            "source": "home",
            "target": "annex",
            "travel_seconds": 1,
            "door_sensor_id": "D1",
        }
    )
    with pytest.raises(ValidationError, match="used by multiple connections"):
        Scenario.model_validate(data)


@pytest.mark.parametrize(
    ("target", "state"),
    [("initial", "BROKEN"), ("action", "OPEN")],
)
def test_unsupported_device_states_are_rejected(
    minimal_scenario_data: dict[str, Any], target: str, state: str
) -> None:
    data = deepcopy(minimal_scenario_data)
    if target == "initial":
        data["rooms"][0]["devices"][0]["initial_state"] = state
    else:
        data["activities"][1]["device_actions"][0]["state"] = state
    with pytest.raises(ValidationError, match="unsupported state"):
        Scenario.model_validate(data)


def test_probability_above_one_is_rejected(minimal_scenario_data: dict[str, Any]) -> None:
    data = deepcopy(minimal_scenario_data)
    data["activities"][1]["secondary_activities"][0]["probability"] = 1.01
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        Scenario.model_validate(data)


def test_activity_cannot_operate_passive_sensor(minimal_scenario_data: dict[str, Any]) -> None:
    data = deepcopy(minimal_scenario_data)
    data["activities"][1]["device_actions"][0] = {"device_id": "M1", "state": "ON"}
    with pytest.raises(ValidationError, match="cannot directly operate passive sensor 'M1'"):
        Scenario.model_validate(data)
