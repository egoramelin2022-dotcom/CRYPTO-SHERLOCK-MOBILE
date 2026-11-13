import math

import pytest

from app.market_data.candles import Candle
from app.research.robustness import run_robustness_audit

STEP = 900_000


def make_candles(count=900):
    rows = []
    for index in range(count):
        base = 100 + 0.02 * index + 2.0 * math.sin(index / 7.0)
        opened = index * STEP
        close = base * (1 + 0.001 * math.sin(index / 3.0))
        rows.append(Candle(
            symbol="BTCUSDT", interval="15m", open_time=opened,
            open=base, high=max(base, close) * 1.003,
            low=min(base, close) * 0.997, close=close,
            volume=10.0, close_time=opened + STEP - 1,
            quote_volume=base * 10, trade_count=10,
            taker_buy_base=5.0, taker_buy_quote=base * 5,
        ))
    return rows


def test_robustness_audit_keeps_parameter_runs_separate_and_reports_baselines():
    result = run_robustness_audit(
        make_candles(), query_window=10, top_k=4, max_folds=3,
        min_training_candles=100, candidate_budget=100,
    )
    assert result["configurations_evaluated"] >= 3
    assert result["method"] == "bounded_one_factor_at_a_time_sensitivity"
    assert "PBO" in " ".join(result["limitations"])
    assert "not pooled" in result["selection_policy"]
    names = [run["configuration"] for run in result["runs"]]
    assert len(names) == len(set(names))
    for run in result["runs"]:
        for horizon in run["metrics_by_horizon"].values():
            assert "excess_vs_best_baseline" in horizon
            assert horizon["evaluated_folds"] >= 0
    for horizon in result["stability_by_horizon"].values():
        assert 0 <= horizon["positive_average_return_share"] <= 1
        assert 0 <= horizon["positive_excess_vs_best_baseline_share"] <= 1


def test_robustness_audit_reports_pbo_and_aligned_portfolio_diagnostics():
    result = run_robustness_audit(
        make_candles(900), query_window=10, top_k=4, max_folds=4,
        min_training_candles=100, candidate_budget=100,
    )
    assert result["paired_diagnostic_configurations"] == [
        "baseline", "fewer_analogs", "more_analogs"
    ]
    assert result["pbo_by_horizon"]
    assert result["strategy_portfolio_by_horizon"]
    for diagnostic in result["pbo_by_horizon"].values():
        if diagnostic["status"] == "completed":
            assert 0 <= diagnostic["pbo"] <= 1
            assert diagnostic["aligned_folds"] >= 4
            assert diagnostic["partitions_evaluated"] > 0
    for diagnostic in result["strategy_portfolio_by_horizon"].values():
        if diagnostic["status"] == "completed":
            assert diagnostic["aligned_folds"] >= 4
            assert "pairwise_return_correlation" in diagnostic


def test_robustness_audit_rejects_invalid_parameters():
    with pytest.raises(ValueError, match="query_window"):
        run_robustness_audit(make_candles(), query_window=2)


def test_robustness_audit_marks_configurations_skipped_when_history_is_insufficient():
    result = run_robustness_audit(
        make_candles(300), query_window=100, top_k=3, max_folds=2,
        min_training_candles=150, candidate_budget=100,
    )
    assert result["configurations_attempted"] >= 1
    assert result["configurations_evaluated"] == 0
    assert all(run["status"] == "skipped" for run in result["runs"])
    assert all(run["reason"] for run in result["runs"])
