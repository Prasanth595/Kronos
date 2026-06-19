import json

from stom_rl.opening_30m_rl_workflow import OpeningWorkflowConfig
from stom_rl.opening_30m_rl_runner import run_opening_workflow_stages
from tests.fixtures.stom_opening_rl import build_opening_fixture_frames, opening_orderbook_frame
from webui.rl_dashboard_opening_tables import load_opening_json_table


def _statuses(payload):
    return {stage["name"]: stage["status"] for stage in payload["stages"]}


def test_opening_workflow_dry_run_writes_stage_statuses(tmp_path):
    output_dir = tmp_path / "dry_run"

    payload = run_opening_workflow_stages(
        build_opening_fixture_frames(),
        OpeningWorkflowConfig(run_id="dry_run", output_dir=output_dir),
    )

    summary_path = output_dir / "opening_30m_rl_workflow_summary.json"
    saved = json.loads(summary_path.read_text(encoding="utf-8"))
    statuses = _statuses(saved)

    assert saved == payload
    assert statuses["contract"] == "passed"
    assert statuses["manifest"] == "passed"
    assert statuses["participant_pressure"] == "passed"
    assert statuses["readiness_env"] == "passed"
    assert statuses["baseline"] == "passed"
    assert statuses["training"] == "skipped"
    assert saved["stage_results"]["training"]["reason"] == "training flag not set"
    assert saved["stage_results"]["baseline"]["artifact_type"] == "opening_30m_baseline_comparator"
    assert saved["feature_groups"] == [
        "price_volume",
        "participant_pressure",
        "orderbook_imbalance",
        "orderbook_persistence",
        "overheat_upper_wick",
        "optional_investor_flow",
    ]
    assert saved["proxy_availability"]["foreign_net_buy"] == "missing"
    assert saved["stage_results"]["orderbook_persistence"]["artifact_type"] == "orderbook_persistence_score"
    assert saved["participant_study_artifacts"]["participant_pressure_readiness_summary_json"]
    assert (output_dir / "episodes" / "opening_episode_manifest_summary.json").is_file()
    assert (output_dir / "baseline" / "opening_baseline_summary.json").is_file()
    assert load_opening_json_table("dry_run", output_dir, "opening_30m_rl_workflow", "proxy_availability", limit=10)["rows"]
    assert load_opening_json_table("dry_run", output_dir, "opening_30m_rl_workflow", "orderbook_persistence", limit=10)["rows"]


def test_opening_workflow_blocks_training_when_readiness_fails(tmp_path):
    bad_frame = opening_orderbook_frame(symbol="000250", session="20250103").iloc[:3].copy()

    payload = run_opening_workflow_stages(
        [bad_frame],
        OpeningWorkflowConfig(run_id="blocked_run", output_dir=tmp_path / "blocked"),
    )

    statuses = _statuses(payload)
    assert statuses["readiness_env"] == "failed"
    assert statuses["training"] == "blocked"
    assert statuses["evaluation"] == "blocked"
    assert statuses["cost_gate"] == "blocked"
    assert payload["stage_results"]["training"]["reason"].startswith("NO-GO_DATA")
    assert payload["verdict"] == "NO-GO_DATA"
