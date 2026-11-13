# CRYPTO SHERLOCK Data Gateway

First backend foundation for the Android app. It is a **read-only** gateway to public Binance Spot market data. It does not place orders, request API keys, or claim to produce profitable signals.

## Run locally (PC)

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` for the interactive API reference.

## Endpoints

- `GET /health`
- `GET /v1/market/ticker/24hr?symbol=BTCUSDT`
- `GET /v1/market/klines?symbol=BTCUSDT&interval=15m&limit=500`
- `GET /v1/market/orderbook?symbol=BTCUSDT&limit=100`
- `GET /v1/market/agg-trades?symbol=BTCUSDT&limit=500`

The kline response preserves Binance timestamps and includes taker-buy volume fields. Order-book endpoint returns a snapshot only: a true live order-flow feed requires a WebSocket stream plus snapshot/delta sequencing, which is the next implementation step. Historical footprint/order-book depth cannot be reconstructed from OHLCV candles.

## Docker

From the repository root: `docker build -t sherlock-gateway ./backend`, then `docker run --rm -p 8000:8000 sherlock-gateway`.

## Safety and deployment

- Keep this service read-only. Do not add exchange trading credentials to the mobile APK.
- For Android on the same Wi-Fi, start with `uvicorn app.main:app --host 0.0.0.0 --port 8000` and set the app server URL to `http://<PC-LAN-IP>:8000` (find the IPv4 address with `ipconfig`). Allow Python/port 8000 through Windows Firewall on Private networks only. Android Emulator uses `http://10.0.2.2:8000`. Do not use `127.0.0.1` from a physical phone: it points to the phone itself.

Bind to localhost for local development. Before exposing it publicly, add authentication, TLS/reverse proxy, request throttling, logging with secrets redacted, and firewall rules.
- Never expose a development server directly to the public internet.
