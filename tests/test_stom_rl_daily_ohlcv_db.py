import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stom_rl.daily_ohlcv_db import (  # noqa: E402
    EXPECTED_COLUMNS,
    connect_readonly,
    resolve_daily_table,
    summarize_daily_db,
    summarize_symbol,
    validate_daily_table_name,
    write_db_summary_artifacts,
)


def _create_daily_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    cols = ", ".join([f'"{col}" REAL' for col in EXPECTED_COLUMNS if col != "date"])
    for table in ("A000250", "A035720", "Q500001"):
        conn.execute(f'CREATE TABLE "{table}" ("date" TEXT, {cols})')
    conn.executemany(
        'INSERT INTO "A000250" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [
            ("2024-01-02", 100.0, 110.0, 90.0, 100.0, 1000.0, 10, 0, 0, 0, 0, 0),
            ("2024-01-03", 102.0, 112.0, 95.0, 105.0, 1200.0, 10, 0, 0, 0, 0, 0),
            ("2024-01-04", 500.0, 520.0, 490.0, 510.0, 2000.0, 10, 0, 0, 0, 0, 0),
        ],
    )
    conn.executemany(
        'INSERT INTO "A035720" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [
            ("2024-01-02", 10.0, 11.0, 9.0, 10.0, 100.0, 10, 0, 0, 0, 0, 0),
            ("2024-01-03", 0.0, 11.0, 9.0, 10.0, 100.0, 10, 0, 0, 0, 0, 0),
            ("2024-01-04", 10.0, 8.0, 9.0, 10.0, 100.0, 10, 0, 0, 0, 0, 0),
        ],
    )
    conn.execute(
        'INSERT INTO "Q500001" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        ("2024-01-04", 10.0, 11.0, 9.0, 10.0, 100.0, 10, 0, 0, 0, 0, 0),
    )
    conn.commit()
    conn.close()
    return path


def test_resolve_daily_table_preserves_leading_zero_code():
    resolved = resolve_daily_table("000250")
    assert resolved.table == "A000250"
    assert resolved.code == "000250"
    assert resolve_daily_table("Q500001").prefix == "Q"


@pytest.mark.parametrize("bad", ["../A000250", "A000250;DROP", "A00025", "AA000250", "000250.csv"])
def test_validate_daily_table_name_rejects_unsafe_values(bad: str):
    with pytest.raises(ValueError):
        validate_daily_table_name(bad)


def test_connect_readonly_blocks_write_attempt(tmp_path: Path):
    db_path = _create_daily_db(tmp_path / "daily.db")
    with connect_readonly(db_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM "A000250"').fetchone()[0] == 3
        with pytest.raises(sqlite3.OperationalError):
            conn.execute('INSERT INTO "A000250" (date) VALUES ("2099-01-01")')


def test_summarize_symbol_reports_price_basis_and_quality(tmp_path: Path):
    db_path = _create_daily_db(tmp_path / "daily.db")
    payload = summarize_symbol("000250", db_path=db_path, sample_limit=2)
    assert payload["table"] == "A000250"
    assert payload["code"] == "000250"
    assert payload["price_basis"] == "unknown"
    assert payload["price_basis_status"] == "UNKNOWN_CONFIRMED"
    assert payload["decision_grade_return_status"] == "BLOCKED_UNTIL_PRICE_BASIS_VERIFIED"
    assert payload["price_basis_audit"]["status"] == "UNKNOWN_CONFIRMED"
    assert payload["price_basis_audit"]["component_status"]["split_adjustment"] == "not_declared_no_split_factor_or_corporate_action_table"
    assert payload["price_basis_audit"]["blocked_uses"] == [
        "decision_grade_return_labels",
        "model_build_or_candidate_promotion",
        "paper_forward_or_live_readiness_claims",
    ]
    assert payload["price_basis_user_guidance"][0]["section"] == "D0 summary"
    assert payload["schema_matches_expected"] is True
    assert payload["quality"]["split_like_discontinuity_count"] == 1
    assert payload["quality"]["material_unknown_adjustment_windows"][0]["date"] == "2024-01-04"
    assert len(payload["sample_rows_desc"]) == 2


def test_summarize_daily_db_contract_and_bounded_tables(tmp_path: Path):
    db_path = _create_daily_db(tmp_path / "daily.db")
    summary = summarize_daily_db(db_path, table_limit=2, quality_table_limit=3)
    assert summary["read_only"] is True
    assert summary["query_only"] is True
    assert summary["table_count"] == 3
    assert summary["prefix_counts"] == {"A": 2, "Q": 1}
    assert summary["total_rows"] == 7
    assert summary["first_date"] == "2024-01-02"
    assert summary["latest_date"] == "2024-01-04"
    assert summary["tables_at_latest_date"] == 3
    assert summary["price_basis"] == "unknown"
    assert summary["decision_grade_status"] == "WATCH_PRICE_BASIS_UNKNOWN_CONFIRMED"
    assert summary["price_basis_status"] == "UNKNOWN_CONFIRMED"
    assert summary["decision_grade_return_status"] == "BLOCKED_UNTIL_PRICE_BASIS_VERIFIED"
    assert summary["price_basis_audit"]["quality_scan_complete"] is True
    assert summary["price_basis_audit"]["split_like_table_count"] == 1
    assert summary["price_basis_audit"]["split_like_window_sample_count"] == 1
    assert "official_or_vendor_field_declaring_adjusted_or_raw_close" in summary["price_basis_required_evidence"]
    assert "model_build_or_candidate_promotion" in summary["price_basis_blocked_uses"]
    assert summary["price_basis_user_guidance"][2]["section"] == "D4-D9 promotion"
    assert summary["table_summaries_returned"] == 2
    assert summary["quality_scan_scope"] == "all_tables"
    assert summary["quality_scan_complete"] is True
    assert summary["material_unknown_adjustment_windows"][0]["table"] == "A000250"
    assert summary["material_unknown_adjustment_windows"][0]["date"] == "2024-01-04"
    assert "open_to_previous_close_ratio" in summary["material_unknown_adjustment_windows"][0]
    flags = {(row["table"], row["flag"]) for row in summary["quality_flags"]}
    assert ("A000250", "split_like_discontinuity_count") in flags
    assert ("A035720", "nonpositive_ohlc_rows") in flags
    assert ("A035720", "ohlc_inconsistency_rows") in flags


def test_write_db_summary_artifacts_stays_under_generated_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = _create_daily_db(tmp_path / "daily.db")
    summary = summarize_daily_db(db_path, table_limit=1, quality_table_limit=1)
    import stom_rl.daily_ohlcv_db as daily_db

    safe_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_db_summary"
    monkeypatch.setattr(daily_db, "DEFAULT_ARTIFACT_ROOT", safe_root)
    written = daily_db.write_db_summary_artifacts(summary, run_id="unit_run")
    assert Path(written["db_summary_path"]).exists()
    assert Path(written["table_summaries_path"]).exists()
    assert Path(written["quality_flags_path"]).exists()
    assert Path(written["price_basis_audit_path"]).exists()
    assert Path(written["price_basis_windows_path"]).exists()
    with pytest.raises(ValueError):
        daily_db.write_db_summary_artifacts(summary, artifact_root=tmp_path / "elsewhere", run_id="bad")
    with pytest.raises(ValueError):
        daily_db.write_db_summary_artifacts(summary, run_id="..")
