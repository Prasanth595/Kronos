"""Evaluate STOM 1-second Kronos checkpoints against holdout QlibDataset pickles."""

from __future__ import annotations

import argparse
import json
import pickle
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
WEBUI_PREDICTION_DIR = PROJECT_ROOT / "webui" / "stom_predictions"
DEFAULT_TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"


@dataclass(frozen=True)
class EvalWindow:
    window_id: int
    key: str
    symbol: str
    session: str
    history: pd.DataFrame
    actual: pd.DataFrame


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_pct(numerator: float, denominator: float) -> float:
    if denominator == 0 or np.isnan(denominator):
        return 0.0
    return numerator / denominator * 100.0


def _split_key(key: str) -> Tuple[str, str]:
    if "_" not in key:
        return key, ""
    symbol, session = key.rsplit("_", 1)
    return symbol, session


def _to_prediction_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy().reset_index().rename(columns={"datetime": "timestamps", "index": "timestamps"})
    if "timestamps" not in out.columns:
        first = out.columns[0]
        out = out.rename(columns={first: "timestamps"})
    out["timestamps"] = pd.to_datetime(out["timestamps"])
    out = out.rename(columns={"vol": "volume", "amt": "amount"})
    if "volume" not in out.columns:
        out["volume"] = 0.0
    if "amount" not in out.columns:
        out["amount"] = out["close"] * out["volume"]
    return out[["timestamps", "open", "high", "low", "close", "volume", "amount"]]


def load_pickle_dataset(dataset_path: Path, split: str = "test") -> Dict[str, pd.DataFrame]:
    path = dataset_path / f"{split}_data.pkl"
    if not path.exists():
        raise FileNotFoundError(f"Dataset split pickle not found: {path}")
    with path.open("rb") as f:
        data = pickle.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict pickle at {path}")
    return data


def _group_by_session(data: Mapping[str, pd.DataFrame]) -> Dict[str, List[Tuple[str, str, pd.DataFrame]]]:
    sessions: Dict[str, List[Tuple[str, str, pd.DataFrame]]] = {}
    for key, frame in data.items():
        symbol, session = _split_key(key)
        sessions.setdefault(session, []).append((key, symbol, frame))
    for rows in sessions.values():
        rows.sort(key=lambda item: item[1])
    return dict(sorted(sessions.items()))


def select_aligned_windows(
    data: Mapping[str, pd.DataFrame],
    lookback_window: int,
    predict_window: int,
    max_symbols: int = 20,
    max_asofs: int = 1,
    max_sessions: int = 1,
    stride: int = 300,
) -> List[EvalWindow]:
    """Select deterministic cross-sectional windows sharing as-of timestamps."""

    selected: List[EvalWindow] = []
    sessions = _group_by_session(data)
    for session_idx, (_session, candidates) in enumerate(sessions.items()):
        if session_idx >= max_sessions:
            break
        usable = [
            (key, symbol, _to_prediction_frame(frame))
            for key, symbol, frame in candidates
            if len(frame) >= lookback_window + predict_window
        ]
        if not usable:
            continue

        max_start = max(len(frame) - lookback_window - predict_window for _, _, frame in usable)
        starts = list(range(0, max_start + 1, max(1, stride)))[:max_asofs]
        for start in starts:
            by_asof: Dict[str, List[Tuple[str, str, pd.DataFrame]]] = {}
            for key, symbol, frame in usable:
                if len(frame) < start + lookback_window + predict_window:
                    continue
                asof = frame["timestamps"].iloc[start + lookback_window - 1].isoformat()
                by_asof.setdefault(asof, []).append((key, symbol, frame))
            if not by_asof:
                continue
            _, aligned = max(by_asof.items(), key=lambda item: len(item[1]))
            for key, symbol, frame in aligned[:max_symbols]:
                history = frame.iloc[start : start + lookback_window].reset_index(drop=True)
                actual = frame.iloc[start + lookback_window : start + lookback_window + predict_window].reset_index(
                    drop=True
                )
                selected.append(
                    EvalWindow(
                        window_id=len(selected),
                        key=key,
                        symbol=symbol,
                        session=str(actual["timestamps"].iloc[0].strftime("%Y%m%d")),
                        history=history,
                        actual=actual,
                    )
                )
    if not selected:
        raise ValueError("No aligned evaluation windows were selected.")
    return selected


