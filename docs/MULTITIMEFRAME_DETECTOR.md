# Multi-Timeframe BTC Setup Detector

Module: `backend/app/research/multitimeframe_detector.py`

Detects the conjunction previously specified for BTC:
1. 15m long lower wick.
2. 4h sweep below prior rolling support followed by a close back above support.
3. 1d unusually large bearish body, relative to the median absolute daily body over a trailing window, during a broader decline.

## Definitions

All thresholds are explicit parameters in `MultiTimeframeConfig`. Initial defaults are research starting points, not fitted or validated trading thresholds. The 15m wick is measured as a fraction of total candle range and relative to body size. The 4h support is the minimum low of the preceding 20 completed 4h bars, excluding the current bar. Daily body size must exceed both the median absolute body return over the preceding 60 daily bars multiplied by `daily_body_multiple_of_median` and the absolute floor `daily_body_min_return` (default 2%). The floor prevents a zero or near-zero historical median from allowing an ordinary red candle to pass as unusually large. Broader decline is measured over 20 daily bars.

The emitted event timestamp is the 15m candle's `close_time`, when the wick is confirmed. A 15m event may use only 4h and daily candles whose `close_time` is no later than the 15m candle's `close_time`. This is essential: using the 4h or daily candle that merely contains the 15m timestamp would leak its future close/high/low into the historical event. The three timeframes may close simultaneously at a boundary, but an unfinished higher-timeframe candle is never visible. Inputs must be complete, validated, chronologically contiguous candles on all three timeframes, and the same symbol. No resampling, gap filling, or data download occurs here.

## Interpretation and limitations

The detector returns timestamped observations and measurements only. It does not claim a reversal, assign probabilities, or issue LONG/SHORT/SIDEWAYS signals. A large red daily candle is evaluated from the supplied daily OHLC; because a daily candle is only final after its close, historical event timestamps must be interpreted with that availability time. For live use, the daily condition cannot be considered confirmed until the daily candle closes; the detector enforces that timing rule.

Before broad history testing, thresholds must be frozen in a training period and assessed on chronological, purged/embargoed validation and test periods. Report raw event counts, overlaps, forward outcome distributions, regime splits, and costs. Compare against simple baseline events and test sensitivity to parameter changes.
