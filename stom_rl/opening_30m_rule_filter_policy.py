"""Deterministic threshold policy for opening RULE filters."""

from __future__ import annotations

from itertools import product
from typing import Any, Mapping, Sequence, assert_never

from .opening_30m_rule_filter_contract import ACTION_SKIP, ACTION_TAKE, FEATURE_SET_FULL_CONTEXT, VERDICT_INCONCLUSIVE, RuleFilterConfig, RuleFilterFeatureSetId, rule_filter_strategy_context


def select_rule_filter_policy(rows: Sequence[Mapping[str, Any]], *, config: RuleFilterConfig, split_hash: str) -> dict[str, Any]:
    """Select thresholds on validation rows and evaluate once on OOS rows."""

    train_rows = [row for row in rows if str(row.get("split")) == "train"]
    validation_rows = [row for row in rows if str(row.get("split")) == "validation"]
    oos_rows = [row for row in rows if str(row.get("split")) == "oos"]
    threshold = _select_threshold(validation_rows or train_rows, feature_set_id=config.feature_set_id)
    actions = {str(row["episode_id"]): _action(row, threshold, feature_set_id=config.feature_set_id) for row in rows}
    validation_metrics = evaluate_rule_filter_metrics(validation_rows, threshold, feature_set_id=config.feature_set_id)
    oos_metrics = evaluate_rule_filter_metrics(oos_rows, threshold, feature_set_id=config.feature_set_id)
    verdict_hint = VERDICT_INCONCLUSIVE if int(oos_metrics["take_count"]) < config.min_oos_take_trades else ""
    return {
        "artifact_type": "opening_rule_filter_policy",
        "policy_id": f"rule_filter_{split_hash}",
        "split_hash": split_hash,
        "feature_set_id": config.feature_set_id,
        "selected_thresholds": threshold,
        "validation_metrics": validation_metrics,
        "oos_metrics": oos_metrics,
        "actions_by_episode": actions,
        "verdict_hint": verdict_hint,
        "strategy_context": rule_filter_strategy_context(),
    }


def _select_threshold(rows: Sequence[Mapping[str, Any]], *, feature_set_id: RuleFilterFeatureSetId) -> dict[str, float]:
    candidates = [
        {"score_threshold": score, "max_overheat_score": overheat}
        for score, overheat in product((0.0, 0.25, 0.5, 0.75), (0.25, 0.5, 0.75, 1.0))
    ]
    return max(candidates, key=lambda item: (evaluate_rule_filter_metrics(rows, item, feature_set_id=feature_set_id)["net_return_pct"], evaluate_rule_filter_metrics(rows, item, feature_set_id=feature_set_id)["take_count"]))


def _action(row: Mapping[str, Any], threshold: Mapping[str, float], *, feature_set_id: RuleFilterFeatureSetId) -> str:
    if str(row.get("base_action")) != ACTION_TAKE:
        return ACTION_SKIP
    match feature_set_id:
        case "minimal_ts_imb":
            return ACTION_TAKE
        case "full_context":
            features = row["feature_values"]
            overheat = float(features.get("overheat_score", 0.0))
            if _score(features, feature_set_id=feature_set_id) >= float(threshold["score_threshold"]) and overheat <= float(threshold["max_overheat_score"]):
                return ACTION_TAKE
            return ACTION_SKIP
        case "time_bucket_only":
            if _score(row["feature_values"], feature_set_id=feature_set_id) >= float(threshold["score_threshold"]):
                return ACTION_TAKE
            return ACTION_SKIP
        case unreachable:
            assert_never(unreachable)


def evaluate_rule_filter_metrics(rows: Sequence[Mapping[str, Any]], threshold: Mapping[str, float], *, feature_set_id: RuleFilterFeatureSetId = FEATURE_SET_FULL_CONTEXT) -> dict[str, float | int]:
    """Evaluate a fixed threshold on supplied rows without selecting on OOS."""
    net = 0.0
    take_count = 0
    skipped_cost = 0.0
    for row in rows:
        if _action(row, threshold, feature_set_id=feature_set_id) == ACTION_TAKE:
            net += float(row.get("base_net_return_pct", 0.0))
            take_count += 1
        else:
            skipped_cost += max(0.0, float(row.get("skipped_opportunity_net_return_pct", 0.0)))
    return {"net_return_pct": net, "take_count": take_count, "skipped_opportunity_cost_pct": skipped_cost}


def _score(features: Mapping[str, Any], *, feature_set_id: RuleFilterFeatureSetId) -> float:
    match feature_set_id:
        case "full_context":
            participant = float(features.get("participant_pressure_score", 0.0))
            orderbook = float(features.get("orderbook_persistence_score", 0.0))
            overheat = float(features.get("overheat_score", 0.0))
            time_bucket = float(features.get("time_bucket_0_10", 0.0))
            return (participant + orderbook + time_bucket + (1.0 - overheat)) / 4.0
        case "minimal_ts_imb":
            return 1.0
        case "time_bucket_only":
            return float(features.get("time_bucket_0_10", 0.0))
        case unreachable:
            assert_never(unreachable)
