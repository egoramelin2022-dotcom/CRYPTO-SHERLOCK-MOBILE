"""First-run local database configuration for the standalone desktop app."""
from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QMessageBox, QPushButton, QVBoxLayout


def default_analytics_path() -> Path:
    base = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    return base / "data" / "sherlock_analytics.db"


class ServerSettingsDialog(QDialog):
    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("CRYPTO SHERLOCK · Local Data Setup")
        self.setMinimumWidth(760)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.source = QLineEdit(settings.value("source_db", ""))
        self.analytics = QLineEdit(settings.value("analytics_db", str(default_analytics_path())))
        source_row = QHBoxLayout()
        source_row.addWidget(self.source, 1)
        browse_source = QPushButton("Browse…")
        browse_source.clicked.connect(self.browse_source)
        source_row.addWidget(browse_source)
        analytics_row = QHBoxLayout()
        analytics_row.addWidget(self.analytics, 1)
        browse_analytics = QPushButton("Browse…")
        browse_analytics.clicked.connect(self.browse_analytics)
        analytics_row.addWidget(browse_analytics)
        form.addRow("Source market database (read-only)", source_row)
        form.addRow("Separate analytics database", analytics_row)
        root.addLayout(form)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("EXIT")
        cancel.clicked.connect(self.reject)
        save = QPushButton("SAVE & START")
        save.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(save)
        root.addLayout(actions)

    def browse_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select source market database", self.source.text(), "SQLite databases (*.db *.sqlite *.sqlite3);;All files (*.*)")
        if path:
            self.source.setText(path)

    def browse_analytics(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select analytics database", self.analytics.text(), "SQLite databases (*.db *.sqlite *.sqlite3)")
        if path:
            self.analytics.setText(path)

    def accept(self):
        source = Path(self.source.text().strip()).expanduser()
        analytics = Path(self.analytics.text().strip()).expanduser()
        if not source.is_file():
            QMessageBox.warning(self, "Source database not found", "Select an existing source market database.")
            return
        if source.resolve() == analytics.resolve():
            QMessageBox.warning(self, "Unsafe database configuration", "Analytics database must be separate from the source database.")
            return
        try:
            analytics.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Cannot create analytics folder", str(exc))
            return
        self.settings.setValue("source_db", str(source.resolve()))
        self.settings.setValue("analytics_db", str(analytics.resolve()))
        super().accept()


def configure_local_databases() -> tuple[Path, Path] | None:
    settings = QSettings("CRYPTO-SHERLOCK", "Desktop")
    source_value = settings.value("source_db", "")
    analytics = Path(settings.value("analytics_db", str(default_analytics_path()))).expanduser()
    source = Path(source_value).expanduser() if source_value else None
    if source is not None and source.is_file() and source.resolve() != analytics.resolve():
        analytics.parent.mkdir(parents=True, exist_ok=True)
        return source.resolve(), analytics.resolve()
    candidates = [Path.cwd() / "data" / "sherlock_market.db", Path(__file__).resolve().parents[1] / "data" / "sherlock_market.db"]
    existing = next((item.resolve() for item in candidates if item.is_file()), None)
    if existing is not None and not source_value:
        settings.setValue("source_db", str(existing))
        settings.setValue("analytics_db", str(analytics.resolve()))
        analytics.parent.mkdir(parents=True, exist_ok=True)
        return existing, analytics.resolve()
    dialog = ServerSettingsDialog(settings)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return Path(settings.value("source_db")).resolve(), Path(settings.value("analytics_db")).resolve()
