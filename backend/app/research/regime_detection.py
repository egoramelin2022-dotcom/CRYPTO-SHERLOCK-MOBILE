"""Causal, rule-based market regime descriptors from trailing closed candles."""
from __future__ import annotations

from math import sqrt
from statistics import pstdev
from typing import Sequence, Any

from app.market_data.candles import Candle


def classify_regime(
    candles: Sequence[Candle],
    *,
    end_index: int | None = None,
    lookback: int = 96,
    high_volatility_threshold: float = 0.006,
    trend_return_threshold: float = 0.015,
    accumulation_volume_ratio: float = 1.10,
) -> dict[str, Any]:
    if isinstance(lookback, bool) or not isinstance(lookback, int) or not 20 <= lookback <= 2000:
        raise ValueError("lookback must be an integer in [20, 2000]")
    if not candles:
        raise ValueError("candles must not be empty")
    end = len(candles) - 1 if end_index is None else end_index
    if isinstance(end, bool) or not isinstance(end, int) or not 0 <= end < len(candles):
        raise ValueError("end_index is outside candle data")
    start = max(0, end - lookback + 1)
    rows = list(candles[start:end + 1])
    if len(rows) < 20:
        raise ValueError("at least 20 trailing candles are required")
    first, last = rows[0], rows[-1]
    close_returns = [
        rows[i].close / rows[i - 1].close - 1.0
        for i in range(1, len(rows))
    ]
    net_return = last.close / first.close - 1.0
    realized_volatility = pstdev(close_returns) * sqrt(len(close_returns)) if close_returns else 0.0
    path_length = sum(abs(value) for value in close_returns)
    efficiency = abs(net_return) / path_length if path_length else 0.0
    highest = max(row.high for row in rows)
    lowest = min(row.low for row in rows)
    range_position = (last.close - lowest) / (highest - lowest) if highest > lowest else 0.5
    volume_split = max(1, len(rows) // 2)
    early_volume = sum(row.volume for row in rows[:volume_split]) / volume_split
    late_rows = rows[volume_split:]
    late_volume = sum(row.volume for row in late_rows) / max(1, len(late_rows))
    volume_ratio = late_volume / early_volume if early_volume > 0 else 1.0

    if realized_volatility >= high_volatility_threshold:
        regime = "HIGH_VOLATILITY"
    elif net_return >= trend_return_threshold and efficiency >= 0.25:
        regime = "TREND_UP"
    elif net_return <= -trend_return_threshold and efficiency >= 0.25:
        regime = "TREND_DOWN"
    elif abs(net_return) < trend_return_threshold and range_position <= 0.35 and volume_ratio >= accumulation_volume_ratio:
        regime = "ACCUMULATION_CANDIDATE"
    else:
        regime = "SIDEWAYS"

    return {
        "regime": regime,
        "start_index": start,
        "end_index": end,
        "start_time": first.open_time,
        "end_time": last.close_time,
        "lookback_candles": len(rows),
        "net_return": net_return,
        "realized_volatility": realized_volatility,
        "directional_efficiency": efficiency,
        "range_position": range_position,
        "volume_ratio_late_vs_early": volume_ratio,
        "causal": True,
        "interpretation": (
            "Rule-based trailing-window descriptor using candles available through "
            "the query close. ACCUMULATION_CANDIDATE is a heuristic label, not proof "
            "of institutional accumulation or a predictive signal."
        ),
    }


def summarize_regime_outcomes(folds: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[float]] = {}
    for fold in folds:
        regime = fold.get("regime", {}).get("regime")
        if not regime:
            continue
        for horizon, outcome in fold.get("horizons", {}).items():
            if outcome.get("predicted_side") == "FLAT":
                value = 0.0
            else:
                value = float(outcome.get("model_return", 0.0))
            grouped.setdefault(f"{regime}|{horizon}", []).append(value)
    result = {}
    for key, values in grouped.items():
        result[key] = {
            "folds": len(values),
            "average_model_return": sum(values) / len(values),
            "positive_fold_rate": sum(value > 0 for value in values) / len(values),
        }
    return result
