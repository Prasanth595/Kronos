"""Portfolio RL smoke runner.

This page-4 runner proves the portfolio environment contract and artifact
schema without requiring a heavy RL dependency.  The deterministic smoke policy
uses the same fixed Discrete action layout that an RL agent will consume.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .portfolio_env import ACTION_HOLD, PortfolioEnv, PortfolioEnvConfig
from .rl_events import RlLiveEventWriter, summarize_live_event_file
from .symbol_norm import read_candidates_csv


DEFAULT_PORTFOLIO_TRAIN_OUTPUT_DIR = Path("webui") / "rl_runs" / "stom_portfolio_smoke"

# Live-event semantics for the portfolio runner (shared with the dashboard's
# realtime view via the same JSONL schema sb3_smoke emits):
#   algorithm = "portfolio", phase = "train"
#   equity    = NAV, reward = step reward, action = discrete action index
#   position  = number of held positions, price = best-candidate decision price
PORTFOLIO_LIVE_ALGORITHM = "portfolio"
PORTFOLIO_LIVE_PHASE = "train"


@dataclass(frozen=True)
class PortfolioTrainConfig:
    candidate_path: Optional[str] = None
    output_dir: str = str(DEFAULT_PORTFOLIO_TRAIN_OUTPUT_DIR)
    top_k_candidates: int = 3
    max_positions: int = 2
    max_steps: int = 12
    seed: int = 100
    initial_cash: float = 1_000_000.0
    cost_bps: float = 25.0
    slippage_bps: float = 0.0
    write_artifacts: bool = True
    write_live_events: bool = True


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _representative_price(env: PortfolioEnv) -> Optional[float]:
    """Best-candidate decision-bar price for the current step.

    The portfolio holds many symbols, so the single-symbol ``price`` field of a
    live event is filled with the top-ranked candidate's decision-bar close (the
    same bar the observation is built from).  Returns ``None`` when no candidate
    is present so the optional field is simply omitted rather than fabricated.
    """

    candidates = env._current_candidates()
    if candidates.empty:
        return None
    try:
        return float(candidates.iloc[0]["price"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _emit_live_event(
    writer: RlLiveEventWriter,
    *,
    global_step: int,
    action: int,
    info: Mapping[str, Any],
    reward: float,
    price: Optional[float],
) -> None:
    """Write one portfolio step as an ``RlLiveEvent`` (NAV mapped to equity)."""

    nav = float(info["nav"])
    cash = float(info["cash"])
    positions = info.get("positions") or []
    bar_timestamp = info.get("timestamp")
    writer.write_step(
        algorithm=PORTFOLIO_LIVE_ALGORITHM,
        phase=PORTFOLIO_LIVE_PHASE,
        global_step=global_step,
        timestamp=bar_timestamp,
        # Pin the event wall-clock to the deterministic bar timestamp so a fixed
        # seed yields byte-identical events (the dataclass otherwise defaults to
        # the non-deterministic ``utc_now_iso``).
        timestamp_utc=bar_timestamp,
        price=price,
        action=int(action),
        reward=float(reward),
        position=float(len(positions)),
        equity=nav,
        info={
            "cash": cash,
            "holdings_value": nav - cash,
            "nav": nav,
            "trade_count": int(info.get("trade_count", 0)),
            "candidate_count": int(sum(info.get("candidate_mask") or [])),
            "invalid_action": bool(info.get("invalid_action", False)),
        },
    )


def _deterministic_action(env: PortfolioEnv, info: Mapping[str, Any]) -> int:
    mask = list(info["action_mask"])
    sell_offset = 1 + env.config.top_k_candidates
    if int(info["current_step"]) % 4 == 3:
        for action in range(sell_offset, len(mask)):
            if mask[action]:
                return action
    for action in range(1, sell_offset):
        if mask[action]:
            return action
    return ACTION_HOLD


def run_portfolio_smoke(config: PortfolioTrainConfig) -> Dict[str, Any]:
    candidates = None
    if config.candidate_path:
        candidates = read_candidates_csv(config.candidate_path)
    env = PortfolioEnv(
        PortfolioEnvConfig(
            candidate_path=config.candidate_path,
            top_k_candidates=config.top_k_candidates,
            max_positions=config.max_positions,
            initial_cash=config.initial_cash,
            cost_bps=config.cost_bps,
            slippage_bps=config.slippage_bps,
            seed=config.seed,
        ),
        candidates=candidates,
    )
    observation, info = env.reset(seed=config.seed)

    output_dir = Path(config.output_dir)
    live_events_path = output_dir / "rl_live_events.jsonl"
    event_writer: Optional[RlLiveEventWriter] = None
    if config.write_artifacts and config.write_live_events:
        event_writer = RlLiveEventWriter(live_events_path, run_id=output_dir.name)
        event_writer.reset()

    terminated = False
    truncated = False
    rewards: List[float] = []
    steps = 0
    while not (terminated or truncated):
        if config.max_steps and steps >= int(config.max_steps):
            break
        action = _deterministic_action(env, info)
        # Capture the decision-bar price before stepping so the event price
        # matches the bar the action was taken on (no lookahead).
        decision_price = _representative_price(env)
        observation, reward, terminated, truncated, info = env.step(action)
        rewards.append(float(reward))
        steps += 1
        if event_writer is not None:
            _emit_live_event(
                event_writer,
                global_step=steps,
                action=action,
                info=info,
                reward=reward,
                price=decision_price,
            )

    payload: Dict[str, Any] = {
        "mode": "stom_rl_portfolio_train_smoke",
        "config": asdict(config),
        "summary": {
            "steps": steps,
            "final_nav": float(info["nav"]),
            "total_reward": float(sum(rewards)),
            "trade_count": int(info["trade_count"]),
            "invalid_action_count": int(info["invalid_action_count"]),
            "observation_shape": list(observation.shape),
            "action_space_n": int(env.action_space.n),
            "candidate_mask_last": info["candidate_mask"],
            "holding_mask_last": info["holding_mask"],
        },
        "artifacts": {
            "output_dir": str(output_dir),
            "summary_json": str(output_dir / "portfolio_train_summary.json"),
            "actions_csv": str(output_dir / "actions.csv"),
            "trades_csv": str(output_dir / "trades.csv"),
            "nav_csv": str(output_dir / "nav.csv"),
            "blocked_actions_json": str(output_dir / "blocked_actions.json"),
            "live_events_jsonl": str(live_events_path),
            "live_summary_json": str(output_dir / "rl_live_summary.json"),
        },
    }
    if event_writer is not None:
        live_summary = summarize_live_event_file(live_events_path)
        payload["live_events"] = live_summary
        payload["summary"]["live_event_count"] = live_summary["event_count"]
        _write_json(output_dir / "rl_live_summary.json", live_summary)
    if config.write_artifacts:
        _write_json(output_dir / "portfolio_train_summary.json", payload)
        _write_csv(
            output_dir / "actions.csv",
            env.action_log,
            ["timestamp", "action", "action_type", "slot", "invalid_action", "blocked_reason", "reward", "nav_after"],
        )
        _write_csv(output_dir / "trades.csv", env.trade_log, ["timestamp", "symbol", "side", "price", "quantity", "gross_value", "cost", "cash_after", "realized_pnl"])
        _write_csv(output_dir / "nav.csv", env.nav_log, ["timestamp", "step", "nav", "cash", "position_count"])
        _write_json(output_dir / "blocked_actions.json", {"blocked_actions": env.invalid_actions})
    return payload


def _parse_args(argv: Optional[Sequence[str]] = None) -> PortfolioTrainConfig:
    parser = argparse.ArgumentParser(description="Run portfolio environment smoke training.")
    parser.add_argument("--smoke", action="store_true", help="Use deterministic synthetic candidates when no CSV is provided.")
    parser.add_argument("--candidate-csv", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_PORTFOLIO_TRAIN_OUTPUT_DIR))
    parser.add_argument("--top-k-candidates", type=int, default=3)
    parser.add_argument("--max-positions", type=int, default=2)
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--cost-bps", type=float, default=25.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--no-live-events", action="store_true")
    args = parser.parse_args(argv)
    return PortfolioTrainConfig(
        candidate_path=args.candidate_csv,
        output_dir=args.output_dir,
        top_k_candidates=args.top_k_candidates,
        max_positions=args.max_positions,
        max_steps=args.max_steps,
        seed=args.seed,
        initial_cash=args.initial_cash,
        cost_bps=args.cost_bps,
        slippage_bps=args.slippage_bps,
        write_artifacts=not args.no_write,
        write_live_events=not args.no_live_events,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    payload = run_portfolio_smoke(_parse_args(argv))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
