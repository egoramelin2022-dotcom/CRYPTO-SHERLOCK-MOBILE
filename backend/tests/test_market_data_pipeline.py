from __future__ import annotations

import sqlite3

import pytest

from app.market_data.pipeline import run_historical_pipeline


def create_source(path):
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE candles (
        symbol TEXT, interval TEXT, open_time INTEGER, open REAL, high REAL,
        low REAL, close REAL, volume REAL, close_time INTEGER,
        quote_volume REAL, trade_count INTEGER, taker_buy_base REAL,
        taker_buy_quote REAL, PRIMARY KEY(symbol, interval, open_time)
    )""")
    rows = []
    for i, close in enumerate([100, 101, 102, 103, 104, 105, 106]):
        t = i * 900000
        rows.append(("BTCUSDT", "15m", t, close - .2, close + .8,
                     close - 1, close, 10, t + 899999, close * 10,
                     10, 6, close * 6))
    # A deliberate gap: pipeline must keep the second segment independent.
    for i, close in [(9, 90), (10, 91), (11, 92)]:
        t = i * 900000
        rows.append(("BTCUSDT", "15m", t, close - .2, close + .8,
                     close - 1, close, 10, t + 899999, close * 10,
                     10, 6, close * 6))
    conn.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_pipeline_reads_source_and_writes_separate_analytics(tmp_path):
    source = tmp_path / "source.db"
    output = tmp_path / "analytics.db"
    create_source(source)
    before = source.read_bytes()
    result = run_historical_pipeline(source, output, window=4)
    assert result.candles_read == 10
    assert result.features_written == 10
    assert result.regimes_written == 10
    assert result.segments == 2
    assert source.read_bytes() == before
    out = sqlite3.connect(output)
    try:
        assert out.execute("SELECT COUNT(*) FROM market_features").fetchone()[0] == 10
        assert out.execute("SELECT COUNT(*) FROM market_regimes").fetchone()[0] == 10
        assert out.execute("SELECT COUNT(*) FROM pattern_dataset").fetchone()[0] == 10
        # Last candle of the first segment has no forward label crossing the gap.
        row = out.execute(
            "SELECT forward_return_4 FROM pattern_dataset WHERE open_time=?",
            (6 * 900000,),
        ).fetchone()
        assert row[0] is None
    finally:
        out.close()


def test_pipeline_refuses_to_use_same_source_and_output_path(tmp_path):
    source = tmp_path / "source.db"
    create_source(source)
    with pytest.raises(ValueError, match="separate"):
        run_historical_pipeline(source, source)


def test_pipeline_source_is_opened_read_only(tmp_path):
    source = tmp_path / "source.db"
    create_source(source)
    with pytest.raises(sqlite3.OperationalError):
        conn = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        try:
            conn.execute("DELETE FROM candles")
            conn.commit()
        finally:
            conn.close()
