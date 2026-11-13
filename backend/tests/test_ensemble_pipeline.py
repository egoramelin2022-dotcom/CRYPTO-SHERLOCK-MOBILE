from types import SimpleNamespace

import pytest

from app.market_data.candles import Candle
from app.research.ensemble_pipeline import run_ensemble_search


STEP = 900_000


def make_candles():
    closes = [100.0] * 40
    motif = [100.0, 102.0, 101.0, 104.0, 100.0]
    closes[10:15] = motif
    closes[30:35] = motif
    rows = []
    previous = 100.0
    for i, close in enumerate(closes):
        op = previous
        rows.append(Candle(
            symbol="BTCUSDT", interval="15m", open_time=i * STEP,
            open=op, high=max(op, close) + 1.0, low=min(op, close) - 1.0,
            close=close, volume=10.0, close_time=(i + 1) * STEP - 1,
            quote_volume=1000.0, trade_count=10,
            taker_buy_base=5.0, taker_buy_quote=500.0,
        ))
        previous = close
    return rows


def test_pattern_only_run_returns_consensus_and_costed_outcomes():
    rows = make_candles()
    result = run_ensemble_search(
        rows, query_start_index=30, query_end_index=34,
        top_k=1, horizons=(1, 2), include_stumpy=False,
        fee_bps_per_side=10, slippage_bps_per_side=5,
    )
    assert result.pattern_candidate_count == 1
    assert result.stumpy_candidate_count == 0
    assert result.ensemble is not None
    assert result.ensemble.candidates[0].candidate_start_time == 10 * STEP
    assert len(result.forward_evaluations) == 1
    assert result.ablations[0].removed_module == "pattern_intelligence"
    assert result.ablations[0].full_candidates_lost == 1
    forward = result.forward_evaluations[0].forward
    assert forward.fee_bps_per_side == 10
    assert forward.slippage_bps_per_side == 5
    assert forward.outcomes[0] is not None
    assert result.outcome_summary
    assert result.outcome_summary[0].horizon == 1
    assert result.outcome_summary[0].sample_count == 1
    assert result.to_dict()["outcome_summary_method"].startswith("Per-horizon")


def test_stumpy_and_pattern_evidence_are_combined(monkeypatch):
    rows = make_candles()
    monkeypatch.setattr(
        "app.research.ensemble_pipeline.find_query_matches",
        lambda history, query, top_k: [
            SimpleNamespace(start_index=10, distance=0.0)
        ],
    )
    result = run_ensemble_search(
        rows, query_start_index=30, query_end_index=34,
        top_k=1, horizons=(1, 2), include_stumpy=True,
        min_supporting_modules=2,
    )
    assert result.pattern_candidate_count == 1
    assert result.stumpy_candidate_count == 1
    assert result.ensemble is not None
    candidate = result.ensemble.candidates[0]
    assert candidate.supporting_modules == ("pattern_intelligence", "stumpy")
    assert candidate.module_count == 2
    assert len(result.ablations) == 2
    assert all(item.full_candidates_lost == 1 for item in result.ablations)


def test_short_query_skips_stumpy_and_falls_back_to_pattern():
    rows = make_candles()
    result = run_ensemble_search(
        rows, query_start_index=5, query_end_index=6,
        horizons=(1, 2), include_stumpy=True,
    )
    assert result.stumpy_candidate_count == 0
    assert result.ensemble is not None


def test_rejects_duplicate_or_invalid_horizons_and_costs():
    rows = make_candles()
    with pytest.raises(ValueError, match="duplicates"):
        run_ensemble_search(
            rows, query_start_index=30, query_end_index=34,
            horizons=(1, 1),
        )
    with pytest.raises(ValueError, match="fee_bps"):
        run_ensemble_search(
            rows, query_start_index=30, query_end_index=34,
            fee_bps_per_side=-1,
        )


def test_invalid_minimum_support_is_rejected_even_without_candidates():
    rows = make_candles()
    with pytest.raises(ValueError, match="min_supporting_modules"):
        run_ensemble_search(
            rows, query_start_index=0, query_end_index=4,
            min_supporting_modules=0,
        )
