import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

import pytest
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stom_rl.daily_portfolio_env import (  # noqa: E402
    FILL_ASSUMPTION,
    DailyPortfolioEnv,
    build_env_inspection,
    OBSERVATION_MODE_ACTION_INDUCTION_V2,
    build_observation_manifest,
    candidates_by_date,
    environment_contract,
    write_env_inspection_artifacts,
    validate_observation_manifest,
)


def _candidate_rows():
    return [
        {"date": "2024-01-01", "code": "20", "split": "train", "score_supervised_linear_ranker": 0.9, "future_return_1d": 0.01},
        {"date": "2024-01-01", "code": "000030", "split": "train", "score_supervised_linear_ranker": 0.5, "future_return_1d": -0.01},
        {"date": "2024-01-02", "code": "000020", "split": "train", "score_supervised_linear_ranker": 0.8, "future_return_1d": 0.02},
        {"date": "2024-01-02", "code": "000040", "split": "train", "score_supervised_linear_ranker": 0.7, "future_return_1d": 0.00},
        {"date": "2024-01-03", "code": "000020", "split": "train", "score_supervised_linear_ranker": 0.3, "future_return_1d": -0.01},
    ]


def test_candidates_preserve_leading_zero_codes_and_limit():
    grouped = candidates_by_date(_candidate_rows(), score_column="score_supervised_linear_ranker", candidate_limit=1)
    assert grouped["2024-01-01"][0].code == "000020"
    assert len(grouped["2024-01-01"]) == 1


def test_action_masks_invalid_action_and_reward_breakdown():
    grouped = candidates_by_date(_candidate_rows(), score_column="score_supervised_linear_ranker", candidate_limit=2)
    env = DailyPortfolioEnv(grouped, max_positions=2)
    assert env.action_mask() == [True, True, False, False, False]
    assert env.action_mask_details()["hold"]["reason"] == "always_valid_no_trade_or_hold"
    assert env.action_mask_details()["add"]["reason"] == "blocked_no_position"

    _state, reward, done, info = env.step(1)
    assert done is False
    assert info["action"] == "buy"
    assert info["requested_action"] == "buy"
    assert info["executed_action"] == "buy"
    assert info["positions"] == ["000020"]
    assert info["turnover"] > 0
    assert info["cost"] > 0
    assert "exposure_penalty" in info
    assert "drawdown_penalty" in info
    assert "churn_penalty" in info
    assert info["fill_assumption"] == FILL_ASSUMPTION
    assert info["reward_components"]["turnover_cost"] == info["cost"]
    assert info["net_return_after_cost"] == pytest.approx(info["gross_return"] - info["cost"])
    assert info["reward_components"]["net_return_after_cost"] == info["net_return_after_cost"]
    assert info["action_mask"]["buy"] is True
    assert reward == info["reward"]

    assert env.action_mask() == [True, False, True, True, False]
    _state, _reward, _done, invalid_info = env.step(4)
    assert invalid_info["invalid_action"] is True
    assert invalid_info["action"] == "hold"
    assert invalid_info["requested_action"] == "reduce"
    assert invalid_info["executed_action"] == "hold"
    assert invalid_info["invalid_action_reason"] == "blocked_requires_multiple_positions"
    assert invalid_info["action_mask_reasons"]["reduce"] == "blocked_requires_multiple_positions"
    assert invalid_info["invalid_action_penalty"] > 0
    assert env.invalid_actions == 1
    env.reset()
    assert env.state() == (0, 1)
    assert env.positions == []
    assert env.invalid_actions == 0
    assert env.current_drawdown == 0.0

def test_no_trade_hold_is_explicit_zero_cost_control():
    grouped = candidates_by_date(_candidate_rows(), score_column="score_supervised_linear_ranker", candidate_limit=2)
    env = DailyPortfolioEnv(grouped, max_positions=2)

    _state, reward, _done, info = env.step(0)

    assert info["requested_action"] == "hold"
    assert info["executed_action"] == "hold"
    assert info["no_trade_action"] is True
    assert info["positions"] == []
    assert info["gross_return"] == 0.0
    assert info["cost"] == 0.0
    assert info["net_return_after_cost"] == 0.0
    assert info["reward_components"]["no_trade_hold_reward"] == 0.0
    assert reward == pytest.approx(
        -info["exposure_penalty"]
        - info["concentration_penalty"]
        - info["invalid_action_penalty"]
        - info["churn_penalty"]
        - info["drawdown_penalty"]
        + info["no_trade_hold_reward"]
    )

