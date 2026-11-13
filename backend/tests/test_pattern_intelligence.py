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
    result = search_analogs(rows, query_start=7, query_end=11, top_k=10,
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
    assert result.to_dict()["stage_weights"] == {
        "preliminary_decline": 0.2,
        "recovery": 0.2,
        "peak": 0.2,
        "sharp_collapse": 0.2,
        "sideways_lower_wicks": 0.2,
    }
    assert result.analogs
    assert set(result.analogs[0].stage_similarities) == {
        "preliminary_decline", "recovery", "peak",
        "sharp_collapse", "sideways_lower_wicks",
    }
    assert all(0.0 < score <= 1.0 for score in result.analogs[0].stage_similarities.values())


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



def test_selected_analogs_do_not_overlap_their_forward_outcome_horizons():
    rows = [candle(i, 100 + (i % 5)) for i in range(40)]
    result = search_analogs(
        rows, query_start=30, query_end=34, top_k=10,
        horizons=(1, 4), embargo=0,
    )
    starts = [item.start_index for item in result.analogs]
    # Five-candle analog plus four-candle forward horizon must not overlap.
    assert all(abs(a - b) >= 9 for i, a in enumerate(starts) for b in starts[i + 1:])
    assert all(item.end_index + 4 < result.query_start_index for item in result.analogs)



def test_search_skips_candidates_and_forward_paths_crossing_data_gaps():
    # There is a missing 15m candle between indices 14 and 16.
    rows = [candle(i, 100 + (i % 7)) for i in list(range(15)) + list(range(16, 40))]
    result = search_analogs(
        rows, query_start=30, query_end=34, top_k=10,
        horizons=(1, 2), embargo=0,
    )
    assert result.analogs
    # Earlier candidates are valid only if their complete forward path ends
    # before the gap; later candidates must start after the gap.
    assert all(item.end_index + 2 < 15 or item.start_index >= 16 for item in result.analogs)
    assert all(item.end_index + 2 < result.query_start_index for item in result.analogs)


def test_search_rejects_query_window_that_crosses_a_gap():
    rows = [candle(i, 100 + i) for i in list(range(15)) + list(range(16, 30))]
    try:
        search_analogs(rows, query_start=13, query_end=17, horizons=(1,))
    except ValueError as exc:
        assert "crosses a missing-candle gap" in str(exc)
    else:
        raise AssertionError("query windows must not bridge missing candles")



def test_search_rejects_non_integer_controls_and_duplicate_timestamps():
    rows = [candle(i, 100 + i) for i in range(12)]
    for kwargs in (
        {"top_k": 1.5},
        {"horizons": (1.5,)},
    ):
        try:
            search_analogs(rows, query_start=8, query_end=10, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid search controls must be rejected")

    rows[4] = candle(3, 104)
    try:
        search_analogs(rows, query_start=8, query_end=10)
    except ValueError as exc:
        assert "strictly increasing" in str(exc)
    else:
        raise AssertionError("duplicate candle timestamps must be rejected")
