import pytest

from app.market_data.candles import Candle
from app.research.intelligence_core import run_intelligence_core


STEP = 900_000


def make_candles(count=180, *, gap_before=None):
    closes = []
    for i in range(count):
        closes.append(100.0 + 0.04 * i + 1.2 * __import__("math").sin(i / 5))
    # Plant a repeated ten-candle motif in eligible history and the query.
    motif = [100.0, 101.5, 100.8, 102.2, 101.0, 99.8, 100.4, 100.1, 100.7, 100.3]
    for offset in (25, 120):
        if offset + len(motif) <= count:
            closes[offset:offset + len(motif)] = motif
    rows = []
    previous = closes[0]
    for i, close in enumerate(closes):
        op = previous
        rows.append(Candle(
            symbol="BTCUSDT",
            interval="15m",
            open_time=(i + (1 if gap_before is not None and i >= gap_before else 0)) * STEP,
            open=op,
            high=max(op, close) * 1.002,
            low=min(op, close) * 0.998,
            close=close,
            volume=100.0 + i,
            close_time=(i + (1 if gap_before is not None and i >= gap_before else 0)) * STEP + STEP - 1,
            quote_volume=100.0 * close,
            trade_count=10,
            taker_buy_base=50.0,
            taker_buy_quote=50.0 * close,
        ))
        previous = close
    return rows


def test_core_orchestrates_pattern_regime_and_costed_outcomes():
    rows = make_candles()
    result = run_intelligence_core(
        rows,
        query_start_index=120,
        query_end_index=129,
        top_k=5,
        min_analogs=1,
        horizons=(1, 4),
        fee_bps_per_side=5,
        slippage_bps_per_side=2,
    )

    assert result["core_version"] == "0.1.0"
    assert result["symbol"] == "BTCUSDT"
    assert result["interval"] == "15m"
    assert result["modules"]["pattern_intelligence"]["status"] == "completed"
    assert result["modules"]["market_regime"]["result"]["causal"] is True
    assert result["modules"]["forward_outcomes"]["analogs_evaluated"] >= 1
    assert result["provenance"]["cost_model"]["fee_bps_per_side"] == 5
    assert result["decision"]["trading_signal"] is None
    assert result["decision"]["abstain"] is True
    assert result["decision"]["paper_trade_eligible"] is False
    assert "untouched final holdout" in result["required_next_checks"][-1]


def test_core_abstains_when_analog_sample_is_below_minimum():
    rows = make_candles()
    result = run_intelligence_core(
        rows,
        query_start_index=120,
        query_end_index=129,
        top_k=2,
        min_analogs=2,
        horizons=(1, 4),
    )
    assert result["research_status"] == "INSUFFICIENT_ANALOGS"
    assert result["decision"]["abstain"] is True
    assert all(
        item["status"] == "insufficient_sample"
        for item in result["modules"]["forward_outcomes"]["horizons"]
    )


def test_core_reports_unclassified_regime_when_trailing_window_crosses_gap():
    rows = make_candles(gap_before=110)
    result = run_intelligence_core(
        rows,
        query_start_index=120,
        query_end_index=129,
        top_k=5,
        min_analogs=1,
        horizons=(1,),
    )
    assert result["modules"]["market_regime"]["status"] == "unclassified"
    assert "missing-candle gap" in result["modules"]["market_regime"]["result"]["reason"]
    assert result["provenance"]["history_gap_count"] == 1


@pytest.mark.parametrize("kwargs, message", [
    ({"min_analogs": 0}, "min_analogs"),
    ({"min_analogs": 6, "top_k": 5}, "min_analogs must not exceed top_k"),
    ({"candidate_stride": True}, "candidate_stride"),
    ({"horizons": (1, 1)}, "duplicates"),
    ({"fee_bps_per_side": -1}, "fee_bps_per_side"),
])
def test_core_rejects_invalid_configuration(kwargs, message):
    rows = make_candles()
    base = {
        "query_start_index": 120,
        "query_end_index": 129,
        "top_k": 5,
        "min_analogs": 1,
        "horizons": (1, 4),
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=message):
        run_intelligence_core(rows, **base)
