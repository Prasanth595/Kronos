"""Tiny SB3 training/evaluation for opening candidate artifacts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd  # noqa: PANDAS_OK - STOM tick/orderbook episodes are pandas frames

from .opening_30m_rl_feature_mask import FeatureMaskEnv, feature_mask_details
from .opening_30m_rl_candidates import CandidateConfig, train_candidate_artifacts
from .opening_30m_rl_realdata import JsonValue
from .orderbook_rl_env import StomOrderbookRlEnvConfig
from .orderbook_sb3_adapter import OrderbookEpisode, StomOrderbookGymEnv


def train_realdata_candidates(
    configs: Sequence[CandidateConfig],
    *,
    frames: Sequence[pd.DataFrame],
    split_manifest: Mapping[str, JsonValue],
    output_dir: Path,
    tiny_train: bool,
) -> dict[str, JsonValue]:
    """Train tiny SB3 candidates when available; otherwise record truthful skip metadata."""

    sb3_available = importlib.util.find_spec("stable_baselines3") is not None
    if not tiny_train or not sb3_available or not frames:
        return train_candidate_artifacts(configs, sb3_available=sb3_available)
    rows = [_train_one_candidate(config, frames, split_manifest, output_dir) for config in configs]
    return {
        "artifact_type": "opening_30m_candidate_training",
        "selection_split": "validation",
        "oos_is_final_only": True,
        "candidates": rows,
    }


def _train_one_candidate(
    config: CandidateConfig,
    frames: Sequence[pd.DataFrame],
    split_manifest: Mapping[str, JsonValue],
    output_dir: Path,
) -> dict[str, JsonValue]:
    try:
        from stable_baselines3 import DQN, PPO

        train_episodes = _episodes_for_split(frames, split_manifest, "train")
        validation_episodes = _episodes_for_split(frames, split_manifest, "validation")
        oos_episodes = _episodes_for_split(frames, split_manifest, "oos")
        model_cls = DQN if config.algorithm.value == "dqn" else PPO
        model = model_cls("MlpPolicy", _make_env(train_episodes, config), seed=int(config.seed), device="cpu", verbose=0, **_model_kwargs(config))
        model.learn(total_timesteps=int(config.total_timesteps), progress_bar=False)
        model_path = output_dir / "models" / f"{config.candidate_id}.zip"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model.save(model_path)
        validation = _evaluate(model, validation_episodes, config)
        oos = _evaluate(model, oos_episodes, config)
        logs = _write_eval_logs(output_dir, config, validation, oos)
        return _trained_row(config, model_path, validation, oos, logs)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:  # pragma: no cover - local dependency/data variance
        return _failed_row(config, str(exc))


def _model_kwargs(config: CandidateConfig) -> dict[str, object]:
    steps = max(2, min(8, int(config.total_timesteps)))
    if config.algorithm.value == "ppo":
        return {"n_steps": steps, "batch_size": steps, "gamma": 0.95}
    return {
        "learning_starts": 1,
        "buffer_size": max(128, int(config.total_timesteps) * 2),
        "batch_size": steps,
        "train_freq": 1,
        "gradient_steps": 1,
        "gamma": 0.95,
    }


def _evaluate(model: Any, episodes: Sequence[OrderbookEpisode], config: CandidateConfig) -> dict[str, JsonValue]:
    cumulative = 0.0
    min_cumulative = 0.0
    trade_count = 0
    rows = []
    for index, episode in enumerate(episodes):
        env = _make_env([episode], config)
        observation, info = env.reset(seed=int(config.seed) + index)
        total_reward = 0.0
        terminated = truncated = False
        last_info = dict(info)
        while not (terminated or truncated):
            action, _ = model.predict(observation, deterministic=True)
            observation, reward, terminated, truncated, last_info = env.step(action)
            total_reward += float(reward)
        cumulative += total_reward * 100.0
        min_cumulative = min(min_cumulative, cumulative)
        trade_count += int(last_info.get("trade_count", 0))
        rows.append({"episode_id": episode.episode_id, "net_return_pct": total_reward * 100.0})
    return {"net_return_pct": cumulative, "trade_count": trade_count, "max_drawdown_pct": min_cumulative, "rows": rows}


def _episodes_for_split(frames: Sequence[pd.DataFrame], split_manifest: Mapping[str, JsonValue], split: str) -> list[OrderbookEpisode]:
    sessions = set(_split_sessions(split_manifest, split))
    episodes = []
    for frame in frames:
        if frame.empty or str(frame["session"].iloc[0]) not in sessions:
            continue
        symbol = str(frame["symbol"].iloc[0])
        session = str(frame["session"].iloc[0])
        episodes.append(OrderbookEpisode(f"{symbol}_{session}", symbol, session, frame))
    if not episodes:
        raise ValueError(f"{split} split has no matching real-data frames")
    return episodes


def _split_sessions(split_manifest: Mapping[str, JsonValue], split: str) -> list[str]:
    raw = split_manifest.get("split_sessions", {})
    if not isinstance(raw, Mapping):
        return []
    sessions = raw.get(split, [])
    return [str(session) for session in sessions] if isinstance(sessions, list) else []


def _make_env(episodes: Sequence[OrderbookEpisode], config: CandidateConfig) -> StomOrderbookGymEnv:
    env = StomOrderbookGymEnv(
        episodes,
        StomOrderbookRlEnvConfig(lookback_window=3, cost_bps=float(config.cost_bps), max_episode_steps=5, seed=int(config.seed)),
        fixed_entry_exit_only=True,
        constrain_invalid_actions=True,
    )
    return FeatureMaskEnv(env, config.feature_set_id)


def _write_eval_logs(
    output_dir: Path,
    config: CandidateConfig,
    validation: Mapping[str, JsonValue],
    oos: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    log_dir = output_dir / "eval_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    validation_path = log_dir / f"{config.candidate_id}_validation.json"
    oos_path = log_dir / f"{config.candidate_id}_oos.json"
    validation_path.write_text(json.dumps(validation, ensure_ascii=True, indent=2), encoding="utf-8")
    oos_path.write_text(json.dumps(oos, ensure_ascii=True, indent=2), encoding="utf-8")
    return {"validation_eval_json": str(validation_path), "oos_eval_json": str(oos_path)}


def _trained_row(
    config: CandidateConfig,
    model_path: Path,
    validation: Mapping[str, JsonValue],
    oos: Mapping[str, JsonValue],
    logs: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    return {
        "candidate_id": config.candidate_id,
        "algorithm": config.algorithm.value,
        "seed": int(config.seed),
        "split_hash": config.split_hash,
        "feature_set_id": config.feature_set_id,
        "total_timesteps": int(config.total_timesteps),
        "status": "trained" if model_path.is_file() else "not_trained",
        "model_path": str(model_path) if model_path.is_file() else "",
        "validation_net_return_pct": validation["net_return_pct"],
        "oos_net_return_pct": oos["net_return_pct"],
        "oos_trade_count": oos["trade_count"],
        "oos_max_drawdown_pct": oos["max_drawdown_pct"],
        "monitor_log_path": logs["validation_eval_json"],
        "eval_log_path": logs["oos_eval_json"],
        "selected_by": "validation",
    }


def _failed_row(config: CandidateConfig, reason: str) -> dict[str, JsonValue]:
    return {
        "candidate_id": config.candidate_id,
        "algorithm": config.algorithm.value,
        "seed": int(config.seed),
        "split_hash": config.split_hash,
        "feature_set_id": config.feature_set_id,
        "total_timesteps": int(config.total_timesteps),
        "status": "training_failed",
        "model_path": "",
        "validation_net_return_pct": 0.0,
        "oos_net_return_pct": None,
        "skip_reason": reason[:500],
        "selected_by": "validation",
    }
