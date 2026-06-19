"""Baseline strategy runner for the STOM independent RL lab.

Page 4 establishes non-RL reference strategies before any learning model is
trained.  The runner uses ``StomTickTradingEnv`` for the same action/episode
contract that future agents will see, while separately tracking realized
trade/equity metrics that are easier to compare across baseline policies.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass, field
from math import exp, log
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .episode_manifest import DEFAULT_OUTPUT_DIR
from .trading_env import (
    ACTION_BUY,
    ACTION_HOLD,
    ACTION_NAMES,
    ACTION_SELL,
    StomTickTradingEnv,
    StomTickTradingEnvConfig,
)


DEFAULT_BASELINE_OUTPUT_DIR = Path("webui") / "rl_runs" / "stom_1s_2025_baselines"
DEFAULT_POLICIES = (
    "no_trade",
    "random",
    "buy_and_hold",
    "momentum",
    "mean_reversion",
    "volume_filter",
)


@dataclass(frozen=True)
class BaselineRunConfig:
    """Configuration for running deterministic baseline strategies."""

    manifest_path: str = str(DEFAULT_OUTPUT_DIR / "episode_manifest.json")
    output_dir: str = str(DEFAULT_BASELINE_OUTPUT_DIR)
    split: str = "test"
    policies: Tuple[str, ...] = DEFAULT_POLICIES
    max_episodes: int = 25
    seed: int = 100
    lookback_window: int = 300
    reward_horizon_seconds: int = 300
    cost_bps: float = 25.0
    slippage_bps: float = 0.0
    momentum_window: int = 30
    signal_threshold_bps: float = 0.0
    volume_window: int = 30
    amount_multiplier: float = 1.5
    max_steps_per_episode: int = 0
    episode_ids: Tuple[str, ...] = field(default_factory=tuple)
    sessions: Tuple[str, ...] = field(default_factory=tuple)
    write_artifacts: bool = True


@dataclass
class AccountState:
    """Simple long-only accounting separate from dense RL reward."""

    cost_pct: float
    equity: float = 1.0
    position: int = 0
    entry_price: float = 0.0
    entry_timestamp: str = ""
    entry_equity_before_cost: float = 1.0
    entry_equity_after_cost: float = 1.0
    trades: List[Dict[str, Any]] = field(default_factory=list)
    forced_exit_count: int = 0

    def mark_equity(self, price: float) -> float:
        if self.position == 0:
            return float(self.equity)
        return float(self.entry_equity_after_cost * (price / self.entry_price))

    def apply_action(
        self,
        *,
        action: int,
        price: float,
        timestamp: str,
        episode_id: str,
        policy: str,
        forced: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if action == ACTION_BUY and self.position == 0:
            self.entry_price = float(price)
            self.entry_timestamp = timestamp
            self.entry_equity_before_cost = float(self.equity)
            self.equity *= 1.0 - self.cost_pct
            self.entry_equity_after_cost = float(self.equity)
            self.position = 1
            return None
        if action == ACTION_SELL and self.position == 1:
            gross_return = (float(price) - self.entry_price) / self.entry_price
            equity_before_entry = self.entry_equity_before_cost
            exit_equity = self.entry_equity_after_cost * (float(price) / self.entry_price) * (1.0 - self.cost_pct)
            trade_net_return = (exit_equity / equity_before_entry) - 1.0
            self.equity = float(exit_equity)
            trade = {
                "policy": policy,
                "episode_id": episode_id,
                "entry_timestamp": self.entry_timestamp,
                "exit_timestamp": timestamp,
                "entry_price": self.entry_price,
                "exit_price": float(price),
                "gross_return_pct": gross_return * 100.0,
                "net_return_pct": trade_net_return * 100.0,
                "cost_pct": self.cost_pct * 100.0,
                "forced_exit": bool(forced),
            }
            self.trades.append(trade)
            if forced:
                self.forced_exit_count += 1
            self.position = 0
            self.entry_price = 0.0
            self.entry_timestamp = ""
            self.entry_equity_before_cost = self.equity
            self.entry_equity_after_cost = self.equity
            return trade
        return None


PolicyFn = Callable[[StomTickTradingEnv, Mapping[str, Any], np.random.Generator, BaselineRunConfig], int]


def _recent_return(env: StomTickTradingEnv, window: int) -> float:
    idx = env.current_idx
    start_idx = max(0, idx - int(window))
    past = env._close_at(start_idx)
    current = env._close_at(idx)
    return float((current - past) / past) if past else 0.0


def _recent_amount_ratio(env: StomTickTradingEnv, window: int) -> float:
    idx = env.current_idx
    start_idx = max(0, idx - int(window))
    hist = env.frame.iloc[start_idx:idx]
    if hist.empty:
        return 0.0
    current_amount = float(env.frame["amount"].iloc[idx])
    avg_amount = float(hist["amount"].mean())
    return current_amount / avg_amount if avg_amount > 0 else 0.0


def policy_no_trade(env: StomTickTradingEnv, info: Mapping[str, Any], rng: np.random.Generator, config: BaselineRunConfig) -> int:
    return ACTION_HOLD


def policy_random(env: StomTickTradingEnv, info: Mapping[str, Any], rng: np.random.Generator, config: BaselineRunConfig) -> int:
    if env.position == 0:
        return int(rng.choice([ACTION_HOLD, ACTION_BUY]))
    return int(rng.choice([ACTION_HOLD, ACTION_SELL]))


def policy_buy_and_hold(env: StomTickTradingEnv, info: Mapping[str, Any], rng: np.random.Generator, config: BaselineRunConfig) -> int:
    if env.position == 0 and env.current_idx == env.config.lookback_window:
        return ACTION_BUY
    return ACTION_HOLD


def policy_momentum(env: StomTickTradingEnv, info: Mapping[str, Any], rng: np.random.Generator, config: BaselineRunConfig) -> int:
    threshold = float(config.signal_threshold_bps) / 10_000.0
    recent = _recent_return(env, config.momentum_window)
    if env.position == 0 and recent > threshold:
        return ACTION_BUY
    if env.position == 1 and recent <= -threshold:
        return ACTION_SELL
    return ACTION_HOLD


def policy_mean_reversion(env: StomTickTradingEnv, info: Mapping[str, Any], rng: np.random.Generator, config: BaselineRunConfig) -> int:
    threshold = float(config.signal_threshold_bps) / 10_000.0
    recent = _recent_return(env, config.momentum_window)
    if env.position == 0 and recent < -threshold:
        return ACTION_BUY
    if env.position == 1 and recent >= threshold:
        return ACTION_SELL
    return ACTION_HOLD


def policy_volume_filter(env: StomTickTradingEnv, info: Mapping[str, Any], rng: np.random.Generator, config: BaselineRunConfig) -> int:
    recent = _recent_return(env, config.momentum_window)
    amount_ratio = _recent_amount_ratio(env, config.volume_window)
    threshold = float(config.signal_threshold_bps) / 10_000.0
    if env.position == 0 and recent > threshold and amount_ratio >= config.amount_multiplier:
        return ACTION_BUY
    if env.position == 1 and (recent <= -threshold or amount_ratio < 1.0):
        return ACTION_SELL
    return ACTION_HOLD


POLICY_REGISTRY: Dict[str, PolicyFn] = {
    "no_trade": policy_no_trade,
    "random": policy_random,
    "buy_and_hold": policy_buy_and_hold,
    "momentum": policy_momentum,
    "mean_reversion": policy_mean_reversion,
    "volume_filter": policy_volume_filter,
}


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def _max_drawdown_pct(equity_values: Sequence[float]) -> float:
    peak = 1.0
    max_dd = 0.0
    for value in equity_values:
        peak = max(peak, float(value))
        if peak > 0:
            max_dd = min(max_dd, (float(value) / peak) - 1.0)
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


def _selected_episode_indices(episodes: Sequence[Mapping[str, Any]], config: BaselineRunConfig) -> List[int]:
    episode_ids = {str(episode_id) for episode_id in config.episode_ids}
    sessions = {str(session) for session in config.sessions}
    selected = [
        idx
        for idx, episode in enumerate(episodes)
        if (not episode_ids or str(episode.get("episode_id")) in episode_ids)
        and (not sessions or str(episode.get("session")) in sessions)
    ]
    if config.max_episodes and config.max_episodes > 0:
        return selected[: int(config.max_episodes)]
    return selected


def _force_close_if_needed(
    env: StomTickTradingEnv,
    account: AccountState,
    policy_name: str,
    episode_id: str,
) -> Optional[Dict[str, Any]]:
    if account.position == 0:
        return None
    idx = min(env.current_idx, env.max_action_idx)
    price = env._close_at(idx)
    timestamp = env._timestamp_at(idx)
    return account.apply_action(
        action=ACTION_SELL,
        price=price,
        timestamp=timestamp,
        episode_id=episode_id,
        policy=policy_name,
        forced=True,
    )


def _run_policy(policy_name: str, config: BaselineRunConfig) -> Dict[str, Any]:
    if policy_name not in POLICY_REGISTRY:
        raise ValueError(f"Unknown baseline policy: {policy_name}")
    policy = POLICY_REGISTRY[policy_name]
    rng = np.random.default_rng(config.seed + sum(ord(ch) for ch in policy_name))
    env_config = StomTickTradingEnvConfig(
        manifest_path=config.manifest_path,
        split=config.split,
        seed=config.seed,
        lookback_window=config.lookback_window,
        reward_horizon_seconds=config.reward_horizon_seconds,
        cost_bps=config.cost_bps,
        slippage_bps=config.slippage_bps,
        reward_mode="horizon",
    )
    probe_env = StomTickTradingEnv(env_config)
    selected_indices = _selected_episode_indices(probe_env.episodes, config)

    action_rows: List[Dict[str, Any]] = []
    equity_rows: List[Dict[str, Any]] = []
    trade_rows: List[Dict[str, Any]] = []
    episode_rows: List[Dict[str, Any]] = []
    aggregate_equity_curve = [1.0]
    action_count = 0
    invalid_action_count = 0

    for episode_index in selected_indices:
        env = StomTickTradingEnv(StomTickTradingEnvConfig(**{**asdict(env_config), "episode_index": episode_index}))
        _, info = env.reset(seed=config.seed + episode_index)
        episode_id = str(info["episode_id"])
        account = AccountState(cost_pct=(config.cost_bps + config.slippage_bps) / 10_000.0)
        terminated = False
        truncated = False
        step_counter = 0
        while not (terminated or truncated):
            if config.max_steps_per_episode and step_counter >= config.max_steps_per_episode:
                break
            price = env._close_at(env.current_idx)
            timestamp = env._timestamp_at(env.current_idx)
            action = policy(env, info, rng, config)
            _, reward, terminated, truncated, step_info = env.step(action)
            trade = account.apply_action(
                action=action,
                price=price,
                timestamp=timestamp,
                episode_id=episode_id,
                policy=policy_name,
            )
            if trade:
                trade_rows.append(trade)
            mark_equity = account.mark_equity(price)
            action_rows.append(
                {
                    "policy": policy_name,
                    "episode_id": episode_id,
                    "symbol": info["symbol"],
                    "session": info["session"],
                    "step_idx": info["current_idx"],
                    "timestamp": timestamp,
                    "price": price,
                    "action": action,
                    "action_name": ACTION_NAMES[action],
                    "position_after": account.position,
                    "env_reward": reward,
                    "mark_equity": mark_equity,
                    "invalid_action": step_info["invalid_action"],
                }
            )
            equity_rows.append(
                {
                    "policy": policy_name,
                    "episode_id": episode_id,
                    "timestamp": timestamp,
                    "equity": mark_equity,
                    "position": account.position,
                }
            )
            action_count += 1
            invalid_action_count += int(bool(step_info["invalid_action"]))
            info = step_info
            step_counter += 1

        forced_trade = _force_close_if_needed(env, account, policy_name, episode_id)
        if forced_trade:
            trade_rows.append(forced_trade)
        episode_return_pct = (account.equity - 1.0) * 100.0
        episode_rows.append(
            {
                "policy": policy_name,
                "episode_id": episode_id,
                "symbol": info["symbol"],
                "session": info["session"],
                "final_equity": account.equity,
                "episode_return_pct": episode_return_pct,
                "trade_count": len(account.trades),
                "forced_exit_count": account.forced_exit_count,
                "steps": step_counter,
            }
        )
        aggregate_equity_curve.append(aggregate_equity_curve[-1] * max(account.equity, 1e-12))

    final_equities = [float(row["final_equity"]) for row in episode_rows]
    trade_returns = [float(row["net_return_pct"]) for row in trade_rows]
    hit_count = sum(1 for value in trade_returns if value > 0)
    summary = {
        "policy": policy_name,
        "split": config.split,
        "episode_count": len(episode_rows),
        "action_count": action_count,
        "trade_count": len(trade_rows),
        "forced_exit_count": sum(int(row["forced_exit"]) for row in trade_rows),
        "avg_episode_net_return_pct": float(np.mean([row["episode_return_pct"] for row in episode_rows]))
        if episode_rows
        else 0.0,
        "median_episode_net_return_pct": float(np.median([row["episode_return_pct"] for row in episode_rows]))
        if episode_rows
        else 0.0,
        "compounded_return_pct": _safe_compounded_return_pct(final_equities),
        "avg_trade_net_return_pct": float(np.mean(trade_returns)) if trade_returns else 0.0,
        "hit_rate": hit_count / len(trade_returns) if trade_returns else 0.0,
        "invalid_action_rate": invalid_action_count / action_count if action_count else 0.0,
        "max_drawdown_pct": _max_drawdown_pct(aggregate_equity_curve),
    }
    return {
        "summary": summary,
        "episodes": episode_rows,
        "trades": trade_rows,
        "actions": action_rows,
        "equity": equity_rows,
    }


def run_baselines(config: BaselineRunConfig) -> Dict[str, Any]:
    """Run configured baseline policies and optionally write artifacts."""

    output_dir = Path(config.output_dir)
    per_policy: Dict[str, Any] = {}
    all_summaries: List[Dict[str, Any]] = []
    for policy_name in config.policies:
        result = _run_policy(policy_name, config)
        per_policy[policy_name] = result
        all_summaries.append(result["summary"])
        if config.write_artifacts:
            policy_dir = output_dir / policy_name
            _write_csv(
                policy_dir / "actions.csv",
                result["actions"],
                [
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
                policy_dir / "trades.csv",
                result["trades"],
                [
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
                policy_dir / "equity.csv",
                result["equity"],
                ["policy", "episode_id", "timestamp", "equity", "position"],
            )
            _write_csv(
                policy_dir / "episodes.csv",
                result["episodes"],
                [
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

    ranking = sorted(all_summaries, key=lambda item: item["avg_episode_net_return_pct"], reverse=True)
    payload = {
        "mode": "stom_rl_baseline_run",
        "config": asdict(config),
        "summary": {
            "policy_count": len(config.policies),
            "episode_limit": config.max_episodes,
            "split": config.split,
            "best_policy_by_avg_episode_net": ranking[0]["policy"] if ranking else None,
            "policies": all_summaries,
            "ranking": ranking,
        },
        "artifacts": {
            "output_dir": str(output_dir),
            "summary_json": str(output_dir / "baseline_summary.json"),
            "summary_csv": str(output_dir / "baseline_summary.csv"),
        },
    }
    if config.write_artifacts:
        _write_json(output_dir / "baseline_summary.json", payload)
        _write_csv(
            output_dir / "baseline_summary.csv",
            all_summaries,
            [
                "policy",
                "split",
                "episode_count",
                "action_count",
                "trade_count",
                "forced_exit_count",
                "avg_episode_net_return_pct",
                "median_episode_net_return_pct",
                "compounded_return_pct",
                "avg_trade_net_return_pct",
                "hit_rate",
                "invalid_action_rate",
                "max_drawdown_pct",
            ],
        )
    return payload


def _parse_policies(raw: str) -> Tuple[str, ...]:
    policies = tuple(part.strip() for part in raw.split(",") if part.strip())
    unknown = [policy for policy in policies if policy not in POLICY_REGISTRY]
    if unknown:
        raise ValueError(f"Unknown policies: {unknown}. Available: {sorted(POLICY_REGISTRY)}")
    return policies


def _parse_list_arg(raw: str) -> Tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _parse_args(argv: Optional[Sequence[str]] = None) -> BaselineRunConfig:
    parser = argparse.ArgumentParser(description="Run STOM RL baseline strategies.")
    parser.add_argument("--manifest", default=str(DEFAULT_OUTPUT_DIR / "episode_manifest.json"))
    parser.add_argument("--output-dir", default=str(DEFAULT_BASELINE_OUTPUT_DIR))
    parser.add_argument("--split", default="test")
    parser.add_argument("--policies", default=",".join(DEFAULT_POLICIES))
    parser.add_argument("--max-episodes", type=int, default=25)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--lookback-window", type=int, default=300)
    parser.add_argument("--reward-horizon-seconds", type=int, default=300)
    parser.add_argument("--cost-bps", type=float, default=25.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--momentum-window", type=int, default=30)
    parser.add_argument("--signal-threshold-bps", type=float, default=0.0)
    parser.add_argument("--volume-window", type=int, default=30)
    parser.add_argument("--amount-multiplier", type=float, default=1.5)
    parser.add_argument("--max-steps-per-episode", type=int, default=0)
    parser.add_argument("--episode-ids", default="", help="Comma-separated episode_id filter.")
    parser.add_argument("--sessions", default="", help="Comma-separated session filter such as 20250103,20250106.")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    return BaselineRunConfig(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        split=args.split,
        policies=_parse_policies(args.policies),
        max_episodes=args.max_episodes,
        seed=args.seed,
        lookback_window=args.lookback_window,
        reward_horizon_seconds=args.reward_horizon_seconds,
        cost_bps=args.cost_bps,
        slippage_bps=args.slippage_bps,
        momentum_window=args.momentum_window,
        signal_threshold_bps=args.signal_threshold_bps,
        volume_window=args.volume_window,
        amount_multiplier=args.amount_multiplier,
        max_steps_per_episode=args.max_steps_per_episode,
        episode_ids=_parse_list_arg(args.episode_ids),
        sessions=_parse_list_arg(args.sessions),
        write_artifacts=not args.no_write,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    config = _parse_args(argv)
    payload = run_baselines(config)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
