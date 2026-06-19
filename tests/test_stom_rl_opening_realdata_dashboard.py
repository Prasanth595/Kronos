import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from webui import rl_dashboard  # noqa: E402
from webui.app import app as flask_app  # noqa: E402


def _write_realdata_run(root: Path) -> None:
    run = root / "opening_30m_rl_realdata_smoke"
    run.mkdir()
    payload = {
        "artifact_type": "opening_30m_rl_workflow",
        "mode": "opening_30m_rl_workflow",
        "run_id": "opening_30m_rl_realdata_smoke",
        "verdict": "INCONCLUSIVE",
        "config": {"cost_bps": 23.0, "time_start": "090000", "time_end": "093000"},
        "strategy_context": {
            "label": "RL EXPERIMENT",
            "is_live_ready": False,
            "is_profit_model": False,
        },
        "guardrails": {
            "not_live_ready": True,
            "not_profit_model": True,
            "baseline": "ts_imb RULE baseline",
            "cost_bps": 23.0,
        },
        "stages": [
            {"name": "contract", "status": "passed", "evidence": "contract"},
            {"name": "dashboard", "status": "blocked", "evidence": ""},
        ],
        "realdata": {
            "bounds": {"max_tables": 5, "time_start": "090000", "time_end": "093000"},
            "sampled_tables": [{"symbol": "000020", "leading_zero_preserved": True}],
            "training_status": "available_not_requested",
            "model_status": "no_model_trained",
            "guardrail": "RL EXPERIMENT; bounded real-data smoke; not live-ready.",
        },
        "realdata_validation_gate": {
            "verdict": "INCONCLUSIVE",
            "can_show_go_candidate": False,
            "feature_ablation_results": {
                "participant_pressure": {"passed": False, "required_for_go_candidate": True},
                "orderbook_persistence": {"passed": False, "required_for_go_candidate": True},
            },
            "blocking_reasons": ["missing_oos_split"],
        },
    }
    (run / "opening_30m_rl_workflow_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_dashboard_loads_realdata_opening_workflow_read_only(tmp_path, monkeypatch):
    _write_realdata_run(tmp_path)
    monkeypatch.setattr(rl_dashboard, "RL_RUN_ROOTS", [tmp_path])

    detail = rl_dashboard.load_rl_run("opening_30m_rl_realdata_smoke")
    feature_ablations = rl_dashboard.load_rl_table("opening_30m_rl_realdata_smoke", "feature_ablations", limit=10)
    client = flask_app.test_client()
    response = client.get("/api/rl/runs/opening_30m_rl_realdata_smoke")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["artifact_type"] == "opening_30m_rl_workflow"
    assert payload["summary"]["realdata_sampled_table_count"] == 1
    assert payload["summary"]["realdata_time_start"] == "090000"
    assert payload["summary"]["model_status"] == "no_model_trained"
    assert payload["summary"]["validation_verdict"] == "INCONCLUSIVE"
    assert detail["detail"]["realdata"]["sampled_tables"][0]["symbol"] == "000020"
    assert feature_ablations["rows"][0]["feature_ablation"] in {
        "orderbook_persistence",
        "participant_pressure",
    }


def test_dashboard_realdata_copy_rejects_profit_live_claims(tmp_path, monkeypatch):
    _write_realdata_run(tmp_path)
    monkeypatch.setattr(rl_dashboard, "RL_RUN_ROOTS", [tmp_path])

    payload = rl_dashboard.load_rl_run("opening_30m_rl_realdata_smoke")
    encoded = json.dumps(payload, ensure_ascii=False).lower()

    assert payload["strategy_context"]["label"] == "RL EXPERIMENT"
    assert payload["strategy_context"]["is_live_ready"] is False
    assert payload["strategy_context"]["is_profit_model"] is False
    assert payload["summary"]["cost_bps"] == 23.0
    assert payload["summary"]["baseline"] == "ts_imb RULE baseline"
    assert "profitable" not in encoded
    assert "broker-ready" not in encoded
