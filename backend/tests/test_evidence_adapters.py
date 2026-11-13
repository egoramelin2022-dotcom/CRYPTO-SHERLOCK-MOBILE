from types import SimpleNamespace

import pytest

from app.market_data.candles import Candle
from app.research.evidence_adapters import (
    pattern_search_evidence,
    stumpy_matches_evidence,
)


def candle(i):
    price = 100.0 + i
    return Candle(
        symbol="BTCUSDT", interval="15m", open_time=i * 900_000,
        open=price, high=price * 1.01, low=price * 0.99, close=price,
        volume=1.0, close_time=i * 900_000 + 899_999,
        quote_volume=price, trade_count=1, taker_buy_base=0.5,
        taker_buy_quote=price * 0.5,
    )


def test_pattern_intelligence_result_maps_indices_to_exact_candle_times():
    rows = [candle(i) for i in range(12)]
    analog = SimpleNamespace(
        start_index=0, end_index=4, start_time=rows[0].open_time,
        end_time=rows[4].open_time, similarity=0.8,
    )
    result = SimpleNamespace(query_start_index=7, query_end_index=11, analogs=(analog,))
    evidence = pattern_search_evidence(result, rows)
    assert len(evidence) == 1
    assert evidence[0].module == "pattern_intelligence"
    assert evidence[0].candidate_end_time == rows[4].open_time
    assert evidence[0].query_start_time == rows[7].open_time


def test_pattern_adapter_rejects_timestamp_mismatch():
    rows = [candle(i) for i in range(12)]
    analog = SimpleNamespace(
        start_index=0, end_index=4, start_time=123,
        end_time=rows[4].open_time, similarity=0.8,
    )
    result = SimpleNamespace(query_start_index=7, query_end_index=11, analogs=(analog,))
    with pytest.raises(ValueError, match="timestamps"):
        pattern_search_evidence(result, rows)


def test_stumpy_offsets_map_to_candidate_window_timestamps():
    matches = [SimpleNamespace(start_index=2, distance=1.0)]
    evidence = stumpy_matches_evidence(
        matches,
        history_open_times=[i * 900_000 for i in range(10)],
        query_open_times=[10 * 900_000, 11 * 900_000, 12 * 900_000],
        interval="15m",
    )
    assert evidence[0].candidate_start_time == 2 * 900_000
    assert evidence[0].candidate_end_time == 4 * 900_000
    assert evidence[0].similarity == 0.5


def test_stumpy_adapter_rejects_gaps_and_future_history():
    with pytest.raises(ValueError, match="contiguous"):
        stumpy_matches_evidence(
            [], history_open_times=[0, 900_000, 1_800_001],
            query_open_times=[3 * 900_000], interval="15m",
        )
    with pytest.raises(ValueError, match="before query"):
        stumpy_matches_evidence(
            [], history_open_times=[0, 900_000, 1_800_000],
            query_open_times=[2 * 900_000], interval="15m",
        )


def test_stumpy_adapter_rejects_out_of_bounds_match():
    with pytest.raises(ValueError, match="outside history"):
        stumpy_matches_evidence(
            [SimpleNamespace(start_index=8, distance=0.1)],
            history_open_times=[i * 900_000 for i in range(10)],
            query_open_times=[10 * 900_000, 11 * 900_000, 12 * 900_000],
            interval="15m",
        )
