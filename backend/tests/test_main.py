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



def test_research_job_not_found():
    response = client.get("/v1/research/jobs/not-a-real-job")
    assert response.status_code == 404


def test_pipeline_rejects_invalid_window():
    response = client.post("/v1/research/pipeline", params={"window": 1})
    assert response.status_code == 422


def test_pipeline_job_is_queued(monkeypatch):
    import app.main as main

    queued = {
        "job_id": "test-job-001",
        "kind": "historical_pipeline",
        "status": "queued",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "result": None,
        "error": None,
    }
    called = {}

    monkeypatch.setattr(main.research_jobs, "queue_pipeline", lambda: queued)
    monkeypatch.setattr(
        main.research_jobs,
        "run_pipeline_job",
        lambda job_id, symbol, interval, window: called.update(
            job_id=job_id, symbol=symbol, interval=interval, window=window
        ),
    )

    response = client.post(
        "/v1/research/pipeline",
        params={"symbol": "BTCUSDT", "interval": "15m", "window": 32},
    )
    assert response.status_code == 202
    assert response.json()["job_id"] == "test-job-001"
    assert called == {
        "job_id": "test-job-001",
        "symbol": "BTCUSDT",
        "interval": "15m",
        "window": 32,
    }



def test_audit_job_is_queued(monkeypatch):
    import app.main as main

    queued = {
        "job_id": "audit-job-001",
        "kind": "data_audit",
        "status": "queued",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "result": None,
        "error": None,
    }
    called = []
    monkeypatch.setattr(main.research_jobs, "queue_audit", lambda: queued)
    monkeypatch.setattr(main.research_jobs, "run_audit_job", lambda job_id: called.append(job_id))

    response = client.post("/v1/research/audit")
    assert response.status_code == 202
    assert response.json()["job_id"] == "audit-job-001"
    assert called == ["audit-job-001"]



def test_research_endpoints_reject_calendar_month_interval():
    for endpoint, params in (
        ("/v1/research/pipeline", {"interval": "1M"}),
        ("/v1/research/pattern", {"interval": "1M"}),
        ("/v1/research/ensemble", {"interval": "1M"}),
    ):
        response = client.post(endpoint, params=params)
        assert response.status_code == 422, (endpoint, response.text)



def test_current_month_sync_job_is_queued(monkeypatch):
    import app.main as main

    called = []
    monkeypatch.setattr(
        main.archive_jobs, "run_recent_sync_job",
        lambda job_id, symbol: called.append((job_id, symbol)),
    )
    response = client.post(
        "/v1/data/sync-current-month", params={"symbol": "BTCUSDT"}
    )
    assert response.status_code == 202
    assert response.json()["kind"] == "binance_recent_sync"
    assert called == [(response.json()["job_id"], "BTCUSDT")]


def test_current_month_sync_rejects_invalid_symbol():
    response = client.post(
        "/v1/data/sync-current-month", params={"symbol": "BTC/USDT"}
    )
    assert response.status_code == 422


def test_adaptive_pattern_endpoint_rejects_invalid_bounds_and_too_many_windows():
    reversed_bounds = client.post(
        "/v1/research/pattern",
        params={"adaptive_search": "true", "adaptive_min_window": 100, "adaptive_max_window": 20},
    )
    assert reversed_bounds.status_code == 422

    too_many = client.post(
        "/v1/research/pattern",
        params={"adaptive_search": "true", "adaptive_min_window": 5, "adaptive_max_window": 100, "adaptive_step": 5},
    )
    assert too_many.status_code == 422
