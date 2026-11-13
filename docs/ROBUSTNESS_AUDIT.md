# Robustness Audit

## Purpose

The Robustness Audit is a bounded parameter-sensitivity diagnostic built on the fixed-method walk-forward evaluator. It is intended to reveal whether the headline result is fragile to small, predeclared changes in the query-window length and number of historical analogs.

It is not an optimizer. The application does not select or recommend a winning configuration.

## Configurations

The audit evaluates up to five one-factor-at-a-time configurations around the values selected in Backtesting Lab:

- baseline query window and analog count;
- a shorter query window (approximately 80% of baseline);
- a longer query window (approximately 120% of baseline);
- fewer analogs (approximately 50% of baseline);
- more analogs (approximately 150% of baseline).

Duplicate configurations are removed, for example near the minimum or maximum supported query-window values.

Each configuration is run independently through the expanding-window walk-forward engine. Each run retains its own folds, analogs, costs, and baseline comparisons. Raw similarity scores and returns are not pooled across parameterizations.

## Reported diagnostics

For each configuration and horizon, the report includes:

- number of evaluated and skipped folds;
- average return per fold and positive fold rate;
- number of model trades and trade rate;
- positive trade rate;
- average returns of always-LONG, theoretical always-SHORT and FLAT baselines;
- excess of the model's average return over the best-performing simple baseline on that same evaluation run.

The cross-configuration summary reports the share of configurations with positive average returns, the share with positive excess over their best simple baseline, and median average return/excess.

The "best baseline" is selected retrospectively from the three simple baselines on the same evaluation run. It is an optimistic reference hurdle, not a strategy selected in advance or an independently validated benchmark.

## Runtime bounds

The desktop endpoint caps the robustness audit at 30 folds and 2,000 candidate windows per fold. The UI applies these caps automatically even if the broader walk-forward controls are set higher.

## Limitations

- The sensitivity neighborhood is small and predeclared, not exhaustive.
- Query-window changes can shift the exact fold boundaries; configuration summaries are independent diagnostics, not a paired statistical experiment on identical timestamps.
- All configurations use the same historical dataset. This does not create a final independent holdout.
- A small-sample PBO-style CSCV diagnostic is additionally calculated only across baseline / fewer-analogs / more-analogs variants paired on identical query timestamps. It is conditional on those three correlated variants, not a comprehensive multiple-testing correction, statistical significance test, or probability of future loss.
- The same aligned analog-count variants receive pairwise return-correlation and equal-weight fold-return diagnostics. This is not a deployable portfolio or capital-allocation simulation.
- Query-window sensitivity configurations may use slightly different fold timestamps; they are not included in the paired PBO/portfolio diagnostics.
- No winning configuration is selected and the audit does not retune the model.
- Positive sensitivity results do not establish future profitability, execution quality or portfolio-level performance.
