"""Manual, explicitly user-triggered paper-only portfolio controls."""
from __future__ import annotations

import json
import httpx
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)


class PaperWorker(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, api_url: str, operation: str, params: dict | None = None):
        super().__init__()
        self.api_url = api_url.rstrip("/")
        self.operation = operation
        self.params = params or {}

    def run(self):
        try:
            if self.isInterruptionRequested():
                return
            with httpx.Client(timeout=20.0) as client:
                if self.operation == "snapshot":
                    response = client.get(f"{self.api_url}/v1/paper/portfolio")
                else:
                    response = client.post(
                        f"{self.api_url}/v1/paper/orders", params=self.params
                    )
                response.raise_for_status()
                self.done.emit(response.json())
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class PaperPanel(QWidget):
    def __init__(self, api_url: str):
        super().__init__()
        self.api_url = api_url
        self.worker: PaperWorker | None = None
        root = QVBoxLayout(self)
        root.setSpacing(12)
        form = QFormLayout()
        self.symbol = QComboBox()
        self.symbol.addItems(["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"])
        self.side = QComboBox()
        self.side.addItems(["BUY", "SELL"])
        self.quantity = QDoubleSpinBox()
        self.quantity.setDecimals(8)
        self.quantity.setRange(0.00000001, 100000000)
        self.quantity.setValue(0.001)
        form.addRow("Asset", self.symbol)
        form.addRow("Virtual action", self.side)
        form.addRow("Quantity", self.quantity)
        root.addLayout(form)
        actions = QHBoxLayout()
        self.submit = QPushButton("PLACE VIRTUAL ORDER")
        self.submit.clicked.connect(self.place_order)
        self.refresh = QPushButton("REFRESH PORTFOLIO")
        self.refresh.clicked.connect(self.load_snapshot)
        actions.addWidget(self.submit)
        actions.addWidget(self.refresh)
        root.addLayout(actions)
        self.status = QLabel("PAPER ONLY · no exchange account access")
        self.status.setObjectName("muted")
        root.addWidget(self.status)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        root.addWidget(self.output, 1)
        disclaimer = QLabel(
            "Orders are manually submitted to the local virtual ledger. "
            "BUY/SELL uses public market price with configured simulated fees and slippage. "
            "Spot only: no leverage, no shorting, no live exchange execution."
        )
        disclaimer.setObjectName("muted")
        disclaimer.setWordWrap(True)
        root.addWidget(disclaimer)
        self.load_snapshot()

    def _start(self, operation: str, params: dict | None = None):
        if self.worker is not None and self.worker.isRunning():
            return
        self.submit.setEnabled(False)
        self.refresh.setEnabled(False)
        self.status.setText("Contacting local paper ledger…")
        self.worker = PaperWorker(self.api_url, operation, params)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def load_snapshot(self):
        self._start("snapshot")

    def place_order(self):
        symbol = self.symbol.currentText()
        side = self.side.currentText()
        quantity = self.quantity.value()
        answer = QMessageBox.question(
            self, "Confirm virtual order",
            f"Confirm PAPER ONLY {side} of {quantity:.8f} {symbol}?\n\n"
            "This changes only the local virtual portfolio. No exchange order is sent.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._start("order", {
            "symbol": symbol, "side": side, "quantity": quantity,
        })

    def _on_done(self, result: dict):
        self.status.setText("Paper ledger updated" if "fill_price" in result else "Paper portfolio loaded")
        self.output.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))

    def _on_failed(self, message: str):
        self.status.setText("Paper operation failed")
        self.output.setPlainText(message)

    def _on_finished(self):
        self.submit.setEnabled(True)
        self.refresh.setEnabled(True)
