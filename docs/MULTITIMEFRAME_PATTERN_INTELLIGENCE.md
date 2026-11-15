# Multi-Timeframe Pattern Intelligence v0.1.0

Module: `backend/app/research/multitimeframe_pattern_intelligence.py`

This module extends the existing specialized multi-timeframe setup detector. It does not replace that detector, the free Pattern Intelligence search, or the saved five-stage mode.

## Purpose

Search historical BTCUSDT (or another supported symbol) for complete price-structure analogues using four simultaneously observed timeframes:

- 15m: local candle sequence and execution/outcome clock;
- 1h: short-term structure;
- 4h: intermediate structure;
- 1d: broader market context.

The first implementation uses equal timeframe weights by default. Weights and window lengths are explicit configuration values and are research parameters, not fitted truths.

## Causal alignment

Every query and historical candidate is anchored to a closed 15m candle. For each timeframe, the module selects the latest candle satisfying:

`close_time <= decision_time`

This is critical: an unfinished 1h, 4h, or daily candle is never used to describe a historical decision point.

Each timeframe window must be contiguous. Missing intervals are not filled or interpolated. A query with a gap in any required timeframe is rejected; candidate windows crossing gaps are skipped.

Candidate shapes and their full forward-outcome paths must end before the query window begins. Candidate episodes are de-duplicated when their higher-timeframe context is identical or their shape/outcome ranges overlap.

## Similarity features

Each timeframe compares scale-free sequences containing:

- normalized cumulative log-price path;
- signed candle body relative to local volatility;
- upper- and lower-wick fractions;
- close location inside the candle range;
- normalized one-candle return;
- short local structure position;
- log relative volume;
- normalized candle range.

The combined distance is a weighted mean of per-timeframe distances. The reported similarity is a monotonic distance transform; it is **not** a probability of future direction.

## Forward outcomes

Outcomes are calculated only after a historical candidate is frozen. Entry is the next 15m candle open; exit is the close of the requested horizon candle. Fees and slippage are charged on both sides using the existing `evaluate_forward_path` implementation.

Default horizons are 16, 96, 288, 480 and 960 15m candles (4h, 1d, 3d, 5d and 10d). A missing candle inside a candidate's forward path invalidates that outcome rather than being silently bridged.

## API

`POST /v1/research/multitimeframe-patterns`

Parameters:
- `symbol` (default BTCUSDT)
- `query_window_15m` (default 32)
- `window_1h` (default 16)
- `window_4h` (default 8)
- `window_1d` (default 5)
- `top_k` (default 30)
- `candidate_budget` (default 2000; bounded sampling stride is derived)
- `query_end_time` (optional exact 15m candle open time in UTC milliseconds for historical replay)
- `fee_bps_per_side` and `slippage_bps_per_side`

The endpoint queues a background job. Read its result from `GET /v1/research/jobs/{job_id}`. The result includes normalized query and candidate close paths for all four timeframes; the Windows desktop panel renders them in separate 15m, 1h, 4h and 1d comparison tabs.

The service loads only locally configured market databases using the existing read-only loader. Each timeframe gets its own canonical candle fingerprint; those fingerprints are combined into the input fingerprint stored in the existing append-only Experiment Ledger. The source market databases are not modified.

## Current limitations

- v0.1.0 supports fixed window lengths per timeframe; automatic multi-window selection is a subsequent phase.
- Feature weights and timeframe weights are explicit starting values, not optimized.
- This version ranks analogues and reports their historical outcomes. It does not calibrate probabilities or issue LONG/SHORT/SIDEWAYS forecasts.
- A historical analogue count is not an independent sample count unless overlap and shared market context have been addressed; this implementation de-duplicates exact higher-timeframe contexts and overlapping candidate/outcome ranges, but later validation must still account for serial dependence.
- No profitability or predictive edge is claimed. Walk-forward validation, baseline comparison, sensitivity testing, and an untouched holdout remain mandatory.

## Tests

`backend/tests/test_multitimeframe_pattern_intelligence.py` covers multi-timeframe ranking, closed-bar alignment, gap rejection, and configuration validation. `backend/tests/test_main.py` covers API queue wiring and parameter validation.
