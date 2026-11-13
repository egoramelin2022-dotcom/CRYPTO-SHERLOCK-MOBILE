"""Aggregate forward outcomes without converting them into forecasts.

Sideways is an explicit, configurable descriptive bucket based on both
maximum path range and absolute close-to-close movement. LONG/SHORT rates
remain separate cost-adjusted measurements and are not mutually exclusive
with the sideways descriptor.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean, median
from typing import Iterable

from app.research.outcome_evaluation import ForwardOutcome, ForwardEvaluation


@dataclass(frozen=True, slots=True)
class HorizonOutcomeSummary:
    horizon: int
    sample_count: int
    long_net_positive_rate: float
    short_net_positive_rate: float
    long_net_mean: float
    long_net_median: float
    short_net_mean: float
    short_net_median: float
    median_absolute_close_return: float
    median_max_range: float
    sideways_rate: float
    mean_long_mae: float
    mean_short_mae: float

    def to_dict(self) -> dict:
        return asdict(self)


def summarize_forward_outcomes(
    evaluations: Iterable[ForwardEvaluation],
    *,
    sideways_max_range: float = 0.01,
    sideways_max_abs_close_return: float = 0.005,
) -> tuple[HorizonOutcomeSummary, ...]:
    """Summarize observed outcomes by horizon, omitting unavailable labels.

    A path is tagged SIDEWAYS only when BOTH its full high-low range and its
    absolute entry-to-exit close move are within the supplied thresholds.
    This is a retrospective descriptive tag, not a live regime detector.
    """
    for name, value in (
        ("sideways_max_range", sideways_max_range),
        ("sideways_max_abs_close_return", sideways_max_abs_close_return),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a finite number in [0, 1)")
        if not 0 <= value < 1:
            raise ValueError(f"{name} must be a finite number in [0, 1)")

    buckets: dict[int, list[ForwardOutcome]] = {}
    for evaluation in evaluations:
        for outcome in evaluation.outcomes:
            if outcome is not None:
                buckets.setdefault(outcome.horizon, []).append(outcome)

    summaries = []
    for horizon in sorted(buckets):
        rows = buckets[horizon]
        count = len(rows)
        sideways_count = sum(
            row.max_high_low_range <= sideways_max_range
            and row.absolute_close_return <= sideways_max_abs_close_return
            for row in rows
        )
        long_returns = [row.long_net_return for row in rows]
        short_returns = [row.short_net_return for row in rows]
        summaries.append(HorizonOutcomeSummary(
            horizon=horizon,
            sample_count=count,
            long_net_positive_rate=sum(value > 0 for value in long_returns) / count,
            short_net_positive_rate=sum(value > 0 for value in short_returns) / count,
            long_net_mean=mean(long_returns),
            long_net_median=median(long_returns),
            short_net_mean=mean(short_returns),
            short_net_median=median(short_returns),
            median_absolute_close_return=median(
                row.absolute_close_return for row in rows
            ),
            median_max_range=median(row.max_high_low_range for row in rows),
            sideways_rate=sideways_count / count,
            mean_long_mae=mean(row.long_mae for row in rows),
            mean_short_mae=mean(row.short_mae for row in rows),
        ))
    return tuple(summaries)
