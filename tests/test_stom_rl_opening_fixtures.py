import codecs

import pandas as pd  # noqa: PANDAS_OK - verifies pandas-compatible STOM fixture frames

from tests.fixtures.stom_opening_rl import (
    build_opening_fixture_frames,
    opening_orderbook_frame,
    quote_coverage_report,
    write_opening_fixture_csv,
)


def test_opening_fixture_preserves_codes_sessions_and_utf8(tmp_path):
    frames = build_opening_fixture_frames()
    combined = pd.concat(frames, ignore_index=True)
    sessions = combined["session"].drop_duplicates().tolist()
    output_path = tmp_path / "opening_fixture.csv"

    write_opening_fixture_csv(output_path, combined)

    raw = output_path.read_bytes()
    loaded = pd.read_csv(output_path, dtype={"symbol": str, "session": str}, encoding="utf-8-sig")
    assert raw.startswith(codecs.BOM_UTF8)
    assert any(symbol.startswith("000") for symbol in loaded["symbol"].unique())
    assert sessions == sorted(sessions)
    assert loaded["session"].drop_duplicates().tolist() == sessions
    assert "체결강도" in loaded.columns
    assert "매수총잔량" in loaded.columns
    assert loaded["symbol"].iloc[0] == "000250"


def test_opening_fixture_can_model_missing_quote_coverage():
    full_quote = opening_orderbook_frame(symbol="000250", session="20250103")
    missing_quote = opening_orderbook_frame(
        symbol="000250",
        session="20250106",
        missing_quote=True,
    )

    full_report = quote_coverage_report(full_quote)
    missing_report = quote_coverage_report(missing_quote)
    assert full_report["quote_coverage"] == 1.0
    assert full_report["missing_quote_rows"] == 0
    assert 0.0 < missing_report["quote_coverage"] < 1.0
    assert missing_report["missing_quote_rows"] > 0
    assert set(full_quote.columns) == set(missing_quote.columns)
