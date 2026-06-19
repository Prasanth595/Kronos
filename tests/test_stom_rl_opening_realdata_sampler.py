import json
import sqlite3

import pytest

from stom_rl.opening_30m_rl_realdata import (
    RealdataSamplerBoundsError,
    RealdataSamplerConfig,
    classify_staging_path,
    sample_opening_realdata_readiness,
)
from tests.fixtures.stom_opening_rl import opening_orderbook_frame


def _write_fixture_db(path):
    frame = opening_orderbook_frame(symbol="000250", session="20250103")
    with sqlite3.connect(path) as conn:
        frame.drop(columns=["symbol", "session"]).to_sql("000250", conn, index=False)
        conn.execute('CREATE TABLE "ABC001" ("index" INTEGER)')


def test_realdata_sampler_records_readonly_bounds_and_symbols(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    output_path = tmp_path / "readiness.json"
    _write_fixture_db(db_path)

    payload = sample_opening_realdata_readiness(
        RealdataSamplerConfig(
            db_path=db_path,
            output_path=output_path,
            max_tables=2,
            max_rows_per_table=3,
            time_start="090000",
            time_end="093000",
        )
    )

    saved = json.loads(output_path.read_text(encoding="utf-8-sig"))
    assert payload["artifact_type"] == "opening_30m_realdata_readiness"
    assert saved["sqlite_uri_mode"] == "ro"
    assert saved["query_only"] is True
    assert saved["bounds"]["max_tables"] == 2
    assert saved["bounds"]["max_rows_per_table"] == 3
    assert saved["bounds"]["time_start"] == "090000"
    assert saved["bounds"]["time_end"] == "093000"
    assert saved["sampled_tables"][0]["symbol"] == "000250"
    assert isinstance(saved["sampled_tables"][0]["symbol"], str)
    assert saved["sampled_tables"][0]["leading_zero_preserved"] is True
    assert saved["sampled_tables"][0]["required_columns_available"] is True
    assert saved["optional_participant_flow"]["foreign_net_buy"]["available"] is False
    assert saved["optional_participant_flow"]["foreign_net_buy"]["filled_with_zero"] is False


def test_realdata_sampler_rejects_unbounded_scan(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    _write_fixture_db(db_path)

    with pytest.raises(RealdataSamplerBoundsError, match="max_tables"):
        sample_opening_realdata_readiness(
            RealdataSamplerConfig(
                db_path=db_path,
                output_path=tmp_path / "readiness.json",
                max_tables=0,
                max_rows_per_table=3,
            )
        )


def test_staging_policy_excludes_generated_paths():
    assert classify_staging_path(".omc/sessions/abc.json") == "exclude_from_commit"
    assert classify_staging_path(".codegraph/index.db") == "exclude_from_commit"
    assert classify_staging_path("_database/stock_tick_back.db") == "exclude_from_commit"
    assert classify_staging_path("pkg/__pycache__/x.pyc") == "exclude_from_commit"
    assert classify_staging_path("webui/static/v2/dist/index.html") == "frontend_dist"
