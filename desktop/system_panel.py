"""System health and local read-only data audit controls."""
from __future__ import annotations

import json
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget
from desktop.research_panel import ResearchJobWorker


class SystemPanel(QWidget):
    def __init__(self, api_url: str):
        super().__init__()
        self.api_url = api_url
        self.worker: ResearchJobWorker | None = None
        root = QVBoxLayout(self)
        actions = QHBoxLayout()
        self.audit = QPushButton("AUDIT SOURCE DATABASE")
        self.audit.clicked.connect(self.run_audit)
        self.pipeline = QPushButton("RUN FEATURE PIPELINE")
        self.pipeline.clicked.connect(self.run_pipeline)
        actions.addWidget(self.audit)
        actions.addWidget(self.pipeline)
        actions.addStretch(1)
        root.addLayout(actions)
        self.status = QLabel("Backend health is shown in the top bar")
        self.status.setObjectName("muted")
        root.addWidget(self.status)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        root.addWidget(self.output, 1)
        note = QLabel(
            "Audit opens the configured source SQLite database read-only. "
            "The feature pipeline writes derived outputs only to the separate analytics database."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)

    def _run(self, endpoint: str, params: dict):
        if self.worker is not None and self.worker.isRunning():
            return
        self.audit.setEnabled(False)
        self.pipeline.setEnabled(False)
        self.output.clear()
        self.worker = ResearchJobWorker(self.api_url, endpoint, params)
        self.worker.status.connect(self.status.setText)
        self.worker.completed.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def run_audit(self):
        self._run("/v1/research/audit", {})

    def run_pipeline(self):
        self._run("/v1/research/pipeline", {"symbol": "BTCUSDT", "interval": "15m", "window": 20})

    def _done(self, job: dict):
        self.status.setText(f"Completed · {job.get('kind')} · {job.get('updated_at')}")
        self.output.setPlainText(json.dumps(job.get("result") or {}, ensure_ascii=False, indent=2))

    def _failed(self, message: str):
        self.status.setText("System task failed")
        self.output.setPlainText(message)

    def _finished(self):
        self.audit.setEnabled(True)
        self.pipeline.setEnabled(True)
