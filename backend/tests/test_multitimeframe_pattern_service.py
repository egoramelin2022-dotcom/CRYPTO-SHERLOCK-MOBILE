import math
import sqlite3

from app.market_data.candles import Candle
from app.research import desktop_services
from app.research.experiment_ledger import ExperimentLedger


STEPS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def make_series(interval, count):
    step = STEPS[interval]
    rows = []
    previous = 100.0
    for index in range(count):
        open_time = index * step
        close = 100.0 + 0.015 * index + 1.8 * math.sin(index / 7.0)
        op = previous
        high = max(op, close) + 0.35
        low = min(op, close) - 0.35
        volume = 100.0 + (index % 17) * 2.0
        rows.append(Candle(
            symbol="BTCUSDT", interval=interval, open_time=open_time,
            open=op, high=high, low=low, close=close, volume=volume,
            close_time=open_time + step - 1, quote_volume=volume * close,
            trade_count=100 + index % 13, taker_buy_base=volume * 0.52,
            taker_buy_quote=volume * close * 0.52,
        ))
        previous = close
    return rows


def test_multitimeframe_service_persists_complete_run_in_append_only_ledger(
    tmp_path, monkeypatch
):
    series = {
        "15m": make_series("15m", 2200),
        "1h": make_series("1h", 550),
        "4h": make_series("4h", 138),
        "1d": make_series("1d", 23),
    }
    source = tmp_path / "source.db"
    sqlite3.connect(source).close()
    analytics = tmp_path / "analytics.db"

    monkeypatch.setattr(
        desktop_services.base_jobs, "_configured_paths",
        lambda: (source, analytics),
    )
    monkeypatch.setattr(
        desktop_services, "_load_candles",
        lambda symbol, interval, limit: (series[interval], ["source"]),
    )

    result = desktop_services.run_multitimeframe_pattern_research(
        symbol="BTCUSDT",
        query_window_15m=32,
        top_k=2,
        candidate_budget=100,
    )

    assert result["engine"] == "multitimeframe_pattern_intelligence"
    assert result["run_id"] == result["experiment_ledger"]["run_id"]
    assert result["experiment_ledger"]["append_only"] is True
    assert set(result["data_fingerprints"]) == {"15m", "1h", "4h", "1d"}

    ledger = ExperimentLedger(analytics)
    runs = ledger.list_runs(limit=10)
    assert len(runs) == 1
    assert runs[0]["run_id"] == result["run_id"]
    assert runs[0]["status"] == "completed"
    assert ledger.verify_integrity()["ok"] is True
