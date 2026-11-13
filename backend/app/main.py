from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query

BINANCE_BASE_URL = os.getenv("BINANCE_BASE_URL", "https://api.binance.com")
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
app = FastAPI(
    title="CRYPTO SHERLOCK Data Gateway",
    version="0.1.0",
    description="Read-only public market-data gateway. No exchange credentials or order execution.",
)


async def binance_get(path: str, params: dict[str, Any]) -> Any:
    try:
        async with httpx.AsyncClient(base_url=BINANCE_BASE_URL, timeout=TIMEOUT) as client:
            response = await client.get(path, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Binance upstream returned HTTP {exc.response.status_code}") from exc
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        raise HTTPException(status_code=503, detail="Binance market-data service is temporarily unavailable") from exc


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "sherlock-data-gateway", "version": "0.1.0"}


@app.get("/v1/market/ticker/24hr")
async def ticker_24hr(
    symbol: str = Query("BTCUSDT", pattern=r"^[A-Z0-9]{5,20}$"),
) -> dict[str, Any]:
    """24-hour rolling ticker from public Binance Spot data."""
    raw = await binance_get("/api/v3/ticker/24hr", {"symbol": symbol})
    return {
        "symbol": symbol,
        "last_price": float(raw["lastPrice"]),
        "price_change": float(raw["priceChange"]),
        "price_change_percent": float(raw["priceChangePercent"]),
        "high_price": float(raw["highPrice"]),
        "low_price": float(raw["lowPrice"]),
        "volume": float(raw["volume"]),
        "quote_volume": float(raw["quoteVolume"]),
        "trade_count": int(raw["count"]),
    }


@app.get("/v1/market/klines")
async def klines(
    symbol: str = Query("BTCUSDT", pattern=r"^[A-Z0-9]{5,20}$"),
    interval: str = Query("15m", pattern=r"^(1m|3m|5m|15m|30m|1h|2h|4h|6h|8h|12h|1d|3d|1w|1M)$"),
    limit: int = Query(500, ge=1, le=1000),
    start_time: int | None = Query(None, ge=0),
    end_time: int | None = Query(None, ge=0),
) -> dict[str, Any]:
    if start_time is not None and end_time is not None and start_time >= end_time:
        raise HTTPException(status_code=422, detail="start_time must be earlier than end_time")
    params: dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
    if start_time is not None:
        params["startTime"] = start_time
    if end_time is not None:
        params["endTime"] = end_time
    raw = await binance_get("/api/v3/klines", params)
    rows = [
        {
            "open_time": int(r[0]), "open": float(r[1]), "high": float(r[2]),
            "low": float(r[3]), "close": float(r[4]), "volume": float(r[5]),
            "close_time": int(r[6]), "quote_volume": float(r[7]),
            "trade_count": int(r[8]), "taker_buy_base": float(r[9]),
            "taker_buy_quote": float(r[10]),
        }
        for r in raw
    ]
    return {"symbol": symbol, "interval": interval, "count": len(rows), "candles": rows}


@app.get("/v1/market/orderbook")
async def orderbook(
    symbol: str = Query("BTCUSDT", pattern=r"^[A-Z0-9]{5,20}$"),
    limit: int = Query(100, ge=5, le=1000),
) -> dict[str, Any]:
    raw = await binance_get("/api/v3/depth", {"symbol": symbol, "limit": limit})
    return {
        "symbol": symbol, "last_update_id": int(raw["lastUpdateId"]),
        "bids": [[float(p), float(q)] for p, q in raw["bids"]],
        "asks": [[float(p), float(q)] for p, q in raw["asks"]],
    }


@app.get("/v1/market/agg-trades")
async def aggregate_trades(
    symbol: str = Query("BTCUSDT", pattern=r"^[A-Z0-9]{5,20}$"),
    limit: int = Query(500, ge=1, le=1000),
    from_id: int | None = Query(None, ge=0),
) -> dict[str, Any]:
    params: dict[str, Any] = {"symbol": symbol, "limit": limit}
    if from_id is not None:
        params["fromId"] = from_id
    raw = await binance_get("/api/v3/aggTrades", params)
    trades = [
        {
            "id": int(t["a"]), "price": float(t["p"]), "quantity": float(t["q"]),
            "first_trade_id": int(t["f"]), "last_trade_id": int(t["l"]),
            "timestamp": int(t["T"]), "buyer_is_maker": bool(t["m"]),
        }
        for t in raw
    ]
    return {"symbol": symbol, "count": len(trades), "trades": trades}


# Research endpoints use only server-configured local database paths. The
# source market database is opened read-only by the research modules.
from app.research import jobs as research_jobs


@app.post("/v1/research/audit", status_code=202)
async def start_data_audit(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Queue a structural audit of the configured local source database."""
    job = research_jobs.queue_audit()
    background_tasks.add_task(research_jobs.run_audit_job, job["job_id"])
    return job


@app.post("/v1/research/pipeline", status_code=202)
async def start_historical_pipeline(
    background_tasks: BackgroundTasks,
    symbol: str = Query("BTCUSDT", pattern=r"^[A-Z0-9]{5,20}$"),
    interval: str = Query("15m", pattern=r"^(1m|3m|5m|15m|30m|1h|2h|4h|6h|8h|12h|1d|3d|1w|1M)$"),
    window: int = Query(20, ge=2, le=500),
) -> dict[str, Any]:
    """Queue point-in-time feature and regime extraction from local history."""
    job = research_jobs.queue_pipeline()
    background_tasks.add_task(
        research_jobs.run_pipeline_job, job["job_id"], symbol, interval, window
    )
    return job


@app.post("/v1/research/ensemble", status_code=202)
async def start_ensemble_research(
    background_tasks: BackgroundTasks,
    symbol: str = Query("BTCUSDT", pattern=r"^[A-Z0-9]{5,20}$"),
    interval: str = Query("15m", pattern=r"^(1m|3m|5m|15m|30m|1h|2h|4h|6h|8h|12h|1d|3d|1w|1M)$"),
    window: int = Query(20, ge=5, le=500),
    top_k: int = Query(10, ge=1, le=100),
    mode: str = Query("free", pattern=r"^(free|five_stage)$"),
    include_stumpy: bool = Query(False),
    fee_bps_per_side: float = Query(0.0, ge=0, lt=10_000),
    slippage_bps_per_side: float = Query(0.0, ge=0, lt=10_000),
) -> dict[str, Any]:
    """Queue read-only Pattern Intelligence + optional STUMPY research."""
    job = research_jobs.queue_ensemble()
    background_tasks.add_task(
        research_jobs.run_ensemble_job,
        job["job_id"], symbol, interval, window, top_k, mode, include_stumpy,
        fee_bps_per_side, slippage_bps_per_side,
    )
    return job


@app.get("/v1/research/jobs/{job_id}")
async def research_job_status(job_id: str) -> dict[str, Any]:
    """Return the current state and result of a research job."""
    job = research_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    return job
