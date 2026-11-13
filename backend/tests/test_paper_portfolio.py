from app.research import paper_portfolio


def test_virtual_buy_and_sell_persist_and_never_go_negative(tmp_path, monkeypatch):
    db = tmp_path / "analytics.db"
    monkeypatch.setattr(paper_portfolio, "_db_path", lambda: db)
    monkeypatch.setattr(paper_portfolio, "DEFAULT_INITIAL_CASH", 1000.0)
    monkeypatch.setattr(paper_portfolio, "FEE_BPS", 10.0)
    monkeypatch.setattr(paper_portfolio, "SLIPPAGE_BPS", 5.0)

    buy = paper_portfolio.place_virtual_order("BTCUSDT", "BUY", 0.01, 50000.0)
    assert buy["mode"] == "PAPER_ONLY"
    assert buy["fill_price"] > 50000.0
    assert buy["cash_after"] < 500.0

    snapshot = paper_portfolio.portfolio_snapshot()
    assert len(snapshot["positions"]) == 1
    assert snapshot["positions"][0]["quantity"] == 0.01

    sell = paper_portfolio.place_virtual_order("BTCUSDT", "SELL", 0.01, 51000.0)
    assert sell["fill_price"] < 51000.0
    assert sell["realized_pnl"] > 0
    final = paper_portfolio.portfolio_snapshot()
    assert final["positions"] == []
    assert final["cash"] > 1000.0


def test_virtual_order_rejects_oversell_and_insufficient_cash(tmp_path, monkeypatch):
    monkeypatch.setattr(paper_portfolio, "_db_path", lambda: tmp_path / "paper.db")
    monkeypatch.setattr(paper_portfolio, "DEFAULT_INITIAL_CASH", 100.0)
    monkeypatch.setattr(paper_portfolio, "FEE_BPS", 10.0)
    monkeypatch.setattr(paper_portfolio, "SLIPPAGE_BPS", 5.0)

    try:
        paper_portfolio.place_virtual_order("BTCUSDT", "BUY", 1.0, 50000.0)
    except ValueError as exc:
        assert "insufficient" in str(exc)
    else:
        raise AssertionError("oversized virtual buy should fail")

    try:
        paper_portfolio.place_virtual_order("BTCUSDT", "SELL", 0.01, 50000.0)
    except ValueError as exc:
        assert "exceeds" in str(exc)
    else:
        raise AssertionError("sell without inventory should fail")
