import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


FEATURE_COLUMNS = ["open", "high", "low", "close", "volume", "amount"]


def load_grouped_ohlcv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"symbol": str, "session": str})
    required = {"symbol", "session", "timestamps", *FEATURE_COLUMNS}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Grouped OHLCV file missing columns: {missing}")
    df["timestamps"] = pd.to_datetime(df["timestamps"])
    for col in FEATURE_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["timestamps", *FEATURE_COLUMNS])
    return df.sort_values(["symbol", "session", "timestamps"]).reset_index(drop=True)


def persistence_prediction(history: pd.DataFrame, pred_len: int, future_timestamps: pd.Series) -> pd.DataFrame:
    last = history.iloc[-1]
    pred = pd.DataFrame(
        {
            "timestamps": future_timestamps.reset_index(drop=True),
            "open": float(last["close"]),
            "high": float(last["close"]),
            "low": float(last["close"]),
            "close": float(last["close"]),
            "volume": float(last.get("volume", 0.0)),
            "amount": float(last.get("amount", 0.0)),
        }
    )
    return pred.iloc[:pred_len].copy()


def kronos_prediction(
    history: pd.DataFrame,
    future_timestamps: pd.Series,
    pred_len: int,
    model_path: str,
    tokenizer_path: str,
    device: str = "cpu",
    max_context: int = 512,
    temperature: float = 1.0,
    top_p: float = 0.9,
    sample_count: int = 1,
) -> pd.DataFrame:
    import torch
    from model import Kronos, KronosPredictor, KronosTokenizer

    tokenizer = KronosTokenizer.from_pretrained(tokenizer_path)
    model = Kronos.from_pretrained(model_path)
    torch_device = torch.device(device)
    tokenizer = tokenizer.to(torch_device)
    model = model.to(torch_device)
    predictor = KronosPredictor(model, tokenizer, max_context=max_context, device=str(torch_device))

    return predictor.predict(
        df=history[FEATURE_COLUMNS],
        x_timestamp=history["timestamps"],
        y_timestamp=future_timestamps,
        pred_len=pred_len,
        T=temperature,
        top_p=top_p,
        sample_count=sample_count,
        verbose=False,
    )


def _window_positions(group_len: int, lookback_window: int, predict_window: int, stride: int) -> List[int]:
    max_start = group_len - lookback_window - predict_window
    if max_start < 0:
        return []
    return list(range(0, max_start + 1, max(1, stride)))


def _safe_pct(numerator: float, denominator: float) -> float:
    if denominator == 0 or math.isnan(denominator):
        return 0.0
    return numerator / denominator * 100.0


