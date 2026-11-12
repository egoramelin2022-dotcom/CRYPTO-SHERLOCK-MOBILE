# CRYPTO SHERLOCK — Platform Blueprint v1

Status: architecture baseline; implementation is staged and must be independently tested.

## Product objective

Build a research-first market-intelligence platform that continuously collects market data, validates it, discovers candidate patterns, tests hypotheses without look-ahead bias, estimates calibrated scenario probabilities, and only advances to paper/live execution after evidence-based gates.

The platform must not claim predictive edge or profitability until out-of-sample and forward paper-trading evidence supports it.

## Non-negotiable invariants

1. Preserve the existing Android application, its SQLite database, Blind Replay workflow, and the legacy five-stage formation strategy.
2. Keep the unconstrained Pattern Intelligence search separate from the legacy five-stage strategy. Both remain independently selectable and independently testable.
3. Never fabricate candles, trades, order-book events, funding rates, or on-chain observations to fill missing data.
4. Every dataset carries source, symbol, market type, interval, event time, ingestion time, schema version, and quality status.
5. Never form a pattern window, feature window, label, or backtest position across an unapproved data gap.
6. Enforce point-in-time correctness: features may use only information available at decision time; labels/outcomes must be strictly in the future.
7. Keep research, paper trading, and live execution isolated. Live execution is disabled by default and requires explicit operator enablement plus risk limits.
8. All strategy results include fees, spread, slippage assumptions, funding where relevant, and uncertainty.
9. Every material change is versioned, tested, reproducible, and traceable to a Git commit and dataset snapshot.
10. Do not put credentials, local databases, or raw private user data in Git.

## Target architecture

### 1. Market Data Engine
- REST historical backfill with pagination, retries, rate-limit handling, checkpointing, and idempotent writes.
- WebSocket streams for trades, depth updates, and market events; maintain sequence IDs and resynchronize from snapshots after gaps.
- Separate adapters by venue and market type (spot, USD-M futures, COIN-M futures).
- Later adapters: funding/open interest/liquidations, on-chain providers, macro calendars, and curated news.
- Preserve raw source payloads or immutable normalized event records where practical.

### 2. Data Quality and Lineage
- Validate schemas, timestamps, candle OHLC invariants, duplicates, ordering, source continuity, and stale/future observations.
- Record gaps as first-class quality events with expected range, source checked, check time, and resolution state.
- Distinguish unavailable-at-source from not-yet-retrieved, API failure, and local ingestion failure.
- Never infer that an empty API response proves the market had no trades; verify endpoint semantics and alternate archives before classifying.
- Data quality gates decide which ranges are eligible for each research run.

### 3. Storage
- Keep SQLite for the current single-machine prototype and preserve the existing database.
- Define repository interfaces so storage can migrate to PostgreSQL/TimescaleDB or a columnar analytical store without rewriting domain logic.
- Separate raw events, normalized market data, derived features, research runs, predictions, and execution records.
- Store UTC timestamps as integer epoch milliseconds or timezone-aware values consistently.

### 4. Feature Engine
- Deterministic, versioned features: returns, ranges, volatility, volume, candle geometry, taker flow, spread, depth imbalance, trade intensity, and cross-timeframe context.
- Every feature records its lookback and availability time.
- No future data, centered rolling windows, or accidental target leakage.

### 5. Pattern Intelligence and Research
- Unconstrained similarity/discovery engine that can find candidate analogues without a required candle sequence.
- Separate legacy five-stage strategy, preserved as an optional mode with equal stage weights as previously specified.
- Candidate generation is not evidence: use holdout periods, walk-forward tests, multiple-testing controls, and baseline comparisons.
- Cluster by market regime and volatility; report sample size and confidence intervals.

### 6. Machine Learning
- Begin with transparent statistical baselines and interpretable models.
- Use time-ordered train/validation/test splits and purged/embargoed splits where labels overlap.
- Track model, feature, dataset, and experiment versions.
- Calibrate probabilities and monitor drift; abstain when confidence or data quality is inadequate.

### 7. Backtesting and Decision Engine
- Event-aware simulation with realistic execution assumptions, fees, spread, slippage, funding, latency, and position constraints.
- Report expectancy, net return, drawdown, turnover, exposure, tail loss, hit rate, calibration, and uncertainty.
- Output LONG / SHORT / WAIT only when rules and evidence pass; include entry/exit logic, invalidation, risk, and reason codes.
- WAIT is a valid and often preferred decision.

### 8. Paper and Live Trading
- Paper trading first, with live market data and simulated fills.
- Compare expected versus realized fills and forecast calibration.
- Live execution is a separate service, off by default, with allowlisted instruments, max position/notional/loss, kill switch, and audit log.
- No exchange API keys are required for data collection; execution credentials must never be stored in source code.

### 9. Interfaces and Operations
- FastAPI remains a read-only data gateway during early milestones.
- Add health, readiness, metrics, structured logs, and operator-visible data-quality status.
- Android remains a client; avoid breaking existing API contracts.
- Background workers and scheduling are added only after idempotency and recovery behavior are tested.

## Proposed repository layout

```text
backend/
  app/
    api/
    domain/
    quality/
    storage/
    features/
    patterns/
    research/
    models/
    backtesting/
    decisions/
    paper/
    execution/       # disabled until explicit later milestone
  collector/
    adapters/
    jobs/
    checkpoints/
  tests/
    unit/
    integration/
    data_quality/
    research/
docs/
  architecture/
  decisions/
  operations/
data/                # local only; excluded from Git
```

This is a target layout, not a claim that these modules already exist.

## Delivery milestones and acceptance gates

### M0 — Baseline and safety
- Capture current repository state and local working changes.
- Add ignore rules, architecture decisions, test conventions, and reproducible environment.
- Verify existing backend tests and Android compatibility assumptions.
- No destructive database migrations.

### M1 — Reliable data foundation
- Harden historical backfill: bounded date ranges, pagination, retries/backoff, checkpoints, idempotency, UTC validation.
- Add gap registry and provenance; do not automatically label empty responses as permanently unavailable.
- Test with mocked Binance responses and small date ranges before any large backfill.
- Acceptance: repeat run adds zero duplicates; interrupted run resumes; gaps are reported accurately.

### M2 — Streaming and normalized storage
- WebSocket trades/depth with sequence validation and resync.
- Persist events and derive candles independently for reconciliation.
- Acceptance: disconnect/reconnect tests, sequence-gap tests, deterministic replay.

### M3 — Feature and pattern research
- Versioned feature definitions and point-in-time tests.
- Unconstrained Pattern Intelligence plus separately selectable legacy five-stage mode.
- Acceptance: no window crosses gaps; no look-ahead; deterministic replay.

### M4 — Research and validation lab
- Walk-forward and holdout evaluation, baselines, multiple-testing controls, realistic costs.
- Acceptance: reproducible reports with dataset/model hashes and uncertainty.

### M5 — Decision and paper trading
- Calibrated LONG/SHORT/WAIT outputs and paper execution.
- Acceptance: forward paper evidence, operational monitoring, risk controls.

### M6 — Optional controlled live execution
- Separate, disabled-by-default execution service.
- Requires explicit user approval, exchange permissions, kill switch, and strict risk limits.
- No automatic promotion from research to live.

## Immediate next implementation task

Implement M1 only: a tested, resumable, idempotent historical data pipeline and explicit gap registry. Do not rewrite the whole backend at once. First inspect and test the current collector, then introduce small modules behind stable interfaces.
