# Matcher-to-Ensemble Adapters

The first real bridge from the existing matchers into the common evidence
contract is implemented in `backend/app/research/evidence_adapters.py`.

## Pattern Intelligence adapter
`pattern_search_evidence(result, candles)` uses the matcher's original
candidate indices and verifies that the supplied candle timestamps agree with
the timestamps recorded in each analogue. It retains the Pattern Intelligence
similarity score and records the query/candidate candle-open times.

## STUMPY adapter
`stumpy_matches_evidence(...)` maps MASS match offsets into the supplied
historical timestamp vector. It verifies:
- timestamp values are integer milliseconds;
- both history and query are contiguous at the requested interval;
- history ends strictly before the query begins;
- every match window fits within the history vector.

STUMPY distance is converted to a bounded monotonic descriptor
`1 / (1 + distance)`. This is only a common [0, 1] field constraint, not a
calibration and not comparable to Pattern Intelligence similarity.

## Known boundary
The adapter does not fetch data, infer missing candles, calculate outcomes,
or persist results. The caller owns feature generation, exact closed-candle
selection, and provenance/run identifiers. This is intentional: adapters
must not conceal data gaps or future leakage.
