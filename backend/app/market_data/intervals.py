"""Strict Binance interval parsing and UTC millisecond arithmetic.

Calendar months (1M) are intentionally excluded: they cannot be represented
by a constant millisecond step and need calendar-aware boundaries.
"""

from __future__ import annotations

import re

_FIXED_UNITS_MS = {
    "s": 1_000,
    "m": 60_000,
    "h": 3_600_000,
    "d": 86_400_000,
    "w": 604_800_000,
}
_INTERVAL_RE = re.compile(r"^([1-9][0-9]*)([smhdw])$")


def interval_to_ms(interval: str) -> int:
    """Return the fixed duration of a Binance interval in milliseconds.

    Raises ValueError for malformed, zero, or calendar-month intervals.
    """
    if not isinstance(interval, str):
        raise ValueError("interval must be a string")
    match = _INTERVAL_RE.fullmatch(interval)
    if not match:
        raise ValueError(f"unsupported fixed interval: {interval!r}")
    amount = int(match.group(1))
    unit = match.group(2)
    return amount * _FIXED_UNITS_MS[unit]


def floor_to_interval(timestamp_ms: int, interval: str) -> int:
    """Floor a UTC epoch-millisecond timestamp to its interval boundary."""
    step = interval_to_ms(interval)
    return timestamp_ms - (timestamp_ms % step)


def expected_open_times(start_ms: int, end_ms: int, interval: str) -> range:
    """Return aligned candle open times in [start_ms, end_ms]."""
    step = interval_to_ms(interval)
    if start_ms > end_ms:
        raise ValueError("start_ms must be <= end_ms")
    if start_ms % step or end_ms % step:
        raise ValueError("range boundaries must align to interval")
    return range(start_ms, end_ms + 1, step)
