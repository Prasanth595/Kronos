import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stom_rl.daily_ohlcv_db import EXPECTED_COLUMNS  # noqa: E402
from stom_rl.daily_ohlcv_universe import (  # noqa: E402
    UNIVERSE_BLOCKED_USES_WHEN_VERIFIED,
    UNIVERSE_BLOCKED_USES_WHEN_WATCH,
    UNIVERSE_REQUIRED_EVIDENCE,
    build_universe_manifest,
    classify_daily_table,
    load_official_metadata_csv,
    load_stockinfo,
    write_universe_artifacts,
)


def _create_daily_db(path: Path, tables: list[str]) -> Path:
    conn = sqlite3.connect(path)
    cols = ", ".join([f'"{col}" REAL' for col in EXPECTED_COLUMNS if col != "date"])
    for table in tables:
        conn.execute(f'CREATE TABLE "{table}" ("date" TEXT, {cols})')
        conn.execute(
            f'INSERT INTO "{table}" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            ("2024-01-02", 10.0, 11.0, 9.0, 10.0, 100.0, 10, 0, 0, 0, 0, 0),
        )
    conn.commit()
    conn.close()
    return path


def _create_stockinfo_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE stockinfo ("index" TEXT, "종목명" TEXT, "코스닥" INTEGER)')
    rows = [
        ("000250", "삼천당제약", 1),
        ("005930", "삼성전자", 0),
        ("069500", "KODEX 200", 0),
        ("580001", "미래에셋 레버리지 원유선물혼합 ETN", 0),
        ("123456", "테스트스팩1호", 1),
        ("654321", "테스트리츠", 0),
        ("005935", "삼성전자우", 0),
        ("195940", "HK이노엔", 1),
        ("111111", "시장없음테스트", None),
    ]
    conn.executemany('INSERT INTO stockinfo VALUES (?, ?, ?)', rows)
    conn.commit()
    conn.close()
    return path
def _create_official_metadata_csv(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "code,name,market,instrument_type,source",
                "000250,삼천당제약,KOSDAQ,common_equity,unit_krx_csv",
                "005930,삼성전자,KOSPI,common_equity,unit_krx_csv",
                "069500,KODEX 200,KOSPI,etf,unit_krx_csv",
                "005935,삼성전자우,KOSPI,preferred_stock,unit_krx_csv",
                "123456,테스트스팩1호,KOSDAQ,spac,unit_krx_csv",
            ]
        ),
        encoding="utf-8",
    )
    return path




def test_load_stockinfo_preserves_codes_and_names(tmp_path: Path):
    stockinfo_path = _create_stockinfo_db(tmp_path / "stockinfo.db")
    records = load_stockinfo(stockinfo_path)
    assert records["000250"].name == "삼천당제약"
    assert records["000250"].kosdaq == 1
    assert "5930" not in records

