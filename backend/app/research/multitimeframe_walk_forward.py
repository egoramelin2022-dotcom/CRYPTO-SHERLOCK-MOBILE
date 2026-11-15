"""Independent chronological validation for multi-timeframe analogue search.

Each fold is evaluated at a historical 15m close. Analogue search is anchored
strictly before the query window and its built-in outcome embargo prevents
training outcomes from reaching the test period. Realized test outcomes are
evaluated only after the decision point. This module is an audit, not a signal.
"""
from __future__ import annotations

from statistics import median
from typing import Any, Mapping, Sequence

from app.market_data.candles import Candle
from app.research.multitimeframe_pattern_intelligence import (
    MultiTimeframeSearchConfig,
    search_multitimeframe_analogs,
)
from app.research.outcome_evaluation import evaluate_forward_path


def _stats(values: Sequence[float]) -> dict[str, float | int]:
    total = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        total += value
        peak = max(peak, total)
        max_drawdown = max(max_drawdown, peak - total)
    count = len(values)
    return {
        "folds": count,
        "mean_net_return": sum(values) / count if count else 0.0,
        "median_net_return": median(values) if count else 0.0,
        "positive_fold_rate": sum(value > 0 for value in values) / count if count else 0.0,
        "cumulative_return_sum": total,
        "max_drawdown_sum_basis": max_drawdown,
    }


