import json
import sqlite3
from pathlib import Path

import pytest

from stom_rl.episode_manifest import (
    EpisodeManifestConfig,
    build_episode_manifest,
    connect_readonly,
    verify_readonly_connection,
)


def _create_sqlite_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute('CREATE TABLE "000001" ("index" INTEGER, "close" REAL)')
        conn.execute('INSERT INTO "000001" VALUES (20250103090000, 1000)')
        conn.commit()
    finally:
        conn.close()


def _write_episode_csv(path: Path, rows: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["symbol,date,open,high,low,close,volume,amount,money,factor"]
    session = path.stem.rsplit("_", 1)[1]
    for idx in range(rows):
        lines.append(
            f"KR000001,{session[:4]}-{session[4:6]}-{session[6:]} 09:00:0{idx},"
            f"100{idx},100{idx},100{idx},100{idx},1,1000,1000,1.0"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def _write_export_report(path: Path, qlib_csv_dir: Path) -> None:
    payload = {
        "mode": "stom_to_qlib_export",
        "qlib_csv_dir": str(qlib_csv_dir),
        "exported_group_count": 4,
        "exported_row_count": 12,
        "split_counts": {
            "train": {"groups": 2, "rows": 6, "sessions": 2},
            "val": {"groups": 1, "rows": 3, "sessions": 1},
            "test": {"groups": 1, "rows": 3, "sessions": 1},
        },
        "split_sessions": {
            "train": ["20250103", "20250106"],
            "val": ["20250107"],
            "test": ["20250108"],
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8-sig")


def test_connect_readonly_blocks_write_probe(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    _create_sqlite_db(db_path)

    conn = connect_readonly(db_path)
    try:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute('CREATE TABLE "should_fail" (id INTEGER)')
    finally:
        conn.close()

    evidence = verify_readonly_connection(db_path)
    assert evidence["sqlite_uri_mode"] == "ro"
    assert evidence["query_only"] == 1
    assert evidence["write_probe_blocked"] is True


def test_build_episode_manifest_uses_export_split_and_writes_artifacts(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    report_path = tmp_path / "stom_qlib_export_report.json"
    csv_dir = tmp_path / "qlib_csv"
    out_dir = tmp_path / "rl_manifest"
    _create_sqlite_db(db_path)
    _write_export_report(report_path, csv_dir)
    for session in ["20250103", "20250106", "20250107", "20250108"]:
        _write_episode_csv(csv_dir / f"KR000001_{session}.csv", rows=3)

    payload = build_episode_manifest(
        EpisodeManifestConfig(
            db_path=str(db_path),
            export_report_path=str(report_path),
            output_dir=str(out_dir),
            count_csv_rows=True,
        )
    )

    assert payload["summary"]["episode_count"] == 4
    assert payload["summary"]["symbol_count"] == 1
    assert payload["summary"]["by_split"] == {"test": 1, "train": 2, "val": 1}
    assert payload["summary"]["by_split_delta_vs_export_report"] == {"test": 0, "train": 0, "val": 0}
    assert payload["summary"]["manifest_group_delta_vs_export_report"] == 0
    assert payload["summary"]["counted_csv_rows"] == 12
    assert payload["summary"]["split_validation"]["overlap_count"] == 0
    assert payload["summary"]["split_validation"]["chronological_train_val_test"] is True
    assert payload["db_readonly"]["write_probe_blocked"] is True

    first = payload["episodes"][0]
    assert first["episode_id"] == "000001_20250103"
    assert first["split"] == "train"
    assert first["reward_horizon_seconds"] == 300
    assert (out_dir / "episode_manifest.json").exists()
    assert (out_dir / "episode_manifest.csv").exists()
    assert (out_dir / "episode_summary.json").exists()


def test_build_episode_manifest_refuses_overlapping_split_sessions(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    report_path = tmp_path / "stom_qlib_export_report.json"
    csv_dir = tmp_path / "qlib_csv"
    _create_sqlite_db(db_path)
    _write_episode_csv(csv_dir / "KR000001_20250103.csv")
    report_path.write_text(
        json.dumps(
            {
                "qlib_csv_dir": str(csv_dir),
                "exported_group_count": 1,
                "split_sessions": {
                    "train": ["20250103"],
                    "val": ["20250103"],
                    "test": [],
                },
                "split_counts": {},
            }
        ),
        encoding="utf-8-sig",
    )

    with pytest.raises(ValueError, match="overlap"):
        build_episode_manifest(
            EpisodeManifestConfig(
                db_path=str(db_path),
                export_report_path=str(report_path),
                output_dir=str(tmp_path / "out"),
            )
        )
