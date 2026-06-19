"""Gymnasium-style STOM single-episode trading environment.

This is page 3 of the independent STOM RL lab.  The environment is intentionally
small and dependency-light: it follows Gymnasium's reset/step return convention
without requiring ``gymnasium`` as a hard dependency.  Later pages can wrap this
class with Gymnasium/Stable-Baselines3 adapters if we decide to add those
dependencies.

The environment is long-only and model-free:

* observations contain only historical rows ending before the action timestamp;
* actions are ``hold`` / ``buy`` / ``sell``;
* rewards use a 300-second horizon by default, but the future horizon value is
  used only for reward/info, never for observations;
* invalid actions are recorded and penalized instead of silently corrected.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar, Dict, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .episode_manifest import DEFAULT_OUTPUT_DIR, load_episode_manifest


ACTION_HOLD = 0
ACTION_BUY = 1
ACTION_SELL = 2
ACTION_NAMES = {
    ACTION_HOLD: "hold",
    ACTION_BUY: "buy",
    ACTION_SELL: "sell",
}
BASE_MARKET_COLUMNS = ["open", "high", "low", "close", "volume", "amount"]
POSITION_FEATURE_COLUMNS = ["position", "unrealized_return", "time_in_position"]


@dataclass(frozen=True)
class StomTickTradingEnvConfig:
    """Configuration for ``StomTickTradingEnv``.

    ``reward_horizon_seconds`` defaults to 300 because the previous Kronos
    horizon comparison found 300 seconds closest to break-even after cost.  The
    environment still steps one row at a time; the horizon defines the
    forward-looking reward target and the latest safe action index.
    """

    manifest_path: str = str(DEFAULT_OUTPUT_DIR / "episode_manifest.json")
    split: str = "train"
    episode_id: Optional[str] = None
    episode_index: Optional[int] = None
    seed: int = 100
    lookback_window: int = 300
    reward_horizon_seconds: int = 300
    cost_bps: float = 25.0
    slippage_bps: float = 0.0
    invalid_action_penalty: float = 0.001
    reward_mode: str = "horizon"
    normalize_observation: bool = True
    feature_columns: Optional[Tuple[str, ...]] = None
    feature_schema_mode: str = "compat"


class DiscreteSpace:
    """Tiny stand-in for ``gymnasium.spaces.Discrete``."""

    def __init__(self, n: int):
        self.n = int(n)

    def contains(self, value: Any) -> bool:
        try:
            action = int(value)
        except (TypeError, ValueError):
            return False
        return 0 <= action < self.n


class BoxSpace:
    """Tiny observation-space descriptor compatible with simple smoke tests."""

    def __init__(self, shape: Sequence[int], dtype: Any = np.float32):
        self.shape = tuple(int(part) for part in shape)
        self.dtype = dtype

    def contains(self, value: Any) -> bool:
        array = np.asarray(value)
        return array.shape == self.shape


class StomTickTradingEnv:
    """Long-only STOM trading environment backed by an episode manifest."""

    metadata: ClassVar[Dict[str, Any]] = {"render_modes": []}

    def __init__(self, config: Optional[StomTickTradingEnvConfig] = None, **overrides: Any):
        if config is not None and overrides:
            raise ValueError("Pass either config or keyword overrides, not both.")
        self.config = config or StomTickTradingEnvConfig(**overrides)
        if self.config.reward_mode not in {"horizon", "mark_to_market"}:
            raise ValueError("reward_mode must be one of: horizon, mark_to_market")
        if self.config.feature_schema_mode not in {"compat", "strict"}:
            raise ValueError("feature_schema_mode must be one of: compat, strict")
        if self.config.lookback_window <= 0:
            raise ValueError("lookback_window must be positive")
        if self.config.reward_horizon_seconds <= 0:
            raise ValueError("reward_horizon_seconds must be positive")

        self.manifest = load_episode_manifest(self.config.manifest_path)
        self.episodes = [
            episode
            for episode in self.manifest.get("episodes", [])
            if episode.get("split") == self.config.split
        ]
        if not self.episodes:
            raise ValueError(f"No episodes found for split={self.config.split!r}")

        self.market_feature_columns = list(self.config.feature_columns or tuple(BASE_MARKET_COLUMNS))
        self.feature_columns = self.market_feature_columns + [
            column for column in POSITION_FEATURE_COLUMNS if column not in self.market_feature_columns
        ]
        self.action_space = DiscreteSpace(3)
        self.observation_space = BoxSpace((self.config.lookback_window, len(self.feature_columns)))
        self._rng = np.random.default_rng(self.config.seed)

        self.episode: Dict[str, Any] = {}
        self.frame = pd.DataFrame()
        self.current_idx = 0
        self.max_action_idx = 0
        self.position = 0
        self.entry_price = 0.0
        self.entry_idx: Optional[int] = None
        self.realized_return = 0.0
        self.cumulative_reward = 0.0
        self.trade_count = 0
        self.invalid_action_count = 0
        self.last_info: Dict[str, Any] = {}

    @property
    def trade_cost_pct(self) -> float:
        return (float(self.config.cost_bps) + float(self.config.slippage_bps)) / 10_000.0

    def reset(self, *, seed: Optional[int] = None, options: Optional[Mapping[str, Any]] = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Reset to a deterministic episode and return ``(observation, info)``."""

        if seed is not None:
            self._rng = np.random.default_rng(seed)
        options = dict(options or {})
        self.episode = self._select_episode(options)
        self.frame = self._load_episode_frame(Path(self.episode["source_csv"]))
        min_rows = self.config.lookback_window + self.config.reward_horizon_seconds + 1
        if len(self.frame) < min_rows:
            raise ValueError(
                f"Episode {self.episode.get('episode_id')} has {len(self.frame)} rows, "
                f"but at least {min_rows} are required."
            )
        self.current_idx = int(self.config.lookback_window)
        self.max_action_idx = int(len(self.frame) - self.config.reward_horizon_seconds - 1)
        self.position = 0
        self.entry_price = 0.0
        self.entry_idx = None
        self.realized_return = 0.0
        self.cumulative_reward = 0.0
        self.trade_count = 0
        self.invalid_action_count = 0

        info = self._base_info()
        info.update(
            {
                "event": "reset",
                "config": asdict(self.config),
                "episode": self.episode,
                "safe_action_range": [self.config.lookback_window, self.max_action_idx],
                "no_future_observation": self._last_observation_timestamp() < self._action_timestamp(),
            }
        )
        self.last_info = info
        return self._observation(), info

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """Apply an action and return Gymnasium-style step output."""

        if not self.action_space.contains(action):
            raise ValueError(f"Invalid action {action!r}; expected 0, 1, or 2.")
        if self.frame.empty:
            raise RuntimeError("Call reset() before step().")
        if self.current_idx > self.max_action_idx:
            raise RuntimeError("Episode is already terminated; call reset().")

        action = int(action)
        action_name = ACTION_NAMES[action]
        current_price = self._close_at(self.current_idx)
        next_price = self._close_at(self.current_idx + 1)
        position_before = self.position
        invalid_action = False
        trade_cost = 0.0
        realized_trade_return = 0.0
        reward = 0.0

        if action == ACTION_BUY:
            if self.position == 1:
                invalid_action = True
            else:
                self.position = 1
                self.entry_price = current_price
                self.entry_idx = self.current_idx
                self.trade_count += 1
                trade_cost = self.trade_cost_pct
        elif action == ACTION_SELL:
            if self.position == 0:
                invalid_action = True
            else:
                realized_trade_return = (current_price - self.entry_price) / self.entry_price
                self.realized_return += realized_trade_return - self.trade_cost_pct
                self.position = 0
                self.entry_price = 0.0
                self.entry_idx = None
                self.trade_count += 1
                trade_cost = self.trade_cost_pct

        if invalid_action:
            self.invalid_action_count += 1
            reward -= float(self.config.invalid_action_penalty)
        elif self.config.reward_mode == "horizon":
            horizon_return = self._horizon_return(self.current_idx)
            if action == ACTION_SELL and position_before == 1 and not invalid_action:
                reward += realized_trade_return
            elif self.position == 1:
                reward += horizon_return
            reward -= trade_cost
        else:
            one_step_return = (next_price - current_price) / current_price
            reward += self.position * one_step_return - trade_cost

        self.cumulative_reward += float(reward)
        self.current_idx += 1
        terminated = self.current_idx > self.max_action_idx
        truncated = False

        info = self._base_info()
        info.update(
            {
                "event": "step",
                "action": action,
                "action_name": action_name,
                "position_before": position_before,
                "position_after": self.position,
                "invalid_action": invalid_action,
                "trade_cost_pct": trade_cost,
                "realized_trade_return": realized_trade_return,
                "reward": float(reward),
                "cumulative_reward": float(self.cumulative_reward),
                "trade_count": self.trade_count,
                "invalid_action_count": self.invalid_action_count,
                "next_close": next_price,
                "terminated": terminated,
                "truncated": truncated,
                "no_future_observation": self._last_observation_timestamp() < self._action_timestamp(),
            }
        )
        self.last_info = info
        return self._observation(), float(reward), terminated, truncated, info

    def _select_episode(self, options: Mapping[str, Any]) -> Dict[str, Any]:
        episode_id = options.get("episode_id") or self.config.episode_id
        if episode_id:
            for episode in self.episodes:
                if episode.get("episode_id") == episode_id:
                    return dict(episode)
            raise ValueError(f"Episode not found in split {self.config.split!r}: {episode_id}")

        episode_index = options.get("episode_index", self.config.episode_index)
        if episode_index is not None:
            return dict(self.episodes[int(episode_index) % len(self.episodes)])
        return dict(self.episodes[int(self._rng.integers(0, len(self.episodes)))])

    def _load_episode_frame(self, path: Path) -> pd.DataFrame:
        frame = pd.read_csv(path)
        required = {"date", *BASE_MARKET_COLUMNS}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"Episode CSV missing required columns: {missing}")
        frame = frame.copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        optional_missing = sorted(set(self.market_feature_columns) - set(frame.columns) - set(BASE_MARKET_COLUMNS))
        if optional_missing and self.config.feature_schema_mode == "strict":
            raise ValueError(f"Episode CSV missing configured feature columns: {optional_missing}")
        numeric_columns = list(dict.fromkeys([*BASE_MARKET_COLUMNS, *self.market_feature_columns]))
        for column in numeric_columns:
            if column not in frame.columns:
                frame[column] = 0.0
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame[numeric_columns] = frame[numeric_columns].ffill().bfill().fillna(0.0)
        frame = frame.dropna(subset=BASE_MARKET_COLUMNS)
        frame = frame[frame["close"] > 0].reset_index(drop=True)
        if frame.empty:
            raise ValueError(f"Episode CSV has no valid rows: {path}")
        return frame

    def _close_at(self, idx: int) -> float:
        return float(self.frame["close"].iloc[int(idx)])

    def _horizon_return(self, idx: int) -> float:
        current = self._close_at(idx)
        horizon = self._close_at(idx + self.config.reward_horizon_seconds)
        return float((horizon - current) / current)

    def _unrealized_return(self, price: Optional[float] = None) -> float:
        if self.position == 0 or not self.entry_price:
            return 0.0
        price = self._close_at(self.current_idx) if price is None else price
        return float((price - self.entry_price) / self.entry_price)

    def _time_in_position(self) -> float:
        if self.position == 0 or self.entry_idx is None:
            return 0.0
        return float(max(0, self.current_idx - self.entry_idx))

    def _observation_frame(self) -> pd.DataFrame:
        start = self.current_idx - self.config.lookback_window
        end = self.current_idx
        if start < 0:
            raise RuntimeError("current_idx is smaller than lookback_window.")
        window = self.frame.iloc[start:end][self.market_feature_columns].copy().reset_index(drop=True)
        window["position"] = float(self.position)
        window["unrealized_return"] = self._unrealized_return()
        window["time_in_position"] = self._time_in_position()
        return window[self.feature_columns]

    def _observation(self) -> np.ndarray:
        obs = self._observation_frame().to_numpy(dtype=np.float32)
        if not self.config.normalize_observation:
            return obs
        market_width = len(self.market_feature_columns)
        market = obs[:, :market_width]
        mean = market.mean(axis=0)
        std = market.std(axis=0)
        obs[:, :market_width] = np.clip((market - mean) / (std + 1e-6), -10.0, 10.0)
        return obs

    def _timestamp_at(self, idx: int) -> str:
        return pd.Timestamp(self.frame["date"].iloc[int(idx)]).isoformat()

    def _last_observation_timestamp(self) -> str:
        return self._timestamp_at(self.current_idx - 1)

    def _action_timestamp(self) -> str:
        idx = min(self.current_idx, len(self.frame) - 1)
        return self._timestamp_at(idx)

    def _horizon_timestamp(self) -> str:
        idx = min(self.current_idx + self.config.reward_horizon_seconds, len(self.frame) - 1)
        return self._timestamp_at(idx)

    def _base_info(self) -> Dict[str, Any]:
        action_idx = min(self.current_idx, len(self.frame) - 1)
        return {
            "episode_id": self.episode.get("episode_id"),
            "symbol": self.episode.get("symbol"),
            "session": self.episode.get("session"),
            "split": self.episode.get("split"),
            "current_idx": int(self.current_idx),
            "max_action_idx": int(self.max_action_idx),
            "last_observation_timestamp": self._last_observation_timestamp(),
            "action_timestamp": self._action_timestamp(),
            "horizon_timestamp": self._horizon_timestamp(),
            "close": self._close_at(action_idx),
            "horizon_return": self._horizon_return(action_idx)
            if action_idx + self.config.reward_horizon_seconds < len(self.frame)
            else None,
            "position": self.position,
            "entry_price": self.entry_price,
            "unrealized_return": self._unrealized_return(self._close_at(action_idx)),
            "realized_return": self.realized_return,
            "reward_mode": self.config.reward_mode,
            "feature_columns": list(self.feature_columns),
        }


