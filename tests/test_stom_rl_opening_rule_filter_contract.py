from stom_rl.opening_30m_rule_filter_contract import (
    ACTION_SKIP,
    ACTION_TAKE,
    RULE_FILTER_TABLE_ALIASES,
    VERDICT_GO_RULE_FILTER,
    RuleFilterConfig,
    rule_filter_strategy_context,
)


def test_rule_filter_contract_uses_rule_specific_labels():
    config = RuleFilterConfig()
    context = rule_filter_strategy_context()

    assert ACTION_TAKE == "TAKE"
    assert ACTION_SKIP == "SKIP"
    assert VERDICT_GO_RULE_FILTER == "GO_RULE_FILTER"
    assert config.cost_bps == 23.0
    assert config.min_oos_take_trades == 3
    assert config.primary_baseline == "ts_imb RULE baseline"
    assert context["is_reinforcement_learning"] is False
    assert context["is_live_ready"] is False
    assert "rule_filter_opportunity_cost" in RULE_FILTER_TABLE_ALIASES
