"""Negative controls for opening RULE filters."""

from __future__ import annotations

from typing import Mapping

from .opening_30m_rule_filter_contract import VERDICT_NO_GO_CONTROL


def build_rule_filter_control_artifact(
    *,
    filter_oos_net_return_pct: float,
    baseline_returns: Mapping[str, float],
    split_hash: str,
    cost_bps: float,
    shuffled_label_return_pct: float,
    time_session_shuffle_return_pct: float,
    randomized_feature_return_pct: float,
) -> dict[str, object]:
    """Build same-split negative-control rows for a RULE filter."""

    rows = [
        _row("no_trade", filter_oos_net_return_pct, baseline_returns.get("no_trade", 0.0), split_hash, cost_bps, "baseline_same_split"),
        _row("buy_and_hold", filter_oos_net_return_pct, baseline_returns.get("buy_and_hold", 0.0), split_hash, cost_bps, "baseline_same_split"),
        _row("ts_imb_rule", filter_oos_net_return_pct, baseline_returns.get("ts_imb_rule", 0.0), split_hash, cost_bps, "baseline_same_split"),
        _row("shuffled_labels", filter_oos_net_return_pct, shuffled_label_return_pct, split_hash, cost_bps, "negative_control"),
        _row("time_session_shuffle", filter_oos_net_return_pct, time_session_shuffle_return_pct, split_hash, cost_bps, "negative_control"),
        _row("randomized_features", filter_oos_net_return_pct, randomized_feature_return_pct, split_hash, cost_bps, "negative_control"),
    ]
    passed = all(bool(row["passed"]) for row in rows)
    return {
        "artifact_type": "opening_rule_filter_controls",
        "table_alias": "rule_filter_controls",
        "split_hash": split_hash,
        "cost_bps": float(cost_bps),
        "negative_control_passed": passed,
        "blocking_verdict": "" if passed else VERDICT_NO_GO_CONTROL,
        "controls": rows,
    }


def _row(control_type: str, filter_return: float, control_return: float, split_hash: str, cost_bps: float, source: str) -> dict[str, object]:
    return {
        "control_type": control_type,
        "split_hash": split_hash,
        "cost_bps": float(cost_bps),
        "evaluation_source": source,
        "filter_oos_net_return_pct": float(filter_return),
        "control_net_return_pct": float(control_return),
        "passed": float(filter_return) > float(control_return),
    }
