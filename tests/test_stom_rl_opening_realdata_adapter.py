import json
import sqlite3
import subprocess
import sys

import pytest

from stom_rl.opening_30m_rl_realdata_adapter import (
    RealdataAdapterConfig,
    RealdataNoGoDataError,
    load_opening_realdata_frames,
)
from stom_rl.opening_30m_rl_runner import run_opening_workflow_stages
from stom_rl.opening_30m_rl_workflow import OpeningWorkflowConfig
from tests.fixtures.stom_opening_rl import opening_orderbook_frame


def _write_fixture_db(path):
    frame = opening_orderbook_frame(symbol="000250", session="20250103")
    with sqlite3.connect(path) as conn:
        frame.drop(columns=["symbol", "session"]).to_sql("000250", conn, index=False)
        conn.execute('CREATE TABLE "ABC001" ("index" INTEGER)')


def test_realdata_adapter_feeds_opening_workflow_frames(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    output_dir = tmp_path / "adapter"
    _write_fixture_db(db_path)

    result = load_opening_realdata_frames(
        RealdataAdapterConfig(
            db_path=db_path,
            output_dir=output_dir,
            max_tables=1,
            max_sessions_per_table=1,
            max_rows_per_session=6,
            min_rows_per_session=4,
        )
    )
    workflow = run_opening_workflow_stages(
        result.frames,
        OpeningWorkflowConfig(run_id="realdata_fixture", output_dir=tmp_path / "workflow", mode="realdata_smoke"),
    )

    assert result.frames[0]["symbol"].iloc[0] == "000250"
    assert result.frames[0]["session"].iloc[0] == "20250103"
    assert result.summary["sampled_tables"][0]["symbol"] == "000250"
    assert result.summary["sampled_tables"][0]["sessions"][0]["row_count"] == 6
    assert result.summary["bounds"]["time_start"] == "090000"
    assert workflow["artifact_type"] == "opening_30m_rl_workflow"
    assert workflow["verdict"] in {"NO-GO_DATA", "PENDING_TRAINING", "PENDING"}
    assert (output_dir / "realdata_adapter_summary.json").is_file()


def test_realdata_adapter_reports_no_go_data_for_missing_quotes(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    output_dir = tmp_path / "adapter_bad"
    frame = opening_orderbook_frame(symbol="000250", session="20250103")
    with sqlite3.connect(db_path) as conn:
        frame.drop(columns=["symbol", "session", "매수호가1"]).to_sql("000250", conn, index=False)

    with pytest.raises(RealdataNoGoDataError, match="NO-GO_DATA"):
        load_opening_realdata_frames(
            RealdataAdapterConfig(
                db_path=db_path,
                output_dir=output_dir,
                max_tables=1,
                max_sessions_per_table=1,
                max_rows_per_session=6,
                min_rows_per_session=4,
            )
        )

    saved = json.loads((output_dir / "realdata_adapter_summary.json").read_text(encoding="utf-8-sig"))
    assert saved["verdict"] == "NO-GO_DATA"
    assert saved["sampled_tables"][0]["exclusion_reason"].startswith("missing required columns")


def test_realdata_cli_writes_bounded_smoke_summary(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    output_dir = tmp_path / "realdata_smoke"
    _write_fixture_db(db_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "stom_rl.opening_30m_rl_realdata",
            "--db",
            str(db_path),
            "--run-id",
            "fixture_realdata_smoke",
            "--output-dir",
            str(output_dir),
            "--max-tables",
            "1",
            "--max-sessions-per-table",
            "1",
            "--max-rows-per-session",
            "6",
            "--time-start",
            "090000",
            "--time-end",
            "093000",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    summary_path = output_dir / "opening_30m_rl_workflow_summary.json"
    assert result.returncode == 0, result.stderr
    assert summary_path.is_file()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["artifact_type"] == "opening_30m_rl_workflow"
    assert payload["verdict"] in {"NO-GO_DATA", "NO-GO", "INCONCLUSIVE", "GO_CANDIDATE"}
    assert payload["config"]["cost_bps"] == 23.0
    assert payload["realdata"]["bounds"]["max_tables"] == 1
    assert payload["realdata"]["sampled_tables"][0]["symbol"] == "000250"
    assert payload["realdata"]["training_status"] in {
        "skipped_sb3_unavailable",
        "skipped_training_not_requested",
        "available_not_requested",
    }
    assert payload["realdata"]["model_status"] == "no_model_trained"


def test_realdata_cli_refuses_missing_db(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "stom_rl.opening_30m_rl_realdata",
            "--db",
            str(tmp_path / "missing.db"),
            "--run-id",
            "missing_db",
            "--output-dir",
            str(tmp_path / "missing_out"),
            "--max-tables",
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "SQLite DB not found" in result.stderr
    assert not (tmp_path / "missing_out" / "opening_30m_rl_workflow_summary.json").exists()
