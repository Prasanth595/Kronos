"""Participant/orderbook context vector for opening RL experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Mapping

import pandas as pd  # noqa: PANDAS_OK - STOM opening RL context uses pandas frames

from .orderbook_persistence import (
    COL_ASK1,
    COL_BID1,
    build_orderbook_persistence_score,
)
from .participant_pressure_features import (
    COL_FOREIGN_NET_BUY,
    COL_INSTITUTION_NET_BUY,
    COL_PROGRAM_NET_BUY,
    compute_participant_pressure_features,
)


@dataclass(frozen=True, slots=True)
class FeatureContract:
    """Dashboard and training metadata for one causal opening RL context feature."""

    feature_name: str
    feature_group: str
    source: str
    causal_lookback: str
    missing_policy: str
    dashboard_label: str


CANONICAL_FEATURE_GROUPS: Final[tuple[str, ...]] = (
    "price_volume",
    "participant_pressure",
    "orderbook_imbalance",
    "orderbook_persistence",
    "overheat_upper_wick",
    "optional_investor_flow",
)
OPENING_RL_CONTEXT_FEATURE_NAMES: Final[tuple[str, ...]] = (
    "participant_pressure_score",
    "orderbook_persistence_score",
    "overheat_score",
    "proxy_available_trade_strength",
    "proxy_available_bid_depth_imbalance",
    "proxy_available_foreign_net_buy",
    "proxy_available_institution_net_buy",
    "proxy_available_program_net_buy",
)
CANONICAL_FEATURE_SET_IDS: Final[tuple[str, ...]] = (
    "full_context",
    "no_participant_pressure",
    "no_orderbook_imbalance",
    "no_orderbook_persistence",
    "no_overheat_upper_wick",
    "minimal_price_volume",
    "shuffled_participant_context",
    "ts_imb_rule_baseline",
)
REQUIRED_ABLATION_KEYS: Final[tuple[str, ...]] = CANONICAL_FEATURE_SET_IDS
LEGACY_FEATURE_SET_ALIASES: Final[Mapping[str, str]] = {
    "full": "full_context",
    "no_participant": "no_participant_pressure",
    "no_orderbook": "no_orderbook_imbalance",
    "no_overheat": "no_overheat_upper_wick",
    "no_overheat_penalty": "no_overheat_upper_wick",
}
FEATURE_CONTRACTS: Final[tuple[FeatureContract, ...]] = (
    FeatureContract("participant_pressure_score", "participant_pressure", "tick trade/amount/depth proxy", "rows <= decision_second", "set unavailable flags; do not infer actor identity", "Participant proxy pressure"),
    FeatureContract("orderbook_persistence_score", "orderbook_persistence", "bid/ask depth and order-flow persistence", "rows <= decision_second", "missing book columns block persistence evidence", "Orderbook persistence"),
    FeatureContract("overheat_score", "overheat_upper_wick", "causal return/volume/orderbook overheat proxy", "rows <= decision_second", "missing values reduce confidence, not profit claim", "Overheat and upper-wick risk"),
    FeatureContract("proxy_available_trade_strength", "participant_pressure", "trade strength column readiness", "schema at decision time", "false when absent", "Trade strength available"),
    FeatureContract("proxy_available_bid_depth_imbalance", "orderbook_imbalance", "bid/ask depth schema readiness", "schema at decision time", "false when absent", "Bid depth imbalance available"),
    FeatureContract("proxy_available_foreign_net_buy", "optional_investor_flow", "optional investor-flow column", "schema at decision time", "None/false when absent; never zero-fill as truth", "Foreign net-buy proxy available"),
    FeatureContract("proxy_available_institution_net_buy", "optional_investor_flow", "optional investor-flow column", "schema at decision time", "None/false when absent; never zero-fill as truth", "Institution net-buy proxy available"),
    FeatureContract("proxy_available_program_net_buy", "optional_investor_flow", "optional investor-flow column", "schema at decision time", "None/false when absent; never zero-fill as truth", "Program net-buy proxy available"),
)


def normalize_feature_set_id(feature_set_id: str) -> str:
    """Return the canonical opening RL feature-set ID for legacy or current input."""

    return LEGACY_FEATURE_SET_ALIASES.get(feature_set_id, feature_set_id)


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _participant_pressure_score(features: Mapping[str, Any]) -> float:
    trade_strength = _clip01(float(features["trade_strength"]) / 150.0)
    signed_flow = _clip01((float(features["signed_amount_ratio"]) + 1.0) / 2.0)
    bid_depth = _clip01(float(features["bid_depth_imbalance"]))
    return (trade_strength + signed_flow + bid_depth) / 3.0


def _proxy_flag(frame: pd.DataFrame, column: str) -> float:
    return 1.0 if column in frame.columns else 0.0


def build_opening_rl_context(
    frame: pd.DataFrame,
    *,
    decision_second: int,
) -> dict[str, Any]:
    """Build the causal context vector that Task 7 training can concatenate."""

    participant = compute_participant_pressure_features(frame, decision_second=decision_second)
    orderbook = build_orderbook_persistence_score(frame, decision_second=decision_second)
    participant_score = _participant_pressure_score(participant)
    orderbook_score = float(orderbook["score"])
    overheat_score = float(orderbook["components"]["overheat_penalty"])
    vector = [
        participant_score,
        orderbook_score,
        overheat_score,
        1.0,
        1.0,
        _proxy_flag(frame, COL_FOREIGN_NET_BUY),
        _proxy_flag(frame, COL_INSTITUTION_NET_BUY),
        _proxy_flag(frame, COL_PROGRAM_NET_BUY),
    ]
    return {
        "artifact_type": "opening_rl_context",
        "participant_context_version": "market_participant_proxy_v1",
        "decision_second": int(decision_second),
        "feature_names": list(OPENING_RL_CONTEXT_FEATURE_NAMES),
        "vector": vector,
        "diagnostics": {
            "participant_pressure_features": participant,
            "orderbook_components": orderbook["components"],
            "source": "causal rows only; no future rows after decision_second",
        },
        "strategy_context": {
            "line": "rl_experiment_context",
            "label": "RL EXPERIMENT CONTEXT",
            "is_reinforcement_learning": False,
            "is_live_ready": False,
            "is_profit_model": False,
        },
    }


def _latest_has_liquidity(frame: pd.DataFrame, decision_second: int) -> bool:
    row = frame.iloc[decision_second]
    return float(row[COL_BID1]) > 0.0 and float(row[COL_ASK1]) > 0.0


def compute_opening_context_reward_penalty(
    frame: pd.DataFrame,
    *,
    decision_second: int,
    action_name: str,
) -> dict[str, Any]:
    """Compute causal reward penalties for participant/orderbook context use."""

    context = build_opening_rl_context(frame, decision_second=decision_second)
    components = context["diagnostics"]["orderbook_components"]
    is_entry = action_name == "market_buy"
    overheat_penalty = float(components["overheat_penalty"]) * 0.01 if is_entry else 0.0
    liquidity_penalty = 0.02 if is_entry and not _latest_has_liquidity(frame, decision_second) else 0.0
    bid_deterioration = (
        0.005
        if is_entry
        and (
            float(components["bid_depth_persistence"]) < 0.45
            or float(components["ofi_pressure"]) < 0.45
        )
        else 0.0
    )
    diagnostics = {
        "decision_second": int(decision_second),
        "action_name": action_name,
        "overheat_entry_penalty": overheat_penalty,
        "missing_liquidity_entry_penalty": liquidity_penalty,
        "deteriorating_bid_depth_overtrade_penalty": bid_deterioration,
    }
    return {"total_penalty": sum(diagnostics[key] for key in diagnostics if key.endswith("_penalty")), "diagnostics": diagnostics}


def apply_participant_context_ablation_gate(
    candidate: Mapping[str, Any],
    ablation_results: Mapping[str, float],
) -> dict[str, Any]:
    """Block GO_CANDIDATE unless participant context survives ablation controls."""

    normalized_results = {normalize_feature_set_id(key): value for key, value in ablation_results.items()}
    missing = [key for key in REQUIRED_ABLATION_KEYS if key not in normalized_results]
    full = float(normalized_results.get("full_context", 0.0))
    ts_imb = float(normalized_results.get("ts_imb_rule_baseline", candidate.get("ts_imb_net_return_pct", 0.0)))
    passes = (
        not missing
        and str(candidate.get("candidate_verdict")) == "GO_CANDIDATE"
        and bool(candidate.get("cost_gate_passed"))
        and full > ts_imb
        and full > float(normalized_results.get("no_participant_pressure", full))
        and full > float(normalized_results.get("no_orderbook_imbalance", full))
        and full > float(normalized_results.get("no_orderbook_persistence", full))
        and full > float(normalized_results.get("no_overheat_upper_wick", full))
        and float(normalized_results.get("shuffled_participant_context", full)) <= ts_imb
    )
    return {
        "verdict": "GO_CANDIDATE" if passes else "NO-GO",
        "participant_context_ablation_passed": passes,
        "negative_control_blocked_go": not passes and str(candidate.get("candidate_verdict")) == "GO_CANDIDATE",
        "go_block_reason": "" if passes else "participant_context_failed_ablation_or_cost_gate",
        "required_ablation_keys": list(REQUIRED_ABLATION_KEYS),
        "missing_ablation_keys": missing,
        "ablation_results": normalized_results,
        "baseline": {"ts_imb_rule_baseline": ts_imb},
    }
