"""Bridge bounded real SQLite opening episodes into workflow frames."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import pandas as pd  # noqa: PANDAS_OK - existing opening workflow consumes pandas frames

from .opening_30m_rl_realdata import DEFAULT_DB_PATH, REQUIRED_COLUMNS, JsonValue
from .participant_pressure_features import FEATURE_SPECS

SUMMARY_FILENAME: Final[str] = "realdata_adapter_summary.json"
ADAPTER_REQUIRED_COLUMNS: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(
        list(REQUIRED_COLUMNS)
        + [
            column
            for spec in FEATURE_SPECS
            if spec.available_at_decision_second == "required"
            for column in spec.required_columns
        ]
    )
)


@dataclass(frozen=True, slots=True)
class RealdataAdapterConfig:
    """Bounded DB-to-frame adapter configuration."""

    db_path: Path | str = DEFAULT_DB_PATH
    output_dir: Path | str = Path(".omo") / "evidence" / "opening_30m_realdata_adapter"
    max_tables: int = 5
    max_sessions_per_table: int = 1
    max_rows_per_session: int = 1800
    min_rows_per_session: int = 4
    time_start: str = "090000"
    time_end: str = "093000"
    write_artifact: bool = True


@dataclass(frozen=True, slots=True)
class RealdataAdapterResult:
    """Workflow-ready real-data frames plus read-only extraction summary."""

    frames: list[pd.DataFrame]
    summary: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class RealdataNoGoDataError(ValueError):
    """Raised after writing a NO-GO_DATA adapter summary."""

    reason: str

    def __str__(self) -> str:
        return self.reason


def load_opening_realdata_frames(config: RealdataAdapterConfig) -> RealdataAdapterResult:
    """Return bounded real DB frames in the opening workflow input shape."""

    _validate_config(config)
    output_dir = Path(config.output_dir)
    frames: list[pd.DataFrame] = []
    sampled_tables: list[dict[str, JsonValue]] = []

    conn = _connect_readonly(Path(config.db_path).resolve())
    try:
        for table in _list_stock_tables(conn, max_tables=config.max_tables):
            table_summary, table_frames = _frames_for_table(conn, table, config)
            sampled_tables.append(table_summary)
            frames.extend(table_frames)
    finally:
        conn.close()

    verdict = "INCONCLUSIVE" if frames else "NO-GO_DATA"
    summary: dict[str, JsonValue] = {
        "artifact_type": "opening_30m_realdata_adapter",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": verdict,
        "sqlite_uri_mode": "ro",
        "query_only": True,
        "bounds": {
            "max_tables": int(config.max_tables),
            "max_sessions_per_table": int(config.max_sessions_per_table),
            "max_rows_per_session": int(config.max_rows_per_session),
            "min_rows_per_session": int(config.min_rows_per_session),
            "time_start": config.time_start,
            "time_end": config.time_end,
        },
        "frame_count": len(frames),
        "sampled_tables": sampled_tables,
        "safety_note": "Read-only bounded real-data frames; not live-ready and not a profit model.",
    }
    if config.write_artifact:
        _write_json(output_dir / SUMMARY_FILENAME, summary)
    if not frames:
        raise RealdataNoGoDataError("NO-GO_DATA: no eligible bounded real-data opening frames")
    return RealdataAdapterResult(frames=frames, summary=summary)


def _validate_config(config: RealdataAdapterConfig) -> None:
    if int(config.max_tables) <= 0:
        raise RealdataNoGoDataError("NO-GO_DATA: max_tables must be positive")
    if int(config.max_sessions_per_table) <= 0:
        raise RealdataNoGoDataError("NO-GO_DATA: max_sessions_per_table must be positive")
    if int(config.max_rows_per_session) <= 0:
        raise RealdataNoGoDataError("NO-GO_DATA: max_rows_per_session must be positive")
    if int(config.min_rows_per_session) <= 0:
        raise RealdataNoGoDataError("NO-GO_DATA: min_rows_per_session must be positive")
    if not _is_hhmmss(config.time_start) or not _is_hhmmss(config.time_end):
        raise RealdataNoGoDataError("NO-GO_DATA: time bounds must be HHMMSS")
    if config.time_start > config.time_end:
        raise RealdataNoGoDataError("NO-GO_DATA: time_start must be <= time_end")


def _is_hhmmss(value: str) -> bool:
    return len(value) == 6 and value.isdigit()


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise RealdataNoGoDataError(f"NO-GO_DATA: SQLite DB not found: {db_path}")
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _list_stock_tables(conn: sqlite3.Connection, *, max_tables: int) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [str(row[0]) for row in rows if str(row[0]).isdigit()][:max_tables]


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({_quote_identifier(table)})").fetchall()
    return [str(row[1]) for row in rows]


def _frames_for_table(
    conn: sqlite3.Connection,
    table: str,
    config: RealdataAdapterConfig,
) -> tuple[dict[str, JsonValue], list[pd.DataFrame]]:
    columns = _table_columns(conn, table)
    missing = [column for column in ADAPTER_REQUIRED_COLUMNS if column not in set(columns)]
    if missing:
        return (
            {
                "symbol": table,
                "exclusion_reason": f"missing required columns: {missing}",
                "missing_required_columns": missing,
                "sessions": [],
            },
            [],
        )

    sessions = _sessions_for_table(conn, table, config)
    frames: list[pd.DataFrame] = []
    session_summaries: list[dict[str, JsonValue]] = []
    for session in sessions:
        frame = _read_session_frame(conn, table, session, config)
        row_count = int(len(frame))
        if row_count < int(config.min_rows_per_session):
            session_summaries.append(
                {"session": session, "row_count": row_count, "eligible": False, "exclusion_reason": "insufficient rows"}
            )
            continue
        frame.insert(0, "session", session)
        frame.insert(0, "symbol", table)
        frames.append(frame)
        session_summaries.append({"session": session, "row_count": row_count, "eligible": True, "exclusion_reason": ""})

    table_summary: dict[str, JsonValue] = {
        "symbol": table,
        "leading_zero_preserved": table.startswith("0"),
        "missing_required_columns": [],
        "exclusion_reason": "" if frames else "no eligible sessions",
        "sessions": session_summaries,
    }
    return table_summary, frames


def _sessions_for_table(
    conn: sqlite3.Connection,
    table: str,
    config: RealdataAdapterConfig,
) -> list[str]:
    query = (
        f"SELECT substr(CAST(\"index\" AS TEXT), 1, 8) AS session "
        f"FROM {_quote_identifier(table)} "
        "WHERE substr(CAST(\"index\" AS TEXT), 9, 6) >= ? "
        "AND substr(CAST(\"index\" AS TEXT), 9, 6) <= ? "
        "GROUP BY session ORDER BY session LIMIT ?"
    )
    rows = conn.execute(query, (config.time_start, config.time_end, int(config.max_sessions_per_table))).fetchall()
    return [str(row[0]) for row in rows]


def _read_session_frame(
    conn: sqlite3.Connection,
    table: str,
    session: str,
    config: RealdataAdapterConfig,
) -> pd.DataFrame:
    columns = ", ".join(_quote_identifier(column) for column in ADAPTER_REQUIRED_COLUMNS)
    query = (
        f"SELECT {columns} FROM {_quote_identifier(table)} "
        "WHERE substr(CAST(\"index\" AS TEXT), 1, 8) = ? "
        "AND substr(CAST(\"index\" AS TEXT), 9, 6) >= ? "
        "AND substr(CAST(\"index\" AS TEXT), 9, 6) <= ? "
        "ORDER BY \"index\" LIMIT ?"
    )
    return pd.read_sql_query(
        query,
        conn,
        params=(session, config.time_start, config.time_end, int(config.max_rows_per_session)),
    )


def _write_json(path: Path, payload: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")
