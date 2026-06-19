"""Read-only analysis helpers for the daily OHLCV SQLite database.

The daily DB is a research input.  These helpers never mutate it; generated
summaries belong under ``webui/rl_runs`` and every price-derived result keeps the
adjustment provenance explicit because the source DB does not carry corporate
action metadata.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAILY_DB_PATH = REPO_ROOT / "_database" / "Stock_Database_ohlcv_1day.db"
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "webui" / "rl_runs" / "daily_ohlcv_db_summary"

DAILY_TABLE_RE = re.compile(r"^[AQ][0-9A-Za-z]{6}$")
SYMBOL_RE = re.compile(r"^[0-9A-Za-z]{6}$")
EXPECTED_COLUMNS = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "상장주식수",
    "외국인주문한도수량",
    "외국인현보유수량",
    "외국인현보유비율",
    "기관순매수",
    "기관누적순매수",
]
CORE_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
PRICE_BASIS = "unknown"
PRICE_BASIS_EVIDENCE = (
    "Daily OHLCV tables include price/volume columns but no explicit adjusted/raw "
    "price flag, split factor, dividend, or corporate-action table was found in "
    "the daily DB contract; decision-grade return labels must treat adjustment "
    "status as unknown until independently verified."
)
ADJUSTMENT_POLICY = (
    "flag_split_like_discontinuities_and_block_decision_grade_metrics_until_price_basis_verified"
)
PRICE_BASIS_STATUS = "UNKNOWN_CONFIRMED"
DECISION_GRADE_RETURN_STATUS = "BLOCKED_UNTIL_PRICE_BASIS_VERIFIED"
PRICE_BASIS_COMPONENT_STATUS = {
    "adjusted_price": "not_declared_in_daily_db_schema",
    "raw_price": "not_declared_in_daily_db_schema",
    "split_adjustment": "not_declared_no_split_factor_or_corporate_action_table",
    "dividend_adjustment": "not_declared_no_dividend_or_total_return_field",
}
PRICE_BASIS_BLOCKING_IMPLICATIONS = [
    "decision_grade_return_labels_blocked_until_adjusted_or_raw_basis_is_verified",
    "split_like_discontinuities_must_be_flagged_or_excluded_from_model_decision_windows",
    "dashboard_must_keep_model_build_allowed_false_until_price_basis_and_gates_pass",
]
PRICE_BASIS_REQUIRED_EVIDENCE = [
    "official_or_vendor_field_declaring_adjusted_or_raw_close",
    "split_factor_or_corporate_action_reference_for_split_like_windows",
    "dividend_or_total_return_policy_if_returns_claim_dividend_adjustment",
    "dated_audit_artifact_showing_rows_windows_and_downstream_blocker_effect",
]
PRICE_BASIS_ALLOWED_USES = [
    "read_only_db_coverage_and_quality_inspection",
    "research_feature_preview_with_price_basis_unknown_label",
    "split_like_window_discovery_for_future_exclusion_or_manual_review",
]
PRICE_BASIS_BLOCKED_USES = [
    "decision_grade_return_labels",
    "model_build_or_candidate_promotion",
    "paper_forward_or_live_readiness_claims",
]
PRICE_BASIS_USER_GUIDANCE = [
    {
        "section": "D0 summary",
        "can_do": "Inspect table count, date coverage, OHLC quality flags, and representative split-like windows.",
        "must_not_do": "Treat D0 returns as decision-grade labels while price_basis is unknown.",
        "next_action": "Provide independent adjusted/raw and split/dividend policy evidence, or keep the blocker visible.",
    },
    {
        "section": "D2/D3 downstream",
        "can_do": "Build preview datasets and baselines with inherited price-basis warnings.",
        "must_not_do": "Freeze or promote baselines without a verified price-basis policy.",
        "next_action": "Rerun dataset and baseline verification after price-basis status changes.",
    },
    {
        "section": "D4-D9 promotion",
        "can_do": "Use D4-D9 charts as research diagnostics only.",
        "must_not_do": "Set model_build_allowed or paper_forward_allowed from unknown-basis evidence.",
        "next_action": "Keep D0_PRICE_BASIS_NOT_VERIFIED in effective gate blockers until D0 is verified.",
    },
]




@dataclass(frozen=True)
class DailyTableRef:
    table: str
    code: str
    prefix: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _db_fingerprint(path: Path) -> str:
    stat = path.stat()
    payload = f"{path.resolve()}|{stat.st_size}|{int(stat.st_mtime)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _quote_ident(name: str) -> str:
    if not DAILY_TABLE_RE.match(name):
        raise ValueError(f"Invalid daily table name: {name!r}")
    return '"' + name.replace('"', '""') + '"'


def validate_daily_table_name(table: str) -> str:
    candidate = str(table or "").strip()
    if not DAILY_TABLE_RE.match(candidate):
        raise ValueError("Daily OHLCV table names must match ^[AQ][0-9A-Za-z]{6}$")
    return candidate


def resolve_daily_table(symbol_or_table: str, *, default_prefix: str = "A") -> DailyTableRef:
    """Resolve a user supplied symbol/table while preserving leading zeros."""

    raw = str(symbol_or_table or "").strip()
    if DAILY_TABLE_RE.match(raw):
        table = raw
    elif SYMBOL_RE.match(raw):
        if default_prefix not in {"A", "Q"}:
            raise ValueError("default_prefix must be A or Q")
        table = f"{default_prefix}{raw}"
    else:
        raise ValueError("Daily OHLCV symbol must be a 6-character code or A/Q-prefixed table")
    return DailyTableRef(table=table, code=table[1:], prefix=table[0])


def connect_readonly(db_path: Path | str = DEFAULT_DAILY_DB_PATH) -> sqlite3.Connection:
    """Open SQLite in read-only/query-only mode."""

    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(path)
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [str(row[0]) for row in rows]


def list_daily_tables(db_path: Path | str = DEFAULT_DAILY_DB_PATH) -> list[str]:
    with connect_readonly(db_path) as conn:
        return [name for name in _list_tables(conn) if DAILY_TABLE_RE.match(name)]


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall()
    return [str(row[1]) for row in rows]


def _schema_signature(columns: Iterable[str]) -> str:
    return hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest()[:16]


def _scalar(conn: sqlite3.Connection, query: str) -> Any:
    row = conn.execute(query).fetchone()
    return row[0] if row else None


def _safe_numeric(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def build_price_basis_audit(
    *,
    quality_scan_scope: str,
    quality_scan_table_count: int,
    quality_scan_total_table_count: int,
    quality_scan_complete: bool,
    representative_windows: list[dict[str, Any]],
    split_like_table_count: int,
    split_like_window_sample_count: int,
    per_table_window_limit: int | None,
) -> dict[str, Any]:
    """Return the explicit D0 price-basis verdict used by docs/API/UI."""

    return {
        "status": PRICE_BASIS_STATUS,
        "price_basis": PRICE_BASIS,
        "decision_grade_return_status": DECISION_GRADE_RETURN_STATUS,
        "component_status": dict(PRICE_BASIS_COMPONENT_STATUS),
        "evidence": PRICE_BASIS_EVIDENCE,
        "adjustment_policy": ADJUSTMENT_POLICY,
        "blocking_implications": list(PRICE_BASIS_BLOCKING_IMPLICATIONS),
        "required_evidence": list(PRICE_BASIS_REQUIRED_EVIDENCE),
        "allowed_uses": list(PRICE_BASIS_ALLOWED_USES),
        "blocked_uses": list(PRICE_BASIS_BLOCKED_USES),
        "user_guidance": [dict(row) for row in PRICE_BASIS_USER_GUIDANCE],
        "quality_scan_scope": quality_scan_scope,
        "quality_scan_table_count": quality_scan_table_count,
        "quality_scan_total_table_count": quality_scan_total_table_count,
        "quality_scan_complete": quality_scan_complete,
        "split_like_table_count": split_like_table_count,
        "split_like_window_sample_count": split_like_window_sample_count,
        "per_table_window_limit": per_table_window_limit,
        "representative_windows": representative_windows,
        "scan_limitation": (
            "split_like windows are representative evidence capped per table; "
            "they confirm unknown adjustment risk but do not prove exact corporate actions"
        ),
    }



def _sample_rows(conn: sqlite3.Connection, table: str, *, limit: int = 5) -> list[dict[str, Any]]:
    safe_limit = max(0, min(int(limit), 200))
    rows = conn.execute(
        f"SELECT * FROM {_quote_ident(table)} ORDER BY date DESC LIMIT ?",
        (safe_limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def analyze_table_quality(
    conn: sqlite3.Connection,
    table: str,
    *,
    discontinuity_limit: int = 20,
) -> dict[str, Any]:
    table = validate_daily_table_name(table)
    qt = _quote_ident(table)
    columns = set(_table_columns(conn, table))
    missing_core = [col for col in CORE_COLUMNS if col not in columns]
    if missing_core:
        return {
            "table": table,
            "missing_core_columns": missing_core,
            "null_core_rows": None,
            "nonpositive_ohlc_rows": None,
            "ohlc_inconsistency_rows": None,
            "split_like_discontinuity_count": None,
            "split_like_windows": [],
            "material_unknown_adjustment_windows": [],
            "quality_status": "BLOCKED_SCHEMA",
        }

    null_core = _scalar(
        conn,
        f"SELECT COUNT(*) FROM {qt} WHERE date IS NULL OR open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL OR volume IS NULL",
    )
    nonpositive_ohlc = _scalar(
        conn,
        f"SELECT COUNT(*) FROM {qt} WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0",
    )
    ohlc_bad = _scalar(
        conn,
        f"SELECT COUNT(*) FROM {qt} WHERE high < low OR open < low OR open > high OR close < low OR close > high",
    )

    rows = conn.execute(
        f"SELECT date, open, close, volume FROM {qt} WHERE close IS NOT NULL AND close > 0 ORDER BY date"
    ).fetchall()
    windows: list[dict[str, Any]] = []
    prev: sqlite3.Row | None = None
    for row in rows:
        if prev is not None:
            prev_close = _safe_numeric(prev["close"])
            open_price = _safe_numeric(row["open"])
            close_price = _safe_numeric(row["close"])
            if prev_close and prev_close > 0:
                open_ratio = (open_price / prev_close) if open_price and open_price > 0 else None
                close_ratio = (close_price / prev_close) if close_price and close_price > 0 else None
                ratios = [r for r in (open_ratio, close_ratio) if r is not None]
                if any(r >= 4.0 or r <= 0.25 for r in ratios):
                    windows.append(
                        {
                            "previous_date": prev["date"],
                            "date": row["date"],
                            "previous_close": prev_close,
                            "open": open_price,
                            "close": close_price,
                            "open_to_previous_close_ratio": open_ratio,
                            "close_to_previous_close_ratio": close_ratio,
                            "reason": "split_like_price_jump_with_unknown_adjustment_basis",
                        }
                    )
                    if len(windows) >= discontinuity_limit:
                        break
        prev = row

    quality_status = "PASS"
    blockers: list[str] = []
    if null_core:
        blockers.append("NULL_CORE_OHLCV")
    if nonpositive_ohlc:
        blockers.append("NONPOSITIVE_OHLC")
    if ohlc_bad:
        blockers.append("OHLC_INCONSISTENCY")
    if windows:
        blockers.append("SPLIT_LIKE_DISCONTINUITY_UNKNOWN_ADJUSTMENT")
    if blockers:
        quality_status = "WATCH"

    return {
        "table": table,
        "missing_core_columns": [],
        "null_core_rows": int(null_core or 0),
        "nonpositive_ohlc_rows": int(nonpositive_ohlc or 0),
        "ohlc_inconsistency_rows": int(ohlc_bad or 0),
        "split_like_discontinuity_count": len(windows),
        "split_like_windows": windows,
        "material_unknown_adjustment_windows": windows,
        "quality_status": quality_status,
        "blockers": blockers,
    }


def summarize_symbol(
    symbol_or_table: str,
    *,
    db_path: Path | str = DEFAULT_DAILY_DB_PATH,
    sample_limit: int = 20,
) -> dict[str, Any]:
    ref = resolve_daily_table(symbol_or_table)
    with connect_readonly(db_path) as conn:
        tables = set(_list_tables(conn))
        if ref.table not in tables:
            raise FileNotFoundError(ref.table)
        qt = _quote_ident(ref.table)
        columns = _table_columns(conn, ref.table)
        row = conn.execute(f"SELECT COUNT(*) AS rows, MIN(date) AS first_date, MAX(date) AS last_date FROM {qt}").fetchone()
        quality = analyze_table_quality(conn, ref.table)
        symbol_windows = [
            {"table": ref.table, "code": ref.code, **window}
            for window in quality.get("material_unknown_adjustment_windows", [])
        ]
        return {
            "schema_version": 1,
            "table": ref.table,
            "code": ref.code,
            "prefix": ref.prefix,
            "row_count": int(row["rows"] or 0),
            "first_date": row["first_date"],
            "last_date": row["last_date"],
            "columns": columns,
            "schema_matches_expected": columns == EXPECTED_COLUMNS,
            "price_basis": PRICE_BASIS,
            "price_basis_status": PRICE_BASIS_STATUS,
            "decision_grade_return_status": DECISION_GRADE_RETURN_STATUS,
            "price_basis_evidence": PRICE_BASIS_EVIDENCE,
            "price_basis_blocking_implications": list(PRICE_BASIS_BLOCKING_IMPLICATIONS),
            "price_basis_required_evidence": list(PRICE_BASIS_REQUIRED_EVIDENCE),
            "price_basis_allowed_uses": list(PRICE_BASIS_ALLOWED_USES),
            "price_basis_blocked_uses": list(PRICE_BASIS_BLOCKED_USES),
            "price_basis_user_guidance": [dict(row) for row in PRICE_BASIS_USER_GUIDANCE],
            "adjustment_policy": ADJUSTMENT_POLICY,
            "price_basis_audit": build_price_basis_audit(
                quality_scan_scope="single_symbol",
                quality_scan_table_count=1,
                quality_scan_total_table_count=1,
                quality_scan_complete=True,
                representative_windows=symbol_windows[:10],
                split_like_table_count=1 if symbol_windows else 0,
                split_like_window_sample_count=len(symbol_windows),
                per_table_window_limit=20,
            ),
            "quality": quality,
            "sample_rows_desc": _sample_rows(conn, ref.table, limit=sample_limit),
        }



def _table_summary(conn: sqlite3.Connection, table: str, *, include_quality: bool) -> dict[str, Any]:
    qt = _quote_ident(table)
    row = conn.execute(f"SELECT COUNT(*) AS rows, MIN(date) AS first_date, MAX(date) AS last_date FROM {qt}").fetchone()
    columns = _table_columns(conn, table)
    first_date = row["first_date"]
    last_date = row["last_date"]
    summary = {
        "table": table,
        "code": table[1:],
        "prefix": table[0],
        "row_count": int(row["rows"] or 0),
        "first_date": str(first_date) if first_date is not None else None,
        "last_date": str(last_date) if last_date is not None else None,
        "schema_signature": _schema_signature(columns),
        "schema_matches_expected": columns == EXPECTED_COLUMNS,
    }
    if include_quality:
        q = analyze_table_quality(conn, table, discontinuity_limit=5)
        summary.update(
            {
                "quality_status": q["quality_status"],
                "null_core_rows": q["null_core_rows"],
                "nonpositive_ohlc_rows": q["nonpositive_ohlc_rows"],
                "ohlc_inconsistency_rows": q["ohlc_inconsistency_rows"],
                "split_like_discontinuity_count": q["split_like_discontinuity_count"],
                "material_unknown_adjustment_windows": q["material_unknown_adjustment_windows"],
            }
        )
    return summary


def summarize_daily_db(
    db_path: Path | str = DEFAULT_DAILY_DB_PATH,
    *,
    table_limit: int | None = None,
    quality_table_limit: int = 250,
) -> dict[str, Any]:
    """Return a bounded, read-only summary of the daily OHLCV DB.

    ``table_limit`` limits the number of table summaries returned to the caller,
    but aggregate counts still cover all valid A/Q daily tables.
    """

    path = Path(db_path)
    with connect_readonly(path) as conn:
        all_tables = _list_tables(conn)
        daily_tables = [name for name in all_tables if DAILY_TABLE_RE.match(name)]
        invalid_tables = [name for name in all_tables if name not in daily_tables]
        prefix_counts = Counter(name[0] for name in daily_tables)
        schema_counts: Counter[str] = Counter()
        total_rows = 0
        global_first: str | None = None
        global_last: str | None = None
        latest_counts: Counter[str] = Counter()
        summaries: list[dict[str, Any]] = []
        quality_flags: list[dict[str, Any]] = []
        material_unknown_adjustment_windows: list[dict[str, Any]] = []
        split_like_table_count = 0
        split_like_window_sample_count = 0

        safe_table_limit = len(daily_tables) if table_limit is None else max(0, min(int(table_limit), len(daily_tables)))
        safe_quality_limit = max(0, min(int(quality_table_limit), len(daily_tables)))

        for index, table in enumerate(daily_tables):
            include_quality = index < safe_quality_limit
            table_summary = _table_summary(conn, table, include_quality=include_quality)
            total_rows += int(table_summary["row_count"])
            first = str(table_summary["first_date"]) if table_summary["first_date"] is not None else None
            last = str(table_summary["last_date"]) if table_summary["last_date"] is not None else None
            if first is not None and (global_first is None or first < global_first):
                global_first = first
            if last is not None and (global_last is None or last > global_last):
                global_last = last
            if last is not None:
                latest_counts[str(last)] += 1
            schema_counts[str(table_summary["schema_signature"])] += 1
            if index < safe_table_limit:
                summaries.append(table_summary)
            if include_quality:
                table_windows = list(table_summary.get("material_unknown_adjustment_windows") or [])
                if table_windows:
                    split_like_table_count += 1
                    split_like_window_sample_count += len(table_windows)
                for window in table_windows:
                    material_unknown_adjustment_windows.append(
                        {
                            "table": table,
                            "code": table[1:],
                            **window,
                        }
                    )

                for key in ("null_core_rows", "nonpositive_ohlc_rows", "ohlc_inconsistency_rows", "split_like_discontinuity_count"):
                    value = table_summary.get(key)
                    if value:
                        quality_flags.append(
                            {
                                "table": table,
                                "code": table[1:],
                                "flag": key,
                                "value": value,
                                "status": "WATCH",
                            }
                        )

        latest_date = global_last
        tables_at_latest = latest_counts.get(latest_date or "", 0)
        quality_scan_complete = safe_quality_limit == len(daily_tables)
        price_basis_audit = build_price_basis_audit(
            quality_scan_scope="all_tables" if quality_scan_complete else "sampled_preview",
            quality_scan_table_count=safe_quality_limit,
            quality_scan_total_table_count=len(daily_tables),
            quality_scan_complete=quality_scan_complete,
            representative_windows=material_unknown_adjustment_windows[:10],
            split_like_table_count=split_like_table_count,
            split_like_window_sample_count=split_like_window_sample_count,
            per_table_window_limit=5,
        )

        return {
            "schema_version": 1,
            "generated_at": _utc_now(),
            "db_path": str(path),
            "db_fingerprint": _db_fingerprint(path),
            "read_only": True,
            "query_only": True,
            "guardrail": "Research-only daily OHLCV DB inspection; no DB mutation, no live/broker/orders, no profit claim.",
            "daily_table_regex": DAILY_TABLE_RE.pattern,
            "table_count": len(daily_tables),
            "non_daily_table_count": len(invalid_tables),
            "prefix_counts": dict(prefix_counts),
            "total_rows": total_rows,
            "first_date": global_first,
            "last_date": global_last,
            "latest_date": latest_date,
            "tables_at_latest_date": tables_at_latest,
            "latest_coverage_fraction": (tables_at_latest / len(daily_tables)) if daily_tables else 0.0,
            "expected_columns": EXPECTED_COLUMNS,
            "schema_signatures": dict(schema_counts),
            "price_basis": PRICE_BASIS,
            "price_basis_evidence": PRICE_BASIS_EVIDENCE,
            "adjustment_policy": ADJUSTMENT_POLICY,
            "price_basis_status": PRICE_BASIS_STATUS,
            "decision_grade_return_status": DECISION_GRADE_RETURN_STATUS,
            "price_basis_blocking_implications": list(PRICE_BASIS_BLOCKING_IMPLICATIONS),
            "price_basis_required_evidence": list(PRICE_BASIS_REQUIRED_EVIDENCE),
            "price_basis_allowed_uses": list(PRICE_BASIS_ALLOWED_USES),
            "price_basis_blocked_uses": list(PRICE_BASIS_BLOCKED_USES),
            "price_basis_user_guidance": [dict(row) for row in PRICE_BASIS_USER_GUIDANCE],
            "price_basis_audit": price_basis_audit,
            "quality_scan_scope": "all_tables" if quality_scan_complete else "sampled_preview",
            "quality_scan_table_count": safe_quality_limit,
            "quality_scan_total_table_count": len(daily_tables),
            "quality_scan_complete": quality_scan_complete,
            "quality_sample_table_count": safe_quality_limit,
            "table_summaries_returned": len(summaries),
            "table_summaries": summaries,
            "quality_flags": quality_flags[:500],
            "material_unknown_adjustment_windows": material_unknown_adjustment_windows[:100],
            "decision_grade_status": (
                "WATCH_PRICE_BASIS_UNKNOWN_CONFIRMED"
                if quality_scan_complete
                else "WATCH_PRICE_BASIS_UNKNOWN_CONFIRMED_QUALITY_SAMPLED"
            ),
        }


def write_db_summary_artifacts(
    summary: dict[str, Any],
    *,
    artifact_root: Path | str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Write generated dashboard artifacts from an already computed summary."""

    root = Path(artifact_root or DEFAULT_ARTIFACT_ROOT).resolve()
    default_root = DEFAULT_ARTIFACT_ROOT.resolve()
    try:
        root.relative_to(default_root)
    except ValueError:
        if root != default_root:
            raise ValueError("Daily OHLCV DB artifacts must stay under webui/rl_runs/daily_ohlcv_db_summary")
    rid = run_id or f"summary_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    if not re.match(r"^[0-9A-Za-z_.-]+$", rid) or rid in {".", ".."} or ".." in rid.split("."):
        raise ValueError("run_id contains unsafe characters")
    out_dir = (root / rid).resolve()
    try:
        out_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("run_id escapes daily OHLCV artifact root") from exc
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = out_dir / "db_summary.json"
    table_path = out_dir / "table_summaries.csv"
    quality_path = out_dir / "quality_flags.csv"
    price_basis_path = out_dir / "price_basis_audit.json"
    price_basis_windows_path = out_dir / "price_basis_windows.csv"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    table_rows = list(summary.get("table_summaries") or [])
    if table_rows:
        fields = sorted({key for row in table_rows for key in row.keys()})
        with table_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(table_rows)
    else:
        table_path.write_text("table\n", encoding="utf-8")

    quality_rows = list(summary.get("quality_flags") or [])
    if quality_rows:
        fields = sorted({key for row in quality_rows for key in row.keys()})
        with quality_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(quality_rows)
    else:
        quality_path.write_text("table,code,flag,value,status\n", encoding="utf-8")
    price_basis_path.write_text(
        json.dumps(summary.get("price_basis_audit") or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    price_basis_rows = list(summary.get("material_unknown_adjustment_windows") or [])
    if price_basis_rows:
        fields = sorted({key for row in price_basis_rows for key in row.keys()})
        with price_basis_windows_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(price_basis_rows)
    else:
        price_basis_windows_path.write_text(
            "table,code,previous_date,date,previous_close,open,close,open_to_previous_close_ratio,close_to_previous_close_ratio,reason\n",
            encoding="utf-8",
        )


    return {
        "run_id": rid,
        "artifact_dir": str(out_dir),
        "db_summary_path": str(summary_path),
        "table_summaries_path": str(table_path),
        "quality_flags_path": str(quality_path),
        "price_basis_audit_path": str(price_basis_path),
        "price_basis_windows_path": str(price_basis_windows_path),
    }


__all__ = [
    "ADJUSTMENT_POLICY",
    "DAILY_TABLE_RE",
    "DEFAULT_ARTIFACT_ROOT",
    "DEFAULT_DAILY_DB_PATH",
    "EXPECTED_COLUMNS",
    "PRICE_BASIS",
    "PRICE_BASIS_EVIDENCE",
    "PRICE_BASIS_STATUS",
    "DECISION_GRADE_RETURN_STATUS",
    "analyze_table_quality",
    "build_price_basis_audit",
    "connect_readonly",
    "list_daily_tables",
    "resolve_daily_table",
    "summarize_daily_db",
    "summarize_symbol",
    "validate_daily_table_name",
    "write_db_summary_artifacts",
]