def test_unknown_action_is_reported_and_penalized():
    grouped = candidates_by_date(_candidate_rows(), score_column="score_supervised_linear_ranker", candidate_limit=2)
    env = DailyPortfolioEnv(grouped, max_positions=2)

    _state, _reward, _done, info = env.step(99)

    assert info["requested_action"] == "unknown"
    assert info["executed_action"] == "hold"
    assert info["invalid_action"] is True
    assert info["invalid_action_reason"] == "unknown_action"
    assert info["invalid_action_penalty"] > 0
    assert env.invalid_actions == 1

def test_reward_formula_and_drawdown_penalty_are_explicit():
    rows = [
        {"date": "2024-03-01", "code": "000020", "split": "train", "score_supervised_linear_ranker": 1.0, "future_return_1d": 0.10},
        {"date": "2024-03-02", "code": "000020", "split": "train", "score_supervised_linear_ranker": 1.0, "future_return_1d": -0.20},
    ]
    grouped = candidates_by_date(rows, score_column="score_supervised_linear_ranker", candidate_limit=1)
    env = DailyPortfolioEnv(grouped, max_positions=1, drawdown_penalty=0.5, churn_penalty=0.001)
    _state, _reward, _done, first = env.step(1)
    components = first["reward_components"]
    assert first["net_return_after_cost"] == pytest.approx(
        components["daily_nav_return"] - components["turnover_cost"]
    )
    assert first["reward"] == pytest.approx(
        components["net_return_after_cost"]
        - components["exposure_penalty"]
        - components["concentration_penalty"]
        - components["invalid_action_penalty"]
        - components["churn_penalty"]
        - components["drawdown_penalty"]
        + components["no_trade_hold_reward"]
    )
    _state, _reward, _done, second = env.step(0)
    second_components = second["reward_components"]
    assert second_components["drawdown_penalty"] > 0
    assert second["current_drawdown"] < 0
    assert second["reward"] == pytest.approx(
        second_components["net_return_after_cost"]
        - second_components["exposure_penalty"]
        - second_components["concentration_penalty"]
        - second_components["invalid_action_penalty"]
        - second_components["churn_penalty"]
        - second_components["drawdown_penalty"]
        + second_components["no_trade_hold_reward"]
    )


def test_state_and_mask_do_not_expose_future_return_labels():
    base_rows = [
        {"date": "2024-02-01", "code": "000020", "split": "train", "score_supervised_linear_ranker": 1.0, "future_return_1d": 0.50},
        {"date": "2024-02-02", "code": "000020", "split": "train", "score_supervised_linear_ranker": 1.0, "future_return_1d": -0.50},
    ]
    grouped = candidates_by_date(base_rows, score_column="score_supervised_linear_ranker", candidate_limit=1)
    env = DailyPortfolioEnv(grouped, max_positions=1)
    assert env.state() == (0, 1)
    assert env.action_mask() == [True, True, False, False, False]
    _state, _reward, _done, info = env.step(1)
    assert info["gross_return"] == 0.50
    assert environment_contract()["state"]["lookahead_policy"].startswith("state uses current candidate scores")

    missing_label_rows = [
        {"date": "2024-02-01", "code": "000999", "split": "train", "score_supervised_linear_ranker": 2.0},
        {"date": "2024-02-01", "code": "000020", "split": "train", "score_supervised_linear_ranker": 1.0, "future_return_1d": 0.50},
    ]
    grouped_missing = candidates_by_date(missing_label_rows, score_column="score_supervised_linear_ranker", candidate_limit=2)
    assert grouped_missing["2024-02-01"][0].code == "000999"
    env_missing = DailyPortfolioEnv(grouped_missing, max_positions=2)
    assert env_missing.state() == (0, 1)
    assert env_missing.action_mask() == [True, True, False, False, False]
    _state, _reward, _done, missing_info = env_missing.step(1)
    assert missing_info["positions"] == ["000999"]
    assert missing_info["missing_reward_label_count"] == 1
    assert missing_info["gross_return"] == 0.0
