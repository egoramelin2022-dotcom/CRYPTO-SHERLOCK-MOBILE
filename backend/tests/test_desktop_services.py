import sqlite3

from app.market_data.candles import Candle
from app.market_data.repository import CandleRepository
from app.research.desktop_services import run_pattern_research, run_ensemble_research, run_walk_forward_research, run_intelligence_core_research, _load_candles, _split_contiguous
from app.research.experiment_ledger import ExperimentLedger


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
    assert result["data_freshness"]["is_stale"] is True
    assert result["data_freshness"]["age_hours"] > 0
    assert result["data_freshness"]["stale_after_hours"] == 0.75
    assert result["query_window"] == 10
    assert result["forward_return_basis"] == "candidate_end_close_to_future_close"
    assert result["forward_path_basis"] == "next_candle_open_to_horizon_close_with_fees_and_slippage"
    assert result["execution_assumptions"]["fee_bps_per_side"] == 5.0
    assert result["execution_assumptions"]["slippage_bps_per_side"] == 2.0
    assert result["execution_assumptions"]["costs_charged_on"] == ["entry", "exit"]
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



def test_verified_history_is_retained_before_gaps(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    analytics = tmp_path / "analytics.db"
    rows = make_candles(120)
    rows.pop(60)  # Simulate one missing 15m candle in the middle of history.
    connection = sqlite3.connect(source)
    repository = CandleRepository(connection)
    repository.ensure_schema()
    repository.insert_many(rows)
    connection.close()
    monkeypatch.setenv("SHERLOCK_SOURCE_DB", str(source))
    monkeypatch.setenv("SHERLOCK_ANALYTICS_DB", str(analytics))

    candles, sources = _load_candles("BTCUSDT", "15m", 200)
    assert len(candles) == 119
    assert candles[0].open_time == rows[0].open_time
    assert candles[-1].open_time == rows[-1].open_time
    assert sources == ["source"]



def test_contiguous_segment_split_preserves_each_side_of_gap():
    rows = make_candles(12)
    rows = rows[:6] + rows[7:]
    chunks = _split_contiguous(rows)
    assert [len(chunk) for chunk in chunks] == [6, 5]
    assert chunks[0][-1].open_time < chunks[1][0].open_time
    assert chunks[0][-1].open_time + 900_000 < chunks[1][0].open_time



def test_desktop_pattern_report_exposes_equal_weight_five_stage_evidence(tmp_path, monkeypatch):
    configure_db(tmp_path, monkeypatch)
    result = run_pattern_research(
        query_window=10, top_k=2, history_limit=120, mode="five_stage"
    )
    assert result["stage_weights"] == {
        "preliminary_decline": 0.2,
        "recovery": 0.2,
        "peak": 0.2,
        "sharp_collapse": 0.2,
        "sideways_lower_wicks": 0.2,
    }
    assert result["analogs"]
    assert result["analogs"][0]["analog"]["stage_similarities"]



def test_pattern_research_can_use_an_exact_historical_query_start(tmp_path, monkeypatch):
    configure_db(tmp_path, monkeypatch)
    selected_open_time = 90 * 900_000
    result = run_pattern_research(
        query_window=10, top_k=2, history_limit=120,
        query_start_time=selected_open_time,
    )
    assert result["query_start_time"] == selected_open_time
    assert result["query_end_time"] == 99 * 900_000
    assert result["query_selection"] == "historical_open_time"
    assert result["analogs"]


def test_pattern_research_rejects_nonexistent_historical_query_start(tmp_path, monkeypatch):
    configure_db(tmp_path, monkeypatch)
    try:
        run_pattern_research(
            query_window=10, top_k=2, history_limit=120,
            query_start_time=90 * 900_000 + 1,
        )
    except ValueError as exc:
        assert "does not match an available closed candle" in str(exc)
    else:
        raise AssertionError("non-candle timestamps must not be silently rounded")


def test_adaptive_pattern_search_keeps_query_end_fixed_and_rankings_separate(tmp_path, monkeypatch):
    configure_db(tmp_path, monkeypatch)
    result = run_pattern_research(
        query_window=20, top_k=2, history_limit=120, adaptive_search=True,
        adaptive_min_window=10, adaptive_max_window=30, adaptive_step=10,
        adaptive_candidate_budget=100,
    )
    assert result["adaptive_search"] is True
    completed = [item for item in result["adaptive_results"] if item["status"] == "completed"]
    assert [item["window_length"] for item in completed] == [10, 20, 30]
    assert len({item["query_end_time"] for item in completed}) == 1
    assert all(item["ranking_scope"] == "independent_within_this_window_length" for item in completed)
    assert "not pooled" in result["adaptive_comparison_note"]
    assert all(item["candidate_stride"] >= 1 for item in completed)


def test_adaptive_pattern_search_rejects_invalid_controls(tmp_path, monkeypatch):
    configure_db(tmp_path, monkeypatch)
    try:
        run_pattern_research(
            query_window=20, history_limit=120, adaptive_search=True,
            adaptive_min_window=40, adaptive_max_window=20,
        )
    except ValueError as exc:
        assert "window bounds" in str(exc)
    else:
        raise AssertionError("invalid adaptive window bounds must fail")


def test_adaptive_search_skips_only_window_that_crosses_gap(tmp_path, monkeypatch):
    configure_db(tmp_path, monkeypatch)
    connection = sqlite3.connect(tmp_path / "source.db")
    connection.execute(
        "DELETE FROM candles WHERE symbol=? AND interval=? AND open_time=?",
        ("BTCUSDT", "15m", 85 * 900_000),
    )
    connection.commit()
    connection.close()
    result = run_pattern_research(
        query_window=20, top_k=2, history_limit=120,
        query_start_time=90 * 900_000,
        adaptive_search=True, adaptive_min_window=20,
        adaptive_max_window=30, adaptive_step=10,
        adaptive_candidate_budget=100,
    )
    assert result["adaptive_results"][0]["status"] == "completed"
    assert result["adaptive_results"][0]["window_length"] == 20
    assert result["adaptive_results"][1]["status"] == "skipped"
    assert "missing-candle gap" in result["adaptive_results"][1]["reason"]


def test_walk_forward_desktop_service_uses_verified_local_history(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    analytics = tmp_path / "analytics.db"
    connection = sqlite3.connect(source)
    repository = CandleRepository(connection)
    repository.ensure_schema()
    repository.insert_many(make_candles(400))
    connection.close()
    monkeypatch.setenv("SHERLOCK_SOURCE_DB", str(source))
    monkeypatch.setenv("SHERLOCK_ANALYTICS_DB", str(analytics))

    result = run_walk_forward_research(
        query_window=10, top_k=3, max_folds=3,
        min_training_candles=100, candidate_budget=100,
        history_limit=400,
    )
    assert result["history_candles"] == 400
    assert result["evaluated_folds"] >= 2
    assert result["data_sources"] == ["source"]
    assert result["anti_leakage"]["candidate_forward_outcomes_end_before_test_start"]


def test_robustness_desktop_service_uses_verified_local_history(tmp_path, monkeypatch):
    from app.research.desktop_services import run_robustness_research

    source = tmp_path / "source.db"
    analytics = tmp_path / "analytics.db"
    connection = sqlite3.connect(source)
    repository = CandleRepository(connection)
    repository.ensure_schema()
    repository.insert_many(make_candles(500))
    connection.close()
    monkeypatch.setenv("SHERLOCK_SOURCE_DB", str(source))
    monkeypatch.setenv("SHERLOCK_ANALYTICS_DB", str(analytics))

    result = run_robustness_research(
        query_window=10, top_k=2, max_folds=2,
        min_training_candles=100, candidate_budget=100,
        history_limit=500,
    )
    assert result["history_candles"] == 500
    assert result["data_sources"] == ["source"]
    assert result["configurations_evaluated"] >= 3
    assert result["method"] == "bounded_one_factor_at_a_time_sensitivity"



def test_intelligence_core_service_runs_on_read_only_verified_history(tmp_path, monkeypatch):
    configure_db(tmp_path, monkeypatch)
    result = run_intelligence_core_research(
        query_window=10,
        query_start_time=90 * 900_000,
        top_k=3,
        min_analogs=1,
        candidate_budget=100,
        history_limit=120,
    )
    assert result["core_version"] == "0.1.0"
    assert result["query_selection"] == "historical_open_time"
    assert result["query"]["start_time"] == 90 * 900_000
    assert result["query_start_time"] == 90 * 900_000
    assert result["query_end_time"] == 99 * 900_000
    assert result["candidates_examined"] > 0
    assert result["data_sources"] == ["source"]
    assert result["history_candles"] == 120
    assert result["decision"]["trading_signal"] is None
    assert result["decision"]["paper_trade_eligible"] is False
    assert result["provenance"]["candidate_stride"] >= 1



def test_intelligence_core_service_persists_reproducible_experiment_record(tmp_path, monkeypatch):
    configure_db(tmp_path, monkeypatch)
    result = run_intelligence_core_research(
        query_window=10,
        query_start_time=90 * 900_000,
        top_k=3,
        min_analogs=1,
        candidate_budget=100,
        history_limit=120,
    )
    ledger = ExperimentLedger(tmp_path / "analytics.db")
    record = ledger.get_run(result["run_id"])
    assert result["experiment_ledger"]["status"] == "completed"
    assert result["experiment_ledger"]["input_fingerprint"]
    assert record["run"]["input_fingerprint"] == result["experiment_ledger"]["input_fingerprint"]
    assert record["result"]["run_id"] == result["run_id"]
    assert record["events"][-1]["event_type"] == "completed"
    assert ledger.verify_integrity()["ok"] is True


def test_intelligence_core_service_records_failed_attempt_without_result(tmp_path, monkeypatch):
    configure_db(tmp_path, monkeypatch)
    try:
        run_intelligence_core_research(
            query_window=10,
            query_start_time=90 * 900_000,
            mode="not-a-mode",
            top_k=3,
            min_analogs=1,
            candidate_budget=100,
            history_limit=120,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("invalid Core mode must fail")

    ledger = ExperimentLedger(tmp_path / "analytics.db")
    rows = ledger.list_runs(limit=10)
    assert len(rows) == 1
    record = ledger.get_run(rows[0]["run_id"])
    assert rows[0]["status"] == "failed"
    assert record["result"] is None
    assert record["events"][-1]["payload"]["error_type"] == "ValueError"
    assert ledger.verify_integrity()["ok"] is True
