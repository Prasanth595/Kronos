"""Daily OHLCV dataset builder for research-only daily modeling.

The builder consumes the read-only daily OHLCV database plus the conservative D1
universe manifest and emits auditable feature/label/split artifacts.  It does
not train models, place orders, or imply profit/liveness; price-basis and
universe WATCH provenance are carried into every manifest.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .daily_ohlcv_db import (
    ADJUSTMENT_POLICY,
    CORE_COLUMNS,
    DECISION_GRADE_RETURN_STATUS,
    DEFAULT_DAILY_DB_PATH,
    EXPECTED_COLUMNS,
    PRICE_BASIS,
    PRICE_BASIS_EVIDENCE,
    PRICE_BASIS_STATUS,
    REPO_ROOT,
    analyze_table_quality,
    connect_readonly,
    validate_daily_table_name,
)
from .daily_ohlcv_universe import DEFAULT_UNIVERSE_ROOT

DEFAULT_DATASET_ROOT = REPO_ROOT / "webui" / "rl_runs" / "daily_ohlcv_dataset"
DATASET_SCHEMA_VERSION = 1
DEFAULT_FEATURE_COLUMNS = [
    "return_1d",
    "return_5d",
    "volatility_5d",
    "volume_ratio_5d",
    "hl_range",
    "gap_from_prev_close",
    "foreign_holding_ratio",
    "institutional_net_buy",
]
DEFAULT_LABEL_COLUMNS = ["future_return_1d", "future_direction_1d", "future_rank_pct_1d"]
FORBIDDEN_FEATURE_PREFIXES = ("future_", "label_", "target_")
DATASET_REQUIRED_EVIDENCE = (
    "d0_price_basis_status_and_decision_grade_return_status",
    "d1_universe_manifest_sha_and_certification_status",
    "chronological_train_val_test_split_with_purge_embargo",
    "train_only_normalization_statistics",
    "material_unknown_adjustment_windows_excluded_from_eligible_rows",
    "feature_label_leakage_report",
)
DATASET_ALLOWED_USES_WITH_UPSTREAM_BLOCKERS = (
    "research_dataset_preview",
    "split_and_leakage_validation",
    "feature_pipeline_debugging",
    "dashboard_evidence_navigation",
)
DATASET_BLOCKED_USES_WITH_UPSTREAM_BLOCKERS = (
    "model_build_or_candidate_promotion",
    "decision_grade_return_labels",
    "paper_forward_or_live_readiness_claims",
)
DATASET_USER_GUIDANCE = (
    {
        "section": "D2 summary",
        "meaning": "D2 PASS means leakage and chronological split checks passed for a generated research dataset artifact.",
        "action": "Use it to inspect features, labels, splits, blocked windows, and normalization provenance.",
    },
    {
        "section": "Upstream blockers",
        "meaning": "D0 price_basis unknown or D1 universe review incomplete still blocks model promotion even if D2 leakage/split checks pass.",
        "action": "Keep upstream_gate_blockers visible until D0/D1 are independently verified.",
    },
    {
        "section": "Model/RL use",
        "meaning": "D2 is not training, not a profit claim, and not live/broker/order readiness.",
        "action": "Run D3 baselines and D5 gates before any model_build_allowed claim.",
    },
)

DATASET_PRICE_BASIS_VERIFIED_STATUSES = {"RAW_VERIFIED", "ADJUSTED_VERIFIED", "PRICE_BASIS_VERIFIED", "VERIFIED"}
DATASET_PRICE_BASIS_VERIFIED_VALUES = {"raw", "adjusted", "split_adjusted", "total_return_adjusted"}
DATASET_UNIVERSE_VERIFIED_VERDICT = "OFFICIAL_OR_MANUAL_REVIEWED"
DATASET_OFFICIAL_METADATA_VERIFIED_STATUS = "OFFICIAL_VERIFIED"
DATASET_OFFICIAL_METADATA_COMPLETE_COVERAGE = "COMPLETE"


def _price_basis_verified_for_dataset() -> bool:
    if str(PRICE_BASIS).lower() not in DATASET_PRICE_BASIS_VERIFIED_VALUES:
        return False
    if str(PRICE_BASIS_STATUS).upper() not in DATASET_PRICE_BASIS_VERIFIED_STATUSES:
        return False
    return not str(DECISION_GRADE_RETURN_STATUS).startswith("BLOCKED")


def _universe_verified_for_dataset(universe: dict[str, Any]) -> bool:
    return (
        str(universe.get("verdict") or "") == DATASET_UNIVERSE_VERIFIED_VERDICT
        and str(universe.get("universe_review_status") or universe.get("review_status") or "") == DATASET_UNIVERSE_VERIFIED_VERDICT
        and str(universe.get("official_metadata_status") or "") == DATASET_OFFICIAL_METADATA_VERIFIED_STATUS
        and str(universe.get("official_metadata_coverage_status") or "") == DATASET_OFFICIAL_METADATA_COMPLETE_COVERAGE
        and str(universe.get("universe_certification_status") or "") == DATASET_UNIVERSE_VERIFIED_VERDICT
    )


def _upstream_gate_blockers(universe: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not _price_basis_verified_for_dataset():
        blockers.append("D0_PRICE_BASIS_NOT_VERIFIED")
    if not _universe_verified_for_dataset(universe):
        blockers.append("D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED")
    return blockers



FEATURE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "return_1d": {
        "description": "Close-to-previous-close return known after the current daily close.",
        "uses_future": False,
        "availability": "after_current_close",
    },
    "return_5d": {
        "description": "Five-session trailing close return known after the current daily close.",
        "uses_future": False,
        "availability": "after_current_close",
    },
    "volatility_5d": {
        "description": "Trailing standard deviation of daily returns over up to five current/past sessions.",
        "uses_future": False,
        "availability": "after_current_close",
    },
    "volume_ratio_5d": {
        "description": "Current volume divided by trailing five-session mean volume.",
        "uses_future": False,
        "availability": "after_current_close",
    },
    "hl_range": {
        "description": "Current high-low range divided by close.",
        "uses_future": False,
        "availability": "after_current_close",
    },
    "gap_from_prev_close": {
        "description": "Current open versus previous close, still same-day causal for next-day labels.",
        "uses_future": False,
        "availability": "after_current_close",
    },
    "foreign_holding_ratio": {
        "description": "Daily foreign holding ratio from the source table, carried as end-of-day evidence.",
        "uses_future": False,
        "availability": "after_current_close",
    },
    "institutional_net_buy": {
        "description": "Daily institutional net buy value from the source table, carried as end-of-day evidence.",
        "uses_future": False,
        "availability": "after_current_close",
    },
}

LABEL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "future_return_1d": {
        "description": "Forward close-to-close return over the configured horizon; label only.",
        "uses_future": True,
    },
    "future_direction_1d": {
        "description": "Binary positive forward-return label; label only.",
        "uses_future": True,
    },
    "future_rank_pct_1d": {
        "description": "Cross-sectional percentile rank of future_return_1d on the same date; label only.",
        "uses_future": True,
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha_json(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def _safe_ratio(numerator: Any, denominator: Any) -> float | None:
    num = _safe_float(numerator)
    den = _safe_float(denominator)
    if num is None or den is None or den == 0:
        return None
    return num / den


def _pct_change(current: Any, previous: Any) -> float | None:
    ratio = _safe_ratio(current, previous)
    if ratio is None:
        return None
    return ratio - 1.0


def _mean(values: Iterable[float]) -> float | None:
    clean = [float(v) for v in values if v is not None and not math.isnan(float(v))]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _std(values: Iterable[float]) -> float | None:
    clean = [float(v) for v in values if v is not None and not math.isnan(float(v))]
    if not clean:
        return None
    avg = sum(clean) / len(clean)
    return math.sqrt(sum((value - avg) ** 2 for value in clean) / len(clean))


def _validate_run_id(run_id: str) -> str:
    rid = str(run_id or "").strip()
    if not re.match(r"^[0-9A-Za-z_.-]+$", rid) or rid in {".", ".."} or ".." in rid.split("."):
        raise ValueError("run_id contains unsafe characters")
    return rid


def _quote_ident(table: str) -> str:
    table = validate_daily_table_name(table)
    return '"' + table.replace('"', '""') + '"'


def validate_no_feature_leakage(feature_columns: Iterable[str], label_columns: Iterable[str]) -> dict[str, Any]:
    """Validate that label/future-looking columns are not used as model features."""

    features = [str(col) for col in feature_columns]
    labels = {str(col) for col in label_columns}
    forbidden = sorted(
        col
        for col in features
        if col in labels or any(col.startswith(prefix) for prefix in FORBIDDEN_FEATURE_PREFIXES)
    )
    report = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "status": "PASS" if not forbidden else "BLOCK",
        "feature_columns": features,
        "label_columns": sorted(labels),
        "forbidden_feature_columns": forbidden,
        "checks": [
            "feature_columns_do_not_overlap_label_columns",
            "feature_columns_do_not_start_with_future_label_or_target_prefix",
            "feature_definitions_mark_uses_future_false",
        ],
    }
    if forbidden:
        raise ValueError(f"Feature leakage detected: {forbidden}")
    return report


def assign_chronological_splits(
    dates: Iterable[str],
    *,
    train_fraction: float = 0.6,
    val_fraction: float = 0.2,
    purge_days: int = 5,
    embargo_days: int = 5,
) -> dict[str, str]:
    """Assign chronological train/val/test labels with blocked purge gaps."""

    ordered = sorted({str(date) for date in dates if date is not None})
    if not ordered:
        return {}
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1")
    if not 0 <= val_fraction < 1 or train_fraction + val_fraction >= 1:
        raise ValueError("train_fraction + val_fraction must be below 1")
    gap = max(0, int(purge_days), int(embargo_days))
    n_dates = len(ordered)
    train_end = max(1, min(n_dates - 2, int(n_dates * train_fraction))) if n_dates >= 3 else max(1, n_dates)
    val_end = max(train_end + 1, min(n_dates - 1, int(n_dates * (train_fraction + val_fraction)))) if n_dates >= 3 else n_dates

    assignments: dict[str, str] = {}
    for index, date in enumerate(ordered):
        if index < train_end:
            split = "train"
        elif index < min(n_dates, train_end + gap):
            split = "blocked_purge_embargo"
        elif index < val_end:
            split = "val"
        elif index < min(n_dates, val_end + gap):
            split = "blocked_purge_embargo"
        else:
            split = "test"
        assignments[date] = split
    return assignments


def latest_universe_manifest_path(root: Path | str = DEFAULT_UNIVERSE_ROOT) -> Path:
    candidates = sorted(Path(root).glob("*/universe.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No daily OHLCV universe manifest found under {root}")
    return candidates[0]


def load_universe_manifest(path: Path | str | None = None) -> tuple[dict[str, Any], Path, str]:
    manifest_path = Path(path) if path is not None else latest_universe_manifest_path()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return payload, manifest_path, _file_sha(manifest_path)


def _included_universe_symbols(manifest: dict[str, Any], *, max_symbols: int | None = None) -> list[dict[str, Any]]:
    symbols = [row for row in manifest.get("symbols") or [] if row.get("include") is True]
    symbols = sorted(symbols, key=lambda row: str(row.get("table") or ""))
    if max_symbols is not None:
        symbols = symbols[: max(0, int(max_symbols))]
    return symbols


def _read_table_rows(conn: sqlite3.Connection, table: str, *, max_rows_per_symbol: int | None = None) -> list[dict[str, Any]]:
    qt = _quote_ident(table)
    if max_rows_per_symbol is None:
        query = f"SELECT * FROM {qt} ORDER BY date ASC"
        rows = conn.execute(query).fetchall()
    else:
        limit = max(0, int(max_rows_per_symbol))
        query = f"SELECT * FROM (SELECT * FROM {qt} ORDER BY date DESC LIMIT ?) ORDER BY date ASC"
        rows = conn.execute(query, (limit,)).fetchall()
    return [dict(row) for row in rows]


def _build_symbol_panels(
    rows: list[dict[str, Any]],
    *,
    table: str,
    code: str,
    horizon_days: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    feature_rows: list[dict[str, Any]] = []
    label_rows: list[dict[str, Any]] = []
    returns: list[float | None] = []
    volumes: list[float | None] = []

    for index, row in enumerate(rows):
        previous = rows[index - 1] if index > 0 else None
        close = _safe_float(row.get("close"))
        prev_close = _safe_float(previous.get("close")) if previous is not None else None
        ret_1d = _pct_change(close, prev_close)
        returns.append(ret_1d)
        volume = _safe_float(row.get("volume"))
        volumes.append(volume)
        window_returns = [value for value in returns[max(0, index - 4) : index + 1] if value is not None]
        window_volumes = [value for value in volumes[max(0, index - 4) : index + 1] if value is not None]
        close_5 = _safe_float(rows[index - 5].get("close")) if index >= 5 else None
        return_5d = _pct_change(close, close_5)
        vol_5d = _std(window_returns)
        mean_volume_5d = _mean(window_volumes)
        volume_ratio_5d = (volume / mean_volume_5d) if volume is not None and mean_volume_5d not in {None, 0} else None
        hl_range = None
        high = _safe_float(row.get("high"))
        low = _safe_float(row.get("low"))
        if high is not None and low is not None and close not in {None, 0}:
            hl_range = (high - low) / close
        gap_from_prev_close = _pct_change(row.get("open"), prev_close)
        feature_rows.append(
            {
                "date": str(row.get("date")),
                "table": table,
                "code": code,
                "return_1d": ret_1d,
                "return_5d": return_5d,
                "volatility_5d": vol_5d,
                "volume_ratio_5d": volume_ratio_5d,
                "hl_range": hl_range,
                "gap_from_prev_close": gap_from_prev_close,
                "foreign_holding_ratio": _safe_float(row.get("외국인현보유비율")),
                "institutional_net_buy": _safe_float(row.get("기관순매수")),
            }
        )

        future = rows[index + horizon_days] if index + horizon_days < len(rows) else None
        future_return = _pct_change(future.get("close"), close) if future is not None else None
        label_rows.append(
            {
                "date": str(row.get("date")),
                "table": table,
                "code": code,
                "future_return_1d": future_return,
                "future_direction_1d": None if future_return is None else int(future_return > 0),
                "future_rank_pct_1d": None,
            }
        )
    return feature_rows, label_rows


def _add_cross_sectional_label_ranks(label_rows: list[dict[str, Any]]) -> None:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in label_rows:
        if row.get("future_return_1d") is not None:
            by_date[str(row["date"])].append(row)
    for rows in by_date.values():
        ordered = sorted(rows, key=lambda row: float(row["future_return_1d"]))
        denom = max(1, len(ordered) - 1)
        for index, row in enumerate(ordered):
            row["future_rank_pct_1d"] = 1.0 if len(ordered) == 1 else index / denom


def _build_candidate_panel(feature_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidate_rows: list[dict[str, Any]] = []
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in feature_rows:
        vol = _safe_float(row.get("volatility_5d"))
        momentum = _safe_float(row.get("return_5d"))
        score = None if momentum is None else momentum / max(abs(vol or 0.0), 1e-9)
        candidate = {
            "date": row["date"],
            "table": row["table"],
            "code": row["code"],
            "candidate_score_causal_momentum": score,
            "candidate_rank_within_date": None,
            "label_join_key": f'{row["date"]}|{row["table"]}',
        }
        candidate_rows.append(candidate)
        if score is not None:
            by_date[str(row["date"])].append(candidate)
    for rows in by_date.values():
        ordered = sorted(rows, key=lambda row: float(row["candidate_score_causal_momentum"]), reverse=True)
        denom = max(1, len(ordered) - 1)
        for index, row in enumerate(ordered):
            row["candidate_rank_within_date"] = 1.0 if len(ordered) == 1 else 1.0 - (index / denom)
    return candidate_rows


def _apply_splits_and_blocks(
    feature_rows: list[dict[str, Any]],
    label_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    *,
    split_by_date: dict[str, str],
    blocked_dates_by_table: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    labels_by_key = {(row["date"], row["table"]): row for row in label_rows}
    candidates_by_key = {(row["date"], row["table"]): row for row in candidate_rows}
    assignments: list[dict[str, Any]] = []
    for row in feature_rows:
        key = (row["date"], row["table"])
        split = split_by_date.get(str(row["date"]), "blocked_out_of_range")
        block_reason = None
        blocked_payload = blocked_dates_by_table.get(row["table"], {}).get(row["date"])
        if blocked_payload is not None:
            split = "blocked_material_unknown_adjustment"
            block_reason = str(blocked_payload.get("reason") or "SPLIT_LIKE_DISCONTINUITY_UNKNOWN_ADJUSTMENT").upper()
        label = labels_by_key.get(key, {})
        if label.get("future_return_1d") is None and split in {"train", "val", "test"}:
            split = "blocked_missing_future_label"
            block_reason = "MISSING_FUTURE_LABEL"
        eligible = split in {"train", "val", "test"} and block_reason is None
        assignment = {
            "date": row["date"],
            "table": row["table"],
            "code": row["code"],
            "split": split,
            "eligible_for_training": eligible,
            "block_reason": block_reason,
        }
        assignments.append(assignment)
        row["split"] = split
        row["eligible_for_training"] = eligible
        row["block_reason"] = block_reason
        if label:
            label["split"] = split
            label["eligible_for_training"] = eligible
            label["block_reason"] = block_reason
        candidate = candidates_by_key.get(key)
        if candidate is not None:
            candidate["split"] = split
            candidate["eligible_for_training"] = eligible
            candidate["block_reason"] = block_reason
    return assignments


def _normalization_stats(feature_rows: list[dict[str, Any]], feature_columns: list[str]) -> dict[str, Any]:
    train_rows = [row for row in feature_rows if row.get("split") == "train" and row.get("eligible_for_training")]
    features: dict[str, dict[str, Any]] = {}
    for column in feature_columns:
        values = [_safe_float(row.get(column)) for row in train_rows]
        values = [value for value in values if value is not None]
        mean = _mean(values)
        std = _std(values)
        features[column] = {
            "mean": mean,
            "std": 1.0 if std in {None, 0} else std,
            "raw_std": std,
            "count": len(values),
            "fit_split": "train",
            "status": "constant_or_missing" if std in {None, 0} else "ok",
        }
    return {
        "schema_version": DATASET_SCHEMA_VERSION,
        "fit_split": "train",
        "fit_row_count": len(train_rows),
        "feature_columns": feature_columns,
        "features": features,
    }


def _split_summary(assignments: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    split_dates: dict[str, set[str]] = defaultdict(set)
    ordered_dates = sorted({str(row["date"]) for row in assignments})
    date_index = {date: index for index, date in enumerate(ordered_dates)}
    for row in assignments:
        split = str(row["split"])
        counts[split] += 1
        split_dates[split].add(str(row["date"]))

    date_ranges: dict[str, dict[str, Any]] = {}
    for split, dates in split_dates.items():
        ordered = sorted(dates, key=lambda date: date_index[date])
        intervals: list[dict[str, str]] = []
        start = end = None
        previous_index: int | None = None
        for date in ordered:
            index = date_index[date]
            if start is None:
                start = end = date
            elif previous_index is not None and index == previous_index + 1:
                end = date
            else:
                intervals.append({"start": str(start), "end": str(end)})
                start = end = date
            previous_index = index
        if start is not None:
            intervals.append({"start": str(start), "end": str(end)})
        if split in {"train", "val", "test"} and len(intervals) == 1:
            date_ranges[split] = {"start": intervals[0]["start"], "end": intervals[0]["end"], "intervals": intervals}
        else:
            date_ranges[split] = {"start": None, "end": None, "intervals": intervals}
    return {"row_counts": dict(counts), "date_ranges": date_ranges}
def _eligible_split_chronology(assignments: list[dict[str, Any]]) -> dict[str, Any]:
    split_dates = {
        split: sorted({str(row["date"]) for row in assignments if row.get("split") == split})
        for split in ("train", "val", "test")
    }
    missing = [split for split, dates in split_dates.items() if not dates]
    ordered = not missing
    if ordered:
        ordered = max(split_dates["train"]) < min(split_dates["val"]) < max(split_dates["val"]) < min(split_dates["test"])
    return {
        "status": "PASS" if ordered else "BLOCK",
        "missing_splits": missing,
        "train_end": max(split_dates["train"]) if split_dates["train"] else None,
        "val_start": min(split_dates["val"]) if split_dates["val"] else None,
        "val_end": max(split_dates["val"]) if split_dates["val"] else None,
        "test_start": min(split_dates["test"]) if split_dates["test"] else None,
    }


def build_daily_ohlcv_dataset(
    *,
    daily_db_path: Path | str = DEFAULT_DAILY_DB_PATH,
    universe_manifest_path: Path | str | None = None,
    max_symbols: int | None = None,
    max_rows_per_symbol: int | None = None,
    horizon_days: int = 1,
    train_fraction: float = 0.6,
    val_fraction: float = 0.2,
    purge_days: int = 5,
    embargo_days: int = 5,
    quality_table_limit: int | None = None,
) -> dict[str, Any]:
    """Build causal daily feature/label panels from a read-only DB and universe manifest."""

    if horizon_days < 1:
        raise ValueError("horizon_days must be >= 1")
    feature_columns = list(DEFAULT_FEATURE_COLUMNS)
    label_columns = list(DEFAULT_LABEL_COLUMNS)
    leakage_report = validate_no_feature_leakage(feature_columns, label_columns)
    universe, universe_path, universe_file_sha = load_universe_manifest(universe_manifest_path)
    included_symbols = _included_universe_symbols(universe, max_symbols=max_symbols)

    all_feature_rows: list[dict[str, Any]] = []
    all_label_rows: list[dict[str, Any]] = []
    blocked_windows: list[dict[str, Any]] = []
    blocked_dates_by_table: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    quality_window_dates_by_table: dict[str, list[str]] = defaultdict(list)
    missing_tables: list[str] = []
    schema_blocked_tables: list[str] = []

    with connect_readonly(daily_db_path) as conn:
        table_names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        quality_limit = len(included_symbols) if quality_table_limit is None else min(len(included_symbols), max(0, int(quality_table_limit)))
        for index, symbol in enumerate(included_symbols):
            table = validate_daily_table_name(str(symbol.get("table")))
            code = str(symbol.get("code") or table[1:]).zfill(6)
            if table not in table_names:
                missing_tables.append(table)
                continue
            if index < quality_limit:
                quality = analyze_table_quality(conn, table, discontinuity_limit=200)
                for window in quality.get("material_unknown_adjustment_windows") or []:
                    blocked = {
                        "table": table,
                        "code": code,
                        "date": str(window.get("date")),
                        "previous_date": str(window.get("previous_date")),
                        "reason": window.get("reason") or "split_like_price_jump_with_unknown_adjustment_basis",
                        "open_to_previous_close_ratio": window.get("open_to_previous_close_ratio"),
                        "close_to_previous_close_ratio": window.get("close_to_previous_close_ratio"),
                    }
                    blocked_windows.append(blocked)
                    quality_window_dates_by_table[table].append(blocked["date"])
                    blocked_dates_by_table[table][blocked["date"]] = blocked
                    blocked_dates_by_table[table][blocked["previous_date"]] = blocked
                if quality.get("quality_status") == "BLOCKED_SCHEMA":
                    schema_blocked_tables.append(table)
                    continue
            rows = _read_table_rows(conn, table, max_rows_per_symbol=max_rows_per_symbol)
            if not rows:
                continue
            if table in quality_window_dates_by_table:
                dates = [str(row.get("date")) for row in rows]
                date_to_index = {date: row_index for row_index, date in enumerate(dates)}
                for window_date in quality_window_dates_by_table[table]:
                    window_index = date_to_index.get(window_date)
                    if window_index is None:
                        continue
                    for row_index in range(max(0, window_index - int(horizon_days)), window_index + 1):
                        expanded_date = dates[row_index]
                        existing = blocked_dates_by_table[table].get(window_date, {})
                        blocked_dates_by_table[table].setdefault(
                            expanded_date,
                            {
                                **existing,
                                "date": expanded_date,
                                "window_date": window_date,
                                "reason": "forward_label_window_touches_split_like_discontinuity_unknown_adjustment",
                            },
                        )
            features, labels = _build_symbol_panels(rows, table=table, code=code, horizon_days=horizon_days)
            all_feature_rows.extend(features)
            all_label_rows.extend(labels)

    _add_cross_sectional_label_ranks(all_label_rows)
    candidate_rows = _build_candidate_panel(all_feature_rows)
    all_dates = [row["date"] for row in all_feature_rows]
    split_by_date = assign_chronological_splits(
        all_dates,
        train_fraction=train_fraction,
        val_fraction=val_fraction,
        purge_days=purge_days,
        embargo_days=embargo_days,
    )
    split_assignments = _apply_splits_and_blocks(
        all_feature_rows,
        all_label_rows,
        candidate_rows,
        split_by_date=split_by_date,
        blocked_dates_by_table=blocked_dates_by_table,
    )
    normalization_stats = _normalization_stats(all_feature_rows, feature_columns)
    split_chronology = _eligible_split_chronology(split_assignments)
    leakage_report = {
        **leakage_report,
        "feature_definition_uses_future": {name: FEATURE_DEFINITIONS[name]["uses_future"] for name in feature_columns},
        "normalization_fit_split": "train",
        "split_chronology_status": split_chronology["status"],
        "material_unknown_adjustment_window_policy": "exclude_from_train_val_test_and_record_blocked_windows",
        "split_chronology": split_chronology,
    }
    split_summary = _split_summary(split_assignments)
    eligible_rows = sum(1 for row in split_assignments if row.get("eligible_for_training"))
    bounded_preview = max_symbols is not None or max_rows_per_symbol is not None
    upstream_blockers = _upstream_gate_blockers(universe)
    manifest = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "guardrail": "Research-only daily OHLCV dataset; no profit guarantee, no live/broker/orders, no model readiness claim.",
        "strategy_label": "daily_supervised_or_rl_research_dataset",
        "daily_db_path": str(Path(daily_db_path)),
        "price_basis": PRICE_BASIS,
        "price_basis_evidence": PRICE_BASIS_EVIDENCE,
        "adjustment_policy": ADJUSTMENT_POLICY,
        "material_unknown_adjustment_window_policy": "exclude_from_train_val_test_and_record_blocked_windows",
        "universe_manifest_path": str(universe_path),
        "universe_manifest_sha": universe.get("manifest_sha") or universe_file_sha,
        "universe_file_sha256": universe_file_sha,
        "price_basis_status": PRICE_BASIS_STATUS,
        "decision_grade_return_status": DECISION_GRADE_RETURN_STATUS,
        "universe_verdict": universe.get("verdict"),
        "universe_review_status": universe.get("universe_review_status") or universe.get("review_status"),
        "official_metadata_status": universe.get("official_metadata_status"),
        "official_metadata_coverage_status": universe.get("official_metadata_coverage_status"),
        "universe_certification_status": universe.get("universe_certification_status"),
        "feature_columns": feature_columns,
        "label_columns": label_columns,
        "feature_definitions": FEATURE_DEFINITIONS,
        "label_definitions": LABEL_DEFINITIONS,
        "horizon_days": horizon_days,
        "split_policy": {
            "method": "chronological_train_val_test_with_purge_embargo",
            "train_fraction": train_fraction,
            "val_fraction": val_fraction,
            "test_fraction": 1.0 - train_fraction - val_fraction,
            "purge_days": int(purge_days),
            "embargo_days": int(embargo_days),
        },
        "split_summary": split_summary,
        "normalization_policy": "fit_train_only_apply_to_val_test_later",
        "cost_assumption_round_trip_bp": 23,
        "artifact_scope": "BOUNDED_PREVIEW" if bounded_preview else "FULL_REQUESTED_UNIVERSE",
        "source_counts": {
            "universe_symbols_total": len(universe.get("symbols") or []),
            "included_symbols_total": sum(1 for row in universe.get("symbols") or [] if row.get("include") is True),
            "included_symbols_used": len(included_symbols),
            "max_symbols": max_symbols,
            "max_rows_per_symbol": max_rows_per_symbol,
            "quality_scanned_symbols": quality_limit,
            "quality_scan_complete_for_used_symbols": quality_limit == len(included_symbols),
            "missing_tables": len(missing_tables),
            "schema_blocked_tables": len(schema_blocked_tables),
        },
        "row_counts": {
            "feature_rows": len(all_feature_rows),
            "label_rows": len(all_label_rows),
            "rl_candidate_rows": len(candidate_rows),
            "split_assignment_rows": len(split_assignments),
            "eligible_rows": eligible_rows,
            "blocked_windows": len(blocked_windows),
        },
        "missing_tables": missing_tables[:100],
        "schema_blocked_tables": schema_blocked_tables[:100],
        "leakage_status": leakage_report["status"],
        "split_chronology_status": split_chronology["status"],
        "upstream_gate_blockers": upstream_blockers,
        "dataset_required_evidence": list(DATASET_REQUIRED_EVIDENCE),
        "dataset_allowed_uses": list(DATASET_ALLOWED_USES_WITH_UPSTREAM_BLOCKERS),
        "dataset_blocked_uses": list(DATASET_BLOCKED_USES_WITH_UPSTREAM_BLOCKERS),
        "dataset_user_guidance": [dict(row) for row in DATASET_USER_GUIDANCE],
        "decision_grade_status": (
            "BLOCKED_BY_UPSTREAM_D0_D1_GUARDRAILS"
            if upstream_blockers
            else "D2_RESEARCH_DATASET_VALIDATED"
        ),
        "model_readiness": (
            "DATASET_RESEARCH_PREVIEW_BLOCKED_BY_UPSTREAM_GUARDRAILS"
            if upstream_blockers
            else (
                "DATASET_RESEARCH_READY_FOR_BASELINE_ONLY"
                if leakage_report["status"] == "PASS" and split_chronology["status"] == "PASS"
                else "BLOCKED_DATASET_VALIDATION"
            )
        ),
    }
    manifest["manifest_sha"] = _sha_json(
        {
            "schema_version": manifest["schema_version"],
            "generated_at": manifest["generated_at"],
            "universe_manifest_sha": manifest["universe_manifest_sha"],
            "feature_columns": feature_columns,
            "label_columns": label_columns,
            "row_counts": manifest["row_counts"],
            "split_policy": manifest["split_policy"],
            "leakage_status": manifest["leakage_status"],
            "split_chronology_status": manifest["split_chronology_status"],
            "candidate_panel_columns": list(candidate_rows[0].keys()) if candidate_rows else [],
        }
    )
    return {
        "manifest": manifest,
        "feature_panel": all_feature_rows,
        "label_panel": all_label_rows,
        "rl_candidate_panel": candidate_rows,
        "split_assignments": split_assignments,
        "normalization_stats": normalization_stats,
        "leakage_report": leakage_report,
        "blocked_windows": blocked_windows,
    }


def _write_rows_csv(path: Path, rows: list[dict[str, Any]], *, fallback_fields: list[str]) -> None:
    if rows:
        fields = sorted({key for row in rows for key in row.keys()})
    else:
        fields = fallback_fields
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_dataset_artifacts(
    dataset: dict[str, Any],
    *,
    artifact_root: Path | str | None = None,
    run_id: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    root = Path(artifact_root or DEFAULT_DATASET_ROOT).resolve()
    default_root = DEFAULT_DATASET_ROOT.resolve()
    try:
        root.relative_to(default_root)
    except ValueError:
        if root != default_root:
            raise ValueError("Daily OHLCV dataset artifacts must stay under webui/rl_runs/daily_ohlcv_dataset")
    rid = _validate_run_id(run_id or f"dataset_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    out_dir = (root / rid).resolve()
    try:
        out_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("run_id escapes daily OHLCV dataset artifact root") from exc
    if out_dir.exists() and any(out_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"Dataset artifact run_id already exists: {rid}")
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = out_dir / "dataset_manifest.json"
    feature_path = out_dir / "feature_panel.csv"
    label_path = out_dir / "label_panel.csv"
    candidate_path = out_dir / "rl_candidate_panel.csv"
    split_path = out_dir / "split_assignments.csv"
    normalization_path = out_dir / "normalization_stats.json"
    leakage_path = out_dir / "leakage_report.json"
    blocked_path = out_dir / "blocked_windows.csv"

    manifest = dict(dataset["manifest"])
    manifest["run_id"] = rid
    manifest["artifact_dir"] = str(out_dir)
    manifest["artifacts"] = {
        "dataset_manifest": str(manifest_path),
        "feature_panel": str(feature_path),
        "label_panel": str(label_path),
        "rl_candidate_panel": str(candidate_path),
        "split_assignments": str(split_path),
        "normalization_stats": str(normalization_path),
        "leakage_report": str(leakage_path),
        "blocked_windows": str(blocked_path),
    }
    manifest["manifest_sha"] = _sha_json(
        {
            "run_id": rid,
            "feature_columns": manifest.get("feature_columns"),
            "label_columns": manifest.get("label_columns"),
            "row_counts": manifest.get("row_counts"),
            "split_policy": manifest.get("split_policy"),
            "universe_manifest_sha": manifest.get("universe_manifest_sha"),
            "split_chronology_status": manifest.get("split_chronology_status"),
            "candidate_panel_columns": list((dataset.get("rl_candidate_panel") or [{}])[0].keys()),
        }
    )

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    normalization_path.write_text(json.dumps(dataset["normalization_stats"], ensure_ascii=False, indent=2), encoding="utf-8")
    leakage_path.write_text(json.dumps(dataset["leakage_report"], ensure_ascii=False, indent=2), encoding="utf-8")
    _write_rows_csv(feature_path, dataset["feature_panel"], fallback_fields=["date", "table", "code", *DEFAULT_FEATURE_COLUMNS])
    _write_rows_csv(label_path, dataset["label_panel"], fallback_fields=["date", "table", "code", *DEFAULT_LABEL_COLUMNS])
    _write_rows_csv(
        candidate_path,
        dataset["rl_candidate_panel"],
        fallback_fields=["date", "table", "code", "candidate_score_causal_momentum", "candidate_rank_within_date", "label_join_key"],
    )
    _write_rows_csv(
        split_path,
        dataset["split_assignments"],
        fallback_fields=["date", "table", "code", "split", "eligible_for_training", "block_reason"],
    )
    _write_rows_csv(
        blocked_path,
        dataset["blocked_windows"],
        fallback_fields=["table", "code", "previous_date", "date", "reason"],
    )
    return {
        "run_id": rid,
        "artifact_dir": str(out_dir),
        "dataset_manifest_path": str(manifest_path),
        "feature_panel_path": str(feature_path),
        "label_panel_path": str(label_path),
        "rl_candidate_panel_path": str(candidate_path),
        "split_assignments_path": str(split_path),
        "normalization_stats_path": str(normalization_path),
        "leakage_report_path": str(leakage_path),
        "blocked_windows_path": str(blocked_path),
        "manifest_sha": manifest["manifest_sha"],
    }


def build_and_write_daily_ohlcv_dataset(
    *,
    run_id: str | None = None,
    artifact_root: Path | str | None = None,
    overwrite: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    dataset = build_daily_ohlcv_dataset(**kwargs)
    written = write_dataset_artifacts(dataset, artifact_root=artifact_root, run_id=run_id, overwrite=overwrite)
    return {"dataset": dataset, "written": written}


__all__ = [
    "DATASET_SCHEMA_VERSION",
    "DEFAULT_DATASET_ROOT",
    "DEFAULT_FEATURE_COLUMNS",
    "DEFAULT_LABEL_COLUMNS",
    "DATASET_REQUIRED_EVIDENCE",
    "DATASET_ALLOWED_USES_WITH_UPSTREAM_BLOCKERS",
    "DATASET_BLOCKED_USES_WITH_UPSTREAM_BLOCKERS",
    "DATASET_USER_GUIDANCE",
    "FEATURE_DEFINITIONS",
    "LABEL_DEFINITIONS",
    "assign_chronological_splits",
    "build_and_write_daily_ohlcv_dataset",
    "build_daily_ohlcv_dataset",
    "latest_universe_manifest_path",
    "load_universe_manifest",
    "validate_no_feature_leakage",
    "write_dataset_artifacts",
]
