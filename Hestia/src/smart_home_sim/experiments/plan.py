"""Explicit experimental factors; no sensor-fault condition is accepted."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from smart_home_sim.schema import StrictModel

House = Literal["compact", "corridor", "branched"]
Lifestyle = Literal["early", "late", "home"]
Frequency = Literal["low", "daily", "high"]
Variability = Literal["fixed", "small", "large"]
TimeBand = Literal["Midnight", "Morning", "Daytime", "Night"]


def time_band_for_minute(minute: float) -> TimeBand:
    hour = minute / 60
    return (
        "Midnight" if hour < 6 else "Morning" if hour < 10 else "Daytime" if hour < 18 else "Night"
    )


class TargetActivity(StrictModel):
    """A repeated evaluation target scheduled through the normal routine machinery."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    activity_id: str = Field(min_length=1)
    resident_id: str = Field(min_length=1)
    time_band: TimeBand
    scheduled_start_minutes: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_schedule(self) -> TargetActivity:
        if len(self.scheduled_start_minutes) != len(set(self.scheduled_start_minutes)):
            raise ValueError(f"target '{self.id}' scheduled_start_minutes must be unique")
        for minute in self.scheduled_start_minutes:
            if not 0 <= minute < 1440:
                raise ValueError(f"target '{self.id}' scheduled start must be within one day")
            if time_band_for_minute(minute) != self.time_band:
                raise ValueError(
                    f"target '{self.id}' scheduled start {minute} is outside {self.time_band}"
                )
        return self


class Condition(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    house: House
    residents: Literal[1, 2] = 1
    lifestyle: Lifestyle = "early"
    frequency: Frequency = "daily"
    variability: Variability = "small"


def default_conditions() -> list[Condition]:
    conditions: list[Condition] = []
    for house in ("compact", "corridor", "branched"):
        base = Condition(id=f"{house}_base", house=house)
        conditions.append(base)
        for suffix, factor, value in (
            ("two", "residents", 2),
            ("late", "lifestyle", "late"),
            ("home", "lifestyle", "home"),
            ("low", "frequency", "low"),
            ("high", "frequency", "high"),
            ("fixed", "variability", "fixed"),
            ("variable", "variability", "large"),
        ):
            conditions.append(
                Condition.model_validate(
                    {**base.model_dump(), "id": f"{house}_{suffix}", factor: value}
                )
            )
    return conditions


class ExperimentPlan(StrictModel):
    schema_version: Literal[1] = 1
    observation_noise: Literal[False] = False
    start_datetime: datetime = datetime.fromisoformat("2025-01-06T00:00:00+09:00")
    train_days: int = Field(default=7, ge=1)
    test_days: int = Field(default=7, ge=1)
    seeds: list[int] = Field(default_factory=lambda: [11, 22, 33], min_length=1)
    conditions: list[Condition] = Field(default_factory=default_conditions, min_length=1)
    n_states: int = Field(default=15, ge=2)
    hamming_threshold: int = Field(default=0, ge=0)
    smoothing_window_sec: int = Field(default=0, ge=0)
    min_train_support: int = Field(default=2, ge=1)
    baseline_top_k: int = Field(default=20, ge=1)
    llm_runs: int = Field(default=3, ge=1)
    targets: list[TargetActivity] | None = Field(default=None, min_length=1)
    fragmentation_containment_threshold: float = Field(default=0.7, ge=0, le=1)

    @model_validator(mode="after")
    def validate_plan(self) -> ExperimentPlan:
        if self.start_datetime.utcoffset() is None:
            raise ValueError("start_datetime must be timezone-aware")
        if any(
            (
                self.start_datetime.hour,
                self.start_datetime.minute,
                self.start_datetime.second,
                self.start_datetime.microsecond,
            )
        ):
            raise ValueError("start_datetime must be local midnight")
        if len(self.seeds) != len(set(self.seeds)):
            raise ValueError("seeds must be unique")
        ids = [condition.id for condition in self.conditions]
        if len(ids) != len(set(ids)):
            raise ValueError("condition IDs must be unique")
        if self.targets is not None:
            target_ids = [target.id for target in self.targets]
            if len(target_ids) != len(set(target_ids)):
                raise ValueError("target IDs must be unique")
            slots = [
                (target.resident_id, minute)
                for target in self.targets
                for minute in target.scheduled_start_minutes
            ]
            if len(slots) != len(set(slots)):
                raise ValueError("target schedules for one resident must not share a start time")
        return self

    @property
    def days(self) -> int:
        return self.train_days + self.test_days


def load_plan(path: Path) -> ExperimentPlan:
    return ExperimentPlan.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
