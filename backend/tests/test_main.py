from fastapi.testclient import TestClient
from types import SimpleNamespace

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


def test_walk_forward_endpoint_queues_research_job(monkeypatch):
    import app.main as main

    queued = {
        "job_id": "walk-forward-job",
        "kind": "walk_forward_research",
        "status": "queued",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "result": None,
        "error": None,
    }
    captured = {}
    monkeypatch.setattr(
        main.research_jobs, "_new_job",
        lambda kind: SimpleNamespace(job_id=queued["job_id"]),
    )
    monkeypatch.setattr(main.research_jobs, "get_job", lambda job_id: queued)
    monkeypatch.setattr(
        main, "_run_desktop_research_job",
        lambda job_id, function, kwargs: captured.update(
            job_id=job_id, function=function, kwargs=kwargs
        ),
    )
    response = client.post(
        "/v1/research/walk-forward",
        params={
            "query_window": 30, "max_folds": 12,
            "min_training_candles": 200, "candidate_budget": 1000,
        },
    )
    assert response.status_code == 202
    assert response.json()["job_id"] == "walk-forward-job"
    assert captured["kwargs"]["query_window"] == 30
    assert captured["kwargs"]["max_folds"] == 12
    assert captured["function"] is main.desktop_services.run_walk_forward_research


def test_walk_forward_endpoint_rejects_calendar_month_interval():
    response = client.post("/v1/research/walk-forward", params={"interval": "1M"})
    assert response.status_code == 422


def test_walk_forward_endpoint_rejects_training_history_shorter_than_embargo():
    response = client.post(
        "/v1/research/walk-forward",
        params={"query_window": 40, "min_training_candles": 100},
    )
    assert response.status_code == 422


def test_robustness_endpoint_queues_sensitivity_job(monkeypatch):
    import app.main as main

    queued = {
        "job_id": "robustness-job",
        "kind": "robustness_research",
        "status": "queued",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "result": None,
        "error": None,
    }
    captured = {}
    monkeypatch.setattr(
        main.research_jobs, "_new_job",
        lambda kind: SimpleNamespace(job_id=queued["job_id"]),
    )
    monkeypatch.setattr(main.research_jobs, "get_job", lambda job_id: queued)
    monkeypatch.setattr(
        main, "_run_desktop_research_job",
        lambda job_id, function, kwargs: captured.update(
            job_id=job_id, function=function, kwargs=kwargs
        ),
    )
    response = client.post(
        "/v1/research/robustness",
        params={
            "query_window": 30, "max_folds": 8,
            "min_training_candles": 200, "candidate_budget": 500,
        },
    )
    assert response.status_code == 202
    assert response.json()["job_id"] == "robustness-job"
    assert captured["function"] is main.desktop_services.run_robustness_research
    assert captured["kwargs"]["query_window"] == 30


def test_robustness_endpoint_rejects_training_history_shorter_than_embargo():
    response = client.post(
        "/v1/research/robustness",
        params={"query_window": 40, "min_training_candles": 100},
    )
    assert response.status_code == 422



def test_intelligence_core_endpoint_queues_research_job(monkeypatch):
    import app.main as main

    queued = {
        "job_id": "intelligence-core-job",
        "kind": "intelligence_core",
        "status": "queued",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "result": None,
        "error": None,
    }
    captured = {}
    monkeypatch.setattr(
        main.research_jobs, "_new_job",
        lambda kind: SimpleNamespace(job_id=queued["job_id"]),
    )
    monkeypatch.setattr(main.research_jobs, "get_job", lambda job_id: queued)
    monkeypatch.setattr(
        main, "_run_desktop_research_job",
        lambda job_id, function, kwargs: captured.update(
            job_id=job_id, function=function, kwargs=kwargs
        ),
    )
    response = client.post(
        "/v1/research/core",
        params={
            "query_window": 32,
            "mode": "five_stage",
            "top_k": 20,
            "min_analogs": 5,
            "candidate_budget": 1500,
        },
    )
    assert response.status_code == 202
    assert response.json()["kind"] == "intelligence_core"
    assert captured["function"] is main.desktop_services.run_intelligence_core_research
    assert captured["kwargs"]["query_window"] == 32
    assert captured["kwargs"]["mode"] == "five_stage"
    assert captured["kwargs"]["candidate_budget"] == 1500


def test_intelligence_core_endpoint_rejects_impossible_sample_and_costs():
    impossible_sample = client.post(
        "/v1/research/core", params={"top_k": 5, "min_analogs": 6}
    )
    assert impossible_sample.status_code == 422

    invalid_costs = client.post(
        "/v1/research/core",
        params={"fee_bps_per_side": 6000, "slippage_bps_per_side": 5000},
    )
    assert invalid_costs.status_code == 422
