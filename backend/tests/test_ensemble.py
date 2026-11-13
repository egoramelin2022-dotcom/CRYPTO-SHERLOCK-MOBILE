import pytest

from app.research.ensemble import ResearchEvidence, build_evidence_report


def row(module, start, end, rank=1, similarity=0.9):
    return ResearchEvidence(
        module=module,
        algorithm_version="0.1.0",
        feature_set="close_returns",
        interval="15m",
        query_start_time=10_000,
        query_end_time=20_000,
        candidate_start_time=start,
        candidate_end_time=end,
        rank=rank,
        similarity=similarity,
        provenance=f"fixture:{module}",
    )


def test_consensus_counts_distinct_modules_without_averaging_scores():
    report = build_evidence_report([
        row("stumpy", 1_000, 9_000, rank=2, similarity=0.99),
        row("pattern", 1_000, 9_000, rank=4, similarity=0.55),
        row("regime", 500, 8_000, rank=1, similarity=1.0),
    ])
    first = report.candidates[0]
    assert first.supporting_modules == ("pattern", "stumpy")
    assert first.module_count == 2
    assert first.mean_rank == 3.0
    assert "probability" in report.to_dict()["interpretation"]


def test_minimum_support_filters_candidates():
    report = build_evidence_report([
        row("stumpy", 1_000, 9_000),
        row("pattern", 1_000, 9_000),
        row("regime", 500, 8_000),
    ], min_supporting_modules=2)
    assert len(report.candidates) == 1
    assert report.candidates[0].candidate_start_time == 1_000


def test_future_or_overlapping_candidate_is_rejected():
    with pytest.raises(ValueError, match="strictly before"):
        row("stumpy", 9_000, 10_000)


def test_mixed_query_context_is_rejected():
    a = row("stumpy", 1_000, 9_000)
    b = ResearchEvidence(
        module="pattern", algorithm_version="0.1.0", feature_set="x",
        interval="1h", query_start_time=10_000, query_end_time=20_000,
        candidate_start_time=1_000, candidate_end_time=9_000,
        rank=1, similarity=0.8, provenance="fixture",
    )
    with pytest.raises(ValueError, match="same query"):
        build_evidence_report([a, b])


def test_duplicate_module_candidate_is_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        build_evidence_report([
            row("stumpy", 1_000, 9_000),
            row("stumpy", 1_000, 9_000, rank=2),
        ])


def test_empty_evidence_and_invalid_threshold_are_rejected():
    with pytest.raises(ValueError, match="at least one"):
        build_evidence_report([])
    with pytest.raises(ValueError, match="integer"):
        build_evidence_report([row("stumpy", 1_000, 9_000)], min_supporting_modules=True)
