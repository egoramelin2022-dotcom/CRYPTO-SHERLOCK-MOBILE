import sqlite3

import pytest

from app.market_data.candles import Candle, find_gaps
from app.market_data.gap_registry import record_gap
from app.market_data.intervals import expected_open_times, floor_to_interval, interval_to_ms


def test_fixed_interval_conversion_and_flooring():
    assert interval_to_ms("15m") == 900_000
    assert interval_to_ms("4h") == 14_400_000
    assert floor_to_interval(1_700_000_123_456, "15m") == 1_700_000_100_000


@pytest.mark.parametrize("value", ["0m", "15M", "1mo", "abc", "1.5h", ""])
def test_rejects_unsupported_intervals(value):
    with pytest.raises(ValueError):
        interval_to_ms(value)


def test_expected_open_times_requires_aligned_bounds():
    assert list(expected_open_times(0, 1_800_000, "15m")) == [0, 900_000, 1_800_000]
    with pytest.raises(ValueError):
        expected_open_times(1, 900_000, "15m")


def test_find_gaps_counts_missing_slots_and_rejects_unsorted_data():
    gaps = find_gaps([0, 900_000, 3_600_000], "15m")
    assert len(gaps) == 1
    assert gaps[0].missing_candles == 2
    with pytest.raises(ValueError):
        find_gaps([900_000, 0], "15m")


def test_candle_validation_checks_interval_and_ohlcv():
    candle = Candle("BTCUSDT", "15m", 0, 100, 110, 90, 105, 2, 899_999,
                    205, 10, 1, 102)
    candle.validate()
    invalid = Candle("BTCUSDT", "15m", 0, 100, 99, 90, 105, 2, 899_999,
                     205, 10, 1, 102)
    with pytest.raises(ValueError):
        invalid.validate()


@pytest.mark.parametrize("trade_count", [-1, True, "10", 1.5])
def test_candle_rejects_invalid_trade_count_types(trade_count):
    candle = Candle("BTCUSDT", "15m", 0, 100, 110, 90, 105, 2, 899_999,
                    205, trade_count, 1, 102)
    with pytest.raises(ValueError):
        candle.validate()


def test_gap_registry_upserts_source_observations():
    conn = sqlite3.connect(":memory:")
    record_gap(conn, symbol="BTCUSDT", interval="15m", previous_open_time=0,
               next_open_time=2_700_000, missing_candles=2,
               status="SOURCE_EMPTY", source="binance-rest")
    record_gap(conn, symbol="BTCUSDT", interval="15m", previous_open_time=0,
               next_open_time=2_700_000, missing_candles=2,
               status="UNRESOLVED", source="binance-rest", details="No rows returned")
    rows = conn.execute("SELECT status, source, details FROM data_gaps").fetchall()
    assert rows == [("UNRESOLVED", "binance-rest", "No rows returned")]
    conn.close()
