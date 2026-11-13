"""Validated parsing helpers for the desktop market-data client."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True, slots=True)
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int


def parse_klines_payload(payload: dict[str, Any]) -> list[Candle]:
    """Parse the documented Sherlock klines response and reject malformed rows."""
    rows = payload.get("candles")
    if not isinstance(rows, list):
        raise ValueError("API response has no candles list")
    candles: list[Candle] = []
    previous_open_time = -1
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"candle {index} is not an object")
        try:
            candle = Candle(
                open_time=int(row["open_time"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                close_time=int(row["close_time"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"candle {index} has invalid fields") from exc
        values = (candle.open, candle.high, candle.low, candle.close, candle.volume)
        if not all(isfinite(value) for value in values):
            raise ValueError(f"candle {index} contains a non-finite number")
        if candle.open_time <= previous_open_time:
            raise ValueError("candles are not strictly ordered by open_time")
        if candle.low <= 0 or candle.volume < 0:
            raise ValueError(f"candle {index} has invalid price or volume")
        if candle.low > min(candle.open, candle.close) or candle.high < max(candle.open, candle.close):
            raise ValueError(f"candle {index} violates OHLC bounds")
        if candle.high < candle.low or candle.close_time < candle.open_time:
            raise ValueError(f"candle {index} has invalid range or timestamps")
        candles.append(candle)
        previous_open_time = candle.open_time
    return candles
