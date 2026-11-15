# Independent Multi-Timeframe Validation

## Scope

`backend/app/research/multitimeframe_walk_forward.py` implements a chronological
holdout audit for the four-timeframe analogue matcher. It is deliberately
separate from the current-query analogue panel and does not issue live signals.

## Protocol

- Use a frozen `MultiTimeframeSearchConfig`; this audit does not optimize
  feature weights, timeframe weights, windows, or decision thresholds.
- Query windows are evaluated in chronological order.
- A fold's analogue search is anchored at the final closed 15m candle in the
  query window. The matcher only admits historical candidates whose maximum
  forward-outcome horizon plus embargo ends before the query window.
- Query windows and their realized forward horizons are spaced so test outcome
  periods do not overlap.
- The realized outcome is measured after the decision close, with entry at the
  next 15m open and fees/slippage charged on both sides.
- Candidate sampling stride is recalculated for each fold to keep the maximum
  historical candidate budget bounded as the training history expands.

## Comparators

At every horizon, report equal-notional fold returns for:
- MTF analogue decision (LONG/SHORT only when median analogue net return is
  positive and strictly better than the opposite side; otherwise FLAT);
- always LONG;
- always SHORT;
- FLAT;
- query-window momentum with a fixed, predeclared threshold.

Returns are not compounded account returns. The audit reports fold count,
mean/median return, positive-fold fraction, cumulative sum, and drawdown on the
sum basis. These are diagnostics, not a claim of profitability.

## Required next checks

1. Run the new deterministic unit tests and full research integration suite.
2. Add an immutable input fingerprint and append-only experiment-ledger record
   for each completed validation run.
3. Expose the audit as a queued backend research job and render its fold and
   baseline tables in the desktop panel.
4. Run on the full verified BTCUSDT 15m/1h/4h/1d history, report data gaps and
   coverage, then repeat on other symbols without retuning.
5. Keep a final untouched time block that is not used to change any settings.
6. Report uncertainty and sample size; do not translate historical positive-fold
   frequency into a probability of future profit.

## Limitations

This first engine is a testable validation core. It is not yet wired into the
HTTP API, desktop UI, experiment ledger, or automated multi-symbol batch runner.
A successful unit test is not an empirical validation result. No predictive
edge or profitability is claimed.
