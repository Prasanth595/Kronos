from stom_rl.opening_30m_rl_candidate_diagnostics import ablation_rows
from stom_rl.opening_30m_rl_candidate_gate import REQUIRED_ABLATIONS, build_ablation_artifact
from stom_rl.opening_30m_rl_candidate_smoke import _ablation_configs
from stom_rl.opening_30m_rl_candidates import default_candidate_configs
from stom_rl.opening_30m_rl_candidate_training import feature_mask_details


def test_feature_ablation_artifact_compares_required_feature_groups():
    rows = [
        {"feature_set_id": "full", "removed_feature_groups": [], "oos_net_return_pct": 3.0, "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": 0.0},
        {"feature_set_id": "no_participant", "removed_feature_groups": ["participant"], "oos_net_return_pct": 2.0, "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": -1.0},
        {"feature_set_id": "no_orderbook", "removed_feature_groups": ["hoga"], "oos_net_return_pct": 1.5, "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": -1.5},
        {"feature_set_id": "no_overheat", "removed_feature_groups": ["overheat"], "oos_net_return_pct": 1.4, "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": -1.6},
        {"feature_set_id": "minimal_price_volume", "removed_feature_groups": ["participant", "hoga"], "oos_net_return_pct": 0.5, "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": -2.5},
        {"feature_set_id": "shuffled_participant_context", "removed_feature_groups": ["participant_pressure"], "oos_net_return_pct": 0.3, "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": -2.7, "shuffled_feature_names": ["participant_pressure_score"]},
    ]

    artifact = build_ablation_artifact(rows, split_hash="split123", candidate_id="dqn")

    assert artifact["feature_ablation_passed"] is True
    assert {row["feature_set_id"] for row in artifact["ablations"]} >= {"full_context", "no_orderbook_imbalance"}
    assert {row["candidate_id"] for row in artifact["ablations"]} == {"dqn"}



def test_ablation_artifact_normalizes_legacy_rows_to_canonical_ids():
    artifact = build_ablation_artifact(
        [
            {"feature_set_id": "full", "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": 0.0},
            {"feature_set_id": "no_participant", "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": -1.0},
            {"feature_set_id": "no_orderbook", "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": -1.0},
            {"feature_set_id": "no_overheat", "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": -1.0},
            {"feature_set_id": "minimal_price_volume", "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": -1.0},
            {"feature_set_id": "shuffled_participant_context", "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": -1.0, "shuffled_feature_names": ["participant_pressure_score"]},
        ],
        split_hash="split123",
    )

    assert tuple(row["feature_set_id"] for row in artifact["ablations"]) == REQUIRED_ABLATIONS
    assert artifact["feature_ablation_passed"] is True

def test_missing_required_ablation_blocks_go_candidate():
    artifact = build_ablation_artifact([{"feature_set_id": "full", "passed": True}], split_hash="split123")

    assert artifact["feature_ablation_passed"] is False
    assert artifact["verdict"] == "INCONCLUSIVE"


def test_candidate_ablation_filters_other_candidate_rows():
    artifact = build_ablation_artifact(
        [
            {"candidate_id": "other", "feature_set_id": "full", "passed": True},
            {"candidate_id": "dqn", "feature_set_id": "full", "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": 0.0},
        ],
        split_hash="split123",
        candidate_id="dqn",
    )

    full = next(row for row in artifact["ablations"] if row["feature_set_id"] == "full_context")
    assert full["candidate_id"] == "dqn"
    assert artifact["feature_ablation_passed"] is False


def test_feature_absent_ablation_is_explicit_not_applicable():
    artifact = build_ablation_artifact(
        [
            {
                "candidate_id": "dqn",
                "feature_set_id": "full",
                "passed": True,
                "comparison_status": "compared_to_full",
                "evaluation_source": "trained_feature_mask_candidate",
                "delta_vs_full_oos_pct": 0.0,
            },
            {
                "candidate_id": "dqn",
                "feature_set_id": "no_participant",
                "passed": True,
                "comparison_status": "not_applicable_feature_absent",
                "applicable": False,
                "unavailable_feature_groups": ["participant"],
                "evaluation_source": "trained_feature_mask_candidate",
            },
            {"candidate_id": "dqn", "feature_set_id": "no_orderbook", "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": -1.0},
            {"candidate_id": "dqn", "feature_set_id": "no_overheat", "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": -1.0},
            {"candidate_id": "dqn", "feature_set_id": "minimal_price_volume", "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": -1.0},
            {"candidate_id": "dqn", "feature_set_id": "shuffled_participant_context", "passed": True, "evaluation_source": "trained_feature_mask_candidate", "comparison_status": "compared_to_full", "delta_vs_full_oos_pct": -1.0, "shuffled_feature_names": ["participant_pressure_score"]},
        ],
        split_hash="split123",
        candidate_id="dqn",
    )

    row = next(row for row in artifact["ablations"] if row["feature_set_id"] == "no_participant_pressure")
    assert row["applicable"] is False
    assert row["comparison_status"] == "not_applicable_feature_absent"
    assert artifact["feature_ablation_passed"] is True


