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
        PaperPanel("http://127.0.0.1:1"),
        DownloadPanel("http://127.0.0.1:1"),
        SystemPanel("http://127.0.0.1:1"),
    ]
    assert len(widgets) == 7
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
