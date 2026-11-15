import sqlite3

import pytest

from app.research.data_foundation import audit_sqlite_dataset


def make_db(path):
    connection = sqlite3.connect(path)
    connection.execute("""CREATE TABLE candles (
        symbol TEXT NOT NULL, interval TEXT NOT NULL, open_time INTEGER NOT NULL,
        open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
        volume REAL NOT NULL, close_time INTEGER NOT NULL, quote_volume REAL NOT NULL,
        trade_count INTEGER NOT NULL, taker_buy_base REAL NOT NULL,
        taker_buy_quote REAL NOT NULL,
        PRIMARY KEY(symbol, interval, open_time))""")
    rows = [
        ("BTCUSDT", "15m", 0, 100, 102, 99, 101, 10, 899999, 1005, 5, 6, 6030),
        ("BTCUSDT", "15m", 900000, 101, 103, 100, 102, 11, 1799999, 1122, 6, 7, 714),
        ("BTCUSDT", "15m", 2700000, 102, 104, 101, 103, 12, 3599999, 1236, 7, 8, 824),
    ]
    connection.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    connection.commit()
    connection.close()


def test_audit_is_read_only_and_reports_gaps(tmp_path):
    db = tmp_path / "market.db"
    make_db(db)
    before = db.read_bytes()
    report = audit_sqlite_dataset(db)
    after = db.read_bytes()
    assert before == after
    assert report["source"]["read_only"] is True
    item = report["datasets"][0]
    assert item["rows"] == 3
    assert item["gap_count"] == 1
    assert item["missing_candles"] == 1
    assert item["malformed_rows"] == 0
    assert report["integrity_check"] == ["ok"]
    assert report["integrity_ok"] is True


def test_audit_rejects_missing_database_and_table(tmp_path):
    with pytest.raises(FileNotFoundError):
        audit_sqlite_dataset(tmp_path / "missing.db")
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    with pytest.raises(ValueError, match="table not found"):
        audit_sqlite_dataset(db)


def test_audit_reports_off_grid_timestamps_instead_of_crashing(tmp_path):
    db = tmp_path / "off_grid.db"
    connection = sqlite3.connect(db)
    connection.execute("""CREATE TABLE candles (
        symbol TEXT, interval TEXT, open_time INTEGER, open REAL, high REAL,
        low REAL, close REAL, volume REAL, close_time INTEGER,
        quote_volume REAL, trade_count INTEGER, taker_buy_base REAL,
        taker_buy_quote REAL)""")
    connection.execute(
        "INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("BTCUSDT", "15m", 1, 100, 102, 99, 101, 10, 900000, 1005, 5, 6, 6030),
    )
    connection.commit()
    connection.close()

    report = audit_sqlite_dataset(db)
    item = report["datasets"][0]
    assert item["rows"] == 1
    assert item["invalid_timestamp_rows"] == 1
    assert item["malformed_rows"] == 1
    assert item["gap_count"] == 0
