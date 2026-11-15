"""Strict parsing of Binance Spot REST kline payloads."""

from __future__ import annotations

from .candles import Candle
from .intervals import interval_to_ms


def parse_binance_kline(row: list | tuple, *, symbol: str, interval: str) -> Candle:
    """Convert one Binance /api/v3/klines row into a validated Candle.

    Binance kline fields:
    0 open time, 1 open, 2 high, 3 low, 4 close, 5 base volume,
    6 close time, 7 quote volume, 8 trade count, 9 taker-buy base,
    10 taker-buy quote, 11 ignored/unused.
    """
    if not isinstance(row, (list, tuple)) or len(row) != 12:
        raise ValueError("Binance kline row must contain exactly 12 fields")
    try:
        raw_open_time = int(row[0])
        raw_close_time = int(row[6])
        # Binance Spot public archives use microseconds from 2025-01-01.
        # Normalize both timestamp fields together before validation.
        open_is_microseconds = raw_open_time >= 100_000_000_000_000
        close_is_microseconds = raw_close_time >= 100_000_000_000_000
        if open_is_microseconds != close_is_microseconds:
            raise ValueError("open_time and close_time use different timestamp precisions")
        divisor = 1_000 if open_is_microseconds else 1
        if divisor == 1_000 and (raw_open_time % divisor or raw_close_time % divisor):
            raise ValueError("microsecond timestamps must represent exact millisecond boundaries")
        open_time = raw_open_time // divisor
        close_time = raw_close_time // divisor
        expected_close = open_time + interval_to_ms(interval) - 1
        # Internal storage uses the final millisecond (inclusive close).
        if close_time == expected_close + 1:
            close_time = expected_close
        if close_time != expected_close:
            raise ValueError(
                f"{interval} close_time mismatch: open={open_time}, close={close_time}, "
                f"expected={expected_close}, raw_open={raw_open_time}, raw_close={raw_close_time}"
            )
        candle = Candle(
            symbol=symbol,
            interval=interval,
            open_time=open_time,
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            close_time=close_time,
            quote_volume=float(row[7]),
            trade_count=int(row[8]),
            taker_buy_base=float(row[9]),
            taker_buy_quote=float(row[10]),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"invalid Binance kline values: {exc}") from exc
    candle.validate()
    return candle
