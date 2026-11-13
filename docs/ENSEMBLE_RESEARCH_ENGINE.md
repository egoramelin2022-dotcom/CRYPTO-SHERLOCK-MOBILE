# Ensemble Research Engine — Evidence Contract v0.1

Status: initial dependency-free evidence layer  
Branch: `ensemble-research-engine-v0.1.0`  
Policy: research / backtest / paper trading only; no live order execution.

## Purpose

Normalize observations from independent research modules without turning
similarity scores into a false probability or a trading decision. The first
implementation groups exact historical candidate windows and reports which
modules independently found each window.

## Contract

Each `ResearchEvidence` row records:
- module and algorithm version;
- feature set and timeframe;
- query start/end timestamps;
- historical candidate start/end timestamps;
- within-module rank and similarity in [0, 1];
- provenance identifying the producing run or fixture.

A candidate must end strictly before the query begins. All rows in one report
must refer to the same query interval and timeframe. Duplicate reports from
the same module for the same candidate are rejected.

## Important interpretation

- `module_count` is a count of distinct modules, **not** independent
  statistical confirmation. Modules may be correlated.
- Similarity values are not averaged because different algorithms have
  different score distributions and normalization.
- `mean_rank` is descriptive ordering metadata, not a probability.
- The report contains no forward outcomes, expected return, LONG/SHORT label,
  or trading signal.
- Candidate matching uses exact timestamp boundaries in this first version.
  Fuzzy temporal matching is deferred until a deterministic tolerance policy
  and tests exist.

## Next validation stage

1. Build adapters that emit this contract from Pattern Intelligence and STUMPY.
2. Persist immutable run metadata and candidate evidence in the analytics DB.
3. Add an outcome evaluator that runs only after candidate discovery is frozen.
4. Compare each module, pairwise combinations, full ensemble, and leave-one-out
   ablations on chronological walk-forward folds.
5. Use purging/embargo for overlapping outcome horizons and charge fees,
   slippage and funding where applicable.
6. Report uncertainty, sample counts, regime splits and multiple-testing risk.
7. Promote no ensemble unless it improves on transparent baselines on unseen
   data and remains robust across folds.

This module is an evidence plumbing primitive, not proof of an edge.
