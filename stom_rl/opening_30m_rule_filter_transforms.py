"""Feature transforms for opening RULE filter controls and ablations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .opening_30m_rule_filter_contract import RuleFilterConfig
from .opening_30m_rule_filter_policy import select_rule_filter_policy

RULE_FILTER_ABLATION_IDS: tuple[str, ...] = (
    "no_participant_pressure",
    "no_orderbook_imbalance",
    "no_orderbook_persistence",
    "no_overheat_upper_wick",
    "no_time_bucket",
    "context_only",
    "tick_only",
    "shuffled_participant_context",
)


@dataclass(frozen=True, slots=True)
class RuleFilterTransformError(ValueError):
    """Raised when a feature transform id is not supported."""

    feature_set: str

    def __str__(self) -> str:
        return f"unsupported rule-filter feature transform: {self.feature_set}"


def build_rule_filter_ablation_returns(rows: Sequence[Mapping[str, Any]], config: RuleFilterConfig, split_hash: str) -> dict[str, float]:
    """Return OOS returns for all preregistered rule-filter ablations."""

    return {feature_set: _ablation_return(rows, config, split_hash, feature_set) for feature_set in RULE_FILTER_ABLATION_IDS}


def _ablation_return(rows: Sequence[Mapping[str, Any]], config: RuleFilterConfig, split_hash: str, feature_set: str) -> float:
    transformed = _apply_ablation(rows, feature_set)
    policy = select_rule_filter_policy(transformed, config=config, split_hash=split_hash)
    return float(policy["oos_metrics"]["net_return_pct"])


def _apply_ablation(rows: Sequence[Mapping[str, Any]], feature_set: str) -> list[dict[str, Any]]:
    match feature_set:
        case "shuffled_participant_context":
            participant_values = _rotate([_subset(dict(row.get("feature_values", {})), _is_participant_key) for row in rows])
            return _transform_rows(rows, lambda features, index: _replace_subset(features, participant_values[index]))
        case "context_only":
            return _transform_rows(rows, lambda features, _index: {key: value if _is_context_key(key) else 0.0 for key, value in features.items()})
        case "tick_only":
            return _transform_rows(rows, lambda features, _index: {key: 0.0 if _is_context_key(key) else value for key, value in features.items()})
        case "no_participant_pressure":
            return _zero_matching(rows, _is_participant_key)
        case "no_orderbook_imbalance":
            return _zero_matching(rows, _is_orderbook_imbalance_key)
        case "no_orderbook_persistence":
            return _zero_matching(rows, _is_orderbook_persistence_key)
        case "no_overheat_upper_wick":
            return _zero_matching(rows, _is_overheat_key)
        case "no_time_bucket":
            return _zero_matching(rows, lambda key: key.startswith("time_bucket"))
        case _:
            raise RuleFilterTransformError(feature_set)


def _zero_matching(rows: Sequence[Mapping[str, Any]], predicate: Callable[[str], bool]) -> list[dict[str, Any]]:
    return _transform_rows(rows, lambda features, _index: {key: 0.0 if predicate(key) else value for key, value in features.items()})


def _copy_row(row: Mapping[str, Any], features: Mapping[str, Any] | None = None) -> dict[str, Any]:
    copied = dict(row)
    copied["feature_values"] = dict(features if features is not None else row.get("feature_values", {}))
    return copied


def _rotate(values: list[Any]) -> list[Any]:
    return values[1:] + values[:1] if len(values) > 1 else values


def _transform_rows(rows: Sequence[Mapping[str, Any]], transform: Callable[[Mapping[str, Any], int], Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [_copy_row(row, features=transform(dict(row.get("feature_values", {})), index)) for index, row in enumerate(rows)]


def _subset(features: Mapping[str, Any], predicate: Callable[[str], bool]) -> dict[str, Any]:
    return {key: value for key, value in features.items() if predicate(key)}


def _replace_subset(features: Mapping[str, Any], replacements: Mapping[str, Any]) -> dict[str, Any]:
    copied = dict(features)
    for key, value in replacements.items():
        if key in copied:
            copied[key] = value
    return copied


def _is_participant_key(key: str) -> bool:
    return "participant" in key or key.startswith("proxy_") or "pressure" in key


def _is_orderbook_imbalance_key(key: str) -> bool:
    return "imb" in key or "imbalance" in key


def _is_orderbook_persistence_key(key: str) -> bool:
    return "orderbook_persistence" in key or key.startswith("ofi") or "micro" in key or "spread" in key


def _is_overheat_key(key: str) -> bool:
    return "overheat" in key or "upper_wick" in key or "wick" in key


def _is_context_key(key: str) -> bool:
    return _is_participant_key(key) or _is_orderbook_imbalance_key(key) or _is_orderbook_persistence_key(key) or _is_overheat_key(key) or key.startswith("time_bucket")
