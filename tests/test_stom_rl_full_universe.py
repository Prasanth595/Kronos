"""Tests for Page 16 full-universe gate (session enumeration + checkpoint/resume).

These tests use a tiny temp-sqlite fixture shaped like the STOM tick DB (UTF-8
Korean columns, ``index`` = YYYYMMDDHHMMSS).  There is NO dependency on the real
29.7 GB DB.  They verify the four gate-critical behaviours:

(a) session enumeration groups *co-dated* symbols (disjoint recording dates);
(b) the checkpoint manifest is written with per-session status;
(c) ``--resume`` SKIPS sessions already marked ``done`` (the key contract);
(d) a failed/stuck session is recorded, never silently lost.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from stom_rl.full_universe import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_RUNNING,
    FullUniverseConfig,
    RunManifest,
    SessionManifestEntry,
    enumerate_sessions,
    flag_stuck_sessions,
    run_full_universe,
)

RULES_DIR = Path(__file__).resolve().parents[1] / "stom_rl" / "rules"

# STOM tick DB column order (UTF-8 Korean names), trimmed to the RL fields.
_FIXTURE_COLUMNS = [
    "index",
    "현재가",
    "시가",
    "고가",
    "저가",
    "초당매수수량",
    "초당매도수량",
    "체결강도",
    "초당거래대금",
    "회전율",
    "매수총잔량",
    "매도총잔량",
    "매수호가1",
    "매도호가1",
]


def _row(idx: int, close: float, buy: float, sell: float, amount: float, strength: float = 200.0) -> tuple:
    return (idx, close, close, close + 10.0, close - 10.0, buy, sell, strength, amount, 0.05, 80.0, 20.0, close - 10.0, close + 10.0)


def _session_rows(date: str, n: int = 8, base: float = 1000.0) -> list:
    """``n`` one-second rows on session ``date`` with buy-dominant order flow.

    Timestamps are ``<date>0900SS``; buy_qty > sell_qty and bid-side imbalance so
    the demand-pressure rule selects them and there are enough distinct
    timestamps to form a walk-forward split.
    """

    rows = []
    for s in range(n):
        idx = int(f"{date}0900{s:02d}")
        rows.append(_row(idx, base + s, buy=20.0 + s, sell=3.0, amount=500.0 + 10.0 * s))
    return rows


def _make_db(db_path: Path, tables: dict[str, list[tuple]]) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        column_defs = ", ".join(f'"{name}"' for name in _FIXTURE_COLUMNS)
        placeholders = ", ".join(["?"] * len(_FIXTURE_COLUMNS))
        for table_name, rows in tables.items():
            conn.execute(f'CREATE TABLE "{table_name}" ({column_defs})')
            conn.executemany(f'INSERT INTO "{table_name}" VALUES ({placeholders})', rows)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def disjoint_db(tmp_path: Path) -> Path:
    """A DB where symbols have DISJOINT recording dates plus one co-dated date.

    * 000100, 000150 both record on 20250709 (co-dated -> one panel group).
    * 000250 records only on 20250710 (its own session).
    """

    db = tmp_path / "tiny_stom.db"
    _make_db(
        db,
        {
            "000100": _session_rows("20250709", base=1000.0),
            "000150": _session_rows("20250709", base=2000.0),
            "000250": _session_rows("20250710", base=3000.0),
        },
    )
    return db


# ---------------------------------------------------------------------------
# (a) session enumeration groups co-dated symbols
# ---------------------------------------------------------------------------
def test_enumerate_sessions_groups_codated_symbols(disjoint_db: Path):
    sessions = enumerate_sessions(disjoint_db)

    assert set(sessions.keys()) == {"20250709", "20250710"}
    # Co-dated symbols are grouped; the disjoint symbol stands alone.
    assert sessions["20250709"] == ["000100", "000150"]
    assert sessions["20250710"] == ["000250"]
    # Symbols never cross sessions (disjoint recording dates honoured).
    assert "000250" not in sessions["20250709"]


def test_enumerate_sessions_respects_max_symbols(disjoint_db: Path):
    # Only the first table (000100) is scanned -> only its session appears.
    sessions = enumerate_sessions(disjoint_db, max_symbols=1)
    assert sessions == {"20250709": ["000100"]}


# ---------------------------------------------------------------------------
# (b) checkpoint manifest written
# ---------------------------------------------------------------------------
def test_run_writes_manifest_with_per_session_status(disjoint_db: Path, tmp_path: Path):
    out = tmp_path / "out"
    config = FullUniverseConfig(
        db_path=str(disjoint_db),
        rule_path=str(RULES_DIR / "buy_demand_pressure.json"),
        output_dir=str(out),
        n_folds=1,
    )
    result = run_full_universe(config)

    manifest = RunManifest.load(out)
    assert manifest is not None
    assert (out / "_manifest.json").exists()
    # Both enumerated sessions are tracked and completed.
    assert set(manifest.entries.keys()) == {"20250709", "20250710"}
    for session in ("20250709", "20250710"):
        entry = manifest.entries[session]
        assert entry.status == STATUS_DONE
        assert entry.started_at and entry.finished_at
        assert entry.candidate_count >= 0
    assert set(result["processed"]) == {"20250709", "20250710"}
    # Per-session artifacts exist.
    assert (out / "20250709" / "candidates.csv").exists()
    assert (out / "20250709" / "session_summary.json").exists()


# ---------------------------------------------------------------------------
# (c) resume SKIPS done sessions (the key test)
# ---------------------------------------------------------------------------
def test_resume_skips_done_sessions(disjoint_db: Path, tmp_path: Path):
    out = tmp_path / "out"
    config = FullUniverseConfig(
        db_path=str(disjoint_db),
        rule_path=str(RULES_DIR / "buy_demand_pressure.json"),
        output_dir=str(out),
        n_folds=1,
    )

    # First run: process only 20250709.
    first = run_full_universe(config, sessions=["20250709"])
    assert first["processed"] == ["20250709"]

    manifest = RunManifest.load(out)
    done_finished_at = manifest.entries["20250709"].finished_at
    assert manifest.entries["20250709"].status == STATUS_DONE

    # Second run with resume over BOTH sessions: 20250709 is skipped, 20250710 runs.
    second = run_full_universe(config, sessions=["20250709", "20250710"], resume=True)
    assert second["skipped"] == ["20250709"]
    assert second["processed"] == ["20250710"]

    # The skipped session's manifest entry is untouched (not reprocessed).
    manifest_after = RunManifest.load(out)
    assert manifest_after.entries["20250709"].finished_at == done_finished_at

    # The skip is recorded in the progress log.
    progress = (out / "_progress.log").read_text(encoding="utf-8")
    assert "SKIP session=20250709 status=done" in progress


def test_resume_without_flag_reprocesses(disjoint_db: Path, tmp_path: Path):
    """Without --resume a done session is re-run (resume is opt-in)."""

    out = tmp_path / "out"
    config = FullUniverseConfig(
        db_path=str(disjoint_db),
        rule_path=str(RULES_DIR / "buy_demand_pressure.json"),
        output_dir=str(out),
        n_folds=1,
    )
    run_full_universe(config, sessions=["20250709"])
    again = run_full_universe(config, sessions=["20250709"], resume=False)
    assert again["processed"] == ["20250709"]
    assert again["skipped"] == []


# ---------------------------------------------------------------------------
# (d) failed / stuck session recorded, not silently lost
# ---------------------------------------------------------------------------
def test_failed_session_recorded(disjoint_db: Path, tmp_path: Path):
    out = tmp_path / "out"
    # A session with no symbols (not in the index) cannot exist; instead force a
    # failure by pointing the run at a session whose symbols are scanned but the
    # rule path is invalid, so load_rules raises inside run_session.
    config = FullUniverseConfig(
        db_path=str(disjoint_db),
        rule_path=str(tmp_path / "missing_rule.json"),  # does not exist -> raises
        output_dir=str(out),
        n_folds=1,
    )
    result = run_full_universe(config, sessions=["20250709"])

    assert result["failed"] == ["20250709"]
    assert result["processed"] == []
    manifest = RunManifest.load(out)
    entry = manifest.entries["20250709"]
    assert entry.status == STATUS_FAILED
    assert entry.error  # the error is captured, not swallowed
    progress = (out / "_progress.log").read_text(encoding="utf-8")
    assert "SESSION_FAILED session=20250709" in progress


def test_flag_stuck_sessions_detects_long_running():
    manifest = RunManifest(rule="r", output_dir="o")
    manifest.entries["20250709"] = SessionManifestEntry(
        session="20250709",
        status=STATUS_RUNNING,
        started_at="2026-05-26T00:00:00Z",
    )
    manifest.entries["20250710"] = SessionManifestEntry(
        session="20250710",
        status=STATUS_DONE,
        started_at="2026-05-26T00:00:00Z",
    )
    # Reference time is 2 hours after the running session started; budget 1800s.
    import datetime as _dt

    now = _dt.datetime(2026, 5, 26, 2, 0, 0, tzinfo=_dt.timezone.utc).timestamp()
    stuck = flag_stuck_sessions(manifest, stuck_seconds=1800.0, now=now)
    assert stuck == ["20250709"]  # done session is never flagged
