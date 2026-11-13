"""Expanding-window, leakage-aware walk-forward evaluation for Pattern Intelligence.

This is a fixed-method research audit, not strategy optimization. Each test
sample is matched only against candles strictly earlier than its start, with
an embargo covering the maximum forward outcome horizon. Test windows and
their outcome paths do not overlap.
"""
from __future__ import annotations

from statistics import median
from typing import Any, Sequence

from app.market_data.candles import Candle
from app.research.outcome_evaluation import evaluate_forward_path
from app.research.pattern_intelligence import search_analogs

DEFAULT_HORIZONS = (1, 4, 16, 32, 64)


def _summary(returns: list[float]) -> dict[str, float | int]:
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in returns:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
    return {
        "folds": len(returns),
        "cumulative_return_sum": cumulative,
        "average_return_per_fold": sum(returns) / len(returns) if returns else 0.0,
        "median_return_per_fold": median(returns) if returns else 0.0,
        "positive_fold_rate": (
            sum(value > 0 for value in returns) / len(returns) if returns else 0.0
        ),
        "max_drawdown_sum_basis": max_drawdown,
    }


def run_walk_forward(
    candles: Sequence[Candle],
    *,
    query_window: int = 40,
    mode: str = "free",
    top_k: int = 10,
    max_folds: int = 30,
    min_training_candles: int = 500,
    candidate_budget: int = 2000,
    fee_bps_per_side: float = 5.0,
    slippage_bps_per_side: float = 2.0,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> dict[str, Any]:
    """Evaluate analog-based directional decisions on chronological test folds.

    The model chooses LONG or SHORT only when the median analog net return
    after configured costs is positive and better than the opposite side.
    Otherwise it stays FLAT. Baselines are always-LONG, always-SHORT and FLAT.
    Returns are equal-notional per-fold sums, not compounded portfolio returns.
    """
    if isinstance(query_window, bool) or not isinstance(query_window, int) or not 5 <= query_window <= 500:
        raise ValueError("query_window must be an integer in [5, 500]")
    if mode not in ("free", "five_stage"):
        raise ValueError("mode must be 'free' or 'five_stage'")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 100:
        raise ValueError("top_k must be an integer in [1, 100]")
    if isinstance(max_folds, bool) or not isinstance(max_folds, int) or not 2 <= max_folds <= 100:
        raise ValueError("max_folds must be an integer in [2, 100]")
    if (isinstance(min_training_candles, bool) or not isinstance(min_training_candles, int)
            or min_training_candles < query_window + max(horizons, default=0) + 1):
        raise ValueError("min_training_candles must cover the query window and forward embargo")
    if isinstance(candidate_budget, bool) or not isinstance(candidate_budget, int) or not 100 <= candidate_budget <= 5000:
        raise ValueError("candidate_budget must be an integer in [100, 5000]")
    if not candles:
        raise ValueError("candles must not be empty")
    if not horizons or any(isinstance(h, bool) or not isinstance(h, int) or h < 1 for h in horizons):
        raise ValueError("horizons must be positive integers")
    if len(set(horizons)) != len(horizons):
        raise ValueError("horizons must not contain duplicates")

    first_candle = candles[0]
    previous = None
    for candle in candles:
        candle.validate()
        if candle.symbol != first_candle.symbol or candle.interval != first_candle.interval:
            raise ValueError("all candles must share symbol and interval")
        if previous is not None and candle.open_time <= previous:
            raise ValueError("candle timestamps must be strictly increasing")
        previous = candle.open_time

    max_horizon = max(horizons)
    first_test_start = min_training_candles
    last_test_start = len(candles) - query_window - max_horizon
    minimum_spacing = query_window + max_horizon
    if last_test_start < first_test_start:
        raise ValueError("not enough history for the requested training, query and forward windows")
    span = last_test_start - first_test_start
    possible_folds = span // minimum_spacing + 1
    fold_count = min(max_folds, possible_folds)
    if fold_count < 2:
        raise ValueError("not enough independent test folds; reduce min_training_candles or query_window")

    if fold_count == 1:
        fold_starts = [first_test_start]
    else:
        fold_starts = [
            first_test_start + round(index * span / (fold_count - 1))
            for index in range(fold_count)
        ]

    fold_rows: list[dict[str, Any]] = []
    per_horizon: dict[int, dict[str, list[float]]] = {
        horizon: {"model": [], "always_long": [], "always_short": [], "flat": []}
        for horizon in horizons
    }
    trade_returns = {horizon: [] for horizon in horizons}
    decision_counts = {
        horizon: {"LONG": 0, "SHORT": 0, "FLAT": 0} for horizon in horizons
    }
    skipped: list[dict[str, Any]] = []

    for fold_number, query_start in enumerate(fold_starts, start=1):
        query_end = query_start + query_window - 1
        eligible_candidates = max(0, query_start - query_window - max_horizon + 1)
        stride = max(1, (eligible_candidates + candidate_budget - 1) // candidate_budget)
        # The matcher and historical analog outcomes receive only data available
        # through the final candle of this query sample; future test candles are excluded.
        known_at_query_close = candles[:query_end + 1]
        try:
            search = search_analogs(
                known_at_query_close, query_start=query_start, query_end=query_end,
                mode=mode, top_k=top_k, horizons=horizons,
                candidate_stride=stride,
            )
            actual = evaluate_forward_path(
                candles, candidate_end_index=query_end, horizons=horizons,
                fee_bps_per_side=fee_bps_per_side,
                slippage_bps_per_side=slippage_bps_per_side,
            )
        except ValueError as exc:
            skipped.append({
                "fold": fold_number,
                "query_start_time": candles[query_start].open_time,
                "reason": str(exc),
            })
            continue

        if not search.analogs:
            skipped.append({
                "fold": fold_number,
                "query_start_time": candles[query_start].open_time,
                "reason": "no eligible historical analogs",
            })
            continue

        analog_outcomes = []
        for analog in search.analogs:
            outcome = evaluate_forward_path(
                known_at_query_close, candidate_end_index=analog.end_index, horizons=horizons,
                fee_bps_per_side=fee_bps_per_side,
                slippage_bps_per_side=slippage_bps_per_side,
            )
            analog_outcomes.append({
                item.horizon: item for item in outcome.outcomes if item is not None
            })

        horizon_decisions = {}
        for horizon in horizons:
            long_values = [
                row[horizon].long_net_return for row in analog_outcomes if horizon in row
            ]
            short_values = [
                row[horizon].short_net_return for row in analog_outcomes if horizon in row
            ]
            realized = next(
                (item for item in actual.outcomes if item is not None and item.horizon == horizon),
                None,
            )
            if not long_values or not short_values or realized is None:
                continue
            expected_long = median(long_values)
            expected_short = median(short_values)
            if expected_long > 0 and expected_long > expected_short:
                side = "LONG"
                model_return = realized.long_net_return
            elif expected_short > 0 and expected_short > expected_long:
                side = "SHORT"
                model_return = realized.short_net_return
            else:
                side = "FLAT"
                model_return = 0.0

            decision_counts[horizon][side] += 1
            if side != "FLAT":
                trade_returns[horizon].append(model_return)
            per_horizon[horizon]["model"].append(model_return)
            per_horizon[horizon]["always_long"].append(realized.long_net_return)
            per_horizon[horizon]["always_short"].append(realized.short_net_return)
            per_horizon[horizon]["flat"].append(0.0)
            horizon_decisions[str(horizon)] = {
                "predicted_side": side,
                "median_analog_long_net": expected_long,
                "median_analog_short_net": expected_short,
                "realized_long_net": realized.long_net_return,
                "realized_short_net": realized.short_net_return,
                "model_return": model_return,
                "always_long_return": realized.long_net_return,
                "always_short_return": realized.short_net_return,
                "flat_return": 0.0,
            }

        fold_rows.append({
            "fold": fold_number,
            "query_start_index": query_start,
            "query_end_index": query_end,
            "query_start_time": candles[query_start].open_time,
            "query_end_time": candles[query_end].open_time,
            "training_candles_available": query_start,
            "training_end_index": query_start - 1,
            "training_end_time": candles[query_start - 1].open_time,
            "known_data_end_index": query_end,
            "known_data_end_time": candles[query_end].open_time,
            "candidates_examined": search.candidates_examined,
            "candidate_stride": search.candidate_stride,
            "analog_count": len(search.analogs),
            "analogs": [
                {
                    "start_index": item.start_index,
                    "end_index": item.end_index,
                    "start_time": item.start_time,
                    "end_time": item.end_time,
                    "similarity": item.similarity,
                }
                for item in search.analogs
            ],
            "horizons": horizon_decisions,
        })

    metrics = {}
    for horizon, rows in per_horizon.items():
        metrics[str(horizon)] = {
            name: _summary(values) for name, values in rows.items()
        }
        model_metrics = metrics[str(horizon)]["model"]
        model_metrics["trades"] = decision_counts[horizon]["LONG"] + decision_counts[horizon]["SHORT"]
        model_metrics["flat_folds"] = decision_counts[horizon]["FLAT"]
        model_metrics["trade_rate"] = (
            model_metrics["trades"] / model_metrics["folds"]
            if model_metrics["folds"] else 0.0
        )
        model_metrics["positive_trade_rate"] = (
            sum(value > 0 for value in trade_returns[horizon]) / len(trade_returns[horizon])
            if trade_returns[horizon] else 0.0
        )

    return {
        "symbol": first_candle.symbol,
        "interval": first_candle.interval,
        "method": "expanding_window_historical_analog_median",
        "mode": mode,
        "query_window": query_window,
        "top_k": top_k,
        "requested_folds": max_folds,
        "evaluated_folds": len(fold_rows),
        "skipped_folds": skipped,
        "candidate_budget_per_fold": candidate_budget,
        "fee_bps_per_side": fee_bps_per_side,
        "slippage_bps_per_side": slippage_bps_per_side,
        "horizons": list(horizons),
        "folds": fold_rows,
        "metrics_by_horizon": metrics,
        "baselines": ["always_long", "always_short_theoretical", "flat"],
        "return_accounting": "equal_notional_per_fold_sum; not compounded",
        "anti_leakage": {
            "training_is_strictly_before_test_start": True,
            "future_candles_excluded_from_analog_search": True,
            "candidate_forward_outcomes_end_before_test_start": True,
            "embargo_candles": max_horizon,
            "test_windows_and_forward_paths_non_overlapping": True,
            "gaps_crossed_by_query_or_forward_paths_are_skipped": True,
        },
        "limitations": [
            "Fixed similarity method and parameters; no parameter optimization is performed.",
            "Fold outcomes are historical research, not live or executable strategy performance.",
            "SHORT returns are theoretical unlevered price-return arithmetic, not a margin, borrow or liquidation model.",
            "Equal-notional fold sums do not model portfolio sizing, compounding, capital constraints or concurrent positions.",
            "A FLAT decision is abstention when median analog returns after costs do not favor either direction; it is not a market-regime classifier.",
        ],
        "interpretation": "Out-of-sample historical validation only; not a forecast, probability or trading signal.",
    }
