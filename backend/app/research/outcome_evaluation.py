"""Leakage-aware forward-path evaluation for frozen historical candidates.

A candidate ends at a closed candle. Entry is the next candle open, and each
horizon exits at that future candle's close. Costs are charged on both entry
and exit. Results are descriptive outcomes, never signals.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Sequence

from app.market_data.candles import Candle, find_gaps
from app.market_data.intervals import interval_to_ms


@dataclass(frozen=True, slots=True)
class ForwardOutcome:
    horizon: int
    entry_time: int
    exit_time: int
    entry_price: float
    exit_price: float
    gross_return: float
    long_net_return: float
    short_net_return: float
    long_mfe: float
    long_mae: float
    short_mfe: float
    short_mae: float
    max_high_low_range: float
    absolute_close_return: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ForwardEvaluation:
    symbol: str
    interval: str
    candidate_end_index: int
    candidate_end_time: int
    entry_time: int | None
    fee_bps_per_side: float
    slippage_bps_per_side: float
    outcomes: tuple[ForwardOutcome | None, ...]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "candidate_end_index": self.candidate_end_index,
            "candidate_end_time": self.candidate_end_time,
            "entry_time": self.entry_time,
            "fee_bps_per_side": self.fee_bps_per_side,
            "slippage_bps_per_side": self.slippage_bps_per_side,
            "outcomes": [item.to_dict() if item else None for item in self.outcomes],
            "interpretation": (
                "Historical forward outcomes only; not a forecast, probability, "
                "or trading signal. Sideways classification is intentionally "
                "not inferred from these metrics."
            ),
        }


def evaluate_forward_path(
    candles: Sequence[Candle],
    *,
    candidate_end_index: int,
    horizons: Sequence[int] = (1, 4, 16, 32, 64),
    fee_bps_per_side: float = 0.0,
    slippage_bps_per_side: float = 0.0,
) -> ForwardEvaluation:
    """Measure future LONG/SHORT path outcomes after a frozen candidate.

    candidate_end_index is inclusive. Entry is the next candle's open.
    Horizon N exits at the close of candle candidate_end_index + N. A horizon
    without enough future candles is returned as None, never extrapolated.

    MFE/MAE are gross price excursions from entry: favorable excursions are
    nonnegative and adverse excursions are nonpositive. The neutral movement
    descriptors are not a SIDEWAYS label.
    """
    if not candles:
        raise ValueError("candles must not be empty")
    if (isinstance(candidate_end_index, bool)
            or not isinstance(candidate_end_index, int)
            or candidate_end_index < 0
            or candidate_end_index >= len(candles)):
        raise ValueError("candidate_end_index is outside candle data")
    if not horizons:
        raise ValueError("at least one horizon is required")
    normalized_horizons = []
    for horizon in horizons:
        if (isinstance(horizon, bool) or not isinstance(horizon, int)
                or horizon < 1):
            raise ValueError("horizons must be positive integers")
        if horizon in normalized_horizons:
            raise ValueError("horizons must not contain duplicates")
        normalized_horizons.append(horizon)
    for label, value in (
        ("fee_bps_per_side", fee_bps_per_side),
        ("slippage_bps_per_side", slippage_bps_per_side),
    ):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0 or value >= 10_000):
            raise ValueError(f"{label} must be finite and in [0, 10000)")

    if fee_bps_per_side + slippage_bps_per_side >= 10_000:
        raise ValueError("combined per-side costs must be below 10000 bps")

    first = candles[0]
    step = interval_to_ms(first.interval)
    previous_time = None
    for candle in candles:
        candle.validate()
        if candle.symbol != first.symbol or candle.interval != first.interval:
            raise ValueError("all candles must share symbol and interval")
        if previous_time is not None and candle.open_time <= previous_time:
            raise ValueError("candle timestamps must be strictly increasing")
        previous_time = candle.open_time

    # Historical data may contain gaps elsewhere. Only the candidate-to-outcome
    # path is relevant here; reject a gap inside that path, not in an unrelated
    # older segment of the same loaded history.
    available_end = min(len(candles) - 1,
                        candidate_end_index + max(normalized_horizons))
    relevant = candles[candidate_end_index:available_end + 1]
    if len(relevant) > 1:
        gaps = find_gaps([c.open_time for c in relevant], first.interval)
        if gaps:
            raise ValueError("candidate forward path contains missing intervals")

    entry_index = candidate_end_index + 1
    if entry_index >= len(candles):
        entry_time = None
        outcomes = tuple(None for _ in normalized_horizons)
    else:
        entry_time = candles[entry_index].open_time
        entry_price = candles[entry_index].open
        round_trip_cost_factor = (
            1.0 - (fee_bps_per_side + slippage_bps_per_side) / 10_000.0
        ) ** 2
        results: list[ForwardOutcome | None] = []
        for horizon in normalized_horizons:
            exit_index = candidate_end_index + horizon
            if exit_index >= len(candles):
                results.append(None)
                continue
            path = candles[entry_index:exit_index + 1]
            exit_price = candles[exit_index].close
            gross = exit_price / entry_price - 1.0
            highest = max(c.high for c in path)
            lowest = min(c.low for c in path)
            long_mfe = max(0.0, highest / entry_price - 1.0)
            long_mae = min(0.0, lowest / entry_price - 1.0)
            short_mfe = max(0.0, entry_price / lowest - 1.0)
            short_mae = min(0.0, entry_price / highest - 1.0)
            results.append(ForwardOutcome(
                horizon=horizon,
                entry_time=entry_time,
                exit_time=candles[exit_index].open_time,
                entry_price=entry_price,
                exit_price=exit_price,
                gross_return=gross,
                long_net_return=(exit_price / entry_price) * round_trip_cost_factor - 1.0,
                short_net_return=(entry_price / exit_price) * round_trip_cost_factor - 1.0,
                long_mfe=long_mfe,
                long_mae=long_mae,
                short_mfe=short_mfe,
                short_mae=short_mae,
                max_high_low_range=highest / lowest - 1.0,
                absolute_close_return=abs(gross),
            ))
        outcomes = tuple(results)

    return ForwardEvaluation(
        symbol=first.symbol,
        interval=first.interval,
        candidate_end_index=candidate_end_index,
        candidate_end_time=candles[candidate_end_index].open_time,
        entry_time=entry_time,
        fee_bps_per_side=float(fee_bps_per_side),
        slippage_bps_per_side=float(slippage_bps_per_side),
        outcomes=outcomes,
    )
