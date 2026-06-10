# Kronos cTrader Extension Architecture

This repository treats the original Kronos code as upstream core. The extension
layer lives outside `model/`, `examples/`, `finetune/`, `finetune_csv/`,
`tests/`, and `webui/` so upstream changes can be pulled with fewer conflicts.

## Boundary

The extension boundary is:

1. cTrader-like market data is mapped into normalized OHLCV pandas DataFrames.
2. Local validation checks the columns and null safety expected by Kronos.
3. A future inference adapter receives an already constructed upstream
   `KronosPredictor` and calls it through its public API.
4. Forecast DataFrames are passed to a separate signal layer.
5. Signal output remains advisory data only. This scaffold contains no live
   trading, order placement, credentials, API keys, model downloads, or network
   calls.

## Why Kronos Core Remains Untouched

The upstream Kronos package already exposes the public classes needed for
forecasting through `from model import Kronos, KronosTokenizer, KronosPredictor`.
Changing core files would make future upstream merges harder and could blur
responsibility between model behavior and integration behavior.

Keeping cTrader mapping, local workflow orchestration, signal rules, storage,
and command-line entry points in `kronos_ext/` lets this fork evolve user-facing
tooling while preserving Kronos model code as a stable dependency.

## Current State

This is a scaffold only. All broker connectivity and model loading are
placeholders by design. The next safe step is to add offline fixtures for
cTrader-like candle payloads and strengthen the mapper/validation tests before
any real API client is introduced.
