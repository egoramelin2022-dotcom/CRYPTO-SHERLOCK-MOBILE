"""Causal multi-timeframe historical analogue search.

Each candidate is sampled at a 15m decision close. For every timeframe,
the comparison window ends at the latest candle whose close_time is no later
than that decision time. This prevents unfinished 1h/4h/1d candles from
leaking into either the query or historical candidates.

The module ranks historical shape analogues. It does not emit trade signals.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, dataclass, field
import math
import statistics
from typing import Mapping, Sequence

from app.market_data.candles import Candle, find_gaps
from app.market_data.intervals import interval_to_ms
from app.research.outcome_evaluation import evaluate_forward_path


DEFAULT_WINDOW_LENGTHS = {"15m": 32, "1h": 16, "4h": 8, "1d": 5}
DEFAULT_TIMEFRAME_WEIGHTS = {"15m": 0.25, "1h": 0.25, "4h": 0.25, "1d": 0.25}


@dataclass(frozen=True, slots=True)
class MultiTimeframeSearchConfig:
    """Frozen, explicit settings for one multi-timeframe search."""

    window_lengths: Mapping[str, int] = field(
        default_factory=lambda: dict(DEFAULT_WINDOW_LENGTHS)
    )
    timeframe_weights: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TIMEFRAME_WEIGHTS)
    )
    top_k: int = 30
    candidate_stride: int = 4
    horizons_15m: tuple[int, ...] = (16, 96, 288, 480, 960)
    embargo_15m: int | None = None
    fee_bps_per_side: float = 5.0
    slippage_bps_per_side: float = 2.0
    deduplicate_higher_timeframe_context: bool = True


@dataclass(frozen=True, slots=True)
class TimeframeSimilarity:
    interval: str
    query_end_time: int
    candidate_end_time: int
    query_window_start_time: int
    candidate_window_start_time: int
    distance: float
    similarity: float


@dataclass(frozen=True, slots=True)
class MultiTimeframeAnalog:
    candidate_end_index_15m: int
    candidate_end_time: int
    decision_time: int
    similarity: float
    timeframe_scores: dict[str, TimeframeSimilarity]
    forward_outcomes: dict

    def to_dict(self) -> dict:
        return {
            "candidate_end_index_15m": self.candidate_end_index_15m,
            "candidate_end_time": self.candidate_end_time,
            "decision_time": self.decision_time,
            "similarity": self.similarity,
            "timeframe_scores": {
                key: asdict(value) for key, value in self.timeframe_scores.items()
            },
            "forward_outcomes": self.forward_outcomes,
        }


@dataclass(frozen=True, slots=True)
class MultiTimeframeSearchResult:
    symbol: str
    query_decision_time: int
    query_start_time_15m: int
    query_end_time_15m: int
    window_lengths: dict[str, int]
    timeframe_weights: dict[str, float]
    candidates_examined: int
    candidates_rejected_for_data: int
    candidates_rejected_for_overlap: int
    candidate_stride: int
    horizons_15m: tuple[int, ...]
    analogs: tuple[MultiTimeframeAnalog, ...]

    def to_dict(self) -> dict:
        return {
            "engine": "multitimeframe_pattern_intelligence",
            "engine_version": "0.1.0",
            "symbol": self.symbol,
            "query_decision_time": self.query_decision_time,
            "query_start_time_15m": self.query_start_time_15m,
            "query_end_time_15m": self.query_end_time_15m,
            "window_lengths": self.window_lengths,
            "timeframe_weights": self.timeframe_weights,
            "candidates_examined": self.candidates_examined,
            "candidates_rejected_for_data": self.candidates_rejected_for_data,
            "candidates_rejected_for_overlap": self.candidates_rejected_for_overlap,
            "candidate_stride": self.candidate_stride,
            "candidate_sampling": "uniform_15m_decision_stride",
            "horizons_15m": list(self.horizons_15m),
            "horizon_units": "15m candles",
            "analogs": [item.to_dict() for item in self.analogs],
            "causality": {
                "closed_candles_only": True,
                "higher_timeframe_rule": (
                    "latest candle with close_time <= decision_time"
                ),
                "candidate_forward_paths_excluded_from_query": True,
                "source_data_modified": False,
            },
            "interpretation": (
                "Historical shape analogues and realized forward outcomes only; "
                "not a forecast, probability, or trading signal."
            ),
        }


def _validate_config(config: MultiTimeframeSearchConfig) -> tuple[dict[str, int], dict[str, float]]:
    lengths = dict(config.window_lengths)
    weights = dict(config.timeframe_weights)
    required = set(DEFAULT_WINDOW_LENGTHS)
    if set(lengths) != required or set(weights) != required:
        raise ValueError("window_lengths and timeframe_weights must define exactly 15m, 1h, 4h, 1d")
    for interval, length in lengths.items():
        if isinstance(length, bool) or not isinstance(length, int) or length < 2:
            raise ValueError(f"window length for {interval} must be an integer >= 2")
    for interval, weight in weights.items():
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight < 0:
            raise ValueError(f"timeframe weight for {interval} must be finite and nonnegative")
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("at least one timeframe weight must be positive")
    weights = {key: value / total_weight for key, value in weights.items()}
    if isinstance(config.top_k, bool) or not isinstance(config.top_k, int) or config.top_k < 1:
        raise ValueError("top_k must be a positive integer")
    if isinstance(config.candidate_stride, bool) or not isinstance(config.candidate_stride, int) or config.candidate_stride < 1:
        raise ValueError("candidate_stride must be a positive integer")
    if not config.horizons_15m or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in config.horizons_15m
    ):
        raise ValueError("horizons_15m must contain positive integers")
    if len(set(config.horizons_15m)) != len(config.horizons_15m):
        raise ValueError("horizons_15m must not contain duplicates")
    if config.embargo_15m is not None and (
        isinstance(config.embargo_15m, bool)
        or not isinstance(config.embargo_15m, int)
        or config.embargo_15m < 0
    ):
        raise ValueError("embargo_15m must be a nonnegative integer")
    for name, value in (
        ("fee_bps_per_side", config.fee_bps_per_side),
        ("slippage_bps_per_side", config.slippage_bps_per_side),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value < 10_000:
            raise ValueError(f"{name} must be finite and in [0, 10000)")
    if config.fee_bps_per_side + config.slippage_bps_per_side >= 10_000:
        raise ValueError("combined per-side costs must be below 10000 bps")
    return lengths, weights


def _validate_timeframe(candles: Sequence[Candle], interval: str, symbol: str) -> list[int]:
    if not candles:
        raise ValueError(f"{interval} candles must not be empty")
    if interval_to_ms(interval) <= 0:
        raise ValueError(f"invalid interval: {interval}")
    previous = None
    for candle in candles:
        candle.validate()
        if candle.symbol != symbol or candle.interval != interval:
            raise ValueError(f"{interval} candles must use symbol {symbol} and interval {interval}")
        if previous is not None and candle.open_time <= previous:
            raise ValueError(f"{interval} candles must be strictly chronological")
        previous = candle.open_time
    return [c.close_time for c in candles]


def _is_contiguous(candles: Sequence[Candle], start: int, end: int) -> bool:
    if start < 0 or end >= len(candles) or start > end:
        return False
    if end - start < 1:
        return True
    step = interval_to_ms(candles[0].interval)
    return all(
        candles[index].open_time - candles[index - 1].open_time == step
        for index in range(start + 1, end + 1)
    )


def _closed_window(
    candles: Sequence[Candle], close_times: Sequence[int], decision_time: int, length: int
) -> tuple[int, int] | None:
    end = bisect_right(close_times, decision_time) - 1
    start = end - length + 1
    if start < 0 or not _is_contiguous(candles, start, end):
        return None
    return start, end


def _window_features(candles: Sequence[Candle]) -> list[tuple[float, ...]]:
    """Scale-free geometry, candle morphology, structure and volume descriptors."""
    if len(candles) < 2:
        raise ValueError("a pattern window requires at least two candles")
    base = candles[0].close
    log_returns = [
        math.log(candles[index].close / candles[index - 1].close)
        for index in range(1, len(candles))
    ]
    scale = max(statistics.pstdev(log_returns), 1e-6)
    volumes = [max(item.volume, 1e-12) for item in candles]
    median_volume = max(statistics.median(volumes), 1e-12)
    result: list[tuple[float, ...]] = []
    rolling_high: list[float] = []
    rolling_low: list[float] = []
    for index, candle in enumerate(candles):
        span = max(candle.high - candle.low, candle.open * 1e-12)
        body_return = (candle.close - candle.open) / candle.open
        upper_wick = (candle.high - max(candle.open, candle.close)) / span
        lower_wick = (min(candle.open, candle.close) - candle.low) / span
        close_location = (candle.close - candle.low) / span
        path = math.log(candle.close / base) / scale
        previous_return = (
            math.log(candle.close / candles[index - 1].close) / scale
            if index else 0.0
        )
        local_start = max(0, index - 3)
        local_high = max(item.high for item in candles[local_start:index + 1])
        local_low = min(item.low for item in candles[local_start:index + 1])
        structure_position = (
            (candle.close - local_low) / (local_high - local_low)
            if local_high > local_low else 0.5
        )
        volume_ratio = math.log(max(candle.volume, 1e-12) / median_volume)
        range_norm = (candle.high - candle.low) / candle.open / scale
        result.append((
            path,
            body_return / scale,
            upper_wick,
            lower_wick,
            close_location,
            previous_return,
            structure_position,
            volume_ratio,
            range_norm,
        ))
    return result


def _distance(left: Sequence[tuple[float, ...]], right: Sequence[tuple[float, ...]]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("feature windows must have equal nonzero length")
    # Explicit feature weights: price path, candle body, wicks, close location,
    # local structure, volume and range/volatility.
    weights = (0.22, 0.14, 0.08, 0.08, 0.08, 0.12, 0.10, 0.08, 0.10)
    squared = []
    for a, b in zip(left, right):
        squared.append(sum(weight * (x - y) ** 2 for weight, x, y in zip(weights, a, b)))
    return math.sqrt(sum(squared) / len(squared))


def search_multitimeframe_analogs(
    series: Mapping[str, Sequence[Candle]],
    *,
    query_end_index_15m: int,
    config: MultiTimeframeSearchConfig = MultiTimeframeSearchConfig(),
) -> MultiTimeframeSearchResult:
    """Find earlier, non-overlapping analogues using closed 15m/1h/4h/1d windows.

    Historical candidates are anchored to a 15m candle close. For each anchor,
    higher-timeframe windows are selected as-of that close, using only bars that
    have already closed. Candidate outcome paths are excluded from the query
    window by max(horizon)+embargo. Analogues sharing the same higher-timeframe
    context or overlapping shape/outcome ranges are de-duplicated.
    """
    lengths, weights = _validate_config(config)
    required = ("15m", "1h", "4h", "1d")
    if set(series) != set(required):
        raise ValueError("series must contain exactly 15m, 1h, 4h and 1d")
    first_15m = series["15m"]
    if not first_15m:
        raise ValueError("15m candles must not be empty")
    symbol = first_15m[0].symbol
    close_times = {
        interval: _validate_timeframe(series[interval], interval, symbol)
        for interval in required
    }
    for interval in required:
        if interval != "15m" and series[interval][0].symbol != symbol:
            raise ValueError("all timeframes must use the same symbol")
    if (
        isinstance(query_end_index_15m, bool)
        or not isinstance(query_end_index_15m, int)
        or not 0 <= query_end_index_15m < len(first_15m)
    ):
        raise ValueError("query_end_index_15m is outside 15m history")

    query_end = query_end_index_15m
    query_start = query_end - lengths["15m"] + 1
    if query_start < 0 or not _is_contiguous(first_15m, query_start, query_end):
        raise ValueError("15m query window is too short or crosses a missing-candle gap")
    query_decision_time = first_15m[query_end].close_time
    query_windows: dict[str, tuple[int, int]] = {}
    query_features: dict[str, list[tuple[float, ...]]] = {}
    for interval in required:
        window = _closed_window(series[interval], close_times[interval], query_decision_time, lengths[interval])
        if window is None:
            raise ValueError(f"insufficient or discontinuous closed {interval} query window")
        query_windows[interval] = window
        start, end = window
        query_features[interval] = _window_features(series[interval][start:end + 1])

    max_horizon = max(config.horizons_15m)
    embargo = max_horizon if config.embargo_15m is None else max(config.embargo_15m, max_horizon)
    last_candidate_end = query_start - embargo - 1
    examined = rejected_data = rejected_overlap = 0
    ranked: list[tuple[float, int, dict[str, TimeframeSimilarity], tuple[int, ...]]] = []

    for candidate_end in range(lengths["15m"] - 1, last_candidate_end + 1, config.candidate_stride):
        candidate_start = candidate_end - lengths["15m"] + 1
        if not _is_contiguous(first_15m, candidate_start, candidate_end):
            rejected_data += 1
            continue
        decision_time = first_15m[candidate_end].close_time
        timeframe_scores: dict[str, TimeframeSimilarity] = {}
        context_signature: list[int] = []
        weighted_distance = 0.0
        usable_weight = 0.0
        valid = True
        for interval in required:
            candidate_window = _closed_window(
                series[interval], close_times[interval], decision_time, lengths[interval]
            )
            if candidate_window is None:
                valid = False
                break
            start, end = candidate_window
            candidate_features = _window_features(series[interval][start:end + 1])
            distance = _distance(query_features[interval], candidate_features)
            similarity = 1.0 / (1.0 + distance)
            timeframe_scores[interval] = TimeframeSimilarity(
                interval=interval,
                query_end_time=series[interval][query_windows[interval][1]].close_time,
                candidate_end_time=series[interval][end].close_time,
                query_window_start_time=series[interval][query_windows[interval][0]].open_time,
                candidate_window_start_time=series[interval][start].open_time,
                distance=distance,
                similarity=similarity,
            )
            if interval != "15m":
                context_signature.append(end)
            weighted_distance += weights[interval] * distance
            usable_weight += weights[interval]
        if not valid or usable_weight <= 0:
            rejected_data += 1
            continue
        examined += 1
        combined_similarity = 1.0 / (1.0 + weighted_distance / usable_weight)
        ranked.append((combined_similarity, candidate_end, timeframe_scores, tuple(context_signature)))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    analogs: list[MultiTimeframeAnalog] = []
    selected_ranges: list[tuple[int, int]] = []
    selected_contexts: set[tuple[int, ...]] = set()
    outcome_horizon = max(config.horizons_15m)
    for similarity, candidate_end, scores, context_signature in ranked:
        candidate_start = candidate_end - lengths["15m"] + 1
        outcome_end = candidate_end + outcome_horizon
        range_start = first_15m[candidate_start].open_time
        range_end = first_15m[outcome_end].close_time
        if config.deduplicate_higher_timeframe_context and context_signature in selected_contexts:
            rejected_overlap += 1
            continue
        if any(not (range_end < prior_start or prior_end < range_start) for prior_start, prior_end in selected_ranges):
            rejected_overlap += 1
            continue
        try:
            forward = evaluate_forward_path(
                first_15m,
                candidate_end_index=candidate_end,
                horizons=config.horizons_15m,
                fee_bps_per_side=config.fee_bps_per_side,
                slippage_bps_per_side=config.slippage_bps_per_side,
            )
        except ValueError:
            rejected_data += 1
            continue
        analogs.append(MultiTimeframeAnalog(
            candidate_end_index_15m=candidate_end,
            candidate_end_time=first_15m[candidate_end].close_time,
            decision_time=first_15m[candidate_end].close_time,
            similarity=similarity,
            timeframe_scores=scores,
            forward_outcomes=forward.to_dict(),
        ))
        selected_ranges.append((range_start, range_end))
        selected_contexts.add(context_signature)
        if len(analogs) >= config.top_k:
            break

    return MultiTimeframeSearchResult(
        symbol=symbol,
        query_decision_time=query_decision_time,
        query_start_time_15m=first_15m[query_start].open_time,
        query_end_time_15m=first_15m[query_end].close_time,
        window_lengths=lengths,
        timeframe_weights=weights,
        candidates_examined=examined,
        candidates_rejected_for_data=rejected_data,
        candidates_rejected_for_overlap=rejected_overlap,
        candidate_stride=config.candidate_stride,
        horizons_15m=tuple(config.horizons_15m),
        analogs=tuple(analogs),
    )
