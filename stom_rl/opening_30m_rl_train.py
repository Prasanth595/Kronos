"""Tiny DQN training stage for the opening 30-minute RL workflow."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import pandas as pd  # noqa: PANDAS_OK - STOM opening fixtures are pandas frames

from .orderbook_rl_env import StomOrderbookRlEnvConfig
from .orderbook_sb3_adapter import OrderbookEpisode, StomOrderbookGymEnv


SUMMARY_JSON = "opening_training_summary.json"
MODEL_ZIP = "dqn_model.zip"


@dataclass(frozen=True, slots=True)
class OpeningTrainingConfig:
    """Configuration for the fixture-safe opening DQN training stage."""

    output_dir: Path | str
    total_timesteps: int = 16
    seed: int = 100
    cost_bps: float = 23.0
    lookback_window: int = 3
    max_episode_steps: int = 5
    fixed_entry_exit_only: bool = True
    constrain_invalid_actions: bool = True
    device: str = "cpu"


@dataclass(frozen=True, slots=True)
class OpeningTrainingError(ValueError):
    """Raised when the opening training stage contract is violated."""

    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class OpeningTrainingUnavailable(Exception):
    """Raised when local SB3/Torch cannot run the DQN stage safely."""

    reason: str

    def __str__(self) -> str:
        return self.reason


def _episode_id(frame: pd.DataFrame) -> str:
    return f"{frame['symbol'].iloc[0]}_{frame['session'].iloc[0]}"


def _episodes_by_id(frames: Sequence[pd.DataFrame]) -> dict[str, OrderbookEpisode]:
    episodes: dict[str, OrderbookEpisode] = {}
    for frame in frames:
        if frame.empty:
            continue
        episode_id = _episode_id(frame)
        episodes[episode_id] = OrderbookEpisode(
            episode_id=episode_id,
            symbol=str(frame["symbol"].iloc[0]),
            session=str(frame["session"].iloc[0]),
            frame=frame,
        )
    if not episodes:
        raise OpeningTrainingError("opening training requires at least one episode")
    return episodes


def _select_episodes(
    episodes: dict[str, OrderbookEpisode],
    ids: Sequence[str],
    split_name: str,
) -> list[OrderbookEpisode]:
    selected: list[OrderbookEpisode] = []
    for episode_id in ids:
        if episode_id not in episodes:
            raise OpeningTrainingError(f"unknown {split_name} episode_id: {episode_id}")
        selected.append(episodes[episode_id])
    if not selected:
        raise OpeningTrainingError(f"{split_name} episode_ids must not be empty")
    return selected


def _assert_no_overlap(train_episode_ids: Sequence[str], eval_episode_ids: Sequence[str]) -> None:
    overlap = sorted(set(train_episode_ids) & set(eval_episode_ids))
    if overlap:
        raise OpeningTrainingError(f"train/eval episode overlap: {overlap}")


def _env_config(config: OpeningTrainingConfig) -> StomOrderbookRlEnvConfig:
    return StomOrderbookRlEnvConfig(
        lookback_window=int(config.lookback_window),
        cost_bps=float(config.cost_bps),
        max_episode_steps=int(config.max_episode_steps),
        seed=int(config.seed),
    )


def _make_env(episodes: Sequence[OrderbookEpisode], config: OpeningTrainingConfig) -> StomOrderbookGymEnv:
    return StomOrderbookGymEnv(
        episodes,
        _env_config(config),
        fixed_entry_exit_only=bool(config.fixed_entry_exit_only),
        constrain_invalid_actions=bool(config.constrain_invalid_actions),
    )


def _probe_sb3_dqn_import() -> str:
    try:
        probe = subprocess.run(
            [sys.executable, "-c", "from stable_baselines3 import DQN; print(DQN.__name__)"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired as exc:
        return f"SB3 DQN import probe timed out after {exc.timeout} seconds"
    output = (probe.stdout + probe.stderr).strip()
    if probe.returncode != 0:
        return output or f"SB3 DQN import probe failed with exit code {probe.returncode}"
    return "" if output == "DQN" else output


def _train_model(train_episodes: Sequence[OrderbookEpisode], config: OpeningTrainingConfig):
    import_message = _probe_sb3_dqn_import()
    if import_message:
        raise OpeningTrainingUnavailable(import_message)
    try:
        from stable_baselines3 import DQN
    except (ImportError, OSError) as exc:
        raise OpeningTrainingUnavailable(str(exc)) from exc

    env = _make_env(train_episodes, config)
    batch_size = max(2, min(8, int(config.total_timesteps)))
    model = DQN(
        "MlpPolicy",
        env,
        seed=int(config.seed),
        device=str(config.device),
        verbose=0,
        learning_starts=1,
        buffer_size=max(128, int(config.total_timesteps) * 2),
        batch_size=batch_size,
        train_freq=1,
        gradient_steps=1,
        gamma=0.95,
    )
    try:
        model.learn(total_timesteps=int(config.total_timesteps), progress_bar=False)
    except OSError as exc:
        raise OpeningTrainingUnavailable(str(exc)) from exc
    return model


def _evaluate_model(model, eval_episodes: Sequence[OrderbookEpisode], config: OpeningTrainingConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, episode in enumerate(eval_episodes):
        env = _make_env([episode], config)
        observation, info = env.reset(seed=int(config.seed) + index)
        total_reward = 0.0
        steps = 0
        terminated = False
        truncated = False
        last_info = dict(info)
        while not (terminated or truncated) and steps < int(config.max_episode_steps):
            action, _ = model.predict(observation, deterministic=True)
            observation, reward, terminated, truncated, last_info = env.step(action)
            total_reward += float(reward)
            steps += 1
        rows.append(
            {
                "episode_id": episode.episode_id,
                "symbol": episode.symbol,
                "session": episode.session,
                "reward": total_reward,
                "steps": steps,
                "trade_count": int(last_info.get("trade_count", 0)),
            }
        )
    return rows


def run_opening_training_stage(
    frames: Sequence[pd.DataFrame],
    *,
    train_episode_ids: Sequence[str],
    eval_episode_ids: Sequence[str],
    config: OpeningTrainingConfig,
) -> dict[str, Any]:
    """Run a tiny fixed-entry DQN stage and write metadata artifacts."""

    _assert_no_overlap(train_episode_ids, eval_episode_ids)
    episodes = _episodes_by_id(frames)
    train_episodes = _select_episodes(episodes, train_episode_ids, "train")
    eval_episodes = _select_episodes(episodes, eval_episode_ids, "eval")
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / SUMMARY_JSON
    payload: dict[str, Any] = {
        "artifact_type": "opening_30m_training_stage",
        "mode": "opening_30m_dqn_training",
        "status": "passed",
        "algorithm": "DQN",
        "seed": int(config.seed),
        "total_timesteps": int(config.total_timesteps),
        "device": str(config.device),
        "fixed_entry_exit_only": bool(config.fixed_entry_exit_only),
        "constrain_invalid_actions": bool(config.constrain_invalid_actions),
        "cost_bps": float(config.cost_bps),
        "train_episode_count": len(train_episodes),
        "eval_episode_count": len(eval_episodes),
        "train_episode_ids": list(train_episode_ids),
        "eval_episode_ids": list(eval_episode_ids),
        "evaluation": [],
        "model_files": {},
        "artifacts": {"summary_json": str(summary_path)},
        "safety_note": "DQN opening training fixture only; not live-ready and not a profit model.",
        "strategy_context": {
            "line": "opening_rl_experiment",
            "label": "RL EXPERIMENT",
            "is_reinforcement_learning": True,
            "is_live_ready": False,
            "is_profit_model": False,
        },
    }
    try:
        model = _train_model(train_episodes, config)
        eval_rows = _evaluate_model(model, eval_episodes, config)
    except OpeningTrainingUnavailable as exc:
        payload["status"] = "skipped_sb3_unavailable"
        payload["sb3_status"] = "skipped_sb3_unavailable"
        payload["skip_reason"] = str(exc)
    else:
        model_path = output_dir / MODEL_ZIP
        model.save(model_path)
        payload["evaluation"] = eval_rows
        payload["model_files"] = {"dqn": str(model_path)}
        payload["artifacts"] = {"summary_json": str(summary_path), "model_zip": str(model_path)}
        payload["sb3_status"] = "passed"
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
