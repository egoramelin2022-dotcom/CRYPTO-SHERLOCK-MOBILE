"""Canonical candle validation and continuity auditing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .intervals import interval_to_ms


@dataclass(frozen=True, slots=True)
class Candle:
    symbol: str
    interval: str
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int
    quote_volume: float
    trade_count: int
    taker_buy_base: float
    taker_buy_quote: float

    def validate(self) -> None:
        """Reject malformed or internally inconsistent exchange candles."""
        if not self.symbol or not self.symbol.isalnum():
            raise ValueError("invalid symbol")
        step = interval_to_ms(self.interval)
        if self.open_time < 0 or self.open_time % step:
            raise ValueError("open_time is not aligned to interval")
        if self.close_time != self.open_time + step - 1:
            raise ValueError("close_time does not match interval")
        prices = (self.open, self.high, self.low, self.close)
        if any(not _finite_positive(value) for value in prices):
            raise ValueError("OHLC prices must be finite and positive")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high is below another OHLC value")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low is above another OHLC value")
        if not _finite_nonnegative(self.volume):
            raise ValueError("volume must be finite and nonnegative")
        if not _finite_nonnegative(self.quote_volume):
            raise ValueError("quote_volume must be finite and nonnegative")
        if not _finite_nonnegative(self.taker_buy_base):
            raise ValueError("taker_buy_base must be finite and nonnegative")
        if not _finite_nonnegative(self.taker_buy_quote):
            raise ValueError("taker_buy_quote must be finite and nonnegative")
        if isinstance(self.trade_count, bool) or self.trade_count < 0:
            raise ValueError("trade_count must be a nonnegative integer")
        if not isinstance(self.trade_count, int):
            raise ValueError("trade_count must be an integer")
        if self.taker_buy_base > self.volume + 1e-12:
            raise ValueError("taker_buy_base exceeds total base volume")
        if self.taker_buy_quote > self.quote_volume + 1e-12:
            raise ValueError("taker_buy_quote exceeds total quote volume")


def _finite_positive(value: float) -> bool:
    import math
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def _finite_nonnegative(value: float) -> bool:
    import math
    return isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


@dataclass(frozen=True, slots=True)
class Gap:
    previous_open_time: int
    next_open_time: int
    missing_candles: int


def find_gaps(open_times: Iterable[int], interval: str) -> list[Gap]:
    """Find missing candle slots; input must be strictly increasing."""
    step = interval_to_ms(interval)
    ordered = list(open_times)
    gaps: list[Gap] = []
    previous = None
    for current in ordered:
        if current % step:
            raise ValueError(f"unaligned candle timestamp: {current}")
        if previous is not None:
            delta = current - previous
            if delta <= 0:
                raise ValueError("timestamps must be strictly increasing")
            if delta > step:
                gaps.append(Gap(previous, current, delta // step - 1))
            elif delta != step:
                raise ValueError("timestamps are not on interval sequence")
        previous = current
    return gaps
