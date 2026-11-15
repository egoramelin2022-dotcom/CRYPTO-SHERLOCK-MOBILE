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
        self.setWindowTitle("CRYPTO SHERLOCK · Настройки сервера")
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
        form.addRow("Исходная база рынка (только чтение)", source_row)
        form.addRow("Отдельная база аналитики", analytics_row)
        root.addLayout(form)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("ОТМЕНА")
        cancel.clicked.connect(self.reject)
        save = QPushButton("СОХРАНИТЬ И ЗАПУСТИТЬ СЕРВЕР")
        save.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(save)
        root.addLayout(actions)

    def browse_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите исходную базу рыночных данных", self.source.text(),
            "Базы SQLite (*.db *.sqlite *.sqlite3);;Все файлы (*.*)",
        )
        if path:
            self.source.setText(path)

    def browse_analytics(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Выберите базу аналитики", self.analytics.text(),
            "Базы SQLite (*.db *.sqlite *.sqlite3)",
        )
        if path:
            self.analytics.setText(path)

    def accept(self):
        source = Path(self.source.text().strip()).expanduser()
        analytics = Path(self.analytics.text().strip()).expanduser()
        if not source.is_file():
            QMessageBox.warning(self, "Исходная база не найдена", "Выберите существующую базу рыночных данных.")
            return
        if source.resolve() == analytics.resolve():
            QMessageBox.warning(self, "Небезопасная настройка баз данных", "База аналитики должна отличаться от исходной базы.")
            return
        try:
            analytics.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Не удалось создать папку базы аналитики", str(exc))
            return
        self.settings.setValue("source_db", str(source.resolve()))
        self.settings.setValue("analytics_db", str(analytics.resolve()))
        super().accept()
