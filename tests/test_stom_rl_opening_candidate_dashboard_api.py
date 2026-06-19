import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from webui import rl_dashboard  # noqa: E402


def _write_candidate_run(root: Path) -> None:
    run = root / "opening_30m_rl_oos_candidate_smoke"
    run.mkdir()
    payload = {
        "artifact_type": "opening_30m_rl_workflow",
        "run_id": "opening_30m_rl_oos_candidate_smoke",
        "verdict": "INCONCLUSIVE",
        "candidate_verdict": "INCONCLUSIVE",
        "config": {"cost_bps": 23.0, "time_start": "090000", "time_end": "093000"},
        "guardrails": {"baseline": "ts_imb RULE baseline"},
        "candidate_history": [{"candidate_id": "dqn_default_seed100", "algorithm": "dqn", "split_hash": "split123"}],
        "candidate_lifecycle": {
            "split_manifest": {"split_hash": "split123", "split_sessions": {"train": ["20250102"], "validation": ["20250103"], "oos": ["20250106"]}},
            "context_features": {"feature_names": ["participant_pressure_score"], "status": "available", "sample": {"decision_second": 3, "vector": [0.5]}},
            "training": {"candidates": [{"candidate_id": "dqn_default_seed100", "algorithm": "dqn", "status": "skipped_sb3_unavailable", "split_hash": "split123"}]},
            "controls": {"controls": [{"control_type": "label_shuffle", "verdict": "NO-GO", "split_hash": "split123", "cost_bps": 23.0}]},
            "ablations": {"ablations": [{"feature_set_id": "no_orderbook_imbalance", "available": True, "passed": False, "split_hash": "split123"}]},
            "promotion_gate": {
                "verdict": "INCONCLUSIVE",
                "blocking_reasons": ["missing_or_failed_controls"],
                "equity_curve": [{"step": 0, "net_return_pct": 0.0}, {"step": 1, "net_return_pct": -1.0}],
                "time_bucket_performance": [{"bucket": "0900-0910", "trade_count": 1, "net_return_pct": -1.0}],
            },
        },
        "stages": [{"name": "cost_gate", "status": "blocked"}, {"name": "feature_ablation", "status": "blocked"}],
    }
    (run / "opening_30m_rl_workflow_summary.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_dashboard_api_exposes_candidate_lifecycle_tables(tmp_path, monkeypatch):
    _write_candidate_run(tmp_path)
    monkeypatch.setattr(rl_dashboard, "RL_RUN_ROOTS", [tmp_path])

    detail = rl_dashboard.load_rl_run("opening_30m_rl_oos_candidate_smoke")
    candidates = rl_dashboard.load_rl_table("opening_30m_rl_oos_candidate_smoke", "candidate_lifecycle", limit=10)
    splits = rl_dashboard.load_rl_table("opening_30m_rl_oos_candidate_smoke", "candidate_splits", limit=10)
    equity = rl_dashboard.load_rl_table("opening_30m_rl_oos_candidate_smoke", "candidate_equity_curve", limit=10)
    buckets = rl_dashboard.load_rl_table("opening_30m_rl_oos_candidate_smoke", "candidate_time_buckets", limit=10)
    controls = rl_dashboard.load_rl_table("opening_30m_rl_oos_candidate_smoke", "candidate_controls", limit=10)
    ablations = rl_dashboard.load_rl_table("opening_30m_rl_oos_candidate_smoke", "candidate_ablations", limit=10)
    reasons = rl_dashboard.load_rl_table("opening_30m_rl_oos_candidate_smoke", "candidate_failure_reasons", limit=10)
    context = rl_dashboard.load_rl_table("opening_30m_rl_oos_candidate_smoke", "context_feature_sample", limit=10)

    assert detail["summary"]["candidate_count"] == 1
    assert detail["summary"]["split_hash"] == "split123"
    assert detail["summary"]["blocked_stage_count"] == 2
    assert candidates["rows"][0]["candidate_id"] == "dqn_default_seed100"
    assert {row["split"] for row in splits["rows"]} == {"train", "validation", "oos"}
    assert equity["rows"][-1]["net_return_pct"] == -1.0
    assert buckets["rows"][0]["bucket"] == "0900-0910"
    assert controls["rows"][0]["control_type"] == "label_shuffle"
    assert ablations["rows"][0]["feature_set_id"] == "no_orderbook_imbalance"
    assert reasons["rows"][0]["reason"] == "missing_or_failed_controls"
    assert context["rows"][0]["feature_name"] == "participant_pressure_score"


def test_candidate_dashboard_tables_reject_path_traversal(tmp_path, monkeypatch):
    _write_candidate_run(tmp_path)
    monkeypatch.setattr(rl_dashboard, "RL_RUN_ROOTS", [tmp_path])

    try:
        rl_dashboard.load_rl_table("../opening_30m_rl_oos_candidate_smoke", "candidate_lifecycle", limit=10)
    except Exception as exc:
        assert "Invalid" in str(exc) or "not found" in str(exc)
    else:
        raise AssertionError("path traversal should fail")


def test_dashboard_api_discovers_nested_candidate_run(tmp_path, monkeypatch):
    category = tmp_path / "opening_30m_rl_oos_validation"
    category.mkdir()
    _write_candidate_run(category)
    monkeypatch.setattr(rl_dashboard, "RL_RUN_ROOTS", [tmp_path])

    runs = rl_dashboard.list_rl_runs(limit=10)
    assert any(run["name"] == "opening_30m_rl_oos_candidate_smoke" for run in runs)
    detail = rl_dashboard.load_rl_run("opening_30m_rl_oos_candidate_smoke")
    assert detail["summary"]["split_hash"] == "split123"


def test_dashboard_api_skips_stale_parent_category_artifact(tmp_path, monkeypatch):
    category = tmp_path / "opening_30m_rl_oos_validation"
    category.mkdir()
    stale_parent = {
        "artifact_type": "opening_30m_rl_workflow",
        "run_id": "opening_30m_rl_oos_validation",
        "verdict": "INCONCLUSIVE",
        "candidate_verdict": "INCONCLUSIVE",
        "config": {"cost_bps": 23.0},
        "guardrails": {"baseline": "ts_imb RULE baseline"},
        "candidate_history": [],
        "candidate_lifecycle": {},
        "stages": [],
    }
    (category / "opening_30m_rl_workflow_summary.json").write_text(json.dumps(stale_parent), encoding="utf-8")
    _write_candidate_run(category)
    monkeypatch.setattr(rl_dashboard, "RL_RUN_ROOTS", [tmp_path])

    runs = rl_dashboard.list_rl_runs(limit=10)

    assert "opening_30m_rl_oos_validation" not in {run["name"] for run in runs}
    assert any(run["name"] == "opening_30m_rl_oos_candidate_smoke" for run in runs)
