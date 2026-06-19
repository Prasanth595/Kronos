import csv
import json
from pathlib import Path

from stom_rl.daily_signal_quality import load_lagged_portfolio_context, run_signal_quality_audit
from stom_rl.daily_signal_quality_batch import run_signal_quality_batch


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def test_lagged_portfolio_context_deduplicates_same_date_rows(tmp_path: Path) -> None:
    portfolio_dir = tmp_path / "portfolio"
    _write_csv(
        portfolio_dir / "drawdown.csv",
        [
            {"split": "val", "date": "20250102", "reward": "0.100", "current_drawdown": "-0.100"},
            {"split": "val+test", "date": "20250102", "reward": "-0.100", "current_drawdown": "-0.200"},
            {"split": "test", "date": "20250103", "reward": "0.050", "current_drawdown": "-0.050"},
        ],
        ["split", "date", "reward", "current_drawdown"],
    )

    context = load_lagged_portfolio_context(portfolio_dir)

    assert context["20250102"]["past_return_volatility"] == 0.0
    assert context["20250102"]["drawdown"] == 0.0
    assert context["20250103"]["past_return_volatility"] == 0.0
    assert context["20250103"]["drawdown"] == -0.2
    assert context["20250103"]["past_return_volatility_source"].startswith("drawdown.csv lagged date-deduplicated")


