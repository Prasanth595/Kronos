"""Read-only portfolio paper replay.

The replay consumes candidate rows and writes decision/NAV/risk logs only.  It
does not integrate with broker, order, or execution APIs.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .portfolio_env import ACTION_HOLD, PortfolioEnv, PortfolioEnvConfig
from .risk_gate import RiskGate, RiskGateConfig, RiskState
from .symbol_norm import read_candidates_csv


DEFAULT_PAPER_REPLAY_OUTPUT_DIR = Path("webui") / "rl_runs" / "stom_portfolio_paper_replay"


@dataclass(frozen=True)
class PaperReplayConfig:
    candidate_path: Optional[str] = None
    output_dir: str = str(DEFAULT_PAPER_REPLAY_OUTPUT_DIR)
    read_only: bool = True
    top_k_candidates: int = 3
    max_positions: int = 2
    max_steps: int = 24
    seed: int = 100
    initial_cash: float = 1_000_000.0
    cost_bps: float = 25.0
    slippage_bps: float = 0.0
    max_drawdown_pct: float = 20.0
    max_consecutive_losses: int = 3
    max_daily_trades: int = 20
    max_position_weight: float = 0.50
    write_artifacts: bool = True


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _proposed_action(env: PortfolioEnv, info: Mapping[str, Any]) -> int:
    mask = list(info["action_mask"])
    sell_offset = 1 + env.config.top_k_candidates
    if int(info["current_step"]) % 5 == 4:
        for action in range(sell_offset, len(mask)):
            if mask[action]:
                return action
    for action in range(1, sell_offset):
        if mask[action]:
            return action
    return ACTION_HOLD


def _action_target(env: PortfolioEnv, info: Mapping[str, Any], action: int) -> Dict[str, Any]:
    """Resolve the symbol/slot a proposed ``action`` would touch.

    Read-only: looks up the current-bar candidate frame (buy) or the held
    symbols (sell) without mutating any state.  Returns ``slot`` and best-effort
    ``symbol`` so blocked-action reason codes carry both.
    """

    decoded = env.decode_action(action)
    action_type = str(decoded["type"])
    slot = decoded.get("slot")
    symbol = ""
    if action_type == "buy" and slot is not None:
        candidates = env._current_candidates()
        if int(slot) < len(candidates):
            symbol = str(candidates.iloc[int(slot)]["symbol"])
    elif action_type == "sell" and slot is not None:
        # ``info["positions"]`` is a list of position dicts already sorted by
        # symbol, matching the env's slot ordering (``_holding_symbols()``).
        holdings = [str(p["symbol"]) for p in info.get("positions", []) if "symbol" in p]
        if int(slot) < len(holdings):
            symbol = holdings[int(slot)]
    return {"action_type": action_type, "slot": slot, "symbol": symbol}


def run_paper_replay(config: PaperReplayConfig) -> Dict[str, Any]:
    if not config.read_only:
        raise ValueError("Paper replay must run with read_only=True; write-mode order routing is not implemented.")
    candidates = read_candidates_csv(config.candidate_path) if config.candidate_path else None
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
    gate = RiskGate(
        RiskGateConfig(
            max_drawdown_pct=config.max_drawdown_pct,
            max_consecutive_losses=config.max_consecutive_losses,
            max_daily_trades=config.max_daily_trades,
            max_position_weight=config.max_position_weight,
            max_positions=config.max_positions,
        )
    )
    _, info = env.reset(seed=config.seed)
    risk_state = RiskState(peak_nav=float(info["nav"]), last_nav=float(info["nav"]))
    decisions: List[Dict[str, Any]] = []
    risk_triggers: List[Dict[str, Any]] = []
    blocked_actions: List[Dict[str, Any]] = []
    terminated = False
    truncated = False
    steps = 0
    while not (terminated or truncated):
        if config.max_steps and steps >= int(config.max_steps):
            break
        proposed = _proposed_action(env, info)
        target = _action_target(env, info, proposed)
        decoded = env.decode_action(proposed)
        action_type = str(decoded["type"])
        proposed_weight = float(env.config.buy_fraction) if action_type == "buy" else 0.0
        risk = gate.evaluate(
            action_type=action_type,
            nav=float(info["nav"]),
            position_count=len(info["positions"]),
            proposed_weight=proposed_weight,
            state=risk_state,
        )
        # A pure HOLD never routes an order, so the risk gate's portfolio-level
        # blocks (drawdown / consecutive_losses) only count as *blocked actions*
        # when an order (buy/sell) was actually proposed.
        risk_blocked = (not risk["allowed"]) and action_type != "hold"
        action = ACTION_HOLD if risk_blocked else proposed
        if risk_blocked:
            blocked = {
                "timestamp": info["timestamp"],
                "source": "risk_gate",
                "proposed_action": proposed,
                "action_type": action_type,
                "slot": target["slot"],
                "symbol": target["symbol"],
                "reason": risk["reason"],
                "risk_state": risk["state"],
            }
            blocked_actions.append(blocked)
            risk_triggers.append(
                {
                    "timestamp": info["timestamp"],
                    "proposed_action": proposed,
                    "reason": risk["reason"],
                    "risk_state": risk["state"],
                }
            )
        nav_before = float(info["nav"])
        invalid_before = len(env.invalid_actions)
        _, reward, terminated, truncated, next_info = env.step(action)
        traded = int(next_info["trade_count"]) > int(info["trade_count"])
        gate.update_after_step(risk_state, nav_before=nav_before, nav_after=float(next_info["nav"]), traded=traded)
        # The env masks structurally invalid orders (padding slot, already held,
        # unfillable / no T+1).  Surface those as blocked actions too, with the
        # current risk state attached so every blocked row carries one.
        env_blocked = not risk_blocked and len(env.invalid_actions) > invalid_before
        env_reason = next_info.get("blocked_reason", "") if env_blocked else ""
        if env_blocked:
            blocked_actions.append(
                {
                    "timestamp": info["timestamp"],
                    "source": "env_mask",
                    "proposed_action": proposed,
                    "action_type": action_type,
                    "slot": target["slot"],
                    "symbol": target["symbol"],
                    "reason": env_reason,
                    "risk_state": dict(risk["state"]),
                }
            )
        decisions.append(
            {
                "timestamp": info["timestamp"],
                "proposed_action": proposed,
                "executed_action": action,
                "action_type": action_type,
                "symbol": target["symbol"],
                "blocked": risk_blocked or env_blocked,
                "blocked_source": "risk_gate" if risk_blocked else ("env_mask" if env_blocked else ""),
                "blocked_reason": risk["reason"] if risk_blocked else env_reason,
                "env_blocked_reason": next_info.get("blocked_reason", ""),
                "reward": float(reward),
                "nav_after": float(next_info["nav"]),
                "read_only": True,
            }
        )
        info = next_info
        steps += 1

    output_dir = Path(config.output_dir)
    payload: Dict[str, Any] = {
        "mode": "stom_rl_portfolio_paper_replay",
        "config": asdict(config),
        "summary": {
            "read_only": True,
            "steps": steps,
            "final_nav": float(info["nav"]),
            "trade_count": int(info["trade_count"]),
            "blocked_action_count": len(blocked_actions),
            "risk_blocked_count": sum(1 for b in blocked_actions if b["source"] == "risk_gate"),
            "env_blocked_count": sum(1 for b in blocked_actions if b["source"] == "env_mask"),
            "risk_trigger_count": len(risk_triggers),
            "order_write_path": False,
        },
        "artifacts": {
            "output_dir": str(output_dir),
            "summary_json": str(output_dir / "paper_replay_summary.json"),
            "decisions_csv": str(output_dir / "decisions.csv"),
            "nav_csv": str(output_dir / "nav.csv"),
            "risk_triggers_json": str(output_dir / "risk_triggers.json"),
            "blocked_actions_json": str(output_dir / "blocked_actions.json"),
        },
    }
    if config.write_artifacts:
        _write_json(output_dir / "paper_replay_summary.json", payload)
        _write_csv(
            output_dir / "decisions.csv",
            decisions,
            [
                "timestamp",
                "proposed_action",
                "executed_action",
                "action_type",
                "symbol",
                "blocked",
                "blocked_source",
                "blocked_reason",
                "env_blocked_reason",
                "reward",
                "nav_after",
                "read_only",
            ],
        )
        _write_csv(output_dir / "nav.csv", env.nav_log, ["timestamp", "step", "nav", "cash", "position_count"])
        _write_json(output_dir / "risk_triggers.json", {"risk_triggers": risk_triggers, "env_blocked_actions": env.invalid_actions})
        _write_json(output_dir / "blocked_actions.json", {"blocked_actions": blocked_actions})
    return payload


def _parse_args(argv: Optional[Sequence[str]] = None) -> PaperReplayConfig:
    parser = argparse.ArgumentParser(description="Run read-only portfolio paper replay.")
    parser.add_argument("--read-only", action="store_true", default=True)
    parser.add_argument("--candidate-csv", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_PAPER_REPLAY_OUTPUT_DIR))
    parser.add_argument("--top-k-candidates", type=int, default=3)
    parser.add_argument("--max-positions", type=int, default=2)
    parser.add_argument("--max-steps", type=int, default=24)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--cost-bps", type=float, default=25.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--max-drawdown-pct", type=float, default=20.0)
    parser.add_argument("--max-consecutive-losses", type=int, default=3)
    parser.add_argument("--max-daily-trades", type=int, default=20)
    parser.add_argument("--max-position-weight", type=float, default=0.50)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    return PaperReplayConfig(
        candidate_path=args.candidate_csv,
        output_dir=args.output_dir,
        read_only=True,
        top_k_candidates=args.top_k_candidates,
        max_positions=args.max_positions,
        max_steps=args.max_steps,
        seed=args.seed,
        initial_cash=args.initial_cash,
        cost_bps=args.cost_bps,
        slippage_bps=args.slippage_bps,
        max_drawdown_pct=args.max_drawdown_pct,
        max_consecutive_losses=args.max_consecutive_losses,
        max_daily_trades=args.max_daily_trades,
        max_position_weight=args.max_position_weight,
        write_artifacts=not args.no_write,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    payload = run_paper_replay(_parse_args(argv))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
