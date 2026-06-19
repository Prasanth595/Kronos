"""Stable-Baselines3 smoke training for the STOM trading environment."""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import asdict, dataclass
from math import exp, log
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .baselines import AccountState
from .episode_manifest import DEFAULT_OUTPUT_DIR
from .rl_events import RlLiveEventWriter, summarize_live_event_file
from .sb3_adapter import StomTickTradingGymEnv, make_sb3_env


DEFAULT_SB3_SMOKE_OUTPUT_DIR = Path("webui") / "rl_runs" / "stom_1s_2025_sb3_smoke"
DEFAULT_ALGORITHMS = ("dqn", "ppo")


@dataclass(frozen=True)
class Sb3SmokeConfig:
    """Configuration for dependency, env-check, DQN, and PPO smoke validation."""

    manifest_path: str = str(DEFAULT_OUTPUT_DIR / "episode_manifest.json")
    output_dir: str = str(DEFAULT_SB3_SMOKE_OUTPUT_DIR)
    train_split: str = "train"
    eval_split: str = "test"
    algorithms: Tuple[str, ...] = DEFAULT_ALGORITHMS
    total_timesteps: int = 256
    max_eval_episodes: int = 2
    max_eval_steps_per_episode: int = 256
    seed: int = 100
    lookback_window: int = 300
    reward_horizon_seconds: int = 300
    cost_bps: float = 25.0
    slippage_bps: float = 0.0
    device: str = "auto"
    dqn_learning_starts: int = 16
    dqn_buffer_size: int = 1024
    dqn_batch_size: int = 32
    ppo_n_steps: int = 64
    ppo_batch_size: int = 32
    ppo_n_epochs: int = 1
    min_trade_count: int = 1
    min_avg_episode_net_pct: float = 0.0
    max_drawdown_pct: float = 20.0
    write_artifacts: bool = True
    write_live_events: bool = True
    live_event_sample_interval: int = 1


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _parse_algorithms(raw: str) -> Tuple[str, ...]:
    algorithms = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    unknown = sorted(set(algorithms) - set(DEFAULT_ALGORITHMS))
    if unknown:
        raise ValueError(f"Unknown SB3 algorithms: {unknown}. Available: {sorted(DEFAULT_ALGORITHMS)}")
    return algorithms


def _sb3_imports():
    from stable_baselines3 import DQN, PPO
    from stable_baselines3.common.env_checker import check_env

    return DQN, PPO, check_env


