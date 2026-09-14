"""Validated, immutable-ish configuration models for simulation scenarios."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Protocol, TypeAlias, TypeVar

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field, model_validator

JsonScalar: TypeAlias = str | int | float | bool

BINARY_STATES = frozenset({"ON", "OFF"})
CONTACT_STATES = frozenset({"OPEN", "CLOSE"})


class DeviceType(StrEnum):
    MOTION_SENSOR = "MotionSensor"
    CONTACT_SENSOR = "ContactSensor"
    DOOR_SENSOR = "DoorSensor"
    LIGHT = "Light"
    AIR_CONDITIONER = "AirConditioner"
    TELEVISION = "Television"
    SMART_PLUG = "SmartPlug"
    COFFEE_MACHINE = "CoffeeMachine"


class Weekday(StrEnum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class DistributionKind(StrEnum):
    FIXED = "fixed"
    UNIFORM = "uniform"
    NORMAL = "normal"
    LOGNORMAL = "lognormal"
    WEIGHTED = "weighted"


class MotionMode(StrEnum):
    ROOM = "room"
    ZONE = "zone"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EditorRoomPosition(StrictModel):
    """Canvas coordinates used by the optional browser-based scenario editor."""

    x: Annotated[float, Field(ge=0, le=100)]
    y: Annotated[float, Field(ge=0, le=100)]
    width: Annotated[float, Field(gt=0, le=100)]
    height: Annotated[float, Field(gt=0, le=100)]


class EditorDevicePosition(StrictModel):
    """A device position expressed as a percentage within its room."""

    x: Annotated[float, Field(ge=0, le=100)]
    y: Annotated[float, Field(ge=0, le=100)]


class EditorLayout(StrictModel):
    """Optional presentation-only layout persisted by Hestia Studio.

    The simulation engine deliberately ignores this model. Keeping it at the
    scenario root avoids coupling visual placement to the simulation topology.
    """

    room_positions: dict[str, EditorRoomPosition] = Field(default_factory=dict)
    device_positions: dict[str, EditorDevicePosition] = Field(default_factory=dict)


class WeightedNumber(StrictModel):
    value: float
    weight: Annotated[float, Field(gt=0)] = 1.0


class DistributionConfig(StrictModel):
    kind: DistributionKind = DistributionKind.FIXED
    value: float = 0.0
    low: float | None = None
    high: float | None = None
    mean: float | None = None
    standard_deviation: Annotated[float | None, Field(ge=0)] = None
    mu: float | None = None
    sigma: Annotated[float | None, Field(ge=0)] = None
    choices: list[WeightedNumber] = Field(default_factory=list)
    clip_min: float | None = None
    clip_max: float | None = None

    @model_validator(mode="after")
    def parameters_match_kind(self) -> DistributionConfig:
        if (
            self.clip_min is not None
            and self.clip_max is not None
            and self.clip_min > self.clip_max
        ):
            raise ValueError("distribution clip_min must not exceed clip_max")
        if self.kind is DistributionKind.UNIFORM:
            if self.low is None or self.high is None or self.low > self.high:
                raise ValueError("uniform distribution requires low <= high")
        elif self.kind is DistributionKind.NORMAL:
            if self.mean is None or self.standard_deviation is None:
                raise ValueError("normal distribution requires mean and standard_deviation")
        elif self.kind is DistributionKind.LOGNORMAL:
            if self.mu is None or self.sigma is None:
                raise ValueError("lognormal distribution requires mu and sigma")
        elif self.kind is DistributionKind.WEIGHTED and not self.choices:
            raise ValueError("weighted distribution requires at least one choice")
        return self


def fixed_distribution(value: float = 0.0) -> DistributionConfig:
    return DistributionConfig(kind=DistributionKind.FIXED, value=value)


class DeviceConfig(StrictModel):
    id: str = Field(min_length=1)
    type: DeviceType
    name: str = Field(min_length=1)
    initial_state: str | None = None
    initial_attributes: dict[str, JsonScalar] = Field(default_factory=dict)
    zone_id: str | None = None

    @model_validator(mode="after")
    def initial_state_matches_device_type(self) -> DeviceConfig:
        if self.initial_state is None:
            return self
        allowed = (
            CONTACT_STATES
            if self.type in {DeviceType.CONTACT_SENSOR, DeviceType.DOOR_SENSOR}
            else BINARY_STATES
        )
        if self.initial_state not in allowed:
            raise ValueError(
                f"device '{self.id}' has unsupported state '{self.initial_state}' "
                f"for {self.type.value}"
            )
        return self


class ZoneConfig(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)


class ZoneConnectionConfig(StrictModel):
    source: str
    target: str
    travel_seconds: Annotated[float, Field(ge=0)]


class RoomConfig(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    capacity: Annotated[int, Field(ge=1)]
    is_outside: bool = False
    devices: list[DeviceConfig] = Field(default_factory=list)
    motion_mode: MotionMode = MotionMode.ROOM
    default_zone_id: str | None = None
    zones: list[ZoneConfig] = Field(default_factory=list)
    zone_connections: list[ZoneConnectionConfig] = Field(default_factory=list)


class ConnectionConfig(StrictModel):
    source: str
    target: str
    travel_seconds: Annotated[float, Field(ge=0)]
    door_sensor_id: str | None = None


class DeviceAction(StrictModel):
    device_id: str
    state: str = "ON"
    attributes: dict[str, JsonScalar] = Field(default_factory=dict)


class MicroActionStep(StrictModel):
    id: str = Field(min_length=1)
    room_id: str | None = None
    zone_id: str | None = None
    dwell_minutes: DistributionConfig = Field(default_factory=fixed_distribution)
    optional_probability: Annotated[float, Field(ge=0, le=1)] = 1.0
    repeat_count: DistributionConfig = Field(default_factory=lambda: fixed_distribution(1.0))
    device_actions: list[DeviceAction] = Field(default_factory=list)
    reason: str = "configured_micro_action"


class MicroActionTemplate(StrictModel):
    id: str = Field(min_length=1)
    weight: Annotated[float, Field(gt=0)] = 1.0
    steps: list[MicroActionStep] = Field(min_length=1)


class SecondaryActivityRule(StrictModel):
    activity_id: str
    probability: Annotated[float, Field(ge=0, le=1)]
    block_minutes: Annotated[float, Field(gt=0)] = 10.0
    preserve_primary_devices: bool = False
    cooldown_minutes: Annotated[float, Field(ge=0)] = 0.0
    return_to_primary: bool = True
    allowed_start_hour: Annotated[float, Field(ge=0, lt=24)] | None = None
    allowed_end_hour: Annotated[float, Field(gt=0, le=24)] | None = None
    max_occurrences: Annotated[int, Field(ge=1)] | None = None
    reason: str = "configured_secondary_activity"

    @model_validator(mode="after")
    def time_window_is_complete(self) -> SecondaryActivityRule:
        if (self.allowed_start_hour is None) != (self.allowed_end_hour is None):
            raise ValueError("secondary time window requires both start and end hour")
        if not self.return_to_primary and self.preserve_primary_devices:
            raise ValueError("non-returning secondary activity cannot preserve primary devices")
        return self


class ActivityConfig(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    room_id: str
    base_duration_minutes: Annotated[float, Field(gt=0)]
    variation_fraction: Annotated[float, Field(ge=0, le=1)] = 0.0
    duration_distribution: DistributionConfig | None = None
    min_duration_minutes: Annotated[float | None, Field(gt=0)] = None
    max_duration_minutes: Annotated[float | None, Field(gt=0)] = None
    zone_id: str | None = None
    device_actions: list[DeviceAction] = Field(default_factory=list)
    secondary_activities: list[SecondaryActivityRule] = Field(default_factory=list)
    micro_action_templates: list[MicroActionTemplate] = Field(default_factory=list)
    adl_label: str = Field(min_length=1)

    @model_validator(mode="after")
    def probabilities_do_not_exceed_one(self) -> ActivityConfig:
        total = sum(rule.probability for rule in self.secondary_activities)
        if total > 1.0 + 1e-12:
            raise ValueError(
                f"activity '{self.id}' secondary activity probabilities sum to {total:.6g}; "
                "the sum must not exceed 1"
            )
        if (
            self.min_duration_minutes is not None
            and self.max_duration_minutes is not None
            and self.min_duration_minutes > self.max_duration_minutes
        ):
            raise ValueError(
                f"activity '{self.id}' min_duration_minutes must not exceed max_duration_minutes"
            )
        _unique_by_id(self.micro_action_templates, f"activity '{self.id}' micro template")
        for template in self.micro_action_templates:
            _unique_by_id(template.steps, f"micro template '{template.id}' step")
        return self


class RoutineEntry(StrictModel):
    activity_id: str
    scheduled_start_minute: Annotated[float | None, Field(ge=0, lt=1440)] = None
    start_jitter_minutes: DistributionConfig = Field(default_factory=fixed_distribution)
    gap_before_minutes: DistributionConfig = Field(default_factory=fixed_distribution)
    inclusion_probability: Annotated[float, Field(ge=0, le=1)] = 1.0


RoutineItem: TypeAlias = str | RoutineEntry


class ResidentConfig(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    initial_room_id: str
    initial_zone_id: str | None = None
    priority: int = 0
    weekly_routine: dict[Weekday, list[RoutineItem]]
    preferences: dict[str, dict[str, JsonScalar]] = Field(default_factory=dict)
    duration_multiplier: Annotated[float, Field(gt=0)] = 1.0
    secondary_activity_factor: Annotated[float, Field(ge=0, le=1)] = 1.0

    @model_validator(mode="after")
    def all_weekdays_are_present(self) -> ResidentConfig:
        missing = sorted(day.value for day in Weekday if day not in self.weekly_routine)
        if missing:
            raise ValueError(f"resident '{self.id}' is missing weekly routines for: {missing}")
        return self


class SensorOutageWindow(StrictModel):
    start_minute: Annotated[float, Field(ge=0)]
    end_minute: Annotated[float, Field(gt=0)]

    @model_validator(mode="after")
    def end_follows_start(self) -> SensorOutageWindow:
        if self.end_minute <= self.start_minute:
            raise ValueError("sensor outage end_minute must exceed start_minute")
        return self


class SensorFaultProfile(StrictModel):
    drop_probability: Annotated[float, Field(ge=0, le=1)] = 0.0
    duplicate_probability: Annotated[float, Field(ge=0, le=1)] = 0.0
    flip_probability: Annotated[float, Field(ge=0, le=1)] = 0.0
    false_trigger_probability: Annotated[float, Field(ge=0, le=1)] = 0.0
    detection_delay_seconds: DistributionConfig = Field(default_factory=fixed_distribution)
    off_delay_seconds: DistributionConfig = Field(default_factory=fixed_distribution)
    clock_skew_seconds: DistributionConfig = Field(default_factory=fixed_distribution)
    false_trigger_duration_seconds: DistributionConfig = Field(
        default_factory=lambda: fixed_distribution(1.0)
    )
    outage_windows: list[SensorOutageWindow] = Field(default_factory=list)


class SensorImperfectionConfig(StrictModel):
    enabled: bool = False
    safe_mode: bool = True
    default_profile: SensorFaultProfile = Field(default_factory=SensorFaultProfile)
    profiles: dict[str, SensorFaultProfile] = Field(default_factory=dict)


class Scenario(StrictModel):
    schema_version: Literal[1] = 1
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    start_datetime: datetime
    rooms: list[RoomConfig]
    connections: list[ConnectionConfig]
    activities: list[ActivityConfig]
    residents: list[ResidentConfig]
    editor_layout: EditorLayout | None = None
    sensor_imperfections: SensorImperfectionConfig = Field(default_factory=SensorImperfectionConfig)

    @model_validator(mode="after")
    def validate_references_and_topology(self) -> Scenario:
        if self.start_datetime.tzinfo is None or self.start_datetime.utcoffset() is None:
            raise ValueError("start_datetime must include an explicit UTC offset")

        room_by_id = _unique_by_id(self.rooms, "room")
        activity_by_id = _unique_by_id(self.activities, "activity")
        resident_by_id = _unique_by_id(self.residents, "resident")
        del resident_by_id

        device_by_id: dict[str, tuple[DeviceConfig, str]] = {}
        zone_by_id: dict[str, str] = {}
        for room in self.rooms:
            room_zone_ids = _unique_by_id(room.zones, f"zone in room '{room.id}'")
            for zone_id in room_zone_ids:
                if zone_id in zone_by_id:
                    raise ValueError(f"duplicate zone id '{zone_id}'")
                zone_by_id[zone_id] = room.id
            if room.zones:
                if room.default_zone_id not in room_zone_ids:
                    raise ValueError(
                        f"room '{room.id}' with zones requires a valid default_zone_id"
                    )
                zone_graph = nx.Graph()
                zone_graph.add_nodes_from(sorted(room_zone_ids))
                seen_zone_edges: set[tuple[str, str]] = set()
                for connection in room.zone_connections:
                    if (
                        connection.source not in room_zone_ids
                        or connection.target not in room_zone_ids
                    ):
                        raise ValueError(
                            f"room '{room.id}' zone connection references unknown zone"
                        )
                    if connection.source == connection.target:
                        raise ValueError(f"room '{room.id}' zone connection cannot be a self-loop")
                    zone_edge = (
                        (connection.source, connection.target)
                        if connection.source <= connection.target
                        else (connection.target, connection.source)
                    )
                    if zone_edge in seen_zone_edges:
                        raise ValueError(
                            f"duplicate zone connection '{zone_edge[0]}'-'{zone_edge[1]}'"
                        )
                    seen_zone_edges.add(zone_edge)
                    zone_graph.add_edge(connection.source, connection.target)
                if len(room_zone_ids) > 1 and not nx.is_connected(zone_graph):
                    unreachable_zones = sorted(
                        set(room_zone_ids)
                        - nx.node_connected_component(zone_graph, min(room_zone_ids))
                    )
                    raise ValueError(f"room '{room.id}' has unreachable zones: {unreachable_zones}")
            elif room.default_zone_id is not None or room.zone_connections:
                raise ValueError(f"room '{room.id}' cannot configure zone metadata without zones")
            for device in room.devices:
                if device.id in device_by_id:
                    first_room = device_by_id[device.id][1]
                    raise ValueError(
                        f"duplicate device id '{device.id}' in rooms '{first_room}' and '{room.id}'"
                    )
                device_by_id[device.id] = (device, room.id)
                if device.zone_id is not None and zone_by_id.get(device.zone_id) != room.id:
                    raise ValueError(
                        f"device '{device.id}' references a zone outside room '{room.id}'"
                    )
                if (
                    room.motion_mode is MotionMode.ZONE
                    and device.type is DeviceType.MOTION_SENSOR
                    and device.zone_id is None
                ):
                    raise ValueError(
                        f"zone-mode room '{room.id}' motion sensor '{device.id}' requires zone_id"
                    )
            if room.motion_mode is MotionMode.ZONE and not room.zones:
                raise ValueError(f"zone-mode room '{room.id}' requires zones")

        if self.editor_layout is not None:
            unknown_layout_rooms = sorted(set(self.editor_layout.room_positions) - set(room_by_id))
            if unknown_layout_rooms:
                raise ValueError(f"editor layout references unknown rooms: {unknown_layout_rooms}")
            unknown_layout_devices = sorted(
                set(self.editor_layout.device_positions) - set(device_by_id)
            )
            if unknown_layout_devices:
                raise ValueError(
                    f"editor layout references unknown devices: {unknown_layout_devices}"
                )

        outside_rooms = [room.id for room in self.rooms if room.is_outside]
        if len(outside_rooms) != 1:
            raise ValueError(
                f"exactly one room must have is_outside=true; found {len(outside_rooms)}"
            )

        graph = nx.Graph()
        graph.add_nodes_from(sorted(room_by_id))
        seen_edges: set[tuple[str, str]] = set()
        used_door_ids: set[str] = set()
        for index, connection in enumerate(self.connections):
            for endpoint_name, endpoint in (
                ("source", connection.source),
                ("target", connection.target),
            ):
                if endpoint not in room_by_id:
                    raise ValueError(
                        f"connections[{index}].{endpoint_name} references unknown room '{endpoint}'"
                    )
            if connection.source == connection.target:
                raise ValueError(f"connections[{index}] cannot connect room to itself")
            edge = (
                (connection.source, connection.target)
                if connection.source <= connection.target
                else (connection.target, connection.source)
            )
            if edge in seen_edges:
                raise ValueError(f"duplicate connection between '{edge[0]}' and '{edge[1]}'")
            seen_edges.add(edge)
            if connection.door_sensor_id is not None:
                found = device_by_id.get(connection.door_sensor_id)
                if found is None:
                    raise ValueError(
                        f"connections[{index}].door_sensor_id references unknown device "
                        f"'{connection.door_sensor_id}'"
                    )
                if found[0].type is not DeviceType.DOOR_SENSOR:
                    raise ValueError(
                        f"connection door '{connection.door_sensor_id}' must be a DoorSensor"
                    )
                if found[0].initial_state not in {None, "CLOSE"}:
                    raise ValueError(
                        f"connected door '{connection.door_sensor_id}' must start closed"
                    )
                if connection.door_sensor_id in used_door_ids:
                    raise ValueError(
                        f"door sensor '{connection.door_sensor_id}' is used by multiple connections"
                    )
                used_door_ids.add(connection.door_sensor_id)
            graph.add_edge(connection.source, connection.target)
        if room_by_id and not nx.is_connected(graph):
            unreachable = sorted(
                set(room_by_id) - nx.node_connected_component(graph, min(room_by_id))
            )
            raise ValueError(f"home graph contains unreachable rooms: {unreachable}")

        for activity in self.activities:
            if activity.room_id not in room_by_id:
                raise ValueError(
                    f"activity '{activity.id}' references unknown room '{activity.room_id}'"
                )
            if (
                activity.zone_id is not None
                and zone_by_id.get(activity.zone_id) != activity.room_id
            ):
                raise ValueError(f"activity '{activity.id}' references a zone outside its room")
            action_ids: set[str] = set()
            for action in activity.device_actions:
                if action.device_id in action_ids:
                    raise ValueError(
                        f"activity '{activity.id}' contains duplicate action for "
                        f"'{action.device_id}'"
                    )
                action_ids.add(action.device_id)
                found = device_by_id.get(action.device_id)
                if found is None:
                    raise ValueError(
                        f"activity '{activity.id}' references unknown device '{action.device_id}'"
                    )
                if found[1] != activity.room_id:
                    raise ValueError(
                        f"activity '{activity.id}' uses device '{action.device_id}' from room "
                        f"'{found[1]}', not activity room '{activity.room_id}'"
                    )
                if found[0].type in {
                    DeviceType.MOTION_SENSOR,
                    DeviceType.CONTACT_SENSOR,
                    DeviceType.DOOR_SENSOR,
                }:
                    raise ValueError(
                        f"activity '{activity.id}' cannot directly operate passive sensor "
                        f"'{action.device_id}'"
                    )
                allowed_states = (
                    CONTACT_STATES
                    if found[0].type in {DeviceType.CONTACT_SENSOR, DeviceType.DOOR_SENSOR}
                    else BINARY_STATES
                )
                if action.state not in allowed_states:
                    raise ValueError(
                        f"activity '{activity.id}' uses unsupported state '{action.state}' "
                        f"for device '{action.device_id}' ({found[0].type.value})"
                    )
            for rule in activity.secondary_activities:
                secondary = activity_by_id.get(rule.activity_id)
                if secondary is None:
                    raise ValueError(
                        f"activity '{activity.id}' references unknown secondary activity "
                        f"'{rule.activity_id}'"
                    )
                if secondary.id == activity.id:
                    raise ValueError(f"activity '{activity.id}' cannot contain itself as secondary")
                if secondary.base_duration_minutes >= activity.base_duration_minutes:
                    raise ValueError(
                        f"secondary activity '{secondary.id}' must be shorter than '{activity.id}'"
                    )
                if rule.preserve_primary_devices:
                    overlapping = sorted(
                        {action.device_id for action in activity.device_actions}
                        & {action.device_id for action in secondary.device_actions}
                    )
                    if overlapping:
                        raise ValueError(
                            f"activity '{activity.id}' cannot preserve shared primary devices "
                            f"also used by secondary '{secondary.id}': {overlapping}"
                        )
            primary_action_ids = {action.device_id for action in activity.device_actions}
            micro_actions_by_device: dict[str, tuple[str, str]] = {}
            for template in activity.micro_action_templates:
                for step in template.steps:
                    target_room_id = step.room_id or activity.room_id
                    if target_room_id not in room_by_id:
                        raise ValueError(
                            f"micro step '{step.id}' references unknown room '{target_room_id}'"
                        )
                    if step.zone_id is not None and zone_by_id.get(step.zone_id) != target_room_id:
                        raise ValueError(
                            f"micro step '{step.id}' references a zone outside target room"
                        )
                    step_action_ids: set[str] = set()
                    for action in step.device_actions:
                        if action.device_id in step_action_ids:
                            raise ValueError(
                                f"micro step '{step.id}' contains duplicate device action"
                            )
                        step_action_ids.add(action.device_id)
                        if action.device_id in primary_action_ids:
                            raise ValueError(
                                f"micro step '{step.id}' reuses primary device '{action.device_id}'"
                            )
                        found = device_by_id.get(action.device_id)
                        if found is None or found[1] != target_room_id:
                            raise ValueError(
                                f"micro step '{step.id}' device '{action.device_id}' is not "
                                "in its target room"
                            )
                        if found[0].type in {
                            DeviceType.MOTION_SENSOR,
                            DeviceType.DOOR_SENSOR,
                        }:
                            raise ValueError(
                                f"micro step '{step.id}' cannot operate passive sensor"
                            )
                        allowed = (
                            CONTACT_STATES
                            if found[0].type is DeviceType.CONTACT_SENSOR
                            else BINARY_STATES
                        )
                        if action.state not in allowed:
                            raise ValueError(
                                f"micro step '{step.id}' uses unsupported device state"
                            )
                        signature = (
                            action.state,
                            stable_config_json(action.attributes),
                        )
                        previous_signature = micro_actions_by_device.setdefault(
                            action.device_id, signature
                        )
                        if previous_signature != signature:
                            raise ValueError(
                                f"activity '{activity.id}' gives micro device "
                                f"'{action.device_id}' conflicting actions"
                            )

        initial_counts = dict.fromkeys(room_by_id, 0)
        for resident in self.residents:
            if resident.initial_room_id not in room_by_id:
                raise ValueError(
                    f"resident '{resident.id}' references unknown initial room "
                    f"'{resident.initial_room_id}'"
                )
            initial_room = room_by_id[resident.initial_room_id]
            expected_initial_zone = resident.initial_zone_id or initial_room.default_zone_id
            if initial_room.motion_mode is MotionMode.ZONE and expected_initial_zone is None:
                raise ValueError(
                    f"resident '{resident.id}' requires an initial zone in zone-mode room"
                )
            if (
                expected_initial_zone is not None
                and zone_by_id.get(expected_initial_zone) != resident.initial_room_id
            ):
                raise ValueError(
                    f"resident '{resident.id}' initial_zone_id is outside initial room"
                )
            initial_counts[resident.initial_room_id] += 1
            for day, routine in resident.weekly_routine.items():
                for position, item in enumerate(routine):
                    activity_id = item if isinstance(item, str) else item.activity_id
                    if activity_id not in activity_by_id:
                        raise ValueError(
                            f"resident '{resident.id}' routine {day.value}[{position}] references "
                            f"unknown activity '{activity_id}'"
                        )
            for device_id in resident.preferences:
                if device_id not in device_by_id:
                    raise ValueError(
                        f"resident '{resident.id}' preference references unknown device "
                        f"'{device_id}'"
                    )
        unknown_profiles = sorted(set(self.sensor_imperfections.profiles) - set(device_by_id))
        if unknown_profiles:
            raise ValueError(
                f"sensor imperfection profiles reference unknown devices: {unknown_profiles}"
            )
        invalid_profiles = sorted(
            device_id
            for device_id in self.sensor_imperfections.profiles
            if device_by_id[device_id][0].type
            not in {DeviceType.MOTION_SENSOR, DeviceType.CONTACT_SENSOR, DeviceType.DOOR_SENSOR}
        )
        if invalid_profiles:
            raise ValueError(
                f"sensor imperfection profiles require passive sensors: {invalid_profiles}"
            )
        exceeded = [
            room_id
            for room_id, count in initial_counts.items()
            if count > room_by_id[room_id].capacity
        ]
        if exceeded:
            raise ValueError(f"initial resident positions exceed room capacity: {sorted(exceeded)}")
        return self

    @property
    def room_by_id(self) -> dict[str, RoomConfig]:
        return {room.id: room for room in self.rooms}

    @property
    def activity_by_id(self) -> dict[str, ActivityConfig]:
        return {activity.id: activity for activity in self.activities}

    @property
    def resident_by_id(self) -> dict[str, ResidentConfig]:
        return {resident.id: resident for resident in self.residents}

    @property
    def device_by_id(self) -> dict[str, tuple[DeviceConfig, RoomConfig]]:
        return {device.id: (device, room) for room in self.rooms for device in room.devices}

    @property
    def zone_by_id(self) -> dict[str, tuple[ZoneConfig, RoomConfig]]:
        return {zone.id: (zone, room) for room in self.rooms for zone in room.zones}


class HasId(Protocol):
    id: str


HasIdT = TypeVar("HasIdT", bound=HasId)


def _unique_by_id(items: Sequence[HasIdT], label: str) -> dict[str, HasIdT]:
    result: dict[str, HasIdT] = {}
    for item in items:
        item_id = item.id
        if item_id in result:
            raise ValueError(f"duplicate {label} id '{item_id}'")
        result[item_id] = item
    return result


def stable_config_json(value: dict[str, JsonScalar]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
