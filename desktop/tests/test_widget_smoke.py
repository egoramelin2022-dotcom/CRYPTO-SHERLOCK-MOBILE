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
    for widget in widgets:
        widget.close()
        widget.deleteLater()
    app.processEvents()
