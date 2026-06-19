"""Daily OHLCV universe classification and manifest helpers.

This module creates a conservative research universe from local daily OHLCV table
names plus the read-only STOM ``stockinfo`` metadata.  It intentionally excludes
products and uncertain symbols by default; inclusion is heuristic WATCH evidence,
not a tradable/live-ready claim.
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
from typing import Any

from .daily_ohlcv_db import (
    DEFAULT_DAILY_DB_PATH,
    REPO_ROOT,
    list_daily_tables,
    validate_daily_table_name,
)

DEFAULT_STOCKINFO_DB_PATH = REPO_ROOT / "_database" / "stock_tick_back.db"
DEFAULT_UNIVERSE_ROOT = REPO_ROOT / "webui" / "rl_runs" / "daily_ohlcv_universe"
DEFAULT_OFFICIAL_METADATA_PATH = REPO_ROOT / "_database" / "krx_listed_products.csv"
OFFICIAL_METADATA_REQUIRED_COLUMNS = ("code", "name", "market", "instrument_type")
OFFICIAL_COMMON_TYPES = {"common_equity", "common", "stock", "ordinary_share"}
OFFICIAL_EXCLUDED_TYPES = {
    "preferred": "OFFICIAL_PREFERRED_SHARE_EXCLUDED",
    "preferred_stock": "OFFICIAL_PREFERRED_SHARE_EXCLUDED",
    "etf": "OFFICIAL_ETF_ETN_FUND_EXCLUDED",
    "etn": "OFFICIAL_ETF_ETN_FUND_EXCLUDED",
    "fund": "OFFICIAL_ETF_ETN_FUND_EXCLUDED",
    "fund_or_etf": "OFFICIAL_ETF_ETN_FUND_EXCLUDED",
    "spac": "OFFICIAL_SPAC_EXCLUDED",
    "reit": "OFFICIAL_REIT_EXCLUDED",
}
UNIVERSE_REQUIRED_EVIDENCE = (
    "official_or_manual_krx_csv_with_code_name_market_instrument_type",
    "six_character_string_codes_preserving_leading_zeros",
    "kospi_kosdaq_common_equity_instrument_type_review",
    "quarantine_artifact_for_unmatched_or_excluded_symbols",
    "dated_manifest_with_metadata_sha_and_review_status",
)
UNIVERSE_ALLOWED_USES_WHEN_WATCH = (
    "research_universe_preview",
    "exclusion_reason_review",
    "quarantine_backlog_triage",
    "dashboard_evidence_navigation",
)
UNIVERSE_ALLOWED_USES_WHEN_VERIFIED = (
    "research_universe_preview",
    "dataset_candidate_filtering_after_d0_price_basis_check",
    "baseline_research_input_after_split_and_cost_controls",
    "dashboard_evidence_navigation",
)
UNIVERSE_BLOCKED_USES_WHEN_WATCH = (
    "model_build_or_candidate_promotion",
    "paper_forward_or_live_readiness_claims",
    "official_common_equity_certification_claims",
)
UNIVERSE_BLOCKED_USES_WHEN_VERIFIED = (
    "live_broker_order_readiness_claims",
    "profitability_claims",
)
UNIVERSE_USER_GUIDANCE = (
    {
        "section": "D1 summary",
        "meaning": "WATCH_HEURISTIC_UNIVERSE means stockinfo/name-prefix rules are only a research preview.",
        "action": "Use inclusion/exclusion counts and quarantine artifacts to review the universe, not to promote a model.",
    },
    {
        "section": "Official/manual CSV",
        "meaning": "D1 can clear only when the KRX/manual CSV contract covers every daily table with leading-zero codes preserved.",
        "action": "Provide code,name,market,instrument_type[,source] evidence outside the local DB and rerun the manifest.",
    },
    {
        "section": "Blocked promotion",
        "meaning": "Missing or partial official/manual evidence blocks model_build_allowed regardless of favorable D3/D5 artifacts.",
        "action": "Keep D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED visible until coverage is complete.",
    },
)


PRODUCT_PREFIXES = (
    "KODEX",
    "TIGER",
    "RISE",
    "KBSTAR",
    "ACE",
    "SOL",
    "HANARO",
    "ARIRANG",
    "KOSEF",
    "TIMEFOLIO",
    "TREX",
    "FOCUS",
    "마이다스",
)
PRODUCT_TOKENS = (
    " ETF",
    " ETN",
    "ETF",
    "ETN",
    "인버스",
    "레버리지",
    "선물",
    "채권",
    "국고채",
    "회사채",
    "커버드콜",
    "액티브",
    "나스닥",
    "S&P",
    "MSCI",
    "TOP10",
    "TOP5",
)
PREFERRED_RE = re.compile(r"(?:\d+우[BC]?|우[BC]?)$")


@dataclass(frozen=True)
class StockInfoRecord:
    code: str
    name: str
    kosdaq: int | None
@dataclass(frozen=True)
class OfficialMetadataRecord:
    code: str
    name: str
    market: str
    instrument_type: str
    source: str




def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _metadata_sha(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _connect_stockinfo_readonly(path: Path | str = DEFAULT_STOCKINFO_DB_PATH) -> sqlite3.Connection:
    db_path = Path(path)
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def load_stockinfo(stockinfo_db_path: Path | str = DEFAULT_STOCKINFO_DB_PATH) -> dict[str, StockInfoRecord]:
    with _connect_stockinfo_readonly(stockinfo_db_path) as conn:
        rows = conn.execute('SELECT "index", "종목명", "코스닥" FROM stockinfo').fetchall()
    records: dict[str, StockInfoRecord] = {}
    for row in rows:
        code = str(row["index"]).zfill(6)
        name = "" if row["종목명"] is None else str(row["종목명"])
        kosdaq_raw = row["코스닥"]
        try:
            kosdaq = int(kosdaq_raw) if kosdaq_raw is not None else None
        except (TypeError, ValueError):
            kosdaq = None
        records[code] = StockInfoRecord(code=code, name=name, kosdaq=kosdaq)
    return records
def load_official_metadata_csv(path: Path | str) -> dict[str, OfficialMetadataRecord]:
    """Load a KRX/manual listed-product CSV contract without mutating source DBs."""

    metadata_path = Path(path)
    if not metadata_path.exists():
        raise FileNotFoundError(metadata_path)
    records: dict[str, OfficialMetadataRecord] = {}
    with metadata_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = [field for field in OFFICIAL_METADATA_REQUIRED_COLUMNS if field not in fieldnames]
        if missing:
            raise ValueError(f"official metadata missing required columns: {missing}")
        for row in reader:
            raw_code = str(row.get("code", "")).strip()
            if not raw_code:
                continue
            if not re.fullmatch(r"[0-9A-Za-z]{6}", raw_code):
                raise ValueError(f"official metadata code must be a 6-character string: {raw_code!r}")
            code = raw_code.zfill(6) if raw_code.isdigit() else raw_code
            market = str(row.get("market", "")).strip().upper()
            instrument_type = str(row.get("instrument_type", "")).strip().lower()
            name = str(row.get("name", "")).strip()
            if not name:
                raise ValueError(f"official metadata name is required for {code}")
            if market not in {"KOSPI", "KOSDAQ", "KONEX", "UNKNOWN", "PRODUCT_Q"}:
                raise ValueError(f"official metadata market is unsupported for {code}: {market!r}")
            if not instrument_type:
                raise ValueError(f"official metadata instrument_type is required for {code}")
            if code in records:
                raise ValueError(f"official metadata duplicate code: {code}")
            records[code] = OfficialMetadataRecord(
                code=code,
                name=name,
                market=market,
                instrument_type=instrument_type,
                source=str(row.get("source", "official_or_manual_csv")).strip() or "official_or_manual_csv",
            )
    return records


def _universe_review_contract(
    *,
    official_records: dict[str, OfficialMetadataRecord] | None,
    table_count: int,
    official_matched_table_count: int,
) -> dict[str, Any]:
    if official_records is None:
        return {
            "verdict": "WATCH_HEURISTIC_UNIVERSE",
            "review_status": "WATCH_REQUIRES_OFFICIAL_OR_MANUAL_REVIEW",
            "official_metadata_status": "MISSING",
            "official_metadata_coverage_status": "MISSING",
            "universe_certification_status": "BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW",
            "universe_allowed_uses": list(UNIVERSE_ALLOWED_USES_WHEN_WATCH),
            "universe_blocked_uses": list(UNIVERSE_BLOCKED_USES_WHEN_WATCH),
        }
    if table_count > 0 and official_matched_table_count == table_count:
        return {
            "verdict": "OFFICIAL_OR_MANUAL_REVIEWED",
            "review_status": "OFFICIAL_OR_MANUAL_REVIEWED",
            "official_metadata_status": "OFFICIAL_VERIFIED",
            "official_metadata_coverage_status": "COMPLETE",
            "universe_certification_status": "OFFICIAL_OR_MANUAL_REVIEWED",
            "universe_allowed_uses": list(UNIVERSE_ALLOWED_USES_WHEN_VERIFIED),
            "universe_blocked_uses": list(UNIVERSE_BLOCKED_USES_WHEN_VERIFIED),
        }
    return {
        "verdict": "WATCH_HEURISTIC_UNIVERSE",
        "review_status": "WATCH_REQUIRES_OFFICIAL_OR_MANUAL_REVIEW",
        "official_metadata_status": "LOADED",
        "official_metadata_coverage_status": "PARTIAL",
        "universe_certification_status": "BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW",
        "universe_allowed_uses": list(UNIVERSE_ALLOWED_USES_WHEN_WATCH),
        "universe_blocked_uses": list(UNIVERSE_BLOCKED_USES_WHEN_WATCH),
    }


def _official_metadata_summary(path: Path, records: dict[str, OfficialMetadataRecord] | None) -> dict[str, Any]:
    if records is None:
        return {
            "status": "MISSING",
            "path": str(path),
            "available": False,
            "used": False,
            "required_columns": list(OFFICIAL_METADATA_REQUIRED_COLUMNS),
            "review_status": "WATCH_OFFICIAL_METADATA_REQUIRED",
            "ingestion_contract": "CSV columns: code,name,market,instrument_type[,source]; codes remain strings with leading zeros.",
        }
    return {
        "status": "LOADED",
        "path": str(path),
        "available": True,
        "used": True,
        "record_count": len(records),
        "required_columns": list(OFFICIAL_METADATA_REQUIRED_COLUMNS),
        "review_status": "OFFICIAL_OR_MANUAL_METADATA_PRESENT",
        "metadata_sha": _metadata_sha(
            {
                "records": [
                    {
                        "code": row.code,
                        "name": row.name,
                        "market": row.market,
                        "instrument_type": row.instrument_type,
                        "source": row.source,
                    }
                    for row in records.values()
                ]
            }
        ),
    }


def _classify_with_official_metadata(
    table: str,
    record: OfficialMetadataRecord | None,
) -> dict[str, Any] | None:
    code = table[1:]
    prefix = table[0]
    if record is None:
        return None
    normalized_type = record.instrument_type.strip().lower()
    if prefix == "Q":
        include = False
        instrument_type = normalized_type or "q_product"
        exclusion_reason = "Q_PRODUCT_TABLE"
        market = "PRODUCT_Q"
    elif normalized_type in OFFICIAL_COMMON_TYPES and record.market in {"KOSPI", "KOSDAQ"}:
        include = True
        instrument_type = "common_equity"
        exclusion_reason = None
        market = record.market
    else:
        include = False
        instrument_type = normalized_type or "unknown_official_type"
        exclusion_reason = OFFICIAL_EXCLUDED_TYPES.get(normalized_type, "OFFICIAL_NON_COMMON_OR_UNSUPPORTED_MARKET_EXCLUDED")
        market = record.market if record.market in {"KOSPI", "KOSDAQ", "KONEX", "UNKNOWN"} else "UNKNOWN"
    payload = {
        "table": table,
        "code": code,
        "name": record.name,
        "market": market,
        "instrument_type": instrument_type,
        "include": include,
        "exclusion_reason": exclusion_reason,
        "classification_source": "official_metadata_csv",
        "classification_confidence": 1.0,
        "official_metadata_status": "matched",
        "official_metadata_source": record.source,
        "review_status": "official_metadata_reviewed" if include else "official_metadata_excluded",
    }
    payload["metadata_sha"] = _metadata_sha(payload)
    return payload




def _detect_instrument_type(name: str, code: str, prefix: str) -> tuple[str, str | None, float, str]:
    normalized = name.strip()
    upper = normalized.upper()
    if prefix == "Q":
        return "q_product", "Q_PRODUCT_TABLE", 0.99, "table_prefix"
    if not code.isdigit():
        return "unknown_alphanumeric", "ALPHANUMERIC_CODE_UNREVIEWED", 0.8, "table_code"
    if not normalized:
        return "unknown", "METADATA_NAME_MISSING", 0.0, "stockinfo_missing_name"
    if any(upper.startswith(token) for token in PRODUCT_PREFIXES):
        return "fund_or_etf", "ETF_ETN_FUND_NAME_PREFIX", 0.97, "stockinfo_name_prefix"
    if any(token in upper for token in PRODUCT_TOKENS):
        return "fund_or_etf", "ETF_ETN_FUND_NAME_TOKEN", 0.93, "stockinfo_name_token"
    if "스팩" in normalized or "SPAC" in upper:
        return "spac", "SPAC_EXCLUDED", 0.96, "stockinfo_name_token"
    if ("리츠" in normalized and not normalized.startswith("메리츠")) or upper.endswith("REIT"):
        return "reit", "REIT_EXCLUDED", 0.9, "stockinfo_name_token"
    if PREFERRED_RE.search(normalized):
        return "preferred", "PREFERRED_SHARE_EXCLUDED", 0.92, "stockinfo_name_suffix"
    return "common_equity", None, 0.85, "stockinfo_name_market_heuristic"


def classify_daily_table(
    table: str,
    stockinfo: dict[str, StockInfoRecord],
    official_metadata: dict[str, OfficialMetadataRecord] | None = None,
) -> dict[str, Any]:
    table = validate_daily_table_name(table)
    code = table[1:]
    prefix = table[0]
    official_payload = _classify_with_official_metadata(table, official_metadata.get(code) if official_metadata is not None else None)
    if official_payload is not None:
        return official_payload
    if prefix == "Q":
        record = stockinfo.get(code)
        payload = {
            "table": table,
            "code": code,
            "name": record.name if record is not None else None,
            "market": "PRODUCT_Q",
            "stockinfo_kosdaq": record.kosdaq if record is not None else None,
            "instrument_type": "q_product",
            "include": False,
            "exclusion_reason": "Q_PRODUCT_TABLE",
            "classification_source": "table_prefix",
            "classification_confidence": 0.99,
            "official_metadata_status": "not_used",
            "review_status": "excluded_by_default",
        }
        payload["metadata_sha"] = _metadata_sha(payload)
        return payload
    if not code.isdigit():
        payload = {
            "table": table,
            "code": code,
            "name": None,
            "market": "UNKNOWN",
            "instrument_type": "unknown_alphanumeric",
            "include": False,
            "exclusion_reason": "ALPHANUMERIC_CODE_UNREVIEWED",
            "classification_source": "table_code",
            "classification_confidence": 0.8,
            "official_metadata_status": "not_used",
            "review_status": "excluded_by_default",
        }
        payload["metadata_sha"] = _metadata_sha(payload)
        return payload
    record = stockinfo.get(code)
    if record is None:
        payload = {
            "table": table,
            "code": code,
            "name": None,
            "market": "UNKNOWN",
            "instrument_type": "unknown_unmatched",
            "include": False,
            "exclusion_reason": "METADATA_UNMATCHED",
            "classification_source": "daily_table_without_stockinfo_match",
            "classification_confidence": 0.0,
            "official_metadata_status": "not_used",
            "review_status": "quarantined_unmatched",
        }
        payload["metadata_sha"] = _metadata_sha(payload)
        return payload
    if record.kosdaq not in {0, 1}:
        payload = {
            "table": table,
            "code": code,
            "name": record.name,
            "market": "UNKNOWN",
            "stockinfo_kosdaq": record.kosdaq,
            "instrument_type": "unknown_market",
            "include": False,
            "exclusion_reason": "UNKNOWN_MARKET_METADATA",
            "classification_source": "stockinfo_market_missing_or_invalid",
            "classification_confidence": 0.0,
            "official_metadata_status": "not_used",
            "review_status": "quarantined_unknown_market",
        }
        payload["metadata_sha"] = _metadata_sha(payload)
        return payload

    instrument_type, exclusion_reason, confidence, source = _detect_instrument_type(record.name, code, prefix)
    include = instrument_type == "common_equity"
    market = "KOSDAQ" if record.kosdaq == 1 else "KOSPI"
    review_status = "heuristic_watch" if include else "excluded_by_default"
    if include:
        exclusion_reason = None
    payload = {
        "table": table,
        "code": code,
        "name": record.name,
        "market": market,
        "stockinfo_kosdaq": record.kosdaq,
        "instrument_type": instrument_type,
        "include": include,
        "exclusion_reason": exclusion_reason,
        "classification_source": source,
        "classification_confidence": confidence,
        "review_status": review_status,
        "official_metadata_status": "not_available",
    }
    payload["metadata_sha"] = _metadata_sha(payload)
    return payload


def build_universe_manifest(
    daily_db_path: Path | str = DEFAULT_DAILY_DB_PATH,
    stockinfo_db_path: Path | str = DEFAULT_STOCKINFO_DB_PATH,
    *,
    official_metadata_path: Path | str | None = DEFAULT_OFFICIAL_METADATA_PATH,
    table_limit: int | None = None,
) -> dict[str, Any]:
    tables = list_daily_tables(daily_db_path)
    if table_limit is not None:
        safe_limit = max(0, min(int(table_limit), len(tables)))
        tables = tables[:safe_limit]
    stockinfo = load_stockinfo(stockinfo_db_path)
    official_path = Path(official_metadata_path) if official_metadata_path is not None else DEFAULT_OFFICIAL_METADATA_PATH
    official_records: dict[str, OfficialMetadataRecord] | None = None
    if official_metadata_path is not None and official_path.exists():
        official_records = load_official_metadata_csv(official_path)
    symbols = [classify_daily_table(table, stockinfo, official_records) for table in tables]
    include_count = sum(1 for row in symbols if row["include"])
    exclusions = [row for row in symbols if not row["include"]]
    by_type = Counter(row["instrument_type"] for row in symbols)
    by_market = Counter(row["market"] for row in symbols)
    by_reason = Counter(row["exclusion_reason"] or "INCLUDED" for row in symbols)
    stockinfo_matched_table_count = sum(1 for table in tables if table[1:] in stockinfo)
    stockinfo_unmatched_table_count = len(tables) - stockinfo_matched_table_count
    official_summary = _official_metadata_summary(official_path, official_records)
    official_matched_table_count = sum(1 for row in symbols if row.get("official_metadata_status") == "matched")
    official_unmatched_table_count = len(tables) - official_matched_table_count if official_records is not None else len(tables)
    official_unmatched_quarantine_count = sum(
        1
        for row in symbols
        if official_records is not None
        and row.get("official_metadata_status") != "matched"
        and not row["include"]
    )
    universe_review = _universe_review_contract(
        official_records=official_records,
        table_count=len(tables),
        official_matched_table_count=official_matched_table_count,
    )
    official_summary["status"] = universe_review["official_metadata_status"]
    official_summary["coverage_status"] = universe_review["official_metadata_coverage_status"]
    official_summary["review_status"] = (
        "OFFICIAL_OR_MANUAL_REVIEWED"
        if universe_review["official_metadata_coverage_status"] == "COMPLETE"
        else official_summary.get("review_status", "WATCH_OFFICIAL_METADATA_REQUIRED")
    )
    official_summary["certification_status"] = universe_review["universe_certification_status"]
    uncertain_quarantine_reasons = {
        "ALPHANUMERIC_CODE_UNREVIEWED",
        "METADATA_UNMATCHED",
        "UNKNOWN_MARKET_METADATA",
    }
    quarantine_artifact_count = sum(
        1
        for row in symbols
        if not row.get("include")
        and (
            row.get("exclusion_reason") in uncertain_quarantine_reasons
            or str(row.get("review_status", "")).startswith("quarantined")
        )
    )
    manifest = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "daily_db_path": str(Path(daily_db_path)),
        "stockinfo_db_path": str(Path(stockinfo_db_path)),
        "guardrail": "Research-only universe classification; no live/broker/orders, no profit claim. Inclusion is heuristic WATCH until official/audited metadata review.",
        "verdict": universe_review["verdict"],
        "official_metadata": official_summary,
        "official_metadata_status": universe_review["official_metadata_status"],
        "official_metadata_coverage_status": universe_review["official_metadata_coverage_status"],
        "official_metadata_path": str(official_path),
        "official_metadata_required_columns": list(OFFICIAL_METADATA_REQUIRED_COLUMNS),
        "official_metadata_matched_table_count": official_matched_table_count,
        "official_metadata_unmatched_table_count": official_unmatched_table_count,
        "official_metadata_unmatched_quarantine_count": official_unmatched_quarantine_count,
        "review_status": universe_review["review_status"],
        "universe_review_status": universe_review["review_status"],
        "universe_certification_status": universe_review["universe_certification_status"],
        "universe_required_evidence": list(UNIVERSE_REQUIRED_EVIDENCE),
        "universe_allowed_uses": universe_review["universe_allowed_uses"],
        "universe_blocked_uses": universe_review["universe_blocked_uses"],
        "universe_user_guidance": [dict(row) for row in UNIVERSE_USER_GUIDANCE],
        "table_count": len(tables),
        "stockinfo_count": len(stockinfo),
        "stockinfo_matched_table_count": stockinfo_matched_table_count,
        "stockinfo_unmatched_table_count": stockinfo_unmatched_table_count,
        "unmatched_quarantine_count": stockinfo_unmatched_table_count,
        "quarantine_artifact_count": quarantine_artifact_count,
        "include_count": include_count,
        "exclude_count": len(exclusions),
        "unmatched_count": stockinfo_unmatched_table_count,
        "metadata_unmatched_count": by_reason.get("METADATA_UNMATCHED", 0),
        "q_product_count": by_reason.get("Q_PRODUCT_TABLE", 0),
        "counts_by_type": dict(by_type),
        "counts_by_market": dict(by_market),
        "counts_by_exclusion_reason": dict(by_reason),
        "required_fields": [
            "classification_source",
            "classification_confidence",
            "exclusion_reason",
            "metadata_sha",
            "review_status",
            "official_metadata_status",
            "official_metadata_coverage_status",
            "universe_certification_status",
        ],
        "symbols": symbols,
        "exclusions": exclusions,
    }
    manifest["manifest_sha"] = _metadata_sha(
        {
            "schema_version": manifest["schema_version"],
            "symbols": [row["metadata_sha"] for row in symbols],
            "verdict": manifest["verdict"],
        }
    )
    return manifest


def write_universe_artifacts(
    manifest: dict[str, Any],
    *,
    artifact_root: Path | str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    root = Path(artifact_root or DEFAULT_UNIVERSE_ROOT).resolve()
    default_root = DEFAULT_UNIVERSE_ROOT.resolve()
    try:
        root.relative_to(default_root)
    except ValueError:
        if root != default_root:
            raise ValueError("Daily OHLCV universe artifacts must stay under webui/rl_runs/daily_ohlcv_universe")
    rid = run_id or f"universe_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    if not re.match(r"^[0-9A-Za-z_.-]+$", rid) or rid in {".", ".."} or ".." in rid.split("."):
        raise ValueError("run_id contains unsafe characters")
    out_dir = (root / rid).resolve()
    try:
        out_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("run_id escapes daily OHLCV universe artifact root") from exc
    out_dir.mkdir(parents=True, exist_ok=True)

    universe_path = out_dir / "universe.json"
    symbols_path = out_dir / "symbols.csv"
    exclusions_path = out_dir / "exclusions.csv"
    official_audit_path = out_dir / "official_metadata_audit.json"
    quarantine_path = out_dir / "quarantine.csv"
    universe_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    _write_rows_csv(symbols_path, manifest.get("symbols") or [])
    _write_rows_csv(exclusions_path, manifest.get("exclusions") or [])
    uncertain_quarantine_reasons = {
        "ALPHANUMERIC_CODE_UNREVIEWED",
        "METADATA_UNMATCHED",
        "UNKNOWN_MARKET_METADATA",
    }
    _write_rows_csv(quarantine_path, [
        row
        for row in manifest.get("symbols") or []
        if not row.get("include") and (
            row.get("exclusion_reason") in uncertain_quarantine_reasons
            or str(row.get("review_status", "")).startswith("quarantined")
        )
    ])
    official_audit_path.write_text(
        json.dumps(
            {
                "official_metadata": manifest.get("official_metadata"),
                "official_metadata_status": manifest.get("official_metadata_status"),
                "official_metadata_matched_table_count": manifest.get("official_metadata_matched_table_count"),
                "official_metadata_unmatched_table_count": manifest.get("official_metadata_unmatched_table_count"),
                "official_metadata_unmatched_quarantine_count": manifest.get("official_metadata_unmatched_quarantine_count"),
                "official_metadata_coverage_status": manifest.get("official_metadata_coverage_status"),
                "universe_certification_status": manifest.get("universe_certification_status"),
                "universe_required_evidence": manifest.get("universe_required_evidence"),
                "universe_allowed_uses": manifest.get("universe_allowed_uses"),
                "universe_blocked_uses": manifest.get("universe_blocked_uses"),
                "quarantine_artifact_count": manifest.get("quarantine_artifact_count"),
                "verdict": manifest.get("verdict"),
                "review_status": manifest.get("review_status"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "run_id": rid,
        "artifact_dir": str(out_dir),
        "universe_path": str(universe_path),
        "symbols_path": str(symbols_path),
        "exclusions_path": str(exclusions_path),
        "official_metadata_audit_path": str(official_audit_path),
        "quarantine_path": str(quarantine_path),
        "manifest_sha": manifest.get("manifest_sha"),
    }


def _write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if rows:
        fields = sorted({key for row in rows for key in row.keys()})
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    else:
        path.write_text("table,code,name,market,instrument_type,include,exclusion_reason\n", encoding="utf-8")


__all__ = [
    "DEFAULT_STOCKINFO_DB_PATH",
    "DEFAULT_UNIVERSE_ROOT",
    "DEFAULT_OFFICIAL_METADATA_PATH",
    "OFFICIAL_METADATA_REQUIRED_COLUMNS",
    "UNIVERSE_REQUIRED_EVIDENCE",
    "UNIVERSE_ALLOWED_USES_WHEN_WATCH",
    "UNIVERSE_ALLOWED_USES_WHEN_VERIFIED",
    "UNIVERSE_BLOCKED_USES_WHEN_WATCH",
    "UNIVERSE_BLOCKED_USES_WHEN_VERIFIED",
    "UNIVERSE_USER_GUIDANCE",
    "OfficialMetadataRecord",
    "StockInfoRecord",
    "build_universe_manifest",
    "classify_daily_table",
    "load_stockinfo",
    "load_official_metadata_csv",
    "write_universe_artifacts",
]
