import json
from pathlib import Path

import pytest

from stom_rl import daily_scenario_runner as runner
from stom_rl import daily_scenario_batch as batch


def test_daily_model_scenario_runner_writes_locked_manifest(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "DEFAULT_SCENARIO_ROOT", tmp_path / "scenarios")

    def fake_dataset(**kwargs):
        calls.append(("dataset", kwargs))
        out = tmp_path / "dataset" / kwargs["run_id"]
        out.mkdir(parents=True, exist_ok=True)
        return {
            "dataset": {"manifest": {"status": "PASS"}},
            "written": {"artifact_dir": str(out), "dataset_manifest_path": str(out / "dataset_manifest.json")},
        }

    def fake_prediction(**kwargs):
        calls.append(("prediction", kwargs))
        out = tmp_path / "prediction" / kwargs["run_id"]
        out.mkdir(parents=True, exist_ok=True)
        return {
            "result": {"manifest": {"status": "WATCH"}},
            "written": {"artifact_dir": str(out), "prediction_manifest_path": str(out / "prediction_manifest.json")},
        }

    def fake_rl(**kwargs):
        calls.append(("rl", kwargs))
        out = tmp_path / "portfolio" / kwargs["run_id"]
        out.mkdir(parents=True, exist_ok=True)
        return {
            "result": {"manifest": {"status": "RESEARCH_ONLY"}},
            "written": {"artifact_dir": str(out), "rl_manifest_path": str(out / "rl_manifest.json")},
        }

    def fake_walk_forward(**kwargs):
        calls.append(("walk_forward", kwargs))
        out = tmp_path / "walk_forward" / kwargs["run_id"]
        out.mkdir(parents=True, exist_ok=True)
        return {
            "result": {
                "gate_verdict": {
                    "status": "NO-GO",
                    "readiness_status": "D5_NO_GO_RESEARCH_ONLY_GATE",
                    "selected_strategy": "equal_weight_topk_momentum",
                    "n_folds": 5,
                    "purge_days": 5,
                    "embargo_days": 5,
                    "cost_sensitivity_bp": [0, 23, 46],
                    "reasons": ["RESEARCH_ONLY_NO_PROFIT_LIVE_BROKER_ORDER_CLAIM"],
                }
            },
            "written": {
                "artifact_dir": str(out),
                "walk_forward_manifest_path": str(out / "walk_forward_manifest.json"),
                "gate_verdict_path": str(out / "gate_verdict.json"),
            },
        }

    monkeypatch.setattr(runner, "build_and_write_daily_ohlcv_dataset", fake_dataset)
    monkeypatch.setattr(runner, "run_and_write_daily_prediction", fake_prediction)
    monkeypatch.setattr(runner, "run_and_write_daily_rl", fake_rl)
    monkeypatch.setattr(runner, "run_and_write_daily_walk_forward", fake_walk_forward)

    manifest = runner.run_daily_model_scenario(
        run_id="scenario_unit",
        overwrite=True,
        max_symbols=8,
        max_rows_per_symbol=120,
        candidate_limit=10,
        max_positions=3,
        episodes=3,
        action_filter_mode="confidence_abstain_v1",
    )

    assert [name for name, _ in calls] == ["dataset", "prediction", "rl", "walk_forward"]
    assert calls[0][1]["max_symbols"] == 8
    assert calls[2][1]["candidate_limit"] == 10
    assert calls[2][1]["action_filter_mode"] == "confidence_abstain_v1"
    assert calls[3][1]["purge_days"] == 5
    assert manifest["status"] == "NO-GO"
    assert manifest["readiness_status"] == "D5_NO_GO_RESEARCH_ONLY_GATE"
    assert manifest["model_build_allowed"] is False
    assert manifest["paper_forward_allowed"] is False
    assert manifest["live_broker_order_allowed"] is False
    assert manifest["gate_verdict_summary"]["cost_sensitivity_bp"] == [0, 23, 46]

    manifest_path = Path(manifest["artifact_paths"]["scenario_manifest"])
    assert manifest_path.is_file()
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted["run_id"] == "scenario_unit"
    assert persisted["artifact_paths"]["candidate_generation_config"].endswith("candidate_generation_config.json")


