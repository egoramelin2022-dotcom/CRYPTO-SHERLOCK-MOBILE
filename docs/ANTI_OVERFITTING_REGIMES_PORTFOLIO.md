# Anti-Overfitting, Regime Detection and Strategy Portfolio

## 1. Anti-overfitting diagnostics

The bounded robustness audit runs a small predeclared neighborhood of query-window and analog-count settings. It never selects a winning configuration or feeds results back into the model.

An additional PBO-style combinatorially symmetric cross-validation diagnostic is calculated only across baseline / fewer-analogs / more-analogs variants. Those three runs share the same query-window length and are paired by exact out-of-sample query timestamps. The fold returns are split into equal in-sample and out-of-sample halves; the in-sample winner is ranked among all tested variants out of sample. PBO is the share of partitions where that winner ranks below the median.

Because the candidate set is intentionally small and correlated, this is a limited diagnostic, not proof against all forms of overfitting, not a probability of future loss, and not a substitute for a truly untouched final holdout. The number of evaluated partitions is capped and deterministic.

## 2. Causal regime detection

Each walk-forward test fold receives a rule-based regime label using only closed candles through that fold's query close. The current labels are HIGH_VOLATILITY, TREND_UP, TREND_DOWN, ACCUMULATION_CANDIDATE and SIDEWAYS. Features include trailing net return, realized volatility, directional efficiency, range position and relative volume.

The regime labels are descriptive heuristics, not trained classifiers. ACCUMULATION_CANDIDATE is not evidence of institutional buying. The engine reports model outcomes by regime and horizon to reveal where historical behavior differed; it does not use future returns to assign a regime.

## 3. Strategy portfolio diagnostics

The robustness audit compares the baseline, fewer-analogs and more-analogs variants on identical fold timestamps. It reports pairwise return correlations and an equal-weight combination of their per-fold returns. This reveals whether parameter variants tend to repeat or offset each other's errors.

The equal-weight series is a diagnostic only. It does not simulate simultaneous positions, cash allocation, turnover, compounding, sizing, market impact or execution interactions. It is not a deployable portfolio.

## Safety and interpretation

All three modules are historical research. They do not place real orders, use leverage, or manage real capital. Research SHORT returns remain theoretical. Any positive historical result can fail out of sample.