def persistence_predictions(windows: Sequence[EvalWindow]) -> List[pd.DataFrame]:
    frames: List[pd.DataFrame] = []
    for window in windows:
        last_close = float(window.history["close"].iloc[-1])
        pred = pd.DataFrame(
            {
                "open": last_close,
                "high": last_close,
                "low": last_close,
                "close": last_close,
                "volume": float(window.history["volume"].iloc[-1]),
                "amount": float(window.history["amount"].iloc[-1]),
            },
            index=window.actual["timestamps"],
        )
        frames.append(pred)
    return frames


def random_direction_predictions(windows: Sequence[EvalWindow], seed: int = 100) -> List[pd.DataFrame]:
    rng = random.Random(seed)
    frames: List[pd.DataFrame] = []
    for window in windows:
        last_close = float(window.history["close"].iloc[-1])
        close = pd.to_numeric(window.history["close"], errors="coerce")
        returns = close.pct_change().replace([np.inf, -np.inf], np.nan).dropna().abs()
        move_pct = float(returns.median() * 100.0) if len(returns) else 0.0
        if move_pct == 0:
            move_pct = 0.05
        direction = 1 if rng.random() >= 0.5 else -1
        final_close = last_close * (1.0 + direction * move_pct / 100.0)
        path = np.linspace(last_close, final_close, len(window.actual) + 1)[1:]
        pred = pd.DataFrame(
            {
                "open": path,
                "high": path,
                "low": path,
                "close": path,
                "volume": float(window.history["volume"].iloc[-1]),
                "amount": float(window.history["amount"].iloc[-1]),
            },
            index=window.actual["timestamps"],
        )
        frames.append(pred)
    return frames


def kronos_predictions(
    windows: Sequence[EvalWindow],
    model_path: str,
    tokenizer_path: str,
    device: str,
    predict_window: int,
    max_context: int = 512,
    batch_size: int = 4,
    temperature: float = 0.6,
    top_p: float = 0.9,
    top_k: int = 0,
    sample_count: int = 1,
) -> List[pd.DataFrame]:
    import torch
    from model import Kronos, KronosPredictor, KronosTokenizer

    tokenizer = KronosTokenizer.from_pretrained(tokenizer_path)
    model = Kronos.from_pretrained(model_path)
    model.eval()
    tokenizer.eval()
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=max_context)
    out: List[pd.DataFrame] = []
    with torch.no_grad():
        for start in range(0, len(windows), max(1, batch_size)):
            batch = windows[start : start + max(1, batch_size)]
            pred_frames = predictor.predict_batch(
                df_list=[w.history[["open", "high", "low", "close", "volume", "amount"]] for w in batch],
                x_timestamp_list=[w.history["timestamps"] for w in batch],
                y_timestamp_list=[w.actual["timestamps"] for w in batch],
                pred_len=predict_window,
                T=temperature,
                top_k=top_k,
                top_p=top_p,
                sample_count=sample_count,
                verbose=False,
            )
            out.extend(pred_frames)
    return out


