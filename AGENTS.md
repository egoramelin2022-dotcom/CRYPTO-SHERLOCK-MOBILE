# CRYPTO SHERLOCK — AI Agent Collaboration Rules

This repository is a shared workspace for ChatGPT, OpenAI Codex, Gemini in Android Studio, and human review.

## Product priorities
1. Stability and correct startup on real Android devices come before new features.
2. Do not claim device validation unless the app was actually installed and exercised on a physical device.
3. Keep the app responsive: network, SQLite scans, downloads, and pattern searches must not block the main/UI thread.
4. Show clear progress, cancellation, retry, and error states for long-running work.
5. Never add real-money order execution without a separate explicit design, user approval, risk controls, and extensive paper-trading validation.

## Core product requirements
- Android app, package `com.cryptosherlock.mobile`.
- Binance Spot BTCUSDT market data and local historical OHLCV storage.
- Pattern Intelligence is the general-purpose historical analogue search; it must not be constrained to the five-stage pattern.
- Five-Stage Strategy remains a separate optional strategy and must never be deleted or silently merged into Pattern Intelligence.
- Preserve multi-timeframe research goals and historical backtesting without lookahead bias.
- Avoid presenting heuristic signals as guaranteed predictions or financial advice.

## Agent workflow
Before editing:
1. Read this file and the relevant source files.
2. Inspect the current Git diff and recent commits.
3. State the concrete problem, files likely affected, and validation plan.
4. Avoid broad rewrites when a focused fix is sufficient.

While editing:
1. Make one logically cohesive change per commit or pull request.
2. Do not overwrite another agent's work; re-read files before writing if the branch changed.
3. Preserve existing working functionality and the separate Five-Stage Strategy.
4. Add or update tests for changed analytical logic.
5. Keep secrets, API keys, signing keys, and personal data out of the repository.

Before handing off:
1. Run the relevant unit tests and `./gradlew assembleDebug` (or the Windows equivalent `gradlew.bat assembleDebug`).
2. Report the exact commit SHA, changed files, tests/build result, and any unverified assumptions.
3. If the emulator or physical device was used, report device/API level and the actual checks performed.
4. Do not mark a task complete if build/test failed or was not run; state the blocker.

## Collaboration handoff format
Every agent handoff must include:
- Goal:
- Findings:
- Changes:
- Commit/branch:
- Build and tests:
- Device verification:
- Risks / next step:

## Ownership and conflict prevention
- Use a separate Git branch for substantial work; do not have multiple agents edit the same files concurrently.
- Prefer pull requests for agent changes so another agent can review before merge.
- One agent owns a task at a time. Other agents may review, write tests in separate files, or inspect logs without modifying the same files.
- The human owner approves merges and any release APK installation.
