"""Compact full-split leaderboard runner for STOM RL performance validation.

The page-4 baseline runner intentionally writes dense action/equity artifacts for
debuggability.  That is useful for smoke runs but too heavy for the 2025 full
test split.  This module keeps the same long-only action semantics but writes
summary-first artifacts so the next performance phase can evaluate all test
episodes before deciding whether a learned policy is usable.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass, field
from math import exp, log
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .baselines import DEFAULT_POLICIES
from .episode_manifest import DEFAULT_OUTPUT_DIR, load_episode_manifest
from .trading_env import ACTION_BUY, ACTION_HOLD, ACTION_SELL


DEFAULT_LEADERBOARD_OUTPUT_DIR = Path("webui") / "rl_runs" / "stom_1s_2025_baseline_leaderboard_full_test"


@dataclass(frozen=True)
class LeaderboardConfig:
    manifest_path: str = str(DEFAULT_OUTPUT_DIR / "episode_manifest.json")
    output_dir: str = str(DEFAULT_LEADERBOARD_OUTPUT_DIR)
    split: str = "test"
    policies: Tuple[str, ...] = DEFAULT_POLICIES
    cost_bps_values: Tuple[float, ...] = (25.0,)
    slippage_bps_values: Tuple[float, ...] = (0.0,)
    target_cost_bps: float = 25.0
    target_slippage_bps: float = 0.0
    max_episodes: int = 0
    seed: int = 100
    lookback_window: int = 300
    reward_horizon_seconds: int = 300
    momentum_window: int = 30
    signal_threshold_bps: float = 0.0
    volume_window: int = 30
    amount_multiplier: float = 1.5
    sample_trade_limit: int = 1000
    write_artifacts: bool = True


@dataclass
class CompactAccount:
    cost_pct: float
    equity: float = 1.0
    position: int = 0
    entry_price: float = 0.0
    entry_idx: int = -1
    trade_count: int = 0
    forced_exit_count: int = 0
    trade_returns: List[float] = field(default_factory=list)

    def buy(self, price: float, idx: int) -> None:
        if self.position:
            return
        self.entry_price = float(price)
        self.entry_idx = int(idx)
        self.equity *= 1.0 - self.cost_pct
        self.position = 1

    def sell(self, price: float, idx: int, *, forced: bool = False) -> Optional[Dict[str, Any]]:
        if not self.position:
            return None
        before_exit = self.equity
        exit_equity = before_exit * (float(price) / self.entry_price) * (1.0 - self.cost_pct)
        trade_return = (exit_equity / max(before_exit / (1.0 - self.cost_pct), 1e-12)) - 1.0
        self.equity = float(exit_equity)
        self.position = 0
        self.trade_count += 1
        self.forced_exit_count += int(bool(forced))
        self.trade_returns.append(float(trade_return))
        row = {
            "entry_idx": self.entry_idx,
            "exit_idx": int(idx),
            "entry_price": self.entry_price,
            "exit_price": float(price),
            "net_return_pct": trade_return * 100.0,
            "forced_exit": bool(forced),
        }
        self.entry_price = 0.0
        self.entry_idx = -1
        return row


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _parse_float_list(raw: str) -> Tuple[float, ...]:
    return tuple(float(part.strip()) for part in raw.split(",") if part.strip())


def _parse_policies(raw: str) -> Tuple[str, ...]:
    policies = tuple(part.strip() for part in raw.split(",") if part.strip())
    unknown = sorted(set(policies) - set(DEFAULT_POLICIES))
    if unknown:
        raise ValueError(f"Unknown policies: {unknown}. Available: {sorted(DEFAULT_POLICIES)}")
    return policies


def _episodes(config: LeaderboardConfig) -> List[Dict[str, Any]]:
    manifest = load_episode_manifest(config.manifest_path)
    rows = [dict(row) for row in manifest.get("episodes", []) if row.get("split") == config.split]
    if config.max_episodes and config.max_episodes > 0:
        rows = rows[: int(config.max_episodes)]
    return rows


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


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    if len(values) == 0:
        return values
    series = pd.Series(values)
    return series.rolling(window=window, min_periods=1).mean().to_numpy(dtype=np.float64)


def _policy_action(
    policy: str,
    *,
    idx: int,
    account: CompactAccount,
    close: np.ndarray,
    momentum_return: np.ndarray,
    amount_ratio: np.ndarray,
    rng: np.random.Generator,
    config: LeaderboardConfig,
) -> int:
    threshold = float(config.signal_threshold_bps) / 10_000.0
    if policy == "no_trade":
        return ACTION_HOLD
    if policy == "random":
        return int(rng.choice([ACTION_HOLD, ACTION_BUY] if account.position == 0 else [ACTION_HOLD, ACTION_SELL]))
    if policy == "buy_and_hold":
        return ACTION_BUY if account.position == 0 and idx == config.lookback_window else ACTION_HOLD
    if policy == "momentum":
        recent = float(momentum_return[idx])
        if account.position == 0 and recent > threshold:
            return ACTION_BUY
        if account.position == 1 and recent <= -threshold:
            return ACTION_SELL
        return ACTION_HOLD
    if policy == "mean_reversion":
        recent = float(momentum_return[idx])
        if account.position == 0 and recent < -threshold:
            return ACTION_BUY
        if account.position == 1 and recent >= threshold:
            return ACTION_SELL
        return ACTION_HOLD
    if policy == "volume_filter":
        recent = float(momentum_return[idx])
        ratio = float(amount_ratio[idx])
        if account.position == 0 and recent > threshold and ratio >= config.amount_multiplier:
            return ACTION_BUY
        if account.position == 1 and (recent <= -threshold or ratio < 1.0):
            return ACTION_SELL
        return ACTION_HOLD
    raise ValueError(f"Unknown policy: {policy}")


def _episode_arrays(path: str) -> Tuple[np.ndarray, np.ndarray]:
    frame = pd.read_csv(path, usecols=["close", "amount"])
    close = frame["close"].to_numpy(dtype=np.float64)
    amount = frame["amount"].to_numpy(dtype=np.float64)
    return close, amount


def _simulate_episode(
    episode: Mapping[str, Any],
    policy: str,
    config: LeaderboardConfig,
    *,
    cost_pct: float,
    rng: np.random.Generator,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    close, amount = _episode_arrays(str(episode["source_csv"]))
    start = int(config.lookback_window)
    stop = int(len(close) - config.reward_horizon_seconds - 1)
    if stop < start:
        raise ValueError(f"Episode {episode.get('episode_id')} is too short: {len(close)} rows")

    momentum_base_idx = np.maximum(np.arange(len(close)) - int(config.momentum_window), 0)
    momentum_base = close[momentum_base_idx]
    momentum_return = np.divide(close - momentum_base, momentum_base, out=np.zeros_like(close), where=momentum_base != 0)
    amount_mean = _rolling_mean(amount, int(config.volume_window))
    amount_ratio = np.divide(amount, amount_mean, out=np.zeros_like(amount), where=amount_mean > 0)

    account = CompactAccount(cost_pct=cost_pct)
    trades: List[Dict[str, Any]] = []
    for idx in range(start, stop + 1):
        action = _policy_action(
            policy,
            idx=idx,
            account=account,
            close=close,
            momentum_return=momentum_return,
            amount_ratio=amount_ratio,
            rng=rng,
            config=config,
        )
        if action == ACTION_BUY:
            account.buy(float(close[idx]), idx)
        elif action == ACTION_SELL:
            trade = account.sell(float(close[idx]), idx)
            if trade:
                trades.append(trade)

    if account.position:
        trade = account.sell(float(close[stop]), stop, forced=True)
        if trade:
            trades.append(trade)

    episode_return_pct = (account.equity - 1.0) * 100.0
    episode_row = {
        "policy": policy,
        "episode_id": episode.get("episode_id"),
        "symbol": episode.get("symbol"),
        "session": episode.get("session"),
        "final_equity": account.equity,
        "episode_return_pct": episode_return_pct,
        "trade_count": account.trade_count,
        "forced_exit_count": account.forced_exit_count,
    }
    for trade in trades:
        trade.update(
            {
                "policy": policy,
                "episode_id": episode.get("episode_id"),
                "symbol": episode.get("symbol"),
                "session": episode.get("session"),
            }
        )
    return episode_row, trades


def _summarize(
    *,
    policy: str,
    cost_bps: float,
    slippage_bps: float,
    episode_rows: Sequence[Mapping[str, Any]],
    trade_rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    returns = np.asarray([float(row["episode_return_pct"]) for row in episode_rows], dtype=np.float64)
    equities = [float(row["final_equity"]) for row in episode_rows]
    trade_returns = np.asarray([float(row["net_return_pct"]) for row in trade_rows], dtype=np.float64)
    sessions: Dict[str, List[float]] = {}
    for row in episode_rows:
        sessions.setdefault(str(row.get("session")), []).append(float(row["episode_return_pct"]))
    positive_sessions = [np.mean(values) > 0.0 for values in sessions.values()]
    return {
        "policy": policy,
        "cost_bps": float(cost_bps),
        "slippage_bps": float(slippage_bps),
        "episode_count": len(episode_rows),
        "trade_count": len(trade_rows),
        "trades_per_episode": float(len(trade_rows) / len(episode_rows)) if episode_rows else 0.0,
        "avg_episode_net_return_pct": float(np.mean(returns)) if len(returns) else 0.0,
        "median_episode_net_return_pct": float(np.median(returns)) if len(returns) else 0.0,
        "compounded_return_pct": _safe_compounded_return_pct(equities),
        "avg_trade_net_return_pct": float(np.mean(trade_returns)) if len(trade_returns) else 0.0,
        "hit_rate": float(np.mean(trade_returns > 0.0)) if len(trade_returns) else 0.0,
        "max_drawdown_pct": _max_drawdown_pct(equities),
        "positive_session_rate": float(np.mean(positive_sessions)) if positive_sessions else 0.0,
    }


def run_leaderboard(config: LeaderboardConfig) -> Dict[str, Any]:
    episodes = _episodes(config)
    output_dir = Path(config.output_dir)
    scenario_rows: List[Dict[str, Any]] = []
    target_episode_rows: List[Dict[str, Any]] = []
    target_trade_sample: List[Dict[str, Any]] = []

    for cost_bps in config.cost_bps_values:
        for slippage_bps in config.slippage_bps_values:
            cost_pct = (float(cost_bps) + float(slippage_bps)) / 10_000.0
            for policy in config.policies:
                rng = np.random.default_rng(config.seed + int(cost_bps * 10) + sum(ord(ch) for ch in policy))
                policy_episode_rows: List[Dict[str, Any]] = []
                policy_trade_rows: List[Dict[str, Any]] = []
                for episode in episodes:
                    episode_row, trades = _simulate_episode(episode, policy, config, cost_pct=cost_pct, rng=rng)
                    episode_row.update({"cost_bps": float(cost_bps), "slippage_bps": float(slippage_bps)})
                    policy_episode_rows.append(episode_row)
                    policy_trade_rows.extend(trades)
                summary = _summarize(
                    policy=policy,
                    cost_bps=cost_bps,
                    slippage_bps=slippage_bps,
                    episode_rows=policy_episode_rows,
                    trade_rows=policy_trade_rows,
                )
                scenario_rows.append(summary)
                if float(cost_bps) == float(config.target_cost_bps) and float(slippage_bps) == float(config.target_slippage_bps):
                    target_episode_rows.extend(policy_episode_rows)
                    remaining = max(0, int(config.sample_trade_limit) - len(target_trade_sample))
                    if remaining:
                        target_trade_sample.extend(policy_trade_rows[:remaining])

    target_rows = [
        row
        for row in scenario_rows
        if float(row["cost_bps"]) == float(config.target_cost_bps)
        and float(row["slippage_bps"]) == float(config.target_slippage_bps)
    ]
    target_rows = sorted(target_rows, key=lambda row: row["avg_episode_net_return_pct"], reverse=True)
    payload = {
        "mode": "stom_rl_baseline_leaderboard",
        "config": asdict(config),
        "summary": {
            "episode_count": len(episodes),
            "scenario_count": len(scenario_rows),
            "target_cost_bps": config.target_cost_bps,
            "target_slippage_bps": config.target_slippage_bps,
            "best_policy_at_target_cost": target_rows[0]["policy"] if target_rows else None,
            "target_rows": target_rows,
        },
        "scenario_rows": sorted(
            scenario_rows,
            key=lambda row: (row["cost_bps"], row["slippage_bps"], -row["avg_episode_net_return_pct"]),
        ),
        "artifacts": {
            "output_dir": str(output_dir),
            "leaderboard_json": str(output_dir / "leaderboard_report.json"),
            "leaderboard_csv": str(output_dir / "leaderboard.csv"),
            "target_episode_csv": str(output_dir / "target_policy_episodes.csv"),
            "target_trade_sample_csv": str(output_dir / "target_trade_sample.csv"),
        },
    }
    if config.write_artifacts:
        _write_json(output_dir / "leaderboard_report.json", payload)
        _write_csv(
            output_dir / "leaderboard.csv",
            payload["scenario_rows"],
            [
                "policy",
                "cost_bps",
                "slippage_bps",
                "episode_count",
                "trade_count",
                "trades_per_episode",
                "avg_episode_net_return_pct",
                "median_episode_net_return_pct",
                "compounded_return_pct",
                "avg_trade_net_return_pct",
                "hit_rate",
                "max_drawdown_pct",
                "positive_session_rate",
            ],
        )
        _write_csv(
            output_dir / "target_policy_episodes.csv",
            target_episode_rows,
            [
                "policy",
                "cost_bps",
                "slippage_bps",
                "episode_id",
                "symbol",
                "session",
                "final_equity",
                "episode_return_pct",
                "trade_count",
                "forced_exit_count",
            ],
        )
        _write_csv(
            output_dir / "target_trade_sample.csv",
            target_trade_sample,
            [
                "policy",
                "episode_id",
                "symbol",
                "session",
                "entry_idx",
                "exit_idx",
                "entry_price",
                "exit_price",
                "net_return_pct",
                "forced_exit",
            ],
        )
    return payload


def _parse_args(argv: Optional[Sequence[str]] = None) -> LeaderboardConfig:
    parser = argparse.ArgumentParser(description="Run compact STOM RL full-split baseline leaderboard.")
    parser.add_argument("--manifest", default=str(DEFAULT_OUTPUT_DIR / "episode_manifest.json"))
    parser.add_argument("--output-dir", default=str(DEFAULT_LEADERBOARD_OUTPUT_DIR))
    parser.add_argument("--split", default="test")
    parser.add_argument("--policies", default=",".join(DEFAULT_POLICIES))
    parser.add_argument("--cost-bps-values", default="25")
    parser.add_argument("--slippage-bps-values", default="0")
    parser.add_argument("--target-cost-bps", type=float, default=25.0)
    parser.add_argument("--target-slippage-bps", type=float, default=0.0)
    parser.add_argument("--max-episodes", type=int, default=0)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--lookback-window", type=int, default=300)
    parser.add_argument("--reward-horizon-seconds", type=int, default=300)
    parser.add_argument("--momentum-window", type=int, default=30)
    parser.add_argument("--signal-threshold-bps", type=float, default=0.0)
    parser.add_argument("--volume-window", type=int, default=30)
    parser.add_argument("--amount-multiplier", type=float, default=1.5)
    parser.add_argument("--sample-trade-limit", type=int, default=1000)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    return LeaderboardConfig(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        split=args.split,
        policies=_parse_policies(args.policies),
        cost_bps_values=_parse_float_list(args.cost_bps_values),
        slippage_bps_values=_parse_float_list(args.slippage_bps_values),
        target_cost_bps=args.target_cost_bps,
        target_slippage_bps=args.target_slippage_bps,
        max_episodes=args.max_episodes,
        seed=args.seed,
        lookback_window=args.lookback_window,
        reward_horizon_seconds=args.reward_horizon_seconds,
        momentum_window=args.momentum_window,
        signal_threshold_bps=args.signal_threshold_bps,
        volume_window=args.volume_window,
        amount_multiplier=args.amount_multiplier,
        sample_trade_limit=args.sample_trade_limit,
        write_artifacts=not args.no_write,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    payload = run_leaderboard(_parse_args(argv))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
