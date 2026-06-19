import csv
import json
import math
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stom_rl.daily_ohlcv_db import EXPECTED_COLUMNS  # noqa: E402
from stom_rl.daily_ohlcv_dataset import (  # noqa: E402
    DATASET_BLOCKED_USES_WITH_UPSTREAM_BLOCKERS,
    DATASET_REQUIRED_EVIDENCE,
    DEFAULT_FEATURE_COLUMNS,
    DEFAULT_LABEL_COLUMNS,
    assign_chronological_splits,
    build_daily_ohlcv_dataset,
    validate_no_feature_leakage,
    write_dataset_artifacts,
)


def _create_daily_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    cols = ", ".join([f'"{col}" REAL' for col in EXPECTED_COLUMNS if col != "date"])
    for table in ("A000250", "A005930", "A069500"):
        conn.execute(f'CREATE TABLE "{table}" ("date" TEXT, {cols})')

    rows_000250 = []
    rows_005930 = []
    rows_etf = []
    for index in range(12):
        day = index + 1
        date = f"2024-01-{day:02d}"
        # A000250 includes one split-like jump at 2024-01-08 that must be blocked.
        close_000250 = 100.0 + index
        open_000250 = close_000250 - 0.5
        if day == 8:
            open_000250 = 500.0
            close_000250 = 510.0
        rows_000250.append(
            (
                date,
                open_000250,
                max(open_000250, close_000250) + 1.0,
                min(open_000250, close_000250) - 1.0,
                close_000250,
                1000.0 + index * 10,
                10,
                0,
                0,
                1.5 + index,
                100.0 + index,
                100.0 + index,
            )
        )
        close_005930 = 200.0 + index * 2
        rows_005930.append(
            (
                date,
                close_005930 - 1.0,
                close_005930 + 2.0,
                close_005930 - 2.0,
                close_005930,
                2000.0 + index * 20,
                10,
                0,
                0,
                2.0 + index,
                200.0 + index,
                200.0 + index,
            )
        )
        rows_etf.append(
            (
                date,
                50.0,
                51.0,
                49.0,
                50.0,
                500.0,
                10,
                0,
                0,
                0,
                0,
                0,
            )
        )
    conn.executemany('INSERT INTO "A000250" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', rows_000250)
    conn.executemany('INSERT INTO "A005930" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', rows_005930)
    conn.executemany('INSERT INTO "A069500" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', rows_etf)
    conn.commit()
    conn.close()
    return path


