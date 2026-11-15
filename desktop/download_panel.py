"""Интерфейс загрузки и проверки архивов Binance Spot в staging-базу."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
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
        latest_complete_month = (
            datetime.now(timezone.utc).replace(day=1) - timedelta(days=1)
        ).strftime("%Y-%m")
        self.end = QLineEdit(latest_complete_month)
        form.addRow("Первый месяц (ГГГГ-ММ)", self.start)
        form.addRow("Последний месяц (ГГГГ-ММ)", self.end)
        root.addLayout(form)
        actions = QHBoxLayout()
        self.run_button = QPushButton("ЗАГРУЗИТЬ АРХИВЫ ВО ВРЕМЕННОЕ ХРАНИЛИЩЕ")
        self.run_button.clicked.connect(self.start_download)
        self.sync_button = QPushButton("СИНХРОНИЗИРОВАТЬ ТЕКУЩИЙ МЕСЯЦ")
        self.sync_button.clicked.connect(self.start_current_month_sync)
        actions.addWidget(self.run_button)
        actions.addWidget(self.sync_button)
        actions.addStretch(1)
        root.addLayout(actions)
        self.status = QLabel("Загрузка архивов ещё не запускалась")
        self.status.setObjectName("muted")
        root.addWidget(self.status)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Здесь появятся результаты загрузки, проверки и импорта.")
        root.addWidget(self.output, 1)
        note = QLabel(
            "Загружаются официальные месячные архивы Binance Spot с проверкой SHA256. "
            "Синхронизация текущего месяца получает только полностью закрытые свечи BTCUSDT "
            "15m / 4h / 1d через публичный API. Обе операции записывают данные только "
            "в отдельную временную базу (staging). Исходная база рынка не изменяется."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)

    def start_download(self):
        if self.worker is not None and self.worker.isRunning():
            return
        start, end = self.start.text().strip(), self.end.text().strip()
        import re
        if not re.fullmatch(r"\\d{4}-(0[1-9]|1[0-2])", start) or not re.fullmatch(r"\\d{4}-(0[1-9]|1[0-2])", end):
            QMessageBox.warning(self, "Неверный формат даты", "Укажите месяц в формате ГГГГ-ММ, например 2017-08.")
            return
        if tuple(map(int, start.split("-"))) > tuple(map(int, end.split("-"))):
            QMessageBox.warning(self, "Неверный период", "Начальный месяц не может быть позже конечного.")
            return
        answer = QMessageBox.question(
            self, "Подтверждение загрузки архивов",
            f"Загрузить архивы Binance Spot BTCUSDT 15m / 4h / 1d за период с {start} по {end}?\\n\\n"
            "Файлы и свечи будут записаны только во временное хранилище. "
            "Потребуется дополнительное место на диске; операция может занять продолжительное время.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.run_button.setEnabled(False)
        self.sync_button.setEnabled(False)
        self.output.clear()
        self.status.setText("Подготовка загрузки архивов…")
        self.worker = ResearchJobWorker(
            self.api_url, "/v1/data/archive-download",
            {"start": start, "end": end},
        )
        self.worker.status.connect(self.status.setText)
        self.worker.completed.connect(self.on_completed)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def start_current_month_sync(self):
        if self.worker is not None and self.worker.isRunning():
            return
        answer = QMessageBox.question(
            self, "Подтверждение синхронизации",
            "Получить полностью закрытые свечи BTCUSDT 15m, 4h и 1d за текущий месяц "
            "из публичного Binance Spot API?\\n\\n"
            "Обновится только временная база. Исходная база останется без изменений.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.run_button.setEnabled(False)
        self.sync_button.setEnabled(False)
        self.output.clear()
        self.status.setText("Запрос текущих данных…")
        self.worker = ResearchJobWorker(
            self.api_url, "/v1/data/sync-current-month", {"symbol": "BTCUSDT"}
        )
        self.worker.status.connect(self.status.setText)
        self.worker.completed.connect(self.on_completed)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_finished(self):
        self.run_button.setEnabled(True)
        self.sync_button.setEnabled(True)

    def on_completed(self, job: dict):
        self.status.setText(f"Задача «{job.get('kind', 'Загрузка данных')}» завершена")
        self.output.setPlainText(json.dumps(job.get("result") or {}, ensure_ascii=False, indent=2))

    def on_failed(self, message: str):
        self.status.setText("Ошибка операции с данными")
        self.output.setPlainText(message)
