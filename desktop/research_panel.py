"""Asynchronous controls for local historical research jobs."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import httpx
import pyqtgraph as pg
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
        self.query_start = QLineEdit()
        self.query_start.setPlaceholderText("Optional · YYYY-MM-DD HH:MM UTC")
        self.query_start.setToolTip(
            "Leave empty to analyze the latest closed candles. "
            "Enter an exact candle open time in UTC to compare a historical sample."
        )
        form.addRow("Historical sample start (UTC)", self.query_start)
        self.top_k = QSpinBox()
        self.top_k.setRange(1, 100)
        self.top_k.setValue(10)
        form.addRow("Top historical analogs", self.top_k)
        if kind == "mtf":
            self.mode.setEnabled(False)
            self.window.setEnabled(False)
            self.query_start.setEnabled(False)
            self.top_k.setEnabled(False)
        elif kind == "ensemble":
            self.query_start.setEnabled(False)
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
        self.plot = None
        if kind == "pattern":
            self.plot = pg.PlotWidget()
            self.plot.setBackground("#111B23")
            self.plot.showGrid(x=True, y=True, alpha=0.15)
            self.plot.setLabel("left", "Normalized close (start = 100)")
            self.plot.setLabel("bottom", "Candle offset")
            self.plot.getAxis("left").setTextPen("#82939F")
            self.plot.getAxis("bottom").setTextPen("#82939F")
            self.plot.setMinimumHeight(260)
            root.addWidget(self.plot, 1)
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
            selected_time = self.query_start.text().strip()
            if selected_time:
                try:
                    parsed = datetime.fromisoformat(selected_time.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    params["query_start_time"] = int(parsed.astimezone(timezone.utc).timestamp() * 1000)
                except ValueError:
                    self.status.setText("Invalid sample time · use YYYY-MM-DD HH:MM UTC")
                    return
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
        result = job.get("result") or {}
        summary = []
        if "history_candles" in result:
            query_label = (
                "Historical sample" if result.get("query_selection") == "historical_open_time"
                else "Latest closed sample"
            )
            summary.extend([
                f"Query: {query_label} · {result.get('query_start_time')}",
                f"History loaded: {result.get('history_candles', 0):,} candles",
                f"Historical gaps: {result.get('historical_gaps', 0)} · "
                f"continuous segments: {result.get('contiguous_segments', 1)}",
                f"Candidates examined: {result.get('candidates_examined', '—'):,}",
            ])
        if result.get("stage_weights"):
            summary.append("FIVE-STAGE WEIGHTS · 20% EACH")
            summary.append(
                result.get("five_stage_method") or
                "Stage scores compare corresponding segments; they are not probabilities."
            )
            summary.extend(
                f"  {name.replace('_', ' ').title()}: {weight:.0%}"
                for name, weight in result["stage_weights"].items()
            )
        assumptions = result.get("execution_assumptions")
        if assumptions:
            summary.extend([
                "\\nFORWARD-PATH ASSUMPTIONS",
                f"Entry: {assumptions.get('entry')} · Exit: {assumptions.get('exit')}",
                f"Fees: {assumptions.get('fee_bps_per_side')} bps/side · "
                f"Slippage: {assumptions.get('slippage_bps_per_side')} bps/side · "
                "charged on entry and exit",
                assumptions.get("short_side", ""),
            ])
        analogs = result.get("analogs", [])
        if analogs:
            summary.append(f"\nTOP HISTORICAL ANALOGS · {len(analogs)}")
            for index, item in enumerate(analogs, start=1):
                analog = item.get("analog", {})
                summary.append(
                    f"\n#{index} · similarity {analog.get('similarity', 0):.4f} · "
                    f"{analog.get('start_time')} → {analog.get('end_time')}"
                )
                for name, score in analog.get("stage_similarities", {}).items():
                    summary.append(f"  {name.replace('_', ' ').title()}: {score:.4f}")
                outcomes = (item.get("forward_path") or {}).get("outcomes", [])
                for outcome in outcomes:
                    if outcome:
                        summary.append(
                            f"  +{outcome['horizon']} candles · "
                            f"LONG net {outcome['long_net_return']:+.2%} · "
                            f"SHORT net {outcome['short_net_return']:+.2%}"
                        )
        if "setups" in result:
            summary.append(f"\nMULTI-TIMEFRAME SETUPS · {len(result['setups'])}")
        if "evidence_report" in result:
            report = result["evidence_report"]
            summary.append(
                f"\nENSEMBLE EVIDENCE · {report.get('evidence_count', 0)} observations · "
                f"{report.get('module_count', 0)} supporting modules"
            )
            summary.append(
                "Engines: " + ", ".join(result.get("engines_available", []))
            )
            if result.get("engines_missing"):
                summary.append("Unavailable: " + ", ".join(result["engines_missing"]))
        summary.extend(["\nFULL RESEARCH DATA", json.dumps(
            result, ensure_ascii=False, indent=2
        )])
        self.output.setPlainText("\n".join(summary))
        if self.plot is not None:
            self.plot.clear()
            self.plot.addLegend()
            query = (result.get("query_chart") or {}).get("normalized_close", [])
            if query:
                query_label = (
                    "Historical sample" if result.get("query_selection") == "historical_open_time"
                    else "Latest sample"
                )
                self.plot.plot(
                    list(range(len(query))), query,
                    pen=pg.mkPen("#56D6B1", width=2.6), name=query_label,
                )
            palette = ["#8CA4B5", "#A7B8C4", "#6F8798", "#C0CDD5", "#718B9C"]
            for index, item in enumerate(result.get("analogs", [])[:5]):
                values = (item.get("chart") or {}).get("normalized_close", [])
                if not values:
                    continue
                similarity = item.get("analog", {}).get("similarity", 0.0)
                self.plot.plot(
                    list(range(len(values))), values,
                    pen=pg.mkPen(palette[index % len(palette)], width=1.2),
                    name=f"Analog {index + 1} · {similarity:.3f}",
                )
            self.plot.setTitle("Selected pattern sample vs top historical analogs")

    def on_failed(self, message: str):
        self.status.setText("Research job failed")
        self.output.setPlainText(message)
