"""Read-only historical feature pipeline with a separate analytics database.

The source market database is opened in SQLite read-only mode. Derived data
is written only to the explicitly supplied analytics database.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .candles import Candle
from .features import MarketFeature, classify_regime, extract_features
from .intervals import interval_to_ms


@dataclass(frozen=True, slots=True)
class PipelineResult:
    symbol: str
    interval: str
    candles_read: int
    features_written: int
    regimes_written: int
    segments: int
    source_min_open_time: int | None
    source_max_open_time: int | None


ANALYTICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS market_features (
    symbol TEXT NOT NULL, interval TEXT NOT NULL, open_time INTEGER NOT NULL,
    body_pct REAL NOT NULL, range_pct REAL NOT NULL,
    upper_wick_pct REAL NOT NULL, lower_wick_pct REAL NOT NULL,
    close_location REAL NOT NULL, return_1 REAL, return_window REAL,
    realized_volatility REAL, atr_pct REAL, volume_zscore REAL,
    taker_buy_ratio REAL, trade_count_zscore REAL, efficiency_ratio REAL,
    PRIMARY KEY(symbol, interval, open_time)
);
CREATE TABLE IF NOT EXISTS market_regimes (
    symbol TEXT NOT NULL, interval TEXT NOT NULL, open_time INTEGER NOT NULL,
    label TEXT NOT NULL, direction TEXT NOT NULL, confidence REAL NOT NULL,
    reasons TEXT NOT NULL,
    PRIMARY KEY(symbol, interval, open_time)
);
CREATE TABLE IF NOT EXISTS pattern_dataset (
    symbol TEXT NOT NULL, interval TEXT NOT NULL, open_time INTEGER NOT NULL,
    feature_json TEXT NOT NULL,
    forward_return_1 REAL, forward_return_4 REAL,
    forward_return_16 REAL,
    PRIMARY KEY(symbol, interval, open_time)
);
CREATE TABLE IF NOT EXISTS analytics_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL, interval TEXT NOT NULL,
    window INTEGER NOT NULL, candles_read INTEGER NOT NULL,
    features_written INTEGER NOT NULL, regimes_written INTEGER NOT NULL,
    segments INTEGER NOT NULL, source_min_open_time INTEGER,
    source_max_open_time INTEGER, completed_at TEXT NOT NULL
);
"""


def _read_only_uri(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"source database does not exist: {resolved}")
    return resolved.as_uri() + "?mode=ro"


def load_candles_read_only(
    source_db: str | Path, *, symbol: str, interval: str
) -> list[Candle]:
    """Load ordered validated candles without permitting source DB writes."""
    uri = _read_only_uri(source_db)
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute(
            """SELECT symbol, interval, open_time, open, high, low, close,
                      volume, close_time, quote_volume, trade_count,
                      taker_buy_base, taker_buy_quote
               FROM candles WHERE symbol=? AND interval=?
               ORDER BY open_time""",
            (symbol, interval),
        )
        candles: list[Candle] = []
        for row in rows:
            candle = Candle(
                symbol=row[0], interval=row[1], open_time=int(row[2]),
                open=float(row[3]), high=float(row[4]), low=float(row[5]),
                close=float(row[6]), volume=float(row[7]), close_time=int(row[8]),
                quote_volume=float(row[9]), trade_count=int(row[10]),
                taker_buy_base=float(row[11]), taker_buy_quote=float(row[12]),
            )
            candle.validate()
            candles.append(candle)
        return candles
    finally:
        conn.close()


def _forward_return(closes: list[float], index: int, horizon: int) -> float | None:
    target = index + horizon
    if target >= len(closes):
        return None
    return closes[target] / closes[index] - 1.0


def _build_pattern_rows(
    candles: list[Candle], features: list[MarketFeature]
) -> list[tuple]:
    """Feature snapshot and separately stored future outcomes within segments."""
    rows: list[tuple] = []
    offset = 0
    for segment_features in _feature_segments(features):
        count = len(segment_features)
        segment_candles = candles[offset:offset + count]
        closes = [c.close for c in segment_candles]
        for i, feature in enumerate(segment_features):
            import json
            rows.append((
                feature.symbol, feature.interval, feature.open_time,
                json.dumps(feature.to_dict(), separators=(",", ":"), sort_keys=True),
                _forward_return(closes, i, 1),
                _forward_return(closes, i, 4),
                _forward_return(closes, i, 16),
            ))
        offset += count
    return rows


def _feature_segments(features: list[MarketFeature]) -> list[list[MarketFeature]]:
    if not features:
        return []
    step = interval_to_ms(features[0].interval)
    result: list[list[MarketFeature]] = []
    current: list[MarketFeature] = []
    previous: int | None = None
    for feature in features:
        if previous is not None and feature.open_time - previous != step:
            result.append(current)
            current = []
        current.append(feature)
        previous = feature.open_time
    if current:
        result.append(current)
    return result


def run_historical_pipeline(
    source_db: str | Path,
    analytics_db: str | Path,
    *,
    symbol: str = "BTCUSDT",
    interval: str = "15m",
    window: int = 20,
) -> PipelineResult:
    """Rebuild derived analytics from source candles; source remains read-only."""
    source_path = Path(source_db).expanduser().resolve()
    output_path = Path(analytics_db).expanduser().resolve()
    if source_path == output_path:
        raise ValueError("analytics database must be separate from source database")
    candles = load_candles_read_only(source_path, symbol=symbol, interval=interval)
    features = extract_features(candles, window=window)
    segments = len(_feature_segments(features))
    regimes = [(f, classify_regime(f)) for f in features]
    pattern_rows = _build_pattern_rows(candles, features)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out = sqlite3.connect(str(output_path))
    try:
        out.executescript(ANALYTICS_SCHEMA)
        feature_rows = [
            (f.symbol, f.interval, f.open_time, f.body_pct, f.range_pct,
             f.upper_wick_pct, f.lower_wick_pct, f.close_location, f.return_1,
             f.return_window, f.realized_volatility, f.atr_pct, f.volume_zscore,
             f.taker_buy_ratio, f.trade_count_zscore, f.efficiency_ratio)
            for f in features
        ]
        regime_rows = [
            (f.symbol, f.interval, f.open_time, r.label, r.direction,
             r.confidence, "|".join(r.reasons))
            for f, r in regimes
        ]
        with out:
            out.executemany(
                """INSERT OR REPLACE INTO market_features VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )""", feature_rows,
            )
            out.executemany(
                "INSERT OR REPLACE INTO market_regimes VALUES (?, ?, ?, ?, ?, ?, ?)",
                regime_rows,
            )
            out.executemany(
                "INSERT OR REPLACE INTO pattern_dataset VALUES (?, ?, ?, ?, ?, ?, ?)",
                pattern_rows,
            )
            from datetime import datetime, timezone
            out.execute(
                """INSERT INTO analytics_runs (
                    symbol, interval, window, candles_read, features_written,
                    regimes_written, segments, source_min_open_time,
                    source_max_open_time, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (symbol, interval, window, len(candles), len(features),
                 len(regimes), segments,
                 candles[0].open_time if candles else None,
                 candles[-1].open_time if candles else None,
                 datetime.now(timezone.utc).isoformat()),
            )
        return PipelineResult(
            symbol, interval, len(candles), len(features), len(regimes),
            segments,
            candles[0].open_time if candles else None,
            candles[-1].open_time if candles else None,
        )
    finally:
        out.close()
