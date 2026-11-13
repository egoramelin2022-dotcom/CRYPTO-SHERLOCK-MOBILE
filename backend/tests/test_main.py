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
