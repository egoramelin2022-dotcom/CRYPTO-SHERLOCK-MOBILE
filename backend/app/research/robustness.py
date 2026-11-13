"""Bounded parameter-sensitivity audit for walk-forward research.

This is a robustness diagnostic, not PBO/CSCV and not an optimizer. Each
configuration is evaluated independently with the leakage-aware walk-forward
engine; scores are never pooled across different parameterizations.
"""
from __future__ import annotations

from statistics import median
from typing import Any, Sequence

from app.market_data.candles import Candle
from app.research.walk_forward import run_walk_forward
from app.research.anti_overfitting import probability_of_backtest_overfitting
from app.research.strategy_portfolio import analyze_strategy_portfolio


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
    if isinstance(query_window, bool) or not isinstance(query_window, int) or not 5 <= query_window <= 500:
        raise ValueError("query_window must be an integer in [5, 500]")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 100:
        raise ValueError("top_k must be an integer in [1, 100]")
    if mode not in ("free", "five_stage"):
        raise ValueError("mode must be free or five_stage")

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
    aligned_fold_returns: dict[str, dict[str, dict[int, float]]] = {}
    for name, window, analog_count in unique:
        training = max(min_training_candles, window + 65)
        try:
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
        except ValueError as exc:
            if ("not enough history" not in str(exc)
                    and "not enough independent test folds" not in str(exc)):
                raise
            runs.append({
                "configuration": name,
                "query_window": window,
                "top_k": analog_count,
                "min_training_candles": training,
                "max_folds": max_folds,
                "candidate_budget": candidate_budget,
                "status": "skipped",
                "reason": str(exc),
                "evaluated_folds": 0,
                "skipped_fold_count": 0,
                "metrics_by_horizon": {},
            })
            continue

        # Pair only analog-count variants that share the exact query timestamps.
        if name in ("baseline", "fewer_analogs", "more_analogs"):
            by_horizon: dict[str, dict[int, float]] = {}
            for horizon in result["horizons"]:
                by_time = {}
                for fold in result["folds"]:
                    outcome = fold.get("horizons", {}).get(str(horizon))
                    if outcome is not None:
                        by_time[fold["query_start_time"]] = float(outcome["model_return"])
                by_horizon[str(horizon)] = by_time
            aligned_fold_returns[name] = by_horizon

        horizons: dict[str, Any] = {}
        for horizon, metrics in result["metrics_by_horizon"].items():
            model = metrics["model"]
            baseline_means = [
                metrics[key]["average_return_per_fold"]
                for key in ("always_long", "always_short", "flat")
            ]
            best_baseline = max(baseline_means)
            horizons[horizon] = {
                "evaluated_folds": model["folds"],
                "trades": model["trades"],
                "trade_rate": model["trade_rate"],
                "average_return_per_fold": model["average_return_per_fold"],
                "positive_fold_rate": model["positive_fold_rate"],
                "positive_trade_rate": model["positive_trade_rate"],
                "best_baseline_average_return": best_baseline,
                "excess_vs_best_baseline": model["average_return_per_fold"] - best_baseline,
            }
        runs.append({
            "configuration": name,
            "query_window": window,
            "top_k": analog_count,
            "min_training_candles": training,
            "max_folds": max_folds,
            "candidate_budget": candidate_budget,
            "status": "completed",
            "evaluated_folds": result["evaluated_folds"],
            "skipped_fold_count": len(result["skipped_folds"]),
            "metrics_by_horizon": horizons,
        })

    pbo_by_horizon: dict[str, Any] = {}
    portfolio_by_horizon: dict[str, Any] = {}
    paired_names = [name for name in ("baseline", "fewer_analogs", "more_analogs")
                    if name in aligned_fold_returns]
    for horizon in sorted(
        {key for name in paired_names for key in aligned_fold_returns[name]},
        key=lambda value: int(value),
    ):
        available = [aligned_fold_returns[name].get(horizon, {}) for name in paired_names]
        common_times = sorted(set.intersection(*(set(row) for row in available))) if available else []
        if len(common_times) < 4 or len(common_times) % 2:
            pbo_by_horizon[horizon] = {"status": "insufficient_aligned_folds", "aligned_folds": len(common_times), "minimum_even_folds": 4}
            portfolio_by_horizon[horizon] = {"status": "insufficient_aligned_folds", "aligned_folds": len(common_times)}
            continue
        matrix = {
            name: [aligned_fold_returns[name][horizon][timestamp] for timestamp in common_times]
            for name in paired_names
        }
        pbo_by_horizon[horizon] = {"status": "completed", **probability_of_backtest_overfitting(matrix)}
        portfolio_by_horizon[horizon] = {"status": "completed", **analyze_strategy_portfolio(matrix)}

    horizon_keys = sorted(
        {key for run in runs for key in run["metrics_by_horizon"]},
        key=lambda value: int(value),
    )
    stability: dict[str, Any] = {}
    for horizon in horizon_keys:
        rows = [
            run["metrics_by_horizon"][horizon]
            for run in runs
            if run["status"] == "completed"
            and horizon in run["metrics_by_horizon"]
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
                median(row["average_return_per_fold"] for row in rows) if rows else 0.0
            ),
            "median_excess_vs_best_baseline": (
                median(row["excess_vs_best_baseline"] for row in rows) if rows else 0.0
            ),
        }

    return {
        "symbol": candles[0].symbol if candles else None,
        "interval": candles[0].interval if candles else None,
        "method": "bounded_one_factor_at_a_time_sensitivity",
        "mode": mode,
        "baseline_query_window": query_window,
        "baseline_top_k": top_k,
        "max_folds": max_folds,
        "candidate_budget_per_fold": candidate_budget,
        "fee_bps_per_side": fee_bps_per_side,
        "slippage_bps_per_side": slippage_bps_per_side,
        "configurations_requested": len(configs),
        "configurations_attempted": len(runs),
        "configurations_evaluated": sum(run["status"] == "completed" for run in runs),
        "configurations_with_oos_folds": sum(run["evaluated_folds"] > 0 for run in runs),
        "runs": runs,
        "stability_by_horizon": stability,
        "pbo_by_horizon": pbo_by_horizon,
        "strategy_portfolio_by_horizon": portfolio_by_horizon,
        "paired_diagnostic_configurations": paired_names,
        "selection_policy": (
            "No best configuration is selected. Each parameterization is reported "
            "independently; results are not pooled and are not used to retune the model."
        ),
        "limitations": [
            "This is a small local sensitivity neighborhood, not an exhaustive parameter search.",
            "PBO is estimated only across baseline/fewer/more analog-count variants on identical fold timestamps; it is conditional on this small candidate set, not a probability of future loss.",
            "The equal-weight strategy portfolio is a paired diagnostic of analog-count variants, not a capital allocation or executable portfolio model.",
            "All configurations share the same historical dataset, so this audit does not create an independent final holdout.",
            "The best simple baseline is selected retrospectively on the same evaluation run and is an optimistic reference hurdle.",
            "Query-window changes can shift exact fold boundaries; configurations are independent diagnostics, not a paired experiment.",
            "Positive historical stability does not establish future profitability or executable performance.",
        ],
    }
