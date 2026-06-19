"""DQN smoke training + OOS evaluator for STOM orderbook RL.

The output is an honest candidate artifact, not a live-trading approval.  It
uses the marketable-only orderbook environment and compares the learned DQN
policy against a same-decision-time ``ts_imb`` TP5/SL1/time rule.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .marketable_fill import simulate_rule_from_entry
from .orderbook_rl_env import (
    ACTION_NAMES,
    DB_REQUIRED_COLUMNS,
    StomOrderbookRlEnvConfig,
    _connect_readonly,
    _quote_ident,
    _table_columns,
    normalize_orderbook_frame,
)
from .orderbook_sb3_adapter import OrderbookEpisode, StomOrderbookGymEnv
from .rl_events import RlLiveEventWriter, summarize_live_event_file


DEFAULT_OUTPUT_DIR = Path("webui") / "rl_runs" / "stom_orderbook_dqn_smoke"
CHANGE_RATE_THRESHOLD = 2.0
TRADE_STRENGTH_THRESHOLD = 100.0
BOOK_IMBALANCE_THRESHOLD = 0.5


@dataclass(frozen=True)
class OrderbookDqnSmokeConfig:
    db_path: str = str(Path("_database") / "stock_tick_back.db")
    output_dir: str = str(DEFAULT_OUTPUT_DIR)
    max_scan_symbols: int = 300
    train_episodes: int = 32
    eval_episodes: int = 32
    lookback_window: int = 30
    max_episode_steps: int = 120
    total_timesteps: int = 512
    seed: int = 100
    cost_bps: float = 23.0
    slippage_bps: float = 0.0
    overtrade_penalty: float = 0.0
    constrain_invalid_actions: bool = False
    single_entry_exit: bool = False
    fixed_entry_exit_only: bool = False
    device: str = "auto"
    dqn_learning_starts: int = 32
    dqn_buffer_size: int = 4096
    dqn_batch_size: int = 32
    min_eval_episodes: int = 10
    min_baseline_delta_pct: float = 0.0
    write_artifacts: bool = True
    write_live_events: bool = True


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _sb3_imports():
    from stable_baselines3 import DQN
    from stable_baselines3.common.env_checker import check_env

    return DQN, check_env


def _torch_runtime() -> Dict[str, Any]:
    import torch

    return {
        "torch_version": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_version": torch.version.cuda,
        "cuda_device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


def _stock_tables(conn: Any, *, max_scan_symbols: int) -> List[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    tables = [str(row[0]) for row in rows if str(row[0]).isdigit()]
    if max_scan_symbols and max_scan_symbols > 0:
        return tables[: int(max_scan_symbols)]
    return tables


def _candidate_sessions(conn: Any, table: str, *, per_table_limit: int = 16) -> List[Dict[str, Any]]:
    qt = _quote_ident(table)
    q = f"""
        WITH ranked AS (
          SELECT
            substr(CAST("index" AS TEXT), 1, 8) AS session,
            "index" AS ts_key,
            "현재가" AS price,
            "등락율" AS change_rate,
            "체결강도" AS trade_strength,
            "매수총잔량" AS bid_tot,
            "매도총잔량" AS ask_tot,
            ROW_NUMBER() OVER (
              PARTITION BY substr(CAST("index" AS TEXT), 1, 8)
              ORDER BY "index"
            ) AS rn
          FROM {qt}
          WHERE substr(CAST("index" AS TEXT), 9, 6) >= '090000'
            AND substr(CAST("index" AS TEXT), 9, 6) <= '092000'
            AND "현재가" > 0
        )
        SELECT session, ts_key, price, change_rate, trade_strength, bid_tot, ask_tot
        FROM ranked
        WHERE rn = 1
          AND change_rate >= ?
          AND trade_strength >= ?
          AND (bid_tot + ask_tot) > 0
          AND (bid_tot * 1.0 / (bid_tot + ask_tot)) >= ?
        ORDER BY session
        LIMIT ?
    """
    rows = conn.execute(
        q,
        (
            float(CHANGE_RATE_THRESHOLD),
            float(TRADE_STRENGTH_THRESHOLD),
            float(BOOK_IMBALANCE_THRESHOLD),
            int(per_table_limit),
        ),
    ).fetchall()
    out = []
    for session, ts_key, price, change_rate, trade_strength, bid_tot, ask_tot in rows:
        out.append(
            {
                "symbol": table,
                "session": str(session),
                "timestamp_key": int(ts_key),
                "entry_price": float(price),
                "entry_change_rate": float(change_rate),
                "entry_trade_strength": float(trade_strength),
                "entry_book_imbalance": float(bid_tot) / (float(bid_tot) + float(ask_tot)),
            }
        )
    return out


def _episode_frame(conn: Any, table: str, session: str, *, max_episode_steps: int, lookback_window: int) -> pd.DataFrame:
    columns = ["index", "등락율", *[col for col in DB_REQUIRED_COLUMNS if col != "index"]]
    select_cols = ", ".join(_quote_ident(col) for col in columns)
    qt = _quote_ident(table)
    limit = max(int(lookback_window) + int(max_episode_steps) + 3, int(lookback_window) + 2)
    q = f"""
        SELECT {select_cols}
        FROM {qt}
        WHERE substr(CAST("index" AS TEXT), 1, 8) = ?
          AND substr(CAST("index" AS TEXT), 9, 6) >= '090000'
          AND substr(CAST("index" AS TEXT), 9, 6) <= '092000'
        ORDER BY "index"
        LIMIT ?
    """
    return pd.read_sql_query(q, conn, params=(str(session), int(limit)))


def load_orderbook_ts_imb_episodes(config: OrderbookDqnSmokeConfig) -> Tuple[List[OrderbookEpisode], List[Dict[str, Any]]]:
    """Extract bounded ts_imb opening episodes from the local STOM DB."""

    conn = _connect_readonly(config.db_path)
    candidates: List[Dict[str, Any]] = []
    episodes: List[OrderbookEpisode] = []
    try:
        required = set(["등락율", *DB_REQUIRED_COLUMNS])
        target = int(config.train_episodes) + int(config.eval_episodes)
        for table in _stock_tables(conn, max_scan_symbols=int(config.max_scan_symbols)):
            columns = set(_table_columns(conn, table))
            if not required.issubset(columns):
                continue
            candidates.extend(_candidate_sessions(conn, table, per_table_limit=8))
            candidates = sorted(candidates, key=lambda row: (row["session"], row["symbol"]))
            if len(candidates) >= target * 2:
                break

        for row in candidates:
            if len(episodes) >= target:
                break
            frame = _episode_frame(
                conn,
                row["symbol"],
                row["session"],
                max_episode_steps=int(config.max_episode_steps),
                lookback_window=int(config.lookback_window),
            )
            try:
                normalized = normalize_orderbook_frame(frame)
            except ValueError:
                continue
            if len(normalized) < int(config.lookback_window) + 2:
                continue
            episode = OrderbookEpisode(
                episode_id=f"{row['symbol']}_{row['session']}",
                symbol=str(row["symbol"]),
                session=str(row["session"]),
                frame=frame,
            )
            episodes.append(episode)
    finally:
        conn.close()
    return episodes, candidates


def _make_env(episodes: Sequence[OrderbookEpisode], config: OrderbookDqnSmokeConfig) -> StomOrderbookGymEnv:
    return StomOrderbookGymEnv(
        episodes,
        StomOrderbookRlEnvConfig(
            lookback_window=int(config.lookback_window),
            cost_bps=float(config.cost_bps),
            slippage_bps=float(config.slippage_bps),
            overtrade_penalty=float(config.overtrade_penalty),
            max_episode_steps=int(config.max_episode_steps),
            force_close_on_done=True,
        ),
        constrain_invalid_actions=bool(config.constrain_invalid_actions),
        single_entry_exit=bool(config.single_entry_exit),
        fixed_entry_exit_only=bool(config.fixed_entry_exit_only),
    )


def _baseline_same_decision(episode: OrderbookEpisode, config: OrderbookDqnSmokeConfig) -> Dict[str, Any]:
    frame = normalize_orderbook_frame(episode.frame)
    entry_idx = min(max(0, int(config.lookback_window) - 1), len(frame) - 1)
    exit_idx = min(len(frame) - 1, entry_idx + int(config.max_episode_steps))
    prices = [float(v) for v in frame["price"].tolist()]
    bids = [float(v) for v in frame["bid1"].tolist()]
    asks = [float(v) for v in frame["ask1"].tolist()]
    secs = [int(v) for v in frame["sec"].tolist()]
    result = simulate_rule_from_entry(
        prices,
        bids,
        asks,
        secs,
        entry_idx,
        tp_pct=5.0,
        sl_pct=1.0,
        time_exit_sec=secs[exit_idx],
        cost_bps=float(config.cost_bps),
        slippage_bps=float(config.slippage_bps),
    )
    return {
        "episode_id": episode.episode_id,
        "symbol": episode.symbol,
        "session": episode.session,
        "baseline_policy": "ts_imb_same_decision_tp5_sl1_time",
        "baseline_net_return_pct": float(result[0]),
        "baseline_exit_reason": result[1],
    }


def _train_dqn(train_episodes: Sequence[OrderbookEpisode], config: OrderbookDqnSmokeConfig, writer: Optional[RlLiveEventWriter]):
    DQN, _ = _sb3_imports()
    from stable_baselines3.common.callbacks import BaseCallback

    class EventCallback(BaseCallback):
        def __init__(self, event_writer: Optional[RlLiveEventWriter]):
            super().__init__(verbose=0)
            self.event_writer = event_writer

        def _on_step(self) -> bool:
            if self.event_writer is None:
                return True
            infos = self.locals.get("infos") or []
            rewards = self.locals.get("rewards") or []
            actions = self.locals.get("actions") or []
            info = dict(infos[0]) if len(infos) else {}
            action = actions[0] if len(actions) else None
            action_int = int(np.asarray(action).item()) if action is not None else None
            event_action = info.get("executed_action", action_int)
            event_action_int = int(event_action) if event_action is not None else None
            reward = float(rewards[0]) if len(rewards) else None
            self.event_writer.write_step(
                algorithm="orderbook_dqn",
                phase="train",
                global_step=int(self.num_timesteps),
                episode_id=info.get("episode_id"),
                timestamp=info.get("timestamp"),
                price=None,
                action=event_action_int,
                reward=reward,
                position=info.get("position"),
                equity=info.get("equity"),
                exploration=getattr(self.model, "exploration_rate", None),
                source="orderbook_sb3_smoke",
                info={
                    "symbol": info.get("symbol"),
                    "session": info.get("session"),
                    "invalid_action": info.get("invalid_action"),
                    "policy_action": info.get("policy_action"),
                    "executed_action": info.get("executed_action"),
                    "semantic_action_name": info.get("semantic_action_name"),
                    "action_remapped": info.get("action_remapped"),
                },
            )
            return True

    env = _make_env(train_episodes, config)
    try:
        _, check_env = _sb3_imports()
        check_env(env, warn=True, skip_render_check=True)
        learning_starts = max(1, min(int(config.dqn_learning_starts), max(1, int(config.total_timesteps) // 4)))
        model = DQN(
            "MlpPolicy",
            env,
            seed=int(config.seed),
            device=str(config.device),
            verbose=0,
            learning_starts=learning_starts,
            buffer_size=max(int(config.dqn_buffer_size), int(config.total_timesteps) * 2, 128),
            batch_size=max(2, min(int(config.dqn_batch_size), int(config.total_timesteps))),
            train_freq=4,
            gradient_steps=1,
            target_update_interval=64,
            exploration_fraction=0.5,
            exploration_final_eps=0.05,
            policy_kwargs={"net_arch": [64, 32]},
        )
        started = time.perf_counter()
        model.learn(
            total_timesteps=int(config.total_timesteps),
            progress_bar=False,
            callback=EventCallback(writer),
        )
        elapsed = time.perf_counter() - started
        return model, elapsed, {
            "passed": True,
            "observation_space": str(env.observation_space),
            "action_space": str(env.action_space),
            "feature_columns": list(env.raw_env.feature_columns),
        }
    finally:
        env.close()


def _evaluate_dqn(
    model: Any,
    eval_episodes: Sequence[OrderbookEpisode],
    config: OrderbookDqnSmokeConfig,
    writer: Optional[RlLiveEventWriter],
) -> Dict[str, Any]:
    episode_rows: List[Dict[str, Any]] = []
    action_rows: List[Dict[str, Any]] = []
    baseline_rows: List[Dict[str, Any]] = []
    global_step = 0
    for idx, episode in enumerate(eval_episodes):
        env = _make_env([episode], config)
        observation, info = env.reset(seed=int(config.seed) + idx)
        terminated = False
        truncated = False
        steps = 0
        last_info = dict(info)
        policy_invalid_attempts = 0
        action_remaps = 0
        while not (terminated or truncated):
            action, _ = model.predict(observation, deterministic=True)
            action_int = int(np.asarray(action).item())
            observation, reward, terminated, truncated, step_info = env.step(action_int)
            steps += 1
            global_step += 1
            last_info = dict(step_info)
            executed_action = int(step_info.get("executed_action", step_info.get("action", action_int)))
            action_name = str(step_info.get("semantic_action_name") or ACTION_NAMES.get(action_int, str(action_int)))
            executed_action_name = str(
                step_info.get("executed_action_name") or ACTION_NAMES.get(executed_action, str(executed_action))
            )
            action_remapped = bool(step_info.get("action_remapped"))
            raw_invalid_action = bool(step_info.get("invalid_action"))
            if action_remapped:
                action_remaps += 1
            if raw_invalid_action or action_remapped:
                policy_invalid_attempts += 1
            price = float(env.raw_env._row(env.raw_env.current_idx).get("price") or 0.0)
            action_row = {
                "model": "orderbook_dqn_smoke",
                "algorithm": "dqn",
                "episode_id": episode.episode_id,
                "symbol": episode.symbol,
                "session": episode.session,
                "step": steps,
                "timestamp": step_info.get("timestamp"),
                "price": price,
                "action": action_int,
                "action_name": action_name,
                "policy_action": action_int,
                "policy_action_name": step_info.get("policy_action_name") or ACTION_NAMES.get(action_int, str(action_int)),
                "executed_action": executed_action,
                "executed_action_name": executed_action_name,
                "semantic_action_name": action_name,
                "action_remapped": action_remapped,
                "invalid_action_prevented": bool(step_info.get("invalid_action_prevented")),
                "reward": float(reward),
                "equity": step_info.get("equity"),
                "position": step_info.get("position_after"),
                "invalid_action": raw_invalid_action,
            }
            action_rows.append(action_row)
            if writer is not None:
                event_action_int = executed_action if config.fixed_entry_exit_only else action_int
                writer.write_step(
                    algorithm="orderbook_dqn",
                    phase="eval",
                    global_step=global_step,
                    episode=idx,
                    episode_id=episode.episode_id,
                    timestamp=step_info.get("timestamp"),
                    price=price,
                    action=event_action_int,
                    reward=float(reward),
                    position=step_info.get("position_after"),
                    equity=step_info.get("equity"),
                    source="orderbook_sb3_smoke",
                    info={
                        "symbol": episode.symbol,
                        "session": episode.session,
                        "policy_action": action_int,
                        "executed_action": executed_action,
                        "semantic_action_name": action_name,
                        "action_remapped": action_remapped,
                        "invalid_action": raw_invalid_action,
                    },
                )
        baseline = _baseline_same_decision(episode, config)
        baseline_rows.append(baseline)
        model_net_pct = float(last_info.get("realized_net_return") or 0.0) * 100.0
        episode_rows.append(
            {
                "model": "orderbook_dqn_smoke",
                "algorithm": "dqn",
                "episode_id": episode.episode_id,
                "symbol": episode.symbol,
                "session": episode.session,
                "episode_return_pct": model_net_pct,
                "baseline_net_return_pct": baseline["baseline_net_return_pct"],
                "baseline_delta_pct": model_net_pct - float(baseline["baseline_net_return_pct"]),
                "trade_count": int(last_info.get("trade_count") or 0),
                "invalid_action_count": int(last_info.get("invalid_action_count") or 0),
                "policy_invalid_action_count": int(policy_invalid_attempts),
                "action_remap_count": int(action_remaps),
                "steps": steps,
            }
        )
        env.close()
    return {"episodes": episode_rows, "actions": action_rows, "baseline": baseline_rows}


def _mean(values: Sequence[float]) -> float:
    return float(np.mean(np.asarray(values, dtype=np.float64))) if values else 0.0


def _diagnose_policy_behavior(
    evaluation: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    config: OrderbookDqnSmokeConfig,
) -> Dict[str, Any]:
    actions = list(evaluation.get("actions", []))
    episodes = list(evaluation.get("episodes", []))
    action_counts: Dict[str, int] = {}
    executed_action_counts: Dict[str, int] = {}
    for row in actions:
        name = str(row.get("action_name") or row.get("action") or "unknown")
        action_counts[name] = action_counts.get(name, 0) + 1
        executed_name = str(row.get("executed_action_name") or row.get("executed_action") or name)
        executed_action_counts[executed_name] = executed_action_counts.get(executed_name, 0) + 1
    total_actions = sum(action_counts.values())
    invalid_count = sum(1 for row in actions if str(row.get("invalid_action")).lower() == "true")
    action_remap_count = sum(1 for row in actions if str(row.get("action_remapped")).lower() == "true")
    policy_invalid_attempt_count = sum(
        1
        for row in actions
        if str(row.get("invalid_action")).lower() == "true" or str(row.get("action_remapped")).lower() == "true"
    )
    trade_counts = [int(row.get("trade_count") or 0) for row in episodes]
    invalid_episode_counts = [int(row.get("invalid_action_count") or 0) for row in episodes]
    policy_invalid_episode_counts = [int(row.get("policy_invalid_action_count") or 0) for row in episodes]
    remap_episode_counts = [int(row.get("action_remap_count") or 0) for row in episodes]
    deltas = [float(row.get("baseline_delta_pct") or 0.0) for row in episodes]
    returns = [float(row.get("episode_return_pct") or 0.0) for row in episodes]
    baseline_returns = [float(row.get("baseline_net_return_pct") or 0.0) for row in episodes]
    worst = sorted(episodes, key=lambda row: float(row.get("baseline_delta_pct") or 0.0))[:5]
    action_rates = {
        key: (value / total_actions if total_actions else 0.0)
        for key, value in sorted(action_counts.items())
    }
    executed_action_rates = {
        key: (value / total_actions if total_actions else 0.0)
        for key, value in sorted(executed_action_counts.items())
    }
    avg_trades = _mean([float(v) for v in trade_counts])
    invalid_rate = invalid_count / total_actions if total_actions else 0.0
    action_remap_rate = action_remap_count / total_actions if total_actions else 0.0
    policy_invalid_attempt_rate = policy_invalid_attempt_count / total_actions if total_actions else 0.0
    likely_causes: List[str] = []
    if avg_trades > 6:
        likely_causes.append("overtrading")
    if invalid_rate > 0.10:
        likely_causes.append("environment_invalid_action_rate_high")
    if policy_invalid_attempt_rate > 0.10:
        likely_causes.append("policy_invalid_action_attempt_rate_high")
    if _mean(deltas) < 0:
        likely_causes.append("baseline_relative_underperformance")
    if not likely_causes:
        likely_causes.append("no_single_dominant_cause")
    return {
        "constrain_invalid_actions": bool(config.constrain_invalid_actions),
        "single_entry_exit": bool(config.single_entry_exit),
        "fixed_entry_exit_only": bool(config.fixed_entry_exit_only),
        "action_counts": dict(sorted(action_counts.items())),
        "action_rates": action_rates,
        "executed_action_counts": dict(sorted(executed_action_counts.items())),
        "executed_action_rates": executed_action_rates,
        "total_actions": total_actions,
        "invalid_action_count": invalid_count,
        "invalid_action_rate": invalid_rate,
        "policy_invalid_attempt_count": policy_invalid_attempt_count,
        "policy_invalid_attempt_rate": policy_invalid_attempt_rate,
        "action_remap_count": action_remap_count,
        "action_remap_rate": action_remap_rate,
        "avg_trade_count_per_episode": avg_trades,
        "max_trade_count_per_episode": max(trade_counts) if trade_counts else 0,
        "avg_invalid_actions_per_episode": _mean([float(v) for v in invalid_episode_counts]),
        "avg_policy_invalid_attempts_per_episode": _mean([float(v) for v in policy_invalid_episode_counts]),
        "avg_action_remaps_per_episode": _mean([float(v) for v in remap_episode_counts]),
        "avg_episode_net_return_pct": _mean(returns),
        "baseline_avg_episode_net_return_pct": _mean(baseline_returns),
        "baseline_delta_mean_pct": _mean(deltas),
        "worst_baseline_delta_episodes": [
            {
                "episode_id": row.get("episode_id"),
                "symbol": row.get("symbol"),
                "session": row.get("session"),
                "episode_return_pct": float(row.get("episode_return_pct") or 0.0),
                "baseline_net_return_pct": float(row.get("baseline_net_return_pct") or 0.0),
                "baseline_delta_pct": float(row.get("baseline_delta_pct") or 0.0),
                "trade_count": int(row.get("trade_count") or 0),
                "invalid_action_count": int(row.get("invalid_action_count") or 0),
                "policy_invalid_action_count": int(row.get("policy_invalid_action_count") or 0),
                "action_remap_count": int(row.get("action_remap_count") or 0),
            }
            for row in worst
        ],
        "likely_causes": likely_causes,
        "smallest_fix_selected": "fixed_entry_exit_only"
        if config.fixed_entry_exit_only
        else "constrained_action_wrapper"
        if config.constrain_invalid_actions or config.single_entry_exit
        else "overtrade_penalty",
        "smallest_fix_rationale": (
            "The ts_imb candidate is treated as the fixed entry decision, so the RL policy only chooses "
            "whether to keep holding or exit. This removes repeated entries and focuses learning on exit timing."
            if config.fixed_entry_exit_only
            else
            "Plain SB3 DQN does not natively consume action masks. A hold-on-invalid wrapper keeps the "
            "marketable-only action contract intact while preventing impossible fills from reaching the "
            "raw environment."
            if config.constrain_invalid_actions or config.single_entry_exit
            else "Plain SB3 DQN does not support action masks without a larger algorithm/wrapper change; "
            "reward clipping changes all reward magnitudes. The existing environment already supports "
            "a per-trade penalty, so exposing overtrade_penalty is the smallest reversible change."
        ),
        "applied_overtrade_penalty": float(config.overtrade_penalty),
    }


def run_orderbook_dqn_smoke(config: OrderbookDqnSmokeConfig) -> Dict[str, Any]:
    episodes, candidates = load_orderbook_ts_imb_episodes(config)
    needed = int(config.train_episodes) + int(config.eval_episodes)
    if len(episodes) < max(2, min(needed, int(config.min_eval_episodes) + 1)):
        raise ValueError(f"Not enough ts_imb orderbook episodes: {len(episodes)}")

    episodes = sorted(episodes, key=lambda ep: (ep.session, ep.symbol))
    train_count = min(int(config.train_episodes), max(1, len(episodes) - int(config.min_eval_episodes)))
    eval_count = min(int(config.eval_episodes), len(episodes) - train_count)
    train_set = episodes[:train_count]
    eval_set = episodes[train_count : train_count + eval_count]
    if len(eval_set) < int(config.min_eval_episodes):
        # Keep the split chronological but allow smaller explicit smoke configs.
        if int(config.eval_episodes) >= int(config.min_eval_episodes):
            raise ValueError(f"Need at least {config.min_eval_episodes} eval episodes, got {len(eval_set)}")

    output_dir = Path(config.output_dir)
    live_events_path = output_dir / "rl_live_events.jsonl"
    writer: Optional[RlLiveEventWriter] = None
    if config.write_artifacts and config.write_live_events:
        writer = RlLiveEventWriter(live_events_path, run_id=output_dir.name)
        writer.reset()

    model, train_elapsed, check_env = _train_dqn(train_set, config, writer)
    evaluation = _evaluate_dqn(model, eval_set, config, writer)
    model_returns = [float(row["episode_return_pct"]) for row in evaluation["episodes"]]
    baseline_returns = [float(row["baseline_net_return_pct"]) for row in evaluation["episodes"]]
    deltas = [float(row["baseline_delta_pct"]) for row in evaluation["episodes"]]
    model_mean = _mean(model_returns)
    baseline_mean = _mean(baseline_returns)
    delta_mean = _mean(deltas)
    trade_count = sum(int(row["trade_count"]) for row in evaluation["episodes"])
    diagnostics = _diagnose_policy_behavior(evaluation, config=config)
    verdict = (
        "GO_CANDIDATE"
        if len(eval_set) >= int(config.min_eval_episodes)
        and delta_mean > float(config.min_baseline_delta_pct)
        and model_mean > 0.0
        and trade_count > 0
        else "NO-GO"
    )

    summary = {
        "algorithm_count": 1,
        "algorithms": ["dqn"],
        "environment": "StomOrderbookRlEnv",
        "artifact_subtype": "orderbook_dqn_smoke",
        "check_env_passed": bool(check_env["passed"]),
        "training_timesteps": int(config.total_timesteps),
        "training_elapsed_seconds": float(train_elapsed),
        "train_episode_count": len(train_set),
        "eval_episode_count": len(eval_set),
        "candidate_count": len(candidates),
        "scanned_symbol_limit": int(config.max_scan_symbols),
        "feature_columns": check_env["feature_columns"],
        "best_algorithm_by_avg_episode_net": "dqn",
        "best_model": "orderbook_dqn_smoke",
        "avg_episode_net_return_pct": model_mean,
        "baseline_avg_episode_net_return_pct": baseline_mean,
        "baseline_delta_mean_pct": delta_mean,
        "trade_count": trade_count,
        "invalid_action_rate": diagnostics["invalid_action_rate"],
        "policy_invalid_attempt_rate": diagnostics["policy_invalid_attempt_rate"],
        "action_remap_rate": diagnostics["action_remap_rate"],
        "avg_trade_count_per_episode": diagnostics["avg_trade_count_per_episode"],
        "overtrade_penalty": float(config.overtrade_penalty),
        "constrain_invalid_actions": bool(config.constrain_invalid_actions),
        "single_entry_exit": bool(config.single_entry_exit),
        "fixed_entry_exit_only": bool(config.fixed_entry_exit_only),
        "passes_cost_gate": verdict == "GO_CANDIDATE",
        "verdict": verdict,
        "is_live_ready": False,
        "is_profit_model": False,
        "baseline_policy": "ts_imb_same_decision_tp5_sl1_time",
        "safety_note": "DQN smoke/OOS evaluator only; not live-ready and not a profit guarantee.",
    }
    model_row = {
        "algorithm": "dqn",
        "model": "orderbook_dqn_smoke",
        "policy": "stable_baselines3_dqn",
        "eval_split": "chronological_oos",
        "training_timesteps": int(config.total_timesteps),
        "training_elapsed_seconds": float(train_elapsed),
        "episode_count": len(eval_set),
        "trade_count": trade_count,
        "avg_episode_net_return_pct": model_mean,
        "baseline_avg_episode_net_return_pct": baseline_mean,
        "baseline_delta_mean_pct": delta_mean,
        "passes_cost_gate": verdict == "GO_CANDIDATE",
        "is_smoke": True,
        "eval_only": False,
        "cost_bps": float(config.cost_bps),
        "slippage_bps": float(config.slippage_bps),
        "overtrade_penalty": float(config.overtrade_penalty),
        "constrain_invalid_actions": bool(config.constrain_invalid_actions),
        "single_entry_exit": bool(config.single_entry_exit),
        "fixed_entry_exit_only": bool(config.fixed_entry_exit_only),
        "invalid_action_rate": diagnostics["invalid_action_rate"],
        "policy_invalid_attempt_rate": diagnostics["policy_invalid_attempt_rate"],
        "action_remap_rate": diagnostics["action_remap_rate"],
        "verdict": verdict,
    }
    payload: Dict[str, Any] = {
        "mode": "stom_orderbook_rl_sb3_smoke",
        "artifact_type": "sb3_smoke",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": asdict(config),
        "runtime": _torch_runtime(),
        "check_env": check_env,
        "summary": summary,
        "models": [model_row],
        "oos_verdict": {
            "verdict": verdict,
            "model_mean_pct": model_mean,
            "baseline_mean_pct": baseline_mean,
            "delta_mean_pct": delta_mean,
            "pass_criteria": {
                "eval_episode_count": len(eval_set),
                "min_eval_episodes": int(config.min_eval_episodes),
                "min_baseline_delta_pct": float(config.min_baseline_delta_pct),
                "requires_positive_model_mean": True,
                "requires_trade_count": True,
            },
        },
        "diagnostics": diagnostics,
        "artifacts": {
            "output_dir": str(output_dir),
            "summary_json": str(output_dir / "sb3_smoke_summary.json"),
            "summary_csv": str(output_dir / "sb3_smoke_summary.csv"),
            "episodes_csv": str(output_dir / "episodes.csv"),
            "actions_csv": str(output_dir / "actions.csv"),
            "baseline_csv": str(output_dir / "baseline.csv"),
            "verdict_json": str(output_dir / "orderbook_oos_verdict.json"),
            "diagnostics_json": str(output_dir / "orderbook_diagnostics.json"),
            "model_files": {"dqn": str(output_dir / "dqn_model.zip")},
            "live_events_jsonl": str(live_events_path),
            "live_summary_json": str(output_dir / "rl_live_summary.json"),
        },
    }

    if config.write_artifacts:
        output_dir.mkdir(parents=True, exist_ok=True)
        model.save(output_dir / "dqn_model.zip")
        if config.write_live_events:
            live_summary = summarize_live_event_file(live_events_path)
            payload["live_events"] = live_summary
            payload["summary"]["live_event_count"] = live_summary["event_count"]
            payload["summary"]["live_event_phases"] = live_summary["phases"]
            _write_json(output_dir / "rl_live_summary.json", live_summary)
        _write_json(output_dir / "sb3_smoke_summary.json", payload)
        _write_json(output_dir / "orderbook_oos_verdict.json", payload["oos_verdict"])
        _write_json(output_dir / "orderbook_diagnostics.json", diagnostics)
        _write_csv(
            output_dir / "sb3_smoke_summary.csv",
            [model_row],
            [
                "algorithm",
                "model",
                "policy",
                "eval_split",
                "training_timesteps",
                "training_elapsed_seconds",
                "episode_count",
                "trade_count",
                "avg_episode_net_return_pct",
                "baseline_avg_episode_net_return_pct",
                "baseline_delta_mean_pct",
                "passes_cost_gate",
                "is_smoke",
                "eval_only",
                "cost_bps",
                "slippage_bps",
                "overtrade_penalty",
                "constrain_invalid_actions",
                "single_entry_exit",
                "fixed_entry_exit_only",
                "invalid_action_rate",
                "policy_invalid_attempt_rate",
                "action_remap_rate",
                "verdict",
            ],
        )
        _write_csv(
            output_dir / "episodes.csv",
            evaluation["episodes"],
            [
                "model",
                "algorithm",
                "episode_id",
                "symbol",
                "session",
                "episode_return_pct",
                "baseline_net_return_pct",
                "baseline_delta_pct",
                "trade_count",
                "invalid_action_count",
                "policy_invalid_action_count",
                "action_remap_count",
                "steps",
            ],
        )
        _write_csv(
            output_dir / "actions.csv",
            evaluation["actions"],
            [
                "model",
                "algorithm",
                "episode_id",
                "symbol",
                "session",
                "step",
                "timestamp",
                "price",
                "action",
                "action_name",
                "policy_action",
                "policy_action_name",
                "executed_action",
                "executed_action_name",
                "semantic_action_name",
                "action_remapped",
                "invalid_action_prevented",
                "reward",
                "equity",
                "position",
                "invalid_action",
            ],
        )
        _write_csv(
            output_dir / "baseline.csv",
            evaluation["baseline"],
            [
                "episode_id",
                "symbol",
                "session",
                "baseline_policy",
                "baseline_net_return_pct",
                "baseline_exit_reason",
            ],
        )
    return payload


def _parse_args(argv: Optional[Sequence[str]] = None) -> OrderbookDqnSmokeConfig:
    parser = argparse.ArgumentParser(description="Run orderbook DQN smoke + OOS ts_imb baseline evaluator.")
    parser.add_argument("--db-path", "--db", default=str(Path("_database") / "stock_tick_back.db"))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-scan-symbols", type=int, default=300)
    parser.add_argument("--train-episodes", type=int, default=32)
    parser.add_argument("--eval-episodes", type=int, default=32)
    parser.add_argument("--lookback-window", type=int, default=30)
    parser.add_argument("--max-episode-steps", type=int, default=120)
    parser.add_argument("--total-timesteps", type=int, default=512)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--cost-bps", type=float, default=23.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--overtrade-penalty", type=float, default=0.0)
    parser.add_argument("--constrain-invalid-actions", action="store_true")
    parser.add_argument("--single-entry-exit", action="store_true")
    parser.add_argument("--fixed-entry-exit-only", action="store_true")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--min-eval-episodes", type=int, default=10)
    parser.add_argument("--min-baseline-delta-pct", type=float, default=0.0)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--no-live-events", action="store_true")
    args = parser.parse_args(argv)
    return OrderbookDqnSmokeConfig(
        db_path=args.db_path,
        output_dir=args.output_dir,
        max_scan_symbols=args.max_scan_symbols,
        train_episodes=args.train_episodes,
        eval_episodes=args.eval_episodes,
        lookback_window=args.lookback_window,
        max_episode_steps=args.max_episode_steps,
        total_timesteps=args.total_timesteps,
        seed=args.seed,
        cost_bps=args.cost_bps,
        slippage_bps=args.slippage_bps,
        overtrade_penalty=args.overtrade_penalty,
        constrain_invalid_actions=bool(args.constrain_invalid_actions),
        single_entry_exit=bool(args.single_entry_exit),
        fixed_entry_exit_only=bool(args.fixed_entry_exit_only),
        device=args.device,
        min_eval_episodes=args.min_eval_episodes,
        min_baseline_delta_pct=args.min_baseline_delta_pct,
        write_artifacts=not args.no_write,
        write_live_events=not args.no_live_events,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    payload = run_orderbook_dqn_smoke(_parse_args(argv))
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    if payload.get("artifacts"):
        print(f"wrote -> {payload['artifacts']['summary_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
