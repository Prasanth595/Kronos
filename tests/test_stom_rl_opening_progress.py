import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from webui import rl_dashboard  # noqa: E402
from webui.app import app as flask_app  # noqa: E402


def _write_opening_progress_run(root: Path, *, controls_status: str = "passed", cost_status: str = "passed") -> None:
    run = root / "opening_progress_run"
    run.mkdir()
    stages = [
        {"name": "contract", "status": "passed", "evidence": "contract"},
        {"name": "manifest", "status": "passed", "evidence": "episodes/opening_episode_manifest_summary.json"},
        {"name": "readiness_env", "status": "passed", "evidence": "env_contract"},
        {"name": "baseline", "status": "passed", "evidence": "baseline/opening_baseline_summary.json"},
        {"name": "training", "status": "passed", "evidence": "training/opening_training_summary.json"},
        {"name": "evaluation", "status": "passed", "evidence": "summary.json"},
        {"name": "controls", "status": controls_status, "evidence": "opening_negative_controls_summary.json", "reason": "NO-GO"},
        {"name": "cost_gate", "status": cost_status, "evidence": "opening_leaderboard.csv", "reason": "below_baseline"},
        {"name": "dashboard", "status": "passed", "evidence": "dashboard"},
    ]
    (run / "opening_30m_rl_workflow_summary.json").write_text(
        json.dumps(
            {
                "artifact_type": "opening_30m_rl_workflow",
                "mode": "opening_30m_rl_workflow",
                "run_id": "opening_progress_run",
                "verdict": "NO-GO" if controls_status != "passed" else "GO_CANDIDATE",
                "config": {"cost_bps": 23.0, "time_start": "090000", "time_end": "093000"},
                "stages": stages,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )


def _opening_page(progress: dict):
    return next(page for page in progress["pages"] if page["page"] == "Opening 30M RL Workflow")


def test_progress_api_summarizes_opening_workflow_stages(tmp_path, monkeypatch):
    _write_opening_progress_run(tmp_path)
    monkeypatch.setattr(rl_dashboard, "RL_RUN_ROOTS", [tmp_path])

    progress = rl_dashboard.load_rl_progress()
    response = flask_app.test_client().get("/api/rl/progress")
    page = _opening_page(progress)
    labels = {row["label"] for row in page["criteria"]}

    assert response.status_code == 200
    assert {
        "opening contract",
        "opening manifest",
        "opening env/readiness",
        "opening baseline",
        "opening training",
        "opening evaluation",
        "opening controls",
        "opening cost gate",
        "opening leaderboard",
        "opening dashboard",
    }.issubset(labels)
    assert page["progress_pct"] == 100
    assert page["status"] == "complete"


def test_progress_api_marks_opening_workflow_incomplete_when_controls_fail(tmp_path, monkeypatch):
    _write_opening_progress_run(tmp_path, controls_status="failed", cost_status="blocked")
    monkeypatch.setattr(rl_dashboard, "RL_RUN_ROOTS", [tmp_path])

    page = _opening_page(rl_dashboard.load_rl_progress())
    controls = next(row for row in page["criteria"] if row["label"] == "opening controls")
    cost_gate = next(row for row in page["criteria"] if row["label"] == "opening cost gate")

    assert page["progress_pct"] < 100
    assert page["status"] == "in_progress"
    assert controls["passed"] is False
    assert cost_gate["passed"] is False
    assert "NO-GO" in controls["evidence"]
    assert "below_baseline" in cost_gate["evidence"]
