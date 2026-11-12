"""Strict parsing of Binance Spot REST kline payloads."""

from __future__ import annotations

from .candles import Candle


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
        candle = Candle(
            symbol=symbol,
            interval=interval,
            open_time=int(row[0]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            close_time=int(row[6]),
            quote_volume=float(row[7]),
            trade_count=int(row[8]),
            taker_buy_base=float(row[9]),
            taker_buy_quote=float(row[10]),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"invalid Binance kline values: {exc}") from exc
    candle.validate()
    return candle
