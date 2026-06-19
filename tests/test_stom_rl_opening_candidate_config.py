from stom_rl.opening_30m_rl_candidates import (
    CandidateConfig,
    CandidateConfigError,
    CandidateAlgorithm,
    candidate_config_artifact,
    default_candidate_configs,
    validate_candidate_config,
)


def test_candidate_config_registry_has_dqn_and_ppo_defaults():
    configs = default_candidate_configs("split123")
    artifact = candidate_config_artifact(configs)

    algorithms = {row["algorithm"] for row in artifact["candidates"]}
    assert algorithms == {"dqn", "ppo"}
    assert artifact["candidates"][0]["split_hash"] == "split123"
    assert artifact["candidates"][0]["cost_bps"] == 23.0


def test_candidate_config_rejects_oos_tuning():
    config = CandidateConfig(
        "bad",
        CandidateAlgorithm.DQN,
        100,
        64,
        "split123",
        "full",
        use_oos_for_selection=True,
    )

    try:
        validate_candidate_config(config)
    except CandidateConfigError as exc:
        assert "OOS" in str(exc)
    else:
        raise AssertionError("OOS tuning should fail")
