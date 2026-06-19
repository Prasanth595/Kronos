"""Candidate contracts and artifacts for opening PPO/DQN validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Sequence

from .opening_30m_rl_realdata import JsonValue


class CandidateAlgorithm(StrEnum):
    """Supported opening candidate algorithms."""

    DQN = "dqn"
    PPO = "ppo"


class OpeningAction(StrEnum):
    """Shared discrete opening action set."""

    HOLD_AFTER_FIXED_ENTRY = "HOLD_AFTER_FIXED_ENTRY"
    EXIT_LONG_MARKETABLE = "EXIT_LONG_MARKETABLE"


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    """Candidate configuration that cannot tune on OOS."""

    candidate_id: str
    algorithm: CandidateAlgorithm
    seed: int
    total_timesteps: int
    split_hash: str
    feature_set_id: str
    cost_bps: float = 23.0
    action_contract_version: str = "opening_discrete_v1"
    use_oos_for_selection: bool = False


@dataclass(frozen=True, slots=True)
class CandidateConfigError(ValueError):
    """Raised when a candidate config violates research guardrails."""

    reason: str

    def __str__(self) -> str:
        return self.reason


def opening_action_contract() -> dict[str, JsonValue]:
    """Return the shared discrete action contract used by PPO and DQN."""

    return {
        "version": "opening_discrete_v1",
        "space": "Discrete(2)",
        "actions": [action.value for action in OpeningAction],
        "environment_mode": "fixed_entry_exit_only",
        "policy_action_names": ["hold", "exit"],
        "live_order_actions": False,
        "continuous_sizing": False,
    }


def default_candidate_configs(split_hash: str, feature_set_id: str = "full_context") -> list[CandidateConfig]:
    """Return bounded DQN/PPO defaults for a frozen split."""

    return [
        CandidateConfig("dqn_default_seed100", CandidateAlgorithm.DQN, 100, 64, split_hash, feature_set_id),
        CandidateConfig("ppo_default_seed100", CandidateAlgorithm.PPO, 100, 64, split_hash, feature_set_id),
    ]


def validate_candidate_config(config: CandidateConfig) -> None:
    """Reject OOS tuning and incompatible candidate configs."""

    if config.use_oos_for_selection:
        raise CandidateConfigError("OOS cannot be used for model selection")
    if config.cost_bps != 23.0:
        raise CandidateConfigError("opening candidates must use 23bp cost by default")
    if config.total_timesteps <= 0:
        raise CandidateConfigError("total_timesteps must be positive")


def candidate_config_artifact(configs: Sequence[CandidateConfig]) -> dict[str, JsonValue]:
    """Serialize candidate configs for dashboard evidence."""

    for config in configs:
        validate_candidate_config(config)
    return {
        "artifact_type": "opening_30m_candidate_configs",
        "action_contract": opening_action_contract(),
        "candidates": [_config_row(config) for config in configs],
        "guardrail": "Validation may select candidates; OOS is final-only.",
    }


def train_candidate_artifacts(
    configs: Sequence[CandidateConfig],
    *,
    sb3_available: bool,
    validation_score_by_candidate: Mapping[str, float] | None = None,
    oos_score_by_candidate: Mapping[str, float] | None = None,
    model_path_by_candidate: Mapping[str, str] | None = None,
) -> dict[str, JsonValue]:
    """Write deterministic candidate training/evaluation metadata."""

    scores = validation_score_by_candidate or {}
    oos_scores = oos_score_by_candidate or {}
    model_paths = model_path_by_candidate or {}
    rows = [
        _training_row(
            config,
            sb3_available=sb3_available,
            validation_score=float(scores.get(config.candidate_id, 0.0)),
            oos_score=oos_scores.get(config.candidate_id),
            model_path=str(model_paths.get(config.candidate_id, "")),
        )
        for config in configs
    ]
    return {
        "artifact_type": "opening_30m_candidate_training",
        "selection_split": "validation",
        "oos_is_final_only": True,
        "candidates": rows,
    }


def _config_row(config: CandidateConfig) -> dict[str, JsonValue]:
    row = asdict(config)
    row["algorithm"] = config.algorithm.value
    return row


def _training_row(
    config: CandidateConfig,
    *,
    sb3_available: bool,
    validation_score: float,
    oos_score: float | None,
    model_path: str,
) -> dict[str, JsonValue]:
    validate_candidate_config(config)
    verified_model_path = str(model_path) if model_path and Path(model_path).is_file() else ""
    if not sb3_available:
        status = "skipped_sb3_unavailable"
    elif verified_model_path:
        status = "trained"
    else:
        status = "not_trained"
    return {
        "candidate_id": config.candidate_id,
        "algorithm": config.algorithm.value,
        "seed": int(config.seed),
        "split_hash": config.split_hash,
        "feature_set_id": config.feature_set_id,
        "total_timesteps": int(config.total_timesteps),
        "status": status,
        "model_path": verified_model_path,
        "validation_net_return_pct": validation_score if status == "trained" else 0.0,
        "oos_net_return_pct": oos_score if status == "trained" else None,
        "selected_by": "validation",
    }
