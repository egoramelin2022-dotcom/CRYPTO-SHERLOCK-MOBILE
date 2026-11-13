from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_invalid_interval_rejected():
    response = client.get("/v1/market/klines", params={"interval": "7m"})
    assert response.status_code == 422


def test_invalid_orderbook_depth_rejected():
    response = client.get("/v1/market/orderbook", params={"limit": 5000})
    assert response.status_code == 422


def test_invalid_time_range_rejected():
    response = client.get(
        "/v1/market/klines",
        params={"start_time": 2000, "end_time": 1000},
    )
    assert response.status_code == 422



def test_ticker_24hr_uses_normalized_response(monkeypatch):
    import asyncio
    import app.main as main

    async def fake_binance_get(path, params):
        assert path == "/api/v3/ticker/24hr"
        assert params == {"symbol": "BTCUSDT"}
        return {
            "lastPrice": "67500.5",
            "priceChange": "500.5",
            "priceChangePercent": "0.75",
            "highPrice": "68000",
            "lowPrice": "66000",
            "volume": "123.4",
            "quoteVolume": "8300000",
            "count": 9876,
        }

    monkeypatch.setattr(main, "binance_get", fake_binance_get)
    response = client.get("/v1/market/ticker/24hr", params={"symbol": "BTCUSDT"})
    assert response.status_code == 200
    assert response.json()["last_price"] == 67500.5
    assert response.json()["price_change_percent"] == 0.75
    assert response.json()["trade_count"] == 9876


def test_ticker_rejects_invalid_symbol():
    response = client.get("/v1/market/ticker/24hr", params={"symbol": "BTC/USDT"})
    assert response.status_code == 422
