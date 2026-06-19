"""First independent STOM RL model: a fixed-horizon contextual bandit.

This is page 6 of the independent RL lab.  It intentionally avoids Kronos and
new heavy RL dependencies.  The model learns a simple buy-vs-hold decision from
historical STOM episodes:

* context = current/past 1-second OHLCV-derived features only;
* action = buy when predicted 300-second net reward is above threshold, else
  hold;
* reward target = fixed-horizon long return after round-trip cost;
* evaluation = replay on unseen split with trade/action/equity artifacts.

The implementation is deliberately small but complete enough to create, save,
load, and use a trained model artifact.  Later pages can replace this policy
with DQN/PPO while preserving the same artifact and cost-gate comparison shape.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from math import exp, log
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .episode_manifest import DEFAULT_OUTPUT_DIR, load_episode_manifest


DEFAULT_BANDIT_OUTPUT_DIR = Path("webui") / "rl_runs" / "stom_1s_2025_contextual_bandit"
FEATURE_COLUMNS = [
    "ret_1s",
    "ret_5s",
    "ret_30s",
    "ret_60s",
    "ret_120s",
    "ret_300s",
    "range_30s",
    "range_120s",
    "close_vs_ma_30s",
    "close_vs_ma_120s",
    "volume_ratio_30s",
    "amount_ratio_30s",
    "seconds_from_episode_start",
]


@dataclass(frozen=True)
class ContextualBanditConfig:
    """Configuration for training and evaluating the first STOM RL model."""

    manifest_path: str = str(DEFAULT_OUTPUT_DIR / "episode_manifest.json")
    output_dir: str = str(DEFAULT_BANDIT_OUTPUT_DIR)
    train_split: str = "train"
    eval_split: str = "test"
    max_train_episodes: int = 25
    max_eval_episodes: int = 25
    train_sample_stride: int = 10
    eval_sample_stride: int = 1
    seed: int = 100
    lookback_window: int = 300
    reward_horizon_seconds: int = 300
    cost_bps: float = 25.0
    slippage_bps: float = 0.0
    ridge_alpha: float = 1.0
    decision_threshold_bps: float = 0.0
    max_trades_per_episode: float = 50.0
    max_drawdown_pct: float = 20.0
    min_avg_episode_net_pct: float = 0.0
    min_trade_count: int = 1
    write_artifacts: bool = True


@dataclass
class ContextualBanditModel:
    """Serializable ridge-regression contextual bandit model."""

    feature_columns: List[str]
    feature_mean: List[float]
    feature_std: List[float]
    weights: List[float]
    intercept: float
    train_summary: Dict[str, Any]

    def predict_score(self, raw_features: Sequence[float]) -> float:
        features = np.asarray(raw_features, dtype=np.float64)
        mean = np.asarray(self.feature_mean, dtype=np.float64)
        std = np.asarray(self.feature_std, dtype=np.float64)
        weights = np.asarray(self.weights, dtype=np.float64)
        scaled = (features - mean) / np.maximum(std, 1e-9)
        return float(self.intercept + scaled @ weights)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_type": "stom_fixed_horizon_contextual_bandit_ridge",
            "feature_columns": self.feature_columns,
            "feature_mean": self.feature_mean,
            "feature_std": self.feature_std,
            "weights": self.weights,
            "intercept": self.intercept,
            "train_summary": self.train_summary,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextualBanditModel":
        return cls(
            feature_columns=list(payload["feature_columns"]),
            feature_mean=[float(v) for v in payload["feature_mean"]],
            feature_std=[float(v) for v in payload["feature_std"]],
            weights=[float(v) for v in payload["weights"]],
            intercept=float(payload["intercept"]),
            train_summary=dict(payload.get("train_summary", {})),
        )


def save_model(path: Path, model: ContextualBanditModel, config: ContextualBanditConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"config": asdict(config), "model": model.to_dict()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def load_model(path: Path) -> ContextualBanditModel:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return ContextualBanditModel.from_dict(payload["model"])


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load_episode_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"date", "open", "high", "low", "close", "volume", "amount"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Episode CSV missing required columns: {missing}")
    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame[["open", "high", "low", "close", "volume", "amount"]] = frame[
        ["open", "high", "low", "close", "volume", "amount"]
    ].ffill().bfill()
    frame = frame.dropna(subset=["open", "high", "low", "close", "volume", "amount"])
    frame = frame[frame["close"] > 0].reset_index(drop=True)
    if frame.empty:
        raise ValueError(f"Episode CSV has no valid rows: {path}")
    return frame


def _episodes_for_split(manifest_path: str, split: str, max_episodes: int) -> List[Dict[str, Any]]:
    manifest = load_episode_manifest(manifest_path)
    episodes = [dict(episode) for episode in manifest.get("episodes", []) if episode.get("split") == split]
    if max_episodes and max_episodes > 0:
        return episodes[: int(max_episodes)]
    return episodes


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _return_at(frame: pd.DataFrame, idx: int, window: int) -> float:
    past_idx = max(0, int(idx) - int(window))
    past = float(frame["close"].iloc[past_idx])
    current = float(frame["close"].iloc[int(idx)])
    return _safe_ratio(current - past, past)


def _rolling_range(frame: pd.DataFrame, idx: int, window: int) -> float:
    start = max(0, int(idx) - int(window) + 1)
    chunk = frame.iloc[start : int(idx) + 1]
    low = float(chunk["low"].min())
    high = float(chunk["high"].max())
    close = float(frame["close"].iloc[int(idx)])
    return _safe_ratio(high - low, close)


def _current_vs_ma(frame: pd.DataFrame, idx: int, window: int) -> float:
    start = max(0, int(idx) - int(window) + 1)
    chunk = frame.iloc[start : int(idx) + 1]
    current = float(frame["close"].iloc[int(idx)])
    ma = float(chunk["close"].mean())
    return _safe_ratio(current - ma, ma)


def _current_vs_avg(frame: pd.DataFrame, idx: int, column: str, window: int) -> float:
    start = max(0, int(idx) - int(window))
    hist = frame.iloc[start:int(idx)]
    current = float(frame[column].iloc[int(idx)])
    avg = float(hist[column].mean()) if not hist.empty else current
    return _safe_ratio(current, avg) if avg > 0 else 0.0


def _raw_features(frame: pd.DataFrame, idx: int, lookback_window: int) -> List[float]:
    episode_start = max(0, int(idx) - int(lookback_window))
    seconds_from_start = float(int(idx) - episode_start)
    return [
        _return_at(frame, idx, 1),
        _return_at(frame, idx, 5),
        _return_at(frame, idx, 30),
        _return_at(frame, idx, 60),
        _return_at(frame, idx, 120),
        _return_at(frame, idx, 300),
        _rolling_range(frame, idx, 30),
        _rolling_range(frame, idx, 120),
        _current_vs_ma(frame, idx, 30),
        _current_vs_ma(frame, idx, 120),
        _current_vs_avg(frame, idx, "volume", 30),
        _current_vs_avg(frame, idx, "amount", 30),
        seconds_from_start / max(float(lookback_window), 1.0),
    ]


def _round_trip_net_return(frame: pd.DataFrame, idx: int, horizon: int, cost_pct: float) -> float:
    entry = float(frame["close"].iloc[int(idx)])
    exit_price = float(frame["close"].iloc[int(idx) + int(horizon)])
    return float((exit_price / entry) * (1.0 - cost_pct) * (1.0 - cost_pct) - 1.0)


def _iter_sample_indices(frame: pd.DataFrame, config: ContextualBanditConfig, stride: int) -> range:
    start = int(config.lookback_window)
    stop = int(len(frame) - config.reward_horizon_seconds)
    if stop <= start:
        return range(0)
    return range(start, stop, max(1, int(stride)))


def _collect_training_samples(config: ContextualBanditConfig) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    features: List[List[float]] = []
    targets: List[float] = []
    episodes = _episodes_for_split(config.manifest_path, config.train_split, config.max_train_episodes)
    cost_pct = (float(config.cost_bps) + float(config.slippage_bps)) / 10_000.0
    skipped = 0
    for episode in episodes:
        frame = _load_episode_frame(Path(episode["source_csv"]))
        indices = _iter_sample_indices(frame, config, config.train_sample_stride)
        if not indices:
            skipped += 1
            continue
        for idx in indices:
            features.append(_raw_features(frame, idx, config.lookback_window))
            targets.append(_round_trip_net_return(frame, idx, config.reward_horizon_seconds, cost_pct))
    if not features:
        raise ValueError("No training samples collected; check split, episode length, and lookback/horizon.")
    x = np.asarray(features, dtype=np.float64)
    y = np.asarray(targets, dtype=np.float64)
    summary = {
        "train_split": config.train_split,
        "train_episode_count": len(episodes),
        "skipped_episode_count": skipped,
        "train_sample_count": int(len(y)),
        "target_mean_pct": float(np.mean(y) * 100.0),
        "target_median_pct": float(np.median(y) * 100.0),
        "target_positive_rate": float(np.mean(y > 0.0)),
    }
    return x, y, summary


def train_contextual_bandit(config: ContextualBanditConfig) -> ContextualBanditModel:
    """Fit a ridge model that predicts fixed-horizon net buy reward."""

    x, y, summary = _collect_training_samples(config)
    mean = x.mean(axis=0)
    std = np.maximum(x.std(axis=0), 1e-9)
    x_scaled = (x - mean) / std
    design = np.column_stack([np.ones(len(x_scaled)), x_scaled])
    penalty = float(config.ridge_alpha) * np.eye(design.shape[1], dtype=np.float64)
    penalty[0, 0] = 0.0
    coef = np.linalg.solve(design.T @ design + penalty, design.T @ y)
    predictions = design @ coef
    residual = predictions - y
    summary.update(
        {
            "ridge_alpha": float(config.ridge_alpha),
            "train_rmse_pct": float(np.sqrt(np.mean(residual * residual)) * 100.0),
            "predicted_positive_rate": float(np.mean(predictions > (config.decision_threshold_bps / 10_000.0))),
        }
    )
    return ContextualBanditModel(
        feature_columns=list(FEATURE_COLUMNS),
        feature_mean=[float(v) for v in mean],
        feature_std=[float(v) for v in std],
        weights=[float(v) for v in coef[1:]],
        intercept=float(coef[0]),
        train_summary=summary,
    )


def _max_drawdown_pct(equity_values: Sequence[float]) -> float:
    peak = 1.0
    max_dd = 0.0
    for value in equity_values:
        value = float(value)
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, (value / peak) - 1.0)
    return max_dd * 100.0


def _safe_compounded_return_pct(final_equities: Sequence[float]) -> float:
    if not final_equities:
        return 0.0
    total_log = sum(log(max(float(value), 1e-12)) for value in final_equities)
    if total_log > 50:
        return float("inf")
    if total_log < -50:
        return -100.0
    return (exp(total_log) - 1.0) * 100.0


def evaluate_contextual_bandit(
    model: ContextualBanditModel,
    config: ContextualBanditConfig,
) -> Dict[str, Any]:
    """Replay the learned fixed-horizon policy on the eval split."""

    episodes = _episodes_for_split(config.manifest_path, config.eval_split, config.max_eval_episodes)
    threshold = float(config.decision_threshold_bps) / 10_000.0
    cost_pct = (float(config.cost_bps) + float(config.slippage_bps)) / 10_000.0
    action_rows: List[Dict[str, Any]] = []
    trade_rows: List[Dict[str, Any]] = []
    equity_rows: List[Dict[str, Any]] = []
    episode_rows: List[Dict[str, Any]] = []
    aggregate_equity_curve = [1.0]

    for episode in episodes:
        frame = _load_episode_frame(Path(episode["source_csv"]))
        idx_values = list(_iter_sample_indices(frame, config, config.eval_sample_stride))
        if not idx_values:
            continue
        episode_id = str(episode["episode_id"])
        symbol = str(episode.get("symbol"))
        session = str(episode.get("session"))
        episode_equity = 1.0
        episode_base_equity = aggregate_equity_curve[-1]
        trade_count = 0
        action_count = 0
        i = 0
        while i < len(idx_values):
            idx = idx_values[i]
            raw = _raw_features(frame, idx, config.lookback_window)
            score = model.predict_score(raw)
            timestamp = pd.Timestamp(frame["date"].iloc[idx]).isoformat()
            price = float(frame["close"].iloc[idx])
            action = "buy" if score > threshold else "hold"
            action_rows.append(
                {
                    "episode_id": episode_id,
                    "symbol": symbol,
                    "session": session,
                    "step_idx": idx,
                    "timestamp": timestamp,
                    "price": price,
                    "predicted_net_return_pct": score * 100.0,
                    "decision_threshold_pct": threshold * 100.0,
                    "action": action,
                    "equity_before": episode_equity,
                }
            )
            action_count += 1
            if action == "buy":
                exit_idx = int(idx) + int(config.reward_horizon_seconds)
                exit_price = float(frame["close"].iloc[exit_idx])
                exit_timestamp = pd.Timestamp(frame["date"].iloc[exit_idx]).isoformat()
                gross_return = (exit_price - price) / price
                net_return = (exit_price / price) * (1.0 - cost_pct) * (1.0 - cost_pct) - 1.0
                episode_equity *= 1.0 + net_return
                trade_count += 1
                trade_rows.append(
                    {
                        "episode_id": episode_id,
                        "symbol": symbol,
                        "session": session,
                        "entry_timestamp": timestamp,
                        "exit_timestamp": exit_timestamp,
                        "entry_idx": idx,
                        "exit_idx": exit_idx,
                        "entry_price": price,
                        "exit_price": exit_price,
                        "predicted_net_return_pct": score * 100.0,
                        "gross_return_pct": gross_return * 100.0,
                        "net_return_pct": net_return * 100.0,
                        "cost_pct": cost_pct * 100.0,
                    }
                )
                equity_rows.append(
                    {
                        "episode_id": episode_id,
                        "symbol": symbol,
                        "session": session,
                        "timestamp": exit_timestamp,
                        "equity": episode_equity,
                        "trade_count": trade_count,
                    }
                )
                aggregate_equity_curve.append(episode_base_equity * max(episode_equity, 1e-12))
                next_allowed = exit_idx + 1
                while i < len(idx_values) and idx_values[i] < next_allowed:
                    i += 1
                continue
            equity_rows.append(
                {
                    "episode_id": episode_id,
                    "symbol": symbol,
                    "session": session,
                    "timestamp": timestamp,
                    "equity": episode_equity,
                    "trade_count": trade_count,
                }
            )
            i += 1
        if not trade_count:
            aggregate_equity_curve.append(episode_base_equity)
        episode_rows.append(
            {
                "episode_id": episode_id,
                "symbol": symbol,
                "session": session,
                "final_equity": episode_equity,
                "episode_return_pct": (episode_equity - 1.0) * 100.0,
                "trade_count": trade_count,
                "action_count": action_count,
            }
        )

    final_equities = [float(row["final_equity"]) for row in episode_rows]
    trade_returns = [float(row["net_return_pct"]) for row in trade_rows]
    hit_count = sum(1 for value in trade_returns if value > 0)
    episode_count = len(episode_rows)
    trade_count = len(trade_rows)
    trades_per_episode = trade_count / episode_count if episode_count else 0.0
    avg_net = float(np.mean([row["episode_return_pct"] for row in episode_rows])) if episode_rows else 0.0
    max_dd = _max_drawdown_pct(aggregate_equity_curve)
    passes_cost_gate = bool(
        avg_net > float(config.min_avg_episode_net_pct)
        and max_dd >= -abs(float(config.max_drawdown_pct))
        and trades_per_episode <= float(config.max_trades_per_episode)
        and trade_count >= int(config.min_trade_count)
    )
    summary = {
        "policy": "contextual_bandit",
        "eval_split": config.eval_split,
        "episode_count": episode_count,
        "action_count": len(action_rows),
        "trade_count": trade_count,
        "trades_per_episode": trades_per_episode,
        "avg_episode_net_return_pct": avg_net,
        "median_episode_net_return_pct": float(np.median([row["episode_return_pct"] for row in episode_rows]))
        if episode_rows
        else 0.0,
        "compounded_return_pct": _safe_compounded_return_pct(final_equities),
        "avg_trade_net_return_pct": float(np.mean(trade_returns)) if trade_returns else 0.0,
        "hit_rate": hit_count / len(trade_returns) if trade_returns else 0.0,
        "max_drawdown_pct": max_dd,
        "passes_cost_gate": passes_cost_gate,
        "threshold_bps": float(config.decision_threshold_bps),
        "cost_bps": float(config.cost_bps),
        "slippage_bps": float(config.slippage_bps),
    }
    return {
        "summary": summary,
        "episodes": episode_rows,
        "trades": trade_rows,
        "actions": action_rows,
        "equity": equity_rows,
    }


def run_contextual_bandit(config: ContextualBanditConfig) -> Dict[str, Any]:
    """Train, save, evaluate, and optionally write all model artifacts."""

    output_dir = Path(config.output_dir)
    model = train_contextual_bandit(config)
    evaluation = evaluate_contextual_bandit(model, config)
    payload = {
        "mode": "stom_rl_contextual_bandit",
        "config": asdict(config),
        "model": model.to_dict(),
        "eval_summary": evaluation["summary"],
        "artifacts": {
            "output_dir": str(output_dir),
            "config_json": str(output_dir / "config.json"),
            "model_json": str(output_dir / "model.json"),
            "train_metrics_jsonl": str(output_dir / "train_metrics.jsonl"),
            "eval_summary_json": str(output_dir / "eval_summary.json"),
            "actions_csv": str(output_dir / "actions.csv"),
            "trades_csv": str(output_dir / "trades.csv"),
            "equity_curve_csv": str(output_dir / "equity_curve.csv"),
            "episodes_csv": str(output_dir / "episodes.csv"),
        },
    }
    if config.write_artifacts:
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(output_dir / "config.json", {"config": asdict(config)})
        save_model(output_dir / "model.json", model, config)
        with (output_dir / "train_metrics.jsonl").open("w", encoding="utf-8-sig") as f:
            f.write(json.dumps(model.train_summary, ensure_ascii=False) + "\n")
        _write_json(output_dir / "eval_summary.json", payload)
        _write_csv(
            output_dir / "actions.csv",
            evaluation["actions"],
            [
                "episode_id",
                "symbol",
                "session",
                "step_idx",
                "timestamp",
                "price",
                "predicted_net_return_pct",
                "decision_threshold_pct",
                "action",
                "equity_before",
            ],
        )
        _write_csv(
            output_dir / "trades.csv",
            evaluation["trades"],
            [
                "episode_id",
                "symbol",
                "session",
                "entry_timestamp",
                "exit_timestamp",
                "entry_idx",
                "exit_idx",
                "entry_price",
                "exit_price",
                "predicted_net_return_pct",
                "gross_return_pct",
                "net_return_pct",
                "cost_pct",
            ],
        )
        _write_csv(
            output_dir / "equity_curve.csv",
            evaluation["equity"],
            ["episode_id", "symbol", "session", "timestamp", "equity", "trade_count"],
        )
        _write_csv(
            output_dir / "episodes.csv",
            evaluation["episodes"],
            ["episode_id", "symbol", "session", "final_equity", "episode_return_pct", "trade_count", "action_count"],
        )
    return payload


def _parse_args(argv: Optional[Sequence[str]] = None) -> ContextualBanditConfig:
    parser = argparse.ArgumentParser(description="Train/evaluate STOM contextual-bandit RL prototype.")
    parser.add_argument("--manifest", default=str(DEFAULT_OUTPUT_DIR / "episode_manifest.json"))
    parser.add_argument("--output-dir", default=str(DEFAULT_BANDIT_OUTPUT_DIR))
    parser.add_argument("--train-split", default="train")
    parser.add_argument("--eval-split", default="test")
    parser.add_argument("--max-train-episodes", type=int, default=25)
    parser.add_argument("--max-eval-episodes", type=int, default=25)
    parser.add_argument("--train-sample-stride", type=int, default=10)
    parser.add_argument("--eval-sample-stride", type=int, default=1)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--lookback-window", type=int, default=300)
    parser.add_argument("--reward-horizon-seconds", type=int, default=300)
    parser.add_argument("--cost-bps", type=float, default=25.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--ridge-alpha", type=float, default=1.0)
    parser.add_argument("--decision-threshold-bps", type=float, default=0.0)
    parser.add_argument("--max-trades-per-episode", type=float, default=50.0)
    parser.add_argument("--max-drawdown-pct", type=float, default=20.0)
    parser.add_argument("--min-avg-episode-net-pct", type=float, default=0.0)
    parser.add_argument("--min-trade-count", type=int, default=1)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    return ContextualBanditConfig(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        train_split=args.train_split,
        eval_split=args.eval_split,
        max_train_episodes=args.max_train_episodes,
        max_eval_episodes=args.max_eval_episodes,
        train_sample_stride=args.train_sample_stride,
        eval_sample_stride=args.eval_sample_stride,
        seed=args.seed,
        lookback_window=args.lookback_window,
        reward_horizon_seconds=args.reward_horizon_seconds,
        cost_bps=args.cost_bps,
        slippage_bps=args.slippage_bps,
        ridge_alpha=args.ridge_alpha,
        decision_threshold_bps=args.decision_threshold_bps,
        max_trades_per_episode=args.max_trades_per_episode,
        max_drawdown_pct=args.max_drawdown_pct,
        min_avg_episode_net_pct=args.min_avg_episode_net_pct,
        min_trade_count=args.min_trade_count,
        write_artifacts=not args.no_write,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    payload = run_contextual_bandit(_parse_args(argv))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
