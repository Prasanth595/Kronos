from stom_rl.opening_30m_rl_leaderboard import evaluate_opening_workflow_leaderboard_row


def test_opening_workflow_cost_gate_uses_23bp_and_negative_control_status():
    row = evaluate_opening_workflow_leaderboard_row(
        run_id="opening_fixture",
        rl_mean_return_pct=0.8,
        baseline_delta_inputs={"no_trade": 0.0, "buy_and_hold": 0.7, "ts_imb_same_decision_tp5_sl1_time": 0.9},
        controls_payload={"final_verdict": "NO-GO", "negative_control_blocked_go": True},
        target_cost_bps=23.0,
        trade_count=3,
        max_drawdown_pct=-1.0,
    )

    assert row["target_cost_bps"] == 23.0
    assert row["negative_control_blocked_go"] is True
    assert row["passes_cost_gate"] is False
    assert row["decision"] == "NO-GO"
    assert row["below_rule_baseline"] is True


def test_opening_leaderboard_keeps_underperforming_rl_below_rule_baseline():
    row = evaluate_opening_workflow_leaderboard_row(
        run_id="opening_underperformer",
        rl_mean_return_pct=0.2,
        baseline_delta_inputs={"no_trade": 0.0, "buy_and_hold": 0.4, "ts_imb_same_decision_tp5_sl1_time": 0.6},
        controls_payload={"final_verdict": "GO_CANDIDATE", "negative_control_blocked_go": False},
        target_cost_bps=23.0,
        trade_count=4,
        max_drawdown_pct=-1.0,
    )

    assert row["baseline_policy"] == "ts_imb_same_decision_tp5_sl1_time"
    assert row["baseline_delta_pct"] < 0.0
    assert row["passes_cost_gate"] is False
    assert row["decision"] == "below_baseline"
