from stom_rl.opening_30m_rule_filter_contract import VERDICT_NO_GO_CONTROL
from stom_rl.opening_30m_rule_filter_controls import build_rule_filter_control_artifact


def test_rule_filter_controls_require_same_split_and_cost():
    artifact = build_rule_filter_control_artifact(
        filter_oos_net_return_pct=2.0,
        baseline_returns={"no_trade": 0.0, "buy_and_hold": 0.5, "ts_imb_rule": 1.0},
        split_hash="split123",
        cost_bps=23.0,
        shuffled_label_return_pct=-1.0,
        time_session_shuffle_return_pct=-0.5,
        randomized_feature_return_pct=-0.1,
    )

    assert artifact["negative_control_passed"] is True
    assert {row["split_hash"] for row in artifact["controls"]} == {"split123"}
    assert {row["cost_bps"] for row in artifact["controls"]} == {23.0}
    assert artifact["table_alias"] == "rule_filter_controls"


def test_shuffled_control_blocks_rule_filter():
    artifact = build_rule_filter_control_artifact(
        filter_oos_net_return_pct=2.0,
        baseline_returns={"no_trade": 0.0, "buy_and_hold": 0.5, "ts_imb_rule": 1.0},
        split_hash="split123",
        cost_bps=23.0,
        shuffled_label_return_pct=3.0,
        time_session_shuffle_return_pct=-0.5,
        randomized_feature_return_pct=-0.1,
    )

    assert artifact["negative_control_passed"] is False
    assert artifact["blocking_verdict"] == VERDICT_NO_GO_CONTROL
