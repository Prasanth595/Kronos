import csv
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stom_rl.daily_walk_forward import run_daily_walk_forward, write_walk_forward_artifacts  # noqa: E402


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _create_prediction_run(root: Path) -> Path:
    run_dir = root / "prediction_unit"
    run_dir.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "price_basis": "unknown",
        "price_basis_evidence": "unit unknown",
        "universe_review_status": "WATCH_REQUIRES_OFFICIAL_OR_MANUAL_REVIEW",
        "verdict": {"status": "WATCH", "go_summary_allowed": False},
    }
    baseline_metrics = {
        "metrics": [
            {"strategy": "no_trade_cash", "total_net_return": 0.0, "mean_turnover": 0.0, "max_drawdown": 0.0},
            {"strategy": "equal_weight_topk_momentum", "total_net_return": 0.05, "mean_turnover": 0.5, "max_drawdown": -0.01},
            {"strategy": "supervised_linear_ranker", "total_net_return": 0.03, "mean_turnover": 0.4, "max_drawdown": -0.02},
        ]
    }
    rows = []
    for idx in range(15):
        date = f"2024-01-{idx + 1:02d}"
        split = "train" if idx < 5 else "val" if idx < 10 else "test"
        for offset, code in enumerate(["000020", "000030", "000040"]):
            score = 0.4 - offset * 0.1 + idx * 0.01
            rows.append(
                {
                    "date": date,
                    "table": f"A{code}",
                    "code": code,
                    "split": split,
                    "future_return_1d": 0.01 if offset == 0 else -0.002,
                    "score_equal_weight_topk_momentum": score,
                    "score_supervised_linear_ranker": score / 2,
                }
            )
    (run_dir / "prediction_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_dir / "baseline_metrics.json").write_text(json.dumps(baseline_metrics), encoding="utf-8")
    (run_dir / "verdict.json").write_text(json.dumps({"status": "WATCH", "go_summary_allowed": False}), encoding="utf-8")
    _write_csv(run_dir / "predictions.csv", rows)
    return run_dir


def _create_portfolio_run(root: Path) -> Path:
    run_dir = root / "portfolio_unit"
    run_dir.mkdir(parents=True)
    observation_manifest = {
        "status": "PASS_RESEARCH_ONLY_STATE_CONTRACT",
        "gate": "D4_OBSERVATION_STATE_MANIFEST",
        "reward_action_telemetry_sufficient_for_d4": False,
        "frozen_d3_comparison": {
            "required_baselines": [
                "no_trade_cash",
                "shuffle_control",
                "equal_weight_topk_momentum",
            ]
        },
    }
    manifest = {
        "schema_version": 1,
        "run_id": "portfolio_unit",
        "verdict": {"status": "RESEARCH_ONLY", "go_summary_allowed": False, "implementation_unlocked": False},
        "slippage_assumption": "No separate daily slippage model is inferred from OHLCV; use 23bp and sensitivity.",
        "observation_manifest": observation_manifest,
        "observation_manifest_validation": {"status": "PASS", "observation_fields": ["position_count", "top_score_bucket"]},
        "state_contract_status": "PASS",
    }
    verdict = {"status": "RESEARCH_ONLY", "go_summary_allowed": False, "implementation_unlocked": False}
    comparison = {
        "policy_total_net_return": -0.10,
        "best_d3_total_net_return": 0.05,
        "delta_vs_best_d3_total_net_return": -0.15,
        "cost_round_trip_bp": 23,
    }
    rewards = []
    state_rows = []
    invalid_rows = []
    policy_nav_rows = []
    ablation_rows = []
    for idx in range(5, 15):
        date = f"2024-01-{idx + 1:02d}"
        rewards.append(
            {
                "split": "val+test",
                "date": date,
                "reward": -0.001,
                "turnover": 0.1,
                "exposure": 0.4,
                "invalid_action": False,
            }
        )
        state_rows.append(
            {
                "split": "val+test",
                "date": date,
                "observation_position_count": 0,
                "observation_top_score_bucket": 1,
                "future_label_exposed": False,
                "top_candidate_code": "000020",
            }
        )
        invalid_rows.append({"split": "val+test", "date": date, "invalid_action": False, "action_mask": "1|1|0|0|0"})
        policy_nav_rows.append({"split": "val+test", "date": date, "policy_nav": 1.0, "policy_current_drawdown": 0.0})
        ablation_rows.append(
            {
                "split": "val+test",
                "ablation_family": "reward_component",
                "ablation": "recorded_reward",
                "rows": 1,
                "total_reward": -0.001,
                "mean_reward": -0.001,
                "delta_vs_recorded_reward": 0.0,
                "cost_round_trip_bp": 23,
            }
        )
    baseline_rows = [
        {"baseline_strategy": "no_trade_cash", "baseline_status": "LOADED", "cost_round_trip_bp": 23},
        {"baseline_strategy": "shuffle_control", "baseline_status": "LOADED", "cost_round_trip_bp": 23},
        {"baseline_strategy": "equal_weight_topk_momentum", "baseline_status": "LOADED", "cost_round_trip_bp": 23},
    ]
    (run_dir / "rl_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_dir / "observation_manifest.json").write_text(json.dumps(observation_manifest), encoding="utf-8")
    (run_dir / "verdict.json").write_text(json.dumps(verdict), encoding="utf-8")
    (run_dir / "baseline_comparison.json").write_text(json.dumps(comparison), encoding="utf-8")
    _write_csv(run_dir / "reward_breakdown.csv", rewards)
    _write_csv(run_dir / "state_observations.csv", state_rows)
    _write_csv(run_dir / "invalid_actions.csv", invalid_rows)
    _write_csv(run_dir / "policy_baseline_comparison.csv", baseline_rows)
    _write_csv(run_dir / "policy_nav.csv", policy_nav_rows)
    _write_csv(run_dir / "reward_action_ablations.csv", ablation_rows)
    (run_dir / "reward_action_ablation_summary.json").write_text(
        json.dumps({"schema_version": 1, "ablation_count": len(ablation_rows), "ablation_names": ["recorded_reward"]}),
        encoding="utf-8",
    )
    (run_dir / "source_hashes.json").write_text(
        json.dumps({"schema_version": 1, "source_hashes": {"stom_rl/daily_rl_train.py": "a" * 64}}),
        encoding="utf-8",
    )
    return run_dir


def test_daily_walk_forward_emits_no_go_gate_and_controls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import stom_rl.daily_walk_forward as walk_forward

    prediction_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_prediction"
    portfolio_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_portfolio"
    walk_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_walk_forward"
    prediction_run = _create_prediction_run(prediction_root)
    portfolio_run = _create_portfolio_run(portfolio_root)
    monkeypatch.setattr(walk_forward, "DEFAULT_PREDICTION_ROOT", prediction_root)
    monkeypatch.setattr(walk_forward, "DEFAULT_PORTFOLIO_ROOT", portfolio_root)
    monkeypatch.setattr(walk_forward, "DEFAULT_WALK_FORWARD_ROOT", walk_root)

    result = run_daily_walk_forward(prediction_run_dir=prediction_run, portfolio_run_dir=portfolio_run, n_folds=5, top_k=1)
    verdict = result["gate_verdict"]
    assert verdict["status"] == "NO-GO"
    assert verdict["model_build_allowed"] is False
    assert verdict["go_summary_allowed"] is False
    assert verdict["paper_forward_allowed"] is False
    assert verdict["live_broker_order_allowed"] is False
    assert verdict["no_live_broker_order_readiness"] is True
    assert verdict["readiness_status"] == "D5_NO_GO_RESEARCH_ONLY_GATE"
    assert verdict["n_folds"] == 5
    assert verdict["no_oos_retuning"] is True
    assert verdict["strategy_selection_policy"] == "preregistered_equal_weight_topk_momentum_no_oos_metric_selection"
    assert verdict["selected_strategy"] == "equal_weight_topk_momentum"
    assert "RL_POLICY_UNDERPERFORMS_D3_BASELINE" in verdict["reasons"]
    assert "PRICE_BASIS_UNKNOWN" in verdict["reasons"]
    assert "D4_OBSERVATION_STATE_MANIFEST_CONSUMED" in verdict["reasons"]
    assert verdict["d4_state_contract_status"] == "PASS"
    assert verdict["d4_observation_manifest_gate"] == "D4_OBSERVATION_STATE_MANIFEST"
    assert verdict["d4_state_contract_artifacts_consumed"] is True
    assert verdict["d4_state_observation_rows"] == 10
    assert verdict["d4_reward_action_telemetry_sufficient_for_d4"] is False
    assert set(verdict["prediction_artifact_hashes"]) == {"prediction_manifest", "predictions", "baseline_metrics", "verdict"}
    assert {"rl_manifest", "reward_breakdown", "state_observations", "policy_baseline_comparison", "policy_nav"} <= set(verdict["portfolio_artifact_hashes"])
    assert "reward_action_ablations" in verdict["portfolio_artifact_hashes"]
    assert "source_hashes" in verdict["portfolio_artifact_hashes"]
    assert verdict["d4_reward_action_ablation_rows"] == 10
    assert verdict["d4_source_hash_count"] == 1
    assert all(len(value) == 64 for value in verdict["prediction_artifact_hashes"].values())
    assert all(len(value) == 64 for value in verdict["portfolio_artifact_hashes"].values())
    assert verdict["d4_artifact_issues"] == []
    assert all(row["forward_only"] is True for row in result["folds"])
    assert all(row["retuned_on_oos"] is False for row in result["folds"])
    assert all(not row["purge_start_date"] or row["train_end_date"] < row["purge_start_date"] for row in result["folds"])
    assert len(result["shuffle_control"]) == 5
    assert len(result["cost_sensitivity"]) == 15
    assert {float(row["cost_bp"]) for row in result["cost_sensitivity"]} == {0.0, 23.0, 46.0}
    assert len(result["rl_fold_metrics"]) == 5
    selected_rows = [row for row in result["fold_metrics"] if row["strategy"] == "equal_weight_topk_momentum" and row["control"] == "actual"]
    assert all("delta_vs_no_trade_total_net_return" in row for row in selected_rows)
    assert all("delta_vs_shuffled_total_net_return" in row for row in selected_rows)
    assert result["gate_verdict"]["fold_consistency"]["folds_beating_no_trade"] >= 0
    assert result["gate_verdict"]["fold_consistency"]["folds_beating_shuffle"] >= 0
    assert "worst_fold_max_drawdown" in result["gate_verdict"]["fold_consistency"]
    assert "mean_fold_turnover" in result["gate_verdict"]["fold_consistency"]
    assert verdict["max_allowed_fold_drawdown"] == -0.20
    assert verdict["max_allowed_mean_turnover"] == 1.00
    assert "MDD_TURNOVER_LIMITS_CHECKED" in verdict["reasons"]

    written = write_walk_forward_artifacts(result, run_id="walk_forward_unit")
    assert Path(written["walk_forward_manifest_path"]).exists()
    assert Path(written["fold_assignments_path"]).exists()
    assert Path(written["fold_metrics_path"]).exists()
    assert Path(written["shuffle_control_path"]).exists()
    assert Path(written["cost_sensitivity_path"]).exists()
    assert Path(written["rl_fold_metrics_path"]).exists()
    assert Path(written["gate_verdict_path"]).exists()
    assert Path(written["d4_state_contract_path"]).exists()
    manifest = json.loads(Path(written["walk_forward_manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["run_id"] == "walk_forward_unit"
    assert manifest["verdict"]["status"] == "NO-GO"
    assert manifest["d4_state_contract_status"] == "PASS"
    assert manifest["row_counts"]["d4_state_observation_rows"] == 10
    assert manifest["model_build_allowed"] is False
    assert manifest["go_summary_allowed"] is False
    assert manifest["paper_forward_allowed"] is False
    assert manifest["live_broker_order_allowed"] is False
    assert manifest["readiness_status"] == "D5_NO_GO_RESEARCH_ONLY_GATE"
    assert len(manifest["prediction_manifest_sha"]) == 64
    assert len(manifest["portfolio_manifest_sha"]) == 64
    assert manifest["prediction_artifact_hashes"] == verdict["prediction_artifact_hashes"]
    assert manifest["portfolio_artifact_hashes"] == verdict["portfolio_artifact_hashes"]
    assert {"fold_metrics", "cost_sensitivity", "rl_fold_metrics", "gate_verdict", "d4_state_contract", "walk_forward_manifest"} <= set(written["artifact_hashes"])
    assert "reward_action_ablations" in manifest["portfolio_artifact_hashes"]
    assert manifest["row_counts"]["d4_reward_action_ablation_rows"] == 10
    assert manifest["row_counts"]["d4_source_hash_count"] == 1
    assert manifest["artifact_hashes"]["gate_verdict"] == written["artifact_hashes"]["gate_verdict"]

    with pytest.raises(FileExistsError):
        write_walk_forward_artifacts(result, run_id="walk_forward_unit")
    with pytest.raises(ValueError):
        write_walk_forward_artifacts(result, artifact_root=tmp_path / "elsewhere", run_id="bad")
    with pytest.raises(ValueError):
        write_walk_forward_artifacts(result, run_id="../escape")
    with pytest.raises(ValueError):
        run_daily_walk_forward(prediction_run_dir=tmp_path / "elsewhere" / "prediction_unit", portfolio_run_dir=portfolio_run)
    with pytest.raises(ValueError):
        run_daily_walk_forward(prediction_run_dir=prediction_run, portfolio_run_dir=tmp_path / "elsewhere" / "portfolio_unit")


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("missing_state_observations", "D4_REQUIRED_ARTIFACT_MISSING_state_observations.csv"),
        ("missing_reward_breakdown", "D4_REQUIRED_ARTIFACT_MISSING_reward_breakdown.csv"),
        ("telemetry_true", "D4_REWARD_ACTION_TELEMETRY_FLAG_NOT_FALSE"),
        ("validation_fail", "D4_OBSERVATION_MANIFEST_VALIDATION_NOT_PASS"),
        ("state_contract_fail", "D4_STATE_CONTRACT_STATUS_NOT_PASS"),
        ("gate_invalid", "D4_OBSERVATION_STATE_MANIFEST_GATE_INVALID"),
        ("missing_frozen_baseline", "D4_FROZEN_D3_BASELINE_MISSING_equal_weight_topk_momentum"),
        ("missing_reward_action_ablations", "D4_REQUIRED_ARTIFACT_MISSING_reward_action_ablations.csv"),
        ("missing_source_hashes", "D4_REQUIRED_ARTIFACT_MISSING_source_hashes.json"),
        ("empty_source_hashes", "D4_SOURCE_HASHES_MISSING"),
        ("bad_source_hashes_json", "D4_SOURCE_HASHES_JSON_INVALID"),
        ("empty_state_observations", "D4_STATE_OBSERVATIONS_EMPTY"),
        ("bad_state_observations_encoding", "D4_STATE_OBSERVATIONS_CSV_INVALID"),
        ("bad_reward_breakdown_encoding", "D4_REWARD_BREAKDOWN_CSV_INVALID"),
        ("empty_reward_action_ablations", "D4_REWARD_ACTION_ABLATIONS_EMPTY"),
        ("schema_bad_state_observations", "D4_STATE_OBSERVATIONS_SCHEMA_INVALID"),
        ("schema_bad_reward_breakdown", "D4_REWARD_BREAKDOWN_SCHEMA_INVALID"),
        ("schema_bad_invalid_actions", "D4_INVALID_ACTIONS_SCHEMA_INVALID"),
        ("schema_bad_policy_baseline_comparison", "D4_POLICY_BASELINE_COMPARISON_SCHEMA_INVALID"),
        ("schema_bad_policy_nav", "D4_POLICY_NAV_SCHEMA_INVALID"),
        ("schema_bad_reward_action_ablations", "D4_REWARD_ACTION_ABLATIONS_SCHEMA_INVALID"),
        ("empty_reward_breakdown", "D4_REWARD_BREAKDOWN_EMPTY"),
        ("empty_invalid_actions", "D4_INVALID_ACTIONS_EMPTY"),
        ("empty_policy_nav", "D4_POLICY_NAV_EMPTY"),
        ("empty_policy_baseline_comparison", "D4_POLICY_BASELINE_COMPARISON_EMPTY"),
        ("empty_reward_action_ablation_summary", "D4_REWARD_ACTION_ABLATION_SUMMARY_EMPTY"),
        ("bad_observation_manifest_json", "D4_OBSERVATION_MANIFEST_JSON_INVALID"),
        ("bad_reward_action_ablation_summary_json", "D4_REWARD_ACTION_ABLATION_SUMMARY_JSON_INVALID"),
        ("missing_required_baseline_list", "D4_FROZEN_D3_BASELINE_REQUIREMENTS_MISSING"),
        ("malformed_required_baseline_list", "D4_FROZEN_D3_BASELINE_REQUIREMENTS_MISSING"),
    ],
)
def test_daily_walk_forward_blocks_d4_state_contract_violations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    reason: str,
):
    import stom_rl.daily_walk_forward as walk_forward

    prediction_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_prediction"
    portfolio_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_portfolio"
    prediction_run = _create_prediction_run(prediction_root)
    portfolio_run = _create_portfolio_run(portfolio_root)
    manifest_path = portfolio_run / "rl_manifest.json"
    observation_path = portfolio_run / "observation_manifest.json"

    if case == "missing_state_observations":
        (portfolio_run / "state_observations.csv").unlink()
    elif case == "missing_reward_breakdown":
        (portfolio_run / "reward_breakdown.csv").unlink()
    elif case == "missing_reward_action_ablations":
        (portfolio_run / "reward_action_ablations.csv").unlink()
    elif case == "missing_source_hashes":
        (portfolio_run / "source_hashes.json").unlink()
    elif case == "empty_source_hashes":
        (portfolio_run / "source_hashes.json").write_text(
            json.dumps({"schema_version": 1, "source_hashes": {}}),
            encoding="utf-8",
        )
    elif case == "bad_source_hashes_json":
        (portfolio_run / "source_hashes.json").write_text("{", encoding="utf-8")
    elif case == "empty_state_observations":
        (portfolio_run / "state_observations.csv").write_text(
            "split,date,observation_position_count,observation_top_score_bucket,future_label_exposed\n",
            encoding="utf-8",
        )
    elif case == "bad_state_observations_encoding":
        (portfolio_run / "state_observations.csv").write_bytes(b"\xff\xfe\x00")
    elif case == "bad_reward_breakdown_encoding":
        (portfolio_run / "reward_breakdown.csv").write_bytes(b"\xff\xfe\x00")
    elif case == "empty_reward_action_ablations":
        (portfolio_run / "reward_action_ablations.csv").write_text(
            "split,ablation_family,ablation,rows,total_reward,cost_round_trip_bp\n",
            encoding="utf-8",
        )
    elif case == "schema_bad_state_observations":
        (portfolio_run / "state_observations.csv").write_text("wrong\nvalue\n", encoding="utf-8")
    elif case == "schema_bad_reward_breakdown":
        (portfolio_run / "reward_breakdown.csv").write_text("wrong\nvalue\n", encoding="utf-8")
    elif case == "schema_bad_invalid_actions":
        (portfolio_run / "invalid_actions.csv").write_text("wrong\nvalue\n", encoding="utf-8")
    elif case == "schema_bad_policy_baseline_comparison":
        (portfolio_run / "policy_baseline_comparison.csv").write_text("wrong\nvalue\n", encoding="utf-8")
    elif case == "schema_bad_policy_nav":
        (portfolio_run / "policy_nav.csv").write_text("wrong\nvalue\n", encoding="utf-8")
    elif case == "schema_bad_reward_action_ablations":
        (portfolio_run / "reward_action_ablations.csv").write_text("wrong\nvalue\n", encoding="utf-8")
    elif case == "empty_reward_breakdown":
        (portfolio_run / "reward_breakdown.csv").write_text("split,date,reward,turnover,exposure,invalid_action\n", encoding="utf-8")
    elif case == "empty_invalid_actions":
        (portfolio_run / "invalid_actions.csv").write_text("split,date,invalid_action,action_mask\n", encoding="utf-8")
    elif case == "empty_policy_nav":
        (portfolio_run / "policy_nav.csv").write_text("split,date,policy_nav,policy_current_drawdown\n", encoding="utf-8")
    elif case == "empty_policy_baseline_comparison":
        (portfolio_run / "policy_baseline_comparison.csv").write_text("baseline_strategy,baseline_status,cost_round_trip_bp\n", encoding="utf-8")
    elif case == "empty_reward_action_ablation_summary":
        (portfolio_run / "reward_action_ablation_summary.json").write_text("{}", encoding="utf-8")
    elif case == "bad_observation_manifest_json":
        observation_path.write_text("{", encoding="utf-8")
    elif case == "bad_reward_action_ablation_summary_json":
        (portfolio_run / "reward_action_ablation_summary.json").write_text("{", encoding="utf-8")
    elif case == "missing_required_baseline_list":
        observation_manifest = json.loads(observation_path.read_text(encoding="utf-8"))
        observation_manifest["frozen_d3_comparison"] = {}
        observation_path.write_text(json.dumps(observation_manifest), encoding="utf-8")
    elif case == "malformed_required_baseline_list":
        observation_manifest = json.loads(observation_path.read_text(encoding="utf-8"))
        observation_manifest["frozen_d3_comparison"] = {"required_baselines": "no_trade_cash"}
        observation_path.write_text(json.dumps(observation_manifest), encoding="utf-8")
    elif case == "telemetry_true":
        observation_manifest = json.loads(observation_path.read_text(encoding="utf-8"))
        observation_manifest["reward_action_telemetry_sufficient_for_d4"] = True
        observation_path.write_text(json.dumps(observation_manifest), encoding="utf-8")
    elif case == "validation_fail":
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["observation_manifest_validation"]["status"] = "FAIL"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif case == "state_contract_fail":
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["state_contract_status"] = "FAIL"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif case == "gate_invalid":
        observation_manifest = json.loads(observation_path.read_text(encoding="utf-8"))
        observation_manifest["gate"] = "D4_TELEMETRY_ONLY"
        observation_path.write_text(json.dumps(observation_manifest), encoding="utf-8")
    elif case == "missing_frozen_baseline":
        _write_csv(
            portfolio_run / "policy_baseline_comparison.csv",
            [
                {"baseline_strategy": "no_trade_cash", "baseline_status": "LOADED", "cost_round_trip_bp": 23},
                {"baseline_strategy": "shuffle_control", "baseline_status": "LOADED", "cost_round_trip_bp": 23},
            ],
        )

    monkeypatch.setattr(walk_forward, "DEFAULT_PREDICTION_ROOT", prediction_root)
    monkeypatch.setattr(walk_forward, "DEFAULT_PORTFOLIO_ROOT", portfolio_root)

    result = run_daily_walk_forward(prediction_run_dir=prediction_run, portfolio_run_dir=portfolio_run, n_folds=5)
    assert result["gate_verdict"]["status"] == "NO-GO"
    assert reason in result["gate_verdict"]["reasons"]
    assert result["gate_verdict"]["d4_state_contract_artifacts_consumed"] is False
    assert result["gate_verdict"]["model_build_allowed"] is False
    assert result["gate_verdict"]["readiness_status"] == "D5_NO_GO_RESEARCH_ONLY_GATE"
    assert "D5_REQUIRED_EVIDENCE_INCOMPLETE" in result["gate_verdict"]["reasons"]

def test_daily_walk_forward_blocks_when_folds_below_five(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import stom_rl.daily_walk_forward as walk_forward

    prediction_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_prediction"
    portfolio_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_portfolio"
    prediction_run = _create_prediction_run(prediction_root)
    portfolio_run = _create_portfolio_run(portfolio_root)
    monkeypatch.setattr(walk_forward, "DEFAULT_PREDICTION_ROOT", prediction_root)
    monkeypatch.setattr(walk_forward, "DEFAULT_PORTFOLIO_ROOT", portfolio_root)

    result = run_daily_walk_forward(prediction_run_dir=prediction_run, portfolio_run_dir=portfolio_run, n_folds=4)
    assert result["gate_verdict"]["status"] == "NO-GO"
    assert "N_FOLDS_BELOW_5" in result["gate_verdict"]["reasons"]
    assert result["gate_verdict"]["model_build_allowed"] is False
    assert result["gate_verdict"]["readiness_status"] == "D5_NO_GO_RESEARCH_ONLY_GATE"
    assert "D5_REQUIRED_EVIDENCE_INCOMPLETE" in result["gate_verdict"]["reasons"]


@pytest.mark.parametrize(
    ("purge_days", "embargo_days", "reason"),
    [
        (0, 5, "PURGE_DAYS_BELOW_REQUIRED_MIN"),
        (5, 0, "EMBARGO_DAYS_BELOW_REQUIRED_MIN"),
    ],
)
def test_daily_walk_forward_blocks_missing_purge_or_embargo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    purge_days: int,
    embargo_days: int,
    reason: str,
):
    import stom_rl.daily_walk_forward as walk_forward

    prediction_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_prediction"
    portfolio_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_portfolio"
    prediction_run = _create_prediction_run(prediction_root)
    portfolio_run = _create_portfolio_run(portfolio_root)
    monkeypatch.setattr(walk_forward, "DEFAULT_PREDICTION_ROOT", prediction_root)
    monkeypatch.setattr(walk_forward, "DEFAULT_PORTFOLIO_ROOT", portfolio_root)

    result = run_daily_walk_forward(
        prediction_run_dir=prediction_run,
        portfolio_run_dir=portfolio_run,
        n_folds=5,
        purge_days=purge_days,
        embargo_days=embargo_days,
    )
    assert result["gate_verdict"]["status"] == "NO-GO"
    assert reason in result["gate_verdict"]["reasons"]
    assert result["gate_verdict"]["model_build_allowed"] is False
    assert result["gate_verdict"]["readiness_status"] == "D5_NO_GO_RESEARCH_ONLY_GATE"
    assert "D5_REQUIRED_EVIDENCE_INCOMPLETE" in result["gate_verdict"]["reasons"]


def test_daily_walk_forward_missing_baseline_comparison_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import stom_rl.daily_walk_forward as walk_forward

    prediction_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_prediction"
    portfolio_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_portfolio"
    prediction_run = _create_prediction_run(prediction_root)
    portfolio_run = _create_portfolio_run(portfolio_root)
    (portfolio_run / "baseline_comparison.json").unlink()
    monkeypatch.setattr(walk_forward, "DEFAULT_PREDICTION_ROOT", prediction_root)
    monkeypatch.setattr(walk_forward, "DEFAULT_PORTFOLIO_ROOT", portfolio_root)

    result = run_daily_walk_forward(prediction_run_dir=prediction_run, portfolio_run_dir=portfolio_run, n_folds=5)

    assert result["gate_verdict"]["status"] == "NO-GO"
    assert result["gate_verdict"]["model_build_allowed"] is False
    assert result["gate_verdict"]["readiness_status"] == "D5_NO_GO_RESEARCH_ONLY_GATE"
    assert "D5_BASELINE_COMPARISON_MISSING" in result["gate_verdict"]["reasons"]
    assert "D5_REQUIRED_EVIDENCE_INCOMPLETE" in result["gate_verdict"]["reasons"]

@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({}, "D5_BASELINE_COMPARISON_FIELD_INVALID_delta_vs_best_d3_total_net_return"),
        ({"policy_total_net_return": -0.10, "best_d3_total_net_return": 0.05, "cost_round_trip_bp": 23}, "D5_BASELINE_COMPARISON_FIELD_INVALID_delta_vs_best_d3_total_net_return"),
        ({"policy_total_net_return": -0.10, "best_d3_total_net_return": 0.05, "delta_vs_best_d3_total_net_return": -0.15}, "D5_BASELINE_COMPARISON_FIELD_INVALID_cost_round_trip_bp"),
        ({"policy_total_net_return": -0.10, "best_d3_total_net_return": 0.05, "delta_vs_best_d3_total_net_return": "nan", "cost_round_trip_bp": 23}, "D5_BASELINE_COMPARISON_FIELD_INVALID_delta_vs_best_d3_total_net_return"),
        ({"policy_total_net_return": -0.10, "best_d3_total_net_return": 0.05, "delta_vs_best_d3_total_net_return": -0.15, "cost_round_trip_bp": 0}, "D5_BASELINE_COMPARISON_COST_MISMATCH"),
    ],
)
def test_daily_walk_forward_malformed_baseline_comparison_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
    reason: str,
):
    import stom_rl.daily_walk_forward as walk_forward

    prediction_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_prediction"
    portfolio_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_portfolio"
    prediction_run = _create_prediction_run(prediction_root)
    portfolio_run = _create_portfolio_run(portfolio_root)
    (portfolio_run / "baseline_comparison.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(walk_forward, "DEFAULT_PREDICTION_ROOT", prediction_root)
    monkeypatch.setattr(walk_forward, "DEFAULT_PORTFOLIO_ROOT", portfolio_root)

    result = run_daily_walk_forward(prediction_run_dir=prediction_run, portfolio_run_dir=portfolio_run, n_folds=5)

    assert result["gate_verdict"]["status"] == "NO-GO"
    assert result["gate_verdict"]["model_build_allowed"] is False
    assert result["gate_verdict"]["readiness_status"] == "D5_NO_GO_RESEARCH_ONLY_GATE"
    assert reason in result["gate_verdict"]["reasons"]
    assert "D5_REQUIRED_EVIDENCE_INCOMPLETE" in result["gate_verdict"]["reasons"]


def test_daily_walk_forward_invalid_baseline_comparison_encoding_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import stom_rl.daily_walk_forward as walk_forward

    prediction_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_prediction"
    portfolio_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_portfolio"
    prediction_run = _create_prediction_run(prediction_root)
    portfolio_run = _create_portfolio_run(portfolio_root)
    (portfolio_run / "baseline_comparison.json").write_bytes(b"\xff\xfe\x00")
    monkeypatch.setattr(walk_forward, "DEFAULT_PREDICTION_ROOT", prediction_root)
    monkeypatch.setattr(walk_forward, "DEFAULT_PORTFOLIO_ROOT", portfolio_root)

    result = run_daily_walk_forward(prediction_run_dir=prediction_run, portfolio_run_dir=portfolio_run, n_folds=5)

    assert result["gate_verdict"]["status"] == "NO-GO"
    assert result["gate_verdict"]["model_build_allowed"] is False
    assert "D5_BASELINE_COMPARISON_JSON_INVALID" in result["gate_verdict"]["reasons"]
    assert "D5_REQUIRED_EVIDENCE_INCOMPLETE" in result["gate_verdict"]["reasons"]

def test_daily_walk_forward_favorable_oos_still_research_locked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import stom_rl.daily_walk_forward as walk_forward

    prediction_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_prediction"
    portfolio_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_portfolio"
    prediction_run = _create_prediction_run(prediction_root)
    portfolio_run = _create_portfolio_run(portfolio_root)
    (portfolio_run / "baseline_comparison.json").write_text(
        json.dumps(
            {
                "policy_total_net_return": 1.0,
                "best_d3_total_net_return": 0.05,
                "delta_vs_best_d3_total_net_return": 0.95,
                "cost_round_trip_bp": 23,
            }
        ),
        encoding="utf-8",
    )
    reward_rows = []
    for idx in range(5, 15):
        reward_rows.append(
            {
                "split": "val+test",
                "date": f"2024-01-{idx + 1:02d}",
                "reward": 0.2,
                "turnover": 0.1,
                "exposure": 0.4,
                "invalid_action": False,
            }
        )
    _write_csv(portfolio_run / "reward_breakdown.csv", reward_rows)
    monkeypatch.setattr(walk_forward, "DEFAULT_PREDICTION_ROOT", prediction_root)
    monkeypatch.setattr(walk_forward, "DEFAULT_PORTFOLIO_ROOT", portfolio_root)

    result = run_daily_walk_forward(prediction_run_dir=prediction_run, portfolio_run_dir=portfolio_run, n_folds=5, top_k=1)

    assert result["gate_verdict"]["status"] == "NO-GO"
    assert result["gate_verdict"]["model_build_allowed"] is False
    assert result["gate_verdict"]["go_summary_allowed"] is False
    assert result["gate_verdict"]["paper_forward_allowed"] is False
    assert result["gate_verdict"]["live_broker_order_allowed"] is False
    assert result["gate_verdict"]["readiness_status"] == "D5_NO_GO_RESEARCH_ONLY_GATE"
    assert "D5_RESEARCH_ONLY_MODEL_BUILD_LOCK" in result["gate_verdict"]["reasons"]
