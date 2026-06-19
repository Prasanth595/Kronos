from stom_rl.opening_30m_rl_candidate_gate import CandidateGateInput, evaluate_candidate_gate


def test_candidate_promotion_requires_oos_controls_ablation_and_baseline():
    passed = evaluate_candidate_gate(
        CandidateGateInput(
            candidate_id="dqn",
            split_hash="split123",
            validation_net_return_pct=1.0,
            oos_net_return_pct=3.0,
            no_trade_net_return_pct=0.0,
            buy_and_hold_net_return_pct=1.0,
            ts_imb_rule_net_return_pct=2.0,
            cost_bps=23.0,
            controls_passed=True,
            ablations_passed=True,
            trade_count=4,
            max_drawdown_pct=-1.0,
        )
    )
    failed = evaluate_candidate_gate(
        CandidateGateInput(
            candidate_id="dqn",
            split_hash="split123",
            validation_net_return_pct=1.0,
            oos_net_return_pct=1.0,
            no_trade_net_return_pct=0.0,
            buy_and_hold_net_return_pct=1.0,
            ts_imb_rule_net_return_pct=2.0,
            cost_bps=23.0,
            controls_passed=True,
            ablations_passed=True,
            trade_count=4,
            max_drawdown_pct=-1.0,
        )
    )

    assert passed["verdict"] == "GO_CANDIDATE"
    assert failed["verdict"] == "NO-GO_BASELINE"
    assert "failed_baseline:ts_imb_rule" in failed["blocking_reasons"]


def test_candidate_gate_writes_equity_curve_and_time_bucket_metrics():
    artifact = evaluate_candidate_gate(
        CandidateGateInput(
            candidate_id="ppo",
            split_hash="split123",
            validation_net_return_pct=2.0,
            oos_net_return_pct=3.0,
            no_trade_net_return_pct=0.0,
            buy_and_hold_net_return_pct=1.0,
            ts_imb_rule_net_return_pct=2.0,
            cost_bps=23.0,
            controls_passed=True,
            ablations_passed=True,
            trade_count=3,
            max_drawdown_pct=-0.5,
        )
    )

    assert artifact["equity_curve"][-1]["net_return_pct"] == 3.0
    assert artifact["time_bucket_performance"][0]["trade_count"] == 3
    assert artifact["metrics"]["oos_validation_gap_pct"] == 1.0


def test_candidate_promotion_blocks_unacceptable_drawdown():
    artifact = evaluate_candidate_gate(
        CandidateGateInput(
            candidate_id="dqn",
            split_hash="split123",
            validation_net_return_pct=1.0,
            oos_net_return_pct=3.0,
            no_trade_net_return_pct=0.0,
            buy_and_hold_net_return_pct=1.0,
            ts_imb_rule_net_return_pct=2.0,
            cost_bps=23.0,
            controls_passed=True,
            ablations_passed=True,
            trade_count=4,
            max_drawdown_pct=-20.0,
            max_drawdown_limit_pct=-10.0,
        )
    )

    assert artifact["verdict"] == "NO-GO_BASELINE"
    assert "failed_mdd" in artifact["blocking_reasons"]