def test_action_induction_v2_state_uses_causal_buckets_without_current_label_leakage():
    base_rows = [
        {"date": "2024-02-01", "code": "000020", "split": "train", "score_supervised_linear_ranker": 0.010, "future_return_1d": 0.02},
        {"date": "2024-02-01", "code": "000030", "split": "train", "score_supervised_linear_ranker": 0.004, "future_return_1d": -0.01},
        {"date": "2024-02-02", "code": "000020", "split": "train", "score_supervised_linear_ranker": 0.012, "future_return_1d": 0.50},
        {"date": "2024-02-02", "code": "000030", "split": "train", "score_supervised_linear_ranker": 0.002, "future_return_1d": -0.50},
    ]
    changed_current_label_rows = [
        {**row, "future_return_1d": (-0.50 if row["code"] == "000020" else 0.50)}
        if row["date"] == "2024-02-02"
        else dict(row)
        for row in base_rows
    ]

    grouped = candidates_by_date(base_rows, score_column="score_supervised_linear_ranker", candidate_limit=2)
    changed_grouped = candidates_by_date(changed_current_label_rows, score_column="score_supervised_linear_ranker", candidate_limit=2)
    env = DailyPortfolioEnv(grouped, max_positions=2, observation_mode=OBSERVATION_MODE_ACTION_INDUCTION_V2)
    changed_env = DailyPortfolioEnv(changed_grouped, max_positions=2, observation_mode=OBSERVATION_MODE_ACTION_INDUCTION_V2)
    env.step(0)
    changed_env.step(0)

    assert env.state() == changed_env.state()
    details = env.state_details()
    assert len(env.state()) == 6
    assert details["score_margin_bucket"] > 0
    assert details["candidate_count_bucket"] == 2
    assert details["d3_confidence_bucket"] > 0

    manifest = build_observation_manifest(
        max_positions=2,
        score_column="score_supervised_linear_ranker",
        candidate_limit=2,
        observation_mode=OBSERVATION_MODE_ACTION_INDUCTION_V2,
        action_prior_mode="entry_bias_v1",
        action_prior_strength=0.0005,
    )
    report = validate_observation_manifest(manifest)
    assert report["status"] == "PASS"
    assert manifest["action_induction_v2"]["enabled"] is True
    assert "future_return_1d" not in report["observation_fields"]
    assert {"score_margin_bucket", "candidate_count_bucket", "recent_score_volatility_bucket", "d3_confidence_bucket"} <= set(
        report["observation_fields"]
    )


def test_observation_manifest_covers_required_d4_state_gate():
    manifest = build_observation_manifest(max_positions=3, score_column="score_supervised_linear_ranker", candidate_limit=2)
    report = validate_observation_manifest(manifest)

    assert report["status"] == "PASS"
    assert manifest["gate"] == "D4_OBSERVATION_STATE_MANIFEST"
    assert manifest["model_build_allowed"] is False
    assert manifest["go_summary_allowed"] is False
    assert manifest["reward_action_telemetry_sufficient_for_d4"] is False
    assert manifest["cash_exposure"]["exposure_formula"] == "position_count / max_positions"
    assert manifest["holdings_identity"]["leading_zero_policy"].startswith("zfill(6)")
    assert manifest["candidate_rank_score_features"]["score_column"] == "score_supervised_linear_ranker"
    assert manifest["horizon_alignment"]["reward_label"] == "future_return_1d"
    assert manifest["frozen_d3_comparison"]["required"] is True
    assert {"no_trade_cash", "shuffle_control", "supervised_linear_ranker"} <= set(
        manifest["frozen_d3_comparison"]["required_baselines"]
    )
    assert "reason_fields" in manifest["action_mask_semantics"]
    assert "future_return_1d" not in report["observation_fields"]

    missing_section = dict(manifest)
    missing_section.pop("cash_exposure")
    assert validate_observation_manifest(missing_section)["status"] == "FAIL"

    leaky_manifest = {
        **manifest,
        "observation_fields": [*manifest["observation_fields"], {"name": "future_return_1d"}],
    }
    leaky_report = validate_observation_manifest(leaky_manifest)
    assert leaky_report["status"] == "FAIL"
    assert leaky_report["future_label_fields"] == ["future_return_1d"]

    failing_check_manifest = {
        **manifest,
        "leakage_checks": [
            {**check, "status": "FAIL"} if check["check"] == "future_label_availability_not_candidate_filter" else check
            for check in manifest["leakage_checks"]
        ],
    }
    failing_check_report = validate_observation_manifest(failing_check_manifest)
    assert failing_check_report["status"] == "FAIL"
    assert failing_check_report["failing_leakage_checks"] == ["future_label_availability_not_candidate_filter"]

    missing_check_manifest = {
        **manifest,
        "leakage_checks": [
            check for check in manifest["leakage_checks"] if check["check"] != "future_label_availability_not_candidate_filter"
        ],
    }
    missing_check_report = validate_observation_manifest(missing_check_manifest)
    assert missing_check_report["status"] == "FAIL"
    assert missing_check_report["missing_leakage_checks"] == ["future_label_availability_not_candidate_filter"]

    duplicate_check_manifest = {
        **manifest,
        "leakage_checks": [
            *manifest["leakage_checks"],
            {"check": "future_label_availability_not_candidate_filter", "status": "FAIL"},
        ],
    }
    duplicate_check_report = validate_observation_manifest(duplicate_check_manifest)
    assert duplicate_check_report["status"] == "FAIL"
    assert duplicate_check_report["duplicate_leakage_checks"] == ["future_label_availability_not_candidate_filter"]
    assert duplicate_check_report["failing_leakage_checks"] == ["future_label_availability_not_candidate_filter"]


