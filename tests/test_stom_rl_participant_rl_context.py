from stom_rl.opening_30m_rl_context import (
    CANONICAL_FEATURE_GROUPS,
    FEATURE_CONTRACTS,
    OPENING_RL_CONTEXT_FEATURE_NAMES,
    REQUIRED_ABLATION_KEYS,
    apply_participant_context_ablation_gate,
    build_opening_rl_context,
    compute_opening_context_reward_penalty,
    normalize_feature_set_id,
)
from stom_rl.orderbook_persistence import COL_ASK1, COL_BID1, COL_PRICE
from stom_rl.orderbook_rl_env import ACTION_NAMES
from tests.fixtures.stom_opening_rl import opening_orderbook_frame


def test_opening_rl_observation_includes_participant_orderbook_context():
    frame = opening_orderbook_frame(symbol="000250", session="20250103")
    changed_future = frame.copy()
    changed_future.loc[changed_future.index > 3, COL_PRICE] = 1600.0

    context = build_opening_rl_context(frame, decision_second=3)
    changed = build_opening_rl_context(changed_future, decision_second=3)

    assert context["feature_names"] == list(OPENING_RL_CONTEXT_FEATURE_NAMES)
    assert context["feature_names"][:3] == [
        "participant_pressure_score",
        "orderbook_persistence_score",
        "overheat_score",
    ]
    assert "proxy_available_trade_strength" in context["feature_names"]
    assert "proxy_available_foreign_net_buy" in context["feature_names"]
    assert len(context["vector"]) == len(OPENING_RL_CONTEXT_FEATURE_NAMES)
    assert context["vector"] == changed["vector"]
    assert set(ACTION_NAMES.values()) == {"hold", "market_buy", "market_exit"}


def test_opening_rl_feature_contract_uses_canonical_groups_and_aliases():
    assert CANONICAL_FEATURE_GROUPS == (
        "price_volume",
        "participant_pressure",
        "orderbook_imbalance",
        "orderbook_persistence",
        "overheat_upper_wick",
        "optional_investor_flow",
    )
    assert normalize_feature_set_id("full") == "full_context"
    assert normalize_feature_set_id("no_participant") == "no_participant_pressure"
    assert normalize_feature_set_id("no_orderbook") == "no_orderbook_imbalance"
    assert normalize_feature_set_id("no_overheat") == "no_overheat_upper_wick"
    assert set(REQUIRED_ABLATION_KEYS) == {
        "full_context",
        "no_participant_pressure",
        "no_orderbook_imbalance",
        "no_orderbook_persistence",
        "no_overheat_upper_wick",
        "minimal_price_volume",
        "shuffled_participant_context",
        "ts_imb_rule_baseline",
    }
    for contract in FEATURE_CONTRACTS:
        assert contract.feature_group in CANONICAL_FEATURE_GROUPS
        assert contract.source
        assert contract.causal_lookback
        assert contract.missing_policy
        assert contract.dashboard_label


def test_participant_context_ablation_failure_blocks_go_candidate():
    result = apply_participant_context_ablation_gate(
        {
            "candidate_verdict": "GO_CANDIDATE",
            "full_context_net_return_pct": 0.4,
            "ts_imb_net_return_pct": 0.6,
            "cost_gate_passed": True,
        },
        {
            "full_context": 0.4,
            "no_participant_pressure": 0.5,
            "no_orderbook_persistence": 0.3,
            "no_overheat_penalty": 0.4,
            "shuffled_participant_context": 0.7,
            "ts_imb_rule_baseline": 0.6,
        },
    )

    assert result["verdict"] == "NO-GO"
    assert result["participant_context_ablation_passed"] is False
    assert result["negative_control_blocked_go"] is True
    assert set(result["required_ablation_keys"]) == set(REQUIRED_ABLATION_KEYS)
    assert result["go_block_reason"] == "participant_context_failed_ablation_or_cost_gate"


def test_context_reward_penalties_are_causal_and_diagnostic():
    frame = opening_orderbook_frame(symbol="000250", session="20250103")
    changed_future = frame.copy()
    frame.loc[1, COL_PRICE] = 1120.0
    frame.loc[3, COL_PRICE] = 1002.0
    changed_future.loc[1, COL_PRICE] = 1120.0
    changed_future.loc[3, COL_PRICE] = 1002.0
    changed_future.loc[changed_future.index > 3, COL_PRICE] = 1600.0
    changed_future.loc[changed_future.index > 3, COL_BID1] = 0.0
    changed_future.loc[changed_future.index > 3, COL_ASK1] = 0.0

    penalty = compute_opening_context_reward_penalty(frame, decision_second=3, action_name="market_buy")
    changed = compute_opening_context_reward_penalty(changed_future, decision_second=3, action_name="market_buy")

    assert penalty == changed
    assert penalty["total_penalty"] > 0.0
    assert penalty["diagnostics"]["overheat_entry_penalty"] > 0.0
    assert penalty["diagnostics"]["decision_second"] == 3
