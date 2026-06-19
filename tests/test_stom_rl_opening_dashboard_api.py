import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from webui import rl_dashboard  # noqa: E402
from webui.app import app as flask_app  # noqa: E402


def _write_csv(path: Path, header: str, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8-sig")


def _write_opening_workflow_fixture(root: Path) -> None:
    run = root / "opening_workflow_run"
    run.mkdir()
    (run / "opening_30m_rl_workflow_summary.json").write_text(
        json.dumps(
            {
                "artifact_type": "opening_30m_rl_workflow",
                "mode": "opening_30m_rl_workflow",
                "run_id": "opening_workflow_run",
                "verdict": "NO-GO",
                "config": {"cost_bps": 23.0, "time_start": "090000", "time_end": "093000"},
                "strategy_context": {
                    "label": "RL EXPERIMENT",
                    "is_live_ready": False,
                    "is_profit_model": False,
                },
                "stages": [
                    {"name": "contract", "status": "passed", "evidence": "contract"},
                    {"name": "controls", "status": "passed", "evidence": "controls"},
                ],
                "guardrails": {"baseline": "ts_imb RULE baseline"},
            }
        ),
        encoding="utf-8-sig",
    )
    (run / "opening_negative_controls_summary.json").write_text(
        json.dumps(
            {
                "artifact_type": "opening_30m_negative_controls",
                "final_verdict": "NO-GO",
                "negative_control_blocked_go": True,
                "controls": [
                    {
                        "control_type": "shuffled_participant_context",
                        "verdict": "GO_CANDIDATE",
                        "seed": 100,
                    }
                ],
            }
        ),
        encoding="utf-8-sig",
    )
    _write_csv(
        run / "opening_leaderboard.csv",
        "run_id,baseline_policy,passes_cost_gate,decision",
        ["opening_workflow_run,ts_imb_same_decision_tp5_sl1_time,False,NO-GO"],
    )
    _write_csv(run / "actions.csv", "episode_id,policy_action_space", ["000250_20250103,fixed_entry_exit_only"])
    _write_csv(run / "trades.csv", "episode_id,trade_count,cost_model", ["000250_20250103,0,23bp_marketable_fill"])
    _write_csv(run / "episodes.csv", "episode_id,split", ["000250_20250103,eval"])


def test_dashboard_loads_opening_workflow_run_read_only(tmp_path, monkeypatch):
    _write_opening_workflow_fixture(tmp_path)
    monkeypatch.setattr(rl_dashboard, "RL_RUN_ROOTS", [tmp_path])

    detail = rl_dashboard.load_rl_run("opening_workflow_run")
    client = flask_app.test_client()
    response = client.get("/api/rl/runs/opening_workflow_run")

    assert response.status_code == 200
    payload = response.get_json()
    assert detail["artifact_type"] == "opening_30m_rl_workflow"
    assert payload["artifact_type"] == "opening_30m_rl_workflow"
    assert payload["strategy_context"]["label"] == "RL EXPERIMENT"
    assert payload["strategy_context"]["is_live_ready"] is False
    assert payload["strategy_context"]["is_profit_model"] is False
    assert payload["summary"]["cost_bps"] == 23.0

    stages = rl_dashboard.load_rl_table("opening_workflow_run", "stages", limit=10)
    controls = rl_dashboard.load_rl_table("opening_workflow_run", "controls", limit=10)
    leaderboard = rl_dashboard.load_rl_table("opening_workflow_run", "leaderboard", limit=10)
    actions = rl_dashboard.load_rl_table("opening_workflow_run", "actions", limit=10)
    trades = rl_dashboard.load_rl_table("opening_workflow_run", "trades", limit=10)
    episodes = rl_dashboard.load_rl_table("opening_workflow_run", "episodes", limit=10)

    assert stages["rows"][0]["name"] == "contract"
    assert controls["rows"][0]["control_type"] == "shuffled_participant_context"
    assert leaderboard["rows"][0]["baseline_policy"] == "ts_imb_same_decision_tp5_sl1_time"
    assert actions["rows"][0]["episode_id"] == "000250_20250103"
    assert trades["rows"][0]["cost_model"] == "23bp_marketable_fill"
    assert episodes["rows"][0]["split"] == "eval"


def test_dashboard_rejects_opening_workflow_path_traversal(tmp_path, monkeypatch):
    _write_opening_workflow_fixture(tmp_path)
    monkeypatch.setattr(rl_dashboard, "RL_RUN_ROOTS", [tmp_path])

    with pytest.raises(ValueError, match="direct child|Invalid"):
        rl_dashboard.load_rl_run("../opening_workflow_run")

    client = flask_app.test_client()
    response = client.get("/api/rl/runs/..%5Copening_workflow_run")
    assert response.status_code in {400, 404}
