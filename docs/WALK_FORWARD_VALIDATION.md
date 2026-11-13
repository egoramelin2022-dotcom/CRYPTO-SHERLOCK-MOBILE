# Walk-Forward Fold Construction

Module: `backend/app/research/walk_forward.py`

This module builds expanding chronological train/validation index ranges. It
does not fit models or evaluate outcomes.

## Leakage controls

- Ranges are half-open and strictly chronological.
- The first fold retains the requested number of usable training observations.
- A purge gap of `max_horizon` bars prevents training labels from reaching
  into the validation period.
- An additional configurable embargo separates training labels from validation.
- Validation windows are spaced so their maximum-horizon forward outcome
  windows do not overlap.
- Incomplete final validation windows are omitted rather than shortened.

The default step is `validation_size + max_horizon + embargo_bars`. A smaller
step is rejected because it would permit overlapping validation outcome
windows. The splitter is intentionally conservative; later evaluation must
still freeze feature transforms and candidate selection within each fold,
report per-fold sample counts, and compare against baselines.

## Important limitation

A fold is an index schedule, not proof against every form of leakage. Callers
must map indices to chronological, gap-audited candle data and ensure every
training label is fully observable before the corresponding validation start.
