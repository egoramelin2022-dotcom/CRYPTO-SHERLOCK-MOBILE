# Anti-Overfitting, Regime Detection and Strategy Portfolio

## 1. Anti-overfitting diagnostics

The bounded robustness audit runs a small predeclared neighborhood of query-window and analog-count settings. It never selects a winning configuration or feeds results back into the model.

An additional PBO-style combinatorially symmetric cross-validation diagnostic is calculated only across baseline / fewer-analogs / more-analogs variants. Those three runs share the same query-window length and are paired by exact out-of-sample query timestamps. The fold returns are split into equal in-sample and out-of-sample halves; the in-sample winner is ranked among all tested variants out of sample. PBO is the share of partitions where that winner ranks below the median.

Because the candidate set is intentionally small and correlated, this is a limited diagnostic, not proof against all forms of overfitting, not a probability of future loss, and not a substitute for a truly untouched final holdout. The number of evaluated partitions is capped and deterministic.

## 2. Causal regime detection

Each walk-forward test fold receives a rule-based regime label using only closed candles through that fold's query close. The current labels are HIGH_VOLATILITY, TREND_UP, TREND_DOWN, ACCUMULATION_CANDIDATE and SIDEWAYS. Features include trailing net return, realized volatility per candle, directional efficiency, range position and late-versus-early volume. The default lookback is up to 96 closed candles. Any window crossing a missing-candle gap is marked unclassified rather than bridged.

Default rule thresholds are 0.6% realized volatility per candle, 1.5% trailing net return for directional trends, and a 1.10 late/early volume ratio for accumulation candidates. They are explicit configuration metadata, not statistically calibrated thresholds; regime labels should not be compared across intervals without recalibration. The regime labels are descriptive heuristics, not trained classifiers. ACCUMULATION_CANDIDATE is not evidence of institutional buying. The engine reports model outcomes by regime and horizon to reveal where historical behavior differed; it does not use future returns to assign a regime.

## 3. Strategy portfolio diagnostics

The Backtesting Lab compares four causal methods on the same walk-forward fold outcomes and horizons:

- **Pattern analogs:** the median cost-adjusted forward outcome of historical matches; LONG / SHORT is selected only when its median is positive and exceeds the opposite side.
- **Trend following:** LONG / SHORT when the query-window close-to-close move exceeds +/-0.5%; otherwise FLAT.
- **Mean reversion baseline:** the opposite of the trailing-momentum direction; this is a deliberately simple contrarian reference, not a full moving-average or statistical-arbitrage model.
- **Range breakout:** LONG / SHORT when the query close breaks the high / low of the 20 candles immediately before the query window; otherwise FLAT.

All signals use only data available by the query close. Their realized returns are measured on the exact same future fold path, with the same configured fees and slippage. The panel reports individual fold returns, pairwise correlations and an equal-weight combination. This reveals whether methods repeat or offset each other's errors.

The robustness audit separately compares baseline, fewer-analogs and more-analogs variants on identical fold timestamps, reporting their correlations and equal-weight diagnostic. Neither equal-weight series simulates simultaneous positions, cash allocation, turnover, compounding, sizing, market impact or execution interactions. These are not deployable portfolios.

## Safety and interpretation

All three modules are historical research. They do not place real orders, use leverage, or manage real capital. Research SHORT returns remain theoretical. Any positive historical result can fail out of sample.