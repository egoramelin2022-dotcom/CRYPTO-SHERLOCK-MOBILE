"""Sherlock Intelligence Core: deterministic orchestration of research modules.

The Core coordinates historical pattern discovery, causal regime description,
and cost-adjusted analogue outcomes. It preserves module provenance, surfaces
cross-module tension, and explicitly abstains from claiming a forecast.
"""
from __future__ import annotations

from statistics import mean, median
import math
from typing import Any, Sequence
from uuid import UUID, uuid4

from app.market_data.candles import Candle, find_gaps
from app.research.outcome_evaluation import evaluate_forward_path
from app.research.pattern_intelligence import SearchMode, search_analogs
from app.research.regime_detection import classify_regime

CORE_VERSION = "0.1.0"
DEFAULT_HORIZONS = (1, 4, 16, 32, 64)


def _validate_positive_integer(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _regime_consistency(regime: str | None, side: str) -> str:
    if side not in ("LONG", "SHORT"):
        return "not_directional"
    if regime == "TREND_UP":
        return "aligned" if side == "LONG" else "opposed"
    if regime == "TREND_DOWN":
        return "aligned" if side == "SHORT" else "opposed"
    if regime is None:
        return "unavailable"
    return "non_directional_regime"


def run_intelligence_core(
    candles: Sequence[Candle],
    *,
    query_start_index: int,
    query_end_index: int,
    mode: SearchMode = "free",
    top_k: int = 20,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    min_analogs: int = 5,
    candidate_stride: int = 1,
    fee_bps_per_side: float = 5.0,
    slippage_bps_per_side: float = 2.0,
    regime_lookback: int = 96,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Coordinate the core research modules for one fixed query window.

    The Core does not train a model, calibrate probabilities, issue a trading
    signal, or execute orders. It is a reproducible research coordinator:
    discovery -> causal context -> cost-adjusted outcomes -> conflict audit.
    """
    _validate_positive_integer("min_analogs", min_analogs)
    _validate_positive_integer("top_k", top_k)
    _validate_positive_integer("candidate_stride", candidate_stride)
    if min_analogs > top_k:
        raise ValueError("min_analogs must not exceed top_k")
    if isinstance(regime_lookback, bool) or not isinstance(regime_lookback, int) or not 20 <= regime_lookback <= 2000:
        raise ValueError("regime_lookback must be an integer in [20, 2000]")
    for name, value in (("fee_bps_per_side", fee_bps_per_side),
                        ("slippage_bps_per_side", slippage_bps_per_side)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value < 10_000:
            raise ValueError(f"{name} must be finite and in [0, 10000)")
    if fee_bps_per_side + slippage_bps_per_side >= 10_000:
        raise ValueError("combined per-side costs must be below 10000 bps")
    if not candles:
        raise ValueError("candles must not be empty")
    for candle in candles:
        candle.validate()
    if not horizons:
        raise ValueError("at least one forward horizon is required")
    normalized_horizons: list[int] = []
    for horizon in horizons:
        _validate_positive_integer("horizons entries", horizon)
        if horizon in normalized_horizons:
            raise ValueError("horizons must not contain duplicates")
        normalized_horizons.append(horizon)

    pattern = search_analogs(
        candles,
        query_start=query_start_index,
        query_end=query_end_index,
        mode=mode,
        top_k=top_k,
        horizons=normalized_horizons,
        candidate_stride=candidate_stride,
    )

    query = candles[query_start_index:query_end_index + 1]
    if not query:
        raise ValueError("query window must not be empty")
    first, last = candles[0], candles[-1]
    if first.symbol != last.symbol or first.interval != last.interval:
        raise ValueError("all candles must share one symbol and interval")

    regime: dict[str, Any]
    try:
        regime = classify_regime(
            candles,
            end_index=query_end_index,
            lookback=regime_lookback,
        )
        regime_status = "classified"
    except ValueError as exc:
        regime = {
            "symbol": query[-1].symbol,
            "interval": query[-1].interval,
            "regime": None,
            "status": "unclassified",
            "reason": str(exc),
            "causal": True,
        }
        regime_status = "unclassified"

    evaluated_analogs: list[dict[str, Any]] = []
    for analog in pattern.analogs:
        forward = evaluate_forward_path(
            candles,
            candidate_end_index=analog.end_index,
            horizons=normalized_horizons,
            fee_bps_per_side=fee_bps_per_side,
            slippage_bps_per_side=slippage_bps_per_side,
        )
        evaluated_analogs.append({
            "start_index": analog.start_index,
            "end_index": analog.end_index,
            "start_time": analog.start_time,
            "end_time": analog.end_time,
            "similarity": analog.similarity,
            "stage_similarities": analog.stage_similarities,
            "forward": forward.to_dict(),
        })

    horizon_summaries: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for horizon in normalized_horizons:
        outcomes = []
        for item in evaluated_analogs:
            outcome = next(
                (row for row in item["forward"]["outcomes"]
                 if row is not None and row["horizon"] == horizon),
                None,
            )
            if outcome is not None:
                outcomes.append(outcome)

        if len(outcomes) < min_analogs:
            horizon_summaries.append({
                "horizon": horizon,
                "status": "insufficient_sample",
                "sample_count": len(outcomes),
                "required_sample_count": min_analogs,
                "interpretation": "No directional assessment is emitted.",
            })
            continue

        long_values = [float(row["long_net_return"]) for row in outcomes]
        short_values = [float(row["short_net_return"]) for row in outcomes]
        median_long = median(long_values)
        median_short = median(short_values)
        if median_long > 0 and median_long > median_short:
            historical_side = "LONG"
        elif median_short > 0 and median_short > median_long:
            historical_side = "SHORT"
        else:
            historical_side = "FLAT"

        sideways_count = sum(
            float(row["max_high_low_range"]) <= 0.01
            and float(row["absolute_close_return"]) <= 0.005
            for row in outcomes
        )
        regime_name = regime.get("regime")
        consistency = _regime_consistency(regime_name, historical_side)
        summary = {
            "horizon": horizon,
            "status": "evaluated",
            "sample_count": len(outcomes),
            "historical_analogue_side": historical_side,
            "median_long_net_return": median_long,
            "median_short_net_return": median_short,
            "mean_long_net_return": mean(long_values),
            "mean_short_net_return": mean(short_values),
            "long_net_positive_rate": sum(value > 0 for value in long_values) / len(outcomes),
            "short_net_positive_rate": sum(value > 0 for value in short_values) / len(outcomes),
            "sideways_path_rate": sideways_count / len(outcomes),
            "median_max_high_low_range": median(
                float(row["max_high_low_range"]) for row in outcomes
            ),
            "regime_consistency": consistency,
            "sideways_definition": {
                "max_high_low_range_lte": 0.01,
                "absolute_close_return_lte": 0.005,
                "requires_both": True,
            },
        }
        horizon_summaries.append(summary)
        if consistency == "opposed":
            conflicts.append({
                "type": "regime_vs_analogue_direction",
                "horizon": horizon,
                "current_regime": regime_name,
                "historical_analogue_side": historical_side,
                "action": "Keep abstaining; inspect walk-forward and regime-conditional baselines.",
            })

    if len(pattern.analogs) < min_analogs:
        research_status = "INSUFFICIENT_ANALOGS"
    elif conflicts:
        research_status = "CONFLICT_REQUIRES_VALIDATION"
    elif any(row["status"] == "evaluated" for row in horizon_summaries):
        research_status = "REQUIRES_WALK_FORWARD_VALIDATION"
    else:
        research_status = "INSUFFICIENT_FORWARD_OUTCOMES"

    gap_count = len(find_gaps([item.open_time for item in candles], first.interval))
    if run_id is None:
        run_id = str(uuid4())
    else:
        try:
            run_id = str(UUID(run_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("run_id must be a UUID") from exc
    return {
        "core_version": CORE_VERSION,
        "run_id": run_id,
        "research_status": research_status,
        "symbol": query[-1].symbol,
        "interval": query[-1].interval,
        "query": {
            "start_index": query_start_index,
            "end_index": query_end_index,
            "start_time": query[0].open_time,
            "end_time": query[-1].close_time,
            "candle_count": len(query),
            "closed_candles_only": True,
        },
        "provenance": {
            "algorithm": "sherlock_intelligence_core",
            "algorithm_version": CORE_VERSION,
            "pattern_engine": "pattern_intelligence",
            "pattern_mode": mode,
            "candidate_stride": pattern.candidate_stride,
            "candidate_sampling": (
                "uniform_index_stride" if pattern.candidate_stride > 1 else "exhaustive"
            ),
            "candidates_examined": pattern.candidates_examined,
            "history_candle_count": len(candles),
            "history_start_time": first.open_time,
            "history_end_time": last.close_time,
            "history_gap_count": gap_count,
            "query_indices": [query_start_index, query_end_index],
            "horizons": normalized_horizons,
            "min_analogs": min_analogs,
            "top_k": top_k,
            "cost_model": {
                "fee_bps_per_side": fee_bps_per_side,
                "slippage_bps_per_side": slippage_bps_per_side,
                "charged_on_entry_and_exit": True,
            },
        },
        "modules": {
            "pattern_intelligence": {
                "status": "completed",
                "mode": pattern.mode,
                "candidates_examined": pattern.candidates_examined,
                "analogs_returned": len(pattern.analogs),
                "analogs": [
                    {
                        "start_index": item.start_index,
                        "end_index": item.end_index,
                        "start_time": item.start_time,
                        "end_time": item.end_time,
                        "similarity": item.similarity,
                        "stage_similarities": item.stage_similarities,
                    }
                    for item in pattern.analogs
                ],
                "stage_weights": pattern.to_dict()["stage_weights"],
            },
            "market_regime": {
                "status": regime_status,
                "result": regime,
            },
            "forward_outcomes": {
                "status": "completed" if evaluated_analogs else "no_analogs",
                "analogs_evaluated": len(evaluated_analogs),
                "horizons": horizon_summaries,
                "analog_details": evaluated_analogs,
            },
        },
        "conflicts": conflicts,
        "required_next_checks": [
            "Run expanding-window walk-forward on unseen chronological folds.",
            "Compare with always-LONG, theoretical always-SHORT, FLAT and causal baselines.",
            "Run bounded robustness and parameter-sensitivity diagnostics.",
            "Reserve a genuinely untouched final holdout before any model promotion.",
        ],
        "decision": {
            "trading_signal": None,
            "paper_trade_eligible": False,
            "abstain": True,
            "reason": (
                "Core output is descriptive research evidence. A single historical "
                "search cannot authorize a forecast or paper-trading decision."
            ),
        },
    }
