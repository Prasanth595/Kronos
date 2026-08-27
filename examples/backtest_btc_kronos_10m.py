"""Backtest de seis meses de Kronos con velas BTCUSDT de 10 minutos."""

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

from backtest_btc_kronos_4h import (
    Config,
    calculate_metrics,
    load_predictor,
    save_outputs,
    simulate,
    walk_forward_predictions,
)

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "btc_10m_backtest"
BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"


def download_binance_10m(months: int, lookback: int) -> tuple[pd.DataFrame, pd.Timestamp]:
    now = pd.Timestamp.now(tz="UTC").floor("5min")
    test_start_requested = now - pd.DateOffset(months=months)
    download_start = test_start_requested - pd.Timedelta(minutes=10 * (lookback + 20))
    start_ms = int(download_start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000) - 1
    rows: list[list[object]] = []
    session = requests.Session()

    print(
        f"📥 Descargando BTCUSDT 5m desde Binance: "
        f"{download_start:%Y-%m-%d} → {now:%Y-%m-%d}..."
    )
    while start_ms <= end_ms:
        response = session.get(
            BINANCE_URL,
            params={
                "symbol": "BTCUSDT",
                "interval": "5m",
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": 1000,
            },
            timeout=30,
        )
        if response.status_code in (418, 429):
            wait_seconds = int(response.headers.get("Retry-After", "5"))
            print(f"   Límite de Binance; esperando {wait_seconds}s...")
            time.sleep(wait_seconds)
            continue
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows.extend(batch)
        next_start = int(batch[-1][0]) + 5 * 60 * 1000
        if next_start <= start_ms:
            raise RuntimeError("Binance no avanzó el cursor de descarga.")
        start_ms = next_start
        print(f"   {len(rows):,} velas 5m", end="\r", flush=True)
    print()
    if not rows:
        raise RuntimeError("Binance no devolvió velas BTCUSDT.")

    frame = pd.DataFrame(
        rows,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "amount", "trades", "taker_base", "taker_quote", "ignore",
        ],
    )
    frame["timestamps"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    for column in ("open", "high", "low", "close", "volume", "amount"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame = frame.set_index("timestamps")
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    bars = frame.resample("10min", origin="epoch").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "amount": "sum"}
    )
    bars = bars.dropna()
    # Exige las dos velas de 5m para no aceptar barras parciales o huecos.
    counts = frame["close"].resample("10min", origin="epoch").count()
    bars = bars.loc[counts[counts == 2].index.intersection(bars.index)]
    test_position = int(bars.index.searchsorted(test_start_requested))
    if test_position < lookback:
        raise RuntimeError(f"Contexto insuficiente: {test_position} velas; se requieren {lookback}.")
    test_start = bars.index[test_position]
    print(f"✅ {len(bars):,} velas 10m completas; backtest desde {test_start}.")
    return bars, test_start


def main() -> int:
    config = Config(
        ticker="BTCUSDT",
        timeframe="10m",
        months=6,
        initial_bank=10_000.0,
        threshold=0.005,
        leverage=10.0,
        base_margin_fraction=0.05,
        fee_rate=0.001,
        slippage_rate=0.0002,
        stop_liquidation_fraction=0.90,
        take_profit_roi=1.0,
        lookback=400,
        batch_size=16,
        seed=42,
    )
    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    bars, test_start = download_binance_10m(config.months, config.lookback)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    bars.to_csv(OUTPUT_DIR / "market_data_10m.csv")
    predictor = load_predictor(config)
    predictions = walk_forward_predictions(bars, test_start, predictor, config)
    trades, equity_curve = simulate(predictions, config)
    metrics = calculate_metrics(predictions, trades, equity_curve, config)
    save_outputs(predictions, trades, equity_curve, metrics, config, OUTPUT_DIR)

    print("\n✅ Backtest 10m terminado")
    print(f"   Periodo: {metrics['test_start']} → {metrics['test_end']}")
    print(f"   Banca: ${metrics['initial_bank']:,.2f} → ${metrics['final_equity']:,.2f}")
    print(f"   Rentabilidad: {metrics['total_return_pct']:.2f}%")
    print(f"   Buy & hold: {metrics['buy_hold_return_pct']:.2f}%")
    print(f"   Drawdown máximo: {metrics['max_drawdown_pct']:.2f}%")
    print(f"   Operaciones: {metrics['trades']} | Acierto: {metrics['win_rate_pct']:.2f}%")
    print(f"   Liquidaciones: {metrics['liquidations']} | Comisiones: ${metrics['fees_paid']:,.2f}")
    print(f"   Resultados: {OUTPUT_DIR.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
