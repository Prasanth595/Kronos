"""Walk-forward (time-period) validation of saved STOM SB3 models (no retraining).

Evaluates a SAVED Stable-Baselines3 model across sequential, contiguous time
periods (folds) to detect overfitting / regime sensitivity. No training happens
here -- the model is loaded and replayed fold by fold.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .episode_manifest import DEFAULT_OUTPUT_DIR
from .sb3_smoke import (
    DEFAULT_ALGORITHMS,
    Sb3SmokeConfig,
    _evaluate_model,
    _make_env,
    _max_drawdown_pct,
    _safe_compounded_return_pct,
    _torch_runtime,
    _write_csv,
    _write_json,
)


DEFAULT_WALK_FORWARD_OUTPUT_DIR = Path("webui") / "rl_runs" / "stom_1s_2025_walk_forward"


@dataclass(frozen=True)
class WalkForwardConfig:
    """Configuration for walk-forward time-period validation of saved SB3 models."""

    model_dir: str
    algorithms: Tuple[str, ...] = ("dqn", "ppo")
    eval_split: str = "test"
    n_folds: int = 6
    max_episodes_per_fold: int = 30
    max_eval_steps_per_episode: int = 2048
    manifest_path: str = str(DEFAULT_OUTPUT_DIR / "episode_manifest.json")
    seed: int = 100
    lookback_window: int = 300
    reward_horizon_seconds: int = 300
    cost_bps: float = 25.0
    slippage_bps: float = 0.0
    device: str = "auto"
    output_dir: Optional[str] = None
    write_artifacts: bool = True
    source_run: Optional[str] = None


def _parse_algorithms(raw: str) -> Tuple[str, ...]:
    algorithms = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    unknown = sorted(set(algorithms) - set(DEFAULT_ALGORITHMS))
    if unknown:
        raise ValueError(f"Unknown SB3 algorithms: {unknown}. Available: {sorted(DEFAULT_ALGORITHMS)}")
    return algorithms


def _source_model_name(algorithm: str, training_timesteps: int, fallback: Optional[str]) -> str:
    """Mirror performance_leaderboard._sb3_model_name suffix logic for the source model."""

    timesteps = int(training_timesteps)
    if timesteps >= 1000:
        suffix = f"{timesteps // 1000}k" if timesteps % 1000 == 0 else str(timesteps)
        return f"{algorithm}_{suffix}"
    return str(fallback) if fallback else f"{algorithm}_smoke"


def _resolve_output_dir(config: WalkForwardConfig) -> Path:
    if config.output_dir:
        return Path(config.output_dir)
    return DEFAULT_WALK_FORWARD_OUTPUT_DIR


def _load_source_summary(model_dir: Path) -> Dict[str, Any]:
    summary_path = model_dir / "sb3_smoke_summary.json"
    if not summary_path.is_file():
        return {}
    try:
        return json.loads(summary_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def _source_row_for_algorithm(source_summary: Dict[str, Any], algorithm: str) -> Dict[str, Any]:
    for row in source_summary.get("models") or []:
        if str(row.get("algorithm") or "").lower() == algorithm:
            return dict(row)
    return {}


def _load_model(algorithm: str, model_path: Path, device: str) -> Any:
    from stable_baselines3 import DQN, PPO

    loaders = {"dqn": DQN, "ppo": PPO}
    loader = loaders.get(algorithm)
    if loader is None:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    return loader.load(str(model_path), device=device)


def _subsample_indices(indices: Sequence[int], cap: int) -> List[int]:
    """Evenly (deterministically) subsample ``indices`` down to at most ``cap`` items.

    Preserves order and always keeps the first and last entries when cap >= 2.
    """

    indices = list(indices)
    if cap <= 0 or len(indices) <= cap:
        return indices
    positions = np.linspace(0, len(indices) - 1, num=cap)
    chosen = sorted({int(round(pos)) for pos in positions})
    return [indices[pos] for pos in chosen]


def _build_session_folds(
    episodes: Sequence[Dict[str, Any]],
    n_folds: int,
    max_episodes_per_fold: int,
) -> List[Dict[str, Any]]:
    """Partition time-ordered episodes into ``n_folds`` contiguous folds by session date.

    Folds are split on unique sorted session boundaries so a single session never
    spans two folds. Each fold gets a roughly equal contiguous bin of sessions.
    Folds exceeding ``max_episodes_per_fold`` are evenly subsampled (deterministic).
    Empty folds (when there are fewer unique sessions than folds) are dropped.
    """

    if n_folds <= 0:
        raise ValueError("n_folds must be positive")

    # episode index -> session, in time order (episodes already time-ordered by session).
    sessions = [str(ep.get("session")) for ep in episodes]
    unique_sessions = sorted(set(sessions))
    if not unique_sessions:
        return []

    n_bins = min(n_folds, len(unique_sessions))
    # Contiguous, roughly-equal session bins via numpy array_split.
    session_bins = [list(bin_) for bin_ in np.array_split(np.asarray(unique_sessions), n_bins)]

    folds: List[Dict[str, Any]] = []
    for fold_index, bin_sessions in enumerate(session_bins):
        bin_set = set(bin_sessions)
        fold_indices = [idx for idx, session in enumerate(sessions) if session in bin_set]
        if not fold_indices:
            continue
        fold_indices = _subsample_indices(fold_indices, max_episodes_per_fold)
        fold_sessions = sorted({sessions[idx] for idx in fold_indices})
        folds.append(
            {
                "fold_index": fold_index,
                "episode_indices": fold_indices,
                "period_start": fold_sessions[0],
                "period_end": fold_sessions[-1],
                "episode_count": len(fold_indices),
            }
        )
    return folds


# Consistency verdict rule:
#   * "consistent"      -> every fold's avg_net is positive AND the spread is tight,
#                          i.e. folds_positive == n_folds and std <= 0.5 * abs(mean).
#   * "regime_sensitive"-> some but not all folds positive (1 <= folds_positive <= n_folds-1).
#   * "unstable"        -> folds_positive <= 1 OR mean_fold_avg_net <= 0.
def _consistency_verdict(fold_avg_nets: Sequence[float]) -> str:
    n = len(fold_avg_nets)
    if n == 0:
        return "unstable"
    values = np.asarray(fold_avg_nets, dtype=np.float64)
    folds_positive = int(np.sum(values > 0.0))
    mean = float(np.mean(values))
    std = float(np.std(values))
    if folds_positive <= 1 or mean <= 0.0:
        return "unstable"
    if folds_positive == n and std <= 0.5 * abs(mean):
        return "consistent"
    return "regime_sensitive"


def _summarize_fold(
    episode_rows: Sequence[Dict[str, Any]],
    trade_rows: Sequence[Dict[str, Any]],
    aggregate_equity_curve: Sequence[float],
    config: WalkForwardConfig,
) -> Dict[str, Any]:
    """Summarize a single fold's evaluation results (mirrors _summarize_model gates)."""

    returns = np.asarray([float(row["episode_return_pct"]) for row in episode_rows], dtype=np.float64)
    final_equities = [float(row["final_equity"]) for row in episode_rows]
    trade_returns = np.asarray([float(row["net_return_pct"]) for row in trade_rows], dtype=np.float64)
    avg_net = float(np.mean(returns)) if len(returns) else 0.0
    max_dd = _max_drawdown_pct(aggregate_equity_curve)
    trade_count = len(trade_rows)
    episode_count = len(episode_rows)
    # Same gate logic as sb3_smoke._summarize_model (defaults: min_avg=0, max_dd=20, min_trade=1).
    passes_cost_gate = bool(
        avg_net > 0.0
        and max_dd >= -20.0
        and trade_count >= 1
    )
    return {
        "episode_count": episode_count,
        "trade_count": trade_count,
        "trades_per_episode": float(trade_count / episode_count) if episode_count else 0.0,
        "avg_episode_net_return_pct": avg_net,
        "median_episode_net_return_pct": float(np.median(returns)) if len(returns) else 0.0,
        "compounded_return_pct": _safe_compounded_return_pct(final_equities),
        "avg_trade_net_return_pct": float(np.mean(trade_returns)) if len(trade_returns) else 0.0,
        "hit_rate": float(np.mean(trade_returns > 0.0)) if len(trade_returns) else 0.0,
        "max_drawdown_pct": max_dd,
        "passes_cost_gate": passes_cost_gate,
    }