def make_env_from_manifest(
    manifest_path: str = str(DEFAULT_OUTPUT_DIR / "episode_manifest.json"),
    **overrides: Any,
) -> StomTickTradingEnv:
    """Convenience factory used by tests, scripts, and future dashboard code."""

    return StomTickTradingEnv(StomTickTradingEnvConfig(manifest_path=manifest_path, **overrides))


def _demo_payload(env: StomTickTradingEnv) -> Dict[str, Any]:
    observation, reset_info = env.reset(seed=env.config.seed)
    next_observation, reward, terminated, truncated, step_info = env.step(ACTION_HOLD)
    return {
        "config": asdict(env.config),
        "reset": {
            "observation_shape": list(observation.shape),
            "info": reset_info,
        },
        "first_step": {
            "observation_shape": list(next_observation.shape),
            "reward": reward,
            "terminated": terminated,
            "truncated": truncated,
            "info": step_info,
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Smoke-test the STOM trading environment.")
    parser.add_argument("--manifest", default=str(DEFAULT_OUTPUT_DIR / "episode_manifest.json"))
    parser.add_argument("--split", default="train")
    parser.add_argument("--episode-id", default=None)
    parser.add_argument("--episode-index", type=int, default=None)
    parser.add_argument("--lookback-window", type=int, default=300)
    parser.add_argument("--reward-horizon-seconds", type=int, default=300)
    parser.add_argument("--seed", type=int, default=100)
    args = parser.parse_args(argv)

    env = StomTickTradingEnv(
        StomTickTradingEnvConfig(
            manifest_path=args.manifest,
            split=args.split,
            episode_id=args.episode_id,
            episode_index=args.episode_index,
            lookback_window=args.lookback_window,
            reward_horizon_seconds=args.reward_horizon_seconds,
            seed=args.seed,
        )
    )
    print(json.dumps(_demo_payload(env), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
