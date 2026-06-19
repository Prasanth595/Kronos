from stom_rl.opening_30m_rl_realdata_validation import (
    RealdataGateInput,
    evaluate_realdata_candidate_gate,
)


def test_missing_oos_blocks_realdata_candidate():
    result = evaluate_realdata_candidate_gate(
        RealdataGateInput(
            candidate_net_return_pct=3.0,
            no_trade_net_return_pct=0.0,
            buy_and_hold_net_return_pct=1.0,
            ts_imb_rule_net_return_pct=2.0,
            cost_bps=23.0,
            has_oos_split=False,
            has_negative_controls=True,
            negative_controls_passed=True,
            ablations={
                "participant_pressure": True,
                "orderbook_persistence": True,
                "overheat_penalty": True,
            },
        )
    )

    assert result["verdict"] == "INCONCLUSIVE"
    assert "missing_oos_split" in result["blocking_reasons"]
    assert result["can_show_go_candidate"] is False


def test_failed_ablation_blocks_go_candidate():
    result = evaluate_realdata_candidate_gate(
        RealdataGateInput(
            candidate_net_return_pct=4.0,
            no_trade_net_return_pct=0.0,
            buy_and_hold_net_return_pct=1.0,
            ts_imb_rule_net_return_pct=2.0,
            cost_bps=23.0,
            has_oos_split=True,
            has_negative_controls=True,
            negative_controls_passed=True,
            ablations={
                "participant_pressure": True,
                "orderbook_persistence": False,
                "overheat_penalty": True,
            },
        )
    )

    assert result["verdict"] == "NO-GO"
    assert result["feature_ablation_results"]["orderbook_persistence"]["passed"] is False
    assert "failed_ablation:orderbook_persistence" in result["blocking_reasons"]


def test_candidate_must_beat_all_baselines_after_23bp():
    result = evaluate_realdata_candidate_gate(
        RealdataGateInput(
            candidate_net_return_pct=1.5,
            no_trade_net_return_pct=0.0,
            buy_and_hold_net_return_pct=1.8,
            ts_imb_rule_net_return_pct=1.2,
            cost_bps=23.0,
            has_oos_split=True,
            has_negative_controls=True,
            negative_controls_passed=True,
            ablations={
                "participant_pressure": True,
                "orderbook_persistence": True,
                "overheat_penalty": True,
            },
        )
    )

    assert result["verdict"] == "NO-GO"
    assert result["cost_bps"] == 23.0
    assert "failed_baseline:buy_and_hold" in result["blocking_reasons"]
    assert result["baseline_results"]["ts_imb_rule"]["is_reinforcement_learning"] is False
