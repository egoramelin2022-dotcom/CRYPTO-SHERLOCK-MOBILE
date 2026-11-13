# CRYPTO SHERLOCK — Open-Source Research & Adoption Matrix

Status: research baseline v0.1.0  
Date: 2026-11-13  
Branch: research-adoption-v0.1.0  
Policy: research / backtest / paper trading only. No live order execution.

This document records candidate upstream projects and a conservative adoption decision. Popularity is not proof of suitability. Every component must pass local benchmarks, correctness tests, license review and integration tests before entering the production path.

## 1. Candidate shortlist

| Project | What it offers | Potential use in Sherlock | Decision |
|---|---|---|---|
| [STUMPY](https://github.com/stumpy-dev/stumpy) | Matrix Profile; motif/discord discovery, semantic segmentation, streaming, multidimensional motifs, pan-profile window selection | Free-form Pattern Intelligence and variable-window discovery | **Prototype first** |
| [Freqtrade](https://github.com/freqtrade/freqtrade) | Exchange data handling, strategy interface, backtesting, hyperopt, dry-run, FreqAI | Reference for data workflows, validation warnings and reporting | **Study; do not embed whole bot** |
| [Jesse](https://github.com/jesse-ai/jesse) | Strategy research, multi-timeframe workflows, backtesting and optimization | Compare research workflow and reporting concepts | **Study selectively** |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | Event-driven market-data/trading engine, backtester, portfolio/risk primitives | Future reference if event simulation becomes a bottleneck | **Defer; too heavy for current CPU-first stage** |
| [vectorbt](https://github.com/polakowo/vectorbt) | Vectorized research/backtesting and parameter sweeps | Fast exploratory baselines and sensitivity studies | **Prototype as optional research dependency** |
| [backtesting.py](https://github.com/kernc/backtesting.py) | Compact single-instrument backtesting framework | Transparent baseline / independent cross-check | **Reference, not core** |
| [PyBroker](https://github.com/edtechre/pybroker) | Python backtesting and ML-oriented strategy research | Compare ML workflow and walk-forward facilities | **Study selectively** |
| [tslearn](https://github.com/tslearn-team/tslearn) | Time-series ML, DTW and shape-based distances | Alignment-tolerant similarity comparison | **Prototype after STUMPY baseline** |
| [aeon](https://github.com/aeon-toolkit/aeon) | Time-series classification, clustering, regression and distance tools | Shapelets / time-series clustering experiments | **Research backlog** |

## 2. First implementation choices

### Pattern Intelligence
Start with STUMPY as an optional, isolated research adapter. Do not make the entire backend depend on it yet.

Initial experiments:
1. Univariate close-return motif search.
2. Multidimensional candle representation: normalized body, upper wick, lower wick, range, volume change and volatility.
3. Variable subsequence lengths using a controlled window bank first; evaluate pan-profile functionality separately.
4. Exclusion zones and non-overlap rules so adjacent windows are not counted as independent analogues.
5. Query-to-history matching with explicit normalization policy.
6. Out-of-sample forward outcome analysis only after matching windows are fixed.

### Backtesting and validation
Keep our own point-in-time dataset contract and leakage controls. External frameworks may be independent comparators, not authorities.

Required controls:
- Chronological train / validation / test.
- Walk-forward evaluation.
- Purge and embargo for overlapping forward outcome horizons.
- No feature values computed using future candles.
- Fees, slippage and funding assumptions explicit.
- Baseline comparisons and uncertainty intervals.
- Long, short and sideways outcomes evaluated separately.
- Record all tried configurations to expose multiple-testing and selection bias.

### Market data
Continue using our read-only SQLite source and existing Binance data path. No third-party project may rewrite or migrate the source database. Imported data must pass our validator and be stored in a derived dataset or staging area.

## 3. License and code-reuse policy

We will not copy code without review. Before adapting any source file:
1. Record repository URL, exact commit SHA and file path.
2. Record the license at that exact revision and any file-level headers.
3. Check whether the license permits modification and redistribution in our intended distribution model.
4. Preserve copyright and license notices; include required attribution and license text.
5. Add an entry to THIRD_PARTY_NOTICES.md with provenance and modifications.
6. Prefer dependency installation or a small adapter over copying large source modules.
7. Do not copy code from repositories with missing, unclear or incompatible licensing.

No source code has been copied into Sherlock as part of this research-baseline commit.

## 4. Hardware and runtime constraints

Target workstation: Intel i5-2400, 16 GB RAM, Windows 10. CPU-first; GPU is not assumed.

Benchmark requirements:
- Test on a representative sample first, not the full 2017–present history.
- Record wall time, peak memory, CPU utilization and output count.
- Bound candidate window lengths, dimensions and parallelism.
- Cache intermediate feature arrays outside the immutable source DB.
- Never run an unbounded all-pairs search on the home server.
- Use chunking / approximate methods only after measuring accuracy against exact results on small samples.

## 5. Acceptance gate

An algorithm is accepted only when:
- Unit tests cover indexing, timestamps, normalization and edge cases.
- Synthetic fixtures prove known motifs are found and unrelated motifs are not.
- Results are deterministic under fixed configuration.
- No future information enters matching features.
- Forward outcome evaluation is separate from the matcher.
- Runtime and memory fit the workstation budget.
- It complements or beats a simple baseline on an unseen period.
- Limitations and false-positive modes are documented.

## 6. Immediate experiment sequence

1. Inspect existing repository architecture and current data schemas.
2. Add a dependency-free motif-search interface and deterministic fixtures.
3. Prototype STUMPY in an optional research extra / isolated environment.
4. Benchmark short BTCUSDT 15m slices before full-history execution.
5. Compare STUMPY against normalized Euclidean sliding-window distance and a DTW baseline.
6. Evaluate historical forward paths without using them to select matches.
7. Decide whether STUMPY becomes the first production Pattern Intelligence backend.

## 7. Sources

- STUMPY docs: https://stumpy.readthedocs.io/en/latest/
- STUMPY repository: https://github.com/stumpy-dev/stumpy
- Freqtrade docs: https://www.freqtrade.io/en/stable/
- Freqtrade repository: https://github.com/freqtrade/freqtrade
- Jesse repository: https://github.com/jesse-ai/jesse
- NautilusTrader overview: https://nautilustrader.io/open-source/
- NautilusTrader repository: https://github.com/nautechsystems/nautilus_trader
- vectorbt repository: https://github.com/polakowo/vectorbt
- backtesting.py repository: https://github.com/kernc/backtesting.py
- PyBroker repository: https://github.com/edtechre/pybroker
- tslearn repository: https://github.com/tslearn-team/tslearn
- aeon repository: https://github.com/aeon-toolkit/aeon


## 8. STUMPY package pin and adapter status (verified 2026-11-13)

- Optional package pin: `stumpy==1.14.1`.
- PyPI metadata reports BSD-3-Clause and Python >=3.10; the release page lists NumPy, SciPy and Numba dependencies.
- The 1.14.1 release notes include compatibility fixes for newer NumPy and Numba versions.
- The package is **not** in the core backend requirements. Install it only in an isolated research environment after reviewing the dependency tree and benchmarking.
- PyPI's release page reported no build provenance for the 1.14.1 wheel/source distribution at the time checked. This is not proof of maliciousness, but it means we should pin and verify the artifact/hash before distributing it.
- Sherlock now has a lazy optional adapter at `backend/app/research/stumpy_adapter.py`. It uses STUMPY MASS for query-to-history distance ranking, applies a non-overlap exclusion zone, and does not calculate forward outcomes.
- Adapter tests mock both NumPy and STUMPY, so the regular backend test suite does not require the optional scientific stack.

Sources:
- https://pypi.org/project/stumpy/
- https://github.com/stumpy-dev/stumpy/blob/main/CHANGELOG.md
- https://stumpy.readthedocs.io/en/stable/install.html

This is a prototype boundary, not a production approval. The actual STUMPY implementation still needs an isolated install test and benchmark on the target Windows machine.
