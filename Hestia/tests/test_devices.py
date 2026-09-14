from __future__ import annotations

from collections.abc import Generator
from typing import Any

import simpy
from conftest import ROOT

from smart_home_sim.config import load_scenario
from smart_home_sim.devices import DeviceManager
from smart_home_sim.events import EventCollector
from smart_home_sim.models import ActivityUse
from smart_home_sim.schema import Scenario


def test_shared_device_priority_reconfiguration_and_duplicate_suppression() -> None:
    scenario = load_scenario(ROOT / "examples/two_residents.yaml")
    env = simpy.Environment()
    collector = EventCollector(
        start_datetime=scenario.start_datetime,
        run_id="device-test",
        seed=1,
        now=lambda: float(env.now),
        occupants=lambda: {room.id: [] for room in scenario.rooms},
    )
    manager = DeviceManager(env, scenario, collector)
    activity = scenario.activity_by_id["shared_evening"]
    ac_action = next(action for action in activity.device_actions if action.device_id == "AC")
    alice = scenario.resident_by_id["alice"]
    bob = scenario.resident_by_id["bob"]
    bob_use = ActivityUse(bob, activity, ac_action)
    alice_use = ActivityUse(alice, activity, ac_action)

    def operate() -> Generator[Any, Any, None]:
        yield from manager.begin_use(bob_use)
        before_duplicate = len(collector.records)
        yield from manager.begin_use(bob_use)
        assert len(collector.records) == before_duplicate
        yield from manager.begin_use(alice_use)
        yield from manager.end_use(alice_use)
        yield from manager.end_use(bob_use)

    env.process(operate())
    env.run()
    values = [record.value for record in collector.records if record.device_id == "AC"]
    states = [record.state for record in collector.records if record.device_id == "AC"]
    assert states == ["ON", "ON", "ON", "OFF"]
    assert '"temperature":25' in values[0]
    assert '"controlled_by":"alice"' in values[1]
    assert '"temperature":22' in values[1]
    assert '"controlled_by":"bob"' in values[2]


def test_device_restores_state_and_attributes_from_before_first_use() -> None:
    scenario = load_scenario(ROOT / "examples/two_residents.yaml")
    env = simpy.Environment()
    collector = EventCollector(
        start_datetime=scenario.start_datetime,
        run_id="restore-test",
        seed=1,
        now=lambda: float(env.now),
        occupants=lambda: {room.id: [] for room in scenario.rooms},
    )
    manager = DeviceManager(env, scenario, collector)
    device = manager.devices["AC"]
    device.state = "ON"
    device.attributes = {"temperature": 19, "mode": "heat"}
    activity = scenario.activity_by_id["shared_evening"]
    action = next(item for item in activity.device_actions if item.device_id == "AC")
    use = ActivityUse(scenario.resident_by_id["bob"], activity, action)

    def operate() -> Generator[Any, Any, None]:
        yield from manager.begin_use(use)
        yield from manager.end_use(use)

    env.process(operate())
    env.run()

    assert device.state == "ON"
    assert device.attributes == {"temperature": 19, "mode": "heat"}
    assert collector.records[-1].state == "ON"
    assert '"temperature":19' in collector.records[-1].value


def test_equal_priority_uses_resident_id_as_tie_breaker() -> None:
    scenario_data = load_scenario(ROOT / "examples/two_residents.yaml").model_dump()
    for resident in scenario_data["residents"]:
        resident["priority"] = 5
    scenario = Scenario.model_validate(scenario_data)
    env = simpy.Environment()
    collector = EventCollector(
        start_datetime=scenario.start_datetime,
        run_id="tie-test",
        seed=1,
        now=lambda: float(env.now),
        occupants=lambda: {room.id: [] for room in scenario.rooms},
    )
    manager = DeviceManager(env, scenario, collector)
    activity = scenario.activity_by_id["shared_evening"]
    action = next(item for item in activity.device_actions if item.device_id == "AC")

    def operate() -> Generator[Any, Any, None]:
        yield from manager.begin_use(ActivityUse(scenario.resident_by_id["bob"], activity, action))
        yield from manager.begin_use(
            ActivityUse(scenario.resident_by_id["alice"], activity, action)
        )

    env.process(operate())
    env.run()
    assert '"controlled_by":"alice"' in collector.records[-1].value
