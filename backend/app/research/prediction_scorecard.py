"""Out-of-sample classification scorecards for historical predictions.

A score is computed only from walk-forward predictions whose forward outcomes
were hidden from the decision process. It is a historical diagnostic, never a
probability that the next prediction will be correct.
"""
from __future__ import annotations

from typing import Iterable

SIDES = ("LONG", "SHORT", "FLAT")


def realized_side(long_net_return: float, short_net_return: float) -> str:
    """Classify the realized cost-adjusted outcome into LONG/SHORT/FLAT."""
    if long_net_return > 0.0 and short_net_return <= 0.0:
        return "LONG"
    if short_net_return > 0.0 and long_net_return <= 0.0:
        return "SHORT"
    if long_net_return > 0.0 and short_net_return > 0.0:
        return "LONG" if long_net_return >= short_net_return else "SHORT"
    return "FLAT"


def build_prediction_scorecard(
    predictions: Iterable[dict[str, object]],
) -> dict[str, object]:
    """Summarize directional hit rate, coverage and 3-class diagnostics.

    Each row must contain predicted_side, realized_long_net and
    realized_short_net. FLAT predictions count in overall accuracy and are
    scored correct only when neither direction cleared assumed costs.
    Directional hit rate is separately calculated only over LONG/SHORT calls.
    """
    rows = list(predictions)
    matrix = {actual: {predicted: 0 for predicted in SIDES} for actual in SIDES}
    for row in rows:
        predicted = row.get("predicted_side")
        if predicted not in SIDES:
            raise ValueError("predicted_side must be LONG, SHORT or FLAT")
        long_value = row.get("realized_long_net")
        short_value = row.get("realized_short_net")
        if (isinstance(long_value, bool) or not isinstance(long_value, (int, float))
                or isinstance(short_value, bool) or not isinstance(short_value, (int, float))):
            raise ValueError("realized net returns must be numeric")
        actual = realized_side(float(long_value), float(short_value))
        matrix[actual][str(predicted)] += 1

    total = len(rows)
    directional_calls = sum(matrix[actual][predicted]
                             for actual in SIDES for predicted in ("LONG", "SHORT"))
    directional_hits = matrix["LONG"]["LONG"] + matrix["SHORT"]["SHORT"]
    correct = sum(matrix[side][side] for side in SIDES)
    recalls = {}
    f1_values = []
    for side in SIDES:
        support = sum(matrix[side].values())
        predicted_count = sum(matrix[actual][side] for actual in SIDES)
        true_positive = matrix[side][side]
        recall = true_positive / support if support else None
        precision = true_positive / predicted_count if predicted_count else None
        if recall is not None and precision is not None and recall + precision > 0:
            f1 = 2 * precision * recall / (precision + recall)
            f1_values.append(f1)
        else:
            f1 = None
        recalls[side] = {
            "support": support,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    all_classes_present = all(item["support"] > 0 for item in recalls.values())
    available_recalls = [item["recall"] for item in recalls.values()
                         if item["recall"] is not None]
    balanced_accuracy = (
        sum(available_recalls) / len(SIDES)
        if all_classes_present else None
    )
    macro_f1 = (
        sum(f1_values) / len(SIDES)
        if all_classes_present and len(f1_values) == len(SIDES) else None
    )
    return {
        "status": "evaluated" if total else "insufficient_sample",
        "definition": (
            "Realized class is based on forward LONG/SHORT net returns after "
            "the configured round-trip costs; FLAT means neither side was profitable."
        ),
        "samples": total,
        "correct": correct,
        "accuracy": correct / total if total else None,
        "accuracy_percent": 100.0 * correct / total if total else None,
        "directional_calls": directional_calls,
        "directional_hits": directional_hits,
        "directional_hit_rate": (
            directional_hits / directional_calls if directional_calls else None
        ),
        "directional_hit_rate_percent": (
            100.0 * directional_hits / directional_calls if directional_calls else None
        ),
        "coverage": directional_calls / total if total else None,
        "coverage_percent": 100.0 * directional_calls / total if total else None,
        "balanced_accuracy": (
            sum(available_recalls) / len(available_recalls) if available_recalls else None
        ),
        "macro_f1": sum(f1_values) / len(f1_values) if f1_values else None,
        "class_metrics": recalls,
        "confusion_matrix": matrix,
        "warning": (
            "Historical out-of-sample score only. It is not a calibrated probability "
            "or a guarantee of future accuracy. Interpret alongside sample count, "
            "baselines, costs, drawdown and temporal stability."
        ),
    }
