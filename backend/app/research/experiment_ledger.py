"""Append-only experiment ledger for reproducible Sherlock research runs.

The ledger lives in the separate analytics database. Market source databases
remain read-only. Run metadata, results and event history are immutable; state
changes are represented by hash-chained events rather than row updates.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import struct
from typing import Any, Sequence
from uuid import UUID

from app.market_data.candles import Candle

LEDGER_SCHEMA_VERSION = 1
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_TERMINAL = {"completed", "failed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


def fingerprint_candles(candles: Sequence[Candle]) -> str:
    """Stable SHA-256 over every canonical market-data field in input order."""
    digest = hashlib.sha256()
    if not candles:
        raise ValueError("cannot fingerprint an empty candle sequence")
    first = candles[0]
    digest.update(first.symbol.encode("ascii"))
    digest.update(b"\0")
    digest.update(first.interval.encode("ascii"))
    digest.update(b"\0")
    previous = None
    for candle in candles:
        candle.validate()
        if candle.symbol != first.symbol or candle.interval != first.interval:
            raise ValueError("fingerprint candles must share symbol and interval")
        if previous is not None and candle.open_time <= previous:
            raise ValueError("fingerprint candles must be strictly chronological")
        previous = candle.open_time
        digest.update(struct.pack(
            ">qqddddddqdd",
            candle.open_time, candle.close_time,
            float(candle.open), float(candle.high), float(candle.low),
            float(candle.close), float(candle.volume), float(candle.quote_volume),
            candle.trade_count, float(candle.taker_buy_base),
            float(candle.taker_buy_quote),
        ))
    return digest.hexdigest()


class ExperimentLedger:
    """SQLite append-only run ledger with verifiable event hash chains."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            already_initialized = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='experiment_runs'"
            ).fetchone() is not None
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS experiment_runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    core_version TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    query_start_time INTEGER NOT NULL,
                    query_end_time INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    input_fingerprint TEXT NOT NULL,
                    input_candle_count INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS experiment_results (
                    run_id TEXT PRIMARY KEY REFERENCES experiment_runs(run_id),
                    stored_at TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    result_sha256 TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS experiment_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES experiment_runs(run_id),
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL CHECK (
                        event_type IN ('started', 'completed', 'failed')
                    ),
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE,
                    UNIQUE(run_id, sequence)
                );

                CREATE INDEX IF NOT EXISTS idx_experiment_runs_created
                    ON experiment_runs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_experiment_runs_market
                    ON experiment_runs(symbol, interval, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_experiment_events_run
                    ON experiment_events(run_id, sequence);

            """)
            # Do not silently recreate missing guards on an existing ledger:
            # the integrity endpoint must be able to report their removal.
            if not already_initialized:
                connection.executescript("""
                    CREATE TRIGGER experiment_runs_no_update
                    BEFORE UPDATE ON experiment_runs
                    BEGIN SELECT RAISE(ABORT, 'experiment ledger is append-only'); END;
                    CREATE TRIGGER experiment_runs_no_delete
                    BEFORE DELETE ON experiment_runs
                    BEGIN SELECT RAISE(ABORT, 'experiment ledger is append-only'); END;
                    CREATE TRIGGER experiment_results_no_update
                    BEFORE UPDATE ON experiment_results
                    BEGIN SELECT RAISE(ABORT, 'experiment ledger is append-only'); END;
                    CREATE TRIGGER experiment_results_no_delete
                    BEFORE DELETE ON experiment_results
                    BEGIN SELECT RAISE(ABORT, 'experiment ledger is append-only'); END;
                    CREATE TRIGGER experiment_events_no_update
                    BEFORE UPDATE ON experiment_events
                    BEGIN SELECT RAISE(ABORT, 'experiment ledger is append-only'); END;
                    CREATE TRIGGER experiment_events_no_delete
                    BEFORE DELETE ON experiment_events
                    BEGIN SELECT RAISE(ABORT, 'experiment ledger is append-only'); END;
                """)

    @staticmethod
    def _event_hash(
        run_id: str, sequence: int, event_type: str, occurred_at: str,
        payload_json: str, previous_hash: str,
    ) -> str:
        body = _canonical_json({
            "run_id": run_id, "sequence": sequence, "event_type": event_type,
            "occurred_at": occurred_at, "payload_json": payload_json,
            "previous_hash": previous_hash,
        })
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def _append_event(
        self, connection: sqlite3.Connection, run_id: str,
        event_type: str, payload: dict[str, Any],
    ) -> str:
        latest = connection.execute(
            """SELECT sequence, event_type, event_hash
               FROM experiment_events WHERE run_id=?
               ORDER BY sequence DESC LIMIT 1""",
            (run_id,),
        ).fetchone()
        if latest is None:
            if event_type != "started":
                raise ValueError("first experiment event must be started")
            sequence, previous_hash = 1, "0" * 64
        else:
            if latest["event_type"] != "started" or event_type not in _ALLOWED_TERMINAL:
                raise ValueError("experiment already has a terminal event")
            sequence = int(latest["sequence"]) + 1
            previous_hash = str(latest["event_hash"])
        occurred_at = _now()
        payload_json = _canonical_json(payload)
        event_hash = self._event_hash(
            run_id, sequence, event_type, occurred_at, payload_json, previous_hash
        )
        connection.execute(
            """INSERT INTO experiment_events
               (run_id, sequence, event_type, occurred_at, payload_json,
                previous_hash, event_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, sequence, event_type, occurred_at, payload_json,
             previous_hash, event_hash),
        )
        return event_hash

    def start_run(
        self, *, run_id: str, core_version: str, symbol: str, interval: str,
        query_start_time: int, query_end_time: int, mode: str,
        parameters: dict[str, Any], input_fingerprint: str,
        input_candle_count: int,
    ) -> dict[str, Any]:
        try:
            UUID(run_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("run_id must be a UUID") from exc
        if not _FINGERPRINT_RE.fullmatch(input_fingerprint):
            raise ValueError("input_fingerprint must be a lowercase SHA-256 hex digest")
        if (isinstance(input_candle_count, bool) or not isinstance(input_candle_count, int)
                or input_candle_count < 1):
            raise ValueError("input_candle_count must be a positive integer")
        if (isinstance(query_start_time, bool) or not isinstance(query_start_time, int)
                or isinstance(query_end_time, bool) or not isinstance(query_end_time, int)
                or query_start_time > query_end_time):
            raise ValueError("query time range is invalid")
        parameters_json = _canonical_json(parameters)
        created_at = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO experiment_runs
                   (run_id, created_at, schema_version, core_version, symbol,
                    interval, query_start_time, query_end_time, mode,
                    parameters_json, input_fingerprint, input_candle_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, created_at, LEDGER_SCHEMA_VERSION, core_version, symbol,
                 interval, query_start_time, query_end_time, mode, parameters_json,
                 input_fingerprint, input_candle_count),
            )
            self._append_event(connection, run_id, "started", {
                "input_fingerprint": input_fingerprint,
                "input_candle_count": input_candle_count,
            })
        return {"run_id": run_id, "status": "started", "created_at": created_at}

    def complete_run(self, run_id: str, result: dict[str, Any]) -> dict[str, Any]:
        if result.get("run_id") != run_id:
            raise ValueError("result run_id does not match ledger run_id")
        result_json = _canonical_json(result)
        result_hash = hashlib.sha256(result_json.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO experiment_results
                   (run_id, stored_at, result_json, result_sha256)
                   VALUES (?, ?, ?, ?)""",
                (run_id, _now(), result_json, result_hash),
            )
            event_hash = self._append_event(connection, run_id, "completed", {
                "result_sha256": result_hash,
                "research_status": result.get("research_status"),
                "abstain": result.get("decision", {}).get("abstain", True),
            })
        return {"run_id": run_id, "status": "completed", "result_sha256": result_hash,
                "event_hash": event_hash}

    def fail_run(self, run_id: str, error_type: str) -> dict[str, Any]:
        candidate = str(error_type).split(":", 1)[0].strip()
        safe_type = candidate if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,79}", candidate) else "ResearchError"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            event_hash = self._append_event(
                connection, run_id, "failed", {"error_type": safe_type}
            )
        return {"run_id": run_id, "status": "failed", "event_hash": event_hash}

    def list_runs(
        self, *, limit: int = 50, offset: int = 0,
        symbol: str | None = None, interval: str | None = None,
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit must be an integer in [1, 200]")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a nonnegative integer")
        clauses, values = [], []
        if symbol is not None:
            clauses.append("r.symbol=?")
            values.append(symbol)
        if interval is not None:
            clauses.append("r.interval=?")
            values.append(interval)
        values.extend([limit, offset])
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT r.*, e.event_type AS status, e.occurred_at AS status_at,
                           json_extract(e.payload_json, '$.result_sha256') AS result_sha256
                    FROM experiment_runs r
                    JOIN experiment_events e ON e.run_id=r.run_id
                    WHERE e.sequence=(SELECT MAX(x.sequence) FROM experiment_events x
                                      WHERE x.run_id=r.run_id)
                    {('AND ' + ' AND '.join(clauses)) if clauses else ''}
                    ORDER BY r.created_at DESC, r.rowid DESC LIMIT ? OFFSET ?""",
                values,
            ).fetchall()
        return [{
            "run_id": row["run_id"], "created_at": row["created_at"],
            "core_version": row["core_version"], "symbol": row["symbol"],
            "interval": row["interval"], "query_start_time": row["query_start_time"],
            "query_end_time": row["query_end_time"], "mode": row["mode"],
            "input_fingerprint": row["input_fingerprint"],
            "input_candle_count": row["input_candle_count"],
            "status": row["status"], "status_at": row["status_at"],
            "result_sha256": row["result_sha256"],
        } for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            run = connection.execute(
                "SELECT * FROM experiment_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if run is None:
                return None
            result = connection.execute(
                "SELECT result_json, result_sha256 FROM experiment_results WHERE run_id=?",
                (run_id,),
            ).fetchone()
            events = connection.execute(
                """SELECT sequence, event_type, occurred_at, payload_json,
                          previous_hash, event_hash FROM experiment_events
                   WHERE run_id=? ORDER BY sequence""",
                (run_id,),
            ).fetchall()
        return {
            "run": {
                key: run[key] for key in run.keys()
                if key != "parameters_json"
            } | {"parameters": json.loads(run["parameters_json"])},
            "result": json.loads(result["result_json"]) if result else None,
            "result_sha256": result["result_sha256"] if result else None,
            "events": [{
                "sequence": row["sequence"], "event_type": row["event_type"],
                "occurred_at": row["occurred_at"],
                "payload": json.loads(row["payload_json"]),
                "previous_hash": row["previous_hash"], "event_hash": row["event_hash"],
            } for row in events],
        }

    def verify_integrity(self) -> dict[str, Any]:
        issues: list[str] = []
        checked_events = checked_results = 0
        with self._connect() as connection:
            quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
            if quick_check != "ok":
                issues.append(f"SQLite quick_check failed: {quick_check}")
            foreign_key_issues = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_issues:
                issues.append(f"SQLite foreign_key_check found {len(foreign_key_issues)} issue(s)")
            required_triggers = {
                "experiment_runs_no_update", "experiment_runs_no_delete",
                "experiment_results_no_update", "experiment_results_no_delete",
                "experiment_events_no_update", "experiment_events_no_delete",
            }
            existing_triggers = {
                row["name"] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                ).fetchall()
            }
            missing_triggers = sorted(required_triggers - existing_triggers)
            if missing_triggers:
                issues.append("Missing append-only trigger(s): " + ", ".join(missing_triggers))
            runs = connection.execute(
                "SELECT run_id FROM experiment_runs ORDER BY created_at, run_id"
            ).fetchall()
            for item in runs:
                run_id = item["run_id"]
                events = connection.execute(
                    """SELECT sequence, event_type, occurred_at, payload_json,
                              previous_hash, event_hash FROM experiment_events
                       WHERE run_id=? ORDER BY sequence""",
                    (run_id,),
                ).fetchall()
                previous = "0" * 64
                for expected_sequence, row in enumerate(events, start=1):
                    checked_events += 1
                    if row["sequence"] != expected_sequence:
                        issues.append(f"{run_id}: event sequence discontinuity")
                    if row["previous_hash"] != previous:
                        issues.append(f"{run_id}: previous event hash mismatch")
                    expected_hash = self._event_hash(
                        run_id, row["sequence"], row["event_type"], row["occurred_at"],
                        row["payload_json"], row["previous_hash"],
                    )
                    if row["event_hash"] != expected_hash:
                        issues.append(f"{run_id}: event hash mismatch")
                    previous = row["event_hash"]
                if not events or events[0]["event_type"] != "started":
                    issues.append(f"{run_id}: missing initial started event")
                if len(events) > 2 or (len(events) == 2 and events[1]["event_type"] not in _ALLOWED_TERMINAL):
                    issues.append(f"{run_id}: invalid event transition")
                result = connection.execute(
                    "SELECT result_json, result_sha256 FROM experiment_results WHERE run_id=?",
                    (run_id,),
                ).fetchone()
                if result is not None:
                    checked_results += 1
                    actual = hashlib.sha256(result["result_json"].encode("utf-8")).hexdigest()
                    if actual != result["result_sha256"]:
                        issues.append(f"{run_id}: result hash mismatch")
                terminal = events[-1]["event_type"] if events else None
                if terminal == "completed" and result is None:
                    issues.append(f"{run_id}: completed event has no result")
                if terminal != "completed" and result is not None:
                    issues.append(f"{run_id}: result exists without completed event")
                if terminal == "completed" and result is not None and events:
                    try:
                        completed_payload = json.loads(events[-1]["payload_json"])
                    except (TypeError, ValueError):
                        issues.append(f"{run_id}: completed event payload is not valid JSON")
                    else:
                        if completed_payload.get("result_sha256") != result["result_sha256"]:
                            issues.append(f"{run_id}: completed event result hash mismatch")
                    try:
                        stored_result = json.loads(result["result_json"])
                    except (TypeError, ValueError):
                        issues.append(f"{run_id}: stored result is not valid JSON")
                    else:
                        if stored_result.get("run_id") != run_id:
                            issues.append(f"{run_id}: stored result run_id mismatch")
        return {
            "ok": not issues, "runs_checked": len(runs),
            "events_checked": checked_events, "results_checked": checked_results,
            "issues": issues,
        }
