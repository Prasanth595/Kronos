"""Reward and cost-gate reporting for the STOM independent RL lab.

Page 5 evaluates whether baseline strategies survive realistic transaction
costs before any RL model is trained.  The report deliberately stays separate
from model training: it reuses the page-4 baseline runner, sweeps cost/slippage
scenarios, and records pass/fail evidence for net return, drawdown, turnover,
and rolling validation stability.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .baselines import DEFAULT_POLICIES, BaselineRunConfig, run_baselines
from .episode_manifest import DEFAULT_OUTPUT_DIR, load_episode_manifest


DEFAULT_COST_GATE_OUTPUT_DIR = Path("webui") / "rl_runs" / "stom_1s_2025_cost_gate"


@dataclass(frozen=True)
class CostGateConfig:
    """Configuration for cost/slippage/rolling validation checks."""

    manifest_path: str = str(DEFAULT_OUTPUT_DIR / "episode_manifest.json")
    output_dir: str = str(DEFAULT_COST_GATE_OUTPUT_DIR)
    split: str = "test"
    policies: Tuple[str, ...] = DEFAULT_POLICIES
    cost_bps_values: Tuple[float, ...] = (5.0, 10.0, 15.0, 25.0)
    slippage_bps_values: Tuple[float, ...] = (0.0,)
    target_cost_bps: float = 25.0
    target_slippage_bps: float = 0.0
    max_episodes: int = 25
    seed: int = 100
    lookback_window: int = 300
    reward_horizon_seconds: int = 300
    momentum_window: int = 30
    signal_threshold_bps: float = 0.0
    volume_window: int = 30
    amount_multiplier: float = 1.5
    max_steps_per_episode: int = 0
    sessions: Tuple[str, ...] = field(default_factory=tuple)
    min_avg_episode_net_pct: float = 0.0
    max_drawdown_pct: float = 20.0
    max_trades_per_episode: float = 50.0
    min_trade_count: int = 1
    rolling_sessions_per_fold: int = 6
    rolling_max_folds: int = 3
    rolling_max_episodes_per_fold: int = 25
    min_positive_fold_rate: float = 0.5
    write_policy_artifacts: bool = False


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _float_label(value: float) -> str:
    value = float(value)
    if value.is_integer():
        return str(int(value))
    return str(value).replace(".", "p")


def _scenario_id(cost_bps: float, slippage_bps: float) -> str:
    return f"cost_{_float_label(cost_bps)}bp_slip_{_float_label(slippage_bps)}bp"


def _parse_float_tuple(raw: str) -> Tuple[float, ...]:
    return tuple(float(part.strip()) for part in raw.split(",") if part.strip())


def _parse_str_tuple(raw: str) -> Tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _manifest_sessions(config: CostGateConfig) -> List[str]:
    manifest = load_episode_manifest(config.manifest_path)
    sessions = [
        str(episode.get("session"))
        for episode in manifest.get("episodes", [])
        if episode.get("split") == config.split
        and (not config.sessions or str(episode.get("session")) in set(config.sessions))
    ]
    return sorted(set(sessions))


def _chunks(items: Sequence[str], chunk_size: int, max_chunks: int) -> List[Tuple[str, ...]]:
    chunk_size = max(1, int(chunk_size))
    chunks = [tuple(items[idx : idx + chunk_size]) for idx in range(0, len(items), chunk_size)]
    if max_chunks and max_chunks > 0:
        return chunks[: int(max_chunks)]
    return chunks


def _baseline_config(
    config: CostGateConfig,
    *,
    output_dir: Path,
    cost_bps: float,
    slippage_bps: float,
    max_episodes: int,
    sessions: Tuple[str, ...] = (),
    write_artifacts: Optional[bool] = None,
) -> BaselineRunConfig:
    return BaselineRunConfig(
        manifest_path=config.manifest_path,
        output_dir=str(output_dir),
        split=config.split,
        policies=config.policies,
        max_episodes=max_episodes,
        seed=config.seed,
        lookback_window=config.lookback_window,
        reward_horizon_seconds=config.reward_horizon_seconds,
        cost_bps=cost_bps,
        slippage_bps=slippage_bps,
        momentum_window=config.momentum_window,
        signal_threshold_bps=config.signal_threshold_bps,
        volume_window=config.volume_window,
        amount_multiplier=config.amount_multiplier,
        max_steps_per_episode=config.max_steps_per_episode,
        sessions=sessions or config.sessions,
        write_artifacts=config.write_policy_artifacts if write_artifacts is None else write_artifacts,
    )


def _scenario_row(summary: Mapping[str, Any], config: CostGateConfig, cost_bps: float, slippage_bps: float) -> Dict[str, Any]:
    episode_count = int(summary.get("episode_count", 0) or 0)
    trade_count = int(summary.get("trade_count", 0) or 0)
    turnover = trade_count / episode_count if episode_count else 0.0
    avg_net = float(summary.get("avg_episode_net_return_pct", 0.0) or 0.0)
    mdd = float(summary.get("max_drawdown_pct", 0.0) or 0.0)
    passes_net = avg_net > config.min_avg_episode_net_pct
    passes_mdd = mdd >= -abs(float(config.max_drawdown_pct))
    passes_turnover = turnover <= float(config.max_trades_per_episode)
    passes_trade_count = trade_count >= int(config.min_trade_count)
    return {
        "scenario_id": _scenario_id(cost_bps, slippage_bps),
        "cost_bps": float(cost_bps),
        "slippage_bps": float(slippage_bps),
        "policy": summary["policy"],
        "episode_count": episode_count,
        "trade_count": trade_count,
        "trades_per_episode": turnover,
        "avg_episode_net_return_pct": avg_net,
        "median_episode_net_return_pct": float(summary.get("median_episode_net_return_pct", 0.0) or 0.0),
        "compounded_return_pct": float(summary.get("compounded_return_pct", 0.0) or 0.0),
        "avg_trade_net_return_pct": float(summary.get("avg_trade_net_return_pct", 0.0) or 0.0),
        "hit_rate": float(summary.get("hit_rate", 0.0) or 0.0),
        "invalid_action_rate": float(summary.get("invalid_action_rate", 0.0) or 0.0),
        "max_drawdown_pct": mdd,
        "passes_net": passes_net,
        "passes_mdd": passes_mdd,
        "passes_turnover": passes_turnover,
        "passes_trade_count": passes_trade_count,
        "passes_scenario_gate": bool(passes_net and passes_mdd and passes_turnover and passes_trade_count),
    }


def _run_cost_scenarios(config: CostGateConfig, output_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    raw_results: Dict[str, Any] = {}
    for cost_bps in config.cost_bps_values:
        for slippage_bps in config.slippage_bps_values:
            sid = _scenario_id(cost_bps, slippage_bps)
            result = run_baselines(
                _baseline_config(
                    config,
                    output_dir=output_dir / "policy_artifacts" / sid,
                    cost_bps=cost_bps,
                    slippage_bps=slippage_bps,
                    max_episodes=config.max_episodes,
                )
            )
            raw_results[sid] = result["summary"]
            for summary in result["summary"]["policies"]:
                rows.append(_scenario_row(summary, config, cost_bps, slippage_bps))
    return rows, raw_results


def _run_rolling_validation(config: CostGateConfig, output_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    sessions = _manifest_sessions(config)
    folds = _chunks(sessions, config.rolling_sessions_per_fold, config.rolling_max_folds)
    rows: List[Dict[str, Any]] = []
    positive_counts = {policy: 0 for policy in config.policies}
    observed_counts = {policy: 0 for policy in config.policies}
    for fold_index, fold_sessions in enumerate(folds, start=1):
        result = run_baselines(
            _baseline_config(
                config,
                output_dir=output_dir / "rolling" / f"fold_{fold_index:02d}",
                cost_bps=config.target_cost_bps,
                slippage_bps=config.target_slippage_bps,
                max_episodes=config.rolling_max_episodes_per_fold,
                sessions=tuple(fold_sessions),
                write_artifacts=False,
            )
        )
        for summary in result["summary"]["policies"]:
            avg_net = float(summary.get("avg_episode_net_return_pct", 0.0) or 0.0)
            policy = str(summary["policy"])
            observed_counts[policy] += 1
            if avg_net > config.min_avg_episode_net_pct:
                positive_counts[policy] += 1
            rows.append(
                {
                    "fold": fold_index,
                    "sessions": ",".join(fold_sessions),
                    "cost_bps": config.target_cost_bps,
                    "slippage_bps": config.target_slippage_bps,
                    "policy": policy,
                    "episode_count": int(summary.get("episode_count", 0) or 0),
                    "trade_count": int(summary.get("trade_count", 0) or 0),
                    "avg_episode_net_return_pct": avg_net,
                    "max_drawdown_pct": float(summary.get("max_drawdown_pct", 0.0) or 0.0),
                    "hit_rate": float(summary.get("hit_rate", 0.0) or 0.0),
                    "positive_fold": avg_net > config.min_avg_episode_net_pct,
                }
            )
    positive_rates = {
        policy: (positive_counts[policy] / observed_counts[policy] if observed_counts[policy] else 0.0)
        for policy in config.policies
    }
    return rows, positive_rates


def _gate_summary(
    config: CostGateConfig,
    scenario_rows: Sequence[Mapping[str, Any]],
    rolling_positive_rates: Mapping[str, float],
) -> List[Dict[str, Any]]:
    target_sid = _scenario_id(config.target_cost_bps, config.target_slippage_bps)
    target_rows = [row for row in scenario_rows if row["scenario_id"] == target_sid]
    summaries: List[Dict[str, Any]] = []
    for row in target_rows:
        positive_fold_rate = float(rolling_positive_rates.get(str(row["policy"]), 0.0))
        passes_rolling = positive_fold_rate >= float(config.min_positive_fold_rate)
        summaries.append(
            {
                "policy": row["policy"],
                "target_scenario_id": target_sid,
                "avg_episode_net_return_pct": row["avg_episode_net_return_pct"],
                "max_drawdown_pct": row["max_drawdown_pct"],
                "trades_per_episode": row["trades_per_episode"],
                "hit_rate": row["hit_rate"],
                "positive_fold_rate": positive_fold_rate,
                "passes_target_scenario_gate": row["passes_scenario_gate"],
                "passes_rolling_gate": passes_rolling,
                "passes_cost_gate": bool(row["passes_scenario_gate"] and passes_rolling),
            }
        )
    return sorted(summaries, key=lambda item: item["avg_episode_net_return_pct"], reverse=True)


def run_cost_gate(config: CostGateConfig) -> Dict[str, Any]:
    """Run cost/slippage scenario and rolling-validation gates."""

    output_dir = Path(config.output_dir)
    scenario_rows, raw_scenarios = _run_cost_scenarios(config, output_dir)
    rolling_rows, positive_rates = _run_rolling_validation(config, output_dir)
    gate_rows = _gate_summary(config, scenario_rows, positive_rates)
    passing = [row for row in gate_rows if row["passes_cost_gate"]]
    payload = {
        "mode": "stom_rl_cost_gate",
        "config": asdict(config),
        "summary": {
            "scenario_count": len(config.cost_bps_values) * len(config.slippage_bps_values),
            "policy_count": len(config.policies),
            "target_cost_bps": config.target_cost_bps,
            "target_slippage_bps": config.target_slippage_bps,
            "passing_policy_count": len(passing),
            "passing_policies": [row["policy"] for row in passing],
            "best_policy_at_target_cost": gate_rows[0]["policy"] if gate_rows else None,
            "gate_rows": gate_rows,
        },
        "scenario_rows": scenario_rows,
        "rolling_rows": rolling_rows,
        "raw_scenarios": raw_scenarios,
        "artifacts": {
            "output_dir": str(output_dir),
            "report_json": str(output_dir / "cost_gate_report.json"),
            "scenario_csv": str(output_dir / "scenario_summary.csv"),
            "rolling_csv": str(output_dir / "rolling_folds.csv"),
            "gate_csv": str(output_dir / "gate_summary.csv"),
        },
    }
    _write_json(output_dir / "cost_gate_report.json", payload)
    _write_csv(
        output_dir / "scenario_summary.csv",
        scenario_rows,
        [
            "scenario_id",
            "cost_bps",
            "slippage_bps",
            "policy",
            "episode_count",
            "trade_count",
            "trades_per_episode",
            "avg_episode_net_return_pct",
            "median_episode_net_return_pct",
            "compounded_return_pct",
            "avg_trade_net_return_pct",
            "hit_rate",
            "invalid_action_rate",
            "max_drawdown_pct",
            "passes_net",
            "passes_mdd",
            "passes_turnover",
            "passes_trade_count",
            "passes_scenario_gate",
        ],
    )
    _write_csv(
        output_dir / "rolling_folds.csv",
        rolling_rows,
        [
            "fold",
            "sessions",
            "cost_bps",
            "slippage_bps",
            "policy",
            "episode_count",
            "trade_count",
            "avg_episode_net_return_pct",
            "max_drawdown_pct",
            "hit_rate",
            "positive_fold",
        ],
    )
    _write_csv(
        output_dir / "gate_summary.csv",
        gate_rows,
        [
            "policy",
            "target_scenario_id",
            "avg_episode_net_return_pct",
            "max_drawdown_pct",
            "trades_per_episode",
            "hit_rate",
            "positive_fold_rate",
            "passes_target_scenario_gate",
            "passes_rolling_gate",
            "passes_cost_gate",
        ],
    )
    return payload


def _parse_args(argv: Optional[Sequence[str]] = None) -> CostGateConfig:
    parser = argparse.ArgumentParser(description="Run STOM RL reward/cost-gate scenarios.")
    parser.add_argument("--manifest", default=str(DEFAULT_OUTPUT_DIR / "episode_manifest.json"))
    parser.add_argument("--output-dir", default=str(DEFAULT_COST_GATE_OUTPUT_DIR))
    parser.add_argument("--split", default="test")
    parser.add_argument("--policies", default=",".join(DEFAULT_POLICIES))
    parser.add_argument("--cost-bps-values", default="5,10,15,25")
    parser.add_argument("--slippage-bps-values", default="0")
    parser.add_argument("--target-cost-bps", type=float, default=25.0)
    parser.add_argument("--target-slippage-bps", type=float, default=0.0)
    parser.add_argument("--max-episodes", type=int, default=25)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--lookback-window", type=int, default=300)
    parser.add_argument("--reward-horizon-seconds", type=int, default=300)
    parser.add_argument("--momentum-window", type=int, default=30)
    parser.add_argument("--signal-threshold-bps", type=float, default=0.0)
    parser.add_argument("--volume-window", type=int, default=30)
    parser.add_argument("--amount-multiplier", type=float, default=1.5)
    parser.add_argument("--max-steps-per-episode", type=int, default=0)
    parser.add_argument("--sessions", default="")
    parser.add_argument("--min-avg-episode-net-pct", type=float, default=0.0)
    parser.add_argument("--max-drawdown-pct", type=float, default=20.0)
    parser.add_argument("--max-trades-per-episode", type=float, default=50.0)
    parser.add_argument("--min-trade-count", type=int, default=1)
    parser.add_argument("--rolling-sessions-per-fold", type=int, default=6)
    parser.add_argument("--rolling-max-folds", type=int, default=3)
    parser.add_argument("--rolling-max-episodes-per-fold", type=int, default=25)
    parser.add_argument("--min-positive-fold-rate", type=float, default=0.5)
    parser.add_argument("--write-policy-artifacts", action="store_true")
    args = parser.parse_args(argv)
    return CostGateConfig(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        split=args.split,
        policies=_parse_str_tuple(args.policies),
        cost_bps_values=_parse_float_tuple(args.cost_bps_values),
        slippage_bps_values=_parse_float_tuple(args.slippage_bps_values),
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
        max_steps_per_episode=args.max_steps_per_episode,
        sessions=_parse_str_tuple(args.sessions),
        min_avg_episode_net_pct=args.min_avg_episode_net_pct,
        max_drawdown_pct=args.max_drawdown_pct,
        max_trades_per_episode=args.max_trades_per_episode,
        min_trade_count=args.min_trade_count,
        rolling_sessions_per_fold=args.rolling_sessions_per_fold,
        rolling_max_folds=args.rolling_max_folds,
        rolling_max_episodes_per_fold=args.rolling_max_episodes_per_fold,
        min_positive_fold_rate=args.min_positive_fold_rate,
        write_policy_artifacts=args.write_policy_artifacts,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    payload = run_cost_gate(_parse_args(argv))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
