"""Local backend path configuration dialog."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout,
)


def default_analytics_path() -> Path:
    base = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    ))
    return base / "data" / "sherlock_analytics.db"


class ServerSettingsDialog(QDialog):
    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("CRYPTO SHERLOCK · Server Settings")
        self.setMinimumWidth(720)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.source = QLineEdit(settings.value("source_db", ""))
        self.analytics = QLineEdit(
            settings.value("analytics_db", str(default_analytics_path()))
        )
        source_row = QHBoxLayout()
        source_row.addWidget(self.source, 1)
        source_browse = QPushButton("Browse…")
        source_browse.clicked.connect(self.browse_source)
        source_row.addWidget(source_browse)
        analytics_row = QHBoxLayout()
        analytics_row.addWidget(self.analytics, 1)
        analytics_browse = QPushButton("Browse…")
        analytics_browse.clicked.connect(self.browse_analytics)
        analytics_row.addWidget(analytics_browse)
        form.addRow("Source market database (read-only)", source_row)
        form.addRow("Separate analytics database", analytics_row)
        root.addLayout(form)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("CANCEL")
        cancel.clicked.connect(self.reject)
        save = QPushButton("SAVE & START SERVER")
        save.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(save)
        root.addLayout(actions)

    def browse_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select source market database", self.source.text(),
            "SQLite databases (*.db *.sqlite *.sqlite3);;All files (*.*)",
        )
        if path:
            self.source.setText(path)

    def browse_analytics(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Select analytics database", self.analytics.text(),
            "SQLite databases (*.db *.sqlite *.sqlite3)",
        )
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
