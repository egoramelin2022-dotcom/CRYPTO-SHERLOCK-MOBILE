"""Combinatorially symmetric cross-validation diagnostics for aligned strategy variants.

This is a small-sample PBO-style diagnostic, not proof of future performance.
Only configurations sharing identical out-of-sample fold timestamps are eligible.
"""
from __future__ import annotations

from itertools import combinations
from math import log
from random import Random
from statistics import mean, median
from typing import Sequence, Any


def probability_of_backtest_overfitting(
    returns_by_strategy: dict[str, Sequence[float]],
    *,
    max_partitions: int = 512,
    seed: int = 17,
) -> dict[str, Any]:
    if not isinstance(returns_by_strategy, dict) or len(returns_by_strategy) < 2:
        raise ValueError("at least two strategy return series are required")
    if isinstance(max_partitions, bool) or not isinstance(max_partitions, int) or not 1 <= max_partitions <= 10000:
        raise ValueError("max_partitions must be an integer in [1, 10000]")
    names = list(returns_by_strategy)
    lengths = {len(returns_by_strategy[name]) for name in names}
    if len(lengths) != 1:
        raise ValueError("all strategy return series must have identical fold counts")
    n = lengths.pop()
    if n < 4 or n % 2:
        raise ValueError("at least four even-numbered aligned folds are required")
    matrix = []
    for name in names:
        row = [float(value) for value in returns_by_strategy[name]]
        if any(not __import__("math").isfinite(value) for value in row):
            raise ValueError("returns must be finite")
        matrix.append(row)

    half = n // 2
    total = __import__("math").comb(n, half)
    if total <= max_partitions:
        splits = list(combinations(range(n), half))
    else:
        rng = Random(seed)
        chosen: set[tuple[int, ...]] = set()
        while len(chosen) < max_partitions:
            chosen.add(tuple(sorted(rng.sample(range(n), half))))
        splits = sorted(chosen)

    logits: list[float] = []
    selected: list[str] = []
    for in_sample in splits:
        in_set = set(in_sample)
        out_sample = [index for index in range(n) if index not in in_set]
        in_scores = [mean(row[index] for index in in_sample) for row in matrix]
        winner = max(range(len(names)), key=lambda idx: (in_scores[idx], -idx))
        oos_scores = [mean(row[index] for index in out_sample) for row in matrix]
        ordered = sorted((score, idx) for idx, score in enumerate(oos_scores))
        rank = next(pos for pos, (_, idx) in enumerate(ordered, start=1) if idx == winner)
        # Mid-rank for exact ties prevents arbitrary ordering from inflating PBO.
        tied = sum(score == oos_scores[winner] for score in oos_scores)
        rank_fraction = (rank + 0.5 * (tied - 1)) / (len(names) + 1)
        rank_fraction = min(1.0 - 1e-12, max(1e-12, rank_fraction))
        logits.append(log(rank_fraction / (1.0 - rank_fraction)))
        selected.append(names[winner])

    return {
        "method": "combinatorially_symmetric_cross_validation_pbo",
        "pbo": sum(value < 0 for value in logits) / len(logits),
        "median_logit_rank": median(logits),
        "partitions_evaluated": len(splits),
        "partitions_possible": total,
        "strategies": names,
        "aligned_folds": n,
        "in_sample_winner_counts": {name: selected.count(name) for name in names},
        "interpretation": (
            "PBO estimates how often the in-sample winner ranks below the median "
            "among tested variants out of sample. It is conditional on this small "
            "candidate set and these historical folds; it is not a future-loss probability."
        ),
    }
