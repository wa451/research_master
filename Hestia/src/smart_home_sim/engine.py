"""SimPy-based discrete-event simulation engine."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Generator, Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import simpy
from simpy.events import AllOf
from simpy.resources.resource import Request

from smart_home_sim.devices import DeviceManager, MotionSensor
from smart_home_sim.errors import SimulationInvariantError
from smart_home_sim.events import EventCollector
from smart_home_sim.home import HomeGraph
from smart_home_sim.imperfections import apply_sensor_imperfections, write_imperfection_audit
from smart_home_sim.models import ActivityUse
from smart_home_sim.outputs import (
    CasasPreset,
    export_aruba,
    transform_state_csv,
    write_event_csv,
    write_room_category_map_json,
    write_sensor_map,
    write_sensor_map_json,
    write_simple_event_csv,
    write_zone_sensor_map,
)
from smart_home_sim.randomness import RandomManager
from smart_home_sim.schema import (
    ActivityConfig,
    DeviceAction,
    MicroActionStep,
    MotionMode,
    ResidentConfig,
    RoutineEntry,
    Scenario,
    SecondaryActivityRule,
    Weekday,
)
from smart_home_sim.traces import ActivityTraceCollector
from smart_home_sim.validation import validate_generated_events
from smart_home_sim.zones import ZoneGraph


@dataclass(frozen=True, slots=True)
class SimulationResult:
    output_dir: Path
    event_count: int
    simple_event_count: int
    state_count: int
    aruba_count: int
    content_hash: str
    validation: dict[str, Any]


class SimulationEngine:
    def __init__(self, scenario: Scenario, *, days: int, seed: int) -> None:
        if days <= 0:
            raise ValueError("days must be greater than zero")
        self.scenario = scenario
        self.days = days
        self.seed = seed
        self.horizon_seconds = days * 24 * 60 * 60
        self.run_id = f"{scenario.id}-d{days}-s{seed}"
        self.env = simpy.Environment()
        self.random = RandomManager(seed)
        self.home = HomeGraph(scenario)
        self.zones = ZoneGraph(scenario)
        self.occupants: dict[str, set[str]] = {
            room.id: set() for room in sorted(scenario.rooms, key=lambda item: item.id)
        }
        self.zone_occupants: dict[str, set[str]] = {
            zone.id: set()
            for room in sorted(scenario.rooms, key=lambda item: item.id)
            for zone in sorted(room.zones, key=lambda item: item.id)
        }
        self.current_zones: dict[str, str | None] = {}
        for resident in sorted(scenario.residents, key=lambda item: item.id):
            self.occupants[resident.initial_room_id].add(resident.id)
            room = scenario.room_by_id[resident.initial_room_id]
            zone_id = resident.initial_zone_id or room.default_zone_id
            self.current_zones[resident.id] = zone_id
            if zone_id is not None:
                self.zone_occupants[zone_id].add(resident.id)
        self.collector = EventCollector(
            start_datetime=scenario.start_datetime,
            run_id=self.run_id,
            seed=seed,
            now=lambda: float(self.env.now),
            occupants=self.occupant_snapshot,
        )
        self.trace = ActivityTraceCollector(scenario.start_datetime)
        self.devices = DeviceManager(self.env, scenario, self.collector)
        self.room_resources = {
            room.id: simpy.Resource(self.env, capacity=room.capacity)
            for room in sorted(scenario.rooms, key=lambda item: item.id)
        }
        self.door_resources = {
            connection.door_sensor_id: simpy.Resource(self.env, capacity=1)
            for connection in scenario.connections
            if connection.door_sensor_id is not None
        }
        self.locations = {
            resident.id: resident.initial_room_id
            for resident in sorted(scenario.residents, key=lambda item: item.id)
        }
        self.room_requests: dict[str, Request] = {}
        self.secondary_last_occurrence: dict[tuple[str, str, str], float] = {}

    def occupant_snapshot(self) -> dict[str, list[str]]:
        return {room_id: sorted(self.occupants[room_id]) for room_id in sorted(self.occupants)}

    def run(self, output_dir: str | Path) -> SimulationResult:
        self._prepare_initial_devices()
        processes = [
            self.env.process(self._resident_process(resident))
            for resident in sorted(self.scenario.residents, key=lambda item: item.id)
        ]
        self.env.run(until=AllOf(self.env, processes))

        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        true_records = self.collector.records
        events_path = destination / "events.csv"
        event_count = write_event_csv(events_path, true_records)

        observed_result = apply_sensor_imperfections(true_records, self.scenario, self.random)
        output_records = observed_result.records
        transform_events_path = events_path
        extra_manifest: dict[str, Any] = {}
        if self.scenario.sensor_imperfections.enabled:
            write_event_csv(destination / "events_true.csv", true_records)
            transform_events_path = destination / "events_observed.csv"
            observed_count = write_event_csv(transform_events_path, output_records)
            write_simple_event_csv(destination / "events_simple_true.csv", true_records)
            transform_state_csv(events_path, destination / "state_vectors_true.csv")
            export_aruba(events_path, destination / "aruba_true.txt")
            audit_count = write_imperfection_audit(
                destination / "sensor_imperfection_audit.csv", observed_result.audit
            )
            extra_manifest.update(
                {
                    "observed_event_count": observed_count,
                    "sensor_imperfection_audit_count": audit_count,
                    "sensor_imperfection_safe_mode": self.scenario.sensor_imperfections.safe_mode,
                }
            )

        simple_count = write_simple_event_csv(destination / "events_simple.csv", output_records)
        state_count = transform_state_csv(transform_events_path, destination / "state_vectors.csv")
        aruba_count = export_aruba(transform_events_path, destination / "aruba.txt")
        casas_motion_door_count = export_aruba(
            transform_events_path,
            destination / "casas_motion_door.txt",
            preset=CasasPreset.MOTION_DOOR,
        )
        casas_all_devices_count = export_aruba(
            transform_events_path,
            destination / "casas_all_devices.txt",
            preset=CasasPreset.ALL_DEVICES,
        )
        write_sensor_map(destination / "sensor_map.csv", self.scenario)
        write_sensor_map_json(destination / "casas_sensor_map.json", self.scenario)
        if self.scenario.zone_by_id:
            write_zone_sensor_map(destination / "zone_sensor_map.csv", self.scenario)
            write_room_category_map_json(destination / "casas_sensor_map_room.json", self.scenario)
        if self.trace.records:
            extra_manifest["activity_trace_count"] = self.trace.write_csv(
                destination / "activity_trace.csv"
            )
        validation = validate_generated_events(events_path, self.scenario)
        manifest = {
            "run_id": self.run_id,
            "scenario_id": self.scenario.id,
            "days": self.days,
            "seed": self.seed,
            "event_count": event_count,
            "simple_event_count": simple_count,
            "state_count": state_count,
            "aruba_count": aruba_count,
            "casas_motion_door_count": casas_motion_door_count,
            "casas_all_devices_count": casas_all_devices_count,
            "validation": validation,
            **extra_manifest,
        }
        (destination / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        content_hash = hash_output_directory(destination)
        return SimulationResult(
            output_dir=destination,
            event_count=event_count,
            simple_event_count=simple_count,
            state_count=state_count,
            aruba_count=aruba_count,
            content_hash=content_hash,
            validation=validation,
        )

    def _prepare_initial_devices(self) -> None:
        for device in self.devices.devices.values():
            if isinstance(device, MotionSensor):
                room = device.room
                if room.motion_mode is MotionMode.ZONE:
                    assert device.config.zone_id is not None
                    device.state = "ON" if self.zone_occupants[device.config.zone_id] else "OFF"
                else:
                    device.state = "ON" if self.occupants[room.id] else "OFF"
            device.emit_initial()

    def _resident_process(self, resident: ResidentConfig) -> Generator[Any, Any, None]:
        initial_request = self.room_resources[resident.initial_room_id].request()
        yield initial_request
        self.room_requests[resident.id] = initial_request
        for day_offset in range(self.days):
            day_start = day_offset * 24 * 60 * 60
            if self.env.now < day_start:
                yield self.env.timeout(day_start - self.env.now)
            if self.env.now >= self.horizon_seconds:
                break
            simulated_day = self.scenario.start_datetime + timedelta(days=day_offset)
            weekday = Weekday(simulated_day.strftime("%A").lower())
            for item in resident.weekly_routine[weekday]:
                if self.env.now >= self.horizon_seconds:
                    break
                if isinstance(item, str):
                    activity = self.scenario.activity_by_id[item]
                else:
                    included = self.random.chance(item.inclusion_probability)
                    activity = self.scenario.activity_by_id[item.activity_id]
                    if not included:
                        self._trace_routine(resident, activity, "SKIPPED", "inclusion_probability")
                        continue
                    yield from self._wait_for_routine_start(day_start, item)
                    if self.env.now >= self.horizon_seconds:
                        break
                    self._trace_routine(resident, activity, "SELECTED", "routine_entry")
                duration = self._activity_duration(activity, resident)
                yield from self._perform_activity(
                    resident,
                    activity,
                    duration_minutes=duration,
                    allow_secondary=True,
                    boundary_prefix="main",
                )
            next_day = min((day_offset + 1) * 24 * 60 * 60, self.horizon_seconds)
            if self.env.now < next_day:
                yield self.env.timeout(next_day - self.env.now)
        if self.env.now < self.horizon_seconds:
            yield self.env.timeout(self.horizon_seconds - self.env.now)

    def _wait_for_routine_start(
        self, day_start: float, item: RoutineEntry
    ) -> Generator[Any, Any, None]:
        if item.scheduled_start_minute is not None:
            target = (
                day_start
                + item.scheduled_start_minute * 60.0
                + self.random.sample(item.start_jitter_minutes) * 60.0
            )
            target = max(day_start, target)
            if self.env.now < target:
                yield self.env.timeout(min(target, self.horizon_seconds) - self.env.now)
        gap_seconds = max(0.0, self.random.sample(item.gap_before_minutes) * 60.0)
        if gap_seconds and self.env.now < self.horizon_seconds:
            yield self.env.timeout(min(gap_seconds, self.horizon_seconds - float(self.env.now)))

    def _activity_duration(self, activity: ActivityConfig, resident: ResidentConfig) -> float:
        if activity.duration_distribution is None:
            duration = self.random.varied_duration(
                activity.base_duration_minutes, activity.variation_fraction
            )
        else:
            duration = self.random.sample(activity.duration_distribution)
        if activity.min_duration_minutes is not None:
            duration = max(activity.min_duration_minutes, duration)
        if activity.max_duration_minutes is not None:
            duration = min(activity.max_duration_minutes, duration)
        return max(0.0, duration * resident.duration_multiplier)

    def _perform_activity(
        self,
        resident: ResidentConfig,
        activity: ActivityConfig,
        *,
        duration_minutes: float,
        allow_secondary: bool,
        boundary_prefix: str,
    ) -> Generator[Any, Any, None]:
        yield from self._move(resident, activity.room_id, activity, target_zone_id=activity.zone_id)
        room = self.scenario.room_by_id[activity.room_id]
        self.collector.record_activity(
            state="START",
            resident=resident,
            activity=activity,
            room=room,
            source=f"{boundary_prefix}_activity_start",
        )
        uses = self._uses_for(resident, activity)
        yield from self._begin_uses(uses)

        enhanced = bool(activity.micro_action_templates) or any(
            not self._legacy_secondary_rule(rule) for rule in activity.secondary_activities
        )
        uses_active = True
        if not enhanced:
            yield from self._perform_legacy_body(
                resident,
                activity,
                uses,
                duration_minutes=duration_minutes,
                allow_secondary=allow_secondary,
            )
        else:
            uses_active = yield from self._perform_enhanced_body(
                resident,
                activity,
                uses,
                duration_minutes=duration_minutes,
                allow_secondary=allow_secondary,
            )

        if uses_active:
            yield from self._end_uses(uses)
        final_room = self.scenario.room_by_id[self.locations[resident.id]]
        self.collector.record_activity(
            state="END",
            resident=resident,
            activity=activity,
            room=final_room,
            source=f"{boundary_prefix}_activity_end",
        )

    def _perform_legacy_body(
        self,
        resident: ResidentConfig,
        activity: ActivityConfig,
        uses: list[ActivityUse],
        *,
        duration_minutes: float,
        allow_secondary: bool,
    ) -> Generator[Any, Any, None]:
        remaining = max(0.0, duration_minutes)
        if allow_secondary and activity.secondary_activities:
            block_minutes = min(rule.block_minutes for rule in activity.secondary_activities)
            while remaining > 1e-9 and self.env.now < self.horizon_seconds:
                block = min(block_minutes, remaining)
                elapsed = yield from self._wait_minutes(block)
                remaining = max(0.0, remaining - elapsed)
                if remaining <= 1e-9 or self.env.now >= self.horizon_seconds:
                    break
                rule = self.random.choose_secondary(
                    activity.secondary_activities, resident.secondary_activity_factor
                )
                if rule is None:
                    continue
                secondary = self.scenario.activity_by_id[rule.activity_id]
                secondary_duration = min(
                    remaining,
                    self._activity_duration(secondary, resident),
                )
                if not rule.preserve_primary_devices:
                    yield from self._end_uses(uses)
                yield from self._perform_activity(
                    resident,
                    secondary,
                    duration_minutes=secondary_duration,
                    allow_secondary=False,
                    boundary_prefix="secondary",
                )
                yield from self._move(
                    resident,
                    activity.room_id,
                    activity,
                    target_zone_id=activity.zone_id,
                )
                if not rule.preserve_primary_devices and self.env.now < self.horizon_seconds:
                    yield from self._begin_uses(uses)
                remaining = max(0.0, remaining - secondary_duration)
        else:
            yield from self._wait_minutes(remaining)

    def _perform_enhanced_body(
        self,
        resident: ResidentConfig,
        activity: ActivityConfig,
        uses: list[ActivityUse],
        *,
        duration_minutes: float,
        allow_secondary: bool,
    ) -> Generator[Any, Any, bool]:
        deadline = min(
            float(self.horizon_seconds), float(self.env.now) + max(0.0, duration_minutes) * 60.0
        )
        if activity.micro_action_templates:
            yield from self._perform_micro_actions(resident, activity, deadline)
        uses_active = True
        if allow_secondary and activity.secondary_activities:
            uses_active = yield from self._perform_enhanced_secondary(
                resident, activity, uses, deadline
            )
        if self.env.now < deadline:
            yield self.env.timeout(deadline - self.env.now)
        return uses_active

    def _perform_micro_actions(
        self, resident: ResidentConfig, activity: ActivityConfig, deadline: float
    ) -> Generator[Any, Any, None]:
        templates = sorted(activity.micro_action_templates, key=lambda item: item.id)
        template = self.random.weighted_choice(templates, [item.weight for item in templates])
        self.trace.record(
            float(self.env.now),
            resident_id=resident.id,
            activity_id=activity.id,
            activity_label=activity.adl_label,
            kind="micro_template",
            template_id=template.id,
            phase="SELECTED",
            room_id=self.locations[resident.id],
            zone_id=self.current_zones[resident.id],
            reason="weighted_template_selection",
        )
        for step in template.steps:
            repeat_count = self.random.sample_count(step.repeat_count)
            for occurrence in range(1, repeat_count + 1):
                if not self.random.chance(step.optional_probability):
                    self._trace_micro(
                        resident,
                        activity,
                        template.id,
                        step,
                        occurrence,
                        "SKIPPED",
                        "optional_step",
                    )
                    continue
                dwell_minutes = max(0.0, self.random.sample(step.dwell_minutes))
                target_room = step.room_id or activity.room_id
                target_zone = self._target_zone(target_room, step.zone_id)
                current_room = self.locations[resident.id]
                current_zone = self.current_zones[resident.id]
                outbound = self._travel_seconds_between(
                    current_room, current_zone, target_room, target_zone
                )
                return_seconds = self._travel_seconds_between(
                    target_room,
                    target_zone,
                    activity.room_id,
                    self._target_zone(activity.room_id, activity.zone_id),
                )
                available = deadline - float(self.env.now) - outbound - return_seconds
                dwell_seconds = min(dwell_minutes * 60.0, max(0.0, available))
                if dwell_seconds <= 1e-9:
                    self._trace_micro(
                        resident,
                        activity,
                        template.id,
                        step,
                        occurrence,
                        "SKIPPED",
                        "insufficient_activity_time",
                    )
                    continue
                yield from self._move(
                    resident,
                    target_room,
                    activity,
                    target_zone_id=target_zone,
                )
                self._trace_micro(
                    resident,
                    activity,
                    template.id,
                    step,
                    occurrence,
                    "START",
                    step.reason,
                )
                step_uses = self._uses_for_actions(resident, activity, step.device_actions)
                yield from self._begin_uses(step_uses)
                yield self.env.timeout(dwell_seconds)
                yield from self._end_uses(step_uses)
                self._trace_micro(
                    resident,
                    activity,
                    template.id,
                    step,
                    occurrence,
                    "END",
                    step.reason,
                )
        target_zone = self._target_zone(activity.room_id, activity.zone_id)
        required = self._travel_seconds_between(
            self.locations[resident.id],
            self.current_zones[resident.id],
            activity.room_id,
            target_zone,
        )
        if float(self.env.now) + required <= deadline + 1e-9:
            yield from self._move(
                resident,
                activity.room_id,
                activity,
                target_zone_id=target_zone,
            )

    def _perform_enhanced_secondary(
        self,
        resident: ResidentConfig,
        activity: ActivityConfig,
        uses: list[ActivityUse],
        deadline: float,
    ) -> Generator[Any, Any, bool]:
        block_minutes = min(rule.block_minutes for rule in activity.secondary_activities)
        occurrences: dict[str, int] = {}
        uses_active = True
        while self.env.now < deadline - 1e-9:
            block_seconds = min(block_minutes * 60.0, deadline - float(self.env.now))
            if block_seconds > 0:
                yield self.env.timeout(block_seconds)
            if self.env.now >= deadline - 1e-9:
                break
            eligible = [
                rule
                for rule in activity.secondary_activities
                if self._secondary_is_eligible(resident, activity, rule, occurrences)
            ]
            if not eligible:
                continue
            rule = self.random.choose_secondary(eligible, resident.secondary_activity_factor)
            if rule is None:
                continue
            secondary = self.scenario.activity_by_id[rule.activity_id]
            target_zone = self._target_zone(secondary.room_id, secondary.zone_id)
            parent_zone = self._target_zone(activity.room_id, activity.zone_id)
            outbound = self._travel_seconds_between(
                self.locations[resident.id],
                self.current_zones[resident.id],
                secondary.room_id,
                target_zone,
            )
            return_seconds = (
                self._travel_seconds_between(
                    secondary.room_id,
                    target_zone,
                    activity.room_id,
                    parent_zone,
                )
                if rule.return_to_primary
                else 0.0
            )
            available_minutes = max(
                0.0,
                (deadline - float(self.env.now) - outbound - return_seconds) / 60.0,
            )
            secondary_duration = min(
                available_minutes, self._activity_duration(secondary, resident)
            )
            if secondary_duration <= 1e-9:
                self._trace_secondary(
                    resident,
                    activity,
                    rule,
                    occurrences.get(rule.activity_id, 0) + 1,
                    "SKIPPED",
                    "insufficient_activity_time",
                )
                continue
            occurrence = occurrences.get(rule.activity_id, 0) + 1
            occurrences[rule.activity_id] = occurrence
            self.secondary_last_occurrence[(resident.id, activity.id, rule.activity_id)] = float(
                self.env.now
            )
            self._trace_secondary(resident, activity, rule, occurrence, "START", rule.reason)
            if not rule.preserve_primary_devices and uses_active:
                yield from self._end_uses(uses)
                uses_active = False
            yield from self._perform_activity(
                resident,
                secondary,
                duration_minutes=secondary_duration,
                allow_secondary=False,
                boundary_prefix="secondary",
            )
            if rule.return_to_primary:
                yield from self._move(
                    resident,
                    activity.room_id,
                    activity,
                    target_zone_id=parent_zone,
                )
                if not rule.preserve_primary_devices and self.env.now < deadline:
                    yield from self._begin_uses(uses)
                    uses_active = True
            self._trace_secondary(resident, activity, rule, occurrence, "END", rule.reason)
            if not rule.return_to_primary:
                break
        return uses_active

    def _secondary_is_eligible(
        self,
        resident: ResidentConfig,
        activity: ActivityConfig,
        rule: SecondaryActivityRule,
        occurrences: dict[str, int],
    ) -> bool:
        if (
            rule.max_occurrences is not None
            and occurrences.get(rule.activity_id, 0) >= rule.max_occurrences
        ):
            return False
        key = (resident.id, activity.id, rule.activity_id)
        last = self.secondary_last_occurrence.get(key)
        if last is not None and float(self.env.now) - last < rule.cooldown_minutes * 60.0:
            return False
        if rule.allowed_start_hour is None or rule.allowed_end_hour is None:
            return True
        timestamp = self.scenario.start_datetime + timedelta(seconds=float(self.env.now))
        hour = timestamp.hour + timestamp.minute / 60.0 + timestamp.second / 3600.0
        if rule.allowed_start_hour < rule.allowed_end_hour:
            return rule.allowed_start_hour <= hour < rule.allowed_end_hour
        return hour >= rule.allowed_start_hour or hour < rule.allowed_end_hour

    @staticmethod
    def _legacy_secondary_rule(rule: SecondaryActivityRule) -> bool:
        return (
            rule.cooldown_minutes == 0
            and rule.return_to_primary
            and rule.allowed_start_hour is None
            and rule.allowed_end_hour is None
            and rule.max_occurrences is None
            and rule.reason == "configured_secondary_activity"
        )

    def _wait_minutes(self, minutes: float) -> Generator[Any, Any, float]:
        available_seconds = max(0.0, self.horizon_seconds - float(self.env.now))
        seconds = min(minutes * 60.0, available_seconds)
        if seconds > 0:
            yield self.env.timeout(seconds)
        return seconds / 60.0

    def _uses_for(self, resident: ResidentConfig, activity: ActivityConfig) -> list[ActivityUse]:
        return self._uses_for_actions(resident, activity, activity.device_actions)

    @staticmethod
    def _uses_for_actions(
        resident: ResidentConfig,
        activity: ActivityConfig,
        actions: Sequence[DeviceAction],
    ) -> list[ActivityUse]:
        return [
            ActivityUse(resident=resident, activity=activity, action=action)
            for action in sorted(actions, key=lambda item: item.device_id)
        ]

    def _begin_uses(self, uses: list[ActivityUse]) -> Generator[Any, Any, None]:
        for use in uses:
            yield from self.devices.begin_use(use)

    def _end_uses(self, uses: list[ActivityUse]) -> Generator[Any, Any, None]:
        for use in uses:
            yield from self.devices.end_use(use)

    def _move(
        self,
        resident: ResidentConfig,
        target_room_id: str,
        activity: ActivityConfig,
        *,
        target_zone_id: str | None = None,
    ) -> Generator[Any, Any, None]:
        current = self.locations[resident.id]
        destination_zone = self._target_zone(target_room_id, target_zone_id)
        if current == target_room_id:
            yield from self._move_zone(resident, destination_zone, activity)
            return
        path = self.home.shortest_path(current, target_room_id)
        for next_room in path[1:]:
            connection = self.home.connection(current, next_room)
            door_id = connection.door_sensor_id
            if door_id is None:
                yield from self._traverse_edge(
                    resident, activity, current, connection.travel_seconds
                )
            else:
                with self.door_resources[door_id].request() as door_request:
                    yield door_request
                    door = self.devices.devices[door_id]
                    door.transition(
                        "OPEN",
                        {},
                        resident=resident,
                        activity=activity,
                        source="door_passage_open",
                    )
                    yield from self._traverse_edge(
                        resident, activity, current, connection.travel_seconds
                    )
                    door.transition(
                        "CLOSE",
                        {},
                        resident=resident,
                        activity=activity,
                        source="door_passage_close",
                    )
            # 退出後に到着先を待ち、容量1の部屋間でも循環待ちを作らない。
            next_request = self.room_resources[next_room].request()
            yield next_request
            self.room_requests[resident.id] = next_request
            self.locations[resident.id] = next_room
            arrival_zone = (
                destination_zone
                if next_room == target_room_id
                else self._target_zone(next_room, None)
            )
            self._enter_room(resident, next_room, arrival_zone, activity)
            current = next_room

    def _move_zone(
        self,
        resident: ResidentConfig,
        target_zone_id: str | None,
        activity: ActivityConfig,
    ) -> Generator[Any, Any, None]:
        current_zone = self.current_zones[resident.id]
        if current_zone is None or target_zone_id is None or current_zone == target_zone_id:
            return
        room_id = self.locations[resident.id]
        for next_zone in self.zones.shortest_path(room_id, current_zone, target_zone_id)[1:]:
            occupants = self.zone_occupants[current_zone]
            occupants.remove(resident.id)
            if not occupants:
                for motion in self._motion_sensors(room_id, current_zone):
                    motion.transition(
                        "OFF",
                        {},
                        resident=resident,
                        activity=activity,
                        source=f"zone_exit::{current_zone}",
                    )
            connection = self.zones.connection(current_zone, next_zone)
            if connection.travel_seconds:
                yield self.env.timeout(connection.travel_seconds)
            next_occupants = self.zone_occupants[next_zone]
            was_empty = not next_occupants
            next_occupants.add(resident.id)
            self.current_zones[resident.id] = next_zone
            if was_empty:
                for motion in self._motion_sensors(room_id, next_zone):
                    motion.transition(
                        "ON",
                        {},
                        resident=resident,
                        activity=activity,
                        source=f"zone_entry::{next_zone}",
                    )
            current_zone = next_zone

    def _traverse_edge(
        self,
        resident: ResidentConfig,
        activity: ActivityConfig,
        current: str,
        travel_seconds: float,
    ) -> Generator[Any, Any, None]:
        self._leave_room(resident, current, activity)
        previous_request = self.room_requests[resident.id]
        self.room_resources[current].release(previous_request)
        if travel_seconds:
            yield self.env.timeout(travel_seconds)

    def _leave_room(self, resident: ResidentConfig, room_id: str, activity: ActivityConfig) -> None:
        room = self.scenario.room_by_id[room_id]
        if room.motion_mode is MotionMode.ZONE:
            zone_id = self.current_zones[resident.id]
            assert zone_id is not None
            zone_occupants = self.zone_occupants[zone_id]
            zone_occupants.remove(resident.id)
            if not zone_occupants:
                for motion in self._motion_sensors(room_id, zone_id):
                    motion.transition(
                        "OFF",
                        {},
                        resident=resident,
                        activity=activity,
                        source=f"zone_exit::{zone_id}",
                    )
            self.current_zones[resident.id] = None
        occupants = self.occupants[room_id]
        occupants.remove(resident.id)
        if room.motion_mode is MotionMode.ROOM and not occupants:
            for motion in self._motion_sensors(room_id):
                motion.transition(
                    "OFF",
                    {},
                    resident=resident,
                    activity=activity,
                    source="room_exit",
                )

    def _enter_room(
        self,
        resident: ResidentConfig,
        room_id: str,
        zone_id: str | None,
        activity: ActivityConfig,
    ) -> None:
        occupants = self.occupants[room_id]
        room = self.scenario.room_by_id[room_id]
        if len(occupants) >= room.capacity:
            raise SimulationInvariantError(f"room '{room_id}' capacity exceeded")
        was_empty = not occupants
        occupants.add(resident.id)
        if room.motion_mode is MotionMode.ZONE:
            assert zone_id is not None
            zone_occupants = self.zone_occupants[zone_id]
            zone_was_empty = not zone_occupants
            zone_occupants.add(resident.id)
            self.current_zones[resident.id] = zone_id
            if zone_was_empty:
                for motion in self._motion_sensors(room_id, zone_id):
                    motion.transition(
                        "ON",
                        {},
                        resident=resident,
                        activity=activity,
                        source=f"zone_entry::{zone_id}",
                    )
        else:
            self.current_zones[resident.id] = zone_id
            if was_empty:
                for motion in self._motion_sensors(room_id):
                    motion.transition(
                        "ON",
                        {},
                        resident=resident,
                        activity=activity,
                        source="room_entry",
                    )

    def _motion_sensors(self, room_id: str, zone_id: str | None = None) -> list[MotionSensor]:
        room = self.scenario.room_by_id[room_id]
        return sorted(
            [
                device
                for device in self.devices.devices.values()
                if isinstance(device, MotionSensor)
                and device.room.id == room_id
                and (
                    room.motion_mode is MotionMode.ROOM
                    or (zone_id is not None and device.config.zone_id == zone_id)
                )
            ],
            key=lambda item: item.config.id,
        )

    def _target_zone(self, room_id: str, requested_zone_id: str | None) -> str | None:
        return ZoneGraph.destination_zone(self.scenario.room_by_id[room_id], requested_zone_id)

    def _travel_seconds_between(
        self,
        source_room: str,
        source_zone: str | None,
        target_room: str,
        target_zone: str | None,
    ) -> float:
        if source_room != target_room:
            return self.home.travel_seconds(source_room, target_room)
        if source_zone is None or target_zone is None or source_zone == target_zone:
            return 0.0
        return self.zones.travel_seconds(source_room, source_zone, target_zone)

    def _trace_routine(
        self,
        resident: ResidentConfig,
        activity: ActivityConfig,
        phase: str,
        reason: str,
    ) -> None:
        self.trace.record(
            float(self.env.now),
            resident_id=resident.id,
            activity_id=activity.id,
            activity_label=activity.adl_label,
            kind="routine",
            phase=phase,
            room_id=self.locations[resident.id],
            zone_id=self.current_zones[resident.id],
            reason=reason,
        )

    def _trace_micro(
        self,
        resident: ResidentConfig,
        activity: ActivityConfig,
        template_id: str,
        step: MicroActionStep,
        occurrence: int,
        phase: str,
        reason: str,
    ) -> None:
        self.trace.record(
            float(self.env.now),
            resident_id=resident.id,
            activity_id=activity.id,
            activity_label=activity.adl_label,
            kind="micro_action",
            template_id=template_id,
            step_id=step.id,
            phase=phase,
            room_id=self.locations[resident.id],
            zone_id=self.current_zones[resident.id],
            occurrence=occurrence,
            reason=reason,
        )

    def _trace_secondary(
        self,
        resident: ResidentConfig,
        activity: ActivityConfig,
        rule: SecondaryActivityRule,
        occurrence: int,
        phase: str,
        reason: str,
    ) -> None:
        self.trace.record(
            float(self.env.now),
            resident_id=resident.id,
            activity_id=activity.id,
            activity_label=activity.adl_label,
            kind="secondary_activity",
            step_id=rule.activity_id,
            phase=phase,
            room_id=self.locations[resident.id],
            zone_id=self.current_zones[resident.id],
            occurrence=occurrence,
            reason=reason,
        )


def hash_output_directory(path: str | Path) -> str:
    root = Path(path)
    digest = hashlib.sha256()
    for file_path in sorted(item for item in root.iterdir() if item.is_file()):
        digest.update(file_path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
