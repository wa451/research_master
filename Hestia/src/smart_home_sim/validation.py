"""Post-generation checks for research-facing output invariants."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

from smart_home_sim.errors import OutputValidationError
from smart_home_sim.events import EVENT_COLUMNS
from smart_home_sim.schema import ActivityConfig, DeviceType, MotionMode, Scenario, Weekday


def _device_value(row: dict[str, str]) -> dict[str, Any]:
    if not row["value"].startswith("{"):
        return {}
    parsed = json.loads(row["value"])
    if not isinstance(parsed, dict):
        raise OutputValidationError(f"device '{row['device_id']}' has a non-object JSON value")
    return parsed


def _expected_use(
    scenario: Scenario,
    device_id: str,
    uses: dict[str, str],
) -> tuple[str, dict[str, Any], str]:
    winner_id = min(
        uses,
        key=lambda resident_id: (-scenario.resident_by_id[resident_id].priority, resident_id),
    )
    activity = scenario.activity_by_id[uses[winner_id]]
    actions = [item for item in activity.device_actions if item.device_id == device_id]
    actions.extend(
        action
        for template in activity.micro_action_templates
        for step in template.steps
        for action in step.device_actions
        if action.device_id == device_id
    )
    if not actions:
        raise OutputValidationError(
            f"activity '{activity.id}' has no configured action for '{device_id}'"
        )
    action = actions[0]
    attributes: dict[str, Any] = dict(action.attributes)
    attributes.update(scenario.resident_by_id[winner_id].preferences.get(device_id, {}))
    return action.state, attributes, winner_id


def audit_event_semantics(rows: list[dict[str, str]], scenario: Scenario) -> dict[str, Any]:
    """Validate relationships that cannot be checked by the CSV schema alone."""
    room_ids = set(scenario.room_by_id)
    resident_ids = set(scenario.resident_by_id)
    adjacency = {room_id: set() for room_id in room_ids}
    connection_by_door = {}
    for connection in scenario.connections:
        adjacency[connection.source].add(connection.target)
        adjacency[connection.target].add(connection.source)
        if connection.door_sensor_id:
            connection_by_door[connection.door_sensor_id] = connection

    last_known_room = {resident.id: resident.initial_room_id for resident in scenario.residents}
    in_transit: set[str] = set()
    motion_states: dict[str, str] = {}
    device_states: dict[str, tuple[str, dict[str, Any]]] = {}
    idle_states: dict[str, tuple[str, dict[str, Any]]] = {}
    device_uses: dict[str, dict[str, str]] = defaultdict(dict)
    activity_stacks: dict[str, list[tuple[str, datetime, bool]]] = defaultdict(list)
    main_starts: dict[str, list[str]] = defaultdict(list)
    open_doors: dict[str, tuple[str, datetime]] = {}
    previous_device_signature: dict[str, tuple[str, str]] = {}
    movement_count = 0
    door_passage_count = 0
    secondary_count = 0
    shared_control_count = 0
    max_room_occupancy = 0
    previous_timestamp: datetime | None = None
    previous_occupants: dict[str, list[str]] | None = None

    motion_room = {
        device.id: room.id
        for room in scenario.rooms
        for device in room.devices
        if device.type is DeviceType.MOTION_SENSOR and room.motion_mode is MotionMode.ROOM
    }
    zone_motion_ids = {
        device.id
        for room in scenario.rooms
        for device in room.devices
        if device.type is DeviceType.MOTION_SENSOR and room.motion_mode is MotionMode.ZONE
    }

    def register_activity_uses(resident_id: str, activity_id: str) -> None:
        configured = scenario.activity_by_id[activity_id]
        for action in configured.device_actions:
            uses = device_uses[action.device_id]
            if not uses:
                previous_state = device_states.get(action.device_id)
                if previous_state is None:
                    raise OutputValidationError(
                        f"activity '{activity_id}' starts use before device "
                        f"'{action.device_id}' initialization"
                    )
                idle_states[action.device_id] = previous_state
            uses[resident_id] = activity_id

    def unregister_activity_uses(resident_id: str, activity_id: str) -> None:
        configured = scenario.activity_by_id[activity_id]
        for action in configured.device_actions:
            uses = device_uses[action.device_id]
            if uses.get(resident_id) == activity_id:
                uses.pop(resident_id)
                if not uses:
                    idle_states.pop(action.device_id, None)

    for index, row in enumerate(rows, start=2):
        timestamp = datetime.fromisoformat(row["timestamp"])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise OutputValidationError(f"row {index} timestamp is not timezone-aware")
        if previous_timestamp is not None and timestamp != previous_timestamp:
            assert previous_occupants is not None
            for motion_id, state in motion_states.items():
                if motion_id in zone_motion_ids:
                    continue
                expected_motion = "ON" if previous_occupants[motion_room[motion_id]] else "OFF"
                if state != expected_motion:
                    raise OutputValidationError(
                        f"row {index - 1} leaves motion '{motion_id}' inconsistent with occupancy"
                    )
        occupants = json.loads(row["occupants"])
        if set(occupants) != room_ids:
            raise OutputValidationError(f"row {index} occupant snapshot has incomplete room keys")
        seen_residents: set[str] = set()
        positions: dict[str, str] = {}
        for room_id in sorted(room_ids):
            listed = occupants[room_id]
            if listed != sorted(listed) or len(listed) != len(set(listed)):
                raise OutputValidationError(
                    f"row {index} occupants for room '{room_id}' are not sorted and unique"
                )
            if len(listed) > scenario.room_by_id[room_id].capacity:
                raise OutputValidationError(f"row {index} exceeds capacity of room '{room_id}'")
            max_room_occupancy = max(max_room_occupancy, len(listed))
            for resident_id in listed:
                if resident_id not in resident_ids:
                    raise OutputValidationError(
                        f"row {index} contains unknown resident '{resident_id}'"
                    )
                if resident_id in seen_residents:
                    raise OutputValidationError(
                        f"row {index} places resident '{resident_id}' in multiple rooms"
                    )
                seen_residents.add(resident_id)
                positions[resident_id] = room_id

        for resident_id in sorted(resident_ids):
            position = positions.get(resident_id)
            previous = last_known_room[resident_id]
            if position is None:
                in_transit.add(resident_id)
            elif resident_id in in_transit:
                if position not in adjacency[previous]:
                    raise OutputValidationError(
                        f"row {index} moves resident '{resident_id}' from '{previous}' "
                        f"to non-adjacent room '{position}'"
                    )
                movement_count += 1
                last_known_room[resident_id] = position
                in_transit.remove(resident_id)
            elif position != previous:
                raise OutputValidationError(
                    f"row {index} changes resident '{resident_id}' room without transit"
                )

        if row["device_type"] != "ActivityBoundary":
            signature = (row["state"], row["value"])
            if previous_device_signature.get(row["device_id"]) == signature:
                raise OutputValidationError(
                    f"row {index} duplicates device state/value for '{row['device_id']}'"
                )
            previous_device_signature[row["device_id"]] = signature

        if row["device_id"] in motion_room:
            expected_motion = "ON" if occupants[motion_room[row["device_id"]]] else "OFF"
            if row["state"] != expected_motion:
                raise OutputValidationError(
                    f"row {index} motion '{row['device_id']}' is {row['state']} while "
                    f"occupancy requires {expected_motion}"
                )
            motion_states[row["device_id"]] = row["state"]
        elif row["device_id"] in zone_motion_ids:
            motion_states[row["device_id"]] = row["state"]
        previous_timestamp = timestamp
        previous_occupants = occupants

        if row["device_type"] == "ActivityBoundary":
            resident_id = row["resident_id"]
            activity = scenario.activity_by_id.get(row["activity_id"])
            if resident_id not in resident_ids or activity is None:
                raise OutputValidationError(f"row {index} has invalid activity references")
            if row["state"] == "START":
                if (
                    row["room_id"] != activity.room_id
                    or positions.get(resident_id) != activity.room_id
                ):
                    raise OutputValidationError(
                        f"row {index} activity '{activity.id}' does not start with its resident "
                        f"in room '{activity.room_id}'"
                    )
            elif positions.get(resident_id) != row["room_id"]:
                raise OutputValidationError(
                    f"row {index} activity '{activity.id}' ends outside its resident's room"
                )
            is_secondary = row["event_source"].startswith("secondary_")
            stack = activity_stacks[resident_id]
            if row["state"] == "START":
                parent_activity: ActivityConfig | None = None
                parent_rule = None
                if is_secondary:
                    if not stack:
                        raise OutputValidationError(
                            f"row {index} starts secondary activity without a primary activity"
                        )
                    parent = scenario.activity_by_id[stack[-1][0]]
                    parent_activity = parent
                    if activity.id not in {
                        rule.activity_id for rule in parent.secondary_activities
                    }:
                        raise OutputValidationError(
                            f"row {index} starts disallowed secondary activity '{activity.id}'"
                        )
                    parent_rule = next(
                        rule
                        for rule in parent.secondary_activities
                        if rule.activity_id == activity.id
                    )
                    secondary_count += 1
                else:
                    main_starts[resident_id].append(activity.id)
                if (
                    parent_activity is not None
                    and parent_rule is not None
                    and not parent_rule.preserve_primary_devices
                ):
                    unregister_activity_uses(resident_id, parent_activity.id)
                stack.append((activity.id, timestamp, is_secondary))
                register_activity_uses(resident_id, activity.id)
            elif row["state"] == "END":
                if not stack or stack[-1][0] != activity.id:
                    raise OutputValidationError(
                        f"row {index} ends activity '{activity.id}' out of nesting order"
                    )
                _, started, started_secondary = stack.pop()
                if started_secondary != is_secondary or timestamp <= started:
                    raise OutputValidationError(
                        f"row {index} has an invalid duration or kind for activity '{activity.id}'"
                    )
                unregister_activity_uses(resident_id, activity.id)
                if is_secondary and stack:
                    parent_activity = scenario.activity_by_id[stack[-1][0]]
                    parent_rule = next(
                        rule
                        for rule in parent_activity.secondary_activities
                        if rule.activity_id == activity.id
                    )
                    if parent_rule.return_to_primary and not parent_rule.preserve_primary_devices:
                        register_activity_uses(resident_id, parent_activity.id)
            else:
                raise OutputValidationError(f"row {index} has invalid activity boundary state")
            continue

        attributes = _device_value(row)
        stored_attributes = {
            key: value for key, value in attributes.items() if key != "controlled_by"
        }
        previous_state = device_states.get(row["device_id"])
        source = row["event_source"]
        if source == "device_use_start":
            uses = device_uses[row["device_id"]]
            if not uses:
                if previous_state is None:
                    raise OutputValidationError(
                        f"row {index} starts use before device '{row['device_id']}' initialization"
                    )
                idle_states[row["device_id"]] = previous_state
            uses[row["resident_id"]] = row["activity_id"]
            expected_state, expected_attributes, winner = _expected_use(
                scenario, row["device_id"], uses
            )
            if len(uses) > 1:
                shared_control_count += 1
            if (
                row["state"] != expected_state
                or stored_attributes != expected_attributes
                or attributes.get("controlled_by") != winner
            ):
                raise OutputValidationError(
                    f"row {index} violates shared-device arbitration for '{row['device_id']}'"
                )
        elif source == "device_use_end":
            uses = device_uses[row["device_id"]]
            uses.pop(row["resident_id"], None)
            if uses:
                expected_state, expected_attributes, winner = _expected_use(
                    scenario, row["device_id"], uses
                )
                if (
                    row["state"] != expected_state
                    or stored_attributes != expected_attributes
                    or attributes.get("controlled_by") != winner
                ):
                    raise OutputValidationError(
                        f"row {index} turns off or misassigns an in-use device '{row['device_id']}'"
                    )
            else:
                restored_state = idle_states.pop(row["device_id"])
                if (row["state"], stored_attributes) != restored_state:
                    raise OutputValidationError(
                        f"row {index} does not restore pre-activity state for '{row['device_id']}'"
                    )

        device_states[row["device_id"]] = (row["state"], stored_attributes)

        if row["device_id"] in connection_by_door:
            if row["state"] == "OPEN":
                if row["device_id"] in open_doors:
                    raise OutputValidationError(f"row {index} reopens an already-open door")
                open_doors[row["device_id"]] = (row["resident_id"], timestamp)
            elif source == "door_passage_close":
                opened = open_doors.pop(row["device_id"], None)
                if opened is None or opened[0] != row["resident_id"]:
                    raise OutputValidationError(f"row {index} closes an unmatched door passage")
                expected_seconds = connection_by_door[row["device_id"]].travel_seconds
                if (timestamp - opened[1]).total_seconds() != expected_seconds:
                    raise OutputValidationError(
                        f"row {index} door passage duration differs from topology"
                    )
                door_passage_count += 1

    assert previous_occupants is not None
    for motion_id, state in motion_states.items():
        if motion_id in zone_motion_ids:
            continue
        expected_motion = "ON" if previous_occupants[motion_room[motion_id]] else "OFF"
        if state != expected_motion:
            raise OutputValidationError(
                f"final motion '{motion_id}' is inconsistent with occupancy"
            )
    if in_transit:
        raise OutputValidationError(f"residents remain in transit: {sorted(in_transit)}")
    active_activities = {key: value for key, value in activity_stacks.items() if value}
    if active_activities:
        raise OutputValidationError(f"activities remain open: {sorted(active_activities)}")
    active_devices = {key: value for key, value in device_uses.items() if value}
    if active_devices:
        raise OutputValidationError(f"device uses remain open: {sorted(active_devices)}")
    if open_doors:
        raise OutputValidationError(f"doors remain open: {sorted(open_doors)}")

    for resident in sorted(scenario.residents, key=lambda item: item.id):
        expected: list[str] = []
        uses_routine_entries = False
        final_event_date = datetime.fromisoformat(rows[-1]["timestamp"]).date()
        observed_calendar_days = max(
            1, (final_event_date - scenario.start_datetime.date()).days + 1
        )
        for day_offset in range(observed_calendar_days):
            simulated_day = scenario.start_datetime.date() + timedelta(days=day_offset)
            weekday = Weekday(simulated_day.strftime("%A").lower())
            routine = resident.weekly_routine[weekday]
            uses_routine_entries = uses_routine_entries or any(
                not isinstance(item, str) for item in routine
            )
            expected.extend(item if isinstance(item, str) else item.activity_id for item in routine)
        observed = main_starts[resident.id]
        follows_routine = (
            _is_subsequence(observed, expected)
            if uses_routine_entries
            else observed == expected[: len(observed)]
        )
        if not follows_routine:
            raise OutputValidationError(
                f"resident '{resident.id}' main activities do not follow the weekly routine"
            )

    return {
        "checks": {
            "activity_nesting": True,
            "device_arbitration": True,
            "device_state_restoration": True,
            "door_pairing_and_duration": True,
            "final_state_closed": True,
            "motion_matches_occupancy": True,
            "occupant_uniqueness": True,
            "room_capacity": True,
            "routine_order": True,
            "topology_movements": True,
        },
        "metrics": {
            "door_passages": door_passage_count,
            "main_activities": sum(len(items) for items in main_starts.values()),
            "max_room_occupancy": max_room_occupancy,
            "movements": movement_count,
            "secondary_activities": secondary_count,
            "shared_control_transitions": shared_control_count,
        },
    }


def _is_subsequence(observed: list[str], expected: list[str]) -> bool:
    cursor = iter(expected)
    return all(any(candidate == activity_id for candidate in cursor) for activity_id in observed)


def validate_generated_events(path: str | Path, scenario: Scenario) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        missing_columns = set(EVENT_COLUMNS) - set(reader.fieldnames or [])
        if missing_columns:
            raise OutputValidationError(f"missing event columns: {sorted(missing_columns)}")
        rows = list(reader)
    if not rows:
        raise OutputValidationError("event output is empty")
    empty = [
        (index + 2, column)
        for index, row in enumerate(rows)
        for column in EVENT_COLUMNS
        if row[column] == ""
    ]
    if empty:
        raise OutputValidationError(f"empty required value at row/column: {empty[0]}")
    timestamps = [datetime.fromisoformat(row["timestamp"]) for row in rows]
    if timestamps != sorted(timestamps):
        raise OutputValidationError("event timestamps are not monotonically nondecreasing")

    rooms = scenario.room_by_id
    activities = scenario.activity_by_id
    for index, row in enumerate(rows, start=2):
        occupants = json.loads(row["occupants"])
        for room_id, resident_ids in occupants.items():
            if room_id not in rooms:
                raise OutputValidationError(
                    f"row {index} contains unknown occupant room '{room_id}'"
                )
            if len(resident_ids) > rooms[room_id].capacity:
                raise OutputValidationError(f"row {index} exceeds capacity of room '{room_id}'")
        if row["event_source"].endswith("activity_start"):
            activity = activities[row["activity_id"]]
            if activity.room_id != row["room_id"]:
                raise OutputValidationError(
                    f"row {index} starts activity '{activity.id}' in invalid room "
                    f"'{row['room_id']}'"
                )

    door_ids = {
        device.id
        for room in scenario.rooms
        for device in room.devices
        if device.type is DeviceType.DOOR_SENSOR
    }
    for door_id in sorted(door_ids):
        states = [row["state"] for row in rows if row["device_id"] == door_id]
        if states and states[0] != "CLOSE":
            raise OutputValidationError(f"door '{door_id}' does not start closed")
        for previous, current in pairwise(states):
            if previous == current or (previous, current) not in {
                ("CLOSE", "OPEN"),
                ("OPEN", "CLOSE"),
            }:
                raise OutputValidationError(
                    f"door '{door_id}' has invalid transition {previous}->{current}"
                )
    semantic = audit_event_semantics(rows, scenario)
    return {
        "rows": len(rows),
        "first_timestamp": rows[0]["timestamp"],
        "last_timestamp": rows[-1]["timestamp"],
        "timestamps_sorted": True,
        "required_values_present": True,
        "door_transitions_valid": True,
        "room_capacities_valid": True,
        "activity_rooms_valid": True,
        "semantic": semantic,
    }
