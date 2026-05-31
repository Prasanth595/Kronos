"""
Fetch 5-minute OHLCV data for one or more NSE/BSE instruments via yfinance
and save in the format expected by CustomKlineDataset.

Required columns: timestamps, open, high, low, close, volume, amount

Ticker conventions
------------------
  Equities  : RELIANCE, TCS, INFY        -> appended with .NS automatically
  Indices   : NIFTY50, BANKNIFTY         -> mapped to ^NSEI, ^NSEBANK
  BSE       : RELIANCE.BO, TCS.BO        -> passed through as-is
  Raw       : ^NSEI, RELIANCE.NS, etc.   -> passed through as-is

Usage:
  python fetch_india_data.py --tickers RELIANCE TCS INFY --output data/india_5min.csv
  python fetch_india_data.py --tickers NIFTY50 BANKNIFTY --period 30d --output data/indices_5min.csv
  python fetch_india_data.py --tickers RELIANCE.NS TCS.NS --period 60d --output data/equities_5min.csv

Note: yfinance supports a maximum of 60 days of 5-min data.
"""

import argparse
import os
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf

# ── Constants ─────────────────────────────────────────────────────────────────

IST          = "Asia/Kolkata"
MARKET_OPEN  = "09:15"
MARKET_CLOSE = "15:30"

NSE_INDEX_MAP = {
    "NIFTY50":    "^NSEI",
    "NIFTY 50":   "^NSEI",
    "NIFTY":      "^NSEI",
    "BANKNIFTY":  "^NSEBANK",
    "BANK NIFTY": "^NSEBANK",
    "FINNIFTY":   "NIFTY_FIN_SERVICE.NS",
    "NIFTYIT":    "^CNXIT",
    "MIDCAPNIFTY":"^NSEMDCP50",
    "SENSEX":     "^BSESN",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def normalise_ticker(raw: str) -> str:
    """Map a human-friendly name to a yfinance-compatible symbol."""
    upper = raw.upper().strip()
    if upper in NSE_INDEX_MAP:
        return NSE_INDEX_MAP[upper]
    if "." in upper or upper.startswith("^"):
        return upper          # already has suffix or is an index
    return upper + ".NS"      # default: NSE equity


def fetch_ticker(ticker: str, period: str) -> pd.DataFrame:
    sym = normalise_ticker(ticker)
    raw = yf.download(sym, period=period, interval="5m", progress=False, auto_adjust=True)

    if raw.empty:
        print(f"  WARNING: no data returned for {ticker} ({sym}), skipping.")
        return pd.DataFrame()

    # Flatten MultiIndex columns produced by yfinance >= 0.2
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    raw = raw.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })

    # Convert to IST and keep only NSE market hours
    if raw.index.tz is None:
        raw.index = raw.index.tz_localize("UTC")
    raw.index = raw.index.tz_convert(IST)
    raw = raw.between_time(MARKET_OPEN, MARKET_CLOSE)

    raw = raw[["open", "high", "low", "close", "volume"]].dropna()

    # amount = volume × avg(OHLC) — proxy for turnover
    raw["amount"] = raw["volume"] * (
        raw["open"] + raw["high"] + raw["low"] + raw["close"]
    ) / 4

    raw = (raw.reset_index()
              .rename(columns={"Datetime": "timestamps", "index": "timestamps"}))
    raw["timestamps"] = pd.to_datetime(raw["timestamps"]).dt.tz_localize(None)
    raw = raw[["timestamps", "open", "high", "low", "close", "volume", "amount"]]
    raw = raw.sort_values("timestamps").reset_index(drop=True)

    print(f"  {ticker} ({sym}): {len(raw)} bars  "
          f"[{raw['timestamps'].iloc[0]} → {raw['timestamps'].iloc[-1]}]")
    return raw

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fetch Indian equity/index 5-min data for Kronos fine-tuning"
    )
    parser.add_argument(
        "--tickers", nargs="+", required=True,
        help="One or more symbols: RELIANCE, TCS, NIFTY50, BANKNIFTY, RELIANCE.NS, …"
    )
    parser.add_argument(
        "--period", type=str, default="60d",
        help="yfinance period string (max 60d for 5-min). Default: 60d"
    )
    parser.add_argument(
        "--output", type=str, default="data/india_5min.csv",
        help="Output CSV path. Default: data/india_5min.csv"
    )
    args = parser.parse_args()

    print(f"Fetching {len(args.tickers)} ticker(s) via yfinance …")
    all_frames = []
    for ticker in args.tickers:
        df = fetch_ticker(ticker, args.period)
        if not df.empty:
            all_frames.append(df)

    if not all_frames:
        raise RuntimeError(
            "No data fetched — check ticker symbols and internet connection.\n"
            "Tip: NSE equities use the .NS suffix (e.g. RELIANCE.NS)."
        )

    combined = pd.concat(all_frames, ignore_index=True)
    combined = combined.sort_values("timestamps").reset_index(drop=True)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    combined.to_csv(args.output, index=False)

    print(f"\nSaved {len(combined):,} rows → {args.output}")
    print(f"Date range  : {combined['timestamps'].min()} → {combined['timestamps'].max()}")
    print(f"Market hours: {MARKET_OPEN}–{MARKET_CLOSE} IST")
    print(f"Columns     : {list(combined.columns)}")


if __name__ == "__main__":
    main()
