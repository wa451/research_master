from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from conftest import ROOT

from smart_home_sim.config import load_scenario
from smart_home_sim.engine import SimulationEngine
from smart_home_sim.schema import Scenario


def test_same_seed_hash_matches_and_different_seed_changes(tmp_path: Path) -> None:
    scenario = load_scenario(ROOT / "examples/aruba_single_resident.yaml")
    first = SimulationEngine(scenario, days=2, seed=42).run(tmp_path / "first")
    repeat = SimulationEngine(scenario, days=2, seed=42).run(tmp_path / "repeat")
    different = SimulationEngine(scenario, days=2, seed=43).run(tmp_path / "different")
    assert first.content_hash == repeat.content_hash
    assert (first.output_dir / "events.csv").read_bytes() == (
        repeat.output_dir / "events.csv"
    ).read_bytes()
    assert first.content_hash != different.content_hash


def test_input_collection_order_does_not_change_output(tmp_path: Path) -> None:
    original = load_scenario(ROOT / "examples/aruba_single_resident.yaml")
    reordered_data = deepcopy(original.model_dump())
    for key in ("rooms", "connections", "activities", "residents"):
        reordered_data[key].reverse()
    for room in reordered_data["rooms"]:
        room["devices"].reverse()
    for resident in reordered_data["residents"]:
        resident["weekly_routine"] = dict(reversed(resident["weekly_routine"].items()))
        resident["preferences"] = dict(reversed(resident["preferences"].items()))
    reordered = Scenario.model_validate(reordered_data)

    first = SimulationEngine(original, days=2, seed=9).run(tmp_path / "ordered")
    second = SimulationEngine(reordered, days=2, seed=9).run(tmp_path / "reordered")
    assert first.content_hash == second.content_hash


def test_seven_day_sample_simulation(tmp_path: Path) -> None:
    scenario = load_scenario(ROOT / "examples/aruba_single_resident.yaml")
    result = SimulationEngine(scenario, days=7, seed=42).run(tmp_path / "seven_days")
    assert result.event_count > 500
    assert {key: value for key, value in result.validation.items() if key != "semantic"} == {
        "rows": result.event_count,
        "first_timestamp": result.validation["first_timestamp"],
        "last_timestamp": result.validation["last_timestamp"],
        "timestamps_sorted": True,
        "required_values_present": True,
        "door_transitions_valid": True,
        "room_capacities_valid": True,
        "activity_rooms_valid": True,
    }
    assert all(result.validation["semantic"]["checks"].values())
