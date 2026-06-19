from stom_rl.opening_30m_rl_candidate_training import _make_env
from stom_rl.opening_30m_rl_candidates import default_candidate_configs, train_candidate_artifacts
from stom_rl.opening_30m_rl_context import OPENING_RL_CONTEXT_FEATURE_NAMES
from stom_rl.opening_30m_rl_feature_mask import feature_mask_details
from stom_rl.orderbook_sb3_adapter import OrderbookEpisode
from tests.fixtures.stom_opening_rl import opening_orderbook_frame


def test_candidate_training_does_not_fake_model_paths_when_sb3_exists():
    configs = default_candidate_configs("split123")
    artifact = train_candidate_artifacts(configs, sb3_available=True, validation_score_by_candidate={"dqn_default_seed100": 1.2})

    rows = artifact["candidates"]
    assert artifact["selection_split"] == "validation"
    assert artifact["oos_is_final_only"] is True
    assert {row["algorithm"] for row in rows} == {"dqn", "ppo"}
    assert {row["split_hash"] for row in rows} == {"split123"}
    assert {row["status"] for row in rows} == {"not_trained"}
    assert {row["model_path"] for row in rows} == {""}


def test_candidate_training_records_sb3_unavailable_without_fake_success():
    artifact = train_candidate_artifacts(default_candidate_configs("split123"), sb3_available=False)

    row = artifact["candidates"][0]
    assert row["status"] == "skipped_sb3_unavailable"
    assert row["model_path"] == ""


def test_candidate_training_env_appends_opening_context_features():
    config = default_candidate_configs("split123", feature_set_id="full_context")[0]
    frame = opening_orderbook_frame(symbol="000250", session="20250103")
    env = _make_env([OrderbookEpisode("000250_20250103", "000250", "20250103", frame)], config)

    observation, info = env.reset(seed=100)

    assert observation.shape[0] == len(info["feature_columns"])
    assert list(info["context_feature_names"]) == list(OPENING_RL_CONTEXT_FEATURE_NAMES)
    assert list(info["feature_columns"][-len(OPENING_RL_CONTEXT_FEATURE_NAMES) :]) == list(OPENING_RL_CONTEXT_FEATURE_NAMES)
    assert info["context_feature_status"] == "available"

def test_candidate_training_ablation_zeroes_appended_context_features():
    config = default_candidate_configs("split123", feature_set_id="no_participant_pressure")[0]
    frame = opening_orderbook_frame(symbol="000250", session="20250103")
    env = _make_env([OrderbookEpisode("000250_20250103", "000250", "20250103", frame)], config)

    observation, info = env.reset(seed=100)

    feature_columns = list(info["feature_columns"])
    for name in ("participant_pressure_score", "proxy_available_trade_strength"):
        assert name in info["zeroed_feature_names"]
        assert observation[feature_columns.index(name)] == 0.0
    assert "participant_pressure" not in info["unavailable_feature_groups"]


def test_candidate_training_shuffled_context_is_not_zero_ablation():
    frame = opening_orderbook_frame(symbol="000250", session="20250103")
    episode = OrderbookEpisode("000250_20250103", "000250", "20250103", frame)
    full_config = default_candidate_configs("split123", feature_set_id="full_context")[0]
    shuffled_config = default_candidate_configs("split123", feature_set_id="shuffled_participant_context")[0]
    full_env = _make_env([episode], full_config)
    shuffled_env = _make_env([episode], shuffled_config)

    full_observation, _full_info = full_env.reset(seed=100)
    shuffled_observation, shuffled_info = shuffled_env.reset(seed=100)

    feature_columns = list(shuffled_info["feature_columns"])
    participant_indices = [feature_columns.index("participant_pressure_score"), feature_columns.index("proxy_available_trade_strength")]
    orderbook_index = feature_columns.index("orderbook_persistence_score")
    assert shuffled_info["zeroed_feature_names"] == []
    assert shuffled_info["shuffled_feature_names"] == ["participant_pressure_score", "proxy_available_trade_strength"]
    assert shuffled_observation[participant_indices].tolist() != full_observation[participant_indices].tolist()
    assert shuffled_observation[orderbook_index] == full_observation[orderbook_index]


def test_feature_mask_details_include_context_feature_groups():
    details = feature_mask_details(OPENING_RL_CONTEXT_FEATURE_NAMES, "minimal_price_volume")

    assert "participant_pressure_score" in details["zeroed_feature_names"]
    assert "orderbook_persistence_score" in details["zeroed_feature_names"]
    assert "overheat_score" in details["zeroed_feature_names"]
    assert "proxy_available_foreign_net_buy" in details["zeroed_feature_names"]
