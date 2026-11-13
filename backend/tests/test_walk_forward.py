import pytest

from app.research.walk_forward import build_walk_forward_folds


def test_first_fold_has_initial_train_and_purge_embargo_gap():
    folds = build_walk_forward_folds(
        100, initial_train_size=40, validation_size=10,
        max_horizon=5, embargo_bars=2,
    )
    first = folds[0]
    assert (first.train_start, first.train_end_exclusive) == (0, 40)
    assert (first.validation_start, first.validation_end_exclusive) == (47, 57)
    assert first.purge_bars == 5
    assert first.embargo_bars == 2


def test_expanding_training_and_validation_outcomes_do_not_overlap():
    folds = build_walk_forward_folds(
        100, initial_train_size=40, validation_size=10,
        max_horizon=5, embargo_bars=2,
    )
    assert len(folds) >= 2
    first, second = folds[:2]
    assert second.train_end_exclusive == 57
    assert second.train_size > first.train_size
    assert second.validation_start >= (
        first.validation_end_exclusive + 5 + 2
    )


def test_custom_step_cannot_allow_validation_label_overlap():
    with pytest.raises(ValueError, match="step_size"):
        build_walk_forward_folds(
            100, initial_train_size=40, validation_size=10,
            max_horizon=5, embargo_bars=2, step_size=16,
        )


def test_incomplete_final_validation_window_is_omitted():
    folds = build_walk_forward_folds(
        60, initial_train_size=40, validation_size=10,
        max_horizon=5, embargo_bars=2,
    )
    assert len(folds) == 1
    assert folds[0].validation_end_exclusive == 57


def test_max_folds_and_invalid_inputs():
    folds = build_walk_forward_folds(
        200, initial_train_size=20, validation_size=5,
        max_horizon=2, max_folds=2,
    )
    assert len(folds) == 2
    with pytest.raises(ValueError, match="initial_train_size"):
        build_walk_forward_folds(
            100, initial_train_size=0, validation_size=5, max_horizon=2,
        )
    with pytest.raises(ValueError, match="integer"):
        build_walk_forward_folds(
            100, initial_train_size=True, validation_size=5, max_horizon=2,
        )
