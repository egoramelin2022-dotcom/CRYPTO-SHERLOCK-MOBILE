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
7. Run leave-one-module-out ablations to measure how removing each engine
   changes the exact-window candidate set.
8. Only after candidate discovery is frozen, evaluate forward paths using
   next-candle-open entry, configured fees and slippage.
9. Aggregate available outcomes by horizon: cost-adjusted LONG/SHORT positive
   rates, mean/median net returns, excursion statistics, and an explicit
   retrospective SIDEWAYS rate.

## Output and limitations

The result contains module candidate counts, evidence count, exact-window
consensus, leave-one-module-out discovery impact, and cost-adjusted LONG/SHORT
forward outcome metrics. Ablations describe candidate-set changes only; they
do not establish that a module adds predictive value. It does not
average engine similarity scores, infer SIDEWAYS labels, calibrate
probabilities, forecast, or emit trading signals. STUMPY is optional and is
not imported until explicitly enabled by the caller.

Candidate forward paths are guaranteed not to overlap the query window when
the configured maximum horizon is respected by the Pattern Intelligence
embargo. The full candle series must contain only closed candles and must be
contiguous; missing intervals invalidate the run.

## Local API job

The FastAPI gateway exposes `POST /v1/research/ensemble`. It accepts
`symbol`, `interval`, `window`, `top_k`, `mode` (`free` or
`five_stage`), and `include_stumpy`, `fee_bps_per_side`, and `slippage_bps_per_side`. Fee and slippage inputs are proportional basis-point assumptions charged on both entry and exit; they are not inferred from an exchange account or fee tier. The endpoint returns a queued job ID;
poll `GET /v1/research/jobs/{job_id}` for completion.

The job reads `SHERLOCK_SOURCE_DB` in SQLite read-only mode and writes the
serialized result to the separate `SHERLOCK_ANALYTICS_DB` table
`research_ensemble_runs`. It filters unfinished candles and searches only
the latest contiguous segment. Earlier segments separated by gaps are
reported as excluded; they are never silently concatenated or gap-filled.
STUMPY remains opt-in because it is an optional research dependency.
