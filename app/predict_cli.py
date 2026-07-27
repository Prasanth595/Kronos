"""CLI: predict next candle(s) from a CSV of historical candles."""

from __future__ import annotations

import argparse
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from predictor_service import CandlePredictor


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict future candles with local Kronos")
    parser.add_argument("csv", help="Path to OHLCV CSV (columns: open,high,low,close[,volume,amount,timestamps])")
    parser.add_argument("--pred-len", type=int, default=1, help="Number of candles to forecast (default: 1)")
    parser.add_argument("--model", default="kronos-small", choices=["kronos-mini", "kronos-small", "kronos-base"])
    parser.add_argument("--device", default=None, help="e.g. cuda:0 or cpu")
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--sample-count", type=int, default=1)
    parser.add_argument("--freq", default=None, help="Optional pandas freq, e.g. 5min")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of table")
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    candles = df.to_dict(orient="records")

    predictor = CandlePredictor(model_key=args.model, device=args.device)
    pred = predictor.predict(
        candles=candles,
        pred_len=args.pred_len,
        temperature=args.temperature,
        top_p=args.top_p,
        sample_count=args.sample_count,
        freq=args.freq,
    )

    if args.json:
        records = pred.to_dict(orient="records")
        for row in records:
            if "timestamps" in row:
                row["timestamps"] = str(row["timestamps"])
        print(json.dumps({"predictions": records, "next_candle": records[0]}, indent=2))
    else:
        print(pred.to_string(index=False))


if __name__ == "__main__":
    main()
