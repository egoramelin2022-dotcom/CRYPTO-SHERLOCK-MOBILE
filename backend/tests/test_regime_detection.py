import math

import pytest

from app.market_data.candles import Candle
from app.research.regime_detection import classify_regime, summarize_regime_outcomes

STEP = 900_000


def candles(count=120, trend=0.0005, volume_growth=0.0):
    rows = []
    price = 100.0
    for index in range(count):
        previous = price
        price *= 1.0 + trend + 0.0002 * math.sin(index / 4)
        opened = index * STEP
        rows.append(Candle(
            symbol="BTCUSDT", interval="15m", open_time=opened,
            open=previous, high=max(previous, price) * 1.001,
            low=min(previous, price) * 0.999, close=price,
            volume=10.0 * (1 + volume_growth * index / count),
            close_time=opened + STEP - 1, quote_volume=price * 10,
            trade_count=10, taker_buy_base=5, taker_buy_quote=price * 5,
        ))
    return rows


def test_regime_classifier_is_causal_and_bounded_to_query_close():
    rows = candles()
    first = classify_regime(rows, end_index=80, lookback=60)
    changed_future = rows[:81] + candles(39, trend=-0.01)
    second = classify_regime(changed_future, end_index=80, lookback=60)
    assert first == second
    assert first["causal"] is True
    assert first["end_index"] == 80
    assert first["regime"] in {"HIGH_VOLATILITY", "TREND_UP", "TREND_DOWN", "ACCUMULATION_CANDIDATE", "SIDEWAYS"}


def test_regime_classifier_validates_history():
    with pytest.raises(ValueError, match="at least 20"):
        classify_regime(candles(10))
    with pytest.raises(ValueError, match="lookback"):
        classify_regime(candles(), lookback=2)


def test_regime_outcome_summary_groups_by_label_and_horizon():
    result = summarize_regime_outcomes([{
        "regime": {"regime": "TREND_UP"},
        "horizons": {"4": {"predicted_side": "LONG", "model_return": 0.02}},
    }])
    assert result["TREND_UP|4"]["folds"] == 1
    assert result["TREND_UP|4"]["average_model_return"] == 0.02
