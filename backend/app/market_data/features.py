"""Deterministic, point-in-time market feature extraction.

Features are computed only from supplied, validated candles. Gaps split the
series into independent segments; no rolling calculation crosses a missing
interval. This module is descriptive, not a trading signal.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

from .candles import Candle
from .intervals import interval_to_ms


@dataclass(frozen=True, slots=True)
class MarketFeature:
    symbol: str
    interval: str
    open_time: int
    body_pct: float
    range_pct: float
    upper_wick_pct: float
    lower_wick_pct: float
    close_location: float
    return_1: float | None
    return_window: float | None
    realized_volatility: float | None
    atr_pct: float | None
    volume_zscore: float | None
    taker_buy_ratio: float | None
    trade_count_zscore: float | None
    efficiency_ratio: float | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MarketRegime:
    label: str
    direction: str
    confidence: float
    reasons: tuple[str, ...]


def split_contiguous_segments(candles: Iterable[Candle]) -> list[list[Candle]]:
    """Validate and split candles at gaps; never bridge missing intervals."""
    items = list(candles)
    if not items:
        return []
    identity = {(c.symbol, c.interval) for c in items}
    if len(identity) != 1:
        raise ValueError("feature input must contain one symbol and interval")
    step = interval_to_ms(items[0].interval)
    segments: list[list[Candle]] = []
    current: list[Candle] = []
    previous: int | None = None
    for candle in items:
        candle.validate()
        if previous is not None and candle.open_time <= previous:
            raise ValueError("candles must be strictly increasing")
        if previous is not None and candle.open_time - previous != step:
            segments.append(current)
            current = []
        current.append(candle)
        previous = candle.open_time
    if current:
        segments.append(current)
    return segments


def _zscore(value: float, values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    deviation = statistics.pstdev(values)
    if deviation == 0:
        return 0.0
    return (value - statistics.mean(values)) / deviation


def extract_features(
    candles: Iterable[Candle], *, window: int = 20
) -> list[MarketFeature]:
    """Extract candle morphology, return, volatility and flow features.

    Rolling windows include the current closed candle and only earlier
    candles from the same uninterrupted segment.
    """
    if isinstance(window, bool) or not isinstance(window, int) or window < 2:
        raise ValueError("window must be an integer >= 2")
    segments = split_contiguous_segments(candles)
    output: list[MarketFeature] = []
    for segment in segments:
        for index, candle in enumerate(segment):
            price_range = candle.high - candle.low
            body = abs(candle.close - candle.open)
            upper = candle.high - max(candle.open, candle.close)
            lower = min(candle.open, candle.close) - candle.low
            close_location = (
                (candle.close - candle.low) / price_range if price_range else 0.5
            )
            history = segment[max(0, index - window + 1): index + 1]
            returns = [
                math.log(history[i].close / history[i - 1].close)
                for i in range(1, len(history))
            ]
            return_1 = (
                math.log(candle.close / segment[index - 1].close)
                if index > 0 else None
            )
            return_window = (
                math.log(candle.close / history[0].close)
                if len(history) >= 2 else None
            )
            realized_volatility = (
                statistics.pstdev(returns) if len(returns) >= 2 else None
            )
            true_ranges = []
            for j, item in enumerate(history):
                previous_close = (
                    history[j - 1].close if j > 0
                    else (segment[index - len(history)].close
                          if index - len(history) >= 0 else item.open)
                )
                true_ranges.append(max(
                    item.high - item.low,
                    abs(item.high - previous_close),
                    abs(item.low - previous_close),
                ))
            atr_pct = (
                statistics.mean(true_ranges) / candle.close
                if true_ranges else None
            )
            volumes = [item.volume for item in history]
            trades = [float(item.trade_count) for item in history]
            volume_zscore = _zscore(candle.volume, volumes)
            trade_count_zscore = _zscore(float(candle.trade_count), trades)
            total_volume = candle.volume
            taker_buy_ratio = (
                candle.taker_buy_base / total_volume if total_volume > 0 else None
            )
            path_length = sum(
                abs(segment[j].close - segment[j - 1].close)
                for j in range(max(1, index - window + 1), index + 1)
            )
            net_move = (
                abs(candle.close - history[0].close) if len(history) >= 2 else 0.0
            )
            efficiency = net_move / path_length if path_length > 0 else (
                0.0 if len(history) >= 2 else None
            )
            output.append(MarketFeature(
                symbol=candle.symbol,
                interval=candle.interval,
                open_time=candle.open_time,
                body_pct=body / candle.open,
                range_pct=price_range / candle.open,
                upper_wick_pct=upper / candle.open,
                lower_wick_pct=lower / candle.open,
                close_location=close_location,
                return_1=return_1,
                return_window=return_window,
                realized_volatility=realized_volatility,
                atr_pct=atr_pct,
                volume_zscore=volume_zscore,
                taker_buy_ratio=taker_buy_ratio,
                trade_count_zscore=trade_count_zscore,
                efficiency_ratio=efficiency,
            ))
    return output


def classify_regime(
    feature: MarketFeature,
    *,
    high_volatility_atr_pct: float = 0.012,
    trend_efficiency: float = 0.35,
    trend_return_abs: float = 0.005,
    range_efficiency: float = 0.20,
) -> MarketRegime:
    """Transparent heuristic regime label; thresholds are configurable."""
    if high_volatility_atr_pct <= 0:
        raise ValueError("high_volatility_atr_pct must be positive")
    if not 0 <= range_efficiency < trend_efficiency <= 1:
        raise ValueError("efficiency thresholds must satisfy 0 <= range < trend <= 1")
    if trend_return_abs < 0:
        raise ValueError("trend_return_abs must be nonnegative")
    efficiency = feature.efficiency_ratio
    move = feature.return_window
    atr = feature.atr_pct
    if efficiency is None or move is None or atr is None:
        return MarketRegime("INSUFFICIENT_DATA", "NEUTRAL", 0.0, ("warmup window",))
    reasons: list[str] = []
    if atr >= high_volatility_atr_pct:
        reasons.append("ATR percentage exceeds high-volatility threshold")
        label = "HIGH_VOLATILITY"
    elif efficiency >= trend_efficiency and abs(move) >= trend_return_abs:
        label = "TREND"
        reasons.extend(("directional efficiency is elevated", "window return is material"))
    elif efficiency <= range_efficiency:
        label = "RANGE"
        reasons.append("directional efficiency is low")
    else:
        label = "TRANSITION"
        reasons.append("trend and range conditions are inconclusive")
    direction = "UP" if move > 0 else "DOWN" if move < 0 else "NEUTRAL"
    confidence = min(1.0, max(0.0, efficiency))
    if label == "HIGH_VOLATILITY":
        confidence = min(1.0, atr / high_volatility_atr_pct - 1.0)
    return MarketRegime(label, direction, confidence, tuple(reasons))
