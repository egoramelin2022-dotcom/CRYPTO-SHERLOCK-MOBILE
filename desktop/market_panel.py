"""Live Binance Spot market panel backed by the local Sherlock API."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pyqtgraph as pg
from PySide6.QtCore import QThread, Signal, QRectF
from PySide6.QtGui import QPicture, QPainter
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from desktop.market_data import Candle, parse_klines_payload


class MarketWorker(QThread):
    loaded = Signal(list, dict)
    failed = Signal(str)

    def __init__(self, base_url: str, symbol: str, interval: str, limit: int = 240):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.symbol = symbol
        self.interval = interval
        self.limit = limit

    def run(self):
        try:
            with httpx.Client(timeout=12.0) as client:
                candles_response = client.get(
                    f"{self.base_url}/v1/market/klines",
                    params={"symbol": self.symbol, "interval": self.interval, "limit": self.limit},
                )
                candles_response.raise_for_status()
                candles = parse_klines_payload(candles_response.json())
                ticker_response = client.get(
                    f"{self.base_url}/v1/market/ticker/24hr",
                    params={"symbol": self.symbol},
                )
                ticker_response.raise_for_status()
                ticker = ticker_response.json()
            if not candles:
                raise ValueError("API returned an empty candle set")
            self.loaded.emit(candles, ticker)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class CandlestickItem(pg.GraphicsObject):
    """Small CPU-friendly candlestick renderer; x is candle index."""

    def __init__(self, candles: list[Candle]):
        super().__init__()
        self.candles = candles
        self.picture = QPicture()
        painter = QPainter(self.picture)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for index, candle in enumerate(candles):
            rising = candle.close >= candle.open
            pen_color = pg.mkColor("#48D6AE" if rising else "#F07178")
            painter.setPen(pg.mkPen(pen_color, width=1))
            painter.drawLine(index, candle.low, index, candle.high)
            top = max(candle.open, candle.close)
            bottom = min(candle.open, candle.close)
            height = max(top - bottom, max(candle.close * 0.00003, 1e-9))
            painter.setBrush(pg.mkBrush(pen_color))
            painter.drawRect(QRectF(index - 0.32, bottom, 0.64, height))
        painter.end()

    def paint(self, painter, *args):
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return self.picture.boundingRect()


class MarketPanel(QWidget):
    def __init__(self, api_url: str):
        super().__init__()
        self.api_url = api_url
        self.worker: MarketWorker | None = None
        self.candles: list[Candle] = []
        root = QVBoxLayout(self)
        root.setSpacing(14)

        controls = QHBoxLayout()
        self.symbol = QComboBox()
        self.symbol.addItems(["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"])
        self.interval = QComboBox()
        self.interval.addItems(["15m", "1h", "4h", "1d"])
        self.refresh_button = QPushButton("REFRESH MARKET")
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(QLabel("SYMBOL"))
        controls.addWidget(self.symbol)
        controls.addWidget(QLabel("TIMEFRAME"))
        controls.addWidget(self.interval)
        controls.addStretch(1)
        controls.addWidget(self.refresh_button)
        root.addLayout(controls)

        self.price = QLabel("—")
        self.price.setObjectName("marketPrice")
        self.change = QLabel("Waiting for verified market response")
        self.change.setObjectName("muted")
        root.addWidget(self.price)
        root.addWidget(self.change)

        self.chart = pg.PlotWidget()
        self.chart.setBackground("#111B23")
        self.chart.showGrid(x=True, y=True, alpha=0.15)
        self.chart.setLabel("left", "Price")
        self.chart.setLabel("bottom", "Recent candles")
        self.chart.getAxis("left").setTextPen("#82939F")
        self.chart.getAxis("bottom").setTextPen("#82939F")
        self.chart.getViewBox().setBorder(pg.mkPen("#263641"))
        root.addWidget(self.chart, 1)

        self.status = QLabel("No market data loaded")
        self.status.setObjectName("muted")
        root.addWidget(self.status)

    def refresh(self):
        if self.worker is not None and self.worker.isRunning():
            return
        self.refresh_button.setEnabled(False)
        self.status.setText("Fetching live public market data…")
        self.worker = MarketWorker(self.api_url, self.symbol.currentText(), self.interval.currentText())
        self.worker.loaded.connect(self.on_loaded)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(lambda: self.refresh_button.setEnabled(True))
        self.worker.start()

    def on_loaded(self, candles: list[Candle], ticker: dict):
        self.candles = candles
        self.chart.clear()
        self.chart.addItem(CandlestickItem(candles))
        self.chart.setXRange(max(0, len(candles) - 100), len(candles) + 2, padding=0)
        self.chart.enableAutoRange(axis="y", enable=True)
        last = float(ticker["last_price"])
        pct = float(ticker["price_change_percent"])
        self.price.setText(f"{self.symbol.currentText()}   {last:,.2f}")
        self.change.setText(f"24H {pct:+.2f}%  ·  High {float(ticker['high_price']):,.2f}  ·  Low {float(ticker['low_price']):,.2f}")
        stamp = datetime.fromtimestamp(candles[-1].open_time / 1000, tz=timezone.utc)
        self.status.setText(
            f"Loaded {len(candles)} candles · last candle open {stamp:%Y-%m-%d %H:%M UTC} · public Binance Spot via Sherlock backend"
        )

    def on_failed(self, message: str):
        self.status.setText(f"Market data unavailable: {message}")
