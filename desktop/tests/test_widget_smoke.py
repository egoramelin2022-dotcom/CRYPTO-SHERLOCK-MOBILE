import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from desktop.download_panel import DownloadPanel
from desktop.market_panel import MarketPanel
from desktop.paper_panel import PaperPanel
from desktop.research_panel import ResearchPanel
from desktop.system_panel import SystemPanel


def test_desktop_panels_construct_without_backend_or_network():
    app = QApplication.instance() or QApplication([])
    widgets = [
        MarketPanel("http://127.0.0.1:1"),
        ResearchPanel("http://127.0.0.1:1", "/v1/research/pattern", "pattern"),
        ResearchPanel("http://127.0.0.1:1", "/v1/research/multitimeframe", "mtf"),
        ResearchPanel("http://127.0.0.1:1", "/v1/research/ensemble", "ensemble"),
        ResearchPanel("http://127.0.0.1:1", "/v1/research/walk-forward", "walk_forward"),
        PaperPanel("http://127.0.0.1:1"),
        DownloadPanel("http://127.0.0.1:1"),
        SystemPanel("http://127.0.0.1:1"),
    ]
    assert len(widgets) == 8
    assert not widgets[0].auto_refresh.isActive()  # Market feed is idle until its page is opened.
    for widget in widgets:
        widget.close()
        widget.deleteLater()
    app.processEvents()



def test_research_panel_formats_stage_scores_and_forward_outcomes():
    app = QApplication.instance() or QApplication([])
    panel = ResearchPanel("http://127.0.0.1:1", "/v1/research/pattern", "pattern")
    panel.on_completed({
        "kind": "pattern_research",
        "updated_at": "test",
        "result": {
            "history_candles": 100,
            "data_freshness": {
                "is_stale": True, "age_hours": 12.0, "stale_after_hours": 0.75,
            },
            "execution_assumptions": {
                "entry": "next candle open", "exit": "horizon candle close",
                "fee_bps_per_side": 5.0, "slippage_bps_per_side": 2.0,
                "short_side": "theoretical price-return calculation",
            },
            "historical_gaps": 1,
            "contiguous_segments": 2,
            "candidates_examined": 5,
            "stage_weights": {"preliminary_decline": 0.2},
            "query_chart": {"normalized_close": [100.0, 101.0]},
            "analogs": [{
                "analog": {
                    "similarity": 0.8,
                    "start_time": 1,
                    "end_time": 2,
                    "stage_similarities": {"preliminary_decline": 0.9},
                },
                "chart": {"normalized_close": [100.0, 100.5]},
                "forward_path": {"outcomes": [{
                    "horizon": 1,
                    "long_net_return": 0.01,
                    "short_net_return": -0.02,
                }]},
            }],
        },
    })
    rendered = panel.output.toPlainText()
    assert "FIVE-STAGE WEIGHTS" in rendered
    assert "Preliminary Decline: 20%" in rendered
    assert "STALE — historical search uses old local data" in rendered
    assert "Fees: 5.0 bps/side" in rendered
    assert "Slippage: 2.0 bps/side" in rendered
    assert "LONG net +1.00%" in rendered
    panel.close()
    app.processEvents()



def test_download_panel_exposes_separate_archive_and_recent_sync_actions():
    app = QApplication.instance() or QApplication([])
    panel = DownloadPanel("http://127.0.0.1:1")
    assert panel.run_button.text() == "DOWNLOAD ARCHIVES TO STAGING"
    assert panel.sync_button.text() == "SYNC CURRENT MONTH"
    panel.close()
    app.processEvents()


def test_walk_forward_panel_renders_out_of_sample_baselines():
    app = QApplication.instance() or QApplication([])
    panel = ResearchPanel("http://127.0.0.1:1", "/v1/research/walk-forward", "walk_forward")
    panel.on_completed({
        "kind": "walk_forward_research",
        "updated_at": "test",
        "result": {
            "method": "expanding_window_historical_analog_median",
            "evaluated_folds": 4,
            "history_candles": 400,
            "skipped_folds": [],
            "anti_leakage": {"embargo_candles": 64},
            "temporal_stability_note": "Chronological thirds, not market regimes.",
            "temporal_stability_by_horizon": {
                "4": {
                    "early": {"model": {"cumulative_return_sum": 0.01, "positive_fold_rate": 0.5, "trade_rate": 0.5}},
                    "middle": {"model": {"cumulative_return_sum": 0.005, "positive_fold_rate": 0.5, "trade_rate": 1.0}},
                    "recent": {"model": {"cumulative_return_sum": 0.01, "positive_fold_rate": 1.0, "trade_rate": 0.5}},
                }
            },
            "metrics_by_horizon": {
                "4": {
                    "model": {"cumulative_return_sum": 0.025, "average_return_per_fold": 0.00625, "positive_fold_rate": 0.5, "max_drawdown_sum_basis": 0.01},
                    "always_long": {"cumulative_return_sum": 0.01, "average_return_per_fold": 0.0025, "positive_fold_rate": 0.5, "max_drawdown_sum_basis": 0.02},
                    "always_short": {"cumulative_return_sum": -0.01, "average_return_per_fold": -0.0025, "positive_fold_rate": 0.25, "max_drawdown_sum_basis": 0.03},
                    "flat": {"cumulative_return_sum": 0.0, "average_return_per_fold": 0.0, "positive_fold_rate": 0.0, "max_drawdown_sum_basis": 0.0},
                }
            },
        },
    })
    rendered = panel.output.toPlainText()
    assert "WALK-FORWARD" in rendered
    assert "evaluated folds: 4" in rendered
    assert panel.robustness_button is not None
    assert panel.robustness_button.text() == "RUN ROBUSTNESS AUDIT"
    calls = []
    panel.run_research = lambda endpoint_override=None: calls.append(endpoint_override)
    panel.robustness_button.click()
    assert calls == ["/v1/research/robustness"]
    assert "embargo: 64 candles" in rendered
    assert "Model: sum +2.50%" in rendered
    assert "Always Long: sum +1.00%" in rendered
    assert "TEMPORAL STABILITY" in rendered
    assert "+4 recent: model sum +1.00%" in rendered
    panel.close()
    app.processEvents()

def test_robustness_panel_formats_parameter_stability_without_picking_winner():
    app = QApplication.instance() or QApplication([])
    panel = ResearchPanel(
        "http://127.0.0.1:1", "/v1/research/walk-forward", "walk_forward"
    )
    panel.on_completed({
        "kind": "robustness_research",
        "updated_at": "test",
        "result": {
            "method": "bounded_one_factor_at_a_time_sensitivity",
            "configurations_requested": 5,
            "configurations_evaluated": 4,
            "selection_policy": "Each configuration remains independent; no winner selected.",
            "stability_by_horizon": {
                "4": {
                    "positive_average_return_share": 0.5,
                    "positive_excess_vs_best_baseline_share": 0.25,
                    "median_average_return_per_fold": 0.001,
                }
            },
            "runs": [{
                "configuration": "baseline",
                "query_window": 40,
                "top_k": 10,
                "evaluated_folds": 8,
                "skipped_fold_count": 1,
            }],
        },
    })
    rendered = panel.output.toPlainText()
    assert "ROBUSTNESS AUDIT" in rendered
    assert "Configurations evaluated: 4 / 5" in rendered
    assert "positive configurations 50%" in rendered
    assert "no winner selected" in rendered
    panel.close()
    app.processEvents()
