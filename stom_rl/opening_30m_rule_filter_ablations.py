"""Feature ablations for opening RULE filters."""

from __future__ import annotations

from typing import Final, Mapping

REQUIRED_RULE_FILTER_ABLATIONS: Final[tuple[str, ...]] = (
    "no_participant_pressure",
    "no_orderbook_imbalance",
    "no_orderbook_persistence",
    "no_overheat_upper_wick",
    "no_time_bucket",
    "context_only",
    "tick_only",
    "shuffled_participant_context",
)


def build_rule_filter_ablation_artifact(*, full_context_return_pct: float, ablation_returns: Mapping[str, float], split_hash: str) -> dict[str, object]:
    """Build required context-ablation rows for a RULE filter."""

    rows = [_row(feature_set_id, full_context_return_pct, ablation_returns.get(feature_set_id), split_hash) for feature_set_id in REQUIRED_RULE_FILTER_ABLATIONS]
    passed = all(bool(row["passed"]) for row in rows)
    return {
        "artifact_type": "opening_rule_filter_ablations",
        "table_alias": "rule_filter_ablations",
        "split_hash": split_hash,
        "full_context_return_pct": float(full_context_return_pct),
        "feature_ablation_passed": passed,
        "ablations": rows,
    }


def _row(feature_set_id: str, full_return: float, ablated_return: float | None, split_hash: str) -> dict[str, object]:
    applicable = ablated_return is not None
    value = float(ablated_return) if ablated_return is not None else None
    shuffled = feature_set_id == "shuffled_participant_context"
    passed = False if not applicable else float(full_return) > float(value)
    return {
        "feature_set_id": feature_set_id,
        "split_hash": split_hash,
        "applicable": applicable,
        "comparison_status": "compared" if applicable else "missing_required_ablation",
        "full_context_return_pct": float(full_return),
        "ablated_return_pct": value,
        "delta_vs_full_oos_pct": None if value is None else float(full_return) - float(value),
        "shuffled_context": shuffled,
        "passed": passed,
    }