def _smoke_config_for_walk_forward(config: WalkForwardConfig, algorithm: str, output_dir: Path) -> Sb3SmokeConfig:
    return Sb3SmokeConfig(
        manifest_path=config.manifest_path,
        output_dir=str(output_dir),
        eval_split=config.eval_split,
        algorithms=(algorithm,),
        total_timesteps=0,
        # Large cap so explicit episode_indices are never truncated by the gate inside _evaluate_model.
        max_eval_episodes=10_000_000,
        max_eval_steps_per_episode=config.max_eval_steps_per_episode,
        seed=config.seed,
        lookback_window=config.lookback_window,
        reward_horizon_seconds=config.reward_horizon_seconds,
        cost_bps=config.cost_bps,
        slippage_bps=config.slippage_bps,
        device=config.device,
        write_artifacts=False,
        write_live_events=False,
    )


def run_walk_forward(config: WalkForwardConfig) -> Dict[str, Any]:
    """Evaluate saved SB3 models across contiguous time-period folds (no training)."""

    algorithms = tuple(config.algorithms)
    if not algorithms:
        raise ValueError("At least one SB3 algorithm is required.")

    model_dir = Path(config.model_dir)
    source_run = config.source_run or model_dir.name
    source_summary = _load_source_summary(model_dir)
    output_dir = _resolve_output_dir(config)
    runtime = _torch_runtime()

    # 1. Build one probe env to read the (time-ordered) eval-split episodes.
    probe_smoke_config = _smoke_config_for_walk_forward(config, algorithms[0], output_dir)
    probe = _make_env(probe_smoke_config, split=config.eval_split)
    episodes = list(probe.raw_env.episodes)
    probe.close()

    # 2. Partition into contiguous session-date folds.
    folds = _build_session_folds(episodes, config.n_folds, config.max_episodes_per_fold)

    fold_rows: List[Dict[str, Any]] = []
    per_algorithm: List[Dict[str, Any]] = []
    evaluated_algorithms: List[str] = []
    skipped: List[Dict[str, str]] = []

    for algorithm in algorithms:
        model_path = model_dir / f"{algorithm}_model.zip"
        if not model_path.is_file():
            message = f"Skipping {algorithm}: model file not found at {model_path}"
            print(message)
            skipped.append({"algorithm": algorithm, "reason": str(model_path)})
            continue

        source_row = _source_row_for_algorithm(source_summary, algorithm)
        source_timesteps = int(float(source_row.get("training_timesteps") or 0))
        source_model = _source_model_name(algorithm, source_timesteps, source_row.get("model"))

        smoke_config = _smoke_config_for_walk_forward(config, algorithm, output_dir)
        model = _load_model(algorithm, model_path, config.device)

        algo_fold_metrics: List[Dict[str, Any]] = []
        for fold in folds:
            evaluation = _evaluate_model(
                model,
                algorithm,
                smoke_config,
                episode_indices=fold["episode_indices"],
            )
            metrics = _summarize_fold(
                evaluation["episodes"],
                evaluation["trades"],
                evaluation["aggregate_equity_curve"],
                config,
            )
            row = {
                "algorithm": algorithm,
                "source_run": source_run,
                "source_model": source_model,
                "fold_index": fold["fold_index"],
                "period_start": fold["period_start"],
                "period_end": fold["period_end"],
                **metrics,
            }
            fold_rows.append(row)
            algo_fold_metrics.append(row)

        fold_avg_nets = [float(row["avg_episode_net_return_pct"]) for row in algo_fold_metrics]
        n_evaluated_folds = len(fold_avg_nets)
        folds_positive = int(sum(1 for value in fold_avg_nets if value > 0.0))
        mean_avg = float(np.mean(fold_avg_nets)) if fold_avg_nets else 0.0
        std_avg = float(np.std(fold_avg_nets)) if fold_avg_nets else 0.0
        worst_dd = (
            float(min(float(row["max_drawdown_pct"]) for row in algo_fold_metrics))
            if algo_fold_metrics
            else 0.0
        )
        per_algorithm.append(
            {
                "algorithm": algorithm,
                "source_run": source_run,
                "source_model": source_model,
                "n_folds": n_evaluated_folds,
                "folds_positive": folds_positive,
                "mean_fold_avg_net": mean_avg,
                "std_fold_avg_net": std_avg,
                "min_fold_avg_net": float(min(fold_avg_nets)) if fold_avg_nets else 0.0,
                "max_fold_avg_net": float(max(fold_avg_nets)) if fold_avg_nets else 0.0,
                "worst_fold_max_drawdown_pct": worst_dd,
                "consistency": _consistency_verdict(fold_avg_nets),
            }
        )
        evaluated_algorithms.append(algorithm)

    ranking = sorted(per_algorithm, key=lambda row: float(row["mean_fold_avg_net"]), reverse=True)
    summary: Dict[str, Any] = {
        "algorithm_count": len(evaluated_algorithms),
        "algorithms": list(evaluated_algorithms),
        "skipped_algorithms": skipped,
        "source_run": source_run,
        "n_folds": len(folds),
        "fold_periods": [
            {
                "fold_index": fold["fold_index"],
                "period_start": fold["period_start"],
                "period_end": fold["period_end"],
                "episode_count": fold["episode_count"],
            }
            for fold in folds
        ],
        "per_algorithm": per_algorithm,
        "best_algorithm_by_mean_fold_avg_net": ranking[0]["algorithm"] if ranking else None,
        "best_model": ranking[0]["source_model"] if ranking else None,
        "device_requested": config.device,
        "cuda_available": runtime["cuda_available"],
    }

    payload: Dict[str, Any] = {
        "mode": "stom_rl_walk_forward",
        "config": asdict(config),
        "runtime": runtime,
        "summary": summary,
        "folds": fold_rows,
        "artifacts": {
            "output_dir": str(output_dir),
            "report_json": str(output_dir / "walk_forward_report.json"),
            "folds_csv": str(output_dir / "walk_forward_folds.csv"),
        },
    }

    if config.write_artifacts:
        _write_json(output_dir / "walk_forward_report.json", payload)
        _write_csv(
            output_dir / "walk_forward_folds.csv",
            fold_rows,
            [
                "algorithm",
                "source_run",
                "source_model",
                "fold_index",
                "period_start",
                "period_end",
                "episode_count",
                "trade_count",
                "trades_per_episode",
                "avg_episode_net_return_pct",
                "median_episode_net_return_pct",
                "compounded_return_pct",
                "avg_trade_net_return_pct",
                "hit_rate",
                "max_drawdown_pct",
                "passes_cost_gate",
            ],
        )
    return payload


