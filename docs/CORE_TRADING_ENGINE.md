# CRYPTO SHERLOCK — Core Trading Engine

## Product vision
The core of CRYPTO SHERLOCK is the user's research hypothesis: recurring and analogous candle/price-action structures. The system must discover, compare, measure, and continuously evaluate these structures rather than replace them with a generic indicator dashboard.

## Analytical layers
1. **Pattern intelligence (primary layer)**
   - Discover recurring candle sequences and price-action analogues across historical data.
   - Preserve the user's original five-stage formation as a separate selectable strategy.
   - Compare analogues by candle geometry, returns, volatility, volume, liquidity context, and multi-timeframe structure.
   - Search freely for recurring structures; do not force every candidate into the five-stage template.
   - Detect similar market regimes and compare what happened after the analogue points.

2. **Technical analysis**
   - Combine trend, momentum, volatility, volume, market structure, support/resistance, liquidity sweeps, breakouts/retests, and multi-timeframe confluence.
   - Indicators are supporting evidence, not standalone trade triggers.
   - Avoid indicator duplication and correlated-feature double counting.

3. **News and event context**
   - Collect timestamped, source-attributed news and macro/market events.
   - Compare current events with historical periods that had similar event types and market conditions.
   - Measure price/volatility/volume response over defined windows after events.
   - Distinguish confirmed facts, market commentary, and unverified claims.

4. **Whole-market context**
   - Assess BTC, ETH, total market direction, breadth, dominance, sector/altcoin relative strength, volatility, liquidity, funding/open interest where reliable, and major macro events.
   - Determine whether the instrument's setup agrees with or conflicts with the broader market.

5. **Probabilistic forecast and live state**
   - Continuously estimate three mutually exclusive near-term scenarios: LONG/up, SHORT/down, and SIDEWAYS.
   - Display probabilities that sum to 100%, a forecast horizon, confidence/calibration status, supporting evidence, and key uncertainties.
   - Keep a continuously updated entry assessment: WAIT, ENTRY WINDOW, ACTIVE SETUP, or INVALIDATED.
   - When an entry window is active, show a proposed entry zone, confirmation conditions, invalidation level, risk/reward estimate, and what would change the scenario.
   - Update as new candles, volume, market context, or news arrive; show the timestamp and data freshness.
   - A directional probability is not a guarantee and must not be presented as certainty.

## Validation and safeguards
- Prevent lookahead/data leakage: only information available at forecast time may be used.
- Backtest with realistic fees, slippage, funding where applicable, and execution delay.
- Use chronological train/validation/test splits and walk-forward testing.
- De-duplicate overlapping historical analogues and report sample size.
- Calibrate probabilities and show reliability/Brier score or equivalent metrics where sample size permits.
- Track every forecast as an immutable timestamped record; later score it against actual market movement and report accuracy by horizon and regime.
- Separate historical backtest, paper trading, and live execution.
- No automatic real-money orders in the initial product. Paper trading and user-confirmed execution must come first, with explicit risk limits.

## User-facing output
At a glance, the main screen should answer:
- What is the market doing now?
- Which historical patterns and event analogues resemble the current state?
- What do technical indicators and broader market context confirm or contradict?
- What are the current LONG / SHORT / SIDEWAYS probabilities and over what horizon?
- Is there an active entry window now? If yes, what are the entry, confirmation, invalidation, and risk parameters?
- What changed since the previous update, and how did previous forecasts perform?

## Implementation priority
Stability and trustworthy data first; then historical pattern engine and forecast logging; then technical and market context; then timestamped news/event analogues; then calibrated live probability and entry-state updates. Do not advertise a feature as real-time until data refresh, latency, and stale-data handling are implemented and measured.
