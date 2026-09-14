"""Extensible smart-device runtime and shared-device arbitration."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, ClassVar

import simpy

from smart_home_sim.events import EventCollector
from smart_home_sim.models import ActivityUse
from smart_home_sim.schema import (
    ActivityConfig,
    DeviceConfig,
    DeviceType,
    ResidentConfig,
    RoomConfig,
    Scenario,
)


class Device:
    """Common interface for sensors and actuators."""

    device_type: ClassVar[DeviceType]
    default_state: ClassVar[str] = "OFF"
    default_attributes: ClassVar[dict[str, Any]] = {}

    def __init__(
        self,
        env: simpy.Environment,
        config: DeviceConfig,
        room: RoomConfig,
        collector: EventCollector,
    ) -> None:
        self.env = env
        self.config = config
        self.room = room
        self.collector = collector
        self.state = config.initial_state or self.default_state
        self.attributes = {**self.default_attributes, **config.initial_attributes}
        self.operation = simpy.Resource(env, capacity=1)
        self.uses: dict[str, ActivityUse] = {}
        self._idle_state: str | None = None
        self._idle_attributes: dict[str, Any] | None = None

    def transition(
        self,
        state: str,
        attributes: dict[str, Any] | None,
        *,
        resident: ResidentConfig | None,
        activity: ActivityConfig | None,
        source: str,
    ) -> bool:
        next_attributes = dict(self.attributes if attributes is None else attributes)
        if self.state == state and self.attributes == next_attributes:
            return False
        self.state = state
        self.attributes = next_attributes
        payload = dict(next_attributes)
        if self.uses:
            winner = self.winning_use()
            payload["controlled_by"] = winner.resident.id
        self.collector.record_device(
            device=self.config,
            room=self.room,
            state=state,
            value=payload or state,
            resident=resident,
            activity=activity,
            source=source,
        )
        return True

    def emit_initial(self) -> None:
        self.collector.record_device(
            device=self.config,
            room=self.room,
            state=self.state,
            value=self.attributes or self.state,
            resident=None,
            activity=None,
            source="initialization",
        )

    def winning_use(self) -> ActivityUse:
        # 優先度が同じ場合はresident IDの辞書順を決定規則とする。
        return min(
            self.uses.values(),
            key=lambda use: (-use.resident.priority, use.resident.id),
        )

    def desired_state(self) -> tuple[str, dict[str, Any], ActivityUse | None]:
        if not self.uses:
            return (
                self._idle_state or self.default_state,
                dict(self._idle_attributes or {}),
                None,
            )
        winner = self.winning_use()
        attributes = dict(winner.action.attributes)
        attributes.update(winner.resident.preferences.get(self.config.id, {}))
        return winner.action.state, attributes, winner


class MotionSensor(Device):
    device_type = DeviceType.MOTION_SENSOR


class ContactSensor(Device):
    device_type = DeviceType.CONTACT_SENSOR
    default_state = "CLOSE"


class DoorSensor(ContactSensor):
    device_type = DeviceType.DOOR_SENSOR


class Light(Device):
    device_type = DeviceType.LIGHT
    default_attributes: ClassVar[dict[str, Any]] = {
        "brightness": 100,
        "color_temperature": 4000,
    }


class AirConditioner(Device):
    device_type = DeviceType.AIR_CONDITIONER
    default_attributes: ClassVar[dict[str, Any]] = {"temperature": 24, "mode": "auto"}


class Television(Device):
    device_type = DeviceType.TELEVISION
    default_attributes: ClassVar[dict[str, Any]] = {"volume": 20}


class SmartPlug(Device):
    device_type = DeviceType.SMART_PLUG


class CoffeeMachine(Device):
    device_type = DeviceType.COFFEE_MACHINE


DEVICE_CLASSES: dict[DeviceType, type[Device]] = {
    DeviceType.MOTION_SENSOR: MotionSensor,
    DeviceType.CONTACT_SENSOR: ContactSensor,
    DeviceType.DOOR_SENSOR: DoorSensor,
    DeviceType.LIGHT: Light,
    DeviceType.AIR_CONDITIONER: AirConditioner,
    DeviceType.TELEVISION: Television,
    DeviceType.SMART_PLUG: SmartPlug,
    DeviceType.COFFEE_MACHINE: CoffeeMachine,
}


class DeviceManager:
    def __init__(
        self, env: simpy.Environment, scenario: Scenario, collector: EventCollector
    ) -> None:
        self.devices: dict[str, Device] = {}
        for room in sorted(scenario.rooms, key=lambda item: item.id):
            for config in sorted(room.devices, key=lambda item: item.id):
                device_class = DEVICE_CLASSES[config.type]
                self.devices[config.id] = device_class(env, config, room, collector)

    def begin_use(self, use: ActivityUse) -> Generator[Any, Any, None]:
        device = self.devices[use.action.device_id]
        with device.operation.request() as request:
            yield request
            if not device.uses:
                device._idle_state = device.state
                device._idle_attributes = dict(device.attributes)
            device.uses[use.resident.id] = use
            state, attributes, winner = device.desired_state()
            device.transition(
                state,
                attributes,
                resident=use.resident,
                activity=winner.activity if winner else use.activity,
                source="device_use_start",
            )

    def end_use(self, use: ActivityUse) -> Generator[Any, Any, None]:
        device = self.devices[use.action.device_id]
        with device.operation.request() as request:
            yield request
            device.uses.pop(use.resident.id, None)
            state, attributes, winner = device.desired_state()
            device.transition(
                state,
                attributes,
                resident=use.resident,
                activity=winner.activity if winner else use.activity,
                source="device_use_end",
            )
            if not device.uses:
                device._idle_state = None
                device._idle_attributes = None
