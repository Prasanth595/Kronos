import json
import sqlite3
from pathlib import Path

from stom_rl.opening_30m_rl_oos_split import build_oos_split_manifest
from stom_rl.opening_30m_rl_candidate_gate import REQUIRED_ABLATIONS
from stom_rl.opening_30m_rl_candidate_diagnostics import oos_baseline_inputs
from stom_rl.opening_30m_rl_context import OPENING_RL_CONTEXT_FEATURE_NAMES
from stom_rl.opening_30m_rl_realdata_cli import main


def _empty_sqlite(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.close()


def test_oos_cli_writes_bounded_split_artifacts(tmp_path):
    db_path = tmp_path / "empty.db"
    _empty_sqlite(db_path)
    output_dir = tmp_path / "run"

    exit_code = main(
        [
            "--db",
            str(db_path),
            "--run-id",
            "opening_30m_rl_oos_candidate_smoke",
            "--output-dir",
            str(output_dir),
            "--max-tables",
            "1",
            "--max-sessions-per-table",
            "1",
            "--create-split",
            "--candidate-algos",
            "dqn,ppo",
            "--tiny-train",
        ]
    )

    run_dir = output_dir / "opening_30m_rl_oos_candidate_smoke"
    lifecycle = json.loads((run_dir / "opening_candidate_lifecycle.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "opening_30m_rl_workflow_summary.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert lifecycle["split_manifest"]["split_hash"]
    assert lifecycle["promotion_gate"]["verdict"] in {"INCONCLUSIVE", "NO-GO_CONTROL", "NO-GO_ABLATION", "NO-GO_BASELINE"}
    assert lifecycle["context_features"]["feature_names"] == list(OPENING_RL_CONTEXT_FEATURE_NAMES)
    assert tuple(row["feature_set_id"] for row in lifecycle["ablations"]["ablations"]) == REQUIRED_ABLATIONS
    assert summary["candidate_verdict"] == lifecycle["promotion_gate"]["verdict"]
    assert summary["verdict"] == lifecycle["promotion_gate"]["verdict"]


def test_oos_cli_requires_existing_split_or_create_flag(tmp_path):
    db_path = tmp_path / "empty.db"
    _empty_sqlite(db_path)

    exit_code = main(
        [
            "--db",
            str(db_path),
            "--run-id",
            "missing_split",
            "--output-dir",
            str(tmp_path / "run"),
            "--candidate-algos",
            "dqn",
        ]
    )

    assert exit_code == 2


def test_oos_cli_uses_provided_split_manifest(tmp_path):
    db_path = tmp_path / "empty.db"
    _empty_sqlite(db_path)
    split_path = tmp_path / "split.json"
    manifest = build_oos_split_manifest(
        {"train": ["20240102"], "validation": ["20240103"], "oos": ["20240104"]},
        output_path=split_path,
    )

    exit_code = main(
        [
            "--db",
            str(db_path),
            "--run-id",
            "custom_split",
            "--output-dir",
            str(tmp_path / "runs"),
            "--candidate-algos",
            "dqn",
            "--split-manifest",
            str(split_path),
        ]
    )

    lifecycle = json.loads((tmp_path / "runs" / "custom_split" / "opening_candidate_lifecycle.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert lifecycle["split_manifest"]["split_hash"] == manifest["split_hash"]
    assert lifecycle["dataset"]["split_hash"] == manifest["split_hash"]


def test_oos_baseline_inputs_filter_to_frozen_oos_sessions(tmp_path):
    run_dir = tmp_path / "run"
    baseline_dir = run_dir / "baseline"
    baseline_dir.mkdir(parents=True)
    manifest = build_oos_split_manifest({"train": ["20240102"], "validation": ["20240103"], "oos": ["20240104"]})
    rows = [
        {"session": "20240102", "policy": "buy_and_hold", "net_return_pct": 99.0},
        {"session": "20240104", "policy": "buy_and_hold", "net_return_pct": 1.5},
        {"session": "20240104", "policy": "no_trade", "net_return_pct": 0.0},
        {"session": "20240104", "policy": "ts_imb_same_decision_tp5_sl1_time", "net_return_pct": -0.25},
    ]
    (baseline_dir / "opening_baseline_summary.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")

    values = oos_baseline_inputs(run_dir, manifest["split_sessions"]["oos"], manifest["split_hash"])

    assert values == {"no_trade": 0.0, "buy_and_hold": 1.5, "ts_imb_rule": -0.25}