def evaluate_predictions(
    data_path: Path,
    output_path: Path,
    lookback_window: int = 300,
    predict_window: int = 60,
    max_windows: int = 50,
    stride: int = 60,
    mode: str = "baseline",
    model_path: Optional[str] = None,
    tokenizer_path: Optional[str] = None,
    device: str = "cpu",
    max_context: int = 512,
) -> Dict[str, Any]:
    df = load_grouped_ohlcv(data_path)
    rows: List[Dict[str, Any]] = []
    window_count = 0

    for (symbol, session), group in df.groupby(["symbol", "session"], sort=True):
        positions = _window_positions(len(group), lookback_window, predict_window, stride)
        if not positions:
            continue

        group = group.reset_index(drop=True)
        for start_idx in positions:
            if window_count >= max_windows:
                break
            history = group.iloc[start_idx : start_idx + lookback_window].copy()
            actual = group.iloc[start_idx + lookback_window : start_idx + lookback_window + predict_window].copy()
            future_timestamps = actual["timestamps"].reset_index(drop=True)

            if mode == "kronos":
                if not model_path or not tokenizer_path:
                    raise ValueError("mode=kronos requires --model-path and --tokenizer-path")
                pred = kronos_prediction(
                    history=history,
                    future_timestamps=future_timestamps,
                    pred_len=predict_window,
                    model_path=model_path,
                    tokenizer_path=tokenizer_path,
                    device=device,
                    max_context=max_context,
                )
                if "timestamps" not in pred.columns:
                    pred = pred.copy()
                    pred["timestamps"] = future_timestamps.values
            else:
                pred = persistence_prediction(history, predict_window, future_timestamps)

            actual = actual.reset_index(drop=True)
            pred = pred.reset_index(drop=True)
            t0_close = float(history["close"].iloc[-1])
            pred_close = float(pred["close"].iloc[-1])
            actual_close = float(actual["close"].iloc[-1])
            pred_return = _safe_pct(pred_close - t0_close, t0_close)
            actual_return = _safe_pct(actual_close - t0_close, t0_close)

            for horizon_idx in range(min(len(actual), len(pred))):
                p_close = float(pred["close"].iloc[horizon_idx])
                a_close = float(actual["close"].iloc[horizon_idx])
                rows.append(
                    {
                        "window_id": window_count,
                        "symbol": symbol,
                        "session": session,
                        "asof_timestamp": history["timestamps"].iloc[-1].isoformat(),
                        "target_timestamp": actual["timestamps"].iloc[horizon_idx].isoformat(),
                        "horizon_step": horizon_idx + 1,
                        "horizon_seconds": horizon_idx + 1,
                        "actual_close_t0": t0_close,
                        "pred_close": p_close,
                        "actual_close": a_close,
                        "error": p_close - a_close,
                        "abs_error": abs(p_close - a_close),
                        "pred_return_window": pred_return,
                        "actual_return_window": actual_return,
                        "direction_hit_window": int(np.sign(pred_return) == np.sign(actual_return)),
                        "mode": mode,
                    }
                )
            window_count += 1

        if window_count >= max_windows:
            break

    if not rows:
        raise ValueError("No prediction windows were generated. Check data length/window settings.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_df = pd.DataFrame(rows)
    out_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    metrics = summarize_prediction_frame(out_df)
    metrics.update(
        {
            "data_path": str(data_path),
            "output_path": str(output_path),
            "mode": mode,
            "lookback_window": lookback_window,
            "predict_window": predict_window,
            "windows": int(out_df["window_id"].nunique()),
            "rows": len(out_df),
        }
    )
    metrics_path = output_path.with_suffix(".metrics.json")
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return metrics


def summarize_prediction_frame(df: pd.DataFrame) -> Dict[str, Any]:
    error = pd.to_numeric(df["error"], errors="coerce")
    abs_error = pd.to_numeric(df["abs_error"], errors="coerce")
    actual = pd.to_numeric(df["actual_close"], errors="coerce").replace(0, np.nan)
    mape = (abs_error / actual).replace([np.inf, -np.inf], np.nan).mean() * 100.0
    latest = df.sort_values(["window_id", "horizon_step"]).groupby("window_id").tail(1)
    return {
        "mae": float(abs_error.mean()),
        "rmse": float(np.sqrt((error**2).mean())),
        "mape": float(0.0 if np.isnan(mape) else mape),
        "direction_accuracy": float(pd.to_numeric(latest["direction_hit_window"], errors="coerce").mean()),
        "avg_pred_return": float(pd.to_numeric(latest["pred_return_window"], errors="coerce").mean()),
        "avg_actual_return": float(pd.to_numeric(latest["actual_return_window"], errors="coerce").mean()),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate STOM actual-vs-predicted evaluation rows.")
    parser.add_argument("--data", required=True, help="Grouped STOM OHLCV CSV.")
    parser.add_argument("--output", required=True, help="Output prediction CSV.")
    parser.add_argument("--lookback-window", type=int, default=300)
    parser.add_argument("--predict-window", type=int, default=60)
    parser.add_argument("--max-windows", type=int, default=50)
    parser.add_argument("--stride", type=int, default=60)
    parser.add_argument("--mode", choices=["baseline", "kronos"], default="baseline")
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--tokenizer-path", default=None)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--max-context", type=int, default=512)
    args = parser.parse_args(argv)

    metrics = evaluate_predictions(
        data_path=Path(args.data),
        output_path=Path(args.output),
        lookback_window=args.lookback_window,
        predict_window=args.predict_window,
        max_windows=args.max_windows,
        stride=args.stride,
        mode=args.mode,
        model_path=args.model_path,
        tokenizer_path=args.tokenizer_path,
        device=args.device,
        max_context=args.max_context,
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
