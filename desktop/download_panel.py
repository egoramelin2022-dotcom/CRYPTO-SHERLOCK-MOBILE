"""Explicitly confirmed Binance historical archive staging controls."""
from __future__ import annotations

import json
from PySide6.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)
from desktop.research_panel import ResearchJobWorker


class DownloadPanel(QWidget):
    def __init__(self, api_url: str):
        super().__init__()
        self.api_url = api_url
        self.worker: ResearchJobWorker | None = None
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.start = QLineEdit("2017-08")
        self.end = QLineEdit("2026-10")
        form.addRow("First month (YYYY-MM)", self.start)
        form.addRow("Last month (YYYY-MM)", self.end)
        root.addLayout(form)
        actions = QHBoxLayout()
        self.run_button = QPushButton("DOWNLOAD TO STAGING")
        self.run_button.clicked.connect(self.start_download)
        actions.addWidget(self.run_button)
        actions.addStretch(1)
        root.addLayout(actions)
        self.status = QLabel("No archive download started")
        self.status.setObjectName("muted")
        root.addWidget(self.status)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Archive verification and import results will appear here.")
        root.addWidget(self.output, 1)
        note = QLabel(
            "Downloads official Binance Spot monthly ZIP archives and verifies SHA256. "
            "Data goes to a separate staging database; it never overwrites the source market database. "
            "The archive download can be large and may take a long time."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)

    def start_download(self):
        if self.worker is not None and self.worker.isRunning():
            return
        start, end = self.start.text().strip(), self.end.text().strip()
        import re
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", start) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", end):
            QMessageBox.warning(self, "Invalid date", "Use YYYY-MM, for example 2017-08.")
            return
        if tuple(map(int, start.split("-"))) > tuple(map(int, end.split("-"))):
            QMessageBox.warning(self, "Invalid range", "Start month must not be after end month.")
            return
        answer = QMessageBox.question(
            self, "Confirm archive download",
            f"Download Binance Spot BTCUSDT 15m / 4h / 1d archives from {start} through {end}?\n\n"
            "Files and candles will be written only to the staging area. This may consume several gigabytes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.run_button.setEnabled(False)
        self.output.clear()
        self.status.setText("Submitting archive download…")
        self.worker = ResearchJobWorker(
            self.api_url, "/v1/data/archive-download",
            {"start": start, "end": end},
        )
        self.worker.status.connect(self.status.setText)
        self.worker.completed.connect(self.on_completed)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(lambda: self.run_button.setEnabled(True))
        self.worker.start()

    def on_completed(self, job: dict):
        self.status.setText("Archive download completed")
        self.output.setPlainText(json.dumps(job.get("result") or {}, ensure_ascii=False, indent=2))

    def on_failed(self, message: str):
        self.status.setText("Archive download failed")
        self.output.setPlainText(message)