def test_load_official_metadata_csv_preserves_codes_and_required_contract(tmp_path: Path):
    path = _create_official_metadata_csv(tmp_path / "krx.csv")
    records = load_official_metadata_csv(path)
    assert records["000250"].market == "KOSDAQ"
    assert records["005935"].instrument_type == "preferred_stock"
    assert "250" not in records
    duplicate_path = tmp_path / "duplicate_krx.csv"
    duplicate_path.write_text(
        "code,name,market,instrument_type\n000250,삼천당제약,KOSDAQ,common_equity\n000250,중복,KOSDAQ,common_equity\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate code"):
        load_official_metadata_csv(duplicate_path)
    short_code_path = tmp_path / "short_code_krx.csv"
    short_code_path.write_text(
        "code,name,market,instrument_type\n250,삼천당제약,KOSDAQ,common_equity\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="6-character string"):
        load_official_metadata_csv(short_code_path)
    blank_name_path = tmp_path / "blank_name_krx.csv"
    blank_name_path.write_text(
        "code,name,market,instrument_type\n000250,,KOSDAQ,common_equity\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="name is required"):
        load_official_metadata_csv(blank_name_path)



def test_classify_daily_table_includes_common_kospi_kosdaq_and_preserves_metadata(tmp_path: Path):
    stockinfo_path = _create_stockinfo_db(tmp_path / "stockinfo.db")
    stockinfo = load_stockinfo(stockinfo_path)
    kosdaq = classify_daily_table("A000250", stockinfo)
    kospi = classify_daily_table("A005930", stockinfo)
    hk_common = classify_daily_table("A195940", stockinfo)
    assert kosdaq["include"] is True
    assert kosdaq["code"] == "000250"
    assert kosdaq["market"] == "KOSDAQ"
    assert kosdaq["instrument_type"] == "common_equity"
    assert kosdaq["review_status"] == "heuristic_watch"
    assert kosdaq["classification_source"] == "stockinfo_name_market_heuristic"
    assert isinstance(kosdaq["metadata_sha"], str) and len(kosdaq["metadata_sha"]) == 64
    assert kosdaq["official_metadata_status"] == "not_available"
    assert kospi["include"] is True
    assert kospi["market"] == "KOSPI"
    assert hk_common["include"] is True


@pytest.mark.parametrize(
    ("table", "expected_reason"),
    [
        ("A069500", "ETF_ETN_FUND_NAME_PREFIX"),
        ("A580001", "ETF_ETN_FUND_NAME_TOKEN"),
        ("Q580001", "Q_PRODUCT_TABLE"),
        ("A123456", "SPAC_EXCLUDED"),
        ("A654321", "REIT_EXCLUDED"),
        ("A005935", "PREFERRED_SHARE_EXCLUDED"),
        ("A999999", "METADATA_UNMATCHED"),
        ("A0017J0", "ALPHANUMERIC_CODE_UNREVIEWED"),
        ("A111111", "UNKNOWN_MARKET_METADATA"),
    ],
)
def test_classify_daily_table_excludes_products_and_uncertain_symbols(tmp_path: Path, table: str, expected_reason: str):
    stockinfo_path = _create_stockinfo_db(tmp_path / "stockinfo.db")
    stockinfo = load_stockinfo(stockinfo_path)
    payload = classify_daily_table(table, stockinfo)
    assert payload["include"] is False
    assert payload["exclusion_reason"] == expected_reason
    assert payload["review_status"] in {"excluded_by_default", "quarantined_unmatched", "quarantined_unknown_market"}
    assert payload["classification_source"]
    assert "metadata_sha" in payload


def test_build_universe_manifest_contract_counts_and_watch_verdict(tmp_path: Path):
    daily_path = _create_daily_db(
        tmp_path / "daily.db",
        ["A000250", "A005930", "A069500", "Q580001", "A005935", "A999999", "A0017J0", "A111111"],
    )
    stockinfo_path = _create_stockinfo_db(tmp_path / "stockinfo.db")
    manifest = build_universe_manifest(daily_path, stockinfo_path)
    assert manifest["verdict"] == "WATCH_HEURISTIC_UNIVERSE"
    assert manifest["table_count"] == 8
    assert manifest["stockinfo_matched_table_count"] == 6
    assert manifest["stockinfo_unmatched_table_count"] == 2
    assert manifest["include_count"] == 2
    assert manifest["exclude_count"] == 6
    assert manifest["unmatched_count"] == 2
    assert manifest["metadata_unmatched_count"] == 1
    assert manifest["q_product_count"] == 1
    assert set(manifest["required_fields"]) == {
        "classification_source",
        "classification_confidence",
        "exclusion_reason",
        "metadata_sha",
        "review_status",
        "official_metadata_status",
        "official_metadata_coverage_status",
        "universe_certification_status",
    }
    assert manifest["official_metadata_status"] == "MISSING"
    assert manifest["official_metadata"]["review_status"] == "WATCH_OFFICIAL_METADATA_REQUIRED"
    assert manifest["official_metadata_coverage_status"] == "MISSING"
    assert manifest["universe_certification_status"] == "BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW"
    assert manifest["universe_required_evidence"] == list(UNIVERSE_REQUIRED_EVIDENCE)
    assert manifest["universe_blocked_uses"] == list(UNIVERSE_BLOCKED_USES_WHEN_WATCH)
    assert "model_build_or_candidate_promotion" in manifest["universe_blocked_uses"]
    assert manifest["official_metadata_unmatched_table_count"] == 8
    assert manifest["quarantine_artifact_count"] == 3
    by_code = {row["code"]: row for row in manifest["symbols"]}
    assert by_code["000250"]["include"] is True
    assert by_code["069500"]["include"] is False
    assert by_code["999999"]["exclusion_reason"] == "METADATA_UNMATCHED"
    assert by_code["111111"]["exclusion_reason"] == "UNKNOWN_MARKET_METADATA"
    assert len(manifest["manifest_sha"]) == 64

def test_build_universe_manifest_can_use_official_metadata_without_overclaim(tmp_path: Path):
    daily_path = _create_daily_db(
        tmp_path / "daily.db",
        ["A000250", "A005930", "A069500", "A005935", "A123456", "A999999"],
    )
    stockinfo_path = _create_stockinfo_db(tmp_path / "stockinfo.db")
    official_path = _create_official_metadata_csv(tmp_path / "krx.csv")
    manifest = build_universe_manifest(daily_path, stockinfo_path, official_metadata_path=official_path)
    assert manifest["verdict"] == "WATCH_HEURISTIC_UNIVERSE"
    assert manifest["official_metadata_status"] == "LOADED"
    assert manifest["official_metadata_matched_table_count"] == 5
    assert manifest["official_metadata_coverage_status"] == "PARTIAL"
    assert manifest["universe_certification_status"] == "BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW"
    assert manifest["universe_blocked_uses"] == list(UNIVERSE_BLOCKED_USES_WHEN_WATCH)
    assert manifest["official_metadata_unmatched_table_count"] == 1
    by_code = {row["code"]: row for row in manifest["symbols"]}
    assert by_code["000250"]["include"] is True
    assert by_code["000250"]["classification_source"] == "official_metadata_csv"
    assert by_code["000250"]["review_status"] == "official_metadata_reviewed"
    assert by_code["069500"]["include"] is False
    assert by_code["069500"]["exclusion_reason"] == "OFFICIAL_ETF_ETN_FUND_EXCLUDED"
    assert by_code["005935"]["exclusion_reason"] == "OFFICIAL_PREFERRED_SHARE_EXCLUDED"
    assert by_code["123456"]["exclusion_reason"] == "OFFICIAL_SPAC_EXCLUDED"
    assert by_code["999999"]["official_metadata_status"] == "not_used"
    assert by_code["999999"]["exclusion_reason"] == "METADATA_UNMATCHED"

def test_build_universe_manifest_can_clear_only_with_complete_official_metadata(tmp_path: Path):
    daily_path = _create_daily_db(
        tmp_path / "daily.db",
        ["A000250", "A005930", "A069500", "A005935", "A123456"],
    )
    stockinfo_path = _create_stockinfo_db(tmp_path / "stockinfo.db")
    official_path = _create_official_metadata_csv(tmp_path / "krx.csv")
    manifest = build_universe_manifest(daily_path, stockinfo_path, official_metadata_path=official_path)

    assert manifest["verdict"] == "OFFICIAL_OR_MANUAL_REVIEWED"
    assert manifest["review_status"] == "OFFICIAL_OR_MANUAL_REVIEWED"
    assert manifest["official_metadata_status"] == "OFFICIAL_VERIFIED"
    assert manifest["official_metadata_coverage_status"] == "COMPLETE"
    assert manifest["official_metadata"]["certification_status"] == "OFFICIAL_OR_MANUAL_REVIEWED"
    assert manifest["universe_certification_status"] == "OFFICIAL_OR_MANUAL_REVIEWED"
    assert manifest["universe_blocked_uses"] == list(UNIVERSE_BLOCKED_USES_WHEN_VERIFIED)
    assert "model_build_or_candidate_promotion" not in manifest["universe_blocked_uses"]
    assert manifest["official_metadata_unmatched_table_count"] == 0



def test_write_universe_artifacts_rejects_escape_and_writes_csvs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    daily_path = _create_daily_db(tmp_path / "daily.db", ["A000250", "A069500", "A999999"])
    stockinfo_path = _create_stockinfo_db(tmp_path / "stockinfo.db")
    manifest = build_universe_manifest(daily_path, stockinfo_path)
    import stom_rl.daily_ohlcv_universe as universe

    safe_root = tmp_path / "webui" / "rl_runs" / "daily_ohlcv_universe"
    monkeypatch.setattr(universe, "DEFAULT_UNIVERSE_ROOT", safe_root)
    written = universe.write_universe_artifacts(manifest, run_id="universe_unit")
    assert Path(written["universe_path"]).exists()
    assert Path(written["symbols_path"]).read_text(encoding="utf-8").startswith("classification_confidence")
    assert Path(written["exclusions_path"]).exists()
    assert Path(written["official_metadata_audit_path"]).exists()
    assert Path(written["quarantine_path"]).exists()
    quarantine_text = Path(written["quarantine_path"]).read_text(encoding="utf-8")
    assert "ALPHANUMERIC_CODE_UNREVIEWED" in quarantine_text or "METADATA_UNMATCHED" in quarantine_text
    with pytest.raises(ValueError):
        universe.write_universe_artifacts(manifest, artifact_root=tmp_path / "elsewhere", run_id="bad")
    with pytest.raises(ValueError):
        universe.write_universe_artifacts(manifest, run_id="..")
