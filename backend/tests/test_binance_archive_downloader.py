import pytest
from scripts.download_binance_spot_klines import (
    archive_url,
    months_between,
    normalize_timestamp,
    normalize_kline_times,
    parse_checksum,
)


def test_normalizes_old_milliseconds_and_new_microseconds():
    assert normalize_timestamp("1502942400000") == 1502942400000
    assert normalize_timestamp("1735689600000000") == 1735689600000


def test_checksum_parser_accepts_sha256_and_rejects_invalid():
    digest = "a" * 64
    assert parse_checksum(digest + " file.zip") == digest
    try:
        parse_checksum("not-a-hash")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid checksum must fail")


def test_month_range_crosses_year_boundary():
    assert list(months_between(2017, 11, 2018, 2)) == [
        (2017, 11), (2017, 12), (2018, 1), (2018, 2)
    ]


def test_archive_url_uses_binance_spot_monthly_layout():
    assert archive_url("BTCUSDT", "15m", 2017, 8) == (
        "https://data.binance.vision/data/spot/monthly/klines/"
        "BTCUSDT/15m/BTCUSDT-15m-2017-08.zip"
    )



def test_normalizes_inclusive_and_exact_exclusive_close_boundaries():
    # 15m candle in milliseconds.
    assert normalize_kline_times("1502942400000", "1502943299999", "15m") == (
        1502942400000, 1502943299999
    )
    # Same candle represented in microseconds.
    assert normalize_kline_times("1502942400000000", "1502943299999000", "15m") == (
        1502942400000, 1502943299999
    )
    # Some exports encode the interval end as an exclusive boundary.
    assert normalize_kline_times("1502942400000", "1502943300000", "15m") == (
        1502942400000, 1502943299999
    )


def test_rejects_close_time_that_is_not_an_exact_interval_boundary():
    try:
        normalize_kline_times("1502942400000", "1502943299998", "15m")
    except ValueError as exc:
        assert "15m close_time mismatch" in str(exc)
    else:
        raise AssertionError("invalid close_time must fail")

@pytest.mark.parametrize(
    "interval,step",
    [("15m", 900_000), ("4h", 14_400_000), ("1d", 86_400_000)],
)
def test_archive_timestamp_normalization_for_all_supported_intervals(interval, step):
    open_ms = 1_735_689_600_000
    assert normalize_kline_times(
        str(open_ms * 1000),
        str((open_ms + step - 1) * 1000),
        interval,
    ) == (open_ms, open_ms + step - 1)


def test_run_fails_instead_of_reporting_complete_when_requested_archive_is_missing(
    tmp_path, monkeypatch
):
    import sqlite3
    import scripts.download_binance_spot_klines as downloader
    from app.market_data.repository import CandleRepository

    monkeypatch.setattr(downloader, "INTERVALS", ("15m",))
    monkeypatch.setattr(
        downloader,
        "ingest_month",
        lambda symbol, interval, year, month, raw_dir, repository: (0, "missing"),
    )
    messages = []
    with pytest.raises(RuntimeError, match="Archive download is incomplete"):
        downloader.run(
            "2017-08", "2017-08", tmp_path / "raw", tmp_path / "staging.db",
            progress_callback=messages.append,
        )
    assert any("15m 2017-08: missing" in message for message in messages)
