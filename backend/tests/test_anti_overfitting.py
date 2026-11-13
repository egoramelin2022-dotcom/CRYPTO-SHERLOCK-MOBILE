import pytest

from app.research.anti_overfitting import probability_of_backtest_overfitting


def test_pbo_is_deterministic_and_reports_partition_counts():
    matrix = {
        "variant_a": [0.02, -0.01, 0.03, -0.02, 0.01, -0.01],
        "variant_b": [0.01, 0.01, 0.00, 0.00, 0.01, 0.01],
        "variant_c": [-0.01, 0.02, -0.01, 0.02, -0.00, 0.02],
    }
    first = probability_of_backtest_overfitting(matrix, max_partitions=100)
    second = probability_of_backtest_overfitting(matrix, max_partitions=100)
    assert first == second
    assert 0 <= first["pbo"] <= 1
    assert first["partitions_evaluated"] > 0
    assert first["aligned_folds"] == 6


def test_pbo_rejects_unaligned_or_odd_fold_counts():
    with pytest.raises(ValueError, match="identical fold counts"):
        probability_of_backtest_overfitting({"a": [1, 2, 3, 4], "b": [1, 2, 3]})
    with pytest.raises(ValueError, match="even-numbered"):
        probability_of_backtest_overfitting({"a": [1, 2, 3], "b": [3, 2, 1]})


def test_pbo_midrank_treats_all_out_of_sample_ties_as_median():
    result = probability_of_backtest_overfitting({
        "variant_a": [0.01, 0.01, 0.01, 0.01],
        "variant_b": [0.01, 0.01, 0.01, 0.01],
        "variant_c": [0.01, 0.01, 0.01, 0.01],
    })
    assert result["pbo"] == 0.0
    assert result["median_logit_rank"] == 0.0
