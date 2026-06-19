from stom_rl.opening_30m_rl_candidates import opening_action_contract


def test_ppo_dqn_share_discrete_opening_actions():
    contract = opening_action_contract()

    assert contract["space"] == "Discrete(2)"
    assert contract["actions"] == ["HOLD_AFTER_FIXED_ENTRY", "EXIT_LONG_MARKETABLE"]
    assert contract["policy_action_names"] == ["hold", "exit"]
    assert contract["environment_mode"] == "fixed_entry_exit_only"
    assert contract["live_order_actions"] is False
    assert contract["continuous_sizing"] is False


def test_opening_action_contract_rejects_live_or_continuous_actions():
    contract = opening_action_contract()

    assert "BROKER_ORDER" not in contract["actions"]
    assert contract["continuous_sizing"] is False
