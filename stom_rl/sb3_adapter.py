"""Gymnasium/Stable-Baselines3 adapter for the STOM tick trading env."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .trading_env import StomTickTradingEnv, StomTickTradingEnvConfig


class StomTickTradingGymEnv(gym.Env):
    """Thin Gymnasium wrapper around :class:`StomTickTradingEnv`.

    ``StomTickTradingEnv`` deliberately stayed dependency-light for the first
    RL pages.  This wrapper owns the real Gymnasium spaces/inheritance needed by
    Stable-Baselines3 while delegating all trading semantics to the base env.
    """

    metadata = {"render_modes": []}

    def __init__(self, config: Optional[StomTickTradingEnvConfig] = None, **overrides: Any):
        if config is not None and overrides:
            raise ValueError("Pass either config or keyword overrides, not both.")
        self.raw_env = StomTickTradingEnv(config, **overrides)
        self.action_space = spaces.Discrete(self.raw_env.action_space.n)
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=self.raw_env.observation_space.shape,
            dtype=np.float32,
        )

    @property
    def config(self) -> StomTickTradingEnvConfig:
        return self.raw_env.config

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        observation, info = self.raw_env.reset(seed=seed, options=options)
        return np.asarray(observation, dtype=np.float32), dict(info)

    def step(self, action: Any) -> Tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        action_int = int(np.asarray(action).item())
        observation, reward, terminated, truncated, info = self.raw_env.step(action_int)
        return np.asarray(observation, dtype=np.float32), float(reward), bool(terminated), bool(truncated), dict(info)

    def render(self) -> None:
        return None

    def close(self) -> None:
        return None


def make_sb3_env(
    manifest_path: str,
    *,
    split: str = "train",
    seed: int = 100,
    episode_index: Optional[int] = None,
    lookback_window: int = 300,
    reward_horizon_seconds: int = 300,
    cost_bps: float = 25.0,
    slippage_bps: float = 0.0,
    reward_mode: str = "horizon",
) -> StomTickTradingGymEnv:
    """Create a Gymnasium-compatible STOM env for SB3 training/evaluation."""

    return StomTickTradingGymEnv(
        StomTickTradingEnvConfig(
            manifest_path=manifest_path,
            split=split,
            seed=seed,
            episode_index=episode_index,
            lookback_window=lookback_window,
            reward_horizon_seconds=reward_horizon_seconds,
            cost_bps=cost_bps,
            slippage_bps=slippage_bps,
            reward_mode=reward_mode,
        )
    )


__all__ = ["StomTickTradingGymEnv", "make_sb3_env"]
