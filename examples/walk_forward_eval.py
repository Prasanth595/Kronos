#!/usr/bin/env python3
"""Walk-forward evaluation of zero-shot Kronos vs a last-price random walk.

This addresses https://github.com/shiyu-coder/Kronos/issues/387:

* Single-name directional PnL is not the paper protocol. The paper reports IC /
  RankIC of predicted vs actual series (and cross-sectional ranking after
  finetuning), not "long/short one futures contract vs a coin flip".
* `predict()` averages sample paths. Plotting high/low of that mean path makes
  uncertainty cones look too narrow. Use `forecast()` quantiles across samples.
* Always compare MAE and hit-rate against a last-price random walk on the
  *same* origins before claiming an edge.

Example:
    python examples/walk_forward_eval.py \\
        --data data/XSHG_5min_600977.csv \\
        --lookback 400 --pred-len 12 --stride 48 --windows 8 --sample-count 8
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model import Kronos, KronosPredictor, KronosTokenizer


def directional_hit_rate(pred_ret: np.ndarray, actual_ret: np.ndarray) -> float:
    pred_ret = np.asarray(pred_ret, dtype=np.float64)
    actual_ret = np.asarray(actual_ret, dtype=np.float64)
    mask = (pred_ret != 0) & (actual_ret != 0) & np.isfinite(pred_ret) & np.isfinite(actual_ret)
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(np.sign(pred_ret[mask]) == np.sign(actual_ret[mask])))


def pearson_ic(pred_ret: np.ndarray, actual_ret: np.ndarray) -> float:
    pred_ret = np.asarray(pred_ret, dtype=np.float64)
    actual_ret = np.asarray(actual_ret, dtype=np.float64)
    if pred_ret.size < 3:
        return float("nan")
    if np.std(pred_ret) == 0 or np.std(actual_ret) == 0:
        return float("nan")
    return float(np.corrcoef(pred_ret, actual_ret)[0, 1])


def cone_coverage(actual: np.ndarray, q_low: np.ndarray, q_high: np.ndarray) -> float:
    actual = np.asarray(actual, dtype=np.float64)
    return float(np.mean((actual >= q_low) & (actual <= q_high)))


def naive_mean_path_cone_width(samples: np.ndarray) -> float:
    """Width you get if you average paths first, then read high-low of the mean bar."""
    mean_path = samples.mean(axis=0)
    return float(np.mean(mean_path[:, 1] - mean_path[:, 2]))


def sample_quantile_cone_width(samples: np.ndarray, q_low=0.1, q_high=0.9, close_idx=3) -> float:
    """Width of the close distribution across samples (the actual forecast cone)."""
    low = np.quantile(samples[:, :, close_idx], q_low, axis=0)
    high = np.quantile(samples[:, :, close_idx], q_high, axis=0)
    return float(np.mean(high - low))


def summarize_windows(rows: list[dict]) -> dict:
    pred = np.array([r["kronos_return"] for r in rows], dtype=np.float64)
    actual = np.array([r["actual_return"] for r in rows], dtype=np.float64)
    rw = np.array([r["rw_return"] for r in rows], dtype=np.float64)
    mae_kronos = float(np.mean([r["kronos_mae"] for r in rows]))
    mae_rw = float(np.mean([r["rw_mae"] for r in rows]))
    coverage = float(np.mean([r["coverage"] for r in rows]))
    naive_width = float(np.mean([r["naive_cone_width"] for r in rows]))
    sample_width = float(np.mean([r["sample_cone_width"] for r in rows]))
    return {
        "n_windows": len(rows),
        "kronos_mae": mae_kronos,
        "random_walk_mae": mae_rw,
        "mae_ratio_vs_rw": mae_kronos / mae_rw if mae_rw else float("nan"),
        "kronos_hit_rate": directional_hit_rate(pred, actual),
        "random_walk_hit_rate": directional_hit_rate(rw, actual),
        "kronos_ic": pearson_ic(pred, actual),
        "q10_q90_coverage": coverage,
        "naive_mean_path_cone_width": naive_width,
        "sample_quantile_cone_width": sample_width,
        "cone_width_ratio_naive_over_sample": naive_width / sample_width if sample_width else float("nan"),
    }


def interpret(summary: dict) -> list[str]:
    lines = []
    ratio = summary["mae_ratio_vs_rw"]
    if np.isfinite(ratio) and ratio >= 1.0:
        lines.append(
            f"No point-forecast edge: Kronos MAE is {ratio:.3f}x the last-price random walk."
        )
    elif np.isfinite(ratio):
        lines.append(
            f"Kronos MAE is {ratio:.3f}x the last-price random walk (lower is better)."
        )
    hit = summary["kronos_hit_rate"]
    if np.isfinite(hit) and hit <= 0.5:
        lines.append(
            f"No directional edge: hit rate {hit:.1%} is not above a coin flip."
        )
    cov = summary["q10_q90_coverage"]
    if np.isfinite(cov) and cov < 0.7:
        lines.append(
            f"Cones still look tight: {cov:.1%} of actuals fell inside the 10-90% sample band "
            "(80% expected if the band is calibrated)."
        )
    width_ratio = summary["cone_width_ratio_naive_over_sample"]
    if np.isfinite(width_ratio) and width_ratio < 0.5:
        lines.append(
            f"The mean-path high/low cone is {width_ratio:.2f}x the sample-quantile cone. "
            "Do not plot high/low of predict() as uncertainty."
        )
    ic = summary["kronos_ic"]
    if np.isfinite(ic):
        lines.append(
            f"Single-series IC of horizon returns is {ic:.4f}. The paper's RankIC is a "
            "cross-sectional ranking metric after (usually) finetuning, not this test."
        )
    lines.append(
        "Zero-shot Kronos-small is a generative K-line prior, not a finished trading signal. "
        "If this walk-forward shows no edge on your futures, finetune on that market "
        "or use cross-sectional ranking — do not expect T=1.5 alone to create alpha."
    )
    return lines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Walk-forward Kronos vs random-walk evaluation")
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "XSHG_5min_600977.csv")
    parser.add_argument("--lookback", type=int, default=400)
    parser.add_argument("--pred-len", type=int, default=12)
    parser.add_argument("--stride", type=int, default=48)
    parser.add_argument("--windows", type=int, default=6)
    parser.add_argument("--sample-count", type=int, default=8)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--tokenizer", default="NeoQuasar/Kronos-Tokenizer-base")
    parser.add_argument("--model", default="NeoQuasar/Kronos-small")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.data.exists():
        print(f"Data file not found: {args.data}")
        return 1

    df = pd.read_csv(args.data)
    time_col = "timestamps" if "timestamps" in df.columns else "timestamp"
    df[time_col] = pd.to_datetime(df[time_col])
    cols = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in df.columns]

    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(model, tokenizer, max_context=512)
    print(f"Device: {predictor.device}")

    max_origin = len(df) - args.pred_len
    origins = list(range(args.lookback, max_origin, args.stride))[: args.windows]
    if not origins:
        print("Not enough rows for the requested lookback/pred_len.")
        return 1

    rows = []
    close_idx = cols.index("close")
    for origin in origins:
        context = df.iloc[origin - args.lookback:origin]
        future = df.iloc[origin:origin + args.pred_len]
        x_df = context[cols].reset_index(drop=True)
        x_ts = context[time_col].reset_index(drop=True)
        y_ts = future[time_col].reset_index(drop=True)

        result = predictor.forecast(
            df=x_df,
            x_timestamp=x_ts,
            y_timestamp=y_ts,
            pred_len=args.pred_len,
            T=args.temperature,
            top_p=args.top_p,
            sample_count=args.sample_count,
            verbose=False,
        )
        last_close = float(context["close"].iloc[-1])
        actual_close = future["close"].to_numpy(dtype=np.float64)
        mean_close = result["mean"]["close"].to_numpy(dtype=np.float64)
        q10 = result["quantiles"]["q10"]["close"].to_numpy(dtype=np.float64)
        q90 = result["quantiles"]["q90"]["close"].to_numpy(dtype=np.float64)
        rw_path = np.repeat(last_close, args.pred_len)

        kronos_end = float(mean_close[-1])
        actual_end = float(actual_close[-1])
        rows.append({
            "origin": str(context[time_col].iloc[-1]),
            "last_close": last_close,
            "kronos_return": kronos_end / last_close - 1.0,
            "actual_return": actual_end / last_close - 1.0,
            "rw_return": 0.0,
            "kronos_mae": float(np.mean(np.abs(mean_close - actual_close))),
            "rw_mae": float(np.mean(np.abs(rw_path - actual_close))),
            "coverage": cone_coverage(actual_close, q10, q90),
            "naive_cone_width": naive_mean_path_cone_width(result["samples"]),
            "sample_cone_width": sample_quantile_cone_width(result["samples"], close_idx=close_idx),
        })
        print(
            f"{rows[-1]['origin']}  kronos_ret={rows[-1]['kronos_return']:+.4f}  "
            f"actual_ret={rows[-1]['actual_return']:+.4f}  "
            f"mae={rows[-1]['kronos_mae']:.4f} vs rw={rows[-1]['rw_mae']:.4f}  "
            f"cover={rows[-1]['coverage']:.0%}"
        )

    summary = summarize_windows(rows)
    print("\n=== Walk-forward summary ===")
    print(json.dumps(summary, indent=2))
    print("\n=== Interpretation ===")
    for line in interpret(summary):
        print(f"- {line}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"windows": rows, "summary": summary}, indent=2))
        print(f"\nWrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
