"""CSV and CASAS-style output converters."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from smart_home_sim.events import EVENT_COLUMNS, EventRecord
from smart_home_sim.schema import Scenario

SIMPLE_STATES = {"ON", "OFF", "OPEN", "CLOSE"}


class CasasPreset(StrEnum):
    LEGACY = "legacy"
    MOTION_DOOR = "motion-door"
    ALL_DEVICES = "all-devices"


CASAS_DEVICE_TYPES = {
    CasasPreset.MOTION_DOOR: {"MotionSensor", "DoorSensor", "ContactSensor"},
    CasasPreset.ALL_DEVICES: {
        "MotionSensor",
        "ContactSensor",
        "DoorSensor",
        "Light",
        "AirConditioner",
        "Television",
        "SmartPlug",
        "CoffeeMachine",
    },
}


def write_event_csv(path: Path, records: Iterable[EventRecord]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    materialized = sorted(records, key=lambda record: (record.timestamp, record.sequence))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=EVENT_COLUMNS)
        writer.writeheader()
        writer.writerows(record.csv_row() for record in materialized)
    return len(materialized)


def write_simple_event_csv(path: Path, records: Iterable[EventRecord]) -> int:
    latest: dict[str, str] = {}
    simple: list[EventRecord] = []
    for record in sorted(records, key=lambda item: (item.timestamp, item.sequence)):
        if record.state not in SIMPLE_STATES or record.device_type == "ActivityBoundary":
            continue
        if latest.get(record.device_id) == record.state:
            continue
        latest[record.device_id] = record.state
        row = record.csv_row()
        row["value"] = record.state
        simple.append(EventRecord(**row, sequence=record.sequence))
    return write_event_csv(path, simple)


def transform_state_csv(events_path: str | Path, output_path: str | Path) -> int:
    rows = _read_events(events_path)
    device_ids = sorted(
        {row["device_id"] for row in rows if row["device_type"] != "ActivityBoundary"}
    )
    fieldnames = ["timestamp", *device_ids, "occupants", "active_activities"]
    states = dict.fromkeys(device_ids, "UNKNOWN")
    active: dict[str, dict[str, str]] = {}
    previous_signature: str | None = None
    snapshots: list[dict[str, str]] = []
    for row in rows:
        if row["device_type"] == "ActivityBoundary":
            if row["state"] == "START":
                active[row["resident_id"]] = {
                    "activity_id": row["activity_id"],
                    "label": row["activity_label"],
                    "room_id": row["room_id"],
                }
            elif row["state"] == "END":
                active.pop(row["resident_id"], None)
        else:
            value = row["value"]
            states[row["device_id"]] = (
                row["state"] if value == row["state"] else f"{row['state']}|{value}"
            )
        activities_json = json.dumps(
            active, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        snapshot = {
            "timestamp": row["timestamp"],
            **states,
            "occupants": row["occupants"],
            "active_activities": activities_json,
        }
        signature = json.dumps(
            {key: value for key, value in snapshot.items() if key != "timestamp"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if signature != previous_signature:
            snapshots.append(snapshot)
            previous_signature = signature
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(snapshots)
    return len(snapshots)


def export_aruba(
    events_path: str | Path,
    output_path: str | Path,
    *,
    preset: CasasPreset | str = CasasPreset.LEGACY,
    include_activity_boundaries: bool | None = None,
) -> int:
    rows = _read_events(events_path)
    selected = CasasPreset(preset)
    if include_activity_boundaries is None:
        include_activity_boundaries = selected is not CasasPreset.LEGACY
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with destination.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            timestamp = datetime.fromisoformat(row["timestamp"]).strftime("%Y-%m-%d %H:%M:%S.%f")
            label = row["activity_label"] if row["activity_label"] != "-" else "Other"
            if selected is CasasPreset.LEGACY:
                stream.write(f"{timestamp} {row['device_id']} {row['state']} {label}\n")
                count += 1
                continue
            if row["device_type"] == "ActivityBoundary":
                if include_activity_boundaries:
                    if row["state"] not in {"START", "END"}:
                        raise ValueError(f"unsupported activity boundary state '{row['state']}'")
                    marker = "begin" if row["state"] == "START" else "end"
                    label = "_".join(label.split())
                    stream.write(
                        f"{timestamp} {row['device_id']} {row['state']} {label} {marker}\n"
                    )
                    count += 1
                continue
            if row["device_type"] not in CASAS_DEVICE_TYPES[selected]:
                continue
            if row["state"] not in SIMPLE_STATES:
                raise ValueError(
                    f"unsupported CASAS state '{row['state']}' for device '{row['device_id']}'"
                )
            stream.write(f"{timestamp} {row['device_id']} {row['state']}\n")
            count += 1
    return count


def write_sensor_map_json(path: Path, scenario: Scenario) -> int:
    mapping = {
        device.id: device.id
        for room in sorted(scenario.rooms, key=lambda item: item.id)
        for device in sorted(room.devices, key=lambda item: item.id)
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return len(mapping)


def write_sensor_map(path: Path, scenario: Scenario) -> int:
    fieldnames = ["sensor_id", "device_type", "room_id", "room_name"]
    rows = [
        {
            "sensor_id": device.id,
            "device_type": device.type.value,
            "room_id": room.id,
            "room_name": room.name,
        }
        for room in sorted(scenario.rooms, key=lambda item: item.id)
        for device in sorted(room.devices, key=lambda item: item.id)
    ]
    rows.extend(
        {
            "sensor_id": f"activity::{resident.id}",
            "device_type": "ActivityBoundary",
            "room_id": "*",
            "room_name": "All rooms",
        }
        for resident in sorted(scenario.residents, key=lambda item: item.id)
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def write_zone_sensor_map(path: Path, scenario: Scenario) -> int:
    fieldnames = [
        "sensor_id",
        "device_type",
        "room_id",
        "room_name",
        "zone_id",
        "zone_name",
    ]
    zone_names = {zone.id: zone.name for room in scenario.rooms for zone in room.zones}
    rows = [
        {
            "sensor_id": device.id,
            "device_type": device.type.value,
            "room_id": room.id,
            "room_name": room.name,
            "zone_id": device.zone_id or "-",
            "zone_name": zone_names.get(device.zone_id or "", "-"),
        }
        for room in sorted(scenario.rooms, key=lambda item: item.id)
        for device in sorted(room.devices, key=lambda item: item.id)
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def write_room_category_map_json(path: Path, scenario: Scenario) -> int:
    """Map fine-grained sensor IDs to stable physical-room categories."""
    mapping = {
        device.id: room.id
        for room in sorted(scenario.rooms, key=lambda item: item.id)
        for device in sorted(room.devices, key=lambda item: item.id)
    }
    path.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return len(mapping)


def _read_events(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    with source.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = set(EVENT_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"events CSV is missing required columns: {sorted(missing)}")
        rows = list(reader)
    indexed_rows = enumerate(rows)
    return [
        pair[1] for pair in sorted(indexed_rows, key=lambda pair: (pair[1]["timestamp"], pair[0]))
    ]
