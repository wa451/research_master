"""Small runtime value objects shared across the engine and device layer."""

from __future__ import annotations

from dataclasses import dataclass

from smart_home_sim.schema import ActivityConfig, DeviceAction, ResidentConfig


@dataclass(frozen=True, slots=True)
class ActivityUse:
    resident: ResidentConfig
    activity: ActivityConfig
    action: DeviceAction
