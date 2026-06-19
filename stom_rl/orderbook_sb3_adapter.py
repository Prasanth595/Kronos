"""Gymnasium adapter for the marketable-only STOM orderbook RL environment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from .orderbook_rl_env import (
    ACTION_HOLD,
    ACTION_MARKET_BUY,
    ACTION_MARKET_EXIT,
    ACTION_NAMES,
    StomOrderbookRlEnv,
    StomOrderbookRlEnvConfig,
)


@dataclass(frozen=True)
class OrderbookEpisode:
    """One pre-extracted tick+orderbook episode."""

    episode_id: str
    symbol: str
    session: str
    frame: pd.DataFrame


class StomOrderbookGymEnv(gym.Env):
    """Gymnasium wrapper over one or more ``StomOrderbookRlEnv`` episodes."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        episodes: Sequence[OrderbookEpisode],
        config: Optional[StomOrderbookRlEnvConfig] = None,
        *,
        constrain_invalid_actions: bool = False,
        single_entry_exit: bool = False,
        fixed_entry_exit_only: bool = False,
        **overrides: Any,
    ) -> None:
        if config is not None and overrides:
            raise ValueError("Pass either config or keyword overrides, not both.")
        if not episodes:
            raise ValueError("episodes must not be empty")
        self.episodes = list(episodes)
        self.config = config or StomOrderbookRlEnvConfig(**overrides)
        self.constrain_invalid_actions = bool(constrain_invalid_actions)
        self.single_entry_exit = bool(single_entry_exit)
        self.fixed_entry_exit_only = bool(fixed_entry_exit_only)
        self._rng = np.random.default_rng(self.config.seed)
        self._next_episode = 0
        self._single_entry_entered = False
        self._pending_fixed_entry_reward = 0.0
        self._pending_fixed_entry_info: dict[str, Any] = {}
        self.current_episode: OrderbookEpisode = self.episodes[0]
        self.raw_env = self._make_raw_env(self.current_episode)
        self.action_space = spaces.Discrete(2 if self.fixed_entry_exit_only else self.raw_env.action_space.n)
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=self.raw_env.observation_space.shape,
            dtype=np.float32,
        )

    def _make_raw_env(self, episode: OrderbookEpisode) -> StomOrderbookRlEnv:
        return StomOrderbookRlEnv(self.config, frame=episode.frame)

    def _select_episode(self, options: Optional[Mapping[str, Any]]) -> OrderbookEpisode:
        options = dict(options or {})
        if "episode_index" in options:
            return self.episodes[int(options["episode_index"]) % len(self.episodes)]
        if "episode_id" in options:
            episode_id = str(options["episode_id"])
            for episode in self.episodes:
                if episode.episode_id == episode_id:
                    return episode
            raise ValueError(f"Unknown orderbook episode_id: {episode_id}")
        if len(self.episodes) == 1:
            return self.episodes[0]
        # Cycle deterministically instead of pure random so tiny smoke runs see
        # more than one episode while still being reproducible.
        episode = self.episodes[self._next_episode % len(self.episodes)]
        self._next_episode += 1
        return episode

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self.current_episode = self._select_episode(options)
        self.raw_env = self._make_raw_env(self.current_episode)
        self._single_entry_entered = False
        self._pending_fixed_entry_reward = 0.0
        self._pending_fixed_entry_info = {}
        observation, info = self.raw_env.reset(seed=seed, options=options)
        if self.fixed_entry_exit_only:
            observation, entry_reward, terminated, truncated, entry_info = self.raw_env.step(ACTION_MARKET_BUY)
            self._single_entry_entered = True
            self._pending_fixed_entry_reward = float(entry_reward)
            self._pending_fixed_entry_info = dict(entry_info)
            info = dict(entry_info)
            info.update(
                {
                    "fixed_entry": True,
                    "fixed_entry_reward": float(entry_reward),
                    "fixed_entry_terminated": bool(terminated),
                    "fixed_entry_truncated": bool(truncated),
                    "constraint_mode": "fixed_entry_exit_only",
                    "policy_action_space": {0: "hold", 1: "exit"},
                }
            )
        return np.asarray(observation, dtype=np.float32), self._add_episode_info(info)

    def step(self, action: Any) -> Tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        policy_action = int(np.asarray(action).item())
        if self.fixed_entry_exit_only:
            return self._step_fixed_entry_exit_only(policy_action)
        if self.single_entry_exit:
            return self._step_single_entry_exit(policy_action)
        executed_action = self._constrain_action(policy_action)
        observation, reward, terminated, truncated, info = self.raw_env.step(executed_action)
        action_remapped = executed_action != policy_action
        info = dict(info)
        info.update(
            {
                "policy_action": policy_action,
                "policy_action_name": ACTION_NAMES.get(policy_action, str(policy_action)),
                "executed_action": executed_action,
                "executed_action_name": ACTION_NAMES.get(executed_action, str(executed_action)),
                "action_remapped": action_remapped,
                "invalid_action_prevented": action_remapped,
                "constraint_mode": "hold_on_invalid" if self.constrain_invalid_actions else "none",
            }
        )
        return (
            np.asarray(observation, dtype=np.float32),
            float(reward),
            bool(terminated),
            bool(truncated),
            self._add_episode_info(info),
        )

    def _step_fixed_entry_exit_only(self, policy_action: int) -> Tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        if policy_action not in {0, 1}:
            raise ValueError(f"Invalid fixed-entry action {policy_action!r}; expected 0=hold or 1=exit.")
        if self.raw_env.position:
            executed_action = ACTION_HOLD if policy_action == 0 else ACTION_MARKET_EXIT
            semantic_action_name = "hold" if policy_action == 0 else "exit"
        else:
            executed_action = ACTION_HOLD
            semantic_action_name = "closed"
        observation, reward, terminated, truncated, info = self.raw_env.step(executed_action)
        pending_entry_reward = float(self._pending_fixed_entry_reward)
        if pending_entry_reward:
            reward = float(reward) + pending_entry_reward
            self._pending_fixed_entry_reward = 0.0
        forced_terminal = bool(policy_action == 1 or not self.raw_env.position)
        terminated = bool(terminated or forced_terminal)
        info = dict(info)
        info.update(
            {
                "policy_action": int(policy_action),
                "policy_action_name": "hold" if policy_action == 0 else "exit",
                "executed_action": int(executed_action),
                "executed_action_name": ACTION_NAMES.get(executed_action, str(executed_action)),
                "semantic_action_name": semantic_action_name,
                "action_remapped": False,
                "invalid_action_prevented": False,
                "constraint_mode": "fixed_entry_exit_only",
                "fixed_entry": True,
                "fixed_entry_reward": pending_entry_reward,
                "episode_closed_by_policy": bool(forced_terminal),
            }
        )
        return (
            np.asarray(observation, dtype=np.float32),
            float(reward),
            bool(terminated),
            bool(truncated),
            self._add_episode_info(info),
        )

    def _step_single_entry_exit(self, policy_action: int) -> Tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        executed_action = int(policy_action)
        semantic_action_name = ACTION_NAMES.get(policy_action, str(policy_action))
        action_remapped = False
        forced_terminal = False

        if not self._single_entry_entered:
            if policy_action == ACTION_MARKET_BUY:
                executed_action = ACTION_MARKET_BUY
                semantic_action_name = "enter"
                self._single_entry_entered = True
            elif policy_action == ACTION_HOLD:
                executed_action = ACTION_HOLD
                semantic_action_name = "skip"
                forced_terminal = True
            else:
                executed_action = ACTION_HOLD
                semantic_action_name = "skip_invalid_exit"
                action_remapped = True
                forced_terminal = True
        elif self.raw_env.position:
            if policy_action == ACTION_MARKET_EXIT:
                executed_action = ACTION_MARKET_EXIT
                semantic_action_name = "exit"
                forced_terminal = True
            elif policy_action == ACTION_HOLD:
                executed_action = ACTION_HOLD
                semantic_action_name = "hold"
            else:
                executed_action = ACTION_HOLD
                semantic_action_name = "hold_invalid_enter"
                action_remapped = True
        else:
            executed_action = ACTION_HOLD
            semantic_action_name = "closed"
            action_remapped = policy_action != ACTION_HOLD
            forced_terminal = True

        observation, reward, terminated, truncated, info = self.raw_env.step(executed_action)
        terminated = bool(terminated or forced_terminal)
        info = dict(info)
        info.update(
            {
                "policy_action": int(policy_action),
                "policy_action_name": ACTION_NAMES.get(policy_action, str(policy_action)),
                "executed_action": int(executed_action),
                "executed_action_name": ACTION_NAMES.get(executed_action, str(executed_action)),
                "semantic_action_name": semantic_action_name,
                "action_remapped": bool(action_remapped),
                "invalid_action_prevented": bool(action_remapped),
                "constraint_mode": "single_entry_exit",
                "single_entry_entered": bool(self._single_entry_entered),
                "episode_closed_by_policy": bool(forced_terminal),
            }
        )
        return (
            np.asarray(observation, dtype=np.float32),
            float(reward),
            bool(terminated),
            bool(truncated),
            self._add_episode_info(info),
        )

    def _constrain_action(self, action: int) -> int:
        if not self.constrain_invalid_actions:
            return int(action)
        if action == ACTION_MARKET_BUY and self.raw_env.position:
            return ACTION_HOLD
        if action == ACTION_MARKET_EXIT and not self.raw_env.position:
            return ACTION_HOLD
        return int(action)

    def _add_episode_info(self, info: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(info)
        payload.update(
            {
                "episode_id": self.current_episode.episode_id,
                "symbol": self.current_episode.symbol,
                "session": self.current_episode.session,
                "environment": "StomOrderbookRlEnv",
            }
        )
        return payload

    def render(self) -> None:
        return None

    def close(self) -> None:
        return None


def make_orderbook_sb3_env(
    episodes: Sequence[OrderbookEpisode],
    *,
    seed: int = 100,
    lookback_window: int = 30,
    cost_bps: float = 23.0,
    slippage_bps: float = 0.0,
    max_episode_steps: int = 120,
    constrain_invalid_actions: bool = False,
    single_entry_exit: bool = False,
    fixed_entry_exit_only: bool = False,
) -> StomOrderbookGymEnv:
    """Create a Gymnasium-compatible orderbook env for Stable-Baselines3."""

    return StomOrderbookGymEnv(
        episodes,
        StomOrderbookRlEnvConfig(
            lookback_window=lookback_window,
            cost_bps=cost_bps,
            slippage_bps=slippage_bps,
            max_episode_steps=max_episode_steps,
        ),
        constrain_invalid_actions=constrain_invalid_actions,
        single_entry_exit=single_entry_exit,
        fixed_entry_exit_only=fixed_entry_exit_only,
    )


__all__ = ["OrderbookEpisode", "StomOrderbookGymEnv", "make_orderbook_sb3_env"]
