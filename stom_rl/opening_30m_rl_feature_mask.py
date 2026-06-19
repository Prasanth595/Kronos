"""Feature-set masking and context observation wrapper for opening RL candidates."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .opening_30m_rl_context import (
    FEATURE_CONTRACTS,
    OPENING_RL_CONTEXT_FEATURE_NAMES,
    build_opening_rl_context,
    normalize_feature_set_id,
)
from .opening_30m_rl_realdata import JsonValue
from .orderbook_persistence import OrderbookPersistenceError
from .orderbook_rl_env import ORDERBOOK_FEATURE_NAMES
from .orderbook_sb3_adapter import StomOrderbookGymEnv
from .participant_pressure_features import ParticipantPressureError

DEFAULT_FEATURE_COLUMNS = tuple(ORDERBOOK_FEATURE_NAMES) + tuple(OPENING_RL_CONTEXT_FEATURE_NAMES)


class FeatureMaskEnv(gym.Wrapper):
    """Apply feature-set ablations and append causal opening context features."""

    def __init__(self, env: StomOrderbookGymEnv, feature_set_id: str) -> None:
        super().__init__(env)
        self.feature_set_id = normalize_feature_set_id(feature_set_id)
        self._feature_columns = list(env.raw_env.feature_columns) + list(OPENING_RL_CONTEXT_FEATURE_NAMES)
        self._zero_indices = _zero_indices(self._feature_columns, self.feature_set_id)
        self._shuffle_indices = _shuffle_indices(self._feature_columns, self.feature_set_id)
        size = len(self._feature_columns)
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(size,), dtype=np.float32)

    def reset(self, **kwargs: Any) -> tuple[np.ndarray, dict[str, Any]]:
        observation, info = self.env.reset(**kwargs)
        return self._mask_and_append(observation), self._with_feature_info(info)

    def step(self, action: Any) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        observation, reward, terminated, truncated, info = self.env.step(action)
        return self._mask_and_append(observation), reward, terminated, truncated, self._with_feature_info(info)

    def _mask_and_append(self, observation: np.ndarray) -> np.ndarray:
        values = np.concatenate([np.asarray(observation, dtype=np.float32), self._context_vector()]).astype(np.float32)
        for index in self._zero_indices:
            if 0 <= index < len(values):
                values[index] = 0.0
        if len(self._shuffle_indices) > 1:
            values[self._shuffle_indices] = np.roll(values[self._shuffle_indices], 1)
        return values

    def _context_vector(self) -> np.ndarray:
        try:
            context = build_opening_rl_context(
                self.env.current_episode.frame,
                decision_second=min(int(self.env.raw_env.current_idx), len(self.env.current_episode.frame) - 1),
            )
            return np.asarray(context["vector"], dtype=np.float32)
        except (ParticipantPressureError, OrderbookPersistenceError, KeyError, IndexError):
            return np.zeros(len(OPENING_RL_CONTEXT_FEATURE_NAMES), dtype=np.float32)

    def _with_feature_info(self, info: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(info)
        context_available = bool(np.any(self._context_vector()))
        payload["feature_set_id"] = self.feature_set_id
        payload["zeroed_feature_count"] = len(self._zero_indices)
        payload["context_feature_names"] = list(OPENING_RL_CONTEXT_FEATURE_NAMES)
        payload["context_feature_status"] = "available" if context_available else "missing"
        payload.update(feature_mask_details(self._feature_columns, self.feature_set_id))
        payload["feature_columns"] = self._feature_columns
        return payload


def _zero_indices(feature_columns: Sequence[str], feature_set_id: str) -> list[int]:
    details = feature_mask_details(feature_columns, feature_set_id)
    zero_names = set(details["zeroed_feature_names"])
    return [index for index, name in enumerate(feature_columns) if name in zero_names]


def _shuffle_indices(feature_columns: Sequence[str], feature_set_id: str) -> list[int]:
    details = feature_mask_details(feature_columns, feature_set_id)
    shuffle_names = set(details["shuffled_feature_names"])
    return [index for index, name in enumerate(feature_columns) if name in shuffle_names]


def feature_mask_details(feature_columns: Sequence[str] = DEFAULT_FEATURE_COLUMNS, feature_set_id: str = "full") -> dict[str, JsonValue]:
    """Return auditable feature-mask details for candidate ablations."""

    canonical_id = normalize_feature_set_id(feature_set_id)
    groups = _removed_groups(canonical_id)
    shuffled_groups = _shuffled_groups(canonical_id)
    names = [name for name in feature_columns if _belongs_to_removed_group(name, groups, canonical_id)]
    shuffled = [name for name in feature_columns if any(_belongs_to_group(name, group) for group in shuffled_groups)]
    checked_groups = tuple(dict.fromkeys((*groups, *shuffled_groups)))
    unavailable = [group for group in checked_groups if not any(_belongs_to_group(name, group) for name in feature_columns)]
    return {
        "feature_set_id": canonical_id,
        "removed_feature_groups": list(groups),
        "shuffled_feature_groups": list(shuffled_groups),
        "zeroed_feature_names": names,
        "zeroed_feature_count": len(names),
        "shuffled_feature_names": shuffled,
        "shuffled_feature_count": len(shuffled),
        "unavailable_feature_groups": unavailable,
    }


def _removed_groups(canonical_id: str) -> tuple[str, ...]:
    if canonical_id == "no_orderbook_imbalance":
        return ("orderbook_imbalance",)
    if canonical_id == "no_orderbook_persistence":
        return ("orderbook_persistence",)
    if canonical_id == "no_overheat_upper_wick":
        return ("overheat_upper_wick",)
    if canonical_id == "minimal_price_volume":
        return (
            "participant_pressure",
            "orderbook_imbalance",
            "orderbook_persistence",
            "overheat_upper_wick",
            "optional_investor_flow",
        )
    if canonical_id == "no_participant_pressure":
        return ("participant_pressure",)
    return ()


def _shuffled_groups(canonical_id: str) -> tuple[str, ...]:
    if canonical_id == "shuffled_participant_context":
        return ("participant_pressure",)
    return ()


def _belongs_to_removed_group(name: str, groups: Sequence[str], feature_set_id: str) -> bool:
    if feature_set_id == "minimal_price_volume":
        return not name.startswith(("ret_", "vol_")) and name not in {"position", "time_frac"}
    return any(_belongs_to_group(name, group) for group in groups)


def _belongs_to_group(name: str, group: str) -> bool:
    for contract in FEATURE_CONTRACTS:
        if contract.feature_name == name:
            return contract.feature_group == group
    if group == "participant_pressure":
        return any(token in name for token in ("foreign", "institution", "program", "personal", "participant", "net_buy"))
    if group == "orderbook_imbalance":
        return any(token in name for token in ("book_imb", "spread", "micro"))
    if group == "orderbook_persistence":
        return any(token in name for token in ("ofi", "sflow"))
    if group == "overheat_upper_wick":
        return name.startswith(("ret_", "vol_")) or name.startswith("ts_")
    return False
