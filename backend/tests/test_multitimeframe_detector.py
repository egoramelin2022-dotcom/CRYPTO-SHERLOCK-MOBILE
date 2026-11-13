import pytest

from app.market_data.candles import Candle
from app.research.multitimeframe_detector import (
    MultiTimeframeConfig,
    detect_multitimeframe_setups,
)


def make(symbol, interval, index, op, high, low, close):
    step = {"15m": 900_000, "4h": 14_400_000, "1d": 86_400_000}[interval]
    return Candle(
        symbol=symbol, interval=interval, open_time=index * step,
        open=op, high=high, low=low, close=close, volume=10.0,
        close_time=(index + 1) * step - 1, quote_volume=op * 10,
        trade_count=10, taker_buy_base=5.0, taker_buy_quote=op * 5,
    )


def fixture():
    # Daily history: 60 small-body candles, then a large red day.
    daily = [make("BTCUSDT", "1d", i, 100, 101, 99, 100) for i in range(60)]
    daily.append(make("BTCUSDT", "1d", 60, 100, 101, 90, 91))

    # 4h history: 20 prior support bars at 95; current bar sweeps to 90,
    # then closes at 96, reclaiming support.
    # 60 daily candles contain 360 four-hour candles each.
    four_hour = [
        make("BTCUSDT", "4h", i, 97, 99, 95, 97)
        for i in range(61 * 6 - 1)
    ]
    four_hour.append(make("BTCUSDT", "4h", 61 * 6 - 1, 97, 98, 90, 96))

    # 15m bars throughout the matching 4h interval; one long lower wick.
    h4_index = 61 * 6 - 1
    fifteen = [
        make("BTCUSDT", "15m", i, 96, 97, 95, 96)
        for i in range(h4_index * 16, (h4_index + 1) * 16)
    ]
    # The last 15m candle closes simultaneously with the 4h and daily bars.
    fifteen[15] = make("BTCUSDT", "15m", h4_index * 16 + 15, 96, 97, 88, 96)
    return fifteen, four_hour, daily


def test_detects_simultaneous_three_timeframe_setup():
    m15, h4, d1 = fixture()
    signals = detect_multitimeframe_setups(m15, h4, d1)
    assert len(signals) == 1
    signal = signals[0]
    assert signal.timestamp == m15[15].open_time
    assert signal.support_4h == 95
    assert signal.sweep_depth_4h == 5
    assert signal.daily_body_return == pytest.approx(-0.09)


def test_rejects_when_daily_candle_is_not_large_red():
    m15, h4, d1 = fixture()
    d1[-1] = make("BTCUSDT", "1d", 60, 100, 101, 98, 99)
    assert detect_multitimeframe_setups(m15, h4, d1) == []


def test_rejects_gaps_and_mixed_symbols():
    m15, h4, d1 = fixture()
    broken = m15[:2] + m15[3:]
    with pytest.raises(ValueError, match="missing"):
        detect_multitimeframe_setups(broken, h4, d1)
