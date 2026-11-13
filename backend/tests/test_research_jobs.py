import sqlite3

from app.market_data.candles import Candle
from app.market_data.repository import CandleRepository
from app.research import jobs


def build_candles(count=100):
    rows = []
    for i in range(count):
        op = 100.0 + i
        close = op + (1.0 if i % 2 else -1.0)
        rows.append(Candle(
            symbol="BTCUSDT", interval="15m", open_time=i * 900_000,
            open=op, high=max(op, close) + 1.0, low=min(op, close) - 1.0,
            close=close, volume=1.0, close_time=(i + 1) * 900_000 - 1,
            quote_volume=op, trade_count=1,
            taker_buy_base=0.5, taker_buy_quote=op * 0.5,
        ))
    return rows


def test_latest_contiguous_segment_does_not_bridge_gaps():
    rows = build_candles(100)
    # Remove one candle to split the series into two valid contiguous segments.
    rows = rows[:50] + rows[51:]
    latest, segment_count, excluded = jobs._latest_contiguous_segment(rows, "15m")
    assert segment_count == 2
    assert excluded == 50
    assert latest[0].open_time == 51 * 900_000
    assert latest[-1].open_time == 99 * 900_000


def test_ensemble_job_reads_source_only_and_persists_analytics(tmp_path, monkeypatch):
    source = tmp_path / "source.sqlite"
    analytics = tmp_path / "analytics" / "derived.sqlite"
    connection = sqlite3.connect(source)
    try:
        repository = CandleRepository(connection)
        repository.ensure_schema()
        repository.insert_many(build_candles())
    finally:
        connection.close()

    monkeypatch.setattr(jobs, "_configured_paths", lambda: (source, analytics))
    job = jobs.queue_ensemble()
    jobs.run_ensemble_job(
        job["job_id"], "BTCUSDT", "15m", 20,
        top_k=3, mode="free", include_stumpy=False,
    )
    completed = jobs.get_job(job["job_id"])
    assert completed["status"] == "completed"
    assert completed["result"]["source_candles_read"] == 100
    assert completed["result"]["closed_candles"] == 100
    assert completed["result"]["contiguous_segments"] == 1
    assert completed["result"]["run"]["symbol"] == "BTCUSDT"

    source_check = sqlite3.connect(source)
    try:
        tables = {
            row[0] for row in source_check.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert tables == {"candles"}
        assert source_check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        source_check.close()

    analytics_check = sqlite3.connect(analytics)
    try:
        row = analytics_check.execute(
            "SELECT symbol, interval, mode, include_stumpy, result_json "
            "FROM research_ensemble_runs"
        ).fetchone()
        assert row[:4] == ("BTCUSDT", "15m", "free", 0)
        assert '"interpretation"' in row[4]
    finally:
        analytics_check.close()
