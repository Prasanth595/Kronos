import json
import sqlite3

import pandas as pd
import pytest

from stom_rl.opening_30m_rule_filter_cli import main
from tests.fixtures.stom_opening_rl import build_opening_fixture_frames, opening_orderbook_frame


def _write_db(path, *, extra_sessions=()):
    frames = [
        *build_opening_fixture_frames(),
        *(opening_orderbook_frame(symbol="000250", session=session) for session in extra_sessions),
    ]
    combined = pd.concat(frames, ignore_index=True).drop(columns=["symbol", "session"])
    with sqlite3.connect(path) as conn:
        combined.to_sql("000250", conn, index=False)


def test_rule_filter_cli_writes_bounded_smoke_artifacts(tmp_path, capsys):
    db = tmp_path / "ticks.sqlite"
    out = tmp_path / "runs"
    _write_db(db)

    rc = main([
        "--db", str(db),
        "--output-dir", str(out),
        "--run-id", "opening_30m_rule_filter_smoke",
        "--create-split",
        "--max-tables", "1",
        "--max-sessions-per-table", "3",
        "--min-rows-per-session", "4",
    ])

    stdout = json.loads(capsys.readouterr().out)
    run_dir = out / "opening_30m_rule_filter_smoke"
    assert rc == 0
    assert stdout["artifact_type"] == "opening_30m_rule_filter"
    assert stdout["run_id"] == "opening_30m_rule_filter_smoke"
    assert stdout["split_hash"]
    summary = json.loads((run_dir / "opening_rule_filter_summary.json").read_text(encoding="utf-8"))
    assert summary["feature_set_id"] == "full_context"
    assert summary["baseline_semantics"]["artifact_ts_imb_rule"].startswith("RULE baseline")
    assert (run_dir / "opening_rule_filter_lifecycle.json").is_file()
    assert (run_dir / "opening_rule_filter_gate.json").is_file()


def test_rule_filter_cli_rejects_missing_split_manifest(tmp_path):
    db = tmp_path / "ticks.sqlite"
    _write_db(db)

    rc = main(["--db", str(db), "--output-dir", str(tmp_path / "runs"), "--split-manifest", str(tmp_path / "missing.json")])

    assert rc == 2


@pytest.mark.parametrize("run_id", ["../escape", "..\\escape", "/absolute", "C:\\escape", "..", "."])
def test_rule_filter_cli_rejects_unsafe_run_id_before_writing(tmp_path, run_id):
    db = tmp_path / "ticks.sqlite"
    out = tmp_path / "runs"
    _write_db(db)

    rc = main([
        "--db", str(db),
        "--output-dir", str(out),
        "--run-id", run_id,
        "--create-split",
        "--max-tables", "1",
        "--max-sessions-per-table", "3",
        "--min-rows-per-session", "4",
    ])

    assert rc == 2
    assert not (tmp_path / "escape").exists()
    assert not (out / "absolute").exists()


def test_rule_filter_cli_rejects_existing_run_dir_before_writing(tmp_path):
    db = tmp_path / "ticks.sqlite"
    out = tmp_path / "runs"
    run_dir = out / "opening_30m_rule_filter_smoke"
    run_dir.mkdir(parents=True)
    sentinel = run_dir / "sentinel.txt"
    sentinel.write_text("do not overwrite", encoding="utf-8")
    _write_db(db)

    rc = main([
        "--db", str(db),
        "--output-dir", str(out),
        "--run-id", "opening_30m_rule_filter_smoke",
        "--create-split",
        "--max-tables", "1",
        "--max-sessions-per-table", "3",
        "--min-rows-per-session", "4",
    ])

    assert rc == 2
    assert sentinel.read_text(encoding="utf-8") == "do not overwrite"
    assert not (run_dir / "opening_rule_filter_summary.json").exists()


def test_rule_filter_cli_auto_split_covers_all_loaded_sessions(tmp_path, capsys):
    db = tmp_path / "ticks.sqlite"
    out = tmp_path / "runs"
    _write_db(db, extra_sessions=("20250108",))

    rc = main([
        "--db", str(db),
        "--output-dir", str(out),
        "--run-id", "opening_30m_rule_filter_smoke",
        "--create-split",
        "--max-tables", "1",
        "--max-sessions-per-table", "4",
        "--min-rows-per-session", "4",
    ])

    json.loads(capsys.readouterr().out)
    manifest = json.loads((out / "opening_30m_rule_filter_smoke" / "opening_rule_filter_split_manifest.json").read_text(encoding="utf-8"))
    split_sessions = manifest["split_sessions"]
    all_sessions = [session for sessions in split_sessions.values() for session in sessions]
    assert rc == 0
    assert all_sessions == ["20250103", "20250106", "20250107", "20250108"]


def test_rule_filter_cli_records_feature_set_id(tmp_path, capsys):
    db = tmp_path / "ticks.sqlite"
    out = tmp_path / "runs"
    _write_db(db)

    rc = main([
        "--db", str(db),
        "--output-dir", str(out),
        "--run-id", "opening_30m_rule_filter_minimal",
        "--create-split",
        "--feature-set", "minimal_ts_imb",
        "--max-tables", "1",
        "--max-sessions-per-table", "3",
        "--min-rows-per-session", "4",
    ])

    json.loads(capsys.readouterr().out)
    summary = json.loads((out / "opening_30m_rule_filter_minimal" / "opening_rule_filter_summary.json").read_text(encoding="utf-8"))
    policy = summary["rule_filter_lifecycle"]["policy"]
    assert rc == 0
    assert summary["feature_set_id"] == "minimal_ts_imb"
    assert summary["baseline_semantics"]["guardrail"] == "Do not report artifact baseline equality as independent outperformance."
    assert policy["feature_set_id"] == "minimal_ts_imb"