def _create_universe_manifest(path: Path) -> Path:
    manifest = {
        "schema_version": 1,
        "manifest_sha": "unit-universe-sha",
        "review_status": "WATCH_REQUIRES_OFFICIAL_OR_MANUAL_REVIEW",
        "verdict": "WATCH_HEURISTIC_UNIVERSE",
        "symbols": [
            {
                "table": "A000250",
                "code": "000250",
                "name": "삼천당제약",
                "market": "KOSDAQ",
                "instrument_type": "common_equity",
                "include": True,
                "review_status": "heuristic_watch",
                "classification_source": "stockinfo_name_market_heuristic",
                "classification_confidence": 0.85,
            },
            {
                "table": "A005930",
                "code": "005930",
                "name": "삼성전자",
                "market": "KOSPI",
                "instrument_type": "common_equity",
                "include": True,
                "review_status": "heuristic_watch",
                "classification_source": "stockinfo_name_market_heuristic",
                "classification_confidence": 0.85,
            },
            {
                "table": "A069500",
                "code": "069500",
                "name": "KODEX 200",
                "market": "KOSPI",
                "instrument_type": "fund_or_etf",
                "include": False,
                "exclusion_reason": "ETF_ETN_FUND_NAME_PREFIX",
                "review_status": "excluded_by_default",
            },
        ],
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return path


def test_validate_no_feature_leakage_rejects_future_label_columns():
    with pytest.raises(ValueError):
        validate_no_feature_leakage(["return_1d", "future_return_1d"], DEFAULT_LABEL_COLUMNS)
    report = validate_no_feature_leakage(DEFAULT_FEATURE_COLUMNS, DEFAULT_LABEL_COLUMNS)
    assert report["status"] == "PASS"
    assert report["forbidden_feature_columns"] == []


def test_assign_chronological_splits_blocks_purge_embargo_dates():
    assignments = assign_chronological_splits([f"2024-01-{idx:02d}" for idx in range(1, 11)], purge_days=1, embargo_days=1)
    assert list(assignments.values()).count("blocked_purge_embargo") == 2
    train_dates = [date for date, split in assignments.items() if split == "train"]
    val_dates = [date for date, split in assignments.items() if split == "val"]
    test_dates = [date for date, split in assignments.items() if split == "test"]
    assert max(train_dates) < min(val_dates) < min(test_dates)


def test_build_daily_dataset_preserves_codes_splits_and_blocks_material_windows(tmp_path: Path):
    db_path = _create_daily_db(tmp_path / "daily.db")
    universe_path = _create_universe_manifest(tmp_path / "universe.json")
    dataset = build_daily_ohlcv_dataset(
        daily_db_path=db_path,
        universe_manifest_path=universe_path,
        horizon_days=1,
        train_fraction=0.5,
        val_fraction=0.25,
        purge_days=1,
        embargo_days=1,
    )
    manifest = dataset["manifest"]
    assert manifest["price_basis"] == "unknown"
    assert manifest["universe_verdict"] == "WATCH_HEURISTIC_UNIVERSE"
    assert manifest["price_basis_status"] == "UNKNOWN_CONFIRMED"
    assert manifest["decision_grade_return_status"] == "BLOCKED_UNTIL_PRICE_BASIS_VERIFIED"
    assert manifest["universe_manifest_path"] == str(universe_path)
    assert manifest["universe_manifest_sha"] == "unit-universe-sha"
    assert manifest["universe_file_sha256"]
    assert manifest["upstream_gate_blockers"] == [
        "D0_PRICE_BASIS_NOT_VERIFIED",
        "D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED",
    ]
    assert manifest["decision_grade_status"] == "BLOCKED_BY_UPSTREAM_D0_D1_GUARDRAILS"
    assert manifest["model_readiness"] == "DATASET_RESEARCH_PREVIEW_BLOCKED_BY_UPSTREAM_GUARDRAILS"
    assert manifest["dataset_required_evidence"] == list(DATASET_REQUIRED_EVIDENCE)
    assert manifest["dataset_blocked_uses"] == list(DATASET_BLOCKED_USES_WITH_UPSTREAM_BLOCKERS)
    assert manifest["row_counts"]["feature_rows"] == 24
    assert manifest["row_counts"]["blocked_windows"] >= 1
    assert manifest["leakage_status"] == "PASS"
    assert manifest["normalization_policy"] == "fit_train_only_apply_to_val_test_later"
    assert manifest["split_chronology_status"] == "PASS"
    codes = {row["code"] for row in dataset["feature_panel"]}
    assert "000250" in codes
    assert "005930" in codes
    assert "069500" not in codes
    assert all(not key.startswith("future_") for row in dataset["rl_candidate_panel"] for key in row)
    assert all("label_join_key" in row for row in dataset["rl_candidate_panel"])
    blocked = [row for row in dataset["split_assignments"] if row["split"] == "blocked_material_unknown_adjustment"]
    assert {row["date"] for row in blocked} & {"2024-01-07", "2024-01-08"}
    assert all(row["eligible_for_training"] is False for row in blocked)
    assert any(row["split"] == "train" for row in dataset["split_assignments"])
    assert any(row["split"] == "val" for row in dataset["split_assignments"])
    assert any(row["split"] == "test" for row in dataset["split_assignments"])
    blocked_h2 = build_daily_ohlcv_dataset(
        daily_db_path=db_path,
        universe_manifest_path=universe_path,
        horizon_days=2,
        train_fraction=0.5,
        val_fraction=0.25,
        purge_days=1,
        embargo_days=1,
    )
    blocked_h2_dates = {
        row["date"]
        for row in blocked_h2["split_assignments"]
        if row["table"] == "A000250" and row["split"] == "blocked_material_unknown_adjustment"
    }
    assert {"2024-01-06", "2024-01-07", "2024-01-08"}.issubset(blocked_h2_dates)


def test_normalization_stats_are_fit_on_train_split_only(tmp_path: Path):
    db_path = _create_daily_db(tmp_path / "daily.db")
    universe_path = _create_universe_manifest(tmp_path / "universe.json")
    dataset = build_daily_ohlcv_dataset(
        daily_db_path=db_path,
        universe_manifest_path=universe_path,
        horizon_days=1,
        train_fraction=0.5,
        val_fraction=0.25,
        purge_days=1,
        embargo_days=1,
    )
    train_values = [
        float(row["return_1d"])
        for row in dataset["feature_panel"]
        if row["split"] == "train" and row["eligible_for_training"] and row["return_1d"] is not None
    ]
    expected_mean = sum(train_values) / len(train_values)
    stats = dataset["normalization_stats"]["features"]["return_1d"]
    assert stats["fit_split"] == "train"
    assert stats["count"] == len(train_values)
    assert math.isclose(stats["mean"], expected_mean)


def test_write_dataset_artifacts_stays_under_generated_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = _create_daily_db(tmp_path / "daily.db")
    universe_path = _create_universe_manifest(tmp_path / "universe.json")
    dataset = build_daily_ohlcv_dataset(
        daily_db_path=db_path,
        universe_manifest_path=universe_path,
        horizon_days=1,
        train_fraction=0.5,
        val_fraction=0.25,
        purge_days=1,
        embargo_days=1,
    )
    import stom_rl.daily_ohlcv_dataset as daily_dataset

    safe_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_dataset"
    monkeypatch.setattr(daily_dataset, "DEFAULT_DATASET_ROOT", safe_root)
    written = daily_dataset.write_dataset_artifacts(dataset, run_id="dataset_unit")
    assert Path(written["dataset_manifest_path"]).exists()
    assert Path(written["feature_panel_path"]).exists()
    assert Path(written["label_panel_path"]).exists()
    assert Path(written["rl_candidate_panel_path"]).exists()
    assert Path(written["split_assignments_path"]).exists()
    assert Path(written["normalization_stats_path"]).exists()
    assert Path(written["leakage_report_path"]).exists()
    assert Path(written["blocked_windows_path"]).exists()
    manifest = json.loads(Path(written["dataset_manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["run_id"] == "dataset_unit"
    assert manifest["universe_manifest_path"] == str(universe_path)
    assert manifest["universe_manifest_sha"] == "unit-universe-sha"
    assert manifest["universe_file_sha256"]
    assert manifest["cost_assumption_round_trip_bp"] == 23
    with Path(written["feature_panel_path"]).open(encoding="utf-8", newline="") as handle:
        feature_rows = list(csv.DictReader(handle))
    assert feature_rows[0]["code"] in {"000250", "005930"}
    with pytest.raises(FileExistsError):
        daily_dataset.write_dataset_artifacts(dataset, run_id="dataset_unit")
    with pytest.raises(ValueError):
        daily_dataset.write_dataset_artifacts(dataset, artifact_root=tmp_path / "elsewhere", run_id="bad")
    with pytest.raises(ValueError):
        daily_dataset.write_dataset_artifacts(dataset, run_id="..")
