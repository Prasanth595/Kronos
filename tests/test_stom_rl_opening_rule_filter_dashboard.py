from stom_rl.opening_30m_rule_filter_artifacts import write_rule_filter_artifacts
from stom_rl.opening_30m_rule_filter_gate import RuleFilterGateInput, evaluate_rule_filter_gate
from webui.rl_dashboard_opening_tables import load_opening_json_table


def _write_run(path):
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
    write_rule_filter_artifacts(
        output_dir=path,
        split_manifest={"split_hash": "split123", "split_sessions": {"train": ["20250103"], "validation": ["20250106"], "oos": ["20250107"]}},
        policy={"policy_id": "p1", "actions_by_episode": {"a": "TAKE"}},
        controls={"controls": [{"control_type": "no_trade", "passed": True}]},
        ablations={"ablations": [{"feature_set_id": "no_participant_pressure", "passed": True}]},
        gate=gate,
        dataset_rows=[{"episode_id": "a", "split": "oos", "symbol": "000250", "feature_values": {"participant_pressure_score": 0.8}}],
    )


def test_dashboard_loads_rule_filter_tables(tmp_path):
    _write_run(tmp_path)
    for table in [
        "rule_filter_lifecycle",
        "rule_filter_splits",
        "rule_filter_controls",
        "rule_filter_ablations",
        "rule_filter_equity_curve",
        "rule_filter_time_buckets",
        "rule_filter_failure_reasons",
        "rule_filter_opportunity_cost",
        "rule_filter_context_sample",
        "rule_filter_proxy_availability",
        "rule_filter_orderbook_persistence",
    ]:
        payload = load_opening_json_table("run", tmp_path, "opening_rule_filter", table, limit=100)
        assert payload is not None, table
        assert payload["table"] == table


def test_dashboard_unknown_rule_filter_table_returns_none(tmp_path):
    _write_run(tmp_path)
    assert load_opening_json_table("run", tmp_path, "opening_rule_filter", "rule_filter_missing", limit=100) is None
