"""Construct shared behavioral motifs in three independently specified homes."""

from __future__ import annotations

from smart_home_sim.experiments.plan import Condition, ExperimentPlan
from smart_home_sim.schema import (
    ActivityConfig,
    ConnectionConfig,
    DeviceAction,
    DeviceConfig,
    DeviceType,
    DistributionConfig,
    DistributionKind,
    MicroActionStep,
    MicroActionTemplate,
    ResidentConfig,
    RoomConfig,
    RoutineEntry,
    RoutineItem,
    Scenario,
    Weekday,
    fixed_distribution,
)

TARGET_ACTIVITIES = ("meal", "relax", "work")


def build_scenario(condition: Condition, plan: ExperimentPlan) -> Scenario:
    room_ids = ["bathroom", "bedroom", "kitchen", "living", "outside"]
    if condition.house != "compact":
        room_ids.append("hallway")
    if condition.house == "branched":
        room_ids.append("study")
    rooms: list[RoomConfig] = []
    for room_id in sorted(room_ids):
        devices = []
        if room_id != "outside":
            devices = [
                DeviceConfig(
                    id=f"M_{room_id}", name=f"{room_id} motion", type=DeviceType.MOTION_SENSOR
                ),
                DeviceConfig(id=f"L_{room_id}", name=f"{room_id} light", type=DeviceType.LIGHT),
            ]
        # livingのTVとPCは同じ部屋にあっても別センサーとして残す。
        for device_id, kind, location in (
            ("coffee", DeviceType.COFFEE_MACHINE, "kitchen"),
            ("tv", DeviceType.TELEVISION, "living"),
            ("pc", DeviceType.SMART_PLUG, "study" if condition.house == "branched" else "living"),
        ):
            if room_id == location:
                devices.append(DeviceConfig(id=device_id, name=f"{room_id} {device_id}", type=kind))
        rooms.append(
            RoomConfig(
                id=room_id,
                name=room_id.title(),
                capacity=2,
                is_outside=room_id == "outside",
                devices=devices,
            )
        )
    hub = "living" if condition.house == "compact" else "hallway"
    connections = [
        ConnectionConfig(source=hub, target=room_id, travel_seconds=10)
        for room_id in sorted(room_ids)
        if room_id != hub
    ]
    if condition.house == "branched":
        connections = [item for item in connections if item.target != "study"]
        connections.append(ConnectionConfig(source="living", target="study", travel_seconds=15))
    for connection in connections:
        door_id = f"D_{connection.target}"
        connection.door_sensor_id = door_id
        room = next(room for room in rooms if room.id == connection.source)
        room.devices.append(
            DeviceConfig(id=door_id, name=f"{connection.target} door", type=DeviceType.DOOR_SENSOR)
        )
    for room in rooms:
        room.devices.sort(key=lambda device: device.id)
    variation = {"fixed": 0.0, "small": 0.1, "large": 0.3}[condition.variability]
    jitter = {"fixed": 0, "small": 10, "large": 45}[condition.variability]

    def dwell(minutes: float) -> DistributionConfig:
        return (
            fixed_distribution(minutes)
            if not variation
            else DistributionConfig(
                kind=DistributionKind.UNIFORM,
                low=minutes * (1 - variation),
                high=minutes * (1 + variation),
            )
        )

    activities = [
        ActivityConfig(
            id="sleep",
            name="Sleep",
            room_id="bedroom",
            base_duration_minutes=300,
            adl_label="Sleep",
        ),
        ActivityConfig(
            id="hygiene",
            name="Hygiene",
            room_id="bathroom",
            base_duration_minutes=10,
            variation_fraction=variation,
            device_actions=[DeviceAction(device_id="L_bathroom")],
            adl_label="Hygiene",
        ),
        ActivityConfig(
            id="outing",
            name="Outing",
            room_id="outside",
            base_duration_minutes=180,
            variation_fraction=variation,
            adl_label="Outing",
        ),
    ]
    for activity_id, room_id, device_id, label in (
        ("meal", "kitchen", "coffee", "Meal"),
        ("relax", "living", "tv", "Relax"),
        ("work", "study" if condition.house == "branched" else "living", "pc", "Work"),
    ):
        activities.append(
            ActivityConfig(
                id=activity_id,
                name=label,
                room_id=room_id,
                adl_label=label,
                base_duration_minutes=45,
                variation_fraction=variation,
                device_actions=[
                    DeviceAction(device_id=device_id),
                    DeviceAction(device_id=f"L_{room_id}"),
                ],
                micro_action_templates=[
                    MicroActionTemplate(
                        id=f"{activity_id}_motif",
                        steps=[
                            MicroActionStep(
                                id="prepare",
                                room_id=room_id,
                                dwell_minutes=dwell(3),
                            ),
                            MicroActionStep(
                                id="use",
                                room_id="living" if activity_id == "meal" else "kitchen",
                                dwell_minutes=dwell(12),
                            ),
                            MicroActionStep(
                                id="finish",
                                room_id=room_id,
                                dwell_minutes=dwell(3),
                            ),
                        ],
                    )
                ],
            )
        )
    if plan.targets is not None:
        resident_ids = {f"resident_{index + 1}" for index in range(condition.residents)}
        activity_ids = {activity.id for activity in activities}
        for target in plan.targets:
            if target.resident_id not in resident_ids:
                raise ValueError(
                    f"target '{target.id}' references resident '{target.resident_id}' "
                    f"outside condition '{condition.id}'"
                )
            if target.activity_id not in activity_ids:
                raise ValueError(
                    f"target '{target.id}' references unknown activity '{target.activity_id}'"
                )

    residents = []
    for index in range(condition.residents):
        offset = (120 if condition.lifestyle == "late" else 0) + index * 20
        schedule: list[tuple[str, float]] = [
            ("sleep", 0),
            ("hygiene", 330 + offset),
            ("meal", 390 + offset),
            ("work", 510 + offset),
            ("meal", 750 + offset),
            ("relax", 840 + offset),
            ("outing", 900 + offset),
            ("meal", 1140 + offset),
            ("relax", 1230 + offset),
        ]
        if condition.lifestyle == "home":
            schedule = [
                ("work" if activity == "outing" else activity, minute)
                for activity, minute in schedule
            ]
        if plan.targets is None:
            # 頻度は行動の実行回数で変える。観測イベントの欠落ではない。
            if condition.frequency == "low":
                schedule = [
                    (activity, minute)
                    for activity, minute in schedule
                    if minute not in (750 + offset, 840 + offset)
                ]
            elif condition.frequency == "high":
                schedule.extend([("meal", 450 + offset), ("relax", 690 + offset)])
        else:
            # 明示targetは従来target枠と同じactivityの既定枠を置換する。
            replaced_activity_ids = set(TARGET_ACTIVITIES) | {
                target.activity_id for target in plan.targets
            }
            schedule = [
                (activity, minute)
                for activity, minute in schedule
                if activity not in replaced_activity_ids
            ]
            schedule.extend(
                (target.activity_id, minute)
                for target in plan.targets
                if target.resident_id == f"resident_{index + 1}"
                for minute in target.scheduled_start_minutes
            )
        routine: list[RoutineItem] = [
            RoutineEntry(
                activity_id=activity,
                scheduled_start_minute=minute,
                start_jitter_minutes=(
                    DistributionConfig(kind=DistributionKind.UNIFORM, low=-jitter, high=jitter)
                    if jitter and minute
                    else fixed_distribution()
                ),
            )
            for activity, minute in sorted(schedule, key=lambda item: item[1])
        ]
        residents.append(
            ResidentConfig(
                id=f"resident_{index + 1}",
                name=f"Resident {index + 1}",
                initial_room_id="bedroom",
                priority=index,
                weekly_routine={day: routine for day in Weekday},
            )
        )
    return Scenario(
        id=condition.id,
        name=condition.id,
        start_datetime=plan.start_datetime,
        rooms=rooms,
        connections=connections,
        activities=sorted(activities, key=lambda x: x.id),
        residents=residents,
    )
