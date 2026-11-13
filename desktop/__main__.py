"""CRYPTO SHERLOCK Windows desktop research terminal."""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone

import httpx
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QProcess, QProcessEnvironment, QSettings
from PySide6.QtGui import QFont
from desktop.market_panel import MarketPanel
from desktop.research_panel import ResearchPanel
from desktop.paper_panel import PaperPanel
from desktop.download_panel import DownloadPanel
from desktop.system_panel import SystemPanel
from desktop.server_settings import ServerSettingsDialog, default_analytics_path

from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QMessageBox,
    QVBoxLayout, QWidget,
)

API_DEFAULT = "http://127.0.0.1:8000"


class HealthWorker(QThread):
    result_ready = Signal(bool, str)

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url.rstrip("/")

    def run(self):
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=3.0)
            response.raise_for_status()
            self.result_ready.emit(True, "Backend connected")
        except Exception as exc:
            self.result_ready.emit(False, f"Backend unavailable: {type(exc).__name__}")


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
        self.backend_online = False
        self.settings = QSettings("CRYPTO_SHERLOCK", "Desktop")
        self.server_process = QProcess(self)
        self.health_timer = QTimer(self)
        self.health_timer.timeout.connect(self.check_backend)
        self.health_timer.start(2000)
        self.server_process.errorOccurred.connect(self.on_server_error)
        self.server_process.finished.connect(self.on_server_finished)
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
        version = QLabel("DESKTOP  •  v0.3.0\nPAPER RESEARCH ONLY")
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
        self.server_settings_button = QPushButton('SERVER SETTINGS')
        self.server_settings_button.setObjectName('settingsButton')
        self.server_settings_button.clicked.connect(self.open_server_settings)
        top.addWidget(self.server_settings_button)
        content.addWidget(topbar)

        self.stack = QStackedWidget()
        self.pages = [
            self.make_overview(),
            self.make_data_page(),
            self.make_research_page("Pattern Intelligence", "Historical analog search with a free mode and the preserved equal-weight five-stage formation.", "/v1/research/pattern", "pattern"),
            self.make_research_page("Multi-Timeframe Scanner", "Aligned 15m lower-wick, 4h support sweep/reclaim and closed 1d bearish-context scan.", "/v1/research/multitimeframe", "mtf"),
            self.make_research_page("Ensemble Engine", "Evidence aggregation with explicit engine availability. No uncalibrated probabilities or signal averaging.", "/v1/research/ensemble", "ensemble"),
            self.make_research_page("Backtesting Lab", "Historical forward-outcome audit for analogs. Full strategy walk-forward backtesting remains a separate validation stage.", "/v1/research/pattern", "pattern"),
            self.make_paper_page(),
            self.make_system_page(),
        ]
        for page in self.pages:
            self.stack.addWidget(page)
        content.addWidget(self.stack, 1)
        shell.addWidget(sidebar)
        main = QWidget()
        main.setLayout(content)
        shell.addWidget(main, 1)
        self.show_page(0)
        source = Path(self.settings.value("source_db", "")).expanduser()
        if source.is_file():
            self.start_local_backend()
        else:
            QTimer.singleShot(0, self.open_server_settings)
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
        page = Page("Market Data & History", "Live public Binance Spot market feed and verified historical archive staging.")
        market_panel = QFrame()
        market_panel.setObjectName("panel")
        market_layout = QVBoxLayout(market_panel)
        market_layout.setContentsMargins(18, 16, 18, 16)
        self.market_panel = MarketPanel(self.api_url)
        market_layout.addWidget(self.market_panel)
        page.body.addWidget(market_panel, 2)

        archive_panel = QFrame()
        archive_panel.setObjectName("panel")
        archive_layout = QVBoxLayout(archive_panel)
        archive_layout.setContentsMargins(18, 16, 18, 16)
        archive_layout.addWidget(DownloadPanel(self.api_url))
        page.body.addWidget(archive_panel, 1)
        return page

    def make_system_page(self):
        page = Page("System Monitor", "Backend connection, read-only source audit and derived feature pipeline.")
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.addWidget(SystemPanel(self.api_url))
        page.body.addWidget(panel, 1)
        return page

    def make_paper_page(self):
        page = Page("Paper Trading", "Persistent virtual spot portfolio. All actions are manually confirmed and simulated locally.")
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        self.paper_panel = PaperPanel(self.api_url)
        layout.addWidget(self.paper_panel)
        page.body.addWidget(panel, 1)
        return page

    def make_research_page(self, title, subtitle, endpoint, kind):
        page = Page(title, subtitle)
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        controls = ResearchPanel(self.api_url, endpoint, kind)
        layout.addWidget(controls)
        page.body.addWidget(panel, 1)
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
        if hasattr(self, "market_panel"):
            if index == 1:
                self.market_panel.auto_refresh.start(30_000)
                if self.backend_online:
                    self.market_panel.refresh()
            else:
                self.market_panel.auto_refresh.stop()
    
    def open_server_settings(self):
        dialog = ServerSettingsDialog(self.settings, self)
        if dialog.exec() == ServerSettingsDialog.DialogCode.Accepted:
            if self.server_process.state() != QProcess.ProcessState.NotRunning:
                self.server_process.terminate()
                if not self.server_process.waitForFinished(3000):
                    self.server_process.kill()
                    self.server_process.waitForFinished(2000)
            self.start_local_backend()

    def start_local_backend(self):
        if self.server_process.state() != QProcess.ProcessState.NotRunning:
            self.connection.setText("●  BACKEND STARTING")
            return
        source = Path(self.settings.value("source_db", "")).expanduser()
        analytics = Path(self.settings.value("analytics_db", str(default_analytics_path()))).expanduser()
        if not source.is_file():
            QMessageBox.information(
                self, "Configure source database",
                "Select the existing sherlock_market.db in Server Settings before starting the local backend."
            )
            self.open_server_settings()
            return
        if source.resolve() == analytics.resolve():
            QMessageBox.warning(self, "Unsafe database paths", "Source and analytics databases must be separate.")
            return
        analytics.parent.mkdir(parents=True, exist_ok=True)
        data_dir = analytics.parent
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("SHERLOCK_SOURCE_DB", str(source.resolve()))
        environment.insert("SHERLOCK_ANALYTICS_DB", str(analytics.resolve()))
        environment.insert("SHERLOCK_ARCHIVE_RAW_DIR", str(data_dir / "binance_public_raw"))
        environment.insert("SHERLOCK_ARCHIVE_STAGING_DB", str(data_dir / "binance_archive_staging.db"))
        environment.insert("SHERLOCK_SERVER_LOG", str(data_dir / "server.log"))
        self.server_process.setProcessEnvironment(environment)
        if getattr(sys, "frozen", False):
            app_dir = Path(sys.executable).resolve().parent
            server_exe = app_dir / "Server" / "CRYPTO-SHERLOCK-Server.exe"
            if not server_exe.is_file():
                QMessageBox.warning(
                    self, "Local server package missing",
                    "The bundled CRYPTO-SHERLOCK-Server.exe was not found. Rebuild the complete Windows package."
                )
                return
            self.server_process.setWorkingDirectory(str(server_exe.parent))
            self.server_process.setProgram(str(server_exe))
            self.server_process.setArguments([])
        else:
            backend_dir = Path(__file__).resolve().parents[1] / "backend"
            server_script = backend_dir / "desktop_server.py"
            if not server_script.is_file():
                QMessageBox.warning(self, "Backend script missing", str(server_script))
                return
            self.server_process.setWorkingDirectory(str(backend_dir))
            self.server_process.setProgram(sys.executable)
            self.server_process.setArguments([str(server_script)])
        self.connection.setText("●  STARTING LOCAL SERVER")
        self.server_process.start()
        QTimer.singleShot(2500, self.check_backend)

    def on_server_error(self, error):
        self.connection.setText("●  SERVER START FAILED")
        QMessageBox.warning(self, "Local server error", f"Could not start the bundled backend: {error}")

    def on_server_finished(self, exit_code, exit_status):
        if exit_code != 0 and self.isVisible():
            self.connection.setText("●  SERVER STOPPED")
            self.backend_detail.setText(
                f"Local backend process exited with code {exit_code}. Check port 8000 and server log: "
                f"{Path(self.settings.value('analytics_db')).expanduser().parent / 'server.log'}"
            )

    def closeEvent(self, event):
        if self.server_process.state() != QProcess.ProcessState.NotRunning:
            self.server_process.terminate()
            if not self.server_process.waitForFinished(3000):
                self.server_process.kill()
                self.server_process.waitForFinished(2000)
        super().closeEvent(event)

    def check_backend(self):
        if self.health_worker is not None and self.health_worker.isRunning():
            return
        self.connection.setText("●  CONNECTING")
        self.health_worker = HealthWorker(self.api_url)
        self.health_worker.result_ready.connect(self.on_health)
        self.health_worker.start()

    def on_health(self, ok: bool, message: str):
        just_connected = ok and not self.backend_online
        self.backend_online = ok
        self.connection.setText("●  BACKEND ONLINE" if ok else "●  BACKEND OFFLINE")
        self.connection.setProperty("online", ok)
        self.connection.style().unpolish(self.connection)
        self.connection.style().polish(self.connection)
        if hasattr(self, "backend_detail"):
            self.backend_detail.setText(f"{message}  ·  {self.api_url}")
        if just_connected:
            if hasattr(self, "market_panel"):
                self.market_panel.refresh()
            if hasattr(self, "paper_panel"):
                self.paper_panel.load_snapshot()