def test_feature_mask_details_identify_absent_participant_group():
    details = feature_mask_details(["ret_open", "book_imb_l1"], "no_participant")

    assert details["feature_set_id"] == "no_participant_pressure"
    assert details["removed_feature_groups"] == ["participant_pressure"]
    assert details["zeroed_feature_names"] == []
    assert details["unavailable_feature_groups"] == ["participant_pressure"]


def test_ablation_rows_without_comparison_metadata_do_not_pass():
    artifact = build_ablation_artifact(
        [
            {"feature_set_id": "full", "passed": True},
            {"feature_set_id": "no_participant", "passed": True},
            {"feature_set_id": "no_orderbook", "passed": True},
            {"feature_set_id": "no_overheat", "passed": True},
            {"feature_set_id": "minimal_price_volume", "passed": True},
        ],
        split_hash="split123",
    )

    assert artifact["feature_ablation_passed"] is False
    assert all(row["passed"] is False for row in artifact["ablations"])






def test_ablation_configs_use_canonical_execution_feature_sets():
    base = default_candidate_configs("split123", feature_set_id="full_context")[0]
    configs = _ablation_configs([base], {"candidate_id": base.candidate_id})

    assert tuple(config.feature_set_id for config in configs) == REQUIRED_ABLATIONS


def test_ablation_rows_compare_against_canonical_full_context():
    rows = ablation_rows(
        {"candidate_id": "dqn"},
        {
            "candidates": [
                {"candidate_id": "dqn_full", "feature_set_id": "full_context", "status": "trained", "oos_net_return_pct": 1.0, "model_path": "model.zip"},
                {"candidate_id": "dqn_no_ob", "feature_set_id": "no_orderbook_imbalance", "status": "trained", "oos_net_return_pct": 0.5, "model_path": "model.zip"},
            ]
        },
    )

    full = next(row for row in rows if row["feature_set_id"] == "full_context")
    no_ob = next(row for row in rows if row["feature_set_id"] == "no_orderbook_imbalance")
    assert full["delta_vs_full_oos_pct"] == 0.0
    assert no_ob["delta_vs_full_oos_pct"] == -0.5

def test_shuffled_participant_context_must_not_outperform_full_context():
    base = {
        "candidate_id": "dqn",
        "passed": True,
        "evaluation_source": "trained_feature_mask_candidate",
        "comparison_status": "compared_to_full",
    }
    rows = [
        {**base, "feature_set_id": "full_context", "oos_net_return_pct": 1.0, "delta_vs_full_oos_pct": 0.0},
        {**base, "feature_set_id": "no_participant_pressure", "oos_net_return_pct": 0.8, "delta_vs_full_oos_pct": -0.2, "zeroed_feature_names": ["participant_pressure_score"]},
        {**base, "feature_set_id": "no_orderbook_imbalance", "oos_net_return_pct": 0.8, "delta_vs_full_oos_pct": -0.2, "zeroed_feature_names": ["proxy_available_bid_depth_imbalance"]},
        {**base, "feature_set_id": "no_orderbook_persistence", "oos_net_return_pct": 0.8, "delta_vs_full_oos_pct": -0.2, "zeroed_feature_names": ["orderbook_persistence_score"]},
        {**base, "feature_set_id": "no_overheat_upper_wick", "oos_net_return_pct": 0.8, "delta_vs_full_oos_pct": -0.2, "zeroed_feature_names": ["overheat_score"]},
        {**base, "feature_set_id": "minimal_price_volume", "oos_net_return_pct": 0.8, "delta_vs_full_oos_pct": -0.2, "zeroed_feature_names": ["participant_pressure_score", "orderbook_persistence_score"]},
        {**base, "feature_set_id": "shuffled_participant_context", "oos_net_return_pct": 1.2, "delta_vs_full_oos_pct": 0.2, "shuffled_feature_names": ["participant_pressure_score"]},
    ]

    artifact = build_ablation_artifact(rows, split_hash="split123", candidate_id="dqn")

    shuffled = next(row for row in artifact["ablations"] if row["feature_set_id"] == "shuffled_participant_context")
    assert shuffled["passed"] is False
    assert artifact["feature_ablation_passed"] is False
