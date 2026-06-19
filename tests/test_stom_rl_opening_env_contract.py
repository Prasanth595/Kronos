import importlib

from stom_rl.opening_30m_rl_workflow import (
    OpeningWorkflowConfig,
    build_opening_env_contract_stage,
    build_opening_workflow_manifest,
    record_workflow_stage,
)
from stom_rl.orderbook_rl_env import ORDERBOOK_FEATURE_NAMES
from tests.fixtures.stom_opening_rl import build_opening_fixture_frames


def test_opening_env_contract_records_action_and_observation_space():
    result = build_opening_env_contract_stage(
        build_opening_fixture_frames(),
        fixed_entry_exit_only=True,
    )

    assert result["stage"] == "readiness_env"
    assert result["environment"] == "StomOrderbookGymEnv"
    assert result["observation_shape"] == [len(ORDERBOOK_FEATURE_NAMES)]
    assert result["action_space"] == {"0": "hold", "1": "exit"}
    assert result["constraint_mode"] == "fixed_entry_exit_only"
    assert result["fixed_entry_exit_only"] is True
    assert "check_env_passed" in result
    assert result["check_env_status"] in {"passed", "skipped_sb3_unavailable"}

    manifest = build_opening_workflow_manifest(OpeningWorkflowConfig(run_id="env_contract_fixture"))
    updated = record_workflow_stage(manifest, "readiness_env", result)
    stage = next(item for item in updated["stages"] if item["name"] == "readiness_env")
    assert stage["status"] == "complete"
    assert stage["evidence"] == "env_contract"
    assert updated["stage_results"]["readiness_env"] == result


def test_opening_env_contract_records_sb3_unavailable(monkeypatch):
    original_import_module = importlib.import_module

    def fake_import_module(name):
        if name == "stable_baselines3.common.env_checker":
            raise ModuleNotFoundError(name)
        return original_import_module(name)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    result = build_opening_env_contract_stage(build_opening_fixture_frames())

    assert result["check_env_passed"] is False
    assert result["check_env_status"] == "skipped_sb3_unavailable"
    assert result["check_env_message"]
