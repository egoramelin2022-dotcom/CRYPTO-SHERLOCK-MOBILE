"""Desktop-triggered research jobs over the immutable local source database."""
from __future__ import annotations

import sqlite3
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from urllib.parse import quote

from app.market_data.candles import Candle, find_gaps
from app.research.pattern_intelligence import search_analogs
from app.research.multitimeframe_detector import (
    MultiTimeframeConfig, detect_multitimeframe_setups,
)
from app.research.evidence_adapters import pattern_search_evidence, stumpy_matches_evidence
from app.research.ensemble import build_evidence_report
from app.research.outcome_evaluation import evaluate_forward_path
from app.research.stumpy_adapter import find_query_matches

from app.research import jobs as base_jobs


def _read_database(path: Path, symbol: str, interval: str, limit: int) -> list[Candle]:
    uri = f"file:{quote(path.as_posix(), safe='/:')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        rows = connection.execute(
            """SELECT symbol, interval, open_time, open, high, low, close,
                      volume, close_time, quote_volume, trade_count,
                      taker_buy_base, taker_buy_quote
               FROM candles WHERE symbol=? AND interval=? AND close_time < ?
               ORDER BY open_time DESC LIMIT ?""",
            (symbol, interval, now_ms, limit),
        ).fetchall()
        return [Candle(**dict(row)) for row in reversed(rows)]
    finally:
        connection.close()


def _load_candles(symbol: str, interval: str, limit: int) -> tuple[list[Candle], list[str]]:
    source, _ = base_jobs._configured_paths()
    paths = [("source", source)]
    staging_value = os.getenv("SHERLOCK_ARCHIVE_STAGING_DB")
    if staging_value:
        staging = Path(staging_value).expanduser().resolve()
        if staging.is_file() and staging != source:
            paths.append(("archive_staging", staging))

    merged: dict[int, Candle] = {}
    used_sources: list[str] = []
    for label, path in paths:
        rows = _read_database(path, symbol, interval, limit)
        if not rows:
            continue
        used_sources.append(label)
        for candle in rows:
            candle.validate()
            previous = merged.get(candle.open_time)
            if previous is not None and previous != candle:
                raise ValueError(
                    f"Conflicting {symbol} {interval} candle at {candle.open_time} "
                    "between source and archive staging databases"
                )
            merged[candle.open_time] = candle

    candles = sorted(merged.values(), key=lambda item: item.open_time)[-limit:]
    if not candles:
        raise ValueError(f"No local candles for {symbol} {interval}")
    gaps = find_gaps([c.open_time for c in candles], interval)
    if gaps:
        last_gap = gaps[-1]
        first_after_gap = next(
            i for i, candle in enumerate(candles)
            if candle.open_time == last_gap.next_open_time
        )
        candles = candles[first_after_gap:]
    if not candles:
        raise ValueError(f"No contiguous local candles for {symbol} {interval}")
    return candles, used_sources

