from stom_rl.opening_30m_rule_filter_ablations import build_rule_filter_ablation_artifact


def test_rule_filter_ablations_emit_required_rows():
    artifact = build_rule_filter_ablation_artifact(
        full_context_return_pct=2.0,
        ablation_returns={
            "no_participant_pressure": 1.0,
            "no_orderbook_imbalance": 1.1,
            "no_orderbook_persistence": 1.2,
            "no_overheat_upper_wick": 1.3,
            "no_time_bucket": 1.4,
            "context_only": 1.5,
            "tick_only": 0.8,
            "shuffled_participant_context": 0.5,
        },
        split_hash="split123",
    )

    ids = {row["feature_set_id"] for row in artifact["ablations"]}
    assert "no_participant_pressure" in ids
    assert "no_time_bucket" in ids
    assert artifact["feature_ablation_passed"] is True
    assert artifact["table_alias"] == "rule_filter_ablations"


def test_shuffled_context_outperformance_fails_ablation():
    artifact = build_rule_filter_ablation_artifact(
        full_context_return_pct=2.0,
        ablation_returns={"shuffled_participant_context": 3.0},
        split_hash="split123",
    )

    shuffled = next(row for row in artifact["ablations"] if row["feature_set_id"] == "shuffled_participant_context")
    assert shuffled["shuffled_context"] is True
    assert artifact["feature_ablation_passed"] is False


def test_missing_required_ablation_blocks_artifact():
    artifact = build_rule_filter_ablation_artifact(
        full_context_return_pct=2.0,
        ablation_returns={"shuffled_participant_context": 1.0},
        split_hash="split123",
    )

    missing = next(row for row in artifact["ablations"] if row["feature_set_id"] == "no_participant_pressure")
    assert missing["comparison_status"] == "missing_required_ablation"
    assert missing["passed"] is False
    assert artifact["feature_ablation_passed"] is False