def _torch_runtime() -> Dict[str, Any]:
    import torch

    return {
        "torch_version": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_version": torch.version.cuda,
        "cuda_device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


def _make_env(config: Sb3SmokeConfig, *, split: str, episode_index: Optional[int] = None) -> StomTickTradingGymEnv:
    return make_sb3_env(
        config.manifest_path,
        split=split,
        seed=config.seed,
        episode_index=episode_index,
        lookback_window=config.lookback_window,
        reward_horizon_seconds=config.reward_horizon_seconds,
        cost_bps=config.cost_bps,
        slippage_bps=config.slippage_bps,
        reward_mode="horizon",
    )


def _check_env(config: Sb3SmokeConfig) -> Dict[str, Any]:
    _, _, check_env = _sb3_imports()
    env = _make_env(config, split=config.train_split, episode_index=0)
    try:
        check_env(env, warn=True, skip_render_check=True)
        return {
            "passed": True,
            "observation_space": str(env.observation_space),
            "action_space": str(env.action_space),
            "feature_columns": list(env.raw_env.feature_columns),
        }
    finally:
        env.close()


def _bounded_batch_size(value: int, *, upper: int) -> int:
    return max(2, min(int(value), int(upper)))


def _train_model(algorithm: str, config: Sb3SmokeConfig, event_writer: Optional[RlLiveEventWriter] = None):
    DQN, PPO, _ = _sb3_imports()
    from stable_baselines3.common.callbacks import BaseCallback

    class LiveEventCallback(BaseCallback):
        def __init__(self, writer: Optional[RlLiveEventWriter], *, algorithm: str, sample_interval: int):
            super().__init__(verbose=0)
            self.writer = writer
            self.algorithm = algorithm
            self.sample_interval = max(1, int(sample_interval))

        def _on_step(self) -> bool:
            if self.writer is None or self.num_timesteps % self.sample_interval:
                return True
            rewards = self.locals.get("rewards")
            actions = self.locals.get("actions")
            infos = self.locals.get("infos")
            rewards = rewards if rewards is not None else []
            actions = actions if actions is not None else []
            infos = infos if infos is not None else []
            reward = rewards[0] if len(rewards) else None
            action = actions[0] if len(actions) else None
            info = dict(infos[0]) if len(infos) else {}
            action_value: Optional[int]
            if action is None:
                action_value = None
            elif hasattr(action, "item"):
                action_value = int(action.item())
            else:
                action_array = np.asarray(action)
                action_value = int(action_array.item()) if action_array.size else None
            self.writer.write_step(
                algorithm=self.algorithm,
                phase="train",
                global_step=int(self.num_timesteps),
                episode_id=info.get("episode_id"),
                timestamp=info.get("action_timestamp"),
                price=info.get("close"),
                action=action_value,
                reward=float(reward) if reward is not None else None,
                position=info.get("position_after"),
                equity=None,
                exploration=getattr(self.model, "exploration_rate", None),
                info={
                    "event": info.get("event"),
                    "split": info.get("split"),
                    "current_idx": info.get("current_idx"),
                    "invalid_action": info.get("invalid_action"),
                    "trade_count": info.get("trade_count"),
                },
            )
            return True

    env = _make_env(config, split=config.train_split)
    policy_kwargs = {"net_arch": [64, 32]}
    try:
        if algorithm == "dqn":
            learning_starts = max(1, min(int(config.dqn_learning_starts), max(1, int(config.total_timesteps) // 4)))
            model = DQN(
                "MlpPolicy",
                env,
                seed=config.seed,
                device=config.device,
                verbose=0,
                learning_starts=learning_starts,
                buffer_size=max(int(config.dqn_buffer_size), int(config.total_timesteps) * 2, 64),
                batch_size=_bounded_batch_size(config.dqn_batch_size, upper=max(2, int(config.total_timesteps))),
                train_freq=4,
                gradient_steps=1,
                target_update_interval=64,
                exploration_fraction=0.4,
                exploration_final_eps=0.05,
                policy_kwargs=policy_kwargs,
            )
        elif algorithm == "ppo":
            n_steps = max(8, min(int(config.ppo_n_steps), max(8, int(config.total_timesteps))))
            model = PPO(
                "MlpPolicy",
                env,
                seed=config.seed,
                device=config.device,
                verbose=0,
                n_steps=n_steps,
                batch_size=_bounded_batch_size(config.ppo_batch_size, upper=n_steps),
                n_epochs=max(1, int(config.ppo_n_epochs)),
                policy_kwargs=policy_kwargs,
            )
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")
        started = time.perf_counter()
        model.learn(
            total_timesteps=int(config.total_timesteps),
            progress_bar=False,
            callback=LiveEventCallback(
                event_writer,
                algorithm=algorithm,
                sample_interval=config.live_event_sample_interval,
            ),
        )
        elapsed = time.perf_counter() - started
        if getattr(model, "env", None) is not None:
            model.env.close()
        return model, elapsed
    finally:
        env.close()


def _safe_compounded_return_pct(final_equities: Sequence[float]) -> float:
    if not final_equities:
        return 0.0
    total_log = sum(log(max(float(value), 1e-12)) for value in final_equities)
    if total_log > 50:
        return float("inf")
    if total_log < -50:
        return -100.0
    return (exp(total_log) - 1.0) * 100.0


def _max_drawdown_pct(equity_values: Sequence[float]) -> float:
    peak = 1.0
    max_dd = 0.0
    for value in equity_values:
        value = float(value)
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, (value / peak) - 1.0)
    return max_dd * 100.0


def _summarize_model(
    *,
    algorithm: str,
    config: Sb3SmokeConfig,
    episode_rows: Sequence[Mapping[str, Any]],
    trade_rows: Sequence[Mapping[str, Any]],
    aggregate_equity_curve: Sequence[float],
    training_elapsed_seconds: float,
    model_name: Optional[str] = None,
    eval_only: bool = False,
    source_run: Optional[str] = None,
    source_model: Optional[str] = None,
    is_smoke: Optional[bool] = None,
) -> Dict[str, Any]:
    returns = np.asarray([float(row["episode_return_pct"]) for row in episode_rows], dtype=np.float64)
    final_equities = [float(row["final_equity"]) for row in episode_rows]
    trade_returns = np.asarray([float(row["net_return_pct"]) for row in trade_rows], dtype=np.float64)
    avg_net = float(np.mean(returns)) if len(returns) else 0.0
    max_dd = _max_drawdown_pct(aggregate_equity_curve)
    trade_count = len(trade_rows)
    episode_count = len(episode_rows)
    passes_cost_gate = bool(
        avg_net > float(config.min_avg_episode_net_pct)
        and max_dd >= -abs(float(config.max_drawdown_pct))
        and trade_count >= int(config.min_trade_count)
    )
    resolved_is_smoke = bool(is_smoke) if is_smoke is not None else True
    summary: Dict[str, Any] = {
        "algorithm": algorithm,
        "model": str(model_name) if model_name is not None else f"{algorithm}_smoke",
        "policy": f"stable_baselines3_{algorithm}",
        "eval_split": config.eval_split,
        "training_timesteps": int(config.total_timesteps),
        "training_elapsed_seconds": float(training_elapsed_seconds),
        "episode_count": episode_count,
        "trade_count": trade_count,
        "trades_per_episode": float(trade_count / episode_count) if episode_rows else 0.0,
        "avg_episode_net_return_pct": avg_net,
        "median_episode_net_return_pct": float(np.median(returns)) if len(returns) else 0.0,
        "compounded_return_pct": _safe_compounded_return_pct(final_equities),
        "avg_trade_net_return_pct": float(np.mean(trade_returns)) if len(trade_returns) else 0.0,
        "hit_rate": float(np.mean(trade_returns > 0.0)) if len(trade_returns) else 0.0,
        "max_drawdown_pct": max_dd,
        "passes_cost_gate": passes_cost_gate,
        "is_smoke": resolved_is_smoke,
        "eval_only": bool(eval_only),
        "source_run": source_run,
        "source_model": source_model,
        "cost_bps": float(config.cost_bps),
        "slippage_bps": float(config.slippage_bps),
    }
    if eval_only:
        summary["eval_episode_count"] = episode_count
    return summary


def _evaluate_model(
    model: Any,
    algorithm: str,
    config: Sb3SmokeConfig,
    event_writer: Optional[RlLiveEventWriter] = None,
    episode_indices: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    if episode_indices is None:
        probe_env = _make_env(config, split=config.eval_split)
        eval_episode_count = len(probe_env.raw_env.episodes)
        probe_env.close()
        if config.max_eval_episodes and config.max_eval_episodes > 0:
            eval_episode_count = min(eval_episode_count, int(config.max_eval_episodes))
        evaluation_indices: Sequence[int] = range(eval_episode_count)
    else:
        evaluation_indices = list(episode_indices)

    action_rows: List[Dict[str, Any]] = []
    equity_rows: List[Dict[str, Any]] = []
    trade_rows: List[Dict[str, Any]] = []
    episode_rows: List[Dict[str, Any]] = []
    aggregate_equity_curve = [1.0]
    policy_name = f"stable_baselines3_{algorithm}"

    for episode_index in evaluation_indices:
        env = _make_env(config, split=config.eval_split, episode_index=episode_index)
        observation, info = env.reset(seed=config.seed + episode_index)
        raw_env = env.raw_env
        account = AccountState(cost_pct=(config.cost_bps + config.slippage_bps) / 10_000.0)
        terminated = False
        truncated = False
        step_counter = 0
        episode_equity_curve = [1.0]

        while not (terminated or truncated):
            if config.max_eval_steps_per_episode and step_counter >= int(config.max_eval_steps_per_episode):
                break
            price = raw_env._close_at(raw_env.current_idx)
            timestamp = raw_env._timestamp_at(raw_env.current_idx)
            action, _ = model.predict(observation, deterministic=True)
            action_int = int(np.asarray(action).item())
            observation, reward, terminated, truncated, step_info = env.step(action_int)
            trade = account.apply_action(
                action=action_int,
                price=price,
                timestamp=timestamp,
                episode_id=str(info["episode_id"]),
                policy=policy_name,
            )
            if trade:
                trade.update({"model": f"{algorithm}_smoke", "algorithm": algorithm})
                trade_rows.append(trade)
            mark_equity = account.mark_equity(price)
            episode_equity_curve.append(mark_equity)
            action_row = {
                "model": f"{algorithm}_smoke",
                "algorithm": algorithm,
                "policy": policy_name,
                "episode_id": info["episode_id"],
                "symbol": info["symbol"],
                "session": info["session"],
                "step_idx": info["current_idx"],
                "timestamp": timestamp,
                "price": price,
                "action": action_int,
                "action_name": step_info.get("action_name"),
                "position_after": account.position,
                "env_reward": reward,
                "mark_equity": mark_equity,
                "invalid_action": step_info.get("invalid_action"),
            }
            action_rows.append(action_row)
            if event_writer is not None:
                event_writer.write_step(
                    algorithm=algorithm,
                    phase="eval",
                    global_step=len(action_rows),
                    episode=episode_index,
                    episode_id=str(info["episode_id"]),
                    timestamp=timestamp,
                    price=price,
                    action=action_int,
                    reward=float(reward),
                    position=account.position,
                    equity=mark_equity,
                    info={
                        "symbol": info["symbol"],
                        "session": info["session"],
                        "step_idx": info["current_idx"],
                        "invalid_action": step_info.get("invalid_action"),
                    },
                )
            equity_rows.append(
                {
                    "model": f"{algorithm}_smoke",
                    "algorithm": algorithm,
                    "policy": policy_name,
                    "episode_id": info["episode_id"],
                    "timestamp": timestamp,
                    "equity": mark_equity,
                    "position": account.position,
                }
            )
            info = step_info
            step_counter += 1

        if account.position:
            idx = min(raw_env.current_idx, raw_env.max_action_idx)
            forced_trade = account.apply_action(
                action=2,
                price=raw_env._close_at(idx),
                timestamp=raw_env._timestamp_at(idx),
                episode_id=str(info["episode_id"]),
                policy=policy_name,
                forced=True,
            )
            if forced_trade:
                forced_trade.update({"model": f"{algorithm}_smoke", "algorithm": algorithm})
                trade_rows.append(forced_trade)
        episode_return_pct = (account.equity - 1.0) * 100.0
        episode_rows.append(
            {
                "model": f"{algorithm}_smoke",
                "algorithm": algorithm,
                "policy": policy_name,
                "episode_id": info["episode_id"],
                "symbol": info["symbol"],
                "session": info["session"],
                "final_equity": account.equity,
                "episode_return_pct": episode_return_pct,
                "trade_count": len(account.trades),
                "forced_exit_count": account.forced_exit_count,
                "steps": step_counter,
            }
        )
        aggregate_base = aggregate_equity_curve[-1]
        aggregate_equity_curve.extend(aggregate_base * value for value in episode_equity_curve[1:])
        env.close()

    return {
        "episodes": episode_rows,
        "trades": trade_rows,
        "actions": action_rows,
        "equity": equity_rows,
        "aggregate_equity_curve": aggregate_equity_curve,
    }


def run_sb3_smoke(config: Sb3SmokeConfig) -> Dict[str, Any]:
    """Run Gymnasium check_env plus DQN/PPO smoke training and evaluation."""

    algorithms = tuple(config.algorithms)
    if not algorithms:
        raise ValueError("At least one SB3 algorithm is required.")
    check_result = _check_env(config)
    runtime = _torch_runtime()
    output_dir = Path(config.output_dir)

    model_summaries: List[Dict[str, Any]] = []
    all_actions: List[Dict[str, Any]] = []
    all_trades: List[Dict[str, Any]] = []
    all_equity: List[Dict[str, Any]] = []
    all_episodes: List[Dict[str, Any]] = []
    model_files: Dict[str, str] = {}
    event_writer: Optional[RlLiveEventWriter] = None
    live_events_path = output_dir / "rl_live_events.jsonl"
    if config.write_artifacts and config.write_live_events:
        event_writer = RlLiveEventWriter(live_events_path, run_id=output_dir.name)
        event_writer.reset()

    for algorithm in algorithms:
        model, elapsed = _train_model(algorithm, config, event_writer=event_writer)
        evaluation = _evaluate_model(model, algorithm, config, event_writer=event_writer)
        summary = _summarize_model(
            algorithm=algorithm,
            config=config,
            episode_rows=evaluation["episodes"],
            trade_rows=evaluation["trades"],
            aggregate_equity_curve=evaluation["aggregate_equity_curve"],
            training_elapsed_seconds=elapsed,
        )
        model_summaries.append(summary)
        all_actions.extend(evaluation["actions"])
        all_trades.extend(evaluation["trades"])
        all_equity.extend(evaluation["equity"])
        all_episodes.extend(evaluation["episodes"])
        if config.write_artifacts:
            output_dir.mkdir(parents=True, exist_ok=True)
            model_path = output_dir / f"{algorithm}_model.zip"
            model.save(model_path)
            model_files[algorithm] = str(model_path)

    ranking = sorted(model_summaries, key=lambda row: float(row["avg_episode_net_return_pct"]), reverse=True)
    payload: Dict[str, Any] = {
        "mode": "stom_rl_sb3_smoke",
        "config": asdict(config),
        "runtime": runtime,
        "check_env": check_result,
        "summary": {
            "algorithm_count": len(algorithms),
            "algorithms": list(algorithms),
            "check_env_passed": bool(check_result["passed"]),
            "best_algorithm_by_avg_episode_net": ranking[0]["algorithm"] if ranking else None,
            "best_model": ranking[0]["model"] if ranking else None,
            "device_requested": config.device,
            "cuda_available": runtime["cuda_available"],
            "feature_columns": check_result["feature_columns"],
        },
        "models": model_summaries,
        "artifacts": {
            "output_dir": str(output_dir),
            "summary_json": str(output_dir / "sb3_smoke_summary.json"),
            "summary_csv": str(output_dir / "sb3_smoke_summary.csv"),
            "actions_csv": str(output_dir / "actions.csv"),
            "trades_csv": str(output_dir / "trades.csv"),
            "equity_csv": str(output_dir / "equity.csv"),
            "episodes_csv": str(output_dir / "episodes.csv"),
            "model_files": model_files,
            "live_events_jsonl": str(live_events_path),
            "live_summary_json": str(output_dir / "rl_live_summary.json"),
        },
    }
    if config.write_artifacts and config.write_live_events:
        live_summary = summarize_live_event_file(live_events_path)
        payload["live_events"] = live_summary
        payload["summary"]["live_event_count"] = live_summary["event_count"]
        payload["summary"]["live_event_phases"] = live_summary["phases"]
        _write_json(output_dir / "rl_live_summary.json", live_summary)
    if config.write_artifacts:
        _write_json(output_dir / "sb3_smoke_summary.json", payload)
        _write_csv(
            output_dir / "sb3_smoke_summary.csv",
            model_summaries,
            [
                "algorithm",
                "model",
                "policy",
                "eval_split",
                "training_timesteps",
                "training_elapsed_seconds",
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
                "is_smoke",
                "eval_only",
                "source_run",
                "source_model",
                "cost_bps",
                "slippage_bps",
            ],
        )
        _write_csv(
            output_dir / "actions.csv",
            all_actions,
            [
                "model",
                "algorithm",
                "policy",
                "episode_id",
                "symbol",
                "session",
                "step_idx",
                "timestamp",
                "price",
                "action",
                "action_name",
                "position_after",
                "env_reward",
                "mark_equity",
                "invalid_action",
            ],
        )
        _write_csv(
            output_dir / "trades.csv",
            all_trades,
            [
                "model",
                "algorithm",
                "policy",
                "episode_id",
                "entry_timestamp",
                "exit_timestamp",
                "entry_price",
                "exit_price",
                "gross_return_pct",
                "net_return_pct",
                "cost_pct",
                "forced_exit",
            ],
        )
        _write_csv(
            output_dir / "equity.csv",
            all_equity,
            ["model", "algorithm", "policy", "episode_id", "timestamp", "equity", "position"],
        )
        _write_csv(
            output_dir / "episodes.csv",
            all_episodes,
            [
                "model",
                "algorithm",
                "policy",
                "episode_id",
                "symbol",
                "session",
                "final_equity",
                "episode_return_pct",
                "trade_count",
                "forced_exit_count",
                "steps",
            ],
        )
    return payload


def _parse_args(argv: Optional[Sequence[str]] = None) -> Sb3SmokeConfig:
    parser = argparse.ArgumentParser(description="Run STOM Gymnasium/SB3 check_env + DQN/PPO smoke training.")
    parser.add_argument("--manifest", default=str(DEFAULT_OUTPUT_DIR / "episode_manifest.json"))
    parser.add_argument("--output-dir", default=str(DEFAULT_SB3_SMOKE_OUTPUT_DIR))
    parser.add_argument("--train-split", default="train")
    parser.add_argument("--eval-split", default="test")
    parser.add_argument("--algorithms", default=",".join(DEFAULT_ALGORITHMS))
    parser.add_argument("--total-timesteps", type=int, default=256)
    parser.add_argument("--max-eval-episodes", type=int, default=2)
    parser.add_argument("--max-eval-steps-per-episode", type=int, default=256)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--lookback-window", type=int, default=300)
    parser.add_argument("--reward-horizon-seconds", type=int, default=300)
    parser.add_argument("--cost-bps", type=float, default=25.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--no-live-events", action="store_true")
    parser.add_argument("--live-event-sample-interval", type=int, default=1)
    args = parser.parse_args(argv)
    return Sb3SmokeConfig(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        train_split=args.train_split,
        eval_split=args.eval_split,
        algorithms=_parse_algorithms(args.algorithms),
        total_timesteps=args.total_timesteps,
        max_eval_episodes=args.max_eval_episodes,
        max_eval_steps_per_episode=args.max_eval_steps_per_episode,
        seed=args.seed,
        lookback_window=args.lookback_window,
        reward_horizon_seconds=args.reward_horizon_seconds,
        cost_bps=args.cost_bps,
        slippage_bps=args.slippage_bps,
        device=args.device,
        write_artifacts=not args.no_write,
        write_live_events=not args.no_live_events,
        live_event_sample_interval=args.live_event_sample_interval,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    payload = run_sb3_smoke(_parse_args(argv))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
