from stom_rl.opening_30m_rule_filter_contract import ACTION_SKIP, ACTION_TAKE, RuleFilterConfig
from stom_rl.opening_30m_rule_filter_policy import select_rule_filter_policy


def _rows():
    base = {
        "base_action": ACTION_TAKE,
        "cost_bps": 23.0,
        "split_hash": "split123",
        "feature_values": {"participant_pressure_score": 0.8, "orderbook_persistence_score": 0.8, "overheat_score": 0.1, "time_bucket_0_10": 1.0},
    }
    return [
        base | {"episode_id": "a", "session": "20250103", "split": "train", "base_net_return_pct": 1.0, "meta_label_take": 1},
        base | {"episode_id": "b", "session": "20250106", "split": "validation", "base_net_return_pct": 1.2, "meta_label_take": 1},
        base | {"episode_id": "c", "session": "20250107", "split": "oos", "base_net_return_pct": -9.0, "meta_label_take": 0, "feature_values": {"participant_pressure_score": 0.1, "orderbook_persistence_score": 0.1, "overheat_score": 0.9, "time_bucket_0_10": 1.0}},
    ]


def test_policy_selection_uses_validation_not_oos():
    selected = select_rule_filter_policy(_rows(), config=RuleFilterConfig(min_oos_take_trades=0), split_hash="split123")
    changed = _rows()
    changed[2]["base_net_return_pct"] = 99.0
    changed_selected = select_rule_filter_policy(changed, config=RuleFilterConfig(min_oos_take_trades=0), split_hash="split123")

    assert selected["selected_thresholds"] == changed_selected["selected_thresholds"]
    assert selected["actions_by_episode"]["c"] == ACTION_SKIP
    assert selected["strategy_context"]["is_reinforcement_learning"] is False


def test_policy_marks_empty_oos_take_set_inconclusive():
    rows = _rows()
    rows[2]["base_action"] = ACTION_SKIP
    selected = select_rule_filter_policy(rows, config=RuleFilterConfig(min_oos_take_trades=1), split_hash="split123")

    assert selected["oos_metrics"]["take_count"] == 0
    assert selected["verdict_hint"] == "INCONCLUSIVE"


def test_minimal_ts_imb_feature_set_ignores_context_scores():
    rows = _rows()
    rows[1]["feature_values"] = {
        "participant_pressure_score": 0.0,
        "orderbook_persistence_score": 0.0,
        "overheat_score": 1.0,
        "time_bucket_0_10": 0.0,
    }
    rows[2]["feature_values"] = {
        "participant_pressure_score": 1.0,
        "orderbook_persistence_score": 1.0,
        "overheat_score": 0.0,
        "time_bucket_0_10": 1.0,
    }

    selected = select_rule_filter_policy(
        rows,
        config=RuleFilterConfig(feature_set_id="minimal_ts_imb", min_oos_take_trades=0),
        split_hash="split123",
    )

    assert selected["feature_set_id"] == "minimal_ts_imb"
    assert selected["actions_by_episode"]["b"] == ACTION_TAKE
    assert selected["actions_by_episode"]["c"] == ACTION_TAKE


def test_time_bucket_only_feature_set_ignores_participant_orderbook_and_overheat():
    rows = _rows()
    rows[1]["base_net_return_pct"] = -1.2
    rows[1]["feature_values"] = {
        "participant_pressure_score": 1.0,
        "orderbook_persistence_score": 1.0,
        "overheat_score": 0.0,
        "time_bucket_0_10": 0.0,
    }
    rows[2]["feature_values"] = {
        "participant_pressure_score": 0.0,
        "orderbook_persistence_score": 0.0,
        "overheat_score": 1.0,
        "time_bucket_0_10": 1.0,
    }

    selected = select_rule_filter_policy(
        rows,
        config=RuleFilterConfig(feature_set_id="time_bucket_only", min_oos_take_trades=0),
        split_hash="split123",
    )

    assert selected["feature_set_id"] == "time_bucket_only"
    assert selected["actions_by_episode"]["b"] == ACTION_SKIP
    assert selected["actions_by_episode"]["c"] == ACTION_TAKE
