"""Opt-in, reproducible separation of true events from observed sensor events."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from smart_home_sim.events import EventRecord
from smart_home_sim.randomness import RandomManager
from smart_home_sim.schema import Scenario, SensorFaultProfile

PASSIVE_SENSOR_TYPES = {"MotionSensor", "ContactSensor", "DoorSensor"}
OPPOSITE_STATE = {"ON": "OFF", "OFF": "ON", "OPEN": "CLOSE", "CLOSE": "OPEN"}
AUDIT_COLUMNS = [
    "true_timestamp",
    "observed_timestamp",
    "device_id",
    "action",
    "reason",
    "true_state",
    "observed_state",
]


@dataclass(frozen=True, slots=True)
class ImperfectionAuditRecord:
    true_timestamp: str
    observed_timestamp: str
    device_id: str
    action: str
    reason: str
    true_state: str
    observed_state: str


@dataclass(frozen=True, slots=True)
class ImperfectionResult:
    records: list[EventRecord]
    audit: list[ImperfectionAuditRecord]


def apply_sensor_imperfections(
    records: list[EventRecord], scenario: Scenario, random: RandomManager
) -> ImperfectionResult:
    """Derive an observed stream without changing the simulator's ground truth."""
    config = scenario.sensor_imperfections
    if not config.enabled:
        return ImperfectionResult(records=list(records), audit=[])

    candidates: list[EventRecord] = []
    audit: list[ImperfectionAuditRecord] = []
    start = scenario.start_datetime
    next_sequence = 0
    for record in sorted(records, key=lambda item: (item.timestamp, item.sequence)):
        if (
            record.device_type not in PASSIVE_SENSOR_TYPES
            or record.event_source == "initialization"
        ):
            candidates.append(replace(record, sequence=next_sequence))
            next_sequence += 1
            continue
        profile = config.profiles.get(record.device_id, config.default_profile)
        true_time = datetime.fromisoformat(record.timestamp)
        if _in_outage(true_time, start, profile):
            audit.append(_audit(record, "-", "dropped", "configured_outage", "-"))
            continue
        if random.chance(profile.drop_probability):
            audit.append(_audit(record, "-", "dropped", "probabilistic_drop", "-"))
            continue

        observed_state = record.state
        if random.chance(profile.flip_probability):
            observed_state = OPPOSITE_STATE[observed_state]
            audit.append(
                _audit(record, record.timestamp, "state_flipped", "configured_flip", observed_state)
            )
        offset_seconds = random.sample(profile.detection_delay_seconds)
        if record.state == "OFF":
            offset_seconds += random.sample(profile.off_delay_seconds)
        offset_seconds += random.sample(profile.clock_skew_seconds)
        observed_time = max(start, true_time + timedelta(seconds=offset_seconds))
        observed = replace(
            record,
            timestamp=observed_time.isoformat(timespec="microseconds"),
            state=observed_state,
            value=_replace_simple_value(record.value, record.state, observed_state),
            event_source=(
                record.event_source
                if offset_seconds == 0 and observed_state == record.state
                else f"observed::{record.event_source}"
            ),
            sequence=next_sequence,
        )
        candidates.append(observed)
        next_sequence += 1
        if offset_seconds != 0:
            audit.append(
                _audit(
                    record,
                    observed.timestamp,
                    "timestamp_shifted",
                    "detection_off_delay_or_clock_skew",
                    observed_state,
                )
            )

        if random.chance(profile.duplicate_probability):
            duplicate_time = observed_time + timedelta(microseconds=1)
            duplicate = replace(
                observed,
                timestamp=duplicate_time.isoformat(timespec="microseconds"),
                event_source="observed::duplicate",
                sequence=next_sequence,
            )
            candidates.append(duplicate)
            next_sequence += 1
            audit.append(
                _audit(
                    record,
                    duplicate.timestamp,
                    "duplicated",
                    "configured_duplicate",
                    observed_state,
                )
            )

        if random.chance(profile.false_trigger_probability):
            false_state = OPPOSITE_STATE[observed_state]
            false_time = observed_time + timedelta(microseconds=2)
            restore_time = false_time + timedelta(
                seconds=max(0.000001, random.sample(profile.false_trigger_duration_seconds))
            )
            candidates.extend(
                [
                    replace(
                        observed,
                        timestamp=false_time.isoformat(timespec="microseconds"),
                        state=false_state,
                        value=_replace_simple_value(observed.value, observed_state, false_state),
                        event_source="observed::false_trigger",
                        sequence=next_sequence,
                    ),
                    replace(
                        observed,
                        timestamp=restore_time.isoformat(timespec="microseconds"),
                        event_source="observed::false_trigger_restore",
                        sequence=next_sequence + 1,
                    ),
                ]
            )
            next_sequence += 2
            audit.append(
                _audit(
                    record,
                    false_time.isoformat(timespec="microseconds"),
                    "false_triggered",
                    "configured_false_trigger",
                    false_state,
                )
            )

    ordered = sorted(candidates, key=lambda item: (item.timestamp, item.sequence))
    if config.safe_mode:
        ordered, suppressed = _make_transition_safe(ordered)
        audit.extend(suppressed)
    resequenced = [replace(record, sequence=index) for index, record in enumerate(ordered)]
    return ImperfectionResult(records=resequenced, audit=audit)


def write_imperfection_audit(path: Path, records: list[ImperfectionAuditRecord]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=AUDIT_COLUMNS)
        writer.writeheader()
        writer.writerows(asdict(record) for record in records)
    return len(records)


def _in_outage(timestamp: datetime, start: datetime, profile: SensorFaultProfile) -> bool:
    minute = (timestamp - start).total_seconds() / 60.0
    return any(
        window.start_minute <= minute < window.end_minute for window in profile.outage_windows
    )


def _make_transition_safe(
    records: list[EventRecord],
) -> tuple[list[EventRecord], list[ImperfectionAuditRecord]]:
    latest: dict[str, str] = {}
    accepted: list[EventRecord] = []
    audit: list[ImperfectionAuditRecord] = []
    for record in records:
        if record.device_type not in PASSIVE_SENSOR_TYPES:
            accepted.append(record)
            continue
        if latest.get(record.device_id) == record.state:
            audit.append(
                _audit(
                    record,
                    "-",
                    "suppressed",
                    "safe_mode_duplicate_state",
                    "-",
                )
            )
            continue
        latest[record.device_id] = record.state
        accepted.append(record)
    return accepted, audit


def _replace_simple_value(value: str, old_state: str, new_state: str) -> str:
    return new_state if value == old_state else value


def _audit(
    record: EventRecord,
    observed_timestamp: str,
    action: str,
    reason: str,
    observed_state: str,
) -> ImperfectionAuditRecord:
    return ImperfectionAuditRecord(
        true_timestamp=record.timestamp,
        observed_timestamp=observed_timestamp,
        device_id=record.device_id,
        action=action,
        reason=reason,
        true_state=record.state,
        observed_state=observed_state,
    )
