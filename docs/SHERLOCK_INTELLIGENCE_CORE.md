# Sherlock Intelligence Core v0.1.0

## Purpose

The Core is the coordinator for research modules. It does not replace Pattern Intelligence, the regime detector, or the walk-forward evaluator with one opaque model. It runs specialist modules, preserves their outputs and provenance, highlights disagreements, and identifies the next validation steps.

## Current execution graph

1. **Input gate** — validate the closed-candle query, candle integrity, symbol/interval consistency, search controls and cost assumptions.
2. **Pattern Intelligence** — search historical analogs in either free mode or the preserved five-stage mode. Candidate sampling is bounded by a deterministic index stride when required by the caller.
3. **Market Regime** — classify the trailing query context using only candles available through the query close. If the trailing window crosses a gap or is too short, report an explicit unclassified state.
4. **Forward Outcome Evaluator** — replay each selected analog from the next candle open, charging the configured fee and slippage on entry and exit.
5. **Evidence Summary** — aggregate per-horizon median/mean net returns, positive-return rates, excursion/range context and a separately defined retrospective sideways-path rate.
6. **Conflict Audit** — compare historical analogue direction with a directional trailing regime. An opposing pair is surfaced as a conflict; the Core does not resolve it by silently preferring one module.
7. **Validation Gate** — emit required walk-forward, baseline, robustness and untouched-holdout checks.

## Output contract

The result contains core_version and unique run_id; query and history time boundaries; algorithm, mode, horizon, sampling, sample-size and cost provenance; independent module status/results; per-horizon outcome summaries and sample counts; cross-module conflicts; required next checks; and an explicit abstention object.

historical_analogue_side is a descriptive summary of the selected analog outcomes after assumed costs. It is not a current-market forecast, calibrated probability, or trading recommendation. SIDEWAYS is counted only when BOTH the full high-low range is at most 1.0% and the absolute entry-to-exit close move is at most 0.5%; these are initial descriptive defaults, not calibrated cross-timeframe thresholds.

## API

POST /v1/research/core queues the Core over verified local candle history. It supports symbol, interval, query_window, optional exact query_start_time, mode, top_k, min_analogs, candidate_budget, and per-side fee/slippage assumptions. Poll the returned job ID through GET /v1/research/jobs/{job_id}.

The service reads the immutable source database and verified archive staging through the existing read-only loader. The endpoint is asynchronous and uses a bounded candidate budget; no source candles are modified.

## Current boundaries

- The first Core release coordinates Pattern Intelligence, causal regime context and cost-adjusted analog outcomes.
- Multi-timeframe detection, STUMPY consensus, walk-forward, robustness and strategy portfolio remain separately callable specialist services. They are listed as mandatory follow-up validation rather than automatically executed on every Core request because of runtime and resource cost.
- No model training, probability calibration, automatic model promotion, capital allocation, leverage, or live exchange order path is included.
- The Core always returns trading_signal: null, paper_trade_eligible: false, and abstain: true.

## Release gate

Before treating Core output as a validated research conclusion, require the backend test suite, data-integrity checks on the user's local database, chronological walk-forward evaluation, baseline comparison, bounded robustness audit, and a genuinely untouched final holdout. The target Windows PC still requires a local smoke test after the branch is integrated.
