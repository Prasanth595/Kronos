"""Opening orderbook environment compliance checks."""

from __future__ import annotations

import importlib
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Sequence

from .orderbook_rl_env import ACTION_NAMES, StomOrderbookRlEnvConfig
from .orderbook_sb3_adapter import OrderbookEpisode, StomOrderbookGymEnv


@dataclass(frozen=True, slots=True)
class OpeningEnvContractError(ValueError):
    """Raised when opening env contract evidence cannot be built."""

    reason: str

    def __str__(self) -> str:
        return self.reason


def _orderbook_episodes(frames: Sequence[Any]) -> list[OrderbookEpisode]:
    episodes: list[OrderbookEpisode] = []
    for frame in frames:
        if frame.empty:
            continue
        symbol = str(frame["symbol"].iloc[0])
        session = str(frame["session"].iloc[0])
        episodes.append(
            OrderbookEpisode(
                episode_id=f"{symbol}_{session}",
                symbol=symbol,
                session=session,
                frame=frame,
            )
        )
    if not episodes:
        raise OpeningEnvContractError("opening env contract requires at least one non-empty frame")
    return episodes


def _probe_sb3_check_env_import() -> str:
    try:
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "from stable_baselines3.common.env_checker import check_env; print(check_env.__name__)",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired as exc:
        return f"SB3 check_env import probe timed out after {exc.timeout} seconds"
    if probe.returncode != 0 or probe.stderr.strip():
        return (probe.stderr or probe.stdout).strip()
    return ""


def _run_sb3_check(env: StomOrderbookGymEnv) -> dict[str, bool | str]:
    import_message = _probe_sb3_check_env_import()
    if import_message:
        return {
            "check_env_passed": False,
            "check_env_status": "skipped_sb3_unavailable",
            "check_env_message": import_message,
        }
    try:
        env_checker = importlib.import_module("stable_baselines3.common.env_checker")
    except (ImportError, OSError) as exc:
        return {
            "check_env_passed": False,
            "check_env_status": "skipped_sb3_unavailable",
            "check_env_message": str(exc),
        }
    check_env = getattr(env_checker, "check_env")
    try:
        check_env(env, warn=False)
    except (AssertionError, ValueError, TypeError) as exc:
        return {
            "check_env_passed": False,
            "check_env_status": "failed",
            "check_env_message": str(exc),
        }
    return {
        "check_env_passed": True,
        "check_env_status": "passed",
        "check_env_message": "",
    }


def build_opening_env_contract_stage(
    frames: Sequence[Any],
    *,
    fixed_entry_exit_only: bool = False,
    constrain_invalid_actions: bool = True,
) -> dict[str, Any]:
    """Validate opening orderbook env contracts on deterministic frames."""

    episodes = _orderbook_episodes(frames)
    config = StomOrderbookRlEnvConfig(lookback_window=3, cost_bps=0.0, max_episode_steps=8)
    env = StomOrderbookGymEnv(
        episodes,
        config,
        constrain_invalid_actions=constrain_invalid_actions,
        fixed_entry_exit_only=fixed_entry_exit_only,
    )
    observation, info = env.reset(seed=100)
    action_space = (
        {"0": "hold", "1": "exit"}
        if fixed_entry_exit_only
        else {str(key): value for key, value in ACTION_NAMES.items()}
    )
    sb3_check = _run_sb3_check(
        StomOrderbookGymEnv(
            episodes,
            config,
            constrain_invalid_actions=constrain_invalid_actions,
            fixed_entry_exit_only=fixed_entry_exit_only,
        )
    )
    result: dict[str, Any] = {
        "stage": "readiness_env",
        "status": "complete",
        "evidence": "env_contract",
        "environment": "StomOrderbookGymEnv",
        "raw_environment": "StomOrderbookRlEnv",
        "observation_shape": list(observation.shape),
        "observation_space_shape": list(env.observation_space.shape),
        "action_space": action_space,
        "action_space_n": int(env.action_space.n),
        "constraint_mode": str(info.get("constraint_mode", "hold_on_invalid" if constrain_invalid_actions else "none")),
        "fixed_entry_exit_only": bool(fixed_entry_exit_only),
        "constrain_invalid_actions": bool(constrain_invalid_actions),
        "episode_count": len(episodes),
    }
    result.update(sb3_check)
    return result
