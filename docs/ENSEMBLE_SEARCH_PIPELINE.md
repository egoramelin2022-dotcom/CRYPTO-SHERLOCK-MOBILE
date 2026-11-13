# Ensemble Search Pipeline

Module: `backend/app/research/ensemble_pipeline.py`

The pipeline is the first end-to-end, read-only coordinator for the two
historical candidate discovery engines.

## Execution sequence

1. Validate the supplied closed-candle series and query bounds through
   Pattern Intelligence's canonical validation.
2. Run Pattern Intelligence in either `free` or `five_stage` mode.
3. Optionally run STUMPY MASS on per-candle log body returns.
4. Restrict STUMPY history to the prefix ending at least the maximum forward
   horizon before the query begins.
5. Convert both engines' candidates to the common evidence contract.
6. Group exact candidate windows and count distinct supporting modules.
7. Only after candidate discovery is frozen, evaluate forward paths using
   next-candle-open entry, configured fees and slippage.

## Output and limitations

The result contains module candidate counts, evidence count, exact-window
consensus, and cost-adjusted LONG/SHORT forward outcome metrics. It does not
average engine similarity scores, infer SIDEWAYS labels, calibrate
probabilities, forecast, or emit trading signals. STUMPY is optional and is
not imported until explicitly enabled by the caller.

Candidate forward paths are guaranteed not to overlap the query window when
the configured maximum horizon is respected by the Pattern Intelligence
embargo. The full candle series must contain only closed candles and must be
contiguous; missing intervals invalidate the run.
