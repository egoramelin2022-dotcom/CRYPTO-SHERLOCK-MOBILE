import sys
import types

import pytest

from app.research.stumpy_adapter import find_query_matches


class FakeArray(list):
    ndim = 1

    @property
    def size(self):
        return len(self)

    def all(self):
        return all(self)


class FakeNumpy(types.SimpleNamespace):
    float64 = float

    @staticmethod
    def asarray(values, dtype=None):
        return FakeArray(values)

    @staticmethod
    def isfinite(values):
        return FakeArray(
            value == value and value not in (float("inf"), float("-inf"))
            for value in values
        )


def install_fake_numpy(monkeypatch):
    monkeypatch.setitem(sys.modules, "numpy", FakeNumpy())


def test_adapter_ranks_matches_and_applies_non_overlap(monkeypatch):
    install_fake_numpy(monkeypatch)
    fake_stumpy = types.SimpleNamespace(
        mass=lambda query, history: FakeArray([0.1, 0.2, 0.05, 0.3, 0.4, 0.01, 0.5])
    )
    monkeypatch.setitem(sys.modules, "stumpy", fake_stumpy)
    result = find_query_matches(
        [0, 1, 2, 3, 4, 5, 6, 7, 8],
        [1, 2, 3],
        top_k=3,
        exclusion_zone=3,
    )
    assert [item.start_index for item in result] == [5, 2]
    assert result[0].distance == pytest.approx(0.01)


def test_adapter_rejects_nonfinite_values(monkeypatch):
    install_fake_numpy(monkeypatch)
    fake_stumpy = types.SimpleNamespace(mass=lambda query, history: FakeArray([0, 0]))
    monkeypatch.setitem(sys.modules, "stumpy", fake_stumpy)
    with pytest.raises(ValueError, match="finite"):
        find_query_matches([1, 2, float("nan"), 4], [1, 2, 3])


def test_adapter_rejects_short_query(monkeypatch):
    install_fake_numpy(monkeypatch)
    fake_stumpy = types.SimpleNamespace(mass=lambda query, history: FakeArray([0]))
    monkeypatch.setitem(sys.modules, "stumpy", fake_stumpy)
    with pytest.raises(ValueError, match="at least 3"):
        find_query_matches([1, 2, 3], [1, 2])


def test_adapter_reports_missing_optional_dependency(monkeypatch):
    install_fake_numpy(monkeypatch)
    real_import = __import__

    def blocked(name, *args, **kwargs):
        if name == "stumpy":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked)
    with pytest.raises(RuntimeError, match="optional"):
        find_query_matches([1, 2, 3, 4], [1, 2, 3])
