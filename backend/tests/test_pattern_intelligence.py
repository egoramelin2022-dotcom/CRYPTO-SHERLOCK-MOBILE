from app.market_data.candles import Candle
from app.research.pattern_intelligence import search_analogs


def candle(i, close, *, high=None, low=None):
    op = close
    return Candle(
        symbol="BTCUSDT", interval="15m", open_time=i * 900_000,
        open=op, high=high if high is not None else op * 1.01,
        low=low if low is not None else op * 0.99, close=close,
        volume=10.0, close_time=i * 900_000 + 899_999,
        quote_volume=10.0 * close, trade_count=1,
        taker_buy_base=5.0, taker_buy_quote=5.0 * close,
    )


def test_search_returns_only_pre_query_candidates_and_future_outcomes():
    closes = [100, 102, 101, 105, 103, 100, 102, 101, 105, 103, 110, 111]
    rows = [candle(i, p) for i, p in enumerate(closes)]
    result = search_analogs(rows, query_start=5, query_end=9, top_k=10,
                            horizons=(1, 2), embargo=0)
    assert result.candidates_examined == 1
    assert all(x.end_index == 4 for x in result.analogs)
    best = result.analogs[0]
    assert best.forward_returns[1] == closes[best.end_index + 1] / closes[best.end_index] - 1


def test_five_stage_requires_five_candles_and_returns_equal_stage_mode():
    rows = [candle(i, 100 + i) for i in range(12)]
    result = search_analogs(rows, query_start=7, query_end=11, mode="five_stage",
                            horizons=(1,), embargo=0)
    assert result.mode == "five_stage"
    assert result.segment_length == 5
    assert result.analogs


def test_no_candidate_is_returned_when_history_is_too_short():
    rows = [candle(i, 100 + i) for i in range(6)]
    result = search_analogs(rows, query_start=0, query_end=5)
    assert result.candidates_examined == 0
    assert result.analogs == ()


def test_five_stage_rejects_short_query():
    rows = [candle(i, 100 + i) for i in range(6)]
    try:
        search_analogs(rows, query_start=3, query_end=5, mode="five_stage")
    except ValueError as exc:
        assert "at least five" in str(exc)
    else:
        raise AssertionError("expected ValueError")