STYLE = """
QWidget { color: #E7EDF2; font-family: 'Segoe UI'; font-size: 10pt; }
#root { background: #0A0F14; }
#sidebar { background: #0D141B; border-right: 1px solid #1C2933; }
#brand { color: #F2F7F8; font-size: 19pt; font-weight: 800; letter-spacing: 1px; }
#brandSub { color: #56D6B1; font-size: 11pt; font-weight: 700; letter-spacing: 3px; }
#eyebrow { color: #718392; font-size: 8pt; font-weight: 700; letter-spacing: 1.5px; }
#navButton { text-align: left; color: #9EACB7; background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 12px 10px; font-size: 9.5pt; }
#navButton:hover { background: #15222B; color: #EAF4F5; }
#navButton:checked { background: #142B2A; color: #67E0BC; border: 1px solid #24564B; font-weight: 700; }
#sidebarFoot { color: #61717D; font-size: 8pt; line-height: 1.6; }
#topbar { background: #0D141B; border-bottom: 1px solid #1C2933; }
#settingsButton { padding: 7px 10px; font-size: 8pt; }
#topLabel { color: #7F919F; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }
#connection { color: #E6B96B; font-size: 8pt; font-weight: 700; }
#connection[online="true"] { color: #59D6B0; }
#pageTitle { color: #F2F6F8; font-size: 25pt; font-weight: 700; }
#pageSubtitle { color: #8D9CA8; font-size: 10pt; }
#metricCard, #panel { background: #111B23; border: 1px solid #22313C; border-radius: 12px; }
#marketPrice { color: #F0F5F6; font-size: 24pt; font-weight: 700; padding: 8px 0; }
QTextEdit { background: #0C141B; color: #D7E1E6; border: 1px solid #263641; border-radius: 8px; padding: 10px; font-family: Consolas; font-size: 9pt; }
QComboBox, QSpinBox, QLineEdit { background: #0C141B; color: #D7E1E6; border: 1px solid #263641; border-radius: 6px; padding: 7px; }
QPushButton { background: #17352F; color: #70E2BF; border: 1px solid #2B6656; border-radius: 7px; padding: 9px 14px; font-weight: 700; }
QPushButton:disabled { color: #718392; background: #17212A; border-color: #293742; }
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
    app.setOrganizationName("CRYPTO_SHERLOCK")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
