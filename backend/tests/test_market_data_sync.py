from __future__ import annotations

import sqlite3

import httpx
import pytest

from app.market_data.sync import HistoricalSyncEngine


def kline(open_time: int, close: float = 100.0) -> list:
    return [
        open_time, "99", "101", "98", str(close), "10",
        open_time + 899999, "999", 12, "4", "399", "0",
    ]


def make_engine(conn: sqlite3.Connection, handler, *, sleeps=None):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HistoricalSyncEngine(
        conn, client=client, max_attempts=3, backoff_base_seconds=0,
        backoff_cap_seconds=0, sleep=(sleeps.append if sleeps is not None else lambda _: None),
        jitter=lambda: 0,
    ), client


def test_sync_downloads_multiple_pages_and_checkpoints_complete():
    conn = sqlite3.connect(":memory:")
    start = 0
    step = 900000
    calls = []

    def handler(request: httpx.Request):
        cursor = int(request.url.params["startTime"])
        calls.append(cursor)
        if cursor == start:
            return httpx.Response(200, json=[kline(start), kline(start + step)], request=request)
        return httpx.Response(200, json=[kline(start + 2 * step)], request=request)

    engine, client = make_engine(conn, handler)
    try:
        result = engine.sync(
            symbol="BTCUSDT", interval="15m", start_ms=start,
            end_ms=start + 2 * step, page_limit=2,
        )
        assert result.status == "COMPLETE"
        assert (result.fetched, result.inserted, result.pages) == (3, 3, 2)
        assert calls == [start, start + 2 * step]
        assert engine.repository.count("BTCUSDT", "15m") == 3
        job = conn.execute("SELECT status, next_start_ms FROM sync_jobs").fetchone()
        assert job == ("COMPLETE", start + 3 * step)
    finally:
        engine.close()
        client.close()
        conn.close()


def test_empty_source_page_is_not_reported_as_complete_and_can_resume():
    conn = sqlite3.connect(":memory:")
    start = 0
    step = 900000
    state = {"empty": True}

    def handler(request: httpx.Request):
        cursor = int(request.url.params["startTime"])
        if cursor == start:
            return httpx.Response(200, json=[kline(start)], request=request)
        if state["empty"]:
            return httpx.Response(200, json=[], request=request)
        return httpx.Response(200, json=[kline(start + step)], request=request)

    engine, client = make_engine(conn, handler)
    try:
        first = engine.sync(
            symbol="BTCUSDT", interval="15m", start_ms=start,
            end_ms=start + step,
        )
        assert first.status == "SOURCE_EMPTY"
        assert first.next_start_ms == start + step
        state["empty"] = False
        second = engine.sync(
            symbol="BTCUSDT", interval="15m", start_ms=start,
            end_ms=start + step,
        )
        assert second.status == "COMPLETE"
        assert second.fetched == 2
        assert second.inserted == 2  # cumulative inserts across the resumed job
        assert engine.repository.count("BTCUSDT", "15m") == 2
        gap_status = conn.execute("SELECT status FROM data_gaps").fetchone()[0]
        assert gap_status == "RECOVERED"
    finally:
        engine.close()
        client.close()
        conn.close()


def test_transient_server_error_is_retried():
    conn = sqlite3.connect(":memory:")
    step = 900000
    attempts = {"count": 0}

    def handler(request: httpx.Request):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json=[kline(0)], request=request)

    engine, client = make_engine(conn, handler)
    try:
        result = engine.sync(
            symbol="BTCUSDT", interval="15m", start_ms=0, end_ms=0,
        )
        assert result.status == "COMPLETE"
        assert attempts["count"] == 2
    finally:
        engine.close()
        client.close()
        conn.close()


