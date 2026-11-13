from __future__ import annotations

import pytest

from app.market_data.candles import Candle
from app.market_data.features import (
    classify_regime, extract_features, split_contiguous_segments,
)


def candle(t: int, close: float, *, volume: float = 10.0,
           taker: float = 6.0, trades: int = 10) -> Candle:
    return Candle(
        symbol="BTCUSDT", interval="15m", open_time=t,
        open=close - 0.2, high=close + 0.8, low=close - 1.0,
        close=close, volume=volume, close_time=t + 899999,
        quote_volume=volume * close, trade_count=trades,
        taker_buy_base=taker, taker_buy_quote=taker * close,
    )


def test_features_extract_candle_shape_and_flow():
    rows = extract_features([
        candle(0, 100.0, volume=10, taker=6),
        candle(900000, 101.0, volume=20, taker=15),
        candle(1800000, 102.0, volume=30, taker=21),
    ], window=3)
    last = rows[-1]
    assert last.symbol == "BTCUSDT"
    assert last.body_pct > 0
    assert last.range_pct > 0
    assert 0 <= last.close_location <= 1
    assert last.taker_buy_ratio == pytest.approx(0.7)
    assert last.return_1 is not None and last.return_1 > 0
    assert last.efficiency_ratio is not None


def test_gap_splits_segments_and_never_bridges_feature_windows():
    candles = [
        candle(0, 100.0),
        candle(900000, 101.0),
        candle(2700000, 80.0),
        candle(3600000, 81.0),
    ]
    segments = split_contiguous_segments(candles)
    assert [len(segment) for segment in segments] == [2, 2]
    rows = extract_features(candles, window=3)
    assert rows[2].return_1 is None
    assert rows[2].return_window is None


def test_feature_input_rejects_unsorted_or_mixed_series():
    with pytest.raises(ValueError, match="strictly increasing"):
        extract_features([candle(900000, 101), candle(0, 100)])
    with pytest.raises(ValueError, match="one symbol and interval"):
        extract_features([candle(0, 100), Candle(
            symbol="ETHUSDT", interval="15m", open_time=900000,
            open=100, high=102, low=99, close=101, volume=1,
            close_time=1799999, quote_volume=101, trade_count=1,
            taker_buy_base=0.5, taker_buy_quote=50.5,
        )])


def test_regime_classifier_has_explicit_warmup_and_labels():
    rows = extract_features(
        [candle(i * 900000, 100 + i * 2) for i in range(8)],
        window=5,
    )
    warmup = classify_regime(rows[0])
    assert warmup.label == "INSUFFICIENT_DATA"
    regime = classify_regime(rows[-1], high_volatility_atr_pct=0.5)
    assert regime.label == "TREND"
    assert regime.direction == "UP"


def test_regime_classifier_rejects_invalid_thresholds():
    rows = extract_features([candle(0, 100), candle(900000, 101)], window=2)
    with pytest.raises(ValueError):
        classify_regime(rows[-1], trend_efficiency=0.1, range_efficiency=0.2)
