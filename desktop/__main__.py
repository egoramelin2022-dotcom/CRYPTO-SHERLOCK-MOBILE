"""CRYPTO SHERLOCK Windows desktop research terminal."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import httpx
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
    QVBoxLayout, QWidget,
)

API_DEFAULT = os.getenv("SHERLOCK_API_URL", "http://127.0.0.1:8000")


class HealthWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url.rstrip("/")

    def run(self):
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=3.0)
            response.raise_for_status()
            self.finished.emit(True, "Backend connected")
        except Exception as exc:
            self.finished.emit(False, f"Backend unavailable: {type(exc).__name__}")


class MetricCard(QFrame):
    def __init__(self, title: str, value: str, detail: str, accent: str = "mint"):
        super().__init__()
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        eyebrow = QLabel(title.upper())
        eyebrow.setObjectName("eyebrow")
        number = QLabel(value)
        number.setObjectName("metricValue")
        number.setProperty("accent", accent)
        note = QLabel(detail)
        note.setObjectName("muted")
        layout.addWidget(eyebrow)
        layout.addWidget(number)
        layout.addWidget(note)


class Page(QWidget):
    def __init__(self, title: str, subtitle: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(18)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        sub = QLabel(subtitle)
        sub.setObjectName("pageSubtitle")
        sub.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(sub)
        self.body = QVBoxLayout()
        self.body.setSpacing(16)
        layout.addLayout(self.body)
        layout.addStretch(1)


class MainWindow(QMainWindow):
    NAV_ITEMS = [
        ("Overview", "01"),
        ("Market Data", "02"),
        ("Pattern Intelligence", "03"),
        ("Multi-Timeframe", "04"),
        ("Ensemble Engine", "05"),
        ("Backtesting Lab", "06"),
        ("Paper Trading", "07"),
        ("System Monitor", "08"),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CRYPTO SHERLOCK")
        self.resize(1480, 920)
        self.setMinimumSize(1120, 720)
        self.api_url = API_DEFAULT
        self.health_worker = None
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(252)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 24, 18, 20)
        side.setSpacing(10)

        brand = QLabel("◈  CRYPTO")
        brand.setObjectName("brand")
        brand2 = QLabel("     SHERLOCK")
        brand2.setObjectName("brandSub")
        side.addWidget(brand)
        side.addWidget(brand2)
        side.addSpacing(28)
        section = QLabel("RESEARCH TERMINAL")
        section.setObjectName("eyebrow")
        side.addWidget(section)
        self.nav_buttons = []
        for index, (name, code) in enumerate(self.NAV_ITEMS):
            button = QPushButton(f"{code}     {name}")
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self.show_page(i))
            side.addWidget(button)
            self.nav_buttons.append(button)
        side.addStretch(1)
        version = QLabel("DESKTOP  •  v0.1.0\nPAPER RESEARCH ONLY")
        version.setObjectName("sidebarFoot")
        side.addWidget(version)

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        topbar = QFrame()
        topbar.setObjectName("topbar")
        top = QHBoxLayout(topbar)
        top.setContentsMargins(28, 14, 28, 14)
        self.breadcrumb = QLabel("OVERVIEW  /  MARKET INTELLIGENCE")
        self.breadcrumb.setObjectName("topLabel")
        self.connection = QLabel("●  CHECKING BACKEND")
        self.connection.setObjectName("connection")
        top.addWidget(self.breadcrumb)
        top.addStretch(1)
        top.addWidget(self.connection)
        content.addWidget(topbar)

        self.stack = QStackedWidget()
        self.pages = [
            self.make_overview(),
            self.make_data_page(),
            self.make_module_page("Pattern Intelligence", "Historical analog discovery across candle shapes, movement paths and configurable formation modes.", [
                "Free pattern search — unrestricted sequence matching",
                "Five-stage formation — preserved as a separate selectable mode",
                "Historical candidates must end before the query window",
                "Forward outcomes are measured separately from similarity ranking",
            ]),
            self.make_module_page("Multi-Timeframe Scanner", "Find synchronized market structure across 15M, 4H and 1D without treating an observation as a trading signal.", [
                "15M — long lower-wick event",
                "4H — support sweep and reclaim",
                "1D — unusually large bearish candle during a broader decline",
                "Thresholds remain explicit research parameters",
            ]),
            self.make_module_page("Ensemble Engine", "Compare independent evidence sources. Module agreement is not automatically statistical confirmation.", [
                "Pattern Intelligence evidence adapter",
                "STUMPY motif evidence adapter",
                "Candidate provenance and timestamp validation",
                "No uncalibrated probability or signal averaging",
            ]),
            self.make_module_page("Backtesting Lab", "Chronological validation before any strategy can be considered reliable.", [
                "Walk-forward evaluation",
                "Purged and embargoed time splits",
                "Fees, slippage and separate LONG / SHORT analysis",
                "Baseline comparison and ablation tests",
            ]),
            self.make_module_page("Paper Trading", "Virtual execution only. Live exchange orders are deliberately not implemented.", [
                "Paper portfolio and virtual positions",
                "Risk limits and execution assumptions",
                "No exchange credentials or live order endpoints",
            ]),
            self.make_module_page("System Monitor", "Local services, data integrity and research job health.", [
                "Backend health endpoint",
                "Source database and analytics database status",
                "Historical archive integrity and gap audit",
                "Research job progress",
            ]),
        ]
        for page in self.pages:
            self.stack.addWidget(page)
        content.addWidget(self.stack, 1)
        shell.addWidget(sidebar)
        main = QWidget()
        main.setLayout(content)
        shell.addWidget(main, 1)
        self.show_page(0)
        self.check_backend()

    def card_row(self, cards):
        row = QHBoxLayout()
        row.setSpacing(14)
        for card in cards:
            row.addWidget(card, 1)
        return row

    def make_overview(self):
        page = Page("Market Intelligence", "A focused command center for historical research, market structure and evidence-backed testing.")
        page.body.addLayout(self.card_row([
            MetricCard("Market feed", "—", "Waiting for local backend", "mint"),
            MetricCard("Historical candles", "NOT LOADED", "BTCUSDT · 15M / 4H / 1D", "amber"),
            MetricCard("Research engine", "READY TO CONNECT", "Local analytics services", "blue"),
            MetricCard("Execution mode", "PAPER ONLY", "Live orders disabled", "mint"),
        ]))
        panel = QFrame()
        panel.setObjectName("panel")
        p = QVBoxLayout(panel)
        title = QLabel("RESEARCH WORKSPACE")
        title.setObjectName("panelTitle")
        desc = QLabel("The desktop shell is connected to the CRYPTO SHERLOCK backend when it is running. Historical data and analytics will appear here only after they have been loaded and verified.")
        desc.setObjectName("bodyText")
        desc.setWordWrap(True)
        p.addWidget(title)
        p.addWidget(desc)
        p.addSpacing(12)
        self.backend_detail = QLabel("Backend: checking local service…")
        self.backend_detail.setObjectName("muted")
        p.addWidget(self.backend_detail)
        page.body.addWidget(panel)
        quick = QLabel("RESEARCH MODULES")
        quick.setObjectName("eyebrow")
        page.body.addWidget(quick)
        page.body.addLayout(self.card_row([
            MetricCard("01 / Discovery", "Pattern Lab", "Search historical analogs", "blue"),
            MetricCard("02 / Structure", "MTF Scanner", "15M + 4H + 1D", "mint"),
            MetricCard("03 / Validation", "Walk Forward", "Test out-of-sample", "amber"),
        ]))
        return page

    def make_data_page(self):
        page = Page("Market Data Center", "Manage verified Binance Spot history. The production/source database is never overwritten by staging imports.")
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        title = QLabel("BINANCE SPOT · BTCUSDT")
        title.setObjectName("panelTitle")
        detail = QLabel("Target intervals: 15m, 4h, 1d    •    Start: August 2017    •    Archive integrity: SHA256")
        detail.setObjectName("bodyText")
        detail.setWordWrap(True)
        status = QLabel("DOWNLOAD WORKFLOW  •  IMPLEMENTED IN RESEARCH BRANCH — DESKTOP ACTION WIRING PENDING")
        status.setObjectName("statusPill")
        layout.addWidget(title)
        layout.addWidget(detail)
        layout.addWidget(status)
        page.body.addWidget(panel)
        note = QLabel("This screen is intentionally not showing invented row counts or progress. The next integration step will launch the verified archive downloader as a background task and display real progress.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        page.body.addWidget(note)
        return page

    def make_module_page(self, title, subtitle, items):
        page = Page(title, subtitle)
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 20, 22, 20)
        heading = QLabel("MODULE CAPABILITIES")
        heading.setObjectName("panelTitle")
        layout.addWidget(heading)
        for item in items:
            line = QLabel("◆   " + item)
            line.setObjectName("bodyText")
            line.setWordWrap(True)
            layout.addWidget(line)
        page.body.addWidget(panel)
        state = QLabel("STATUS  •  FOUNDATION / INTEGRATION IN PROGRESS")
        state.setObjectName("statusPill")
        page.body.addWidget(state)
        return page

    def show_page(self, index):
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        self.breadcrumb.setText(f"{self.NAV_ITEMS[index][0].upper()}  /  CRYPTO SHERLOCK")
    
    def check_backend(self):
        self.connection.setText("●  CONNECTING")
        self.health_worker = HealthWorker(self.api_url)
        self.health_worker.finished.connect(self.on_health)
        self.health_worker.start()

    def on_health(self, ok: bool, message: str):
        self.connection.setText("●  BACKEND ONLINE" if ok else "●  BACKEND OFFLINE")
        self.connection.setProperty("online", ok)
        self.connection.style().unpolish(self.connection)
        self.connection.style().polish(self.connection)
        if hasattr(self, "backend_detail"):
            self.backend_detail.setText(f"{message}  ·  {self.api_url}")


STYLE = """
QWidget { color: #E7EDF2; font-family: 'Segoe UI'; font-size: 10pt; }
#root { background: #0A0F14; }
#sidebar { background: #0D141B; border-right: 1px solid #1C2933; }
#brand { color: #F2F7F8; font-size: 19pt; font-weight: 800; letter-spacing: 1px; }
#brandSub { color: #56D6B1; font-size: 11pt; font-weight: 700; letter-spacing: 3px; }
#eyebrow { color: #718392; font-size: 8pt; font-weight: 700; letter-spacing: 1.5px; }
.navButton { text-align: left; color: #9EACB7; background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 12px 10px; font-size: 9.5pt; }
.navButton:hover { background: #15222B; color: #EAF4F5; }
.navButton:checked { background: #142B2A; color: #67E0BC; border: 1px solid #24564B; font-weight: 700; }
#sidebarFoot { color: #61717D; font-size: 8pt; line-height: 1.6; }
#topbar { background: #0D141B; border-bottom: 1px solid #1C2933; }
#topLabel { color: #7F919F; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }
#connection { color: #E6B96B; font-size: 8pt; font-weight: 700; }
#connection[online="true"] { color: #59D6B0; }
#pageTitle { color: #F2F6F8; font-size: 25pt; font-weight: 700; }
#pageSubtitle { color: #8D9CA8; font-size: 10pt; }
#metricCard, #panel { background: #111B23; border: 1px solid #22313C; border-radius: 12px; }
#metricValue { color: #F0F5F6; font-size: 18pt; font-weight: 700; padding-top: 6px; padding-bottom: 4px; }
#metricValue[accent="mint"] { color: #62DDB8; }
#metricValue[accent="amber"] { color: #E6B96B; }
#metricValue[accent="blue"] { color: #79B8F4; }
#muted { color: #7D8D99; font-size: 9pt; }
#panelTitle { color: #C8D5DC; font-size: 9pt; font-weight: 700; letter-spacing: 1px; }
#bodyText { color: #AEBCC5; font-size: 10pt; padding: 5px 0; }
#statusPill { color: #E4BB72; background: #2B2418; border: 1px solid #59452A; border-radius: 7px; padding: 9px 12px; font-size: 8pt; font-weight: 700; }
"""

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CRYPTO SHERLOCK")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
