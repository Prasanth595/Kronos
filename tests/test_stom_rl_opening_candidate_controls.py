from stom_rl.opening_30m_rl_candidate_gate import build_control_artifact


def test_candidate_controls_use_same_split_and_23bp_cost():
    artifact = build_control_artifact(
        [
            {"control_type": "no_trade", "verdict": "NO-GO", "evaluation_source": "baseline_same_split"},
            {"control_type": "buy_and_hold", "verdict": "NO-GO", "evaluation_source": "baseline_same_split"},
            {"control_type": "ts_imb_rule", "verdict": "NO-GO", "evaluation_source": "baseline_same_split"},
            {"control_type": "random_policy", "verdict": "NO-GO", "evaluation_source": "policy_eval_oos", "eval_log_path": "random.json"},
            {"control_type": "label_shuffle", "verdict": "NO-GO", "evaluation_source": "label_shuffle_eval_oos", "eval_log_path": "label.json"},
            {
                "control_type": "time_session_shuffle",
                "verdict": "NO-GO",
                "evaluation_source": "time_session_shuffle_eval_oos",
                "eval_log_path": "time.json",
            },
        ],
        split_hash="split123",
        cost_bps=23.0,
    )

    assert artifact["negative_control_passed"] is True
    assert {row["split_hash"] for row in artifact["controls"]} == {"split123"}
    assert {row["cost_bps"] for row in artifact["controls"]} == {23.0}


def test_missing_or_failed_shuffle_controls_block_candidate():
    artifact = build_control_artifact(
        [{"control_type": "label_shuffle", "verdict": "GO_CANDIDATE"}],
        split_hash="split123",
    )

    assert artifact["negative_control_passed"] is False
    assert artifact["verdict"] == "INCONCLUSIVE"


def test_proxy_generated_control_rows_do_not_pass():
    artifact = build_control_artifact(
        [
            {
                "control_type": "random_policy",
                "verdict": "NO-GO",
                "evaluation_source": "same_split_baseline_or_shuffle_proxy",
            }
        ],
        split_hash="split123",
    )

    random_policy = next(row for row in artifact["controls"] if row["control_type"] == "random_policy")
    assert random_policy["passed"] is False
    assert artifact["negative_control_passed"] is False
