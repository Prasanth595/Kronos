"""Gymnasium/Stable-Baselines3 adapter for the STOM portfolio env.

:class:`PortfolioEnv` stays dependency-light (it uses the in-house
``BoxSpace``/``DiscreteSpace`` and already returns the Gymnasium 5-tuple from
``step``).  This wrapper owns the real Gymnasium spaces/inheritance that
Stable-Baselines3 requires, while delegating every trading decision to the base
env.  It is a *faithful passthrough*: no extra observation normalization is
applied beyond what ``PortfolioEnv._observation`` already does (price/100k,
cash & NAV / initial_cash, ``nan_to_num`` clipping).

It also exposes ``action_masks()`` (plural) wrapping ``PortfolioEnv.action_mask``
(singular) so the gated sb3-contrib MaskablePPO path in Stage B can read the
per-step action mask.  Plain PPO/DQN ignore it.  ``sb3-contrib`` is intentionally
NOT a dependency here.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .portfolio_env import PortfolioEnv, PortfolioEnvConfig


class PortfolioSb3GymEnv(gym.Env):
    """Thin Gymnasium wrapper around :class:`PortfolioEnv`.

    The wrapped env exposes the SAME logical spaces as the underlying env: a
    ``Discrete(1 + top_k + max_positions)`` action space and a ``Box`` of the
    underlying observation width.  ``reset``/``step`` are pure passthroughs that
    return the Gymnasium 5-tuple ``(obs, reward, terminated, truncated, info)``.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        config: Optional[PortfolioEnvConfig] = None,
        *,
        candidates: Optional[Any] = None,
        **overrides: Any,
    ) -> None:
        if config is not None and overrides:
            raise ValueError("Pass either config or keyword overrides, not both.")
        self.raw_env = PortfolioEnv(config, candidates=candidates, **overrides)
        self.action_space = spaces.Discrete(self.raw_env.action_space.n)
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=self.raw_env.observation_space.shape,
            dtype=np.float32,
        )

    @property
    def config(self) -> PortfolioEnvConfig:
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
        return (
            np.asarray(observation, dtype=np.float32),
            float(reward),
            bool(terminated),
            bool(truncated),
            dict(info),
        )

    def action_masks(self) -> np.ndarray:
        """Per-step action mask for sb3-contrib MaskablePPO (Stage B, gated).

        Wraps the underlying singular ``action_mask()`` and returns an int8
        array of length ``action_space.n``.  Plain PPO/DQN ignore this method.
        """

        return np.asarray(self.raw_env.action_mask(), dtype=np.int8)

    def render(self) -> None:
        return None

    def close(self) -> None:
        return None


def make_portfolio_sb3_env(
    candidate_path: Optional[str] = None,
    *,
    candidates: Optional[Any] = None,
    top_k_candidates: int = 3,
    max_positions: int = 2,
    initial_cash: float = 1_000_000.0,
    buy_fraction: float = 0.25,
    cost_bps: float = 25.0,
    slippage_bps: float = 0.0,
    invalid_action_penalty: float = 0.001,
    turnover_penalty_lambda: float = 0.0,
    seed: int = 100,
    feature_columns: Optional[Tuple[str, ...]] = None,
) -> PortfolioSb3GymEnv:
    """Create a Gymnasium-compatible STOM portfolio env for SB3 training/eval.

    Mirrors :func:`stom_rl.sb3_adapter.make_sb3_env`.  Pass an in-memory
    ``candidates`` frame (e.g. ``synthetic_candidates()``) or a ``candidate_path``
    CSV; the factory threads the remaining knobs through ``PortfolioEnvConfig``.
    """

    return PortfolioSb3GymEnv(
        PortfolioEnvConfig(
            candidate_path=candidate_path,
            top_k_candidates=top_k_candidates,
            max_positions=max_positions,
            initial_cash=initial_cash,
            buy_fraction=buy_fraction,
            cost_bps=cost_bps,
            slippage_bps=slippage_bps,
            invalid_action_penalty=invalid_action_penalty,
            turnover_penalty_lambda=turnover_penalty_lambda,
            seed=seed,
            feature_columns=feature_columns,
        ),
        candidates=candidates,
    )


__all__ = ["PortfolioSb3GymEnv", "make_portfolio_sb3_env"]