def run_pattern_research(
    symbol: str = "BTCUSDT", interval: str = "15m", query_window: int = 40,
    mode: str = "free", top_k: int = 10, history_limit: int = 400000,
    fee_bps_per_side: float = 5.0, slippage_bps_per_side: float = 2.0,
) -> dict[str, Any]:
    if history_limit < query_window + 2 or history_limit > 500000:
        raise ValueError("history_limit must be between query_window + 2 and 500000")
    candles, data_sources = _load_candles(symbol, interval, history_limit)
    if len(candles) <= query_window:
        raise ValueError("Not enough local history for query window and earlier analogs")
    query_start = len(candles) - query_window
    query_end = len(candles) - 1
    result = search_analogs(
        candles, query_start=query_start, query_end=query_end,
        mode=mode, top_k=top_k, horizons=(1, 4, 16, 32, 64),
    )
    evidence = pattern_search_evidence(result, candles)
    query_segment = candles[query_start:query_end + 1]
    query_chart = [item.close / query_segment[0].close * 100.0 for item in query_segment]
    evaluated = []
    for analog in result.analogs:
        analog_segment = candles[analog.start_index:analog.end_index + 1]
        analog_chart = [item.close / analog_segment[0].close * 100.0 for item in analog_segment]
        evaluated.append({
            "analog": asdict(analog),
            "chart": {"normalized_close": analog_chart},
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
        "data_sources": data_sources,
        "query_start_time": candles[query_start].open_time,
        "query_end_time": candles[query_end].open_time,
        "query_window": query_window,
        "query_chart": {"normalized_close": query_chart},
        "candidates_examined": result.candidates_examined,
        "evidence": [asdict(item) for item in evidence],
        "analogs": evaluated,
        "interpretation": "Historical analogs and realized forward outcomes only; not a forecast or trading signal.",
    }


def run_multitimeframe_research(symbol: str = "BTCUSDT") -> dict[str, Any]:
    # These are intentionally bounded, recent contiguous windows. Daily
    # candles are historical closed bars in the local source database.
    m15, sources_15m = _load_candles(symbol, "15m", 400000)
    h4, sources_4h = _load_candles(symbol, "4h", 25000)
    d1, sources_1d = _load_candles(symbol, "1d", 5000)
    results = detect_multitimeframe_setups(m15, h4, d1, config=MultiTimeframeConfig())
    return {
        "symbol": symbol,
        "config": asdict(MultiTimeframeConfig()),
        "rows_loaded": {"15m": len(m15), "4h": len(h4), "1d": len(d1)},
        "data_sources": {"15m": sources_15m, "4h": sources_4h, "1d": sources_1d},
        "setups": [item.to_dict() for item in results],
        "interpretation": "Aligned historical observations only; not a forecast or trading signal. Daily bars must be closed.",
    }


def run_ensemble_research(symbol: str = "BTCUSDT", interval: str = "15m",
                          query_window: int = 40, mode: str = "free",
                          top_k: int = 20) -> dict[str, Any]:
    candles, data_sources = _load_candles(symbol, interval, 400000)
    if len(candles) <= query_window:
        raise ValueError("Not enough local history for ensemble query")
    start, end = len(candles) - query_window, len(candles) - 1
    pattern = search_analogs(
        candles, query_start=start, query_end=end, mode=mode,
        top_k=top_k, horizons=(1, 4, 16, 32),
    )
    evidence = pattern_search_evidence(pattern, candles)
    engines_available = ["pattern_intelligence"]
    engines_missing = []
    stumpy_error = None
    try:
        import numpy as np

        embargo = 32
        history = candles[:max(0, start - embargo)]
        query = candles[start:end + 1]
        if len(history) < len(query):
            raise RuntimeError("not enough pre-query history for STUMPY with the configured embargo")
        history_close = np.asarray([item.close for item in history], dtype=np.float64)
        # Include the close immediately before the query so its first return
        # is measured from the true prior candle, not replaced with zero.
        query_close = np.asarray(
            [candles[start - 1].close, *[item.close for item in query]],
            dtype=np.float64,
        )
        history_values = np.diff(np.log(history_close), prepend=np.log(history_close[0]))
        query_values = np.diff(np.log(query_close))
        matches = find_query_matches(
            history_values, query_values, top_k=top_k,
            exclusion_zone=len(query_values),
        )
        evidence.extend(stumpy_matches_evidence(
            matches,
            history_open_times=[item.open_time for item in history],
            query_open_times=[item.open_time for item in query],
            interval=interval,
        ))
        engines_available.append("stumpy")
    except (ImportError, RuntimeError) as exc:
        engines_missing.append("stumpy")
        stumpy_error = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        engines_missing.append("stumpy_runtime")
        stumpy_error = f"{type(exc).__name__}: {exc}"

    report = (
        build_evidence_report(evidence, min_supporting_modules=2).to_dict()
        if evidence else {
            "interval": interval,
            "query_start_time": candles[start].open_time,
            "query_end_time": candles[end].open_time,
            "evidence_count": 0,
            "module_count": 0,
            "candidates": [],
            "interpretation": "No candidate evidence was produced by the available engines.",
        }
    )
    return {
        "symbol": symbol, "mode": mode, "query_window": query_window,
        "data_sources": data_sources,
        "engines_available": engines_available,
        "engines_missing": engines_missing,
        "optional_engine_note": stumpy_error,
        "evidence_report": report,
        "interpretation": (
            "Only exact candidate windows independently returned by multiple engines "
            "appear in consensus. Consensus is descriptive evidence, not a probability, "
            "forecast, or trading signal."
        ),
    }
