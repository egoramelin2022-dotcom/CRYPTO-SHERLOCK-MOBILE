import sys
import types

import pytest

from app.research.stumpy_adapter import find_query_matches


def test_adapter_ranks_matches_and_applies_non_overlap(monkeypatch):
    import numpy as np

    fake = types.SimpleNamespace(
        mass=lambda query, history: np.asarray([0.1, 0.2, 0.05, 0.3, 0.4, 0.01, 0.5])
    )
    monkeypatch.setitem(sys.modules, "stumpy", fake)
    result = find_query_matches(
        [0, 1, 2, 3, 4, 5, 6, 7, 8],
        [1, 2, 3],
        top_k=3,
        exclusion_zone=3,
    )
    assert [item.start_index for item in result] == [5, 2]
    assert result[0].distance == pytest.approx(0.01)


def test_adapter_rejects_nonfinite_values(monkeypatch):
    import numpy as np

    fake = types.SimpleNamespace(mass=lambda query, history: np.zeros(3))
    monkeypatch.setitem(sys.modules, "stumpy", fake)
    with pytest.raises(ValueError, match="finite"):
        find_query_matches([1, 2, float("nan"), 4], [1, 2, 3])


def test_adapter_rejects_short_query(monkeypatch):
    import numpy as np

    fake = types.SimpleNamespace(mass=lambda query, history: np.zeros(1))
    monkeypatch.setitem(sys.modules, "stumpy", fake)
    with pytest.raises(ValueError, match="at least 3"):
        find_query_matches([1, 2, 3], [1, 2])


def test_adapter_reports_missing_optional_dependency(monkeypatch):
    real_import = __import__

    def blocked(name, *args, **kwargs):
        if name == "stumpy":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked)
    with pytest.raises(RuntimeError, match="optional"):
        find_query_matches([1, 2, 3, 4], [1, 2, 3])
