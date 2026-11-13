from scripts.download_binance_spot_klines import (
    archive_url,
    months_between,
    normalize_timestamp,
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
