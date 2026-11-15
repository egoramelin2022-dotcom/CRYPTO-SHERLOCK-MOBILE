import math

import pytest

from app.market_data.candles import Candle
from app.research.multitimeframe_pattern_intelligence import (
    MultiTimeframeSearchConfig,
    search_multitimeframe_analogs,
)


STEPS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def make_series(interval, count, *, gap_at=None, phase=0.0):
    step = STEPS[interval]
    rows = []
    previous = 100.0
    for index in range(count):
        if gap_at is not None and index >= gap_at:
            open_time = (index + 1) * step
        else:
            open_time = index * step
        close = 100.0 + 0.015 * index + 1.8 * math.sin(index / 7.0 + phase)
        op = previous
        high = max(op, close) + 0.35
        low = min(op, close) - 0.35
        volume = 100.0 + (index % 17) * 2.0
        rows.append(Candle(
            symbol="BTCUSDT",
            interval=interval,
            open_time=open_time,
            open=op,
            high=high,
            low=low,
            close=close,
            volume=volume,
            close_time=open_time + step - 1,
            quote_volume=volume * close,
            trade_count=100 + index % 13,
            taker_buy_base=volume * 0.52,
            taker_buy_quote=volume * close * 0.52,
        ))
        previous = close
    return rows


def fixture():
    return {
        "15m": make_series("15m", 3000),
        "1h": make_series("1h", 750),
        "4h": make_series("4h", 188),
        "1d": make_series("1d", 32),
    }


def test_search_returns_ranked_multitimeframe_analogs_with_costed_outcomes():
    data = fixture()
    config = MultiTimeframeSearchConfig(
        top_k=5,
        candidate_stride=4,
        horizons_15m=(4, 16),
        fee_bps_per_side=5,
        slippage_bps_per_side=2,
    )
    result = search_multitimeframe_analogs(
        data, query_end_index_15m=2800, config=config
    )

    assert result.symbol == "BTCUSDT"
    assert result.candidates_examined > 0
    assert result.analogs
    assert len(result.analogs) <= 5
    assert all(0.0 < item.similarity <= 1.0 for item in result.analogs)
    assert all(
        item.forward_outcomes["fee_bps_per_side"] == 5
        for item in result.analogs
    )
    assert all(
        set(item.timeframe_scores) == {"15m", "1h", "4h", "1d"}
        for item in result.analogs
    )
    assert result.to_dict()["causality"]["closed_candles_only"] is True


def test_higher_timeframe_windows_never_use_unclosed_candles():
    data = fixture()
    result = search_multitimeframe_analogs(
        data,
        query_end_index_15m=2800,
        config=MultiTimeframeSearchConfig(
            top_k=3, candidate_stride=8, horizons_15m=(4, 16)
        ),
    )
    assert result.analogs
    for analog in result.analogs:
        assert analog.decision_time <= result.query_decision_time
        for score in analog.timeframe_scores.values():
            assert score.candidate_end_time <= analog.decision_time
            assert score.query_end_time <= result.query_decision_time


def test_query_rejects_a_gap_in_the_15m_window():
    data = fixture()
    del data["15m"][2790]
    with pytest.raises(ValueError, match="15m query window"):
        search_multitimeframe_analogs(
            data,
            query_end_index_15m=2800,
            config=MultiTimeframeSearchConfig(
                top_k=2, candidate_stride=8, horizons_15m=(4, 16)
            ),
        )


def test_query_rejects_a_gap_in_a_higher_timeframe_window():
    data = fixture()
    del data["4h"][180]
    with pytest.raises(ValueError, match="closed 4h query window"):
        search_multitimeframe_analogs(
            data,
            query_end_index_15m=2800,
            config=MultiTimeframeSearchConfig(
                top_k=2, candidate_stride=8, horizons_15m=(4, 16)
            ),
        )


def test_config_rejects_missing_timeframes_and_bad_weights():
    data = fixture()
    with pytest.raises(ValueError, match="exactly 15m"):
        search_multitimeframe_analogs(
            {"15m": data["15m"]},
            query_end_index_15m=2800,
        )
    with pytest.raises(ValueError, match="weight"):
        search_multitimeframe_analogs(
            data,
            query_end_index_15m=2800,
            config=MultiTimeframeSearchConfig(
                timeframe_weights={"15m": -1, "1h": 1, "4h": 1, "1d": 1}
            ),
        )
