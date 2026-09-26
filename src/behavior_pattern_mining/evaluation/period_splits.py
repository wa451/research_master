"""Shared chronological scoring windows for Evaluations 6 and 7.

The generated state definition and LLM patterns are always learned from the
initial ``generation_days``.  This module only controls which later intervals
are visible to a scoring evaluation; it never re-learns a state table.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Iterable, Literal, Sequence, TypeVar


SPLIT_MODES = ("holdout", "legacy")
SplitMode = Literal["holdout", "legacy"]
EvaluationRole = Literal["validation", "test"]
T = TypeVar("T")


@dataclass(frozen=True)
class EvaluationSplit:
    """Resolved half-open calendar windows, anchored at the first data day."""

    split_mode: SplitMode
    dataset_start: datetime
    dataset_end: datetime
    generation_days: int
    validation_start_day: int
    validation_end_day: int
    test_start_day: int
    test_end_day: int

    def day_boundary(self, day: int) -> datetime:
        return self.dataset_start + timedelta(days=day - 1)

    @property
    def generation_start(self) -> datetime:
        return self.dataset_start

    @property
    def generation_end(self) -> datetime:
        return self.dataset_start + timedelta(days=self.generation_days)

    def scoring_period(self, role: EvaluationRole) -> tuple[datetime, datetime]:
        if self.split_mode == "legacy":
            return self.dataset_start, self.dataset_end
        if role == "validation":
            return self.day_boundary(self.validation_start_day), min(
                self.day_boundary(self.validation_end_day + 1), self.dataset_end
            )
        return self.day_boundary(self.test_start_day), min(
            self.day_boundary(self.test_end_day + 1), self.dataset_end
        )

    def metadata(self, role: EvaluationRole) -> dict[str, object]:
        start, end = self.scoring_period(role)
        return {
            "split_mode": self.split_mode,
            "evaluation_role": role,
            "generation_start": self.generation_start.isoformat(sep=" "),
            "generation_end": self.generation_end.isoformat(sep=" "),
            "evaluation_start": start.isoformat(sep=" "),
            "evaluation_end": end.isoformat(sep=" "),
            "generation_days": self.generation_days,
            "validation_start_day": self.validation_start_day,
            "validation_end_day": self.validation_end_day,
            "test_start_day": self.test_start_day,
            "test_end_day": self.test_end_day,
        }


def add_split_arguments(parser) -> None:
    parser.add_argument("--split-mode", choices=SPLIT_MODES, default="holdout")
    parser.add_argument("--generation-days", type=int, default=None)
    parser.add_argument("--validation-start-day", type=int, default=15)
    parser.add_argument("--validation-end-day", type=int, default=154)
    parser.add_argument("--test-start-day", type=int, default=155)
    parser.add_argument("--test-end-day", type=int, default=220)


def resolve_split(
    intervals: Sequence[object],
    *,
    split_mode: str,
    generation_days: int,
    validation_start_day: int,
    validation_end_day: int,
    test_start_day: int,
    test_end_day: int,
) -> EvaluationSplit:
    if not intervals:
        raise ValueError("cannot resolve an evaluation split without intervals")
    starts = [item.start_time for item in intervals]
    ends = [item.end_time for item in intervals]
    first = min(starts)
    # Keep the timestamp implementation (including pandas-compatible datetime
    # subclasses) and anchor chronological "Day 1" at its local midnight.
    dataset_start = first.replace(hour=0, minute=0, second=0, microsecond=0)
    dataset_end = max(ends)
    if split_mode not in SPLIT_MODES:
        raise ValueError(f"unknown split mode: {split_mode}")
    values = (generation_days, validation_start_day, validation_end_day, test_start_day, test_end_day)
    if any(value < 1 for value in values):
        raise ValueError("split day indexes must be >= 1")
    if validation_start_day > validation_end_day or test_start_day > test_end_day:
        raise ValueError("split start day must not exceed its end day")
    if split_mode == "holdout" and not (
        generation_days < validation_start_day <= validation_end_day < test_start_day <= test_end_day
    ):
        raise ValueError("holdout windows must be ordered and non-overlapping")
    return EvaluationSplit(
        split_mode=split_mode, dataset_start=dataset_start, dataset_end=dataset_end,
        generation_days=generation_days, validation_start_day=validation_start_day,
        validation_end_day=validation_end_day, test_start_day=test_start_day,
        test_end_day=test_end_day,
    )


def clip_intervals(intervals: Iterable[T], start: datetime, end: datetime) -> list[T]:
    """Clip interval dataclasses to ``[start, end)`` without double counting."""
    clipped: list[T] = []
    for interval in intervals:
        interval_start = max(interval.start_time, start)
        interval_end = min(interval.end_time, end)
        if interval_end > interval_start:
            clipped.append(replace(interval, start_time=interval_start, end_time=interval_end))
    return clipped
