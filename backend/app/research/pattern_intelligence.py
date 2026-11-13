"""Historical analog search for closed OHLCV candle sequences.

This is a descriptive research primitive, not a trading signal. Candidate
windows are strictly earlier than the query window; forward outcomes are
measured only after each candidate ends. No source database writes occur here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Literal, Sequence

from app.market_data.candles import Candle
from app.market_data.intervals import interval_to_ms

SearchMode = Literal["free", "five_stage"]


@dataclass(frozen=True, slots=True)
class Analog:
    start_index: int
    end_index: int
    start_time: int
    end_time: int
    similarity: float
    forward_returns: dict[int, float | None]
    max_favorable_excursion: float | None
    max_adverse_excursion: float | None


@dataclass(frozen=True, slots=True)
class SearchResult:
    mode: SearchMode
    query_start_index: int
    query_end_index: int
    segment_length: int
    candidates_examined: int
    analogs: tuple[Analog, ...]

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "query_start_index": self.query_start_index,
            "query_end_index": self.query_end_index,
            "segment_length": self.segment_length,
            "candidates_examined": self.candidates_examined,
            "analogs": [asdict(item) for item in self.analogs],
        }


def _shape(candles: Sequence[Candle]) -> list[tuple[float, ...]]:
    """Build scale-invariant per-candle descriptors for shape comparison."""
    base = candles[0].close
    path = [math.log(c.close / base) for c in candles]
    scale = math.sqrt(sum(x * x for x in path) / max(1, len(path)))
    if scale < 1e-12:
        scale = max(
            math.sqrt(sum(math.log(c.close / candles[i - 1].close) ** 2
                          for i, c in enumerate(candles) if i > 0)
                      / max(1, len(candles) - 1)),
            1e-8,
        )
    result = []
    for i, c in enumerate(candles):
        span = max(c.high - c.low, c.open * 1e-12)
        signed_body = (c.close - c.open) / c.open
        result.append((
            path[i] / scale,
            signed_body / scale,
            (c.high - max(c.open, c.close)) / span,
            (min(c.open, c.close) - c.low) / span,
            (c.close - c.low) / span,
        ))
    return result


def _distance(a: Sequence[tuple[float, ...]],
              b: Sequence[tuple[float, ...]], mode: SearchMode) -> float:
    n = len(a)
    if mode == "free":
        squared = [sum((x - y) ** 2 for x, y in zip(a[i], b[i])) / len(a[i])
                   for i in range(n)]
        return math.sqrt(sum(squared) / n)

    # Five equally weighted stages. Each stage contributes one fifth of the
    # total distance, independent of its absolute candle count.
    stage_errors = []
    for stage in range(5):
        lo = stage * n // 5
        hi = (stage + 1) * n // 5
        if hi <= lo:
            raise ValueError("five_stage mode requires at least five candles")
        err = [sum((x - y) ** 2 for x, y in zip(a[i], b[i])) / len(a[i])
               for i in range(lo, hi)]
        stage_errors.append(sum(err) / len(err))
    return math.sqrt(sum(stage_errors) / 5)


def _outcomes(candles: Sequence[Candle], end: int,
              horizons: Sequence[int]) -> tuple[dict[int, float | None], float | None, float | None]:
    entry = candles[end].close
    max_h = max(horizons, default=0)
    if end + 1 >= len(candles):
        return ({h: None for h in horizons}, None, None)
    future = candles[end + 1:min(len(candles), end + max_h + 1)]
    if not future:
        return ({h: None for h in horizons}, None, None)
    returns = {
        h: (candles[end + h].close / entry - 1.0)
        if end + h < len(candles) else None
        for h in horizons
    }
    mfe = max(c.high for c in future) / entry - 1.0
    mae = min(c.low for c in future) / entry - 1.0
    return returns, mfe, mae


def search_analogs(
    candles: Sequence[Candle],
    *,
    query_start: int,
    query_end: int,
    mode: SearchMode = "free",
    top_k: int = 10,
    horizons: Sequence[int] = (1, 4, 16),
    embargo: int | None = None,
) -> SearchResult:
    """Find earlier same-length windows and score their subsequent outcomes.

    The query is [query_start, query_end], inclusive. Candidates must end before query_start by at least the maximum forward
    horizon (and any larger requested embargo). Returned analog windows and
    their forward-outcome horizons are mutually non-overlapping. The caller should pass one contiguous,
    chronologically ordered segment so no candidate crosses a data gap.
    """
    if mode not in ("free", "five_stage"):
        raise ValueError("mode must be 'free' or 'five_stage'")
    if isinstance(top_k, bool) or top_k < 1:
        raise ValueError("top_k must be >= 1")
    if not candles or query_start < 0 or query_end >= len(candles) or query_start > query_end:
        raise ValueError("invalid query bounds")
    length = query_end - query_start + 1
    if mode == "five_stage" and length < 5:
        raise ValueError("five_stage mode requires at least five candles")
    if any(h < 1 for h in horizons):
        raise ValueError("horizons must be positive")
    max_horizon = max(horizons, default=0)
    gap = max_horizon if embargo is None else max(embargo, max_horizon)
    if gap < 0:
        raise ValueError("embargo must be nonnegative")

    step = interval_to_ms(candles[0].interval)
    # Prefix counts make continuity checks O(1), even when scanning hundreds
    # of thousands of overlapping candidate windows.
    gap_prefix = [0] * len(candles)
    for index in range(1, len(candles)):
        gap_prefix[index] = gap_prefix[index - 1] + int(
            candles[index].open_time - candles[index - 1].open_time != step
        )

    def is_contiguous(start: int, end: int) -> bool:
        if start < 0 or end >= len(candles) or start > end:
            return False
        return gap_prefix[end] == gap_prefix[start]

    if not is_contiguous(query_start, query_end):
        raise ValueError("query window crosses a missing-candle gap; choose a fully contiguous latest window")

    query = _shape(candles[query_start:query_end + 1])
    last_candidate_end = query_start - gap - 1
    examined = 0
    ranked: list[tuple[float, int]] = []
    for end in range(length - 1, last_candidate_end + 1):
        start = end - length + 1
        # Both the candidate shape and its maximum forward outcome must be continuous.
        if not is_contiguous(start, end):
            continue
        if max_horizon and not is_contiguous(end, end + max_horizon):
            continue
        candidate = _shape(candles[start:end + 1])
        distance = _distance(query, candidate, mode)
        ranked.append((distance, start))
        examined += 1

    ranked.sort(key=lambda item: (item[0], item[1]))
    analogs = []
    selected_ranges: list[tuple[int, int]] = []
    for distance, start in ranked:
        end = start + length - 1
        outcome_end = end + max_horizon
        range_start = candles[start].open_time
        range_end = candles[outcome_end].close_time if max_horizon else candles[end].close_time
        if any(not (range_end < previous_start or previous_end < range_start)
               for previous_start, previous_end in selected_ranges):
            continue
        returns, mfe, mae = _outcomes(candles, end, horizons)
        analogs.append(Analog(
            start, end, candles[start].open_time, candles[end].open_time,
            1.0 / (1.0 + distance), returns, mfe, mae,
        ))
        selected_ranges.append((range_start, range_end))
        if len(analogs) >= top_k:
            break
    return SearchResult(mode, query_start, query_end, length, examined, tuple(analogs))