def test_env_inspection_artifacts_document_contract_and_reject_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import stom_rl.daily_portfolio_env as portfolio_env

    grouped = candidates_by_date(_candidate_rows(), score_column="score_supervised_linear_ranker", candidate_limit=2)
    inspection = build_env_inspection(grouped, max_positions=2, scripted_actions=[1, 2, 4, 3])
    manifest = inspection["env_manifest"]
    assert manifest["status"] == "RESEARCH_ONLY"
    assert manifest["fill_assumption"] == FILL_ASSUMPTION
    assert manifest["cost_round_trip_bp"] == 23
    assert manifest["model_build_allowed"] is False
    assert "drawdown_penalty" in manifest["reward_components"]
    assert "net_return_after_cost" in manifest["reward_components"]
    assert "no_trade_hold_reward" in manifest["reward_components"]
    assert manifest["observation_manifest_validation"]["status"] == "PASS"
    assert manifest["observation_manifest"]["reward_action_telemetry_sufficient_for_d4"] is False
    assert inspection["reward_breakdown"]
    assert inspection["action_masks"][0]["mask_buy"] is True
    assert "mask_reason_hold" in inspection["action_masks"][0]
    assert inspection["action_masks"][0]["mask_reason_hold"] == "always_valid_no_trade_or_hold"
    assert {row["code"] for row in inspection["positions"]} <= {"000020", "000030", "000040"}
    assert inspection["state_observations"]
    assert inspection["state_observations"][0]["cash_fraction"] == 1.0
    assert inspection["state_observations"][0]["exposure_fraction"] == 0.0
    assert inspection["state_observations"][0]["future_label_exposed"] is False
    assert "top_candidate_reward_label_available" in inspection["state_observations"][0]

    root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_portfolio_env"
    monkeypatch.setattr(portfolio_env, "DEFAULT_ENV_INSPECTION_ROOT", root)
    written = write_env_inspection_artifacts(inspection, run_id="env_unit", artifact_root=root)
    assert Path(written["env_manifest_path"]).exists()
    assert Path(written["observation_manifest_path"]).exists()
    assert Path(written["reward_breakdown_path"]).exists()
    assert Path(written["action_masks_path"]).exists()
    assert Path(written["positions_path"]).exists()
    assert Path(written["state_observations_path"]).exists()
    on_disk = Path(written["env_manifest_path"]).read_text(encoding="utf-8")
    assert "no live/broker/orders" in on_disk
    assert "net_return_after_cost" in on_disk
    observation_on_disk = Path(written["observation_manifest_path"]).read_text(encoding="utf-8")
    assert "reward_action_telemetry_sufficient_for_d4" in observation_on_disk
    assert "future_return_1d" in observation_on_disk
    with pytest.raises(FileExistsError):
        write_env_inspection_artifacts(inspection, run_id="env_unit", artifact_root=root)
    with pytest.raises(ValueError):
        write_env_inspection_artifacts(inspection, run_id="../escape", artifact_root=root)
    with pytest.raises(ValueError):
        write_env_inspection_artifacts(inspection, run_id="bad", artifact_root=tmp_path / "elsewhere")

def test_sell_clears_positions_and_reduce_requires_multiple_positions():
    grouped = candidates_by_date(_candidate_rows(), score_column="score_supervised_linear_ranker", candidate_limit=2)
    env = DailyPortfolioEnv(grouped, max_positions=2)
    env.step(1)
    env.step(2)
    assert len(env.positions) == 2
    assert env.action_mask()[4] is True
    _state, _reward, _done, info = env.step(3)
    assert info["action"] == "sell"
    assert info["positions"] == []