def test_signal_quality_audit_emits_frozen_causal_diagnostics(tmp_path: Path) -> None:
    prediction_dir = tmp_path / "prediction"
    wf_dir = tmp_path / "walk_forward"
    portfolio_dir = tmp_path / "portfolio"
    rows = [
        {"code": "000001", "date": "20250102", "split": "train", "score_supervised_linear_ranker": "0.030", "future_return_1d": "0.020", "future_direction_1d": "1"},
        {"code": "000002", "date": "20250102", "split": "train", "score_supervised_linear_ranker": "0.010", "future_return_1d": "-0.010", "future_direction_1d": "0"},
        {"code": "000001", "date": "20250103", "split": "val", "score_supervised_linear_ranker": "0.006", "future_return_1d": "0.010", "future_direction_1d": "1"},
        {"code": "000002", "date": "20250103", "split": "val", "score_supervised_linear_ranker": "-0.002", "future_return_1d": "-0.005", "future_direction_1d": "0"},
        {"code": "000003", "date": "20250106", "split": "test", "score_supervised_linear_ranker": "0.004", "future_return_1d": "0.003", "future_direction_1d": "1"},
        {"code": "000004", "date": "20250106", "split": "test", "score_supervised_linear_ranker": "-0.004", "future_return_1d": "-0.004", "future_direction_1d": "0"},
        {"code": "000001", "date": "20250107", "split": "test", "score_supervised_linear_ranker": "0.021", "future_return_1d": "0.002", "future_direction_1d": "1"},
        {"code": "000002", "date": "20250107", "split": "test", "score_supervised_linear_ranker": "0.001", "future_return_1d": "-0.002", "future_direction_1d": "0"},
    ]
    _write_csv(
        prediction_dir / "predictions.csv",
        rows,
        [
            "code",
            "date",
            "split",
            "score_supervised_linear_ranker",
            "future_return_1d",
            "future_direction_1d",
        ],
    )
    _write_csv(
        wf_dir / "fold_assignments.csv",
        [
            {"fold_id": "F01", "date": "20250106", "role": "test"},
            {"fold_id": "F02", "date": "20250107", "role": "test"},
        ],
        ["fold_id", "date", "role"],
    )
    _write_csv(
        portfolio_dir / "drawdown.csv",
        [
            {"split": "train", "date": "20250102", "reward": "0.000", "current_drawdown": "0.000"},
            {"split": "val", "date": "20250103", "reward": "-0.010", "current_drawdown": "-0.010"},
            {"split": "test", "date": "20250106", "reward": "0.020", "current_drawdown": "0.000"},
            {"split": "test", "date": "20250107", "reward": "-0.030", "current_drawdown": "-0.030"},
        ],
        ["split", "date", "reward", "current_drawdown"],
    )


    manifest = run_signal_quality_audit(
        prediction_dir=prediction_dir,
        walk_forward_dir=wf_dir,
        portfolio_dir=portfolio_dir,
        output_root=tmp_path / "out",
        run_id="unit_signal_quality",
    )

    assert manifest["status"] == "COMPLETED_RESEARCH_ONLY"
    assert manifest["promotion_status"] == "NO-GO_RESEARCH_ONLY"
    assert manifest["threshold_policy"] == "frozen_absolute_no_quantile_search_no_oos_retune"
    assert manifest["score_thresholds"] == [0.001, 0.005, 0.02]
    assert manifest["cost_sensitivity_bp"] == [0, 23, 46]
    assert manifest["model_build_allowed"] is False
    assert manifest["paper_forward_allowed"] is False
    assert manifest["live_broker_order_allowed"] is False
    assert manifest["abstention_reasons_requirement"].startswith("not_applicable_pure_signal_quality")

    artifacts = {key: Path(value) for key, value in manifest["required_artifacts"].items()}
    for path in artifacts.values():
        assert path.exists(), path

    bucket_rows = list(csv.DictReader(artifacts["signal_quality_bucket_metrics"].open(encoding="utf-8")))
    assert {row["split"] for row in bucket_rows} >= {"train", "val", "test"}
    assert {row["fold"] for row in bucket_rows if row["split"] == "test"} >= {"F01", "F02"}
    assert {"score_magnitude_bucket", "score_margin_bucket", "d3_confidence_bucket"} <= {
        row["bucket_name"] for row in bucket_rows
    }
    assert {row["cost_bp"] for row in bucket_rows} == {"0", "23", "46"}
    assert all(row["source_timing"] == "t/current/pre_action" for row in bucket_rows)
    assert all(row["future_label_used_for_bucket"] == "False" for row in bucket_rows)
    assert all(row["future_label_used_for_evaluation"] == "True" for row in bucket_rows)

    risk_rows = list(csv.DictReader(artifacts["risk_proxy_bucket_metrics"].open(encoding="utf-8")))
    assert {"recent_score_volatility_bucket", "past_return_volatility_bucket", "drawdown_bucket"} <= {
        row["proxy_name"] for row in risk_rows
    }
    assert {row["cost_bp"] for row in risk_rows} == {"0", "23", "46"}
    assert all(row["source_timing"] for row in risk_rows)
    assert all(row["future_label_used_for_proxy"] == "False" for row in risk_rows)
    assert any(row["proxy_status"] == "AVAILABLE_T_MINUS_1_GENERATED_PATH" for row in risk_rows)
    assert any(float(row["policy_delta_vs_d3"]) != 0.0 for row in risk_rows)
    assert any(float(row["turnover_proxy"]) != 0.0 for row in risk_rows)


    baseline_rows = list(csv.DictReader(artifacts["baseline_control_metrics"].open(encoding="utf-8")))
    assert {"no_trade_cash", "shuffle_control", "equal_weight_topk", "frozen_d3_baseline"} <= {
        row["baseline_strategy"] for row in baseline_rows
    }
    assert {row["cost_bp"] for row in baseline_rows} == {"0", "23", "46"}
    assert all(row["future_label_used_for_selection"] == "False" for row in baseline_rows)
    assert all(row["future_label_used_for_evaluation"] == "True" for row in baseline_rows)

    leakage = json.loads(artifacts["signal_quality_leakage_audit"].read_text(encoding="utf-8"))
    assert leakage["verdict"] == "PASS"
    feature_rows = {row["feature_name"]: row for row in leakage["rows"]}
    assert feature_rows["score_magnitude_bucket"]["future_label_used"] is False
    assert feature_rows["future_return_1d"]["verdict"] == "PASS_EVALUATION_LABEL_ONLY"

    stored_manifest = json.loads(artifacts["signal_quality_manifest"].read_text(encoding="utf-8"))
    assert stored_manifest["source_hashes"]["predictions_csv"]
    assert stored_manifest["no_future_label_policy"] == "future_return_1d is evaluation_label_only after bucket/proxy construction"
    assert stored_manifest["baseline_controls_measured"] is True
    assert stored_manifest["row_counts"]["baseline_control_metrics"] == len(baseline_rows)
    assert stored_manifest["source_hashes"]["drawdown_csv"]
