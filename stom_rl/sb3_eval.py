"""Eval-only re-evaluation of saved Stable-Baselines3 STOM models (no retraining)."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .episode_manifest import DEFAULT_OUTPUT_DIR
from .rl_events import RlLiveEventWriter, summarize_live_event_file
from .sb3_smoke import (
    DEFAULT_ALGORITHMS,
    Sb3SmokeConfig,
    _evaluate_model,
    _summarize_model,
    _torch_runtime,
    _write_csv,
    _write_json,
)


DEFAULT_SB3_EVAL_OUTPUT_DIR = Path("webui") / "rl_runs" / "stom_1s_2025_sb3_eval"


@dataclass(frozen=True)
class Sb3EvalConfig:
    """Configuration for re-evaluating saved SB3 models on more episodes."""

    model_dir: str
    algorithms: Tuple[str, ...] = ("dqn", "ppo")
    eval_episodes: int = 100
    max_eval_steps_per_episode: int = 2048
    manifest_path: str = str(DEFAULT_OUTPUT_DIR / "episode_manifest.json")
    eval_split: str = "test"
    seed: int = 100
    lookback_window: int = 300
    reward_horizon_seconds: int = 300
    cost_bps: float = 25.0
    slippage_bps: float = 0.0
    device: str = "auto"
    output_dir: Optional[str] = None
    write_artifacts: bool = True
    write_live_events: bool = True
    live_event_sample_interval: int = 1
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


def _resolve_output_dir(config: Sb3EvalConfig) -> Path:
    if config.output_dir:
        return Path(config.output_dir)
    return Path("webui") / "rl_runs" / f"stom_1s_2025_sb3_50k_eval{int(config.eval_episodes)}"


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


def run_sb3_eval(config: Sb3EvalConfig) -> Dict[str, Any]:
    """Re-evaluate saved SB3 models on more episodes without any training."""

    algorithms = tuple(config.algorithms)
    if not algorithms:
        raise ValueError("At least one SB3 algorithm is required.")

    model_dir = Path(config.model_dir)
    source_run = config.source_run or model_dir.name
    source_summary = _load_source_summary(model_dir)
    output_dir = _resolve_output_dir(config)
    runtime = _torch_runtime()

    model_summaries: List[Dict[str, Any]] = []
    all_actions: List[Dict[str, Any]] = []
    all_trades: List[Dict[str, Any]] = []
    all_equity: List[Dict[str, Any]] = []
    all_episodes: List[Dict[str, Any]] = []
    evaluated_algorithms: List[str] = []
    skipped: List[Dict[str, str]] = []

    event_writer: Optional[RlLiveEventWriter] = None
    live_events_path = output_dir / "rl_live_events.jsonl"
    if config.write_artifacts and config.write_live_events:
        event_writer = RlLiveEventWriter(live_events_path, run_id=output_dir.name)
        event_writer.reset()

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

        smoke_config = Sb3SmokeConfig(
            manifest_path=config.manifest_path,
            output_dir=str(output_dir),
            eval_split=config.eval_split,
            algorithms=(algorithm,),
            total_timesteps=source_timesteps,
            max_eval_episodes=config.eval_episodes,
            max_eval_steps_per_episode=config.max_eval_steps_per_episode,
            seed=config.seed,
            lookback_window=config.lookback_window,
            reward_horizon_seconds=config.reward_horizon_seconds,
            cost_bps=config.cost_bps,
            slippage_bps=config.slippage_bps,
            device=config.device,
            write_artifacts=config.write_artifacts,
            write_live_events=config.write_live_events,
            live_event_sample_interval=config.live_event_sample_interval,
        )

        model = _load_model(algorithm, model_path, config.device)
        evaluation = _evaluate_model(model, algorithm, smoke_config, event_writer=event_writer)
        summary = _summarize_model(
            algorithm=algorithm,
            config=smoke_config,
            episode_rows=evaluation["episodes"],
            trade_rows=evaluation["trades"],
            aggregate_equity_curve=evaluation["aggregate_equity_curve"],
            training_elapsed_seconds=0.0,
            model_name=f"{source_model}_eval",
            eval_only=True,
            source_run=source_run,
            source_model=source_model,
            is_smoke=False,
        )
        model_summaries.append(summary)
        all_actions.extend(evaluation["actions"])
        all_trades.extend(evaluation["trades"])
        all_equity.extend(evaluation["equity"])
        all_episodes.extend(evaluation["episodes"])
        evaluated_algorithms.append(algorithm)

    ranking = sorted(model_summaries, key=lambda row: float(row["avg_episode_net_return_pct"]), reverse=True)
    payload: Dict[str, Any] = {
        "mode": "stom_rl_sb3_eval",
        "config": asdict(config),
        "runtime": runtime,
        "summary": {
            "eval_only": True,
            "algorithm_count": len(evaluated_algorithms),
            "algorithms": list(evaluated_algorithms),
            "skipped_algorithms": skipped,
            "source_run": source_run,
            "eval_episodes": int(config.eval_episodes),
            "best_algorithm_by_avg_episode_net": ranking[0]["algorithm"] if ranking else None,
            "best_model": ranking[0]["model"] if ranking else None,
            "device_requested": config.device,
            "cuda_available": runtime["cuda_available"],
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
                "eval_episode_count",
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


def _parse_args(argv: Optional[Sequence[str]] = None) -> Sb3EvalConfig:
    parser = argparse.ArgumentParser(
        description="Re-evaluate saved STOM SB3 models on more episodes without retraining.",
    )
    parser.add_argument("--model-dir", required=True, help="Directory containing {algo}_model.zip and source summary.")
    parser.add_argument("--algorithms", default=",".join(("dqn", "ppo")))
    parser.add_argument("--eval-episodes", type=int, default=100)
    parser.add_argument("--max-eval-steps-per-episode", type=int, default=2048)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--manifest", default=str(DEFAULT_OUTPUT_DIR / "episode_manifest.json"))
    parser.add_argument("--eval-split", default="test")
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--cost-bps", type=float, default=25.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--no-live-events", action="store_true")
    parser.add_argument("--live-event-sample-interval", type=int, default=1)
    parser.add_argument("--source-run", default=None)
    args = parser.parse_args(argv)
    return Sb3EvalConfig(
        model_dir=args.model_dir,
        algorithms=_parse_algorithms(args.algorithms),
        eval_episodes=args.eval_episodes,
        max_eval_steps_per_episode=args.max_eval_steps_per_episode,
        manifest_path=args.manifest,
        eval_split=args.eval_split,
        seed=args.seed,
        cost_bps=args.cost_bps,
        slippage_bps=args.slippage_bps,
        device=args.device,
        output_dir=args.output_dir,
        write_artifacts=not args.no_write,
        write_live_events=not args.no_live_events,
        live_event_sample_interval=args.live_event_sample_interval,
        source_run=args.source_run,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    payload = run_sb3_eval(_parse_args(argv))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