def _parse_args(argv: Optional[Sequence[str]] = None) -> WalkForwardConfig:
    parser = argparse.ArgumentParser(
        description="Walk-forward (time-period) validation of saved STOM SB3 models without retraining.",
    )
    parser.add_argument("--model-dir", required=True, help="Directory containing {algo}_model.zip and source summary.")
    parser.add_argument("--algorithms", default=",".join(("dqn", "ppo")))
    parser.add_argument("--n-folds", type=int, default=6)
    parser.add_argument("--max-episodes-per-fold", type=int, default=30)
    parser.add_argument("--eval-split", default="test")
    parser.add_argument("--max-eval-steps-per-episode", type=int, default=2048)
    parser.add_argument("--manifest", default=str(DEFAULT_OUTPUT_DIR / "episode_manifest.json"))
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--cost-bps", type=float, default=25.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--source-run", default=None)
    args = parser.parse_args(argv)
    return WalkForwardConfig(
        model_dir=args.model_dir,
        algorithms=_parse_algorithms(args.algorithms),
        n_folds=args.n_folds,
        max_episodes_per_fold=args.max_episodes_per_fold,
        eval_split=args.eval_split,
        max_eval_steps_per_episode=args.max_eval_steps_per_episode,
        manifest_path=args.manifest,
        seed=args.seed,
        cost_bps=args.cost_bps,
        slippage_bps=args.slippage_bps,
        device=args.device,
        output_dir=args.output_dir,
        write_artifacts=not args.no_write,
        source_run=args.source_run,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    payload = run_walk_forward(_parse_args(argv))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
