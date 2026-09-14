from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def minimal_scenario_data() -> dict[str, Any]:
    daily = ["stay_home", "go_outside"]
    return {
        "schema_version": 1,
        "id": "minimal",
        "name": "Minimal test home",
        "start_datetime": "2025-01-06T00:00:00+09:00",
        "rooms": [
            {
                "id": "home",
                "name": "Home",
                "capacity": 2,
                "devices": [
                    {"id": "M1", "type": "MotionSensor", "name": "Motion"},
                    {"id": "L1", "type": "Light", "name": "Light"},
                    {"id": "D1", "type": "DoorSensor", "name": "Door"},
                ],
            },
            {
                "id": "outside",
                "name": "Outside",
                "capacity": 4,
                "is_outside": True,
                "devices": [{"id": "MO", "type": "MotionSensor", "name": "Outside motion"}],
            },
        ],
        "connections": [
            {
                "source": "home",
                "target": "outside",
                "travel_seconds": 5,
                "door_sensor_id": "D1",
            }
        ],
        "activities": [
            {
                "id": "quick_break",
                "name": "Quick break",
                "room_id": "outside",
                "base_duration_minutes": 2,
                "variation_fraction": 0,
                "adl_label": "Break",
            },
            {
                "id": "stay_home",
                "name": "Stay home",
                "room_id": "home",
                "base_duration_minutes": 20,
                "variation_fraction": 0.2,
                "device_actions": [
                    {
                        "device_id": "L1",
                        "state": "ON",
                        "attributes": {"brightness": 50, "color_temperature": 3200},
                    }
                ],
                "secondary_activities": [
                    {
                        "activity_id": "quick_break",
                        "probability": 0.25,
                        "block_minutes": 5,
                    }
                ],
                "adl_label": "Relax",
            },
            {
                "id": "go_outside",
                "name": "Go outside",
                "room_id": "outside",
                "base_duration_minutes": 5,
                "variation_fraction": 0,
                "adl_label": "Leave_Home",
            },
        ],
        "residents": [
            {
                "id": "r1",
                "name": "Resident",
                "initial_room_id": "home",
                "priority": 1,
                "preferences": {"L1": {"brightness": 40, "color_temperature": 3000}},
                "weekly_routine": {
                    "monday": deepcopy(daily),
                    "tuesday": deepcopy(daily),
                    "wednesday": deepcopy(daily),
                    "thursday": deepcopy(daily),
                    "friday": deepcopy(daily),
                    "saturday": deepcopy(daily),
                    "sunday": deepcopy(daily),
                },
            }
        ],
    }
