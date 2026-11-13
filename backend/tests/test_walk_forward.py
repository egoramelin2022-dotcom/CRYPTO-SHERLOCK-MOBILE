import math

import pytest

from app.market_data.candles import Candle
from app.research.walk_forward import run_walk_forward


STEP = 900_000


def make_candles(count=500, gap_at=None):
    rows = []
    for index in range(count):
        # Repeating but non-identical movement gives the matcher real variation.
        base = 100 + 0.03 * index + 2.0 * math.sin(index / 7.0) + 0.8 * math.sin(index / 19.0)
        open_time = index * STEP
        if gap_at is not None and index > gap_at:
            open_time += STEP
        open_price = base
        close = base * (1.0 + 0.0015 * math.sin(index / 3.0))
        rows.append(Candle(
            symbol="BTCUSDT", interval="15m", open_time=open_time,
            open=open_price, high=max(open_price, close) * 1.003,
            low=min(open_price, close) * 0.997, close=close,
            volume=10.0, close_time=open_time + STEP - 1,
            quote_volume=base * 10, trade_count=10,
            taker_buy_base=5.0, taker_buy_quote=base * 5,
        ))
    return rows


def test_walk_forward_uses_strictly_prior_analogs_and_reports_baselines():
    result = run_walk_forward(
        make_candles(), query_window=10, top_k=3, max_folds=5,
        min_training_candles=100, candidate_budget=100,
        horizons=(1, 4, 8),
    )
    assert result["evaluated_folds"] >= 2
    assert result["anti_leakage"]["training_is_strictly_before_test_start"] is True
    assert result["anti_leakage"]["candidate_forward_outcomes_end_before_test_start"] is True
    assert result["anti_leakage"]["test_windows_and_forward_paths_non_overlapping"] is True
    for fold in result["folds"]:
        assert fold["training_candles_available"] == fold["query_start_index"]
        for analog in fold["analogs"]:
            assert analog["end_index"] + 8 < fold["query_start_index"]
    for horizon in ("1", "4", "8"):
        assert set(result["metrics_by_horizon"][horizon]) == {
            "model", "always_long", "always_short", "flat"
        }


def test_walk_forward_skips_a_gapped_test_query_and_continues():
    result = run_walk_forward(
        make_candles(gap_at=104), query_window=10, top_k=3,
        max_folds=5, min_training_candles=100, candidate_budget=100,
        horizons=(1, 4, 8),
    )
    assert any("query window crosses a missing-candle gap" in item["reason"]
               for item in result["skipped_folds"])
    assert result["evaluated_folds"] >= 1


def test_walk_forward_rejects_invalid_controls():
    rows = make_candles()
    with pytest.raises(ValueError, match="candidate_budget"):
        run_walk_forward(rows, candidate_budget=99)
    with pytest.raises(ValueError, match="min_training_candles"):
        run_walk_forward(rows, query_window=40, min_training_candles=10)
