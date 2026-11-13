"""Optional STUMPY adapter for query-to-history motif discovery.

STUMPY is deliberately imported lazily: the core backend and its test suite
remain usable without the research extra installed. This adapter returns
similarity candidates only; it never reads or scores future outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


@dataclass(frozen=True, slots=True)
class MotifMatch:
    start_index: int
    distance: float


def find_query_matches(
    history: Iterable[float],
    query: Iterable[float],
    *,
    top_k: int = 10,
    exclusion_zone: int | None = None,
) -> list[MotifMatch]:
    """Find non-overlapping query matches in a 1-D historical series.

    Inputs should be finite, point-in-time features (for example closed-candle
    log returns). The caller is responsible for splitting data at timestamp
    gaps and for keeping the query interval outside the history interval.

    The returned distance is STUMPY's z-normalized Euclidean MASS distance.
    It is a similarity measure, not a probability or forecast.
    """
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be an integer >= 1")

    try:
        import numpy as np
        import stumpy
    except ImportError as exc:
        raise RuntimeError(
            "STUMPY adapter is optional; install backend/requirements-research.txt"
        ) from exc

    history_values = np.asarray(list(history), dtype=np.float64)
    query_values = np.asarray(list(query), dtype=np.float64)
    if history_values.ndim != 1 or query_values.ndim != 1:
        raise ValueError("history and query must be one-dimensional")
    if query_values.size < 3:
        raise ValueError("query must contain at least 3 observations")
    if history_values.size < query_values.size:
        raise ValueError("history must be at least as long as query")
    if not np.isfinite(history_values).all() or not np.isfinite(query_values).all():
        raise ValueError("history and query must contain only finite values")

    m = int(query_values.size)
    zone = m if exclusion_zone is None else exclusion_zone
    if isinstance(zone, bool) or not isinstance(zone, int) or zone < 0:
        raise ValueError("exclusion_zone must be a nonnegative integer")

    distances = np.asarray(stumpy.mass(query_values, history_values), dtype=np.float64)
    expected = history_values.size - m + 1
    if distances.ndim != 1 or distances.size != expected:
        raise RuntimeError("STUMPY returned an unexpected MASS profile shape")

    ranked = [
        (float(distance), index)
        for index, distance in enumerate(distances)
        if math.isfinite(float(distance))
    ]
    ranked.sort(key=lambda item: (item[0], item[1]))

    selected: list[MotifMatch] = []
    for distance, index in ranked:
        if any(abs(index - match.start_index) < max(zone, m) for match in selected):
            continue
        selected.append(MotifMatch(start_index=index, distance=distance))
        if len(selected) >= top_k:
            break
    return selected
