"""Asynchronous controls for local historical research jobs."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import httpx
import pyqtgraph as pg
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
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
        self.adaptive = QCheckBox("Automatically compare multiple pattern lengths")
        self.adaptive.setToolTip("Keeps the sample end fixed; each length is ranked independently.")
        form.addRow("Adaptive window search", self.adaptive)
        self.adaptive_min = QSpinBox()
        self.adaptive_min.setRange(5, 500)
        self.adaptive_min.setValue(20)
        form.addRow("Adaptive minimum length", self.adaptive_min)
        self.adaptive_max = QSpinBox()
        self.adaptive_max.setRange(5, 500)
        self.adaptive_max.setValue(100)
        form.addRow("Adaptive maximum length", self.adaptive_max)
        self.adaptive_step = QSpinBox()
        self.adaptive_step.setRange(1, 500)
        self.adaptive_step.setValue(20)
        form.addRow("Adaptive length step", self.adaptive_step)
        self.wf_folds = QSpinBox()
        self.wf_folds.setRange(2, 100)
        self.wf_folds.setValue(30)
        self.wf_training = QSpinBox()
        self.wf_training.setRange(100, 399000)
        self.wf_training.setMinimum(self.window.value() + 65)
        self.wf_training.setValue(max(500, self.window.value() + 65))
        self.window.valueChanged.connect(
            lambda value: self.wf_training.setMinimum(value + 65)
        )
        self.wf_budget = QSpinBox()
        self.wf_budget.setRange(100, 5000)
        self.wf_budget.setValue(2000)
        if kind != "pattern":
            for control in (self.adaptive, self.adaptive_min, self.adaptive_max, self.adaptive_step):
                control.hide()
                label = form.labelForField(control)
                if label is not None:
                    label.hide()
        if kind == "walk_forward":
            form.addRow("Out-of-sample folds", self.wf_folds)
            form.addRow("Minimum training history (candles)", self.wf_training)
            form.addRow("Candidate budget per fold", self.wf_budget)
            self.query_start.setEnabled(False)
            self.adaptive.setEnabled(False)
            self.adaptive_min.setEnabled(False)
            self.adaptive_max.setEnabled(False)
            self.adaptive_step.setEnabled(False)
        if kind == "mtf":
            self.mode.setEnabled(False)
            self.window.setEnabled(False)
            self.query_start.setEnabled(False)
            self.top_k.setEnabled(False)
            self.adaptive.setEnabled(False)
            self.adaptive_min.setEnabled(False)
            self.adaptive_max.setEnabled(False)
            self.adaptive_step.setEnabled(False)
        elif kind == "ensemble":
            self.query_start.setEnabled(False)
            self.adaptive.setEnabled(False)
            self.adaptive_min.setEnabled(False)
            self.adaptive_max.setEnabled(False)
            self.adaptive_step.setEnabled(False)
        root.addLayout(form)

        actions = QHBoxLayout()
        self.run_button = QPushButton("RUN RESEARCH")
        self.run_button.clicked.connect(self.run_research)
        actions.addWidget(self.run_button)
        self.robustness_button = None
        if kind == "walk_forward":
            self.robustness_button = QPushButton("RUN ROBUSTNESS AUDIT")
            self.robustness_button.setToolTip(
                "Run up to five independent parameter configurations. "
                "Capped at 30 folds and 2,000 candidate windows per fold; no winner is selected."
            )
            self.robustness_button.clicked.connect(lambda: self.run_research("/v1/research/robustness"))
            actions.addWidget(self.robustness_button)
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

    def run_research(self, endpoint_override: str | None = None):
        if self.worker is not None and self.worker.isRunning():
            return
        params = {"symbol": self.symbol.currentText()}
        if self.kind == "pattern":
            params.update({
                "interval": self.interval.currentText(),
                "query_window": self.window.value(),
                "mode": self.mode.currentData(),
                "top_k": self.top_k.value(),
                "adaptive_search": self.adaptive.isChecked(),
                "adaptive_min_window": self.adaptive_min.value(),
                "adaptive_max_window": self.adaptive_max.value(),
                "adaptive_step": self.adaptive_step.value(),
            })
            if self.adaptive_min.value() > self.adaptive_max.value():
                self.status.setText("Adaptive minimum length cannot exceed maximum length")
                return
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
        elif self.kind == "walk_forward":
            params.update({
                "interval": self.interval.currentText(),
                "query_window": self.window.value(),
                "mode": self.mode.currentData(),
                "top_k": self.top_k.value(),
                "max_folds": self.wf_folds.value(),
                "min_training_candles": self.wf_training.value(),
                "candidate_budget": self.wf_budget.value(),
            })
        elif self.kind == "ensemble":
            params.update({
                "interval": self.interval.currentText(),
                "query_window": self.window.value(),
                "mode": self.mode.currentData(),
                "top_k": self.top_k.value(),
            })
        if endpoint_override and endpoint_override.endswith("/robustness"):
            params["max_folds"] = min(params.get("max_folds", 20), 30)
            params["candidate_budget"] = min(params.get("candidate_budget", 1000), 2000)
        self.run_button.setEnabled(False)
        if self.robustness_button is not None:
            self.robustness_button.setEnabled(False)
        self.output.clear()
        self.status.setText("Submitting research job…")
        self.worker = ResearchJobWorker(self.api_url, endpoint_override or self.endpoint, params)
        self.worker.status.connect(self.status.setText)
        self.worker.completed.connect(self.on_completed)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(lambda: self.run_button.setEnabled(True))
        if self.robustness_button is not None:
            self.worker.finished.connect(lambda: self.robustness_button.setEnabled(True))
        self.worker.start()

    def on_completed(self, job: dict):
        self.status.setText(
            f"Completed · {job.get('kind')} · {job.get('updated_at')}"
        )
        result = job.get("result") or {}
        summary = []
        freshness = result.get("data_freshness")
        if freshness:
            freshness_state = "STALE — historical search uses old local data" if freshness.get("is_stale") else "Fresh within configured threshold"
            summary.extend([
                f"DATA FRESHNESS · {freshness_state}",
                f"Latest closed candle age: {freshness.get('age_hours', 0):.1f}h · "
                f"stale threshold: {freshness.get('stale_after_hours', 0):.1f}h",
            ])
        if result.get("adaptive_search"):
            summary.append("\nADAPTIVE WINDOW SEARCH · INDEPENDENT RANKINGS")
            summary.append(result.get("adaptive_comparison_note", ""))
            for window_result in result.get("adaptive_results", []):
                if window_result.get("status") != "completed":
                    summary.append(f"  {window_result.get('window_length')} candles · skipped · {window_result.get('reason', '')}")
                    continue
                summary.append(
                    f"  {window_result['window_length']} candles · {window_result['candidates_examined']:,} candidates · "
                    f"stride {window_result['candidate_stride']} · {len(window_result['analogs'])} analogs"
                )
                for rank, item in enumerate(window_result["analogs"], start=1):
                    analog = item.get("analog", {})
                    summary.append(f"    #{rank} similarity {analog.get('similarity', 0):.4f} · {analog.get('start_time')} → {analog.get('end_time')}")
        if result.get("method") == "bounded_one_factor_at_a_time_sensitivity":
            summary.extend([
                "\nROBUSTNESS AUDIT · BOUNDED PARAMETER SENSITIVITY",
                f"Configurations evaluated: {result.get('configurations_evaluated', 0)} / {result.get('configurations_requested', 0)} · attempted {result.get('configurations_attempted', 0)} · with OOS folds {result.get('configurations_with_oos_folds', 0)}",
                result.get("selection_policy", ""),
                "Not PBO/CSCV; no winning configuration is selected.",
            ])
            for horizon, stability in result.get("stability_by_horizon", {}).items():
                summary.append(
                    f"  +{horizon}: positive configurations {stability['positive_average_return_share']:.0%} · "
                    f"positive excess vs best baseline {stability['positive_excess_vs_best_baseline_share']:.0%} · "
                    f"median avg/fold {stability['median_average_return_per_fold']:+.2%}"
                )
            for run in result.get("runs", []):
                summary.append(
                    f"  {run['configuration']}: {run.get('status', 'completed')} · window {run['query_window']} · top_k {run['top_k']} · "
                    f"folds {run['evaluated_folds']} · skipped {run['skipped_fold_count']}"
                if run.get("status") == "skipped":
                    summary.append(f"    reason: {run.get('reason', 'not enough usable history')}")
                )
        if result.get("method") == "expanding_window_historical_analog_median":
            summary.extend([
                "\nWALK-FORWARD · EXPANDING TRAINING WINDOW",
                f"History: {result.get('history_candles', 0):,} candles · evaluated folds: {result.get('evaluated_folds', 0)} · skipped: {len(result.get('skipped_folds', []))}",
                f"Training is strictly prior · embargo: {result.get('anti_leakage', {}).get('embargo_candles')} candles",
                "Equal-notional fold sums · not compounded · SHORT is theoretical",
            ])
            for horizon, strategies in result.get("metrics_by_horizon", {}).items():
                summary.append(f"  HORIZON +{horizon} candles")
                for strategy, values in strategies.items():
                    summary.append(
                        f"    {strategy.replace('_', ' ').title()}: "
                        f"sum {values['cumulative_return_sum']:+.2%} · "
                        f"avg/fold {values['average_return_per_fold']:+.2%} · "
                        f"positive {values['positive_fold_rate']:.0%} · "
                        f"max DD {values['max_drawdown_sum_basis']:.2%}"
                    )
                    if strategy == "model":
                        summary.append(f"      Trades: {values.get('trades', 0)} · FLAT folds: {values.get('flat_folds', 0)} · positive trades: {values.get('positive_trade_rate', 0):.0%}")
            if result.get("temporal_stability_by_horizon"):
                summary.append("  TEMPORAL STABILITY · EARLY / MIDDLE / RECENT")
                summary.append(result.get("temporal_stability_note", ""))
                for horizon, periods in result["temporal_stability_by_horizon"].items():
                    for period_name, period_metrics in periods.items():
                        model = period_metrics["model"]
                        summary.append(
                            f"    +{horizon} {period_name}: model sum {model['cumulative_return_sum']:+.2%} · "
                            f"positive folds {model['positive_fold_rate']:.0%} · "
                            f"trade rate {model['trade_rate']:.0%}"
                        )
        if "history_candles" in result and result.get("query_selection") is not None:
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
                "\nFORWARD-PATH ASSUMPTIONS",
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
