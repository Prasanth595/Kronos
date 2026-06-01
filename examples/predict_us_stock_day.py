import argparse
import os
from datetime import timedelta

import pandas as pd
import yfinance as yf
import torch

import sys
sys.path.append("../")
from model import Kronos, KronosTokenizer, KronosPredictor


def pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda:0"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_us_daily(symbol: str, min_rows: int = 520) -> pd.DataFrame:
    # Pull enough daily candles to satisfy lookback while preserving recent context.
    df = yf.download(symbol, period="5y", interval="1d", auto_adjust=False, progress=False)
    if df is None or df.empty:
        raise RuntimeError(f"No data returned for {symbol} from Yahoo Finance")

    df = df.reset_index().rename(
        columns={
            "Date": "timestamps",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    df["timestamps"] = pd.to_datetime(df["timestamps"]).dt.tz_localize(None)
    df["amount"] = df["close"] * df["volume"]
    df = df[["timestamps", "open", "high", "low", "close", "volume", "amount"]]
    df = df.dropna().sort_values("timestamps").reset_index(drop=True)

    if len(df) < min_rows:
        raise RuntimeError(
            f"Not enough rows for robust context. Need >= {min_rows}, got {len(df)} for {symbol}."
        )

    return df


def future_business_days(last_day: pd.Timestamp, periods: int) -> pd.Series:
    start = last_day + timedelta(days=1)
    return pd.Series(pd.bdate_range(start=start, periods=periods))


def main(symbol: str, pred_len: int, lookback: int, out_dir: str) -> None:
    device = pick_device()
    print(f"Using device: {device}")

    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=512)

    df = load_us_daily(symbol)
    hist = df.tail(lookback).copy()

    x_df = hist[["open", "high", "low", "close", "volume", "amount"]]
    x_timestamp = hist["timestamps"]
    y_timestamp = future_business_days(hist["timestamps"].iloc[-1], pred_len)

    pred_df = predictor.predict(
        df=x_df,
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=pred_len,
        T=1.0,
        top_p=0.9,
        sample_count=1,
        verbose=False,
    ).reset_index().rename(columns={"index": "timestamps"})

    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"pred_{symbol}_{pred_len}d.csv")
    pred_df.to_csv(out_file, index=False)

    print("\nLast observed row:")
    print(hist.tail(1).to_string(index=False))
    print("\nForecast:")
    print(pred_df[["timestamps", "open", "high", "low", "close", "volume", "amount"]].to_string(index=False))
    print(f"\nSaved: {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Predict next N business days for a US stock with Kronos")
    parser.add_argument("--symbol", type=str, default="F", help="Ticker symbol, e.g. F")
    parser.add_argument("--pred-len", type=int, default=3, help="Number of future business days")
    parser.add_argument("--lookback", type=int, default=400, help="Historical lookback rows")
    parser.add_argument("--out-dir", type=str, default="./outputs", help="Output directory")
    args = parser.parse_args()

    main(symbol=args.symbol, pred_len=args.pred_len, lookback=args.lookback, out_dir=args.out_dir)
