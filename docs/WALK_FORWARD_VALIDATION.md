# Walk-Forward Validation

## Purpose

The Backtesting Lab provides a fixed-method, expanding-window out-of-sample audit of Pattern Intelligence. It does not optimize strategy parameters and does not place orders.

For each chronological test fold:

1. A query formation is taken from a later, unseen section of the candle history.
2. Historical analogs are searched only in candles strictly before the query start.
3. Candidate forward-outcome paths must end before the test sample begins. The embargo equals the largest requested outcome horizon.
4. The median cost-adjusted LONG and theoretical SHORT outcomes of the selected analogs are used to choose LONG, SHORT or FLAT.
5. The realized forward path after the test query is measured separately, using next-candle-open entry, horizon-close exit, fees and slippage.
6. The fold is compared with always-LONG, always-SHORT and FLAT baselines.

Test query windows and their forward outcome paths are non-overlapping. Training is expanding: data from a completed earlier fold may be used as historical information in a later fold, but never before its timestamp.

## Controls

- **Query window:** number of candles in the formation being matched.
- **Search mode:** free Pattern Intelligence or the preserved five-stage equal-weight positional model.
- **Top analogs:** number of best non-overlapping historical analogs used for the median.
- **Out-of-sample folds:** maximum number of chronological test samples.
- **Minimum training history:** minimum number of candles available before the first test sample. It must be at least query-window length plus 65 candles because the longest default outcome horizon is 64.
- **Candidate budget:** maximum approximate historical candidate windows scanned per fold. Larger budgets improve coverage but increase runtime.

The fold positions are distributed through the available history while preserving a minimum spacing of query-window length plus the maximum forward horizon. This gives a broad chronological sample without reusing test outcome paths.

## Decision rule

For each horizon, the evaluator computes the median net LONG and theoretical SHORT return across the selected historical analogs. It chooses a direction only when that side's median is positive and greater than the opposite side. Otherwise it abstains and records FLAT.

This is a transparent baseline decision rule, not a calibrated probability model. It does not infer a separate SIDEWAYS regime.

## Metrics

Each horizon reports:

- **Cumulative return sum:** sum of equal-notional fold returns; not compounded.
- **Average return per fold.**
- **Positive fold rate:** share of folds with a return above zero. For the model this includes FLAT folds in the denominator.
- **Maximum drawdown on cumulative-sum basis.**

The same measures are calculated for the analog model and three simple baselines. Returns are not compounded because this research pass does not model capital allocation, sizing or concurrent positions.

## Data integrity and limitations

- Query formations and realized forward paths crossing missing-candle gaps are skipped.
- Candidate analogs and their forward paths crossing gaps are excluded by Pattern Intelligence.
- The source market database is read-only.
- SHORT return arithmetic is theoretical and does not model borrow, margin, liquidation, funding or exchange-specific execution.
- Fees and slippage are applied to both entry and exit.
- A fixed method tested on historical folds is not proof of future performance. No parameter search, multiple-testing correction, probability calibration or portfolio-level risk model is performed here.
- The output is historical research only, not a forecast, trading signal or recommendation.

## API

`POST /v1/research/walk-forward` queues a background job. The job result includes fold-level analogs and decisions, per-horizon model/baseline metrics, skipped folds, data freshness and explicit anti-leakage declarations.
