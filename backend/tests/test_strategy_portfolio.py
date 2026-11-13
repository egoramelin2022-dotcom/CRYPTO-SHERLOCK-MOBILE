import pytest

from app.research.strategy_portfolio import analyze_strategy_portfolio


def test_strategy_portfolio_reports_correlation_and_equal_weight_metrics():
    result = analyze_strategy_portfolio({
        "trend": [0.01, -0.01, 0.02, -0.02],
        "reversal": [-0.01, 0.01, -0.01, 0.01],
    })
    assert result["aligned_folds"] == 4
    assert result["pairwise_return_correlation"]["trend|reversal"] == -1.0
    assert result["equal_weight_portfolio"]["cumulative_return_sum"] == 0.0


def test_strategy_portfolio_rejects_misaligned_series():
    with pytest.raises(ValueError, match="identical aligned folds"):
        analyze_strategy_portfolio({"a": [1, 2], "b": [1]})
