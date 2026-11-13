# Research Memory & Experiment Ledger

## Purpose

The ledger preserves the history of Sherlock Intelligence Core executions so that later research can distinguish a genuinely new experiment from a rerun with different parameters or different market data. It does not adapt model weights or declare a strategy successful.

## Recorded for each Core run

- UUID run identifier and Core/schema versions;
- symbol, interval, exact query time range and search mode;
- all search, horizon and execution-cost parameters;
- SHA-256 fingerprint of the complete ordered candle input;
- input candle count;
- full immutable Core result and its SHA-256 digest;
- append-only lifecycle events: started, completed or failed.

The input fingerprint covers symbol, interval, timestamps, OHLCV, quote volume, trade count and taker-buy fields. A changed candle changes the fingerprint. This supports reproducibility checks; it does not prove that an upstream data provider's original data was correct.

## Storage and integrity

Records are stored in the separate SHERLOCK_ANALYTICS_DB. The source market database remains read-only. Three SQLite tables hold run metadata, result JSON and lifecycle events. Update/delete triggers prevent ordinary application mutations. On an existing ledger, a missing trigger is reported rather than silently recreated, so opening the app cannot hide evidence that an integrity guard was removed. Each event includes the previous event hash and its own SHA-256 digest, forming a per-run chain.

GET /v1/research/experiments lists runs. GET /v1/research/experiments/{run_id} returns one full record. GET /v1/research/experiments/verify checks event chains and result digests.

A completed run contains both a result record and a completed event. Failed attempts retain a failed event and the exception class only; raw exception messages and local file paths are intentionally not persisted. An interrupted process can leave a run in started, which is visible and is not silently treated as a completed experiment.

## Important security boundary

This is tamper-evident application-level history, not a cryptographic signature or external timestamp authority. A person with direct write access to the SQLite file can bypass SQLite triggers and could rewrite the database and recompute hashes. For stronger audit guarantees, a later version can periodically export signed checkpoints to a separate trusted location.

## Desktop workflow

Open Experiment Ledger in the Windows application and refresh history. Select a run to inspect its parameters, result, input fingerprint and event chain. Use Verify Ledger Integrity to audit the currently stored records. The panel is read-only: new research adds records; existing records are not edited or deleted through the application.

## Current scope

Version 1 records Sherlock Core runs and their failed attempts. It does not yet link walk-forward, robustness, MTF or ensemble jobs as child experiments, nor does it automatically compare strategy versions. Those integrations should use explicit parent/child run IDs and preserve the exact validation folds and holdout boundaries rather than overwriting an earlier record.
