"""Causal dataset rows for the opening RULE filter."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import pandas as pd  # noqa: PANDAS_OK - existing STOM opening pipeline is pandas-based

from .opening_30m_rl_baselines import OpeningBaselineConfig, POLICY_TS_IMB, evaluate_opening_baselines
from .opening_30m_rl_context import build_opening_rl_context
from .opening_30m_rl_oos_split import validate_oos_split_manifest
from .opening_30m_rule_filter_contract import ACTION_SKIP, ACTION_TAKE, RuleFilterConfig, rule_filter_strategy_context


def build_rule_filter_dataset(
    frames: Sequence[pd.DataFrame],
    *,
    split_manifest: Mapping[str, Any],
    config: RuleFilterConfig,
) -> dict[str, Any]:
    """Build TAKE/SKIP meta-label rows without using future rows for features."""

    validate_oos_split_manifest(split_manifest)
    split_hash = str(split_manifest["split_hash"])
    split_lookup = _split_lookup(split_manifest)
    baseline = evaluate_opening_baselines(
        frames,
        OpeningBaselineConfig(decision_index=config.decision_second, cost_bps=config.cost_bps),
    )
    baseline_rows = {
        str(row["episode_id"]): row
        for row in baseline["rows"]
        if str(row.get("policy")) == POLICY_TS_IMB
    }
    rows = [_dataset_row(frame, baseline_rows, split_lookup, split_hash, config) for frame in frames]
    return {
        "artifact_type": "opening_rule_filter_dataset",
        "split_hash": split_hash,
        "cost_bps": float(config.cost_bps),
        "rows": rows,
        "strategy_context": rule_filter_strategy_context(),
    }


def _dataset_row(
    frame: pd.DataFrame,
    baseline_rows: Mapping[str, Mapping[str, Any]],
    split_lookup: Mapping[str, str],
    split_hash: str,
    config: RuleFilterConfig,
) -> dict[str, Any]:
    episode_id = f"{frame['symbol'].iloc[0]}_{frame['session'].iloc[0]}"
    baseline = baseline_rows[episode_id]
    context = build_opening_rl_context(frame, decision_second=config.decision_second)
    features = dict(zip(context["feature_names"], context["vector"], strict=True))
    features["time_bucket_0_10"] = 1.0 if config.decision_second <= 10 else 0.0
    base_net = float(baseline["net_return_pct"])
    base_action = ACTION_TAKE if int(baseline.get("trade_count", 0)) > 0 else ACTION_SKIP
    session = str(frame["session"].iloc[0])
    return {
        "episode_id": episode_id,
        "symbol": str(frame["symbol"].iloc[0]),
        "session": session,
        "split": split_lookup[session],
        "split_hash": split_hash,
        "cost_bps": float(config.cost_bps),
        "base_action": base_action,
        "meta_label_take": 1 if base_action == ACTION_TAKE and base_net > 0.0 else 0,
        "base_net_return_pct": base_net,
        "skip_net_return_pct": 0.0,
        "skipped_opportunity_net_return_pct": base_net if base_action == ACTION_TAKE else 0.0,
        "feature_values": features,
        "proxy_availability": {name: value for name, value in features.items() if name.startswith("proxy_available_")},
        "diagnostics": context["diagnostics"],
    }


def _split_lookup(split_manifest: Mapping[str, Any]) -> dict[str, str]:
    raw = split_manifest["split_sessions"]
    lookup: dict[str, str] = {}
    for split, sessions in raw.items():
        for session in sessions:
            lookup[str(session)] = str(split)
    return lookup
