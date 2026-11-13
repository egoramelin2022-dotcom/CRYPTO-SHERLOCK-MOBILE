"""Multi-timeframe BTC exhaustion/reclaim setup detector.

The detector is deliberately descriptive and configurable. It finds a 15m
lower-wick event that occurs inside a 4h support sweep/reclaim candle and a
large bearish daily candle during a broader decline. It emits observations,
not trade signals or forecasts.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, dataclass
import statistics
from typing import Sequence

from app.market_data.candles import Candle, find_gaps


@dataclass(frozen=True, slots=True)
class MultiTimeframeConfig:
    support_lookback_4h: int = 20
    daily_body_lookback: int = 60
    daily_decline_lookback: int = 20
    lower_wick_min_range_fraction: float = 0.55
    lower_wick_to_body_min: float = 2.0
    daily_body_multiple_of_median: float = 1.5
    daily_body_min_return: float = 0.02
    daily_decline_min_return: float = 0.0
    support_sweep_tolerance: float = 0.0


@dataclass(frozen=True, slots=True)
class MultiTimeframeSignal:
    timestamp: int
    price: float
    wick_15m_fraction: float
    wick_15m_to_body: float
    support_4h: float
    sweep_depth_4h: float
    reclaim_close_4h: float
    daily_body_return: float
    daily_body_median: float
    daily_return_lookback: float

    def to_dict(self) -> dict:
        return asdict(self)


def _validate_series(candles: Sequence[Candle], interval: str, label: str) -> None:
    if not candles:
        raise ValueError(f"{label} candles must not be empty")
    for candle in candles:
        candle.validate()
        if candle.interval != interval:
            raise ValueError(f"{label} candles must use {interval}")
        if candle.symbol != candles[0].symbol:
            raise ValueError(f"{label} candles must share one symbol")
    gaps = find_gaps([c.open_time for c in candles], interval)
    if gaps:
        raise ValueError(f"{label} candle sequence contains missing intervals")


def _containing_index(candles: Sequence[Candle], open_times: list[int], timestamp: int) -> int | None:
    index = bisect_right(open_times, timestamp) - 1
    if index < 0 or timestamp > candles[index].close_time:
        return None
    return index


def detect_multitimeframe_setups(
    candles_15m: Sequence[Candle],
    candles_4h: Sequence[Candle],
    candles_1d: Sequence[Candle],
    *,
    config: MultiTimeframeConfig = MultiTimeframeConfig(),
) -> list[MultiTimeframeSignal]:
    """Find aligned 15m wick + 4h support reclaim + bearish daily context.

    The support level for a 4h bar is the minimum low of the preceding
    lookback bars, excluding the current bar. A sweep requires the current
    low to pierce that level and the same 4h candle to close back above it.

    A large bearish daily candle has a body return below zero whose absolute
    size is at least the configured multiple of the median absolute body
    return over prior daily bars. The broader decline is measured from the
    close N daily bars earlier to the current daily close.

    Only complete historical candles should be supplied. No unfinished
    current candles are inferred or fetched here.
    """
    if config.support_lookback_4h < 2:
        raise ValueError("support_lookback_4h must be >= 2")
    if config.daily_body_lookback < 5 or config.daily_decline_lookback < 2:
        raise ValueError("daily lookbacks are too short")
    if not 0 < config.lower_wick_min_range_fraction <= 1:
        raise ValueError("lower_wick_min_range_fraction must be in (0, 1]")
    if config.lower_wick_to_body_min < 0 or config.daily_body_multiple_of_median <= 0:
        raise ValueError("wick and daily body multipliers must be positive")
    if not 0 <= config.daily_body_min_return < 1:
        raise ValueError("daily_body_min_return must be in [0, 1)")
    if config.support_sweep_tolerance < 0:
        raise ValueError("support_sweep_tolerance must be nonnegative")

    _validate_series(candles_15m, "15m", "15m")
    _validate_series(candles_4h, "4h", "4h")
    _validate_series(candles_1d, "1d", "1d")
    symbol = candles_15m[0].symbol
    if candles_4h[0].symbol != symbol or candles_1d[0].symbol != symbol:
        raise ValueError("all timeframes must use the same symbol")

    times_4h = [c.open_time for c in candles_4h]
    times_1d = [c.open_time for c in candles_1d]
    results: list[MultiTimeframeSignal] = []

    for candle_15m in candles_15m:
        span = candle_15m.high - candle_15m.low
        lower_wick = min(candle_15m.open, candle_15m.close) - candle_15m.low
        body = abs(candle_15m.close - candle_15m.open)
        if span <= 0 or lower_wick / span < config.lower_wick_min_range_fraction:
            continue
        wick_to_body = lower_wick / max(body, candle_15m.open * 1e-12)
        if wick_to_body < config.lower_wick_to_body_min:
            continue

        index_4h = _containing_index(candles_4h, times_4h, candle_15m.open_time)
        if index_4h is None or index_4h < config.support_lookback_4h:
            continue
        bar_4h = candles_4h[index_4h]
        prior_support = min(
            c.low for c in candles_4h[
                index_4h - config.support_lookback_4h:index_4h
            ]
        )
        sweep_line = prior_support * (1.0 - config.support_sweep_tolerance)
        if not (bar_4h.low < sweep_line and bar_4h.close > prior_support):
            continue

        index_1d = _containing_index(candles_1d, times_1d, candle_15m.open_time)
        if index_1d is None:
            continue
        if index_1d < max(config.daily_body_lookback, config.daily_decline_lookback):
            continue
        bar_1d = candles_1d[index_1d]
        daily_body_return = bar_1d.close / bar_1d.open - 1.0
        prior_bodies = [
            abs(c.close / c.open - 1.0)
            for c in candles_1d[
                index_1d - config.daily_body_lookback:index_1d
            ]
        ]
        median_body = statistics.median(prior_bodies)
        decline_return = (
            bar_1d.close /
            candles_1d[index_1d - config.daily_decline_lookback].close - 1.0
        )
        if daily_body_return >= 0:
            continue
        if abs(daily_body_return) < median_body * config.daily_body_multiple_of_median:
            continue
        if decline_return > -config.daily_decline_min_return:
            continue

        results.append(MultiTimeframeSignal(
            timestamp=candle_15m.open_time,
            price=candle_15m.close,
            wick_15m_fraction=lower_wick / span,
            wick_15m_to_body=wick_to_body,
            support_4h=prior_support,
            sweep_depth_4h=prior_support - bar_4h.low,
            reclaim_close_4h=bar_4h.close,
            daily_body_return=daily_body_return,
            daily_body_median=median_body,
            daily_return_lookback=decline_return,
        ))
    return results
