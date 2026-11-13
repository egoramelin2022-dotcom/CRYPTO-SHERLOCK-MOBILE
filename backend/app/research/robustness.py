"""Bounded parameter-sensitivity audit for walk-forward research.

This is a robustness diagnostic, not PBO/CSCV and not an optimizer. Each
configuration is evaluated independently with the leakage-aware walk-forward
engine; scores are never pooled across different parameterizations.
"""
from __future__ import annotations

from typing import Any, Sequence
from statistics import median

from app.market_data.candles import Candle
from app.research.walk_forward import run_walk_forward


def run_robustness_audit(
    candles: Sequence[Candle],
    *,
    query_window: int = 40,
    mode: str = "free",
    top_k: int = 10,
    max_folds: int = 20,
    min_training_candles: int = 500,
    candidate_budget: int = 1000,
    fee_bps_per_side: float = 5.0,
    slippage_bps_per_side: float = 2.0,
) -> dict[str, Any]:
    """Compare a small, predeclared neighborhood around the requested settings."""
    if not 5 <= query_window <= 500:
        raise ValueError("query_window must be in [5, 500]")
    if not 1 <= top_k <= 100:
        raise ValueError("top_k must be in [1, 100]")

    shorter = max(5, round(query_window * 0.8))
    longer = min(500, round(query_window * 1.2))
    configs = [
        ("baseline", query_window, top_k),
        ("shorter_window", shorter, top_k),
        ("longer_window", longer, top_k),
        ("fewer_analogs", query_window, max(1, round(top_k * 0.5))),
        ("more_analogs", query_window, min(100, max(top_k + 1, round(top_k * 1.5)))),
    ]
    unique: list[tuple[str, int, int]] = []
    seen: set[tuple[int, int]] = set()
    for name, window, analog_count in configs:
        key = (window, analog_count)
        if key not in seen:
            unique.append((name, window, analog_count))
            seen.add(key)

    runs: list[dict[str, Any]] = []
    for name, window, analog_count in unique:
        training = max(min_training_candles, window + 65)
        result = run_walk_forward(
            candles,
            query_window=window,
            mode=mode,
            top_k=analog_count,
            max_folds=max_folds,
            min_training_candles=training,
            candidate_budget=candidate_budget,
            fee_bps_per_side=fee_bps_per_side,
            slippage_bps_per_side=slippage_bps_per_side,
        )
        horizons: dict[str, Any] = {}
        for horizon, metrics in result["metrics_by_horizon"].items():
            model = metrics["model"]
            baseline_means = [
                metrics[key]["average_return_per_fold"]
                for key in ("always_long", "always_short", "flat")
            ]
            horizons[horizon] = {
                "evaluated_folds": model["folds"],
                "trades": model["trades"],
                "trade_rate": model["trade_rate"],
                "average_return_per_fold": model["average_return_per_fold"],
                "positive_fold_rate": model["positive_fold_rate"],
                "positive_trade_rate": model["positive_trade_rate"],
                "best_baseline_average_return": max(baseline_means),
                "excess_vs_best_baseline": (
                    model["average_return_per_fold"] - max(baseline_means)
                ),
            }
        runs.append({
            "configuration": name,
            "query_window": window,
            "top_k": analog_count,
            "min_training_candles": training,
            "evaluated_folds": result["evaluated_folds"],
            "skipped_fold_count": len(result["skipped_folds"]),
            "metrics_by_horizon": horizons,
        })

    horizon_keys = sorted(
        {key for run in runs for key in run["metrics_by_horizon"]},
        key=lambda value: int(value),
    )
    stability: dict[str, Any] = {}
    for horizon in horizon_keys:
        rows = [
            run["metrics_by_horizon"][horizon]
            for run in runs if horizon in run["metrics_by_horizon"]
            and run["metrics_by_horizon"][horizon]["evaluated_folds"] > 0
        ]
        stability[horizon] = {
            "configurations_evaluated": len(rows),
            "positive_average_return_share": (
                sum(row["average_return_per_fold"] > 0 for row in rows) / len(rows)
                if rows else 0.0
            ),
            "positive_excess_vs_best_baseline_share": (
                sum(row["excess_vs_best_baseline"] > 0 for row in rows) / len(rows)
                if rows else 0.0
            ),
            "median_average_return_per_fold": (
                median(row["average_return_per_fold"] for row in rows)
                if rows else 0.0
            ),
            "median_excess_vs_best_baseline": (
                median(row["excess_vs_best_baseline"] for row in rows)
                if rows else 0.0
            ),
        }

    return {
        "symbol": candles[0].symbol if candles else None,
        "interval": candles[0].interval if candles else None,
        "method": "bounded_one_factor_at_a_time_sensitivity",
        "configurations_requested": len(configs),
        "configurations_evaluated": len(runs),
        "runs": runs,
        "stability_by_horizon": stability,
        "selection_policy": (
            "No best configuration is selected. Each parameterization is reported "
            "independently; results are not pooled and are not used to retune the model."
        ),
        "limitations": [
            "This is a small local sensitivity neighborhood, not an exhaustive parameter search.",
            "It is not Probability of Backtest Overfitting (PBO), CSCV, or a statistical significance test.",
            "All configurations share the same historical dataset, so this audit does not create an independent final holdout.",
            "Positive historical stability does not establish future profitability or executable performance.",
        ],
    }
