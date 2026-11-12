from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query

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
