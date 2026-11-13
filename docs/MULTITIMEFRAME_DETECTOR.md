# Multi-Timeframe BTC Setup Detector

Module: `backend/app/research/multitimeframe_detector.py`

Detects the conjunction previously specified for BTC:
1. 15m long lower wick.
2. 4h sweep below prior rolling support followed by a close back above support.
3. 1d unusually large bearish body, relative to the median absolute daily body over a trailing window, during a broader decline.

## Definitions

All thresholds are explicit parameters in `MultiTimeframeConfig`. Initial defaults are research starting points, not fitted or validated trading thresholds. The 15m wick is measured as a fraction of total candle range and relative to body size. The 4h support is the minimum low of the preceding 20 completed 4h bars, excluding the current bar. Daily body size is compared with the median absolute body return over the preceding 60 daily bars. Broader decline is measured over 20 daily bars.

A 15m candle is associated with the 4h and daily candles whose open/close interval contains its timestamp. Inputs must be complete, validated, chronologically contiguous candles on all three timeframes, and the same symbol. No resampling, gap filling, data download, or use of unfinished candles occurs here.

## Interpretation and limitations

The detector returns timestamped observations and measurements only. It does not claim a reversal, assign probabilities, or issue LONG/SHORT/SIDEWAYS signals. A large red daily candle is evaluated from the supplied daily OHLC; because a daily candle is only final after its close, historical event timestamps must be interpreted with that availability time. For live use, the daily condition cannot be considered confirmed until the daily candle closes.

Before broad history testing, thresholds must be frozen in a training period and assessed on chronological, purged/embargoed validation and test periods. Report raw event counts, overlaps, forward outcome distributions, regime splits, and costs. Compare against simple baseline events and test sensitivity to parameter changes.
