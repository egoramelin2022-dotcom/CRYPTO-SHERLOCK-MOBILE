from desktop.market_data import parse_klines_payload


def row(t=1000, **changes):
    value = {
        "open_time": t, "open": 10, "high": 12, "low": 9,
        "close": 11, "volume": 3, "close_time": t + 899999,
    }
    value.update(changes)
    return value


def test_parse_valid_candles():
    candles = parse_klines_payload({"candles": [row(), row(901000)]})
    assert len(candles) == 2
    assert candles[0].close == 11


def test_reject_unsorted_candles():
    try:
        parse_klines_payload({"candles": [row(2000), row(1000)]})
    except ValueError as exc:
        assert "strictly ordered" in str(exc)
    else:
        raise AssertionError("unsorted candles must be rejected")


def test_reject_invalid_ohlc():
    try:
        parse_klines_payload({"candles": [row(low=11.5)]})
    except ValueError as exc:
        assert "OHLC" in str(exc)
    else:
        raise AssertionError("invalid OHLC must be rejected")


def test_reject_non_finite_values():
    try:
        parse_klines_payload({"candles": [row(close=float("nan"))]})
    except ValueError as exc:
        assert "non-finite" in str(exc)
    else:
        raise AssertionError("NaN must be rejected")
