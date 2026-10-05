#!/usr/bin/env python3
"""
Prediction example using data downloaded directly from Yahoo Finance.

Instead of preparing a CSV, this script downloads the most recent candles for
any ticker covered by Yahoo Finance (stocks, ETFs, crypto, ...) via yfinance,
runs several independent Kronos predictions (sample_count=1 each), and plots
the 5-95% quantile band together with the median forecast path.

Usage:
    python prediction_yfinance.py [TICKER] [--interval 1h] [--pred-len 120] [--runs 20]

Examples:
    python prediction_yfinance.py BTC-USD
    python prediction_yfinance.py AAPL --interval 1d --runs 50
"""

import argparse
import os
import re
import sys
import time

import numpy as np
import pandas as pd
import torch

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yfinance as yf

# Make the repo root importable regardless of the working directory
# (this file lives in examples/, so the repo root is one level up)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from model import Kronos, KronosTokenizer, KronosPredictor  # noqa: E402

LOOKBACK = 400
MODEL_ID = "NeoQuasar/Kronos-small"
TOKENIZER_ID = "NeoQuasar/Kronos-Tokenizer-base"
COLS = ["open", "high", "low", "close", "volume", "amount"]


def pick_device() -> str:
    """'cuda:0' if CUDA is available, otherwise 'cpu'."""
    return "cuda:0" if torch.cuda.is_available() else "cpu"


def download_candles(ticker: str, interval: str, period: str, lookback: int) -> pd.DataFrame:
    print(f"Downloading last {lookback} {interval} candles for {ticker} (period={period}) via yfinance ...")
    raw = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
    if raw.empty:
        raise SystemExit(f"yfinance returned no data for {ticker} ({interval}/{period}).")
    df = raw.rename(columns=str.lower).dropna(subset=["open", "high", "low", "close", "volume"])
    if "amount" not in df.columns:
        # Yahoo does not provide turnover; approximate amount as close * volume
        df["amount"] = df["close"] * df["volume"]
    df = df[COLS].astype(float).tail(lookback)
    if len(df) < lookback:
        raise SystemExit(f"Only got {len(df)} candles, need {lookback}. Try a longer --period.")
    print(f"Got {len(df)} candles: {df.index[0]} -> {df.index[-1]}")
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description="Kronos probabilistic forecast from Yahoo Finance candles")
    ap.add_argument("ticker", nargs="?", default="BTC-USD", help="Yahoo Finance ticker (default: BTC-USD)")
    ap.add_argument("--interval", default="1h", help="Candle interval (default: 1h)")
    ap.add_argument("--period", default="30d", help="History window to fetch (default: 30d)")
    ap.add_argument("--pred-len", type=int, default=120, help="Forecast horizon in candles (default: 120)")
    ap.add_argument("--runs", type=int, default=20, help="Number of independent Kronos runs (default: 20)")
    ap.add_argument("--out", default=None, help="Output PNG path (default: prediction_<ticker>.png)")
    args = ap.parse_args()

    device = pick_device()
    print(f"Device: {device} (CUDA available: {torch.cuda.is_available()})")

    df = download_candles(args.ticker, args.interval, args.period, LOOKBACK)

    # Context timestamps + future timestamps on the same grid (Kronos expects Series with .dt)
    step = df.index.to_series().diff().median()
    x_timestamp = df.index.to_series()
    y_index = pd.date_range(start=df.index[-1] + step, periods=args.pred_len, freq=step)
    y_timestamp = y_index.to_series()

    print(f"Loading {MODEL_ID} + {TOKENIZER_ID} (HuggingFace download on first run) ...")
    t0 = time.time()
    tokenizer = KronosTokenizer.from_pretrained(TOKENIZER_ID)
    model = Kronos.from_pretrained(MODEL_ID)
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=512)
    print(f"Models loaded in {time.time() - t0:.1f}s")

    # Several independent stochastic runs, sample_count=1 each
    paths = []
    for i in range(1, args.runs + 1):
        t0 = time.time()
        pred_df = predictor.predict(
            df=df[COLS],
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=args.pred_len,
            T=1.0,
            top_p=0.9,
            sample_count=1,
            verbose=False,
        )
        paths.append(pred_df["close"].to_numpy(dtype=float))
        print(f"  run {i:2d}/{args.runs} done in {time.time() - t0:5.1f}s | "
              f"close[t+1]={paths[-1][0]:.2f} close[t+{args.pred_len}]={paths[-1][-1]:.2f}")

    stack = np.stack(paths)  # (runs, pred_len)
    p05, p50, p95 = np.quantile(stack, [0.05, 0.50, 0.95], axis=0)

    safe_ticker = re.sub(r"[^A-Za-z0-9._-]", "_", args.ticker)
    png_path = args.out or f"prediction_{safe_ticker}.png"
    csv_path = f"prediction_{safe_ticker}_quantiles.csv"
    pd.DataFrame({"timestamp": y_index, "p05": p05, "median": p50, "p95": p95}).to_csv(csv_path, index=False)

    # Plot: history, 5-95% band, median path (+ faint individual runs)
    hist_n = min(100, len(df))
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(df.index[-hist_n:], df["close"].tail(hist_n).to_numpy(), color="#222222", lw=1.4,
            label=f"Historical close (last {hist_n} candles)")
    ax.axvline(df.index[-1], color="#888888", ls="--", lw=1)
    for path in stack:
        ax.plot(y_index, path, color="tab:blue", lw=0.5, alpha=0.15)
    ax.fill_between(y_index, p05, p95, color="tab:blue", alpha=0.25,
                    label=f"5\u201395% range ({args.runs} runs)")
    ax.plot(y_index, p50, color="tab:blue", lw=2.0, label="Median path")
    ax.set_title(f"Kronos-small forecast \u2014 {args.ticker} {args.interval} | "
                 f"{args.runs} runs \u00d7 pred_len={args.pred_len} | device={device}")
    ax.set_ylabel("Price")
    ax.legend(loc="best")
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(png_path, dpi=150)

    last_close = df["close"].iloc[-1]
    print(f"\nSaved plot     -> {os.path.abspath(png_path)}")
    print(f"Saved quantiles -> {os.path.abspath(csv_path)}")
    print("\n=== Forecast summary (close) ===")
    print(f"last historical close : {last_close:,.2f}")
    print(f"median @ t+{args.pred_len:<3d}        : {p50[-1]:,.2f}  (5%: {p05[-1]:,.2f} / 95%: {p95[-1]:,.2f})")


if __name__ == "__main__":
    main()
