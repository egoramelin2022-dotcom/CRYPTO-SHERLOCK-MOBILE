# Prediction Accuracy and Controlled Learning

## What "accuracy" means

The Sherlock Core's analogue outcome summary is descriptive: it tells what
happened after historical analogues. It is not itself a prediction accuracy
measurement.

The walk-forward evaluator is the source of historical out-of-sample
predictions. At each test fold it:
- freezes the query using only candles available at that time;
- searches only earlier history and applies the forward-horizon embargo;
- emits LONG, SHORT or FLAT before the hidden forward path is evaluated;
- scores the realized path after configured fees and slippage.

`prediction_scorecard_by_horizon` reports:
- **overall accuracy**: correct LONG/SHORT/FLAT classifications divided by all scored folds;
- **directional hit rate**: correct LONG/SHORT calls divided by directional calls only;
- **coverage**: directional calls divided by all scored folds;
- per-class precision, recall and F1;
- balanced accuracy and the full confusion matrix.

The realized class is LONG when only the cost-adjusted long side is profitable,
SHORT when only the cost-adjusted short side is profitable, and FLAT when
neither side clears the configured costs. If both sides are positive due to
unusual input/cost assumptions, the larger net-return side is used.

These are historical diagnostic rates, not calibrated probabilities. Always
display the sample count and coverage beside a percentage. A system that only
makes one correct call out of one has 100% observed accuracy but no meaningful
evidence of reliability. Compare with simple baselines and inspect results by
time period and market regime.

## Controlled self-learning: required architecture

The current Experiment Ledger is passive research memory. It stores runs and
results; it does not learn parameters, train a model or promote strategies.
The new scorecard makes hidden-history performance measurable, but it does
not by itself create self-learning.

The next learning system must be staged:

1. **Hypothesis memory** — group runs by a canonical strategy/hypothesis ID,
   algorithm version, feature schema, parameters and exact input fingerprint.
   Keep every version immutable.
2. **Outcome labels** — persist the walk-forward fold predictions and realized
   outcomes, including horizon, costs, regime, query timestamp and data
   fingerprint. Labels must never be visible to the predictor at decision time.
3. **Candidate generation** — create new strategy variants from explicit,
   bounded changes to features/windows/thresholds. Record the parent version
   and the reason for each change.
4. **Nested chronological evaluation** — use inner training/validation windows
   for candidate selection and outer untouched walk-forward folds for
   unbiased evaluation. Purge overlapping forward labels and embargo at least
   the maximum outcome horizon.
5. **Promotion gate** — compare the candidate with the incumbent and simple
   baselines on identical folds, including costs, drawdown, coverage, sample
   count, regime stability, parameter sensitivity and multiple-testing risk.
6. **Final holdout** — reserve a final chronological segment that is not used
   for feature design, parameter selection or candidate ranking. Open it only
   for a frozen candidate; if it fails, retire the candidate and do not tune
   against that same holdout.
7. **Paper-only shadow phase** — run the frozen candidate without real orders.
   Monitor drift and prediction quality. Any material change creates a new
   version and requires a fresh validation cycle.

## Non-negotiable safeguards

- No online weight updates from the latest candles or from the same holdout
  used to report final accuracy.
- No promotion based on raw accuracy alone; include coverage, net returns,
  drawdown, costs and baselines.
- No automatic strategy promotion from a single good fold or a small sample.
- No real exchange orders, leverage, capital allocation or live trading path.
- A model may abstain. Insufficient evidence must remain "not evaluated",
  not be converted into a guessed percentage.
