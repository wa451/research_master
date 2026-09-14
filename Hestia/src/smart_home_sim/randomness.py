"""Single deterministic source for every stochastic simulation decision."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import TypeVar

from smart_home_sim.schema import (
    DistributionConfig,
    DistributionKind,
    SecondaryActivityRule,
)

T = TypeVar("T")


class RandomManager:
    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._random = random.Random(seed)

    def varied_duration(self, base_minutes: float, variation_fraction: float) -> float:
        if variation_fraction == 0:
            return base_minutes
        return self._random.uniform(
            base_minutes * (1 - variation_fraction),
            base_minutes * (1 + variation_fraction),
        )

    def sample(self, distribution: DistributionConfig) -> float:
        if distribution.kind is DistributionKind.FIXED:
            value = distribution.value
        elif distribution.kind is DistributionKind.UNIFORM:
            assert distribution.low is not None and distribution.high is not None
            value = self._random.uniform(distribution.low, distribution.high)
        elif distribution.kind is DistributionKind.NORMAL:
            assert distribution.mean is not None
            assert distribution.standard_deviation is not None
            value = self._random.gauss(distribution.mean, distribution.standard_deviation)
        elif distribution.kind is DistributionKind.LOGNORMAL:
            assert distribution.mu is not None and distribution.sigma is not None
            value = self._random.lognormvariate(distribution.mu, distribution.sigma)
        else:
            total = sum(choice.weight for choice in distribution.choices)
            draw = self._random.random() * total
            cumulative = 0.0
            value = distribution.choices[-1].value
            for choice in distribution.choices:
                cumulative += choice.weight
                if draw < cumulative:
                    value = choice.value
                    break
        if distribution.clip_min is not None:
            value = max(distribution.clip_min, value)
        if distribution.clip_max is not None:
            value = min(distribution.clip_max, value)
        return value

    def sample_count(self, distribution: DistributionConfig) -> int:
        return max(0, round(self.sample(distribution)))

    def chance(self, probability: float) -> bool:
        if probability <= 0:
            return False
        if probability >= 1:
            return True
        return self._random.random() < probability

    def weighted_choice(self, items: Sequence[T], weights: Sequence[float]) -> T:
        if not items or len(items) != len(weights):
            raise ValueError("weighted choice requires equally sized non-empty items and weights")
        total = sum(weights)
        if total <= 0:
            raise ValueError("weighted choice requires a positive total weight")
        draw = self._random.random() * total
        cumulative = 0.0
        for item, weight in zip(items, weights, strict=True):
            cumulative += weight
            if draw < cumulative:
                return item
        return items[-1]

    def choose_secondary(
        self, rules: Sequence[SecondaryActivityRule], factor: float
    ) -> SecondaryActivityRule | None:
        draw = self._random.random()
        cumulative = 0.0
        for rule in rules:
            cumulative += rule.probability * factor
            if draw < cumulative:
                return rule
        return None
