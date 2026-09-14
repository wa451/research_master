from __future__ import annotations

from conftest import ROOT

from smart_home_sim.config import load_scenario
from smart_home_sim.home import HomeGraph
from smart_home_sim.randomness import RandomManager
from smart_home_sim.schema import SecondaryActivityRule


def test_weighted_shortest_path_is_deterministic() -> None:
    scenario = load_scenario(ROOT / "examples/aruba_single_resident.yaml")
    graph = HomeGraph(scenario)
    assert graph.shortest_path("bedroom", "kitchen") == ["bedroom", "hallway", "kitchen"]
    assert graph.connection("hallway", "bedroom").travel_seconds == 4


def test_duration_variation_is_seeded_and_bounded() -> None:
    first = RandomManager(42)
    repeat = RandomManager(42)
    different = RandomManager(43)
    values = [first.varied_duration(100, 0.2) for _ in range(5)]
    assert values == [repeat.varied_duration(100, 0.2) for _ in range(5)]
    assert values != [different.varied_duration(100, 0.2) for _ in range(5)]
    assert all(80 <= value <= 120 for value in values)


def test_secondary_selection_respects_probability_and_factor() -> None:
    certain = SecondaryActivityRule(activity_id="break", probability=1, block_minutes=10)
    never = RandomManager(1).choose_secondary([certain], factor=0)
    selected = RandomManager(1).choose_secondary([certain], factor=1)
    assert never is None
    assert selected == certain
