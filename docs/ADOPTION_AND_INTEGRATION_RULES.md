# CRYPTO SHERLOCK — Adoption & Integration Rules

## Goal
Build a research-first crypto market intelligence system by reusing proven open-source algorithms where appropriate, while retaining Sherlock's own architecture, data contracts, validation rules and product behavior.

## Non-negotiable constraints
- Research, backtesting and paper trading only. No live order execution.
- Original market databases and CSV archives are immutable inputs.
- Derived features, motifs, experiments, model artifacts and paper-trading state are stored separately.
- No look-ahead leakage; every feature must be available at the decision timestamp.
- Chronological validation, walk-forward, purge/embargo for overlapping labels.
- Include fees, slippage and funding where relevant.
- Separate LONG, SHORT and SIDEWAYS outcomes.
- No model promotion without independent evaluation against a baseline.
- CPU-first and bounded memory/runtime for the i5-2400 / 16 GB target.
- Preserve free-form Pattern Intelligence and the separately switchable Five-Stage Strategy.

## External component boundary
Every third-party algorithm sits behind a Sherlock-owned interface. External libraries may calculate candidate motifs, distances or backtest comparisons; Sherlock owns:
- timestamp alignment and point-in-time feature generation;
- normalization policy and query definitions;
- candidate filtering and non-overlap rules;
- forward outcome measurement;
- leakage-safe validation;
- confidence / uncertainty reporting;
- experiment registry and promotion gates;
- API and Android presentation contracts.

## Pattern Intelligence contract (target)
Input: symbol, exchange, timeframe(s), query interval, feature set, normalization mode, allowed window lengths, search history range, max results and exclusion-zone policy.

Output per candidate:
- query and match start/end timestamps;
- similarity distance and ranking method;
- feature dimensions used;
- window length and timeframe;
- data-quality status;
- forward returns / MFE / MAE at predeclared horizons;
- outcome label and uncertainty;
- whether candidate overlaps another match;
- algorithm and configuration version.

The matcher must not inspect future outcomes. Outcome analysis is a separate downstream stage and may only read candles after the matched interval.

## Five-Stage Strategy
Remain an optional named strategy. The five stages are:
1. preliminary decline;
2. recovery;
3. peak;
4. sharp collapse;
5. sideways movement with lower wicks.

Equal weighting is retained as the initial hypothesis, not treated as proof of semantic recognition. The current equal-sized chunk implementation is a placeholder and must not be represented as a validated semantic detector.

## External code intake checklist
Before code is imported:
- repository and commit pinned;
- license and notices checked;
- dependencies and transitive dependencies reviewed;
- security and maintenance status reviewed;
- source provenance documented;
- tests adapted and added;
- performance benchmarked on target hardware;
- no live-trading path accidentally enabled.

## Decision process
Use an adapter first. Prefer dependency reuse over copying. If source adaptation is required, preserve notices and record modifications. A component can be rejected after benchmark even if popular or feature-rich.

## Current first candidate
STUMPY is the first candidate for a bounded Pattern Intelligence prototype because its Matrix Profile supports motif discovery, anomaly discovery, multidimensional motifs and window-size exploration. It is not a forecasting model and does not validate profitability by itself.
