"""Point-in-time orchestration for Pattern Intelligence and STUMPY evidence.

This module coordinates discovery, consensus, and post-discovery outcomes.
It never turns similarity into a probability or trading signal.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from app.market_data.candles import Candle
from app.research.ensemble import EnsembleEvidenceReport, ResearchEvidence, build_evidence_report
from app.research.evidence_adapters import pattern_search_evidence, stumpy_matches_evidence
from app.research.outcome_evaluation import ForwardEvaluation, evaluate_forward_path
from app.research.outcome_summary import HorizonOutcomeSummary, summarize_forward_outcomes
from app.research.pattern_intelligence import SearchMode, search_analogs
from app.research.stumpy_adapter import find_query_matches


@dataclass(frozen=True, slots=True)
class CandidateForwardReport:
    candidate_start_time: int
    candidate_end_time: int
    supporting_modules: tuple[str, ...]
    forward: ForwardEvaluation

    def to_dict(self) -> dict:
        return {
            "candidate_start_time": self.candidate_start_time,
            "candidate_end_time": self.candidate_end_time,
            "supporting_modules": list(self.supporting_modules),
            "forward": self.forward.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ModuleAblation:
    """Leave-one-module-out candidate-set impact, not predictive value."""

    removed_module: str
    candidate_count_without_module: int
    full_candidates_retained: int
    full_candidates_lost: int
    additional_candidates: int

    def to_dict(self) -> dict:
        return {
            "removed_module": self.removed_module,
            "candidate_count_without_module": self.candidate_count_without_module,
            "full_candidates_retained": self.full_candidates_retained,
            "full_candidates_lost": self.full_candidates_lost,
            "additional_candidates": self.additional_candidates,
            "interpretation": "Discovery-set impact only; not evidence of predictive edge.",
        }


@dataclass(frozen=True, slots=True)
class EnsembleSearchRun:
    symbol: str
    interval: str
    query_start_time: int
    query_end_time: int
    query_start_index: int
    query_end_index: int
    horizons: tuple[int, ...]
    pattern_candidate_count: int
    stumpy_candidate_count: int
    evidence_count: int
    ensemble: EnsembleEvidenceReport | None
    ablations: tuple[ModuleAblation, ...]
    forward_evaluations: tuple[CandidateForwardReport, ...]
    outcome_summary: tuple[HorizonOutcomeSummary, ...]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "query_start_time": self.query_start_time,
            "query_end_time": self.query_end_time,
            "query_start_index": self.query_start_index,
            "query_end_index": self.query_end_index,
            "horizons": list(self.horizons),
            "pattern_candidate_count": self.pattern_candidate_count,
            "stumpy_candidate_count": self.stumpy_candidate_count,
            "evidence_count": self.evidence_count,
            "ensemble": self.ensemble.to_dict() if self.ensemble else None,
            "ablations": [item.to_dict() for item in self.ablations],
            "forward_evaluations": [item.to_dict() for item in self.forward_evaluations],
            "outcome_summary": [item.to_dict() for item in self.outcome_summary],
            "outcome_summary_method": (
                "Per-horizon descriptive aggregates over available candidate outcomes. "
                "SIDEWAYS requires both max range and absolute close move thresholds; "
                "LONG/SHORT positive rates are net of configured costs."
            ),
            "interpretation": (
                "Historical analogue agreement and forward outcomes only; "
                "not a probability, forecast, or trading signal."
            ),
        }


def run_ensemble_search(
    candles: Sequence[Candle],
    *,
    query_start_index: int,
    query_end_index: int,
    mode: SearchMode = "free",
    top_k: int = 10,
    horizons: Sequence[int] = (1, 4, 16, 32),
    min_supporting_modules: int = 1,
    include_stumpy: bool = False,
    fee_bps_per_side: float = 0.0,
    slippage_bps_per_side: float = 0.0,
) -> EnsembleSearchRun:
    """Run pattern and optional STUMPY discovery on one closed-candle series.

    The history supplied to STUMPY ends early enough that the maximum
    forward-outcome horizon of any candidate cannot overlap the query.
    Evidence is grouped by exact candidate timestamps. Forward outcomes are
    evaluated only after evidence collection and use the next candle open.
    """
    if not candles:
        raise ValueError("candles must not be empty")
    if (isinstance(min_supporting_modules, bool)
            or not isinstance(min_supporting_modules, int)
            or min_supporting_modules < 1):
        raise ValueError("min_supporting_modules must be an integer >= 1")
    if not horizons:
        raise ValueError("at least one forward horizon is required")
    normalized_horizons: list[int] = []
    for horizon in horizons:
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
            raise ValueError("horizons must be positive integers")
        if horizon in normalized_horizons:
            raise ValueError("horizons must not contain duplicates")
        normalized_horizons.append(horizon)
    for label, value in (
        ("fee_bps_per_side", fee_bps_per_side),
        ("slippage_bps_per_side", slippage_bps_per_side),
    ):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0 or value >= 10_000):
            raise ValueError(f"{label} must be finite and in [0, 10000)")
    if fee_bps_per_side + slippage_bps_per_side >= 10_000:
        raise ValueError("combined per-side costs must be below 10000 bps")

    # search_analogs performs canonical candle, symbol, timeframe and gap checks.
    pattern_result = search_analogs(
        candles,
        query_start=query_start_index,
        query_end=query_end_index,
        mode=mode,
        top_k=top_k,
        horizons=normalized_horizons,
    )
    pattern_rows = pattern_search_evidence(pattern_result, candles)
    evidence: list[ResearchEvidence] = list(pattern_rows)
    stumpy_count = 0

    if include_stumpy and pattern_result.segment_length >= 3:
        history_end_exclusive = query_start_index - max(normalized_horizons)
        history = candles[:max(0, history_end_exclusive)]
        query = candles[query_start_index:query_end_index + 1]
        if len(history) >= len(query):
            # Candle body log-returns are point-in-time features once each
            # candle has closed. STUMPY only sees the frozen historical prefix.
            history_features = [
                math.log(c.close / c.open) for c in history
            ]
            query_features = [
                math.log(c.close / c.open) for c in query
            ]
            matches = find_query_matches(
                history_features, query_features, top_k=top_k,
            )
            stumpy_rows = stumpy_matches_evidence(
                matches,
                history_open_times=[c.open_time for c in history],
                query_open_times=[c.open_time for c in query],
                interval=candles[0].interval,
            )
            evidence.extend(stumpy_rows)
            stumpy_count = len(stumpy_rows)

    report = (
        build_evidence_report(
            evidence, min_supporting_modules=min_supporting_modules,
        )
        if evidence else None
    )
    ablation_reports: list[ModuleAblation] = []
    if report is not None:
        full_keys = {
            (item.candidate_start_time, item.candidate_end_time)
            for item in report.candidates
        }
        for module in sorted({row.module for row in evidence}):
            reduced_rows = [row for row in evidence if row.module != module]
            reduced_report = (
                build_evidence_report(
                    reduced_rows, min_supporting_modules=min_supporting_modules,
                )
                if reduced_rows else None
            )
            reduced_keys = {
                (item.candidate_start_time, item.candidate_end_time)
                for item in reduced_report.candidates
            } if reduced_report else set()
            ablation_reports.append(ModuleAblation(
                removed_module=module,
                candidate_count_without_module=len(reduced_keys),
                full_candidates_retained=len(full_keys & reduced_keys),
                full_candidates_lost=len(full_keys - reduced_keys),
                additional_candidates=len(reduced_keys - full_keys),
            ))

    index_by_open_time = {c.open_time: i for i, c in enumerate(candles)}
    forward_reports: list[CandidateForwardReport] = []
    if report is not None:
        for candidate in report.candidates:
            end_index = index_by_open_time[candidate.candidate_end_time]
            forward = evaluate_forward_path(
                candles,
                candidate_end_index=end_index,
                horizons=normalized_horizons,
                fee_bps_per_side=fee_bps_per_side,
                slippage_bps_per_side=slippage_bps_per_side,
            )
            forward_reports.append(CandidateForwardReport(
                candidate_start_time=candidate.candidate_start_time,
                candidate_end_time=candidate.candidate_end_time,
                supporting_modules=candidate.supporting_modules,
                forward=forward,
            ))

    outcome_summary = summarize_forward_outcomes(
        [item.forward for item in forward_reports]
    )

    query_start = candles[query_start_index]
    query_end = candles[query_end_index]
    return EnsembleSearchRun(
        symbol=query_start.symbol,
        interval=query_start.interval,
        query_start_time=query_start.open_time,
        query_end_time=query_end.open_time,
        query_start_index=query_start_index,
        query_end_index=query_end_index,
        horizons=tuple(normalized_horizons),
        pattern_candidate_count=len(pattern_rows),
        stumpy_candidate_count=stumpy_count,
        evidence_count=len(evidence),
        ensemble=report,
        ablations=tuple(ablation_reports),
        forward_evaluations=tuple(forward_reports),
        outcome_summary=outcome_summary,
    )
