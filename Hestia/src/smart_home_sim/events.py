"""Stable event records and in-memory collection."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from smart_home_sim.schema import (
    ActivityConfig,
    DeviceConfig,
    ResidentConfig,
    RoomConfig,
)

EVENT_COLUMNS = [
    "timestamp",
    "device_id",
    "device_type",
    "state",
    "value",
    "resident_id",
    "resident_name",
    "occupants",
    "activity_id",
    "activity_label",
    "room_id",
    "room_name",
    "event_source",
    "run_id",
    "seed",
]


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class EventRecord:
    timestamp: str
    device_id: str
    device_type: str
    state: str
    value: str
    resident_id: str
    resident_name: str
    occupants: str
    activity_id: str
    activity_label: str
    room_id: str
    room_name: str
    event_source: str
    run_id: str
    seed: str
    sequence: int

    def csv_row(self) -> dict[str, str]:
        data = asdict(self)
        data.pop("sequence")
        return data


class EventCollector:
    def __init__(
        self,
        *,
        start_datetime: datetime,
        run_id: str,
        seed: int,
        now: Callable[[], float],
        occupants: Callable[[], dict[str, list[str]]],
    ) -> None:
        self.start_datetime = start_datetime
        self.run_id = run_id
        self.seed = seed
        self._now = now
        self._occupants = occupants
        self._records: list[EventRecord] = []

    @property
    def records(self) -> list[EventRecord]:
        return list(self._records)

    def record_device(
        self,
        *,
        device: DeviceConfig,
        room: RoomConfig,
        state: str,
        value: dict[str, Any] | str | int | float | bool,
        resident: ResidentConfig | None,
        activity: ActivityConfig | None,
        source: str,
    ) -> None:
        self._append(
            device_id=device.id,
            device_type=device.type.value,
            state=state,
            value=value,
            resident=resident,
            activity=activity,
            room=room,
            source=source,
        )

    def record_activity(
        self,
        *,
        state: str,
        resident: ResidentConfig,
        activity: ActivityConfig,
        room: RoomConfig,
        source: str,
    ) -> None:
        self._append(
            device_id=f"activity::{resident.id}",
            device_type="ActivityBoundary",
            state=state,
            value=activity.adl_label,
            resident=resident,
            activity=activity,
            room=room,
            source=source,
        )

    def _append(
        self,
        *,
        device_id: str,
        device_type: str,
        state: str,
        value: dict[str, Any] | str | int | float | bool,
        resident: ResidentConfig | None,
        activity: ActivityConfig | None,
        room: RoomConfig,
        source: str,
    ) -> None:
        timestamp = self.start_datetime + timedelta(seconds=self._now())
        value_text = stable_json(value) if isinstance(value, dict) else str(value)
        self._records.append(
            EventRecord(
                timestamp=timestamp.isoformat(timespec="microseconds"),
                device_id=device_id,
                device_type=device_type,
                state=state,
                value=value_text or "-",
                resident_id=resident.id if resident else "-",
                resident_name=resident.name if resident else "-",
                occupants=stable_json(self._occupants()),
                activity_id=activity.id if activity else "-",
                activity_label=activity.adl_label if activity else "-",
                room_id=room.id,
                room_name=room.name,
                event_source=source,
                run_id=self.run_id,
                seed=str(self.seed),
                sequence=len(self._records),
            )
        )
