import pytest

from app.market_data.candles import Candle
from app.research.outcome_evaluation import evaluate_forward_path


STEP = 900_000


def candle(i, op, high, low, close):
    return Candle(
        symbol="BTCUSDT", interval="15m", open_time=i * STEP,
        open=op, high=high, low=low, close=close, volume=1.0,
        close_time=i * STEP + STEP - 1, quote_volume=op,
        trade_count=1, taker_buy_base=0.5, taker_buy_quote=op * 0.5,
    )


def path():
    return [
        candle(0, 100, 101, 99, 100),
        candle(1, 102, 106, 100, 104),
        candle(2, 104, 105, 98, 99),
        candle(3, 99, 103, 97, 101),
        candle(4, 101, 108, 100, 107),
    ]


def test_entry_is_next_open_and_horizon_exits_are_forward_only():
    result = evaluate_forward_path(path(), candidate_end_index=0, horizons=(1, 2, 4))
    one, two, missing = result.outcomes
    assert one.entry_price == 102
    assert one.exit_price == 104
    assert one.gross_return == pytest.approx(104 / 102 - 1)
    assert two.exit_time == 2 * STEP
    assert missing is None


def test_long_short_excursions_and_neutral_range_metrics():
    result = evaluate_forward_path(path(), candidate_end_index=0, horizons=(2,))
    item = result.outcomes[0]
    assert item.long_mfe == pytest.approx(106 / 102 - 1)
    assert item.long_mae == pytest.approx(98 / 102 - 1)
    assert item.short_mfe == pytest.approx(102 / 98 - 1)
    assert item.short_mae == pytest.approx(102 / 106 - 1)
    assert item.max_high_low_range == pytest.approx(106 / 98 - 1)
    assert item.absolute_close_return == pytest.approx(abs(99 / 102 - 1))


def test_round_trip_fees_and_slippage_reduce_both_directions():
    raw = evaluate_forward_path(path(), candidate_end_index=0, horizons=(1,))
    charged = evaluate_forward_path(
        path(), candidate_end_index=0, horizons=(1,),
        fee_bps_per_side=10, slippage_bps_per_side=5,
    )
    assert charged.outcomes[0].long_net_return < raw.outcomes[0].long_net_return
    assert charged.outcomes[0].short_net_return < raw.outcomes[0].short_net_return


def test_no_future_entry_returns_missing_horizons():
    result = evaluate_forward_path(path()[:1], candidate_end_index=0, horizons=(1, 4))
    assert result.entry_time is None
    assert result.outcomes == (None, None)


def test_rejects_gaps():
    rows = path()
    rows[2] = candle(3, 104, 105, 98, 99)
    with pytest.raises(ValueError, match="missing"):
        evaluate_forward_path(rows, candidate_end_index=0, horizons=(2,))


def test_rejects_invalid_costs_horizons_and_candidate_index():
    rows = path()
    with pytest.raises(ValueError, match="positive integers"):
        evaluate_forward_path(rows, candidate_end_index=0, horizons=(0,))
    with pytest.raises(ValueError, match="fee_bps"):
        evaluate_forward_path(rows, candidate_end_index=0, fee_bps_per_side=-1)
    with pytest.raises(ValueError, match="candidate_end_index"):
        evaluate_forward_path(rows, candidate_end_index=99)
