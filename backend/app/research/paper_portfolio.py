"""Persistent virtual spot portfolio. This module never sends exchange orders."""
from __future__ import annotations

import math
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

_lock = Lock()
DEFAULT_INITIAL_CASH = float(os.getenv("SHERLOCK_PAPER_INITIAL_CASH", "10000"))
FEE_BPS = float(os.getenv("SHERLOCK_PAPER_FEE_BPS", "10"))
SLIPPAGE_BPS = float(os.getenv("SHERLOCK_PAPER_SLIPPAGE_BPS", "5"))


def _db_path() -> Path:
    value = os.getenv("SHERLOCK_ANALYTICS_DB")
    if not value:
        raise RuntimeError("SHERLOCK_ANALYTICS_DB is not configured")
    path = Path(value).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_db_path(), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=15000")
    return connection


def _ensure(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS paper_account (
            account_id TEXT PRIMARY KEY,
            initial_cash REAL NOT NULL,
            cash REAL NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS paper_positions (
            symbol TEXT PRIMARY KEY,
            quantity REAL NOT NULL,
            average_entry REAL NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS paper_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            fill_price REAL NOT NULL,
            fee REAL NOT NULL,
            realized_pnl REAL NOT NULL,
            cash_after REAL NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    connection.execute(
        "INSERT OR IGNORE INTO paper_account VALUES ('default', ?, ?, ?)",
        (DEFAULT_INITIAL_CASH, DEFAULT_INITIAL_CASH, datetime.now(timezone.utc).isoformat()),
    )


def place_virtual_order(symbol: str, side: str, quantity: float, market_price: float) -> dict[str, Any]:
    """Execute a simulated spot BUY/SELL against virtual cash and inventory."""
    if side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    if (not isinstance(quantity, (int, float)) or isinstance(quantity, bool)
            or not math.isfinite(quantity) or quantity <= 0):
        raise ValueError("quantity must be finite and positive")
    if (not isinstance(market_price, (int, float)) or isinstance(market_price, bool)
            or not math.isfinite(market_price) or market_price <= 0):
        raise ValueError("market price must be finite and positive")
    if not (0 <= FEE_BPS < 10000 and 0 <= SLIPPAGE_BPS < 10000):
        raise RuntimeError("paper fee/slippage configuration is invalid")
    direction = 1 if side == "BUY" else -1
    fill = float(market_price) * (1 + direction * SLIPPAGE_BPS / 10000)
    fee = fill * float(quantity) * FEE_BPS / 10000
    now = datetime.now(timezone.utc).isoformat()

    with _lock:
        with closing(_connect()) as connection:
            with connection:
                _ensure(connection)
                connection.commit()
                connection.execute("BEGIN IMMEDIATE")
                account = connection.execute(
                    "SELECT * FROM paper_account WHERE account_id='default'"
                ).fetchone()
                cash = float(account["cash"])
                position = connection.execute(
                    "SELECT * FROM paper_positions WHERE symbol=?", (symbol,)
                ).fetchone()
                realized = 0.0
                if side == "BUY":
                    total_cost = fill * quantity + fee
                    if total_cost > cash:
                        raise ValueError("insufficient virtual cash")
                    old_qty = float(position["quantity"]) if position else 0.0
                    old_entry = float(position["average_entry"]) if position else 0.0
                    new_qty = old_qty + quantity
                    average = ((old_qty * old_entry) + (quantity * fill + fee)) / new_qty
                    connection.execute(
                        """INSERT INTO paper_positions VALUES (?, ?, ?, ?)
                           ON CONFLICT(symbol) DO UPDATE SET quantity=excluded.quantity,
                           average_entry=excluded.average_entry, updated_at=excluded.updated_at""",
                        (symbol, new_qty, average, now),
                    )
                    cash -= total_cost
                else:
                    if position is None or quantity > float(position["quantity"]) + 1e-12:
                        raise ValueError("sell quantity exceeds virtual position")
                    old_qty = float(position["quantity"])
                    average = float(position["average_entry"])
                    proceeds = fill * quantity - fee
                    realized = (fill - average) * quantity - fee
                    cash += proceeds
                    remaining = old_qty - quantity
                    if remaining <= 1e-12:
                        connection.execute("DELETE FROM paper_positions WHERE symbol=?", (symbol,))
                    else:
                        connection.execute(
                            "UPDATE paper_positions SET quantity=?, updated_at=? WHERE symbol=?",
                            (remaining, now, symbol),
                        )
                connection.execute(
                    "UPDATE paper_account SET cash=? WHERE account_id='default'", (cash,)
                )
                connection.execute(
                    """INSERT INTO paper_events
                       (symbol, side, quantity, fill_price, fee, realized_pnl, cash_after, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (symbol, side, quantity, fill, fee, realized, cash, now),
                )
                return {
                    "mode": "PAPER_ONLY", "symbol": symbol, "side": side,
                    "quantity": float(quantity), "market_price": float(market_price),
                    "fill_price": fill, "fee": fee, "realized_pnl": realized,
                    "cash_after": cash, "created_at": now,
                    "execution": "simulated locally; no exchange order was submitted",
                }


def portfolio_snapshot(marks: dict[str, float] | None = None) -> dict[str, Any]:
    marks = marks or {}
    with _lock:
        with closing(_connect()) as connection:
            _ensure(connection)
            connection.commit()
            account = connection.execute(
                "SELECT * FROM paper_account WHERE account_id='default'"
            ).fetchone()
            positions = connection.execute(
                "SELECT * FROM paper_positions ORDER BY symbol"
            ).fetchall()
            events = connection.execute(
                "SELECT * FROM paper_events ORDER BY event_id DESC LIMIT 20"
            ).fetchall()
            account_data = dict(account)
            position_rows = [dict(row) for row in positions]
            event_rows = [dict(row) for row in events]

    items = []
    equity = float(account_data["cash"])
    for row in position_rows:
        symbol = row["symbol"]
        mark = float(marks.get(symbol, row["average_entry"]))
        quantity = float(row["quantity"])
        value = mark * quantity
        unrealized = (mark - float(row["average_entry"])) * quantity
        equity += value
        items.append({
            "symbol": symbol, "quantity": quantity,
            "average_entry": float(row["average_entry"]),
            "mark_price": mark,
            "mark_source": "public_spot" if symbol in marks else "average_entry_fallback",
            "market_value": value, "unrealized_pnl": unrealized,
        })
    return {
        "mode": "PAPER_ONLY",
        "initial_cash": float(account_data["initial_cash"]),
        "cash": float(account_data["cash"]),
        "equity": equity,
        "positions": items,
        "recent_events": event_rows,
        "disclaimer": "Virtual spot ledger only; marks default to average entry unless live public prices are supplied.",
    }
