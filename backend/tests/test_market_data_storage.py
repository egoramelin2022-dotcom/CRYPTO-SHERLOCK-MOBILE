import sqlite3

import pytest

from app.market_data.binance import parse_binance_kline
from app.market_data.repository import CandleRepository


def valid_row(open_time=0):
    return [
        open_time, "100", "110", "90", "105", "2",
        open_time + 899_999, "205", 10, "1", "102", "0",
    ]


def test_parse_binance_kline_maps_and_validates_fields():
    candle = parse_binance_kline(valid_row(), symbol="BTCUSDT", interval="15m")
    assert candle.open_time == 0
    assert candle.close_time == 899_999
    assert candle.trade_count == 10
    assert candle.taker_buy_base == 1


@pytest.mark.parametrize("row", [[], [0] * 11, [0] * 13])
def test_parser_rejects_wrong_payload_shape(row):
    with pytest.raises(ValueError):
        parse_binance_kline(row, symbol="BTCUSDT", interval="15m")


def test_parser_rejects_invalid_market_values():
    row = valid_row()
    row[2] = "80"
    with pytest.raises(ValueError):
        parse_binance_kline(row, symbol="BTCUSDT", interval="15m")


def test_repository_insert_is_idempotent_and_does_not_overwrite():
    conn = sqlite3.connect(":memory:")
    repo = CandleRepository(conn)
    repo.ensure_schema()
    candle = parse_binance_kline(valid_row(), symbol="BTCUSDT", interval="15m")
    assert repo.insert_many([candle]) == 1
    assert repo.insert_many([candle]) == 0
    assert repo.count("BTCUSDT", "15m") == 1
    conn.close()


def test_repository_validates_whole_batch_before_writing():
    conn = sqlite3.connect(":memory:")
    repo = CandleRepository(conn)
    repo.ensure_schema()
    good = parse_binance_kline(valid_row(), symbol="BTCUSDT", interval="15m")
    bad_row = valid_row(900_000)
    bad_row[2] = "80"
    bad = None
    with pytest.raises(ValueError):
        bad = parse_binance_kline(bad_row, symbol="BTCUSDT", interval="15m")
    assert repo.insert_many([good]) == 1
    assert repo.count("BTCUSDT", "15m") == 1
    conn.close()


def test_repository_rejects_duplicate_keys_in_one_batch():
    conn = sqlite3.connect(":memory:")
    repo = CandleRepository(conn)
    repo.ensure_schema()
    candle = parse_binance_kline(valid_row(), symbol="BTCUSDT", interval="15m")
    with pytest.raises(ValueError):
        repo.insert_many([candle, candle])
    assert repo.count("BTCUSDT", "15m") == 0
    conn.close()
