from __future__ import annotations

import csv
import json
from copy import deepcopy
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
from conftest import ROOT
from pydantic import ValidationError

from smart_home_sim.config import load_scenario
from smart_home_sim.engine import SimulationEngine
from smart_home_sim.randomness import RandomManager
from smart_home_sim.schema import DistributionConfig, Scenario


def _daily(items: list[Any]) -> dict[str, list[Any]]:
    return {
        day: deepcopy(items)
        for day in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _zone_scenario_data(minimal_scenario_data: dict[str, Any]) -> dict[str, Any]:
    data = deepcopy(minimal_scenario_data)
    room = data["rooms"][0]
    room.update(
        {
            "motion_mode": "zone",
            "default_zone_id": "home_a",
            "zones": [
                {"id": "home_a", "name": "Home A"},
                {"id": "home_b", "name": "Home B"},
            ],
            "zone_connections": [{"source": "home_a", "target": "home_b", "travel_seconds": 2}],
        }
    )
    room["devices"][0]["zone_id"] = "home_a"
    room["devices"].append(
        {"id": "M2", "type": "MotionSensor", "name": "Motion B", "zone_id": "home_b"}
    )
    resident = data["residents"][0]
    resident["initial_zone_id"] = "home_a"
    resident["weekly_routine"] = _daily(["stay_home"])
    stay = next(item for item in data["activities"] if item["id"] == "stay_home")
    stay.update(
        {
            "base_duration_minutes": 5,
            "variation_fraction": 0,
            "zone_id": "home_a",
            "device_actions": [],
            "secondary_activities": [],
            "micro_action_templates": [
                {
                    "id": "cross_room",
                    "steps": [
                        {
                            "id": "visit_b",
                            "zone_id": "home_b",
                            "dwell_minutes": {"kind": "fixed", "value": 1},
                        }
                    ],
                }
            ],
        }
    )
    return data


def test_functional_inheritance_is_the_exact_existing_scenario() -> None:
    original = load_scenario(ROOT / "examples/aruba_single_resident.yaml")
    functional = load_scenario(ROOT / "examples/functional/aruba_single_resident.yaml")
    assert functional.model_dump() == original.model_dump()


def test_zone_motion_path_trace_and_room_category_mapping(
    tmp_path: Path, minimal_scenario_data: dict[str, Any]
) -> None:
    scenario = Scenario.model_validate(_zone_scenario_data(minimal_scenario_data))
    result = SimulationEngine(scenario, days=1, seed=3).run(tmp_path / "zone")
    rows = _read_csv(result.output_dir / "events.csv")
    trace = _read_csv(result.output_dir / "activity_trace.csv")
    mapping = json.loads((result.output_dir / "casas_sensor_map_room.json").read_text())

    assert [row["state"] for row in rows if row["device_id"] == "M1"][:3] == [
        "ON",
        "OFF",
        "ON",
    ]
    assert [row["state"] for row in rows if row["device_id"] == "M2"][:3] == [
        "OFF",
        "ON",
        "OFF",
    ]
    assert any(row["step_id"] == "visit_b" and row["phase"] == "START" for row in trace)
    assert mapping["M1"] == mapping["M2"] == "home"


def test_invalid_zone_topologies_are_rejected(
    minimal_scenario_data: dict[str, Any],
) -> None:
    unreachable = _zone_scenario_data(minimal_scenario_data)
    unreachable["rooms"][0]["zones"].append({"id": "home_c", "name": "Home C"})
    with pytest.raises(ValidationError, match="unreachable zones"):
        Scenario.model_validate(unreachable)

    negative = _zone_scenario_data(minimal_scenario_data)
    negative["rooms"][0]["zone_connections"][0]["travel_seconds"] = -1
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Scenario.model_validate(negative)

    duplicate = _zone_scenario_data(minimal_scenario_data)
    duplicate["rooms"][0]["zones"][1]["id"] = "home_a"
    with pytest.raises(ValidationError, match="duplicate zone"):
        Scenario.model_validate(duplicate)


def test_micro_optional_repeat_and_deadline_skip_are_traced(
    tmp_path: Path, minimal_scenario_data: dict[str, Any]
) -> None:
    data = _zone_scenario_data(minimal_scenario_data)
    data["rooms"][0]["zone_connections"][0]["travel_seconds"] = 30
    stay = next(item for item in data["activities"] if item["id"] == "stay_home")
    stay["base_duration_minutes"] = 1
    stay["micro_action_templates"][0]["steps"] = [
        {
            "id": "never",
            "zone_id": "home_b",
            "dwell_minutes": {"kind": "fixed", "value": 0.1},
            "optional_probability": 0,
        },
        {
            "id": "repeated",
            "zone_id": "home_a",
            "dwell_minutes": {"kind": "fixed", "value": 0.1},
            "repeat_count": {"kind": "fixed", "value": 2},
        },
        {
            "id": "too_long",
            "zone_id": "home_b",
            "dwell_minutes": {"kind": "fixed", "value": 10},
        },
    ]
    scenario = Scenario.model_validate(data)
    result = SimulationEngine(scenario, days=1, seed=1).run(tmp_path / "micro")
    trace = _read_csv(result.output_dir / "activity_trace.csv")

    assert any(row["step_id"] == "never" and row["phase"] == "SKIPPED" for row in trace)
    repeated = [row for row in trace if row["step_id"] == "repeated" and row["phase"] == "START"]
    assert [row["occurrence"] for row in repeated] == ["1", "2"]
    assert any(
        row["step_id"] == "too_long"
        and row["phase"] == "SKIPPED"
        and row["reason"] == "insufficient_activity_time"
        for row in trace
    )


def test_weighted_template_choice_and_distribution_sampling_are_reproducible() -> None:
    distribution = DistributionConfig.model_validate(
        {
            "kind": "weighted",
            "choices": [
                {"value": 1, "weight": 1},
                {"value": 3, "weight": 2},
            ],
        }
    )
    first = RandomManager(44)
    repeat = RandomManager(44)
    different = RandomManager(45)
    first_values = [first.sample(distribution) for _ in range(12)]
    assert first_values == [repeat.sample(distribution) for _ in range(12)]
    assert first_values != [different.sample(distribution) for _ in range(12)]


def test_routine_start_gap_duration_and_omission(
    tmp_path: Path, minimal_scenario_data: dict[str, Any]
) -> None:
    data = deepcopy(minimal_scenario_data)
    stay = next(item for item in data["activities"] if item["id"] == "stay_home")
    stay.update(
        {
            "device_actions": [],
            "secondary_activities": [],
            "duration_distribution": {"kind": "fixed", "value": 3},
            "min_duration_minutes": 2,
            "max_duration_minutes": 4,
        }
    )
    data["residents"][0]["weekly_routine"] = _daily(
        [
            {
                "activity_id": "go_outside",
                "scheduled_start_minute": 20,
                "inclusion_probability": 0,
            },
            {
                "activity_id": "stay_home",
                "scheduled_start_minute": 60,
                "start_jitter_minutes": {"kind": "fixed", "value": 0},
                "gap_before_minutes": {"kind": "fixed", "value": 2},
            },
        ]
    )
    scenario = Scenario.model_validate(data)
    result = SimulationEngine(scenario, days=1, seed=1).run(tmp_path / "routine")
    boundaries = [
        row
        for row in _read_csv(result.output_dir / "events.csv")
        if row["device_type"] == "ActivityBoundary"
    ]
    start = datetime.fromisoformat(boundaries[0]["timestamp"])
    end = datetime.fromisoformat(boundaries[1]["timestamp"])

    assert boundaries[0]["activity_id"] == "stay_home"
    assert (start.hour, start.minute) == (1, 2)
    assert (end - start).total_seconds() == 180


def test_secondary_cooldown_night_window_and_return(
    tmp_path: Path, minimal_scenario_data: dict[str, Any]
) -> None:
    data = deepcopy(minimal_scenario_data)
    stay = next(item for item in data["activities"] if item["id"] == "stay_home")
    stay.update(
        {
            "base_duration_minutes": 25,
            "variation_fraction": 0,
            "secondary_activities": [
                {
                    "activity_id": "quick_break",
                    "probability": 1,
                    "block_minutes": 1,
                    "cooldown_minutes": 8,
                    "max_occurrences": 2,
                    "allowed_start_hour": 23,
                    "allowed_end_hour": 6,
                    "reason": "night_check",
                }
            ],
        }
    )
    data["residents"][0]["weekly_routine"] = _daily(["stay_home"])
    scenario = Scenario.model_validate(data)
    result = SimulationEngine(scenario, days=1, seed=1).run(tmp_path / "secondary")
    trace = _read_csv(result.output_dir / "activity_trace.csv")
    starts = [
        row for row in trace if row["kind"] == "secondary_activity" and row["phase"] == "START"
    ]
    main_end = next(
        row
        for row in _read_csv(result.output_dir / "events.csv")
        if row["activity_id"] == "stay_home" and row["state"] == "END"
    )

    assert len(starts) == 2
    assert all(row["reason"] == "night_check" for row in starts)
    assert main_end["room_id"] == "home"


def test_sensor_truth_observation_audit_and_seed_reproducibility(
    tmp_path: Path, minimal_scenario_data: dict[str, Any]
) -> None:
    data = _zone_scenario_data(minimal_scenario_data)
    data["sensor_imperfections"] = {
        "enabled": True,
        "safe_mode": True,
        "default_profile": {
            "duplicate_probability": 1,
            "false_trigger_probability": 1,
            "detection_delay_seconds": {"kind": "fixed", "value": 2},
            "off_delay_seconds": {"kind": "fixed", "value": 3},
            "clock_skew_seconds": {"kind": "fixed", "value": 1},
            "false_trigger_duration_seconds": {"kind": "fixed", "value": 0.5},
        },
    }
    scenario = Scenario.model_validate(data)
    first = SimulationEngine(scenario, days=1, seed=8).run(tmp_path / "first")
    repeat = SimulationEngine(scenario, days=1, seed=8).run(tmp_path / "repeat")
    audit = _read_csv(first.output_dir / "sensor_imperfection_audit.csv")

    assert first.content_hash == repeat.content_hash
    assert (first.output_dir / "events_true.csv").read_bytes() == (
        first.output_dir / "events.csv"
    ).read_bytes()
    assert (first.output_dir / "events_observed.csv").read_bytes() != (
        first.output_dir / "events_true.csv"
    ).read_bytes()
    assert {row["action"] for row in audit} >= {
        "duplicated",
        "false_triggered",
        "timestamp_shifted",
        "suppressed",
    }


def test_sensor_outage_flip_and_safe_transition_filter(
    tmp_path: Path, minimal_scenario_data: dict[str, Any]
) -> None:
    data = _zone_scenario_data(minimal_scenario_data)
    data["sensor_imperfections"] = {
        "enabled": True,
        "safe_mode": True,
        "profiles": {
            "M1": {"outage_windows": [{"start_minute": 0, "end_minute": 1440}]},
            "M2": {"flip_probability": 1},
        },
    }
    scenario = Scenario.model_validate(data)
    result = SimulationEngine(scenario, days=1, seed=4).run(tmp_path / "faults")
    observed = _read_csv(result.output_dir / "events_observed.csv")
    audit = _read_csv(result.output_dir / "sensor_imperfection_audit.csv")

    assert len([row for row in observed if row["device_id"] == "M1"]) == 1
    assert any(row["reason"] == "configured_outage" for row in audit)
    assert any(row["action"] == "state_flipped" and row["device_id"] == "M2" for row in audit)
    m2_states = [row["state"] for row in observed if row["device_id"] == "M2"]
    assert all(previous != current for previous, current in pairwise(m2_states))


def test_nonreturning_secondary_explicitly_ends_primary_at_new_location(
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
                    "return_to_primary": False,
                    "max_occurrences": 1,
                    "reason": "continue_outside",
                }
            ],
        }
    )
    data["residents"][0]["weekly_routine"] = _daily(["stay_home"])
    scenario = Scenario.model_validate(data)
    result = SimulationEngine(scenario, days=1, seed=2).run(tmp_path / "no_return")
    main_end = next(
        row
        for row in _read_csv(result.output_dir / "events.csv")
        if row["activity_id"] == "stay_home" and row["state"] == "END"
    )
    assert main_end["room_id"] == "outside"
    assert result.validation["semantic"]["checks"]["activity_nesting"] is True


def test_realistic_examples_are_diverse_and_stress_separates_truth(
    tmp_path: Path,
) -> None:
    realistic = load_scenario(ROOT / "examples/realistic_calibrated/aruba_single_resident.yaml")
    first = SimulationEngine(realistic, days=2, seed=21).run(tmp_path / "realistic_a")
    different = SimulationEngine(realistic, days=2, seed=22).run(tmp_path / "realistic_b")
    stress = load_scenario(ROOT / "examples/stress/two_residents_sensor_noise.yaml")
    stress_result = SimulationEngine(stress, days=1, seed=21).run(tmp_path / "stress")

    assert first.content_hash != different.content_hash
    assert first.event_count > 2 * 150
    assert (stress_result.output_dir / "events_true.csv").is_file()
    assert (stress_result.output_dir / "events_observed.csv").is_file()
    assert stress_result.validation["semantic"]["checks"]["device_state_restoration"] is True
    assert not (first.output_dir / "events_true.csv").exists()
