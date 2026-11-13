"""Read-only desktop view of the append-only research experiment ledger."""
from __future__ import annotations

import json

import httpx
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)


class LedgerWorker(QThread):
    completed = Signal(str, dict)
    failed = Signal(str)

    def __init__(self, api_url: str, action: str, run_id: str | None = None):
        super().__init__()
        self.api_url = api_url.rstrip("/")
        self.action = action
        self.run_id = run_id

    def run(self):
        try:
            with httpx.Client(timeout=30.0) as client:
                if self.action == "list":
                    response = client.get(
                        f"{self.api_url}/v1/research/experiments",
                        params={"limit": 100},
                    )
                elif self.action == "verify":
                    response = client.get(
                        f"{self.api_url}/v1/research/experiments/verify"
                    )
                elif self.action == "detail" and self.run_id:
                    response = client.get(
                        f"{self.api_url}/v1/research/experiments/{self.run_id}"
                    )
                else:
                    raise ValueError("Unknown experiment ledger action")
                response.raise_for_status()
                self.completed.emit(self.action, response.json())
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class ExperimentLedgerPanel(QWidget):
    def __init__(self, api_url: str):
        super().__init__()
        self.api_url = api_url
        self.worker: LedgerWorker | None = None
        root = QVBoxLayout(self)
        root.setSpacing(12)

        actions = QHBoxLayout()
        self.refresh_button = QPushButton("REFRESH HISTORY")
        self.refresh_button.clicked.connect(self.refresh)
        self.verify_button = QPushButton("VERIFY LEDGER INTEGRITY")
        self.verify_button.clicked.connect(self.verify)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.verify_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.status = QLabel("Research history has not been loaded yet.")
        self.status.setObjectName("muted")
        root.addWidget(self.status)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "RUN ID", "CREATED (UTC)", "MARKET", "MODE", "STATUS", "INPUT CANDLES"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        root.addWidget(self.table, 2)

        detail_title = QLabel("EXPERIMENT RECORD / INTEGRITY REPORT")
        detail_title.setObjectName("panelTitle")
        root.addWidget(detail_title)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText(
            "Select a run to inspect its parameters, result, hashes and event history."
        )
        self.details.setMinimumHeight(220)
        root.addWidget(self.details, 1)

        note = QLabel(
            "APPEND-ONLY HISTORY · New research creates new records. Existing runs cannot be edited or deleted."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)

    def _start(self, action: str, run_id: str | None = None):
        if self.worker is not None and self.worker.isRunning():
            return
        self.refresh_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.status.setText("Reading local research ledger…")
        self.worker = LedgerWorker(self.api_url, action, run_id)
        self.worker.completed.connect(self._completed)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _worker_finished(self):
        self.refresh_button.setEnabled(True)
        self.verify_button.setEnabled(True)

    def refresh(self):
        self._start("list")

    def verify(self):
        self._start("verify")

    def _selection_changed(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        run_id = selected[0].data(256)
        if run_id:
            self._start("detail", run_id)

    def _completed(self, action: str, payload: dict):
        if action == "list":
            rows = payload.get("experiments", [])
            self.table.setRowCount(len(rows))
            for row_index, record in enumerate(rows):
                values = [
                    str(record.get("run_id", ""))[:8],
                    str(record.get("created_at", "")),
                    f"{record.get('symbol', '')} · {record.get('interval', '')}",
                    str(record.get("mode", "")),
                    str(record.get("status", "")).upper(),
                    f"{record.get('input_candle_count', 0):,}",
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column == 0:
                        item.setData(256, record.get("run_id"))
                    self.table.setItem(row_index, column, item)
            self.status.setText(
                f"Loaded {len(rows)} experiment(s) · total shown up to {payload.get('limit', 100)}"
            )
            self.details.clear()
        elif action == "verify":
            ok = bool(payload.get("ok"))
            self.status.setText(
                "LEDGER INTEGRITY: PASS" if ok else "LEDGER INTEGRITY: ISSUES FOUND"
            )
            self.details.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))
        elif action == "detail":
            self.status.setText(
                f"Loaded immutable experiment {payload.get('run', {}).get('run_id', '')}"
            )
            self.details.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))

    def _failed(self, message: str):
        self.status.setText("Ledger request failed · " + message)
        self.details.setPlainText(message)
