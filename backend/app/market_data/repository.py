"""SQLite persistence for canonical market candles.

The schema intentionally matches the existing local candles table so the
new repository can be tested independently and later adopted without a
destructive database migration.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from .candles import Candle


CANDLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    open_time INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    close_time INTEGER NOT NULL,
    quote_volume REAL NOT NULL,
    trade_count INTEGER NOT NULL,
    taker_buy_base REAL NOT NULL,
    taker_buy_quote REAL NOT NULL,
    PRIMARY KEY (symbol, interval, open_time)
)
"""


class CandleRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def ensure_schema(self) -> None:
        self.connection.execute(CANDLE_SCHEMA)
        self.connection.commit()

    def insert_many(self, candles: Iterable[Candle]) -> int:
        """Validate all rows, then insert idempotently in one transaction.

        Existing rows are never overwritten. Sparse but valid exchange
        responses are retained; continuity is audited separately and gaps
        are recorded in the gap registry rather than blocking ingestion.
        """
        batch = list(candles)
        if not batch:
            return 0
        for candle in batch:
            candle.validate()
        identity = {(c.symbol, c.interval) for c in batch}
        if len(identity) != 1:
            raise ValueError("one insert batch must contain one symbol and interval")
        keys = [(c.symbol, c.interval, c.open_time) for c in batch]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate candle timestamps inside input batch")
        batch.sort(key=lambda c: c.open_time)

        rows = [
            (
                c.symbol, c.interval, c.open_time, c.open, c.high, c.low,
                c.close, c.volume, c.close_time, c.quote_volume,
                c.trade_count, c.taker_buy_base, c.taker_buy_quote,
            )
            for c in batch
        ]
        before = self.connection.total_changes
        with self.connection:
            self.connection.executemany(
                """INSERT OR IGNORE INTO candles VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )""",
                rows,
            )
        return self.connection.total_changes - before

    def count(self, symbol: str, interval: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) FROM candles WHERE symbol=? AND interval=?",
            (symbol, interval),
        ).fetchone()
        return int(row[0])

    def open_times(self, symbol: str, interval: str) -> list[int]:
        rows = self.connection.execute(
            """SELECT open_time FROM candles
               WHERE symbol=? AND interval=? ORDER BY open_time""",
            (symbol, interval),
        ).fetchall()
        return [int(row[0]) for row in rows]
