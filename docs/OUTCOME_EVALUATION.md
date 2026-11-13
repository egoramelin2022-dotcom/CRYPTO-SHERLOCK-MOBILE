# Forward Outcome Evaluation

The outcome_evaluation module is a pure, read-only evaluator for a frozen historical candidate window.

## Timing contract

- Candidate end is inclusive and must already be closed.
- Entry is the next candle open, not the candidate candle close.
- Horizon N exits at the close of candle candidate_end_index + N.
- A horizon without enough future candles is null; no extrapolation or partial-horizon substitution is made.
- The evaluated path is checked for candle validity, common symbol/timeframe, and timestamp continuity. A gap invalidates the evaluation.

## Metrics

Each horizon reports gross close-to-close return, cost-adjusted LONG and SHORT net returns, directional MFE/MAE, maximum high/low range, and absolute close return.

MFE is nonnegative and MAE nonpositive, measured from the next candle open. LONG and SHORT excursions are reported separately. Fees and slippage are configurable in basis points per side and charged on both entry and exit. This is a simplified proportional-cost model; it does not model spread dynamics, market impact, funding, borrow costs, partial fills, or exchange-specific fee tiers.

The neutral range and absolute-return fields are descriptors only. They do not classify a market as SIDEWAYS. A sideways label needs a separately specified, calibrated rule and independent validation; it must not be inferred from a convenient threshold after seeing outcomes.

## Leakage and interpretation

This module evaluates forward paths only after candidate discovery. It does not discover candidates, tune parameters, assign probabilities, create forecasts, or emit trading signals. For a fair historical study, candidate selection and all feature transforms must be frozen using information available at query time. Overlapping candidate outcome windows must later be handled by chronological purged/embargoed evaluation folds; this function does not construct those folds.

Default horizons (1, 4, 16, 32, 64) are measurement windows, not optimized trading holding periods.
