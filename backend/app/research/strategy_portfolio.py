"""Diversification diagnostics for aligned walk-forward strategy variants."""
from __future__ import annotations

from math import sqrt
from statistics import mean, pstdev
from typing import Sequence, Any


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    ml, mr = mean(left), mean(right)
    dl = [value - ml for value in left]
    dr = [value - mr for value in right]
    denom = sqrt(sum(value * value for value in dl) * sum(value * value for value in dr))
    return sum(a * b for a, b in zip(dl, dr)) / denom if denom else None


def analyze_strategy_portfolio(
    returns_by_strategy: dict[str, Sequence[float]],
) -> dict[str, Any]:
    if not isinstance(returns_by_strategy, dict) or len(returns_by_strategy) < 2:
        raise ValueError("at least two aligned strategies are required")
    lengths = {len(values) for values in returns_by_strategy.values()}
    if len(lengths) != 1 or not lengths or next(iter(lengths)) < 2:
        raise ValueError("strategies must have at least two aligned folds")
    names = list(returns_by_strategy)
    series = {name: [float(value) for value in values] for name, values in returns_by_strategy.items()}
    if any(not __import__("math").isfinite(value) for values in series.values() for value in values):
        raise ValueError("returns must be finite")
    correlations = {}
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            correlations[f"{left}|{right}"] = _correlation(series[left], series[right])
    equal_weight = [
        sum(series[name][index] for name in names) / len(names)
        for index in range(next(iter(lengths)))
    ]
    individual = {
        name: {
            "average_return_per_fold": mean(values),
            "volatility_per_fold": pstdev(values),
            "positive_fold_rate": sum(value > 0 for value in values) / len(values),
            "cumulative_return_sum": sum(values),
        }
        for name, values in series.items()
    }
    portfolio = {
        "average_return_per_fold": mean(equal_weight),
        "volatility_per_fold": pstdev(equal_weight),
        "positive_fold_rate": sum(value > 0 for value in equal_weight) / len(equal_weight),
        "cumulative_return_sum": sum(equal_weight),
    }
    return {
        "method": "equal_weight_aligned_fold_diversification_diagnostic",
        "aligned_folds": next(iter(lengths)),
        "strategies": names,
        "individual_metrics": individual,
        "pairwise_return_correlation": correlations,
        "equal_weight_portfolio": portfolio,
        "interpretation": (
            "Equal-weight fold arithmetic is a diversification diagnostic only. "
            "It does not model concurrent positions, capital constraints, turnover, "
            "compounding, position sizing, or execution interactions."
        ),
    }
