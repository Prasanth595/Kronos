import csv
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stom_rl.daily_rl_train import (  # noqa: E402
    build_action_prior_values,
    build_action_filter_decision,
    build_action_distribution,
    build_no_trade_opportunity_summary,
    run_daily_rl,
    write_rl_artifacts,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _create_prediction_run(root: Path, *, verdict_status: str = "WATCH") -> Path:
    run_dir = root / "prediction_unit"
    run_dir.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "manifest_sha": "prediction-sha-unit",
        "price_basis": "unknown",
        "price_basis_evidence": "unit unknown",
        "universe_review_status": "WATCH_REQUIRES_OFFICIAL_OR_MANUAL_REVIEW",
        "verdict": {"status": verdict_status, "go_summary_allowed": False},
    }
    verdict = {
        "schema_version": 1,
        "status": verdict_status,
        "go_summary_allowed": False,
        "reasons": ["UNIT_TEST"],
    }
    baseline_metrics = {
        "metrics": [
            {"strategy": "no_trade_cash", "total_net_return": 0.0, "max_drawdown": 0.0, "mean_turnover": 0.0},
            {"strategy": "equal_weight_topk_momentum", "total_net_return": 0.01, "max_drawdown": -0.01, "mean_turnover": 0.5},
            {"strategy": "supervised_linear_ranker", "total_net_return": 0.02, "max_drawdown": -0.02, "mean_turnover": 0.4},
        ]
    }
    rows = []
    split_by_index = {0: "train", 1: "train", 2: "train", 3: "val", 4: "val", 5: "test", 6: "test"}
    for idx in range(7):
        date = f"2024-01-{idx + 1:02d}"
        split = split_by_index[idx]
        for offset, code in enumerate(["000020", "000030", "000040"]):
            score = 0.5 - offset * 0.1 + idx * 0.01
            future = (0.01 if offset == 0 else -0.002) + idx * 0.0005
            rows.append(
                {
                    "date": date,
                    "table": f"A{code}",
                    "code": code,
                    "split": split,
                    "future_return_1d": future,
                    "score_supervised_linear_ranker": score,
                    "score_equal_weight_topk_momentum": score,
                }
            )
    (run_dir / "prediction_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_dir / "baseline_metrics.json").write_text(json.dumps(baseline_metrics), encoding="utf-8")
    (run_dir / "verdict.json").write_text(json.dumps(verdict), encoding="utf-8")
    _write_csv(run_dir / "predictions.csv", rows)
    return run_dir


def test_action_distribution_preserves_invalid_and_no_trade_reasons():
    rows = [
        {
            "split": "unit",
            "action": "hold",
            "requested_action": "reduce",
            "executed_action": "hold",
            "invalid_action": True,
            "invalid_action_reason": "blocked_requires_multiple_positions",
            "no_trade_action": False,
        },
        {
            "split": "unit",
            "action": "hold",
            "requested_action": "hold",
            "executed_action": "hold",
            "invalid_action": False,
            "invalid_action_reason": "",
            "no_trade_action": True,
        },
    ]

    distribution = build_action_distribution(rows)

    invalid = next(row for row in distribution if row["invalid_action"])
    no_trade = next(row for row in distribution if row["no_trade_action"])
    assert invalid["requested_action"] == "reduce"
    assert invalid["executed_action"] == "hold"
    assert invalid["invalid_action_reason"] == "blocked_requires_multiple_positions"
    assert invalid["action_rate"] == pytest.approx(0.5)
    assert no_trade["requested_action"] == "hold"
    assert no_trade["executed_action"] == "hold"
    assert no_trade["action_rate"] == pytest.approx(0.5)

def test_no_trade_opportunity_summary_is_post_policy_diagnostic_only():
    rows = [
        {
            "split": "unit",
            "no_trade_action": True,
            "top_candidate_score": 0.8,
            "top_candidate_net_after_entry_cost": 0.012,
            "diagnostic_future_label_exposed": True,
            "future_label_used_for_training_state": False,
        },
        {
            "split": "unit",
            "no_trade_action": True,
            "top_candidate_score": 0.3,
            "top_candidate_net_after_entry_cost": -0.004,
            "diagnostic_future_label_exposed": True,
            "future_label_used_for_training_state": False,
        },
        {
            "split": "unit",
            "no_trade_action": False,
            "top_candidate_score": 0.9,
            "top_candidate_net_after_entry_cost": 0.02,
            "diagnostic_future_label_exposed": True,
            "future_label_used_for_training_state": False,
        },
    ]

    summary = build_no_trade_opportunity_summary(rows)
    unit = summary["by_split"][0]

    assert summary["status"] == "POST_POLICY_DIAGNOSTIC_ONLY"
    assert summary["training_state_uses_future_label"] is False
    assert summary["diagnostic_uses_future_label_after_policy"] is True
    assert unit["no_trade_rows"] == 2
    assert unit["missed_positive_no_trade_count"] == 1
    assert unit["risk_avoided_no_trade_count"] == 1
    assert unit["total_missed_positive_net_after_entry_cost"] == pytest.approx(0.012)
    assert unit["total_risk_avoided_net_after_entry_cost"] == pytest.approx(-0.004)
def test_action_induction_v2_emits_richer_state_and_action_prior(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import stom_rl.daily_rl_train as rl_train

    prediction_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_prediction"
    run_dir = _create_prediction_run(prediction_root, verdict_status="WATCH")
    monkeypatch.setattr(rl_train, "DEFAULT_PREDICTION_ROOT", prediction_root)

    priors = build_action_prior_values(mode="entry_bias_v1", strength=0.0005)
    assert priors[1] == pytest.approx(0.0005)
    assert priors[2] == pytest.approx(0.0005)
    assert priors[0] == 0.0

    result = run_daily_rl(
        prediction_run_dir=run_dir,
        episodes=2,
        candidate_limit=2,
        max_positions=2,
        seed=3,
        observation_mode="action_induction_v2",
        action_prior_mode="entry_bias_v1",
        action_prior_strength=0.0005,
    )

    manifest = result["manifest"]
    observation_manifest = result["observation_manifest"]
    first_state = result["state_observations"][0]
    action_counts = {row["action"]: row["count"] for row in result["action_distribution"]}

    assert manifest["policy_type"] == "tabular_q_action_prior_v2"
    assert manifest["observation_mode"] == "action_induction_v2"
    assert observation_manifest["action_induction_v2"]["enabled"] is True
    assert {"score_margin_bucket", "candidate_count_bucket", "recent_score_volatility_bucket", "d3_confidence_bucket"} <= {
        field["name"] for field in observation_manifest["observation_fields"]
    }
    assert first_state["future_label_exposed"] is False
    assert first_state["observation_state_key"].count("|") == 5
    assert first_state["action_prior_buy"] == pytest.approx(0.0005)
    assert first_state["policy_score_buy"] == pytest.approx(first_state["policy_value_buy"] + first_state["action_prior_buy"])
    assert action_counts.get("buy", 0) > 0


def test_trade_quality_filter_blocks_entry_without_future_label(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import stom_rl.daily_rl_train as rl_train

    prediction_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_prediction"
    run_dir = _create_prediction_run(prediction_root, verdict_status="WATCH")
    monkeypatch.setattr(rl_train, "DEFAULT_PREDICTION_ROOT", prediction_root)

    decision = build_action_filter_decision(
        mode="confidence_abstain_v1",
        state_details={
            "d3_confidence_bucket": 1,
            "score_margin_bucket": 4,
            "recent_score_volatility_bucket": 0,
        },
        mask=[True, True, False, False, False],
    )
    assert decision["future_label_exposed"] is False
    assert decision["filtered_mask"] == [True, False, False, False, False]
    assert decision["blocked_entry_actions"] == ["buy"]
    assert decision["reasons_by_action"]["buy"] == "blocked_confidence_bucket_below_threshold"

    with pytest.raises(ValueError, match="action_induction_v2 state fields"):
        build_action_filter_decision(
            mode="margin_abstain_v1",
            state_details={"top_score_bucket": 1},
            mask=[True, True, False, False, False],
        )

    result = run_daily_rl(
        prediction_run_dir=run_dir,
        episodes=2,
        candidate_limit=2,
        max_positions=2,
        seed=3,
        observation_mode="action_induction_v2",
        action_prior_mode="entry_bias_v1",
        action_prior_strength=0.0005,
        action_filter_mode="confidence_margin_joint_v1",
    )

    manifest = result["manifest"]
    observation_manifest = result["observation_manifest"]
    first_abstention = result["abstention_reasons"][0]
    assert manifest["policy_type"] == "tabular_q_trade_quality_filter_v1"
    assert manifest["action_filter_mode"] == "confidence_margin_joint_v1"
    assert observation_manifest["trade_quality_filter"]["enabled"] is True
    assert observation_manifest["trade_quality_filter"]["telemetry_artifact"] == "abstention_reasons.csv"
    assert first_abstention["future_label_exposed"] is False
    assert {"filter_reason_buy", "filtered_action_mask_hold_buy_add_sell_reduce"} <= set(first_abstention)
    assert result["state_observations"][0]["action_filter_mode"] == "confidence_margin_joint_v1"


def test_run_daily_rl_emits_research_only_gate_and_required_metrics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import stom_rl.daily_rl_train as rl_train

    prediction_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_prediction"
    portfolio_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_portfolio"
    run_dir = _create_prediction_run(prediction_root, verdict_status="WATCH")
    monkeypatch.setattr(rl_train, "DEFAULT_PREDICTION_ROOT", prediction_root)
    monkeypatch.setattr(rl_train, "DEFAULT_PORTFOLIO_ROOT", portfolio_root)

    result = run_daily_rl(prediction_run_dir=run_dir, episodes=3, candidate_limit=2, max_positions=2, seed=3)
    manifest = result["manifest"]
    verdict = result["verdict"]
    assert manifest["cost_assumption_round_trip_bp"] == 23
    assert "slippage" in manifest["slippage_assumption"]
    assert manifest["action_space"][1] == "buy"
    assert manifest["go_summary_allowed"] is False
    assert manifest["model_build_allowed"] is False
    assert manifest["paper_forward_allowed"] is False
    assert manifest["live_broker_order_allowed"] is False
    assert manifest["readiness_status"] == "D4_RESEARCH_ONLY_DIAGNOSTICS"
    assert len(manifest["prediction_manifest_sha"]) == 64
    assert manifest["prediction_artifact_hashes"]["prediction_manifest"] == manifest["prediction_manifest_sha"]
    assert set(manifest["prediction_artifact_hashes"]) == {"prediction_manifest", "predictions", "baseline_metrics", "verdict"}
    assert all(len(value) == 64 for value in manifest["prediction_artifact_hashes"].values())
    assert manifest["prediction_artifact_hash_mismatches"] == []
    assert set(manifest["source_hashes"]) >= {
        "stom_rl/daily_rl_train.py",
        "stom_rl/daily_portfolio_env.py",
        "stom_rl/daily_prediction.py",
    }
    assert all(len(value) == 64 for value in manifest["source_hashes"].values())
    assert manifest["state_contract_status"] == "PASS"
    assert manifest["observation_manifest_validation"]["status"] == "PASS"
    assert manifest["observation_manifest"]["reward_action_telemetry_sufficient_for_d4"] is False
    assert manifest["observation_manifest"]["frozen_d3_comparison"]["required"] is True
    assert verdict["status"] == "RESEARCH_ONLY"
    assert verdict["ui_badge"] == "RESEARCH_ONLY"
    assert verdict["gate_dependency"] == "D3_WATCH_D5_NOT_RUN"
    assert verdict["go_summary_allowed"] is False
    assert verdict["model_build_allowed"] is False
    assert verdict["readiness_status"] == "D4_RESEARCH_ONLY_DIAGNOSTICS"
    assert verdict["paper_forward_allowed"] is False
    assert verdict["live_broker_order_allowed"] is False
    eval_metric = next(row for row in result["policy_metrics"]["metrics"] if row["split"] == "val+test")
    assert "invalid_action_rate" in eval_metric
    assert eval_metric["invalid_action_rate"] == 0.0
    assert result["reward_breakdown"]
    assert "slippage_cost" in result["reward_breakdown"][0]
    assert {"requested_action", "executed_action", "invalid_action_reason", "no_trade_action"} <= set(result["reward_breakdown"][0])
    assert "net_return_after_cost" in result["reward_breakdown"][0]
    assert "no_trade_hold_reward" in result["reward_breakdown"][0]
    assert result["baseline_comparison"]["best_d3_strategy"] == "supervised_linear_ranker"
    assert "slippage" in result["baseline_comparison"]["slippage_assumption"]
    assert result["learning_curve"]
    assert result["learning_curve"][0]["rolling_mean_reward"] == pytest.approx(result["episode_metrics"][0]["total_reward"])
    assert result["action_distribution"]
    assert result["turnover"]
    assert result["drawdown"]
    assert result["reward_component_summary"]["by_split"]
    assert "net_return_after_cost" in result["reward_component_summary"]["component_keys"]
    assert "no_trade_hold_reward" in result["reward_component_summary"]["component_keys"]
    assert result["reward_action_ablations"]
    assert result["reward_action_ablation_summary"]["ablation_count"] == len(result["reward_action_ablations"])
    assert "without_turnover_cost" in result["reward_action_ablation_summary"]["ablation_names"]
    assert result["no_trade_opportunity_diagnostics"]
    assert result["no_trade_opportunity_summary"]["status"] == "POST_POLICY_DIAGNOSTIC_ONLY"
    assert result["no_trade_opportunity_summary"]["training_state_uses_future_label"] is False
    assert result["no_trade_opportunity_summary"]["diagnostic_uses_future_label_after_policy"] is True
    assert result["source_hashes"] == manifest["source_hashes"]
    assert manifest["telemetry"]["status"] == "READY_RESEARCH_ONLY"
    assert "learning_curve.csv" in manifest["telemetry"]["canonical_artifacts"]
    assert "observation_manifest.json" in manifest["telemetry"]["canonical_artifacts"]
    assert "state_observations.csv" in manifest["telemetry"]["canonical_artifacts"]
    assert "policy_baseline_comparison.csv" in manifest["telemetry"]["canonical_artifacts"]
    assert "policy_nav.csv" in manifest["telemetry"]["canonical_artifacts"]
    assert "reward_action_ablations.csv" in manifest["telemetry"]["canonical_artifacts"]
    assert "reward_action_ablation_summary.json" in manifest["telemetry"]["canonical_artifacts"]
    assert "no_trade_opportunity_diagnostics.csv" in manifest["telemetry"]["canonical_artifacts"]
    assert "no_trade_opportunity_summary.json" in manifest["telemetry"]["canonical_artifacts"]
    assert "abstention_reasons.csv" in manifest["telemetry"]["canonical_artifacts"]
    assert "source_hashes.json" in manifest["telemetry"]["canonical_artifacts"]
    assert {row["baseline_strategy"] for row in result["policy_baseline_comparison"]} == {
        "no_trade_cash",
        "shuffle_control",
        "equal_weight_topk_momentum",
        "vol_adjusted_momentum",
        "supervised_linear_ranker",
        "supervised_direction_classifier",
    }
    assert all(row["cost_round_trip_bp"] == 23 for row in result["policy_baseline_comparison"])
    assert result["policy_nav"]
    assert result["state_observations"]
    assert result["state_observations"][0]["future_label_exposed"] is False
    assert result["no_trade_opportunity_diagnostics"][0]["diagnostic_future_label_exposed"] is True
    assert result["no_trade_opportunity_diagnostics"][0]["future_label_used_for_training_state"] is False

    written = write_rl_artifacts(result, run_id="portfolio_unit")
    assert Path(written["rl_manifest_path"]).exists()
    assert Path(written["observation_manifest_path"]).exists()
    assert Path(written["state_observations_path"]).exists()
    assert Path(written["policy_metrics_path"]).exists()
    assert Path(written["episode_metrics_path"]).exists()
    assert Path(written["positions_path"]).exists()
    assert Path(written["invalid_actions_path"]).exists()
    assert Path(written["reward_breakdown_path"]).exists()
    assert Path(written["baseline_comparison_path"]).exists()
    assert Path(written["verdict_path"]).exists()
    assert Path(written["training_manifest_path"]).exists()
    assert Path(written["learning_curve_path"]).exists()
    assert Path(written["action_distribution_path"]).exists()
    assert Path(written["turnover_path"]).exists()
    assert Path(written["drawdown_path"]).exists()
    assert Path(written["reward_component_summary_path"]).exists()
    assert Path(written["policy_baseline_comparison_path"]).exists()
    assert Path(written["policy_nav_path"]).exists()
    assert Path(written["policy_evaluation_manifest_path"]).exists()
    assert Path(written["reward_action_ablations_path"]).exists()
    assert Path(written["reward_action_ablation_summary_path"]).exists()
    assert Path(written["no_trade_opportunity_diagnostics_path"]).exists()
    assert Path(written["no_trade_opportunity_summary_path"]).exists()
    assert Path(written["abstention_reasons_path"]).exists()
    assert Path(written["source_hashes_path"]).exists()
    manifest_on_disk = json.loads(Path(written["rl_manifest_path"]).read_text(encoding="utf-8"))
    assert manifest_on_disk["run_id"] == "portfolio_unit"
    assert manifest_on_disk["verdict"]["go_summary_allowed"] is False
    assert manifest_on_disk["model_build_allowed"] is False
    assert manifest_on_disk["readiness_status"] == "D4_RESEARCH_ONLY_DIAGNOSTICS"
    assert manifest_on_disk["artifact_hashes"]["policy_metrics"]
    training_manifest = json.loads(Path(written["training_manifest_path"]).read_text(encoding="utf-8"))
    observation_manifest = json.loads(Path(written["observation_manifest_path"]).read_text(encoding="utf-8"))
    assert observation_manifest["gate"] == "D4_OBSERVATION_STATE_MANIFEST"
    assert observation_manifest["reward_action_telemetry_sufficient_for_d4"] is False
    assert "shuffle_control" in observation_manifest["frozen_d3_comparison"]["required_baselines"]
    state_rows = list(csv.DictReader(Path(written["state_observations_path"]).open("r", encoding="utf-8", newline="")))
    assert {"cash_fraction", "exposure_fraction", "future_label_exposed"} <= set(state_rows[0])
    assert {"action_mask_hold_buy_add_sell_reduce", "mask_reason_hold", "mask_reason_buy"} <= set(state_rows[0])
    assert training_manifest["telemetry"]["training_status"] == "TABULAR_Q_TELEMETRY_RECORDED"
    assert training_manifest["artifact_hashes"]["policy_metrics"]
    learning_curve = list(csv.DictReader(Path(written["learning_curve_path"]).open("r", encoding="utf-8", newline="")))
    assert {"episode", "rolling_mean_reward", "best_total_reward"} <= set(learning_curve[0])
    action_distribution = list(csv.DictReader(Path(written["action_distribution_path"]).open("r", encoding="utf-8", newline="")))
    assert {"split", "action", "action_rate"} <= set(action_distribution[0])
    assert {"requested_action", "executed_action", "invalid_action_reason", "no_trade_action"} <= set(action_distribution[0])
    reward_rows = list(csv.DictReader(Path(written["reward_breakdown_path"]).open("r", encoding="utf-8", newline="")))
    assert {"net_return_after_cost", "no_trade_hold_reward", "mask_reason_reduce"} <= set(reward_rows[0])
    ablation_rows = list(csv.DictReader(Path(written["reward_action_ablations_path"]).open("r", encoding="utf-8", newline="")))
    assert {"ablation", "delta_vs_recorded_reward", "cost_round_trip_bp"} <= set(ablation_rows[0])
    assert {row["ablation"] for row in ablation_rows} >= {"recorded_reward", "without_turnover_cost"}
    opportunity_rows = list(csv.DictReader(Path(written["no_trade_opportunity_diagnostics_path"]).open("r", encoding="utf-8", newline="")))
    assert {"diagnostic", "top_candidate_net_after_entry_cost", "future_label_used_for_training_state"} <= set(opportunity_rows[0])
    abstention_rows = list(csv.DictReader(Path(written["abstention_reasons_path"]).open("r", encoding="utf-8", newline="")))
    assert {"action_filter_mode", "future_label_exposed", "filter_reason_buy"} <= set(abstention_rows[0])
    assert abstention_rows[0]["future_label_exposed"] == "False"
    opportunity_summary = json.loads(Path(written["no_trade_opportunity_summary_path"]).read_text(encoding="utf-8"))
    assert opportunity_summary["guardrail"].startswith("No-trade opportunity diagnostics")
    assert opportunity_summary["training_state_uses_future_label"] is False
    policy_rows = list(csv.DictReader(Path(written["policy_baseline_comparison_path"]).open("r", encoding="utf-8", newline="")))
    assert {"baseline_strategy", "policy_nav", "baseline_nav", "baseline_delta_total_net_return"} <= set(policy_rows[0])
    policy_manifest = json.loads(Path(written["policy_evaluation_manifest_path"]).read_text(encoding="utf-8"))
    assert policy_manifest["readiness_status"] == "D4_RESEARCH_ONLY_DIAGNOSTICS"
    assert policy_manifest["paper_forward_allowed"] is False
    assert policy_manifest["live_broker_order_allowed"] is False
    assert policy_manifest["reward_action_ablation_rows"] == len(result["reward_action_ablations"])
    assert policy_manifest["no_trade_opportunity_diagnostic_rows"] == len(result["no_trade_opportunity_diagnostics"])
    assert policy_manifest["abstention_reason_rows"] == len(result["abstention_reasons"])
    assert policy_manifest["source_hashes"] == result["source_hashes"]
    source_hashes = json.loads(Path(written["source_hashes_path"]).read_text(encoding="utf-8"))
    assert source_hashes["source_hashes"] == result["source_hashes"]
    assert policy_manifest["required_frozen_baselines"] == [
        "no_trade_cash",
        "shuffle_control",
        "equal_weight_topk_momentum",
        "vol_adjusted_momentum",
        "supervised_linear_ranker",
        "supervised_direction_classifier",
    ]

    with pytest.raises(FileExistsError):
        write_rl_artifacts(result, run_id="portfolio_unit")
    with pytest.raises(ValueError):
        write_rl_artifacts(result, artifact_root=tmp_path / "elsewhere", run_id="bad")
    with pytest.raises(ValueError):
        write_rl_artifacts(result, run_id="../escape")


def test_run_daily_rl_records_declared_prediction_hash_mismatches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import stom_rl.daily_rl_train as rl_train

    prediction_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_prediction"
    run_dir = _create_prediction_run(prediction_root, verdict_status="WATCH")
    manifest_path = run_dir / "prediction_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_hashes"] = {
        "predictions": "0" * 64,
        "baseline_metrics": "1" * 64,
        "verdict": "2" * 64,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(rl_train, "DEFAULT_PREDICTION_ROOT", prediction_root)

    result = run_daily_rl(prediction_run_dir=run_dir, episodes=2, candidate_limit=2, max_positions=2)

    artifact_hashes = result["manifest"]["prediction_artifact_hashes"]
    assert set(result["manifest"]["prediction_artifact_hash_mismatches"]) == {
        "predictions",
        "baseline_metrics",
        "verdict",
    }
    assert artifact_hashes["predictions"] != "0" * 64
    assert artifact_hashes["baseline_metrics"] != "1" * 64
    assert artifact_hashes["verdict"] != "2" * 64
    assert all(len(value) == 64 for value in artifact_hashes.values())

def test_d3_failed_or_skipped_forces_research_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import stom_rl.daily_rl_train as rl_train

    prediction_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_prediction"
    run_dir = _create_prediction_run(prediction_root, verdict_status="skipped")
    monkeypatch.setattr(rl_train, "DEFAULT_PREDICTION_ROOT", prediction_root)

    result = run_daily_rl(prediction_run_dir=run_dir, episodes=2, candidate_limit=2, max_positions=2)
    verdict = result["verdict"]
    assert verdict["research_override"] is True
    assert verdict["gate_dependency"] == "D3_FAILED_OR_SKIPPED"
    assert verdict["d3_status_normalized"] == "SKIPPED"
    assert verdict["go_summary_allowed"] is False
