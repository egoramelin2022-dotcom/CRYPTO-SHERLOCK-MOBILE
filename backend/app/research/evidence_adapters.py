"""Adapters from existing matchers into the common ensemble evidence contract."""
from __future__ import annotations

from typing import Sequence

from app.market_data.candles import Candle
from app.market_data.intervals import interval_to_ms
from app.research.ensemble import ResearchEvidence


def pattern_search_evidence(
    result,
    candles: Sequence[Candle],
    *,
    algorithm_version: str = "pattern-intelligence-v0",
    feature_set: str = "ohlcv_candle_shape",
    provenance: str = "pattern_intelligence.search_analogs",
) -> list[ResearchEvidence]:
    """Convert a Pattern Intelligence SearchResult into evidence rows."""
    if not candles:
        raise ValueError("candles must not be empty")
    start = result.query_start_index
    end = result.query_end_index
    if start < 0 or end >= len(candles) or start > end:
        raise ValueError("search result query indices are outside candle data")
    query_start = candles[start]
    query_end = candles[end]
    if any(c.interval != query_start.interval for c in candles[start:end + 1]):
        raise ValueError("query candles must share one interval")

    rows = []
    for rank, analog in enumerate(result.analogs, start=1):
        if analog.start_index < 0 or analog.end_index >= len(candles):
            raise ValueError("analog indices are outside candle data")
        candidate_start = candles[analog.start_index]
        candidate_end = candles[analog.end_index]
        if candidate_end.open_time != analog.end_time or candidate_start.open_time != analog.start_time:
            raise ValueError("analog timestamps do not match supplied candles")
        rows.append(ResearchEvidence(
            module="pattern_intelligence",
            algorithm_version=algorithm_version,
            feature_set=feature_set,
            interval=query_start.interval,
            query_start_time=query_start.open_time,
            query_end_time=query_end.open_time,
            candidate_start_time=candidate_start.open_time,
            candidate_end_time=candidate_end.open_time,
            rank=rank,
            similarity=analog.similarity,
            provenance=provenance,
        ))
    return rows


def stumpy_matches_evidence(
    matches,
    *,
    history_open_times: Sequence[int],
    query_open_times: Sequence[int],
    interval: str,
    feature_set: str = "closed_candle_log_returns",
    algorithm_version: str = "stumpy-mass-1.14.1",
    provenance: str = "stumpy_adapter.find_query_matches",
) -> list[ResearchEvidence]:
    """Map STUMPY match offsets to timestamped candidate evidence.

    Timestamps must be complete, strictly contiguous candle-open times. The
    caller must pass history strictly before the query and the exact query
    window used to create the MASS profile.
    """
    if not query_open_times:
        raise ValueError("query_open_times must not be empty")
    if not history_open_times:
        raise ValueError("history_open_times must not be empty")
    step = interval_to_ms(interval)
    for label, timestamps in (
        ("history", history_open_times), ("query", query_open_times)
    ):
        if any(
            isinstance(ts, bool) or not isinstance(ts, int) or ts < 0
            for ts in timestamps
        ):
            raise ValueError(f"{label} timestamps must be nonnegative integers")
        if any(b - a != step for a, b in zip(timestamps, timestamps[1:])):
            raise ValueError(f"{label} timestamps must be contiguous")
    if history_open_times[-1] >= query_open_times[0]:
        raise ValueError("history must end before query starts")

    rows = []
    for rank, match in enumerate(matches, start=1):
        start = match.start_index
        end = start + len(query_open_times) - 1
        if start < 0 or end >= len(history_open_times):
            raise ValueError("STUMPY match window is outside history timestamps")
        distance = float(match.distance)
        if distance < 0:
            raise ValueError("STUMPY distance must be nonnegative")
        rows.append(ResearchEvidence(
            module="stumpy",
            algorithm_version=algorithm_version,
            feature_set=feature_set,
            interval=interval,
            query_start_time=query_open_times[0],
            query_end_time=query_open_times[-1],
            candidate_start_time=history_open_times[start],
            candidate_end_time=history_open_times[end],
            rank=rank,
            similarity=1.0 / (1.0 + distance),
            provenance=provenance,
        ))
    return rows