def test_daily_model_scenario_runner_rejects_unsafe_run_id(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "DEFAULT_SCENARIO_ROOT", tmp_path / "scenarios")
    with pytest.raises(ValueError, match="run_id"):
        runner.run_daily_model_scenario(run_id="../bad")

def test_daily_scenario_batch_runs_multiple_locked_scenarios(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(batch, "DEFAULT_SCENARIO_BATCH_ROOT", tmp_path / "batches")

    def fake_run_daily_model_scenario(**kwargs):
        calls.append(kwargs)
        run_id = kwargs["run_id"]
        out = tmp_path / "scenarios" / run_id
        out.mkdir(parents=True, exist_ok=True)
        return {
            "run_id": run_id,
            "status": "NO-GO",
            "readiness_status": "D5_NO_GO_RESEARCH_ONLY_GATE",
            "artifact_paths": {"scenario_manifest": str(out / "scenario_manifest.json")},
            "gate_verdict_summary": {
                "status": "NO-GO",
                "readiness_status": "D5_NO_GO_RESEARCH_ONLY_GATE",
                "selected_strategy": "equal_weight_topk_momentum",
                "n_folds": kwargs["n_folds"],
                "purge_days": kwargs["purge_days"],
                "embargo_days": kwargs["embargo_days"],
                "cost_sensitivity_bp": [0, 23, 46],
                "reasons": ["RESEARCH_ONLY_NO_PROFIT_LIVE_BROKER_ORDER_CLAIM"],
            },
        }

    monkeypatch.setattr(batch, "run_daily_model_scenario", fake_run_daily_model_scenario)

    plan = {
        "batch_id": "batch_unit",
        "defaults": {
            "max_symbols": 8,
            "max_rows_per_symbol": 120,
            "quality_table_limit": 0,
            "episodes": 3,
            "candidate_limit": 10,
            "max_positions": 3,
            "n_folds": 5,
            "top_k": 10,
            "purge_days": 5,
            "embargo_days": 5,
        },
        "scenarios": [
            {"scenario_id": "seed7", "overrides": {"rl_seed": 7, "wf_seed": 17}},
            {"scenario_id": "seed11", "overrides": {"rl_seed": 11, "wf_seed": 31, "action_filter_mode": "margin_abstain_v1"}},
        ],
    }

    manifest = batch.run_daily_scenario_batch(plan=plan, overwrite=True)

    assert [call["run_id"] for call in calls] == ["batch_unit__seed7", "batch_unit__seed11"]
    assert calls[0]["max_symbols"] == 8
    assert calls[1]["rl_seed"] == 11
    assert calls[1]["action_filter_mode"] == "margin_abstain_v1"
    assert manifest["mode"] == "daily_ohlcv_model_scenario_batch"
    assert manifest["platform_stage"] == "SCENARIO_BATCH_RUNNER_MVP"
    assert manifest["scenario_count"] == 2
    assert manifest["failed_count"] == 0
    assert manifest["gate_status_counts"] == {"NO-GO": 2}
    assert manifest["model_build_allowed"] is False
    assert manifest["paper_forward_allowed"] is False
    assert manifest["live_broker_order_allowed"] is False
    assert all(row["cost_sensitivity_bp"] == [0, 23, 46] for row in manifest["comparison_rows"])

    manifest_path = Path(manifest["artifact_paths"]["scenario_batch_manifest"])
    assert manifest_path.is_file()
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted["batch_id"] == "batch_unit"
    assert persisted["artifact_paths"]["scenario_batch_plan"].endswith("scenario_batch_plan.json")


def test_daily_scenario_batch_rejects_sub_gate_folds(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "DEFAULT_SCENARIO_BATCH_ROOT", tmp_path / "batches")
    plan = {
        "batch_id": "bad_batch",
        "defaults": {"n_folds": 4, "purge_days": 5, "embargo_days": 5},
        "scenarios": [{"scenario_id": "bad"}],
    }

    with pytest.raises(ValueError, match="n_folds"):
        batch.run_daily_scenario_batch(plan=plan, overwrite=True)
