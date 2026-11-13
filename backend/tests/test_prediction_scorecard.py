import pytest

from app.research.prediction_scorecard import (
    build_prediction_scorecard,
    realized_side,
)


def test_realized_side_uses_cost_adjusted_direction_and_flat_class():
    assert realized_side(0.01, -0.01) == "LONG"
    assert realized_side(-0.01, 0.01) == "SHORT"
    assert realized_side(-0.001, -0.001) == "FLAT"


def test_scorecard_separates_directional_hit_rate_from_coverage():
    rows = [
        {"predicted_side": "LONG", "realized_long_net": 0.02, "realized_short_net": -0.02},
        {"predicted_side": "SHORT", "realized_long_net": -0.01, "realized_short_net": 0.01},
        {"predicted_side": "LONG", "realized_long_net": -0.01, "realized_short_net": 0.01},
        {"predicted_side": "FLAT", "realized_long_net": -0.01, "realized_short_net": -0.01},
    ]
    result = build_prediction_scorecard(rows)
    assert result["samples"] == 4
    assert result["correct"] == 3
    assert result["accuracy_percent"] == 75.0
    assert result["directional_calls"] == 3
    assert result["directional_hits"] == 2
    assert result["directional_hit_rate_percent"] == pytest.approx(66.6666667)
    assert result["coverage_percent"] == 75.0
    assert result["confusion_matrix"]["SHORT"]["LONG"] == 1
    assert result["confusion_matrix"]["FLAT"]["FLAT"] == 1
    assert "not a calibrated probability" in result["warning"]


def test_scorecard_empty_sample_is_explicitly_unavailable():
    result = build_prediction_scorecard([])
    assert result["status"] == "insufficient_sample"
    assert result["accuracy"] is None
    assert result["directional_hit_rate"] is None


def test_scorecard_rejects_invalid_prediction_side():
    with pytest.raises(ValueError, match="predicted_side"):
        build_prediction_scorecard([{
            "predicted_side": "BUY",
            "realized_long_net": 0.01,
            "realized_short_net": -0.01,
        }])
