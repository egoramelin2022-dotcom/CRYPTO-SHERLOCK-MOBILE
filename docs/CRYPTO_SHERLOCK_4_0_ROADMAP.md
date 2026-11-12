# CRYPTO SHERLOCK 4.0 — Research & Validation Roadmap

## Product objective
Build a dependable market-research workstation. The app must discover recurring structures, quantify uncertainty, and prove any claimed edge on unseen chronological data. A visually polished UI is important, but no strategy is promoted because of an attractive in-sample result.

## Non-negotiable research rules
- No look-ahead: features at decision time may use only candles that have closed by that time.
- Chronological train/validation/test splits; parameters are frozen before the final test.
- Purge/embargo windows around split boundaries at least as long as the maximum forecast horizon.
- Deduplicate overlapping analog windows and report the effective independent sample count.
- Compare every strategy against buy-and-hold, always-flat, simple momentum/trend and shuffled-label baselines.
- Include fees, spread, slippage, funding (when applicable), and execution delay.
- Report trade count, exposure, coverage, win rate, mean and median net return, profit factor, expectancy, max drawdown, time under water, MAE/MFE, and confidence intervals.
- Separate descriptive similarity scores from calibrated probabilities.
- Never present backtest performance as a promise of future returns.

## 4.0 workstreams

### A. Pattern Intelligence 3.x
Represent each candle with normalized body, upper/lower wick, range, log return, relative volume, and volatility context. Compare multiple scales (short/medium/long windows), preserve temporal order, and allow weighted feature ablations. Return analog clusters, not just a top-10 list. Show how results change when each feature family is removed.

### B. Blind Replay / Walk-forward Lab
Run chronological rolling-origin tests with frozen parameters. Show progress, allow cancellation, persist reports, and resume safely. Keep the future segment hidden until the prediction is recorded. Add several forecast horizons and non-overlapping scoring windows. Persist every prediction with timestamp, model version, data range, parameters, and later outcome.

### C. Strategy Benchmark
Evaluate Pattern Intelligence, Five-Stage, Cycle Hunter and baseline strategies on identical dates, costs, position sizing, and risk limits. The Five-Stage strategy remains an independent optional mode and is never merged into free-form Pattern Intelligence.

### D. Cycle Hunter
Detect multi-month and multi-year structures using trend slope, drawdown/recovery geometry, volatility contraction/expansion, volume regime, moving-average structure, and cycle duration. Match historical cycles without selecting examples based on their later returns. Clearly label incomplete/current cycles.

### E. Forecast & decision layer
Produce LONG / SHORT / SIDEWAYS probabilities only after calibration on validation data. Include horizon, confidence interval, evidence, invalidation, freshness, and WAIT / SETUP / ACTIVE / INVALIDATED state. If evidence is weak, abstain.

### F. Premium mobile experience
Create a compact dashboard with clear navigation, cards, charts, filters, progress, and readable research reports. Long calculations must run off the UI thread, show progress and cancellation, and never block market refresh or navigation.

## Release gates for 4.0
1. Automated unit tests for no-look-ahead, split embargo, candle features, and scoring.
2. Synthetic-data tests where expected patterns and outcomes are known.
3. Reproducible benchmark report with data provenance and frozen parameters.
4. Out-of-sample performance compared with baselines, net of realistic costs.
5. Stable APK build and device smoke test covering navigation, database persistence, long replay, cancellation, and recovery after process death.
6. No real-money automated execution in 4.0. Paper trading only after research gates pass.

## Current known limitations to close
- Blind Replay is still an experimental prototype; costs and funding are not included.
- Similarity and directional confidence are not calibrated probabilities.
- Effective sample size and overlap/purge controls need explicit reporting.
- Strategy comparison currently has too few test trades for strong conclusions.
- Physical device behavior must be smoke-tested; CI build success alone is not device validation.