def rows_from_predictions(windows: Sequence[EvalWindow], predictions: Sequence[pd.DataFrame], mode: str) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for window, pred in zip(windows, predictions):
        actual = window.actual.reset_index(drop=True)
        pred = pred.reset_index().rename(columns={"index": "timestamps"}).reset_index(drop=True)
        t0_close = float(window.history["close"].iloc[-1])
        pred_close_final = float(pred["close"].iloc[-1])
        actual_close_final = float(actual["close"].iloc[-1])
        pred_return = _safe_pct(pred_close_final - t0_close, t0_close)
        actual_return = _safe_pct(actual_close_final - t0_close, t0_close)
        direction_hit = int(np.sign(pred_return) == np.sign(actual_return))
        pred_close_series = pd.to_numeric(pred["close"], errors="coerce")
        if pred_return >= 0:
            pred_path_consistency = float((pred_close_series >= t0_close).mean())
        else:
            pred_path_consistency = float((pred_close_series <= t0_close).mean())
        pred_range_pct = _safe_pct(float(pred_close_series.max() - pred_close_series.min()), t0_close)
        history_close = pd.to_numeric(window.history["close"], errors="coerce")
        history_returns = history_close.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        history_volatility_pct = float(history_returns.std(ddof=0) * 100.0) if len(history_returns) else 0.0
        history_return_pct = _safe_pct(float(history_close.iloc[-1] - history_close.iloc[0]), float(history_close.iloc[0]))
        history_mean_amount = float(pd.to_numeric(window.history["amount"], errors="coerce").fillna(0.0).mean())
        history_last_amount = float(pd.to_numeric(window.history["amount"], errors="coerce").fillna(0.0).iloc[-1])
        history_mean_volume = float(pd.to_numeric(window.history["volume"], errors="coerce").fillna(0.0).mean())
        history_last_volume = float(pd.to_numeric(window.history["volume"], errors="coerce").fillna(0.0).iloc[-1])
        for idx in range(min(len(actual), len(pred))):
            pred_close = float(pred["close"].iloc[idx])
            actual_close = float(actual["close"].iloc[idx])
            rows.append(
                {
                    "window_id": window.window_id,
                    "symbol": window.symbol,
                    "session": window.session,
                    "asof_timestamp": window.history["timestamps"].iloc[-1].isoformat(),
                    "target_timestamp": actual["timestamps"].iloc[idx].isoformat(),
                    "horizon_step": idx + 1,
                    "horizon_seconds": idx + 1,
                    "actual_close_t0": t0_close,
                    "pred_close": pred_close,
                    "actual_close": actual_close,
                    "error": pred_close - actual_close,
                    "abs_error": abs(pred_close - actual_close),
                    "pred_return_window": pred_return,
                    "actual_return_window": actual_return,
                    "direction_hit_window": direction_hit,
                    "pred_path_consistency": pred_path_consistency,
                    "pred_range_pct": pred_range_pct,
                    "history_volatility_pct": history_volatility_pct,
                    "history_return_pct": history_return_pct,
                    "history_mean_amount": history_mean_amount,
                    "history_last_amount": history_last_amount,
                    "history_mean_volume": history_mean_volume,
                    "history_last_volume": history_last_volume,
                    "mode": mode,
                }
            )
    return pd.DataFrame(rows)


def summarize_prediction_frame(df: pd.DataFrame, top_k: int = 5) -> Dict[str, Any]:
    error = pd.to_numeric(df["error"], errors="coerce")
    abs_error = pd.to_numeric(df["abs_error"], errors="coerce")
    actual = pd.to_numeric(df["actual_close"], errors="coerce").replace(0, np.nan)
    latest = df.sort_values(["window_id", "horizon_step"]).groupby("window_id").tail(1)
    mape = (abs_error / actual).replace([np.inf, -np.inf], np.nan).mean() * 100.0
    top_rows = []
    for _, group in latest.groupby("asof_timestamp", sort=True):
        top_rows.append(group.sort_values("pred_return_window", ascending=False).head(top_k))
    top = pd.concat(top_rows, ignore_index=True) if top_rows else latest.iloc[0:0]
    return {
        "rows": int(len(df)),
        "windows": int(latest["window_id"].nunique()),
        "symbols": int(latest["symbol"].nunique()),
        "mae": float(abs_error.mean()),
        "rmse": float(np.sqrt((error**2).mean())),
        "mape": float(0.0 if np.isnan(mape) else mape),
        "direction_accuracy": float(pd.to_numeric(latest["direction_hit_window"], errors="coerce").mean()),
        "avg_pred_return": float(pd.to_numeric(latest["pred_return_window"], errors="coerce").mean()),
        "avg_actual_return": float(pd.to_numeric(latest["actual_return_window"], errors="coerce").mean()),
        "topk": {
            "k": int(top_k),
            "periods": int(latest["asof_timestamp"].nunique()),
            "trades": int(len(top)),
            "avg_actual_return": float(pd.to_numeric(top.get("actual_return_window", pd.Series(dtype=float))).mean())
            if len(top)
            else 0.0,
            "hit_rate": float(pd.to_numeric(top.get("direction_hit_window", pd.Series(dtype=float))).mean())
            if len(top)
            else 0.0,
        },
        "beats_direction_0_40": bool(
            pd.to_numeric(latest["direction_hit_window"], errors="coerce").mean() > 0.40
        ),
    }