def test_bad_page_is_not_persisted_and_job_is_failed():
    conn = sqlite3.connect(":memory:")
    step = 900000

    def handler(request: httpx.Request):
        return httpx.Response(200, json=[kline(0), kline(0)], request=request)

    engine, client = make_engine(conn, handler)
    try:
        with pytest.raises(ValueError, match="strictly increasing"):
            engine.sync(
                symbol="BTCUSDT", interval="15m", start_ms=0, end_ms=step,
            )
        assert engine.repository.count("BTCUSDT", "15m") == 0
        assert conn.execute("SELECT status FROM sync_jobs").fetchone()[0] == "FAILED"
    finally:
        engine.close()
        client.close()
        conn.close()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_ms": -1, "end_ms": 0},
        {"start_ms": 1, "end_ms": 900000},
        {"start_ms": 900000, "end_ms": 0},
        {"start_ms": 0, "end_ms": 0, "page_limit": 1001},
    ],
)
def test_sync_rejects_invalid_ranges_before_network(kwargs):
    conn = sqlite3.connect(":memory:")
    requests = {"count": 0}

    def handler(request: httpx.Request):
        requests["count"] += 1
        return httpx.Response(200, json=[], request=request)

    engine, client = make_engine(conn, handler)
    args = {"symbol": "BTCUSDT", "interval": "15m", "start_ms": 0, "end_ms": 0}
    args.update(kwargs)
    try:
        with pytest.raises(ValueError):
            engine.sync(**args)
        assert requests["count"] == 0
    finally:
        engine.close()
        client.close()
        conn.close()

def test_completed_job_is_idempotent_and_does_not_call_exchange_again():
    conn = sqlite3.connect(":memory:")
    requests = {"count": 0}

    def handler(request: httpx.Request):
        requests["count"] += 1
        return httpx.Response(200, json=[kline(0)], request=request)

    engine, client = make_engine(conn, handler)
    try:
        first = engine.sync(
            symbol="BTCUSDT", interval="15m", start_ms=0, end_ms=0,
        )
        second = engine.sync(
            symbol="BTCUSDT", interval="15m", start_ms=0, end_ms=0,
        )
        assert first == second
        assert requests["count"] == 1
        assert engine.repository.count("BTCUSDT", "15m") == 1
    finally:
        engine.close()
        client.close()
        conn.close()

def test_restart_after_candle_commit_before_checkpoint_is_safe():
    conn = sqlite3.connect(":memory:")
    step = 900000

    def handler(request: httpx.Request):
        return httpx.Response(
            200, json=[kline(0), kline(step)], request=request
        )

    engine, client = make_engine(conn, handler)
    original_checkpoint = engine._checkpoint

    class SimulatedProcessCrash(BaseException):
        pass

    def crash_after_candle_commit(
        symbol, interval, start_ms, end_ms, next_start_ms, status,
        fetched, inserted, pages, error=None,
    ):
        # Simulate abrupt process death after candle INSERT committed,
        # but before the advanced cursor can be persisted.
        if status == "RUNNING" and next_start_ms == 2 * step:
            raise SimulatedProcessCrash()
        return original_checkpoint(
            symbol, interval, start_ms, end_ms, next_start_ms, status,
            fetched, inserted, pages, error,
        )

    engine._checkpoint = crash_after_candle_commit
    try:
        with pytest.raises(SimulatedProcessCrash):
            engine.sync(
                symbol="BTCUSDT", interval="15m", start_ms=0, end_ms=step,
                page_limit=2,
            )
        assert engine.repository.count("BTCUSDT", "15m") == 2
        # The durable checkpoint still points to the original page.
        job = conn.execute(
            "SELECT status, next_start_ms FROM sync_jobs"
        ).fetchone()
        assert job == ("RUNNING", 0)

        engine._checkpoint = original_checkpoint
        resumed = engine.sync(
            symbol="BTCUSDT", interval="15m", start_ms=0, end_ms=step,
            page_limit=2,
        )
        assert resumed.status == "COMPLETE"
        assert resumed.inserted == 0
        assert engine.repository.count("BTCUSDT", "15m") == 2
    finally:
        engine.close()
        client.close()
        conn.close()

def test_sparse_page_is_ingested_but_marked_partial_with_gap_registry():
    conn = sqlite3.connect(":memory:")
    step = 900000

    def handler(request: httpx.Request):
        return httpx.Response(
            200, json=[kline(0), kline(2 * step)], request=request
        )

    engine, client = make_engine(conn, handler)
    try:
        result = engine.sync(
            symbol="BTCUSDT", interval="15m", start_ms=0,
            end_ms=2 * step,
        )
        assert result.status == "PARTIAL"
        assert engine.repository.count("BTCUSDT", "15m") == 2
        gaps = conn.execute(
            """SELECT previous_open_time, next_open_time, missing_candles,
                      status, source
               FROM data_gaps"""
        ).fetchall()
        assert gaps == [(0, 2 * step, 1, "GAP_DETECTED", "BINANCE_SPOT_REST")]
        job_status = conn.execute("SELECT status FROM sync_jobs").fetchone()[0]
        assert job_status == "PARTIAL"
    finally:
        engine.close()
        client.close()
        conn.close()
