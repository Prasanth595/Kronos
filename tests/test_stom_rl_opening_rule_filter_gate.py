from stom_rl.opening_30m_rule_filter_contract import (
    VERDICT_GO_RULE_FILTER,
    VERDICT_NO_GO_ABLATION,
    VERDICT_NO_GO_BASELINE,
    VERDICT_NO_GO_CONTROL,
)
from stom_rl.opening_30m_rule_filter_gate import RuleFilterGateInput, evaluate_rule_filter_gate


def _gate(**overrides):
    base = dict(
        split_hash="split123",
        cost_bps=23.0,
        validation_net_return_pct=2.0,
        oos_net_return_pct=3.0,
        no_trade_net_return_pct=0.0,
        buy_and_hold_net_return_pct=1.0,
        ts_imb_rule_net_return_pct=1.5,
        controls_passed=True,
        ablations_passed=True,
        oos_take_count=4,
        min_oos_take_count=3,
        max_drawdown_pct=0.5,
        max_allowed_drawdown_pct=5.0,
        skipped_opportunity_cost_pct=0.2,
    )
    base.update(overrides)
    return RuleFilterGateInput(**base)


def test_rule_filter_gate_verdicts_are_explicit():
    assert evaluate_rule_filter_gate(_gate())["verdict"] == VERDICT_GO_RULE_FILTER
    assert evaluate_rule_filter_gate(_gate(oos_net_return_pct=1.0))["verdict"] == VERDICT_NO_GO_BASELINE
    assert evaluate_rule_filter_gate(_gate(controls_passed=False))["verdict"] == VERDICT_NO_GO_CONTROL
    assert evaluate_rule_filter_gate(_gate(ablations_passed=False))["verdict"] == VERDICT_NO_GO_ABLATION


def test_rule_filter_gate_blocks_non_default_cost():
    artifact = evaluate_rule_filter_gate(_gate(cost_bps=0.0))

    assert artifact["verdict"] == VERDICT_NO_GO_CONTROL
    assert "failed_cost:expected_23bp" in artifact["blocking_reasons"]


def test_rule_filter_gate_writes_opportunity_cost_curve():
    artifact = evaluate_rule_filter_gate(_gate())
    assert artifact["equity_curve"][-1]["net_return_pct"] == 3.0
    assert artifact["opportunity_cost_curve"][-1]["skipped_opportunity_cost_pct"] == 0.2
    assert artifact["strategy_context"]["is_reinforcement_learning"] is False


def test_rule_filter_gate_blocks_insufficient_oos_trades_and_drawdown():
    low_trade = evaluate_rule_filter_gate(_gate(oos_take_count=1, min_oos_take_count=3))
    drawdown = evaluate_rule_filter_gate(_gate(max_drawdown_pct=6.0, max_allowed_drawdown_pct=5.0))

    assert low_trade["verdict"] != VERDICT_GO_RULE_FILTER
    assert "insufficient_oos_take_trades" in low_trade["blocking_reasons"]
    assert drawdown["verdict"] != VERDICT_GO_RULE_FILTER
    assert "failed_risk:max_drawdown" in drawdown["blocking_reasons"]
