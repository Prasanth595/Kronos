import json
import subprocess
import sys
from pathlib import Path

import pytest

from stom_rl.opening_30m_rl_workflow import (
    OpeningWorkflowConfig,
    UnsafeWorkflowClaimError,
    build_opening_workflow_manifest,
    write_opening_workflow_manifest,
)


def test_opening_workflow_contract_writes_minimal_manifest(tmp_path):
    output_dir = tmp_path / "run"

    payload = write_opening_workflow_manifest(
        OpeningWorkflowConfig(run_id="fixture_opening_run", output_dir=output_dir)
    )

    summary_path = output_dir / "opening_30m_rl_workflow_summary.json"
    assert summary_path.is_file()
    saved = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    assert saved == payload
    assert payload["artifact_type"] == "opening_30m_rl_workflow"
    assert payload["mode"] == "opening_30m_rl_workflow"
    assert payload["run_id"] == "fixture_opening_run"
    assert payload["config"]["cost_bps"] == 23.0
    assert payload["config"]["time_start"] == "090000"
    assert payload["config"]["time_end"] == "093000"
    assert payload["strategy_context"]["label"] == "RL EXPERIMENT"
    assert payload["strategy_context"]["is_live_ready"] is False
    assert payload["strategy_context"]["is_profit_model"] is False
    assert payload["guardrails"]["not_live_ready"] is True
    assert payload["guardrails"]["not_profit_model"] is True
    assert payload["stages"][0]["name"] == "contract"
    assert payload["stages"][0]["status"] == "complete"


def test_opening_workflow_rejects_live_ready_or_profit_flags(tmp_path):
    with pytest.raises(UnsafeWorkflowClaimError):
        build_opening_workflow_manifest(
            OpeningWorkflowConfig(
                output_dir=tmp_path / "live",
                is_live_ready=True,
            )
        )

    with pytest.raises(UnsafeWorkflowClaimError):
        build_opening_workflow_manifest(
            OpeningWorkflowConfig(
                output_dir=tmp_path / "profit",
                is_profit_model=True,
            )
        )


def test_opening_workflow_cli_no_write_does_not_touch_output_dir(tmp_path):
    output_dir = tmp_path / "cli-run"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "stom_rl.opening_30m_rl_workflow",
            "--run-id",
            "cli_fixture",
            "--output-dir",
            str(output_dir),
            "--no-write",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["run_id"] == "cli_fixture"
    assert payload["artifacts"]["summary_json"] == str(output_dir / "opening_30m_rl_workflow_summary.json")
    assert not output_dir.exists()
