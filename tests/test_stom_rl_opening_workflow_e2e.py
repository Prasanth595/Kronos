import csv
import json
from pathlib import Path

from stom_rl.market_participant_studies import build_market_participant_studies
from stom_rl.opening_30m_rl_artifacts import write_opening_eval_artifacts
from stom_rl.opening_30m_rl_baselines import OpeningBaselineConfig, evaluate_opening_baselines
from stom_rl.opening_30m_rl_controls import write_opening_controls_artifact
from stom_rl.opening_30m_rl_leaderboard import evaluate_opening_workflow_leaderboard_row
from stom_rl.opening_30m_rl_train import OpeningTrainingConfig, run_opening_training_stage
from stom_rl.opening_30m_rl_workflow import OpeningWorkflowConfig, record_workflow_stage
from stom_rl.opening_30m_rl_runner import run_opening_workflow_stages
from stom_rl.orderbook_persistence import write_orderbook_persistence_artifact
from stom_rl.participant_pressure_features import build_participant_pressure_readiness
from tests.fixtures.stom_opening_rl import build_opening_fixture_frames
from webui import rl_dashboard
from webui.app import app as flask_app


def _episode_ids() -> tuple[tuple[str, ...], tuple[str, ...]]:
    return ("000250_20250103", "005930_20250106"), ("000660_20250107",)


def _mean_training_reward(training_payload):
    rows = training_payload.get("evaluation", [])
    if not rows:
        return -1.0, 0
    rewards = [float(row.get("reward", 0.0)) for row in rows]
    trades = sum(int(row.get("trade_count", 0)) for row in rows)
    return sum(rewards) / len(rewards), trades


def _write_leaderboard(path: Path, row) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "run_id",
        "baseline_policy",
        "target_cost_bps",
        "passes_cost_gate",
        "decision",
        "baseline_delta_pct",
        "trade_count",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerow(row)


def _write_workflow_summary(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_opening_workflow_fixture_e2e_reaches_dashboard_evidence(tmp_path, monkeypatch):
    frames = build_opening_fixture_frames()
    output_dir = tmp_path / "opening_e2e_run"
    train_episode_ids, eval_episode_ids = _episode_ids()

    workflow = run_opening_workflow_stages(
        frames,
        OpeningWorkflowConfig(run_id="opening_e2e_run", output_dir=output_dir),
        request_training=True,
    )
    training = run_opening_training_stage(
        frames,
        train_episode_ids=train_episode_ids,
        eval_episode_ids=eval_episode_ids,
        config=OpeningTrainingConfig(output_dir=output_dir / "training", total_timesteps=8, seed=404),
    )
    baseline = evaluate_opening_baselines(frames, OpeningBaselineConfig(cost_bps=23.0))
    eval_artifacts = write_opening_eval_artifacts(
        output_dir=output_dir,
        training_payload=training,
        baseline_payload=baseline,
        source_manifest_path=output_dir / "episodes" / "opening_episode_manifest_summary.json",
        seed=404,
        cost_bps=23.0,
    )
    controls = write_opening_controls_artifact(
        output_dir=output_dir,
        primary_verdict="GO_CANDIDATE",
        controls=({"control_type": "shuffled_participant_context", "verdict": "GO_CANDIDATE", "metric": "reward"},),
        seed=404,
    )
    build_participant_pressure_readiness(frames[0], output_dir=output_dir, decision_second=3)
    build_market_participant_studies(frames, output_dir=output_dir, decision_second=3)
    write_orderbook_persistence_artifact(frames[0], output_dir=output_dir, decision_second=3)
    rl_mean_reward, trade_count = _mean_training_reward(training)
    leaderboard_row = evaluate_opening_workflow_leaderboard_row(
        run_id="opening_e2e_run",
        rl_mean_return_pct=rl_mean_reward,
        baseline_delta_inputs=baseline["summary"]["baseline_delta_inputs"],
        controls_payload=controls,
        trade_count=trade_count,
        max_drawdown_pct=-1.0,
    )
    leaderboard_path = output_dir / "opening_leaderboard.csv"
    _write_leaderboard(leaderboard_path, leaderboard_row)

    workflow["feature_ablation_results"] = {
        "no_participant_pressure": {"verdict": "NO-GO", "baseline_delta_pct": -0.25}
    }
    workflow = record_workflow_stage(
        workflow,
        "training",
        {"status": training["status"], "evidence": training["artifacts"]["summary_json"]},
    )
    workflow = record_workflow_stage(
        workflow,
        "evaluation",
        {"status": "passed", "evidence": eval_artifacts["artifacts"]["summary_json"]},
    )
    workflow = record_workflow_stage(
        workflow,
        "controls",
        {"status": "passed", "evidence": controls["artifacts"]["summary_json"]},
    )
    workflow = record_workflow_stage(
        workflow,
        "cost_gate",
        {"status": "passed", "evidence": str(leaderboard_path)},
    )
    workflow = record_workflow_stage(
        workflow,
        "dashboard",
        {"status": "passed", "evidence": "dashboard loader/API/table smoke"},
    )
    workflow["verdict"] = "NO-GO"
    _write_workflow_summary(output_dir / "opening_30m_rl_workflow_summary.json", workflow)

    monkeypatch.setattr(rl_dashboard, "RL_RUN_ROOTS", [tmp_path])
    client = flask_app.test_client()

    detail = rl_dashboard.load_rl_run("opening_e2e_run")
    response = client.get("/api/rl/runs/opening_e2e_run")
    progress = client.get("/api/rl/progress").get_json()
    stages = rl_dashboard.load_rl_table("opening_e2e_run", "stages", limit=20)
    controls_table = rl_dashboard.load_rl_table("opening_e2e_run", "controls", limit=20)
    leaderboard = rl_dashboard.load_rl_table("opening_e2e_run", "leaderboard", limit=20)
    proxy = rl_dashboard.load_rl_table("opening_e2e_run", "proxy_availability", limit=20)
    participant = rl_dashboard.load_rl_table("opening_e2e_run", "participant_study_groups", limit=20)
    orderbook = rl_dashboard.load_rl_table("opening_e2e_run", "orderbook_persistence", limit=20)
    episodes = rl_dashboard.load_rl_table("opening_e2e_run", "episodes", limit=20)

    assert response.status_code == 200
    assert detail["artifact_type"] == "opening_30m_rl_workflow"
    assert detail["summary"]["verdict"] == "NO-GO"
    assert detail["strategy_context"]["is_live_ready"] is False
    assert detail["strategy_context"]["is_profit_model"] is False
    assert response.get_json()["strategy_context"]["label"] == "RL EXPERIMENT"
    assert stages["row_count"] >= 10
    assert controls_table["rows"][0]["control_type"] == "shuffled_participant_context"
    assert leaderboard["rows"][0]["baseline_policy"] == "ts_imb_same_decision_tp5_sl1_time"
    assert leaderboard["rows"][0]["passes_cost_gate"] is False
    assert proxy["row_count"] > 0
    assert participant["row_count"] > 0
    assert orderbook["row_count"] > 0
    assert episodes["row_count"] == 3
    assert progress["evidence"]["latest_opening_workflow_run"] == "opening_e2e_run"
    assert any(page["page"] == "Opening 30M RL Workflow" for page in progress["pages"])
