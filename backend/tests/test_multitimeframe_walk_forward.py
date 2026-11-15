import math

import pytest

from app.market_data.candles import Candle
from app.research.multitimeframe_pattern_intelligence import MultiTimeframeSearchConfig
from app.research.multitimeframe_walk_forward import run_multitimeframe_walk_forward


STEPS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def make_series(interval, count):
    step = STEPS[interval]
    rows = []
    previous = 100.0
    for index in range(count):
        close = 100.0 + 0.01 * index + 1.5 * math.sin(index / 7.0)
        op = previous
        high = max(op, close) + 0.3
        low = min(op, close) - 0.3
        volume = 100.0 + (index % 19)
        rows.append(Candle(
            symbol="BTCUSDT", interval=interval, open_time=index * step,
            open=op, high=high, low=low, close=close, volume=volume,
            close_time=(index + 1) * step - 1, quote_volume=volume * close,
            trade_count=100 + index % 11, taker_buy_base=volume * 0.51,
            taker_buy_quote=volume * close * 0.51,
        ))
        previous = close
    return rows


def fixture():
    return {
        "15m": make_series("15m", 2200),
        "1h": make_series("1h", 560),
        "4h": make_series("4h", 150),
        "1d": make_series("1d", 50),
    }


def test_mtf_walk_forward_is_chronological_cost_aware_and_compares_baselines():
    report = run_multitimeframe_walk_forward(
        fixture(),
        config=MultiTimeframeSearchConfig(
            top_k=3, candidate_stride=8, horizons_15m=(4, 16),
            fee_bps_per_side=5.0, slippage_bps_per_side=2.0,
        ),
        min_training_candles=1200,
        max_folds=4,
        candidate_budget=500,
    )
    assert report["engine"] == "multitimeframe_independent_walk_forward"
    assert report["parameters_frozen"] is True
    assert report["parameter_optimization_performed"] is False
    assert report["folds_evaluated"] >= 2
    assert report["folds_evaluated"] <= 4
    assert report["costs"] == {"fee_bps_per_side": 5.0, "slippage_bps_per_side": 2.0}
    for horizon in ("4", "16"):
        assert set(report["metrics_by_horizon"][horizon]) == {
            "mtf_analogs", "always_long", "always_short", "flat", "momentum"
        }
    starts = [row["query_start_time"] for row in report["fold_details"]]
    assert starts == sorted(starts)
    assert all(
        row["training_data_end_time"] < row["query_start_time"]
        for row in report["fold_details"]
    )


def test_mtf_walk_forward_rejects_insufficient_independent_folds():
    data = fixture()
    data["15m"] = data["15m"][:200]
    with pytest.raises(ValueError, match="not enough history"):
        run_multitimeframe_walk_forward(
            data,
            config=MultiTimeframeSearchConfig(horizons_15m=(4, 16)),
            min_training_candles=1200,
        )


def test_mtf_walk_forward_validates_fold_controls():
    with pytest.raises(ValueError, match="max_folds"):
        run_multitimeframe_walk_forward(
            fixture(), max_folds=1,
            config=MultiTimeframeSearchConfig(horizons_15m=(4, 16)),
            min_training_candles=1200,
        )
