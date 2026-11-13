import sqlite3

from app.market_data.candles import Candle
from app.market_data.repository import CandleRepository
from app.research.desktop_services import run_pattern_research, run_ensemble_research, _load_candles


def make_candles(count=120):
    rows = []
    for i in range(count):
        price = 100 + (i % 11) * 0.2 + (i // 11) * 0.05
        open_time = i * 900_000
        rows.append(Candle(
            symbol="BTCUSDT", interval="15m", open_time=open_time,
            open=price, high=price * 1.002, low=price * 0.998,
            close=price * (1.0005 if i % 2 else 0.9995),
            volume=10.0, close_time=open_time + 899_999,
            quote_volume=price * 10, trade_count=10,
            taker_buy_base=5.0, taker_buy_quote=price * 5,
        ))
    return rows


def configure_db(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    analytics = tmp_path / "analytics.db"
    connection = sqlite3.connect(source)
    repository = CandleRepository(connection)
    repository.ensure_schema()
    repository.insert_many(make_candles())
    connection.close()
    monkeypatch.setenv("SHERLOCK_SOURCE_DB", str(source))
    monkeypatch.setenv("SHERLOCK_ANALYTICS_DB", str(analytics))


def test_desktop_pattern_research_uses_local_verified_history(tmp_path, monkeypatch):
    configure_db(tmp_path, monkeypatch)
    result = run_pattern_research(
        query_window=10, top_k=3, history_limit=120, mode="free"
    )
    assert result["symbol"] == "BTCUSDT"
    assert result["history_candles"] == 120
    assert result["query_window"] == 10
    assert len(result["query_chart"]["normalized_close"]) == 10
    assert result["analogs"]
    assert all(len(item["chart"]["normalized_close"]) == 10 for item in result["analogs"])
    assert all(
        item["analog"]["end_time"] < result["query_start_time"]
        for item in result["analogs"]
    )
    assert "not a forecast" in result["interpretation"]


def test_ensemble_reports_optional_engine_availability(tmp_path, monkeypatch):
    configure_db(tmp_path, monkeypatch)
    result = run_ensemble_research(query_window=10, top_k=3)
    assert "pattern_intelligence" in result["engines_available"]
    assert "evidence_report" in result
    assert "not a probability" in result["interpretation"]



def test_verified_archive_staging_is_merged_with_source_without_duplicates(tmp_path, monkeypatch):
    rows = make_candles(120)
    source = tmp_path / "source.db"
    staging = tmp_path / "staging.db"
    analytics = tmp_path / "analytics.db"

    for path, selected in ((source, rows[60:]), (staging, rows[:80])):
        connection = sqlite3.connect(path)
        repository = CandleRepository(connection)
        repository.ensure_schema()
        repository.insert_many(selected)
        connection.close()

    monkeypatch.setenv("SHERLOCK_SOURCE_DB", str(source))
    monkeypatch.setenv("SHERLOCK_ANALYTICS_DB", str(analytics))
    monkeypatch.setenv("SHERLOCK_ARCHIVE_STAGING_DB", str(staging))

    candles, sources = _load_candles("BTCUSDT", "15m", 200)
    assert len(candles) == 120
    assert [item.open_time for item in candles] == [item.open_time for item in rows]
    assert sources == ["source", "archive_staging"]
