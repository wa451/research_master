"""Lossless trace records for configured routine, micro, and interruption decisions."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

TRACE_COLUMNS = [
    "timestamp",
    "resident_id",
    "activity_id",
    "activity_label",
    "kind",
    "template_id",
    "step_id",
    "phase",
    "room_id",
    "zone_id",
    "occurrence",
    "reason",
]


@dataclass(frozen=True, slots=True)
class ActivityTraceRecord:
    timestamp: str
    resident_id: str
    activity_id: str
    activity_label: str
    kind: str
    template_id: str
    step_id: str
    phase: str
    room_id: str
    zone_id: str
    occurrence: str
    reason: str


class ActivityTraceCollector:
    def __init__(self, start_datetime: datetime) -> None:
        self.start_datetime = start_datetime
        self.records: list[ActivityTraceRecord] = []

    def record(
        self,
        now_seconds: float,
        *,
        resident_id: str,
        activity_id: str,
        activity_label: str,
        kind: str,
        template_id: str = "-",
        step_id: str = "-",
        phase: str,
        room_id: str,
        zone_id: str | None = None,
        occurrence: int | None = None,
        reason: str,
    ) -> None:
        timestamp = self.start_datetime + timedelta(seconds=now_seconds)
        self.records.append(
            ActivityTraceRecord(
                timestamp=timestamp.isoformat(timespec="microseconds"),
                resident_id=resident_id,
                activity_id=activity_id,
                activity_label=activity_label,
                kind=kind,
                template_id=template_id,
                step_id=step_id,
                phase=phase,
                room_id=room_id,
                zone_id=zone_id or "-",
                occurrence=str(occurrence) if occurrence is not None else "-",
                reason=reason,
            )
        )

    def write_csv(self, path: Path) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=TRACE_COLUMNS)
            writer.writeheader()
            writer.writerows(asdict(record) for record in self.records)
        return len(self.records)
