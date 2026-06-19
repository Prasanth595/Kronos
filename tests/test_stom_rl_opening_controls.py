import json

from stom_rl.opening_30m_rl_controls import apply_opening_negative_controls, write_opening_controls_artifact


def test_opening_negative_control_blocks_primary_go(tmp_path):
    payload = write_opening_controls_artifact(
        output_dir=tmp_path / "controls",
        primary_verdict="GO_CANDIDATE",
        controls=[
            {"control_type": "shuffled_participant_context", "verdict": "GO_CANDIDATE", "seed": 7},
            {"control_type": "random_policy", "verdict": "NO-GO", "seed": 7},
        ],
        seed=7,
    )

    assert payload["artifact_type"] == "opening_30m_negative_controls"
    assert payload["primary_verdict_before_controls"] == "GO_CANDIDATE"
    assert payload["final_verdict"] == "NO-GO"
    assert payload["negative_control_blocked_go"] is True
    assert payload["blocked_reason"] == "negative_control_not_no_go"
    assert payload["controls"][0]["seed"] == 7
    saved = json.loads((tmp_path / "controls" / "opening_negative_controls_summary.json").read_text(encoding="utf-8"))
    assert saved == payload


def test_opening_negative_controls_preserve_candidate_when_all_no_go():
    payload = apply_opening_negative_controls(
        primary_verdict="GO_CANDIDATE",
        controls=[
            {"control_type": "shuffled_features", "verdict": "NO-GO", "seed": 11},
            {"control_type": "hold_policy", "verdict": "NO-GO", "seed": 11},
            {"control_type": "ts_imb_rule_baseline", "verdict": "NO-GO", "seed": 11},
        ],
        seed=11,
    )

    assert payload["final_verdict"] == "GO_CANDIDATE"
    assert payload["negative_control_passed"] is True
    assert payload["negative_control_blocked_go"] is False
    assert payload["blocked_reason"] == ""
    assert {row["control_type"] for row in payload["controls"]} == {
        "shuffled_features",
        "hold_policy",
        "ts_imb_rule_baseline",
    }
