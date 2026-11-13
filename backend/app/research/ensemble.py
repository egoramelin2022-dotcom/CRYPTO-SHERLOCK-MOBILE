"""Evidence contracts for combining independent research engines.

This module deliberately produces candidate evidence summaries, not trade
signals, probabilities, or expected returns. Outcome labels belong in a
separate evaluator after candidate discovery has been frozen.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class ResearchEvidence:
    """One engine's point-in-time observation about one historical analogue."""

    module: str
    algorithm_version: str
    feature_set: str
    interval: str
    query_start_time: int
    query_end_time: int
    candidate_start_time: int
    candidate_end_time: int
    rank: int
    similarity: float
    provenance: str

    def __post_init__(self) -> None:
        for name in ("module", "algorithm_version", "feature_set", "interval", "provenance"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.query_start_time > self.query_end_time:
            raise ValueError("query timestamps are reversed")
        if self.candidate_start_time > self.candidate_end_time:
            raise ValueError("candidate timestamps are reversed")
        if self.candidate_end_time >= self.query_start_time:
            raise ValueError("candidate must end strictly before query starts")
        if isinstance(self.rank, bool) or self.rank < 1:
            raise ValueError("rank must be >= 1")
        if not 0.0 <= self.similarity <= 1.0:
            raise ValueError("similarity must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class CandidateConsensus:
    """Descriptive cross-engine agreement; not a calibrated confidence score."""

    candidate_start_time: int
    candidate_end_time: int
    supporting_modules: tuple[str, ...]
    best_rank_by_module: dict[str, int]
    mean_rank: float

    @property
    def module_count(self) -> int:
        return len(self.supporting_modules)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["module_count"] = self.module_count
        return result


@dataclass(frozen=True, slots=True)
class EnsembleEvidenceReport:
    interval: str
    query_start_time: int
    query_end_time: int
    evidence_count: int
    module_count: int
    candidates: tuple[CandidateConsensus, ...]

    def to_dict(self) -> dict:
        return {
            "interval": self.interval,
            "query_start_time": self.query_start_time,
            "query_end_time": self.query_end_time,
            "evidence_count": self.evidence_count,
            "module_count": self.module_count,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "interpretation": (
                "Descriptive agreement only; not a probability, forecast, "
                "or trading signal."
            ),
        }


def build_evidence_report(
    evidence: Iterable[ResearchEvidence],
    *,
    min_supporting_modules: int = 1,
) -> EnsembleEvidenceReport:
    """Group identical historical windows and summarize distinct-engine support.

    Candidate windows are matched by exact start/end timestamps. The function
    never averages similarity scores across engines: score scales can differ
    and correlated engines must not be mistaken for independent confirmation.
    """
    if (isinstance(min_supporting_modules, bool)
            or not isinstance(min_supporting_modules, int)
            or min_supporting_modules < 1):
        raise ValueError("min_supporting_modules must be an integer >= 1")

    rows = list(evidence)
    if not rows:
        raise ValueError("at least one evidence row is required")

    context = {
        (row.interval, row.query_start_time, row.query_end_time)
        for row in rows
    }
    if len(context) != 1:
        raise ValueError("all evidence must refer to the same query and interval")

    # One engine may report a candidate only once. Silently keeping its best
    # row would hide duplicate emissions and inflate apparent support.
    seen: set[tuple[str, int, int]] = set()
    grouped: dict[tuple[int, int], dict[str, int]] = {}
    for row in rows:
        identity = (row.module, row.candidate_start_time, row.candidate_end_time)
        if identity in seen:
            raise ValueError("duplicate candidate evidence from the same module")
        seen.add(identity)
        key = (row.candidate_start_time, row.candidate_end_time)
        grouped.setdefault(key, {})[row.module] = row.rank

    candidates = []
    for (start, end), ranks in grouped.items():
        if len(ranks) < min_supporting_modules:
            continue
        ordered = tuple(sorted(ranks))
        candidates.append(CandidateConsensus(
            candidate_start_time=start,
            candidate_end_time=end,
            supporting_modules=ordered,
            best_rank_by_module=dict(sorted(ranks.items())),
            mean_rank=sum(ranks.values()) / len(ranks),
        ))

    candidates.sort(key=lambda item: (
        -item.module_count, item.mean_rank,
        item.candidate_start_time, item.candidate_end_time,
    ))
    interval, query_start, query_end = next(iter(context))
    return EnsembleEvidenceReport(
        interval=interval,
        query_start_time=query_start,
        query_end_time=query_end,
        evidence_count=len(rows),
        module_count=len({row.module for row in rows}),
        candidates=tuple(candidates),
    )
