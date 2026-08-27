"""Genera predicciones walk-forward 4h de tres años y tres semillas Kronos."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

if os.environ.get("HSA_OVERRIDE_GFX_VERSION") == "11.0.0":
    os.environ.pop("HSA_OVERRIDE_GFX_VERSION")

import numpy as np
import pandas as pd
import requests
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, EXAMPLES_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from backtest_btc_kronos_4h import Config, load_predictor, walk_forward_predictions

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "kronos_research_4h_3y"
BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"
SEEDS = (42, 43, 44)


def download_4h(years: int, lookback: int) -> tuple[pd.DataFrame, pd.Timestamp]:
    now = pd.Timestamp.now(tz="UTC").floor("4h")
    test_start_requested = now - pd.DateOffset(years=years)
    download_start = test_start_requested - pd.Timedelta(hours=4 * (lookback + 10))
    cursor = int(download_start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000) - 1
    rows: list[list[object]] = []
    session = requests.Session()
    print(f"📥 Descargando BTCUSDT 4h: {download_start:%Y-%m-%d} → {now:%Y-%m-%d}...")
    while cursor <= end_ms:
        response = session.get(
            BINANCE_URL,
            params={"symbol": "BTCUSDT", "interval": "4h", "startTime": cursor, "endTime": end_ms, "limit": 1000},
            timeout=30,
        )
        if response.status_code in (418, 429):
            time.sleep(int(response.headers.get("Retry-After", "5")))
            continue
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows.extend(batch)
        cursor = int(batch[-1][0]) + 4 * 60 * 60 * 1000
        print(f"   {len(rows):,} velas", end="\r", flush=True)
    print()
    frame = pd.DataFrame(
        rows,
        columns=["open_time", "open", "high", "low", "close", "volume", "close_time", "amount", "trades", "taker_base", "taker_quote", "ignore"],
    )
    frame["timestamps"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    for column in ("open", "high", "low", "close", "volume", "amount"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    bars = frame.set_index("timestamps")[["open", "high", "low", "close", "volume", "amount"]]
    bars = bars[~bars.index.duplicated(keep="last")].dropna().sort_index()
    start_position = int(bars.index.searchsorted(test_start_requested))
    if start_position < lookback:
        raise RuntimeError("No hay contexto suficiente antes del periodo de investigación.")
    return bars, bars.index[start_position]


def main() -> int:
    config = Config(
        ticker="BTCUSDT",
        timeframe="4h",
        months=36,
        initial_bank=10_000.0,
        threshold=0.0,
        leverage=1.0,
        base_margin_fraction=1.0,
        fee_rate=0.001,
        slippage_rate=0.0002,
        lookback=400,
        batch_size=16,
    )
    bars, test_start = download_4h(3, config.lookback)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    bars.to_csv(OUTPUT_DIR / "market_data_4h.csv")
    predictor = load_predictor(config)
    seed_frames: list[pd.DataFrame] = []
    for seed in SEEDS:
        output = OUTPUT_DIR / f"predictions_seed_{seed}.csv"
        if output.exists():
            existing = pd.read_csv(output)
            expected = len(bars) - int(bars.index.get_loc(test_start)) - 1
            if len(existing) == expected:
                print(f"✅ Semilla {seed} ya completa; reutilizando {len(existing):,} filas.")
                seed_frames.append(existing)
                continue
        print(f"\n🎲 Semilla {seed}")
        np.random.seed(seed)
        torch.manual_seed(seed)
        predicted = walk_forward_predictions(bars, test_start, predictor, config)
        predicted.to_csv(output, index=False)
        seed_frames.append(predicted)

    base_columns = ["decision_time", "exit_time", "entry", "next_open", "next_high", "next_low", "exit"]
    ensemble = seed_frames[0][base_columns].copy()
    predicted_returns: list[str] = []
    for seed, frame in zip(SEEDS, seed_frames, strict=True):
        column = f"predicted_return_seed_{seed}"
        ensemble[column] = frame["predicted_return"].to_numpy()
        predicted_returns.append(column)
    ensemble["predicted_return_mean"] = ensemble[predicted_returns].mean(axis=1)
    ensemble["predicted_return_std"] = ensemble[predicted_returns].std(axis=1)
    ensemble["actual_return"] = ensemble["exit"] / ensemble["entry"] - 1.0
    ensemble.to_csv(OUTPUT_DIR / "ensemble_predictions.csv", index=False)
    print(f"\n✅ Dataset ensemble: {len(ensemble):,} predicciones en {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
