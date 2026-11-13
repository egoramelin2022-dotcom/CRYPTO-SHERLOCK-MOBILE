"""Chronological walk-forward fold construction with purge and embargo.

This module only creates index ranges. It does not fit models, select
strategies, or inspect future outcomes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    """One expanding-window train/validation split using half-open ranges."""

    fold: int
    train_start: int
    train_end_exclusive: int
    validation_start: int
    validation_end_exclusive: int
    purge_bars: int
    embargo_bars: int

    @property
    def train_size(self) -> int:
        return self.train_end_exclusive - self.train_start

    @property
    def validation_size(self) -> int:
        return self.validation_end_exclusive - self.validation_start

    def to_dict(self) -> dict:
        result = asdict(self)
        result["train_size"] = self.train_size
        result["validation_size"] = self.validation_size
        return result


def build_walk_forward_folds(
    n_samples: int,
    *,
    initial_train_size: int,
    validation_size: int,
    max_horizon: int,
    embargo_bars: int = 0,
    step_size: int | None = None,
    max_folds: int | None = None,
) -> tuple[WalkForwardFold, ...]:
    """Build expanding chronological folds with label-overlap protection.

    `initial_train_size` is the number of usable training observations in
    the first fold. The first validation window starts after a gap of
    `max_horizon + embargo_bars` observations. Later folds expand training
    through all observations that are safely in the past.

    Validation windows are separated by at least
    `validation_size + max_horizon + embargo_bars`, so their forward outcome
    windows cannot overlap when outcomes use at most `max_horizon` bars.
    All ranges are half-open. Incomplete final validation windows are omitted.
    """
    integer_values = {
        "n_samples": n_samples,
        "initial_train_size": initial_train_size,
        "validation_size": validation_size,
        "max_horizon": max_horizon,
        "embargo_bars": embargo_bars,
    }
    for name, value in integer_values.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
    if n_samples < 0:
        raise ValueError("n_samples must be nonnegative")
    if initial_train_size < 1:
        raise ValueError("initial_train_size must be >= 1")
    if validation_size < 1:
        raise ValueError("validation_size must be >= 1")
    if max_horizon < 1:
        raise ValueError("max_horizon must be >= 1")
    if embargo_bars < 0:
        raise ValueError("embargo_bars must be nonnegative")

    minimum_step = validation_size + max_horizon + embargo_bars
    if step_size is None:
        step_size = minimum_step
    if isinstance(step_size, bool) or not isinstance(step_size, int):
        raise ValueError("step_size must be an integer")
    if step_size < minimum_step:
        raise ValueError(
            "step_size must keep validation outcome windows and embargo separate"
        )
    if max_folds is not None:
        if (isinstance(max_folds, bool) or not isinstance(max_folds, int)
                or max_folds < 1):
            raise ValueError("max_folds must be a positive integer")

    purge_bars = max_horizon
    first_validation_start = initial_train_size + purge_bars + embargo_bars
    folds: list[WalkForwardFold] = []
    validation_start = first_validation_start

    while validation_start + validation_size <= n_samples:
        train_end = validation_start - purge_bars - embargo_bars
        if train_end < initial_train_size:
            raise RuntimeError("internal fold construction error")
        fold = WalkForwardFold(
            fold=len(folds),
            train_start=0,
            train_end_exclusive=train_end,
            validation_start=validation_start,
            validation_end_exclusive=validation_start + validation_size,
            purge_bars=purge_bars,
            embargo_bars=embargo_bars,
        )
        folds.append(fold)
        if max_folds is not None and len(folds) >= max_folds:
            break
        validation_start += step_size

    return tuple(folds)
