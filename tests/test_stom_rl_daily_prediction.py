import csv
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stom_rl.daily_prediction import BASELINE_STRATEGIES, D3_BLOCKED_USES_WHEN_WATCH, D3_REQUIRED_EVIDENCE, run_daily_prediction  # noqa: E402

FEATURE_COLUMNS = [
    "return_1d",
    "return_5d",
    "volatility_5d",
    "volume_ratio_5d",
    "hl_range",
    "gap_from_prev_close",
    "foreign_holding_ratio",
    "institutional_net_buy",
]
LABEL_COLUMNS = ["future_return_1d", "future_direction_1d", "future_rank_pct_1d"]


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _create_dataset_run(root: Path) -> Path:
    run_dir = root / "dataset_unit"
    run_dir.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "manifest_sha": "dataset-sha-unit",
        "artifact_scope": "UNIT",
        "price_basis": "unknown",
        "price_basis_evidence": "unit unknown",
        "price_basis_status": "UNKNOWN_CONFIRMED",
        "decision_grade_return_status": "BLOCKED_UNTIL_PRICE_BASIS_VERIFIED",
        "universe_verdict": "WATCH_HEURISTIC_UNIVERSE",
        "universe_review_status": "WATCH_REQUIRES_OFFICIAL_OR_MANUAL_REVIEW",
        "official_metadata_status": "MISSING",
        "official_metadata_coverage_status": "MISSING",
        "universe_certification_status": "BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW",
        "feature_columns": FEATURE_COLUMNS,
        "label_columns": LABEL_COLUMNS,
        "model_readiness": "DATASET_RESEARCH_PREVIEW_BLOCKED_BY_UPSTREAM_GUARDRAILS",
        "decision_grade_status": "BLOCKED_BY_UPSTREAM_D0_D1_GUARDRAILS",
        "upstream_gate_blockers": [
            "D0_PRICE_BASIS_NOT_VERIFIED",
            "D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED",
        ],
    }
    (run_dir / "dataset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    feature_rows = []
    label_rows = []
    split_rows = []
    dates = [f"2024-01-{idx:02d}" for idx in range(1, 10)]
    split_by_date = {date: ("train" if idx < 5 else "val" if idx < 7 else "test") for idx, date in enumerate(dates)}
    for idx, date in enumerate(dates):
        for offset, code in enumerate(["000001", "000002", "000003"]):
            momentum = (offset - 1) * 0.02 + idx * 0.001
            future = momentum * 0.5
            table = f"A{code}"
            feature_rows.append(
                {
                    "date": date,
                    "table": table,
                    "code": code,
                    "return_1d": momentum / 2,
                    "return_5d": momentum,
                    "volatility_5d": 0.01 + offset * 0.005,
                    "volume_ratio_5d": 1.0 + offset * 0.1,
                    "hl_range": 0.02,
                    "gap_from_prev_close": momentum / 3,
                    "foreign_holding_ratio": 2.0 + offset,
                    "institutional_net_buy": 100.0 * offset,
                }
            )
            label_rows.append(
                {
                    "date": date,
                    "table": table,
                    "code": code,
                    "future_return_1d": future,
                    "future_direction_1d": int(future > 0),
                    "future_rank_pct_1d": offset / 2,
                }
            )
            split_rows.append(
                {
                    "date": date,
                    "table": table,
                    "code": code,
                    "split": split_by_date[date],
                    "eligible_for_training": True,
                    "block_reason": "",
                }
            )
    _write_csv(run_dir / "feature_panel.csv", feature_rows)
    _write_csv(run_dir / "label_panel.csv", label_rows)
    _write_csv(run_dir / "split_assignments.csv", split_rows)
    return run_dir


def test_run_daily_prediction_builds_baselines_and_watch_verdict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import stom_rl.daily_prediction as prediction

    dataset_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_dataset"
    run_dir = _create_dataset_run(dataset_root)
    monkeypatch.setattr(prediction, "DEFAULT_DATASET_ROOT", dataset_root)
    result = run_daily_prediction(dataset_run_dir=run_dir, top_k=2)
    manifest = result["manifest"]
    assert manifest["fit_split"] == "train"
    assert manifest["no_oos_retuning"] is True
    assert manifest["price_basis"] == "unknown"
    assert manifest["universe_verdict"] == "WATCH_HEURISTIC_UNIVERSE"
    assert manifest["cost_assumption_round_trip_bp"] == 23
    assert manifest["status"] == "WATCH"
    assert manifest["readiness_status"] == "D3_WATCH_RESEARCH_ONLY"
    assert manifest["model_build_allowed"] is False
    assert manifest["go_summary_allowed"] is False
    assert manifest["verdict"]["status"] == "WATCH"
    assert manifest["verdict"]["readiness_status"] == "D3_WATCH_RESEARCH_ONLY"
    assert manifest["verdict"]["go_summary_allowed"] is False
    assert manifest["verdict"]["model_build_allowed"] is False
    assert manifest["dataset_run_id"] == run_dir.name
    assert manifest["dataset_upstream_gate_blockers"] == [
        "D0_PRICE_BASIS_NOT_VERIFIED",
        "D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED",
    ]
    assert manifest["d3_gate_blockers"] == [
        "D0_PRICE_BASIS_NOT_VERIFIED",
        "D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED",
        "D5_WALK_FORWARD_NOT_PASS",
        "D3_BASELINE_WATCH_RESEARCH_ONLY",
    ]
    assert manifest["d3_required_evidence"] == list(D3_REQUIRED_EVIDENCE)
    assert manifest["d3_blocked_uses"] == list(D3_BLOCKED_USES_WHEN_WATCH)
    assert manifest["baseline_freeze_contract"]["deterministic_shuffle_method"] == "sha256(date:code)_ascending"
    assert manifest["baseline_freeze_contract"]["frozen_dataset_manifest_sha"] == "dataset-sha-unit"
    strategies = {row["strategy"] for row in result["baseline_metrics"]}
    assert set(BASELINE_STRATEGIES).issubset(strategies)
    assert "shuffle_control" in strategies
    assert manifest["models"]["supervised_linear_ranker"]["train_row_count"] == 15
    assert manifest["models"]["supervised_linear_ranker"]["training_policy"] == "fit_train_split_only_no_oos_retuning"
    cash = next(row for row in result["baseline_metrics"] if row["strategy"] == "no_trade_cash")
    assert cash["total_net_return"] == 0.0
    market_proxy = next(row for row in result["baseline_metrics"] if row["strategy"] == "market_proxy")
    assert market_proxy["mean_turnover"] == 1.0
    shuffle = next(row for row in result["baseline_metrics"] if row["strategy"] == "shuffle_control")
    assert shuffle["strategy_family"] == "control"
    assert shuffle["is_shuffle_control"] is True
    assert shuffle["positions"] > 0
    assert all("delta_vs_shuffle_control_total_net_return" in row for row in result["baseline_metrics"])
    assert all("delta_vs_best_rule_baseline_total_net_return" in row for row in result["baseline_metrics"])
    summary = manifest["baseline_delta_summary"]
    metrics_by_strategy = {row["strategy"]: row for row in result["baseline_metrics"]}
    for row in result["baseline_metrics"]:
        assert row["delta_vs_shuffle_control_total_net_return"] == pytest.approx(
            row["total_net_return"] - shuffle["total_net_return"]
        )
        assert row["delta_vs_best_rule_baseline_total_net_return"] == pytest.approx(
            row["total_net_return"] - metrics_by_strategy[summary["best_rule_baseline_strategy"]]["total_net_return"]
        )
    best_rule = max(
        (row for row in result["baseline_metrics"] if row["strategy_family"] == "rule_baseline"),
        key=lambda row: row["total_net_return"],
    )
    best_supervised = max(
        (row for row in result["baseline_metrics"] if row["strategy_family"] == "supervised"),
        key=lambda row: row["total_net_return"],
    )
    assert result["baseline_delta_summary"] == summary
    assert summary["shuffle_control_strategy"] == "shuffle_control"
    assert summary["best_rule_baseline_strategy"] in strategies
    assert summary["best_supervised_strategy"] in {"supervised_linear_ranker", "supervised_direction_classifier"}
    assert summary["model_build_allowed"] is False
    assert summary["go_summary_allowed"] is False
    assert summary["readiness_status"] == "D3_WATCH_RESEARCH_ONLY"
    assert summary["d3_gate_blockers"] == manifest["d3_gate_blockers"]
    assert summary["deterministic_shuffle_method"] == "sha256(date:code)_ascending"
    assert summary["best_rule_baseline_strategy"] == best_rule["strategy"]
    assert summary["best_supervised_strategy"] == best_supervised["strategy"]
    assert summary["best_supervised_delta_vs_best_rule_baseline"] == pytest.approx(best_supervised["total_net_return"] - best_rule["total_net_return"])
    assert summary["best_supervised_delta_vs_shuffle_control"] == pytest.approx(best_supervised["total_net_return"] - shuffle["total_net_return"])
    repeat = run_daily_prediction(dataset_run_dir=run_dir, top_k=2)
    shuffle_positions = [(row["date"], row["rank"], row["code"]) for row in result["topk_positions"] if row["strategy"] == "shuffle_control"]
    repeat_shuffle_positions = [(row["date"], row["rank"], row["code"]) for row in repeat["topk_positions"] if row["strategy"] == "shuffle_control"]
    assert repeat_shuffle_positions == shuffle_positions
    assert result["topk_positions"]
    assert {row["code"] for row in result["topk_positions"]} <= {"000001", "000002", "000003"}
    assert all(row["split"] in {"val", "test"} for row in result["topk_positions"])
    assert result["calibration"]

def test_run_daily_prediction_treats_unverified_price_basis_as_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import stom_rl.daily_prediction as prediction

    dataset_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_dataset"
    run_dir = _create_dataset_run(dataset_root)
    manifest_path = run_dir / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "price_basis": "raw",
            "price_basis_status": "UNVERIFIED",
            "decision_grade_return_status": "READY_FOR_DECISION_GRADE_RETURNS",
            "universe_verdict": "OFFICIAL_OR_MANUAL_REVIEWED",
            "universe_review_status": "OFFICIAL_OR_MANUAL_REVIEWED",
            "official_metadata_status": "OFFICIAL_VERIFIED",
            "official_metadata_coverage_status": "COMPLETE",
            "universe_certification_status": "OFFICIAL_OR_MANUAL_REVIEWED",
            "upstream_gate_blockers": [],
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(prediction, "DEFAULT_DATASET_ROOT", dataset_root)

    result = run_daily_prediction(dataset_run_dir=run_dir, top_k=2)

    assert result["manifest"]["price_basis"] == "raw"
    assert "D0_PRICE_BASIS_NOT_VERIFIED" in result["manifest"]["d3_gate_blockers"]
    assert "D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED" not in result["manifest"]["d3_gate_blockers"]


def test_write_prediction_artifacts_rejects_escape_and_duplicate_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import stom_rl.daily_prediction as prediction

    dataset_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_dataset"
    prediction_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_prediction"
    run_dir = _create_dataset_run(dataset_root)
    monkeypatch.setattr(prediction, "DEFAULT_DATASET_ROOT", dataset_root)
    monkeypatch.setattr(prediction, "DEFAULT_PREDICTION_ROOT", prediction_root)
    result = run_daily_prediction(dataset_run_dir=run_dir, top_k=2)
    written = prediction.write_prediction_artifacts(result, run_id="prediction_unit")
    assert Path(written["prediction_manifest_path"]).exists()
    assert Path(written["baseline_metrics_path"]).exists()
    assert Path(written["model_metrics_path"]).exists()
    assert Path(written["baseline_delta_summary_path"]).exists()
    assert Path(written["topk_positions_path"]).exists()
    assert Path(written["predictions_path"]).exists()
    manifest = json.loads(Path(written["prediction_manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["run_id"] == "prediction_unit"
    assert manifest["status"] == "WATCH"
    assert manifest["readiness_status"] == "D3_WATCH_RESEARCH_ONLY"
    assert manifest["model_build_allowed"] is False
    assert manifest["go_summary_allowed"] is False
    assert manifest["artifact_hashes"]["baseline_metrics"]
    assert written["prediction_manifest_sha256"]
    assert written["artifact_hashes"]["prediction_manifest"] == written["prediction_manifest_sha256"]
    assert manifest["verdict"]["status"] == "WATCH"
    assert manifest["verdict"]["readiness_status"] == "D3_WATCH_RESEARCH_ONLY"
    assert manifest["baseline_delta_summary"]["shuffle_control_strategy"] == "shuffle_control"
    with pytest.raises(FileExistsError):
        prediction.write_prediction_artifacts(result, run_id="prediction_unit")
    with pytest.raises(ValueError):
        prediction.write_prediction_artifacts(result, artifact_root=tmp_path / "elsewhere", run_id="bad")
    with pytest.raises(ValueError):
        prediction.write_prediction_artifacts(result, run_id="..")
