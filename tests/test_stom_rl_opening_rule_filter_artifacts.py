import json

from stom_rl.opening_30m_rule_filter_artifacts import write_rule_filter_artifacts
from stom_rl.opening_30m_rule_filter_gate import RuleFilterGateInput, evaluate_rule_filter_gate


def test_rule_filter_artifact_writer_includes_opportunity_cost(tmp_path):
    gate = evaluate_rule_filter_gate(
        RuleFilterGateInput(
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
            max_drawdown_pct=0.5,
            skipped_opportunity_cost_pct=0.2,
        )
    )
    payload = write_rule_filter_artifacts(
        output_dir=tmp_path,
        split_manifest={"split_hash": "split123", "split_sessions": {"train": ["20250103"], "validation": ["20250106"], "oos": ["20250107"]}},
        policy={"policy_id": "p1", "actions_by_episode": {}},
        controls={"controls": []},
        ablations={"ablations": []},
        gate=gate,
        dataset_rows=[],
    )

    assert (tmp_path / "opening_rule_filter_lifecycle.json").is_file()
    assert (tmp_path / "opening_rule_filter_gate.json").is_file()
    loaded = json.loads((tmp_path / "opening_rule_filter_lifecycle.json").read_text(encoding="utf-8"))
    assert loaded["promotion_gate"]["opportunity_cost_curve"]
    assert payload["strategy_context"]["is_live_ready"] is False
