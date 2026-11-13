"""Asynchronous controls for local historical research jobs."""
from __future__ import annotations

import json
import time

import httpx
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)


class ResearchJobWorker(QThread):
    completed = Signal(dict)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, api_url: str, endpoint: str, params: dict):
        super().__init__()
        self.api_url = api_url.rstrip("/")
        self.endpoint = endpoint
        self.params = params

    def run(self):
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(
                    f"{self.api_url}{self.endpoint}", params=self.params
                )
                response.raise_for_status()
                job = response.json()
                job_id = job["job_id"]
                self.status.emit(f"Queued research job {job_id[:8]}…")
                deadline = time.monotonic() + 43200
                while time.monotonic() < deadline:
                    time.sleep(2.0)
                    response = client.get(
                        f"{self.api_url}/v1/research/jobs/{job_id}"
                    )
                    response.raise_for_status()
                    job = response.json()
                    progress = (job.get("result") or {}).get("progress")
                    self.status.emit(
                        str(progress) if progress else
                        f"Research job: {job.get('status', 'unknown')} · {job_id[:8]}"
                    )
                    if job.get("status") == "completed":
                        self.completed.emit(job)
                        return
                    if job.get("status") == "failed":
                        raise RuntimeError(job.get("error") or "Research job failed")
                raise TimeoutError("Research job exceeded 12-hour desktop wait limit")
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class ResearchPanel(QWidget):
    def __init__(self, api_url: str, endpoint: str, kind: str):
        super().__init__()
        self.api_url = api_url
        self.endpoint = endpoint
        self.kind = kind
        self.worker: ResearchJobWorker | None = None
        root = QVBoxLayout(self)
        root.setSpacing(12)
        form = QFormLayout()
        self.symbol = QComboBox()
        self.symbol.addItems(["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"])
        form.addRow("Market", self.symbol)
        self.interval = QComboBox()
        self.interval.addItems(["15m", "1h", "4h", "1d"])
        if kind == "mtf":
            self.interval.setEnabled(False)
            self.interval.setToolTip("MTF scanner always combines 15m, 4h and 1d")
        form.addRow("Interval", self.interval)
        self.mode = QComboBox()
        self.mode.addItem("Free Pattern Intelligence", "free")
        self.mode.addItem("Five-stage formation", "five_stage")
        form.addRow("Search mode", self.mode)
        self.window = QSpinBox()
        self.window.setRange(5, 500)
        self.window.setValue(40)
        form.addRow("Query window (candles)", self.window)
        self.top_k = QSpinBox()
        self.top_k.setRange(1, 100)
        self.top_k.setValue(10)
        form.addRow("Top historical analogs", self.top_k)
        root.addLayout(form)

        actions = QHBoxLayout()
        self.run_button = QPushButton("RUN RESEARCH")
        self.run_button.clicked.connect(self.run_research)
        actions.addWidget(self.run_button)
        actions.addStretch(1)
        root.addLayout(actions)
        self.status = QLabel("No research job started")
        self.status.setObjectName("muted")
        root.addWidget(self.status)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Verified research results will appear here.")
        self.output.setMinimumHeight(280)
        root.addWidget(self.output, 1)
        disclaimer = QLabel(
            "Historical analysis only. Results are not predictions, probabilities or trading signals. "
            "Source database is read-only."
        )
        disclaimer.setObjectName("muted")
        disclaimer.setWordWrap(True)
        root.addWidget(disclaimer)

    def run_research(self):
        if self.worker is not None and self.worker.isRunning():
            return
        params = {"symbol": self.symbol.currentText()}
        if self.kind == "pattern":
            params.update({
                "interval": self.interval.currentText(),
                "query_window": self.window.value(),
                "mode": self.mode.currentData(),
                "top_k": self.top_k.value(),
            })
        elif self.kind == "ensemble":
            params.update({
                "interval": self.interval.currentText(),
                "query_window": self.window.value(),
                "mode": self.mode.currentData(),
                "top_k": self.top_k.value(),
            })
        self.run_button.setEnabled(False)
        self.output.clear()
        self.status.setText("Submitting research job…")
        self.worker = ResearchJobWorker(self.api_url, self.endpoint, params)
        self.worker.status.connect(self.status.setText)
        self.worker.completed.connect(self.on_completed)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(lambda: self.run_button.setEnabled(True))
        self.worker.start()

    def on_completed(self, job: dict):
        self.status.setText(
            f"Completed · {job.get('kind')} · {job.get('updated_at')}"
        )
        self.output.setPlainText(json.dumps(
            job.get("result") or {}, ensure_ascii=False, indent=2
        ))

    def on_failed(self, message: str):
        self.status.setText("Research job failed")
        self.output.setPlainText(message)
