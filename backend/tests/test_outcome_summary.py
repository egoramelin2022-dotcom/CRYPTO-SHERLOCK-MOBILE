from app.market_data.candles import Candle
from app.research.outcome_evaluation import evaluate_forward_path
from app.research.outcome_summary import summarize_forward_outcomes


def candle(i, open_price, high, low, close):
    return Candle(
        symbol="BTCUSDT",
        interval="15m",
        open_time=i * 900_000,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=10.0,
        close_time=i * 900_000 + 899_999,
        quote_volume=1000.0,
        trade_count=1,
        taker_buy_base=5.0,
        taker_buy_quote=500.0,
    )


def test_summary_reports_directional_rates_and_explicit_sideways_bucket():
    up = [candle(0, 100, 100.1, 99.9, 100),
          candle(1, 100, 100.3, 99.9, 100.2)]
    down = [candle(0, 100, 100.1, 99.9, 100),
            candle(1, 100, 100.3, 98.8, 99.0)]
    evaluations = [
        evaluate_forward_path(up, candidate_end_index=0, horizons=(1,)),
        evaluate_forward_path(down, candidate_end_index=0, horizons=(1,)),
    ]

    summary = summarize_forward_outcomes(
        evaluations,
        sideways_max_range=0.01,
        sideways_max_abs_close_return=0.005,
    )

    assert len(summary) == 1
    row = summary[0]
    assert row.horizon == 1
    assert row.sample_count == 2
    assert row.long_net_positive_rate == 0.5
    assert row.short_net_positive_rate == 0.5
    assert row.sideways_rate == 0.5


def test_summary_omits_horizons_without_available_outcomes():
    rows = [candle(0, 100, 100.1, 99.9, 100)]
    evaluation = evaluate_forward_path(
        rows, candidate_end_index=0, horizons=(1, 4)
    )
    assert summarize_forward_outcomes([evaluation]) == ()


def test_summary_rejects_invalid_sideways_thresholds():
    try:
        summarize_forward_outcomes([], sideways_max_range=1.0)
    except ValueError as exc:
        assert "sideways_max_range" in str(exc)
    else:
        raise AssertionError("expected ValueError")