def write_prediction_artifacts(
    frames: Mapping[str, pd.DataFrame],
    output_dir: Path,
    prefix: str,
    top_k: int,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result: Dict[str, Any] = {"created_at": _utc_now(), "files": {}, "metrics": {}}
    for mode, df in frames.items():
        path = output_dir / f"{prefix}_{mode}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        metrics = summarize_prediction_frame(df, top_k=top_k)
        metrics_path = path.with_suffix(".metrics.json")
        metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        result["files"][mode] = str(path)
        result["metrics"][mode] = metrics
    comparison_path = output_dir / f"{prefix}_comparison.json"
    comparison_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["comparison_path"] = str(comparison_path)
    return result


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate STOM 1s fine-tuned Kronos checkpoint on holdout split.")
    parser.add_argument("--dataset-path", required=True, help="processed_datasets directory containing test_data.pkl")
    parser.add_argument("--model-path", required=True, help="Fine-tuned Kronos checkpoint or HF model id")
    parser.add_argument("--tokenizer-path", default=DEFAULT_TOKENIZER)
    parser.add_argument("--output-dir", default=str(WEBUI_PREDICTION_DIR))
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--lookback-window", type=int, default=300)
    parser.add_argument("--predict-window", type=int, required=True)
    parser.add_argument("--max-symbols", type=int, default=20)
    parser.add_argument("--max-asofs", type=int, default=1)
    parser.add_argument("--max-sessions", type=int, default=1)
    parser.add_argument("--stride", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--modes", default="kronos,persistence,random")
    parser.add_argument("--seed", type=int, default=100)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    data = load_pickle_dataset(Path(args.dataset_path), split="test")
    windows = select_aligned_windows(
        data,
        lookback_window=args.lookback_window,
        predict_window=args.predict_window,
        max_symbols=args.max_symbols,
        max_asofs=args.max_asofs,
        max_sessions=args.max_sessions,
        stride=args.stride,
    )
    modes = [item.strip() for item in args.modes.split(",") if item.strip()]
    frames: Dict[str, pd.DataFrame] = {}
    if "kronos" in modes:
        kronos = kronos_predictions(
            windows,
            model_path=args.model_path,
            tokenizer_path=args.tokenizer_path,
            device=args.device,
            predict_window=args.predict_window,
            batch_size=args.batch_size,
        )
        frames["kronos"] = rows_from_predictions(windows, kronos, mode="kronos")
    if "persistence" in modes:
        frames["persistence"] = rows_from_predictions(windows, persistence_predictions(windows), mode="persistence")
    if "random" in modes:
        frames["random"] = rows_from_predictions(windows, random_direction_predictions(windows, args.seed), mode="random")
    if not frames:
        raise ValueError("No evaluation modes selected.")

    result = write_prediction_artifacts(frames, Path(args.output_dir), args.prefix, top_k=args.top_k)
    result["dataset_path"] = str(Path(args.dataset_path))
    result["model_path"] = args.model_path
    result["tokenizer_path"] = args.tokenizer_path
    result["lookback_window"] = args.lookback_window
    result["predict_window"] = args.predict_window
    result["selected_windows"] = len(windows)
    result["asof_timestamps"] = sorted({window.history["timestamps"].iloc[-1].isoformat() for window in windows})
    comparison_path = Path(result["comparison_path"])
    comparison_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
