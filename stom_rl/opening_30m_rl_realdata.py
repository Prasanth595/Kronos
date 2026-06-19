"""Read-only real-data readiness sampling for opening 30-minute RL research."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

DEFAULT_DB_PATH: Final[Path] = Path("_database") / "stock_tick_back.db"
DEFAULT_OUTPUT_PATH: Final[Path] = Path(".omo") / "evidence" / "opening_30m_realdata_readiness.json"
REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "index",
    "\ud604\uc7ac\uac00",
    "\uccb4\uacb0\uac15\ub3c4",
    "\ucd08\ub2f9\ub9e4\uc218\uae08\uc561",
    "\ucd08\ub2f9\ub9e4\ub3c4\uae08\uc561",
    "\ucd08\ub2f9\ub9e4\uc218\uc218\ub7c9",
    "\ucd08\ub2f9\ub9e4\ub3c4\uc218\ub7c9",
    "\ub9e4\uc218\ucd1d\uc794\ub7c9",
    "\ub9e4\ub3c4\ucd1d\uc794\ub7c9",
    "\ub9e4\uc218\ud638\uac001",
    "\ub9e4\ub3c4\ud638\uac001",
    "\ub9e4\uc218\uc794\ub7c91",
    "\ub9e4\ub3c4\uc794\ub7c91",
)
OPTIONAL_PARTICIPANT_FLOW_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "foreign_net_buy": ("foreign_net_buy", "외국인순매수"),
    "institution_net_buy": ("institution_net_buy", "기관순매수"),
    "program_net_buy": ("program_net_buy", "프로그램순매수"),
}


@dataclass(frozen=True, slots=True)
class RealdataSamplerConfig:
    """Bounded sampler configuration for local STOM SQLite opening data."""

    db_path: Path | str = DEFAULT_DB_PATH
    output_path: Path | str = DEFAULT_OUTPUT_PATH
    max_tables: int = 5
    max_rows_per_table: int = 20
    time_start: str = "090000"
    time_end: str = "093000"
    write_artifact: bool = True


@dataclass(frozen=True, slots=True)
class RealdataSamplerBoundsError(ValueError):
    """Raised when a real-data sample request is not safely bounded."""

    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class RealdataSamplerSchemaError(ValueError):
    """Raised when the SQLite source cannot satisfy sampler safety rules."""

    reason: str

    def __str__(self) -> str:
        return self.reason


def classify_staging_path(path: str) -> str:
    """Classify generated/session paths for commit-scope policy checks."""

    normalized = path.replace("\\", "/").lower()
    if normalized.startswith((".omc/", ".codegraph/", "_database/")) or "__pycache__/" in normalized:
        return "exclude_from_commit"
    if "cdp-profile" in normalized or ("browser" in normalized and "profile" in normalized):
        return "exclude_from_commit"
    if normalized.startswith("webui/static/v2/dist/"):
        return "frontend_dist"
    if normalized.startswith(".omo/"):
        return "omo_plan_evidence"
    return "source_or_review_required"


def sample_opening_realdata_readiness(config: RealdataSamplerConfig) -> dict[str, JsonValue]:
    """Sample bounded real DB schema/readiness evidence without write authority."""

    _validate_config(config)
    db_path = Path(config.db_path).resolve()
    if not db_path.is_file():
        raise RealdataSamplerSchemaError(f"SQLite DB not found: {db_path}")

    conn = _connect_readonly(db_path)
    try:
        query_only = _query_only_enabled(conn)
        tables = _list_stock_tables(conn, max_tables=config.max_tables)
        sampled_tables = [
            _sample_table_readiness(conn, table, config)
            for table in tables
        ]
    finally:
        conn.close()

    payload: dict[str, JsonValue] = {
        "artifact_type": "opening_30m_realdata_readiness",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "db_path": str(db_path),
        "sqlite_uri_mode": "ro",
        "query_only": query_only,
        "bounds": {
            "max_tables": int(config.max_tables),
            "max_rows_per_table": int(config.max_rows_per_table),
            "time_start": config.time_start,
            "time_end": config.time_end,
        },
        "required_columns": list(REQUIRED_COLUMNS),
        "sampled_table_count": len(sampled_tables),
        "sampled_tables": sampled_tables,
        "optional_participant_flow": _participant_flow_availability(sampled_tables),
        "safety_note": "Read-only bounded schema/readiness sample; not a live-ready or profitability claim.",
        "config": _json_ready_config(config),
    }
    if config.write_artifact:
        _write_json(Path(config.output_path), payload)
    return payload


def _validate_config(config: RealdataSamplerConfig) -> None:
    if int(config.max_tables) <= 0:
        raise RealdataSamplerBoundsError("max_tables must be positive to prevent unbounded DB scans")
    if int(config.max_rows_per_table) <= 0:
        raise RealdataSamplerBoundsError("max_rows_per_table must be positive to prevent unbounded DB scans")
    if not _is_hhmmss(config.time_start):
        raise RealdataSamplerBoundsError("time_start must be HHMMSS")
    if not _is_hhmmss(config.time_end):
        raise RealdataSamplerBoundsError("time_end must be HHMMSS")
    if config.time_start > config.time_end:
        raise RealdataSamplerBoundsError("time_start must be <= time_end")


def _is_hhmmss(value: str) -> bool:
    return len(value) == 6 and value.isdigit()


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _query_only_enabled(conn: sqlite3.Connection) -> bool:
    row = conn.execute("PRAGMA query_only").fetchone()
    if row is None:
        raise RealdataSamplerSchemaError("PRAGMA query_only returned no row")
    return int(row[0]) == 1


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _list_stock_tables(conn: sqlite3.Connection, *, max_tables: int) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name LIMIT ?", (max_tables,)).fetchall()
    return [str(row[0]) for row in rows if str(row[0]).isdigit()]


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({_quote_identifier(table)})").fetchall()
    return [str(row[1]) for row in rows]


def _sample_table_readiness(
    conn: sqlite3.Connection,
    table: str,
    config: RealdataSamplerConfig,
) -> dict[str, JsonValue]:
    columns = _table_columns(conn, table)
    column_set = set(columns)
    missing = [column for column in REQUIRED_COLUMNS if column not in column_set]
    row_count = _bounded_row_count(conn, table, config) if not missing else 0
    return {
        "symbol": table,
        "leading_zero_preserved": table.startswith("0"),
        "columns": columns,
        "missing_required_columns": missing,
        "required_columns_available": not missing,
        "sample_row_count": row_count,
        "optional_participant_flow": {
            key: {
                "available": any(alias in column_set for alias in aliases),
                "filled_with_zero": False,
            }
            for key, aliases in OPTIONAL_PARTICIPANT_FLOW_COLUMNS.items()
        },
    }


def _bounded_row_count(
    conn: sqlite3.Connection,
    table: str,
    config: RealdataSamplerConfig,
) -> int:
    query = (
        f"SELECT COUNT(*) FROM ("
        f"SELECT 1 FROM {_quote_identifier(table)} "
        "WHERE substr(CAST(\"index\" AS TEXT), 9, 6) >= ? "
        "AND substr(CAST(\"index\" AS TEXT), 9, 6) <= ? "
        "ORDER BY \"index\" LIMIT ?)"
    )
    row = conn.execute(query, (config.time_start, config.time_end, int(config.max_rows_per_table))).fetchone()
    if row is None:
        return 0
    return int(row[0])


def _participant_flow_availability(sampled_tables: list[dict[str, JsonValue]]) -> dict[str, JsonValue]:
    availability: dict[str, JsonValue] = {}
    for key in OPTIONAL_PARTICIPANT_FLOW_COLUMNS:
        available = any(_table_participant_available(table, key) for table in sampled_tables)
        availability[key] = {"available": available, "filled_with_zero": False}
    return availability


def _table_participant_available(table: dict[str, JsonValue], key: str) -> bool:
    flow = table.get("optional_participant_flow")
    if not isinstance(flow, dict):
        return False
    detail = flow.get(key)
    if not isinstance(detail, dict):
        return False
    return detail.get("available") is True


def _json_ready_config(config: RealdataSamplerConfig) -> dict[str, JsonValue]:
    raw = asdict(config)
    return {key: str(value) if isinstance(value, Path) else value for key, value in raw.items()}


def _write_json(path: Path, payload: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def main() -> int:
    """Run the bounded real-data smoke CLI."""

    from .opening_30m_rl_realdata_cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