def test_signal_quality_batch_writes_reproducible_manifest(tmp_path: Path) -> None:
    prediction_dir = tmp_path / "prediction"
    wf_dir = tmp_path / "walk_forward"
    portfolio_dir = tmp_path / "portfolio"
    _write_csv(
        prediction_dir / "predictions.csv",
        [
            {"code": "000001", "date": "20250102", "split": "train", "score_supervised_linear_ranker": "0.030", "future_return_1d": "0.020", "future_direction_1d": "1"},
            {"code": "000002", "date": "20250102", "split": "train", "score_supervised_linear_ranker": "0.010", "future_return_1d": "-0.010", "future_direction_1d": "0"},
            {"code": "000001", "date": "20250103", "split": "val", "score_supervised_linear_ranker": "0.006", "future_return_1d": "0.010", "future_direction_1d": "1"},
            {"code": "000002", "date": "20250103", "split": "val", "score_supervised_linear_ranker": "-0.002", "future_return_1d": "-0.005", "future_direction_1d": "0"},
            {"code": "000001", "date": "20250106", "split": "test", "score_supervised_linear_ranker": "0.004", "future_return_1d": "0.003", "future_direction_1d": "1"},
            {"code": "000002", "date": "20250106", "split": "test", "score_supervised_linear_ranker": "-0.004", "future_return_1d": "-0.004", "future_direction_1d": "0"},
        ],
        ["code", "date", "split", "score_supervised_linear_ranker", "future_return_1d", "future_direction_1d"],
    )
    _write_csv(
        wf_dir / "fold_assignments.csv",
        [{"fold_id": "F01", "date": "20250106", "role": "test"}],
        ["fold_id", "date", "role"],
    )
    _write_csv(
        portfolio_dir / "drawdown.csv",
        [
            {"split": "train", "date": "20250102", "reward": "0.000", "current_drawdown": "0.000"},
            {"split": "val", "date": "20250103", "reward": "-0.010", "current_drawdown": "-0.010"},
            {"split": "test", "date": "20250106", "reward": "0.020", "current_drawdown": "0.000"},
        ],
        ["split", "date", "reward", "current_drawdown"],
    )

    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "batch_id": "unit_signal_quality_batch",
                "defaults": {
                    "prediction_dir": str(prediction_dir),
                    "walk_forward_dir": str(wf_dir),
                    "cost_bp": 23,
                    "portfolio_dir": str(portfolio_dir),
                },
                "scenarios": [
                    {"scenario_id": "score_magnitude_audit_v1", "diagnostic_focus": "score_magnitude", "status": "WATCH"},
                    {"scenario_id": "risk_proxy_audit_v1", "diagnostic_focus": "risk_proxy", "status": "WATCH"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest = run_signal_quality_batch(
        plan_path=plan_path,
        batch_root=tmp_path / "batches",
        output_root=tmp_path / "runs",
    )

    assert manifest["batch_id"] == "unit_signal_quality_batch"
    assert manifest["status"] == "COMPLETED_RESEARCH_ONLY"
    assert manifest["scenario_count"] == 2
    assert manifest["completed_count"] == 2
    assert manifest["failed_count"] == 0
    assert manifest["gate_status_counts"] == {"WATCH": 2}
    assert manifest["cost_sensitivity_bp"] == [0, 23, 46]
    assert manifest["model_build_allowed"] is False
    assert manifest["paper_forward_allowed"] is False
    assert manifest["live_broker_order_allowed"] is False
    assert Path(manifest["artifact_paths"]["scenario_batch_manifest"]).exists()
    assert Path(manifest["artifact_paths"]["scenario_batch_plan"]).exists()
    for row in manifest["runs"]:
        assert row["promotion_status"] == "NO-GO_RESEARCH_ONLY"
        assert row["cost_sensitivity_bp"] == [0, 23, 46]
        assert row["baseline_controls"] == ["no_trade_cash", "shuffle_control", "equal_weight_topk", "frozen_d3_baseline"]
        assert Path(row["artifact_paths"]["signal_quality_manifest"]).exists()
        assert Path(row["artifact_paths"]["baseline_control_metrics"]).exists()
        assert row["baseline_control_metrics"]
