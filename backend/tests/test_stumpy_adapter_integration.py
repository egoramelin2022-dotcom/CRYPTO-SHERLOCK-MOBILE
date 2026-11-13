"""Real-package integration checks for the optional STUMPY adapter.

These tests run only in the research-integration CI job, where the pinned
STUMPY and NumPy dependencies are installed. Core CI remains lightweight.
"""
import numpy as np

from app.research.stumpy_adapter import find_query_matches


def test_real_mass_finds_repeated_shape_in_history():
    # Same shape at two locations, with a different scale/offset. MASS uses
    # z-normalization, so the shape should still be recognized.
    motif = np.array([0.0, 0.7, -0.2, 1.1, -0.8, 0.3, 0.0], dtype=np.float64)
    history = np.concatenate([
        np.array([4.0, 3.0, 5.0, 2.0]),
        motif * 2.5 + 11.0,
        np.array([8.0, 9.0, 7.0, 6.0, 10.0]),
        motif * 0.4 - 3.0,
        np.array([1.0, 2.0, 4.0]),
    ])
    matches = find_query_matches(
        history,
        motif,
        top_k=5,
        exclusion_zone=len(motif),
    )
    starts = [item.start_index for item in matches]
    assert len(matches) >= 2
    assert 4 in starts
    assert 16 in starts
    assert all(np.isfinite(item.distance) for item in matches)
    assert all(item.distance >= 0 for item in matches)


def test_real_mass_output_is_ranked_and_non_overlapping():
    rng = np.random.default_rng(20261113)
    query = rng.normal(size=12)
    history = np.concatenate([rng.normal(size=40), query, rng.normal(size=40), query])
    matches = find_query_matches(history, query, top_k=4)
    distances = [item.distance for item in matches]
    starts = [item.start_index for item in matches]
    assert distances == sorted(distances)
    assert all(abs(a - b) >= len(query) for i, a in enumerate(starts)
               for b in starts[i + 1:])