def run_multitimeframe_walk_forward(
    series: Mapping[str, Sequence[Candle]],
    *,
    config: MultiTimeframeSearchConfig | None = None,
    min_training_candles: int = 20_000,
    max_folds: int = 30,
    candidate_budget: int = 2_000,
    momentum_threshold: float = 0.005,
) -> dict[str, Any]:
    """Run a fixed, chronological, non-overlapping MTF holdout audit.

    No parameter optimization occurs inside this function. At each fold the
    model selects LONG/SHORT only if the median net outcome of retrieved
    analogues is positive and exceeds the opposite side; otherwise it abstains.
    Baselines: always LONG, always SHORT, FLAT, and query-window momentum.
    Returns are equal-notional fold returns (not compounded account returns).
    """
    base = config or MultiTimeframeSearchConfig()
    if set(series) != {"15m", "1h", "4h", "1d"}:
        raise ValueError("series must contain exactly 15m, 1h, 4h and 1d")
    candles = series["15m"]
    if not candles:
        raise ValueError("15m candles must not be empty")
    if isinstance(min_training_candles, bool) or not isinstance(min_training_candles, int) or min_training_candles < 1:
        raise ValueError("min_training_candles must be a positive integer")
    if isinstance(max_folds, bool) or not isinstance(max_folds, int) or not 2 <= max_folds <= 100:
        raise ValueError("max_folds must be an integer in [2, 100]")
    if isinstance(candidate_budget, bool) or not isinstance(candidate_budget, int) or not 100 <= candidate_budget <= 5000:
        raise ValueError("candidate_budget must be an integer in [100, 5000]")
    if momentum_threshold < 0:
        raise ValueError("momentum_threshold must be nonnegative")

    window = int(base.window_lengths["15m"])
    max_horizon = max(base.horizons_15m)
    first_end = max(min_training_candles, window + max_horizon) - 1
    last_end = len(candles) - 1 - max_horizon
    fold_spacing = window + max_horizon
    if last_end < first_end:
        raise ValueError("not enough history for independent MTF walk-forward folds")
    possible = ((last_end - first_end) // fold_spacing) + 1
    fold_count = min(max_folds, possible)
    if fold_count < 2:
        raise ValueError("not enough independent MTF test folds; at least two are required")
    fold_ends = [first_end + i * fold_spacing for i in range(fold_count)]

    returns: dict[str, dict[int, list[float]]] = {
        name: {h: [] for h in base.horizons_15m}
        for name in ("mtf_analogs", "always_long", "always_short", "flat", "momentum")
    }
    folds: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    stride = max(1, (first_end + 1 - window - max_horizon) // candidate_budget)
    search_config = MultiTimeframeSearchConfig(
        window_lengths=base.window_lengths,
        timeframe_weights=base.timeframe_weights,
        top_k=base.top_k,
        candidate_stride=max(base.candidate_stride, stride),
        horizons_15m=base.horizons_15m,
        embargo_15m=max(base.embargo_15m or 0, max_horizon),
        fee_bps_per_side=base.fee_bps_per_side,
        slippage_bps_per_side=base.slippage_bps_per_side,
        deduplicate_higher_timeframe_context=base.deduplicate_higher_timeframe_context,
    )

    for number, query_end in enumerate(fold_ends, start=1):
        query_start = query_end - window + 1
        try:
            search = search_multitimeframe_analogs(
                series, query_end_index_15m=query_end, config=search_config
            )
            actual = evaluate_forward_path(
                candles, candidate_end_index=query_end,
                horizons=base.horizons_15m,
                fee_bps_per_side=base.fee_bps_per_side,
                slippage_bps_per_side=base.slippage_bps_per_side,
            )
        except ValueError as exc:
            skipped.append({"fold": number, "query_end_time": candles[query_end].close_time,
                            "reason": str(exc)})
            continue
        if not search.analogs:
            skipped.append({"fold": number, "query_end_time": candles[query_end].close_time,
                            "reason": "no eligible historical analogues"})
            continue

        query_return = candles[query_end].close / candles[query_start].close - 1.0
        momentum_side = (
            "LONG" if query_return > momentum_threshold else
            "SHORT" if query_return < -momentum_threshold else "FLAT"
        )
        horizon_results: dict[str, Any] = {}
        for outcome in actual.outcomes:
            if outcome is None:
                continue
            horizon = outcome.horizon
            analog_long, analog_short = [], []
            for analog in search.analogs:
                rows = analog.forward_outcomes.get("outcomes", [])
                match = next((row for row in rows if row and row["horizon"] == horizon), None)
                if match:
                    analog_long.append(float(match["long_net_return"]))
                    analog_short.append(float(match["short_net_return"]))
            if not analog_long or not analog_short:
                continue
            expected_long, expected_short = median(analog_long), median(analog_short)
            if expected_long > 0 and expected_long > expected_short:
                side = "LONG"
                model_return = outcome.long_net_return
            elif expected_short > 0 and expected_short > expected_long:
                side = "SHORT"
                model_return = outcome.short_net_return
            else:
                side, model_return = "FLAT", 0.0
            momentum_return = (
                outcome.long_net_return if momentum_side == "LONG" else
                outcome.short_net_return if momentum_side == "SHORT" else 0.0
            )
            values = {
                "mtf_analogs": model_return,
                "always_long": outcome.long_net_return,
                "always_short": outcome.short_net_return,
                "flat": 0.0,
                "momentum": momentum_return,
            }
            for name, value in values.items():
                returns[name][horizon].append(float(value))
            horizon_results[str(horizon)] = {
                "predicted_side": side,
                "momentum_side": momentum_side,
                "analogue_count": len(analog_long),
                "median_analogue_long_net": expected_long,
                "median_analogue_short_net": expected_short,
                "realized_long_net": outcome.long_net_return,
                "realized_short_net": outcome.short_net_return,
                "strategy_net_returns": values,
            }
        folds.append({
            "fold": number,
            "query_start_time": candles[query_start].open_time,
            "query_end_time": candles[query_end].close_time,
            "training_data_end_time": candles[query_start - 1].close_time,
            "candidate_count_examined": search.candidates_examined,
            "analogue_count": len(search.analogs),
            "horizons": horizon_results,
        })

    metrics = {
        str(horizon): {
            name: _stats(values[horizon])
            for name, values in returns.items()
        }
        for horizon in base.horizons_15m
    }
    return {
        "engine": "multitimeframe_independent_walk_forward",
        "validation_protocol": "expanding_history_non_overlapping_holdout",
        "symbol": candles[0].symbol,
        "interval": "15m",
        "fold_spacing_15m": fold_spacing,
        "query_window_15m": window,
        "horizons_15m": list(base.horizons_15m),
        "costs": {
            "fee_bps_per_side": base.fee_bps_per_side,
            "slippage_bps_per_side": base.slippage_bps_per_side,
        },
        "parameters_frozen": True,
        "parameter_optimization_performed": False,
        "folds_evaluated": len(folds),
        "folds_skipped": len(skipped),
        "fold_details": folds,
        "skipped_folds": skipped,
        "metrics_by_horizon": metrics,
        "interpretation": (
            "Independent chronological holdout diagnostics. Equal-notional fold "
            "returns are not compounded portfolio returns. Results do not prove "
            "future profitability; compare all baselines and inspect sample size."
        ),
    }
