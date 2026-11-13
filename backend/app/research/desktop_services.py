"""Desktop-triggered research jobs over the immutable local source database."""
from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.market_data.candles import Candle, find_gaps
from app.research.pattern_intelligence import search_analogs
from app.research.multitimeframe_detector import (
    MultiTimeframeConfig, detect_multitimeframe_setups,
)
from app.research.evidence_adapters import pattern_search_evidence
from app.research.ensemble import build_evidence_report
from app.research.outcome_evaluation import evaluate_forward_path

from app.research import jobs as base_jobs


def _load_candles(symbol: str, interval: str, limit: int) -> list[Candle]:
    source, _ = base_jobs._configured_paths()
    uri = f"file:{source.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """SELECT symbol, interval, open_time, open, high, low, close,
                      volume, close_time, quote_volume, trade_count,
                      taker_buy_base, taker_buy_quote
               FROM candles WHERE symbol=? AND interval=?
               ORDER BY open_time DESC LIMIT ?""",
            (symbol, interval, limit),
        ).fetchall()
    finally:
        connection.close()
    candles = [Candle(**dict(row)) for row in reversed(rows)]
    if not candles:
        raise ValueError(f"No local candles for {symbol} {interval}")
    for candle in candles:
        candle.validate()
    gaps = find_gaps([c.open_time for c in candles], interval)
    if gaps:
        raise ValueError(
            f"Local {symbol} {interval} history has {len(gaps)} gaps; "
            "repair or select a verified contiguous range before research"
        )
    return candles


def run_pattern_research(
    symbol: str = "BTCUSDT", interval: str = "15m", query_window: int = 40,
    mode: str = "free", top_k: int = 10, history_limit: int = 20000,
    fee_bps_per_side: float = 5.0, slippage_bps_per_side: float = 2.0,
) -> dict[str, Any]:
    if history_limit < query_window + 2 or history_limit > 50000:
        raise ValueError("history_limit must be between query_window + 2 and 50000")
    candles = _load_candles(symbol, interval, history_limit)
    if len(candles) <= query_window:
        raise ValueError("Not enough local history for query window and earlier analogs")
    query_start = len(candles) - query_window
    query_end = len(candles) - 1
    result = search_analogs(
        candles, query_start=query_start, query_end=query_end,
        mode=mode, top_k=top_k, horizons=(1, 4, 16, 32, 64),
    )
    evidence = pattern_search_evidence(result, candles)
    evaluated = []
    for analog in result.analogs:
        evaluated.append({
            "analog": asdict(analog),
            "forward_path": evaluate_forward_path(
                candles, candidate_end_index=analog.end_index,
                horizons=(1, 4, 16, 32, 64),
                fee_bps_per_side=fee_bps_per_side,
                slippage_bps_per_side=slippage_bps_per_side,
            ).to_dict(),
        })
    return {
        "symbol": symbol, "interval": interval, "mode": mode,
        "history_candles": len(candles),
        "query_start_time": candles[query_start].open_time,
        "query_end_time": candles[query_end].open_time,
        "query_window": query_window,
        "candidates_examined": result.candidates_examined,
        "evidence": [asdict(item) for item in evidence],
        "analogs": evaluated,
        "interpretation": "Historical analogs and realized forward outcomes only; not a forecast or trading signal.",
    }


def run_multitimeframe_research(symbol: str = "BTCUSDT") -> dict[str, Any]:
    # These are intentionally bounded, recent contiguous windows. Daily
    # candles are historical closed bars in the local source database.
    m15 = _load_candles(symbol, "15m", 30000)
    h4 = _load_candles(symbol, "4h", 3000)
    d1 = _load_candles(symbol, "1d", 1000)
    results = detect_multitimeframe_setups(m15, h4, d1, config=MultiTimeframeConfig())
    return {
        "symbol": symbol,
        "config": asdict(MultiTimeframeConfig()),
        "rows_loaded": {"15m": len(m15), "4h": len(h4), "1d": len(d1)},
        "setups": [item.to_dict() for item in results],
        "interpretation": "Aligned historical observations only; not a forecast or trading signal. Daily bars must be closed.",
    }


def run_ensemble_research(symbol: str = "BTCUSDT", interval: str = "15m",
                          query_window: int = 40, mode: str = "free",
                          top_k: int = 20) -> dict[str, Any]:
    candles = _load_candles(symbol, interval, 20000)
    if len(candles) <= query_window:
        raise ValueError("Not enough local history for ensemble query")
    start, end = len(candles) - query_window, len(candles) - 1
    pattern = search_analogs(
        candles, query_start=start, query_end=end, mode=mode,
        top_k=top_k, horizons=(1, 4, 16, 32),
    )
    evidence = pattern_search_evidence(pattern, candles)
    report = build_evidence_report(evidence, min_supporting_modules=1)
    return {
        "symbol": symbol, "mode": mode, "query_window": query_window,
        "engines_available": ["pattern_intelligence"],
        "engines_missing": ["stumpy_motif_adapter"],
        "evidence_report": report.to_dict(),
        "interpretation": (
            "Single-engine evidence report. Cross-engine consensus is unavailable "
            "until independent STUMPY evidence is produced; no confidence score is inferred."
        ),
    }
