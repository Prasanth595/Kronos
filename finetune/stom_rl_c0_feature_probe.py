"""Stage C-0 DB feature feasibility probe (read-only, bounded sampling).

Decides whether the high-signal features the RL export currently drops can be
added to ``export-stom-rl``.  Reuses the existing read-only helpers
(``connect_readonly`` / ``list_stock_tables`` / ``_decode_table_columns``) so it
never performs a full-DB scan: a bounded sample of symbols x their available
sessions x a bounded row read per session is inspected.

Target candidate source columns (Korean, UTF-8 in the STOM tick DB):
  등락율            -> change_rate
  시가총액          -> market_cap
  고저평균대비등락율  -> high_low_mid_change_rate (else computed from 고가/저가/현재가)
  체결강도          -> trade_strength_avg_n (trailing mean; already a source)
  회전율            -> turnover_rate (already canonical)

Coverage rule (plan V10): per existing target column, compute PER-SESSION
non-null coverage % (and non-zero where 0 plausibly means missing).  If a
feature has < 80% non-null coverage in ANY sampled session => "fallback-or-drop".
Features >= 80% everywhere => "add".

Usage:
  py -3.11 finetune/stom_rl_c0_feature_probe.py \
      --db _database/stock_tick_back.db --symbols 8 --sessions-per-symbol 3 \
      --rows-per-session 3000 --out .omx/artifacts/deep_rl/stageC_export/c0_probe.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
FINETUNE_CSV_DIR = PROJECT_ROOT / "finetune_csv"
if str(FINETUNE_CSV_DIR) not in sys.path:
    sys.path.insert(0, str(FINETUNE_CSV_DIR))

from stom_tick_dataset import connect_readonly, list_stock_tables  # noqa: E402
from qlib_stom_pipeline import _decode_table_columns, _sqlite_quote_ident  # noqa: E402

# Candidate source columns to probe (target_feature -> accepted DB column names).
# Names that are ALREADY in STOM_RL_SOURCE_COLUMNS (체결강도, 회전율, 고가/저가/현재가)
# are probed too, so coverage of "already-present" sources is measured on the
# same footing as the NEW columns (등락율 / 시가총액 / 고저평균대비등락율).
PROBE_COLUMNS: Dict[str, List[str]] = {
    "change_rate(등락율)": ["등락율"],
    "market_cap(시가총액)": ["시가총액"],
    "high_low_mid_change_rate(고저평균대비등락율)": ["고저평균대비등락율"],
    "trade_strength(체결강도)": ["체결강도"],
    "turnover_rate(회전율)": ["회전율"],
    # OHLC sources backing the computed high_low_mid fallback:
    "high(고가)": ["고가"],
    "low(저가)": ["저가"],
    "close(현재가)": ["현재가", "종가"],
}

# Columns where a literal 0 plausibly signals "not recorded" (missing) rather
# than a true value, so coverage is reported both as non-null and non-zero.
ZERO_MEANS_MISSING = {
    "market_cap(시가총액)",
    "turnover_rate(회전율)",
    "trade_strength(체결강도)",
}

COVERAGE_THRESHOLD = 0.80


def _sessions_for_table(conn: Any, table: str, ts_col: str, limit: int) -> List[str]:
    """Return distinct YYYYMMDD session dates for a table (bounded)."""
    q = (
        f"SELECT DISTINCT substr(CAST({_sqlite_quote_ident(ts_col)} AS TEXT), 1, 8) AS s "
        f"FROM {_sqlite_quote_ident(table)} ORDER BY s LIMIT {int(limit)}"
    )
    rows = conn.execute(q).fetchall()
    return [str(r[0]) for r in rows if r[0] is not None and str(r[0]).isdigit() and len(str(r[0])) == 8]


def _resolve_ts_col(columns: List[str]) -> Optional[str]:
    for c in ("index", "timestamps", "timestamp"):
        if c in columns:
            return c
    return None


def _coverage_for_session(
    conn: Any,
    table: str,
    ts_col: str,
    session: str,
    present_cols: Dict[str, str],
    rows_per_session: int,
) -> Dict[str, Any]:
    """Bounded read of one session window; return per-column coverage stats."""
    select_cols = sorted(set(present_cols.values()))
    select_clause = ", ".join(_sqlite_quote_ident(c) for c in select_cols)
    prefix = f"substr(CAST({_sqlite_quote_ident(ts_col)} AS TEXT), 1, 8)"
    limit_sql = f" LIMIT {int(rows_per_session)}" if rows_per_session > 0 else ""
    q = (
        f"SELECT {select_clause} FROM {_sqlite_quote_ident(table)} "
        f"WHERE {prefix} = ? ORDER BY {_sqlite_quote_ident(ts_col)}{limit_sql}"
    )
    raw = pd.read_sql_query(q, conn, params=[session])
    total = int(len(raw))
    out: Dict[str, Any] = {"session": session, "rows": total, "columns": {}}
    for feat, dbcol in present_cols.items():
        series = pd.to_numeric(raw[dbcol], errors="coerce")
        non_null = int(series.notna().sum())
        non_zero = int((series.fillna(0) != 0).sum())
        finite = series.replace([np.inf, -np.inf], np.nan).dropna()
        out["columns"][feat] = {
            "db_column": dbcol,
            "non_null_pct": (non_null / total) if total else 0.0,
            "non_zero_pct": (non_zero / total) if total else 0.0,
            "min": float(finite.min()) if not finite.empty else None,
            "max": float(finite.max()) if not finite.empty else None,
            "mean": float(finite.mean()) if not finite.empty else None,
        }
    return out


def _effective_coverage(feat: str, col_stat: Dict[str, Any]) -> float:
    """Use non-zero coverage where 0 means missing, else non-null."""
    if feat in ZERO_MEANS_MISSING:
        return float(col_stat["non_zero_pct"])
    return float(col_stat["non_null_pct"])


def run_probe(
    db_path: str,
    symbols: int,
    sessions_per_symbol: int,
    rows_per_session: int,
    symbol_scan_cap: int,
) -> Dict[str, Any]:
    conn = connect_readonly(db_path)
    try:
        # Bounded symbol discovery: only scan up to symbol_scan_cap tables to
        # find ones that actually carry the candidate columns.
        all_tables = list_stock_tables(conn, max_tables=symbol_scan_cap)
        # First, decode columns for the scan window to learn which symbols carry
        # the NEW target columns (등락율 / 시가총액 / 고저평균대비등락율).
        new_targets = ["등락율", "시가총액", "고저평균대비등락율"]
        column_presence: Dict[str, List[str]] = {}
        candidate_tables: List[str] = []
        for table in all_tables:
            cols = _decode_table_columns(conn, table)
            column_presence[table] = cols
            if any(t in cols for t in new_targets):
                candidate_tables.append(table)

        # Prefer tables carrying the new columns; fall back to first tables.
        chosen = (candidate_tables or all_tables)[:symbols]

        per_symbol: List[Dict[str, Any]] = []
        # feature -> list of (symbol, session, effective_coverage)
        coverage_log: Dict[str, List[Tuple[str, str, float]]] = {f: [] for f in PROBE_COLUMNS}
        sanity: Dict[str, Dict[str, float]] = {f: {"min": np.inf, "max": -np.inf} for f in PROBE_COLUMNS}

        for table in chosen:
            cols = column_presence.get(table) or _decode_table_columns(conn, table)
            ts_col = _resolve_ts_col(cols)
            if ts_col is None:
                per_symbol.append({"table": table, "error": "no timestamp column", "decoded_columns": cols})
                continue
            present_cols: Dict[str, str] = {}
            for feat, candidates in PROBE_COLUMNS.items():
                for cand in candidates:
                    if cand in cols:
                        present_cols[feat] = cand
                        break
            sessions = _sessions_for_table(conn, table, ts_col, sessions_per_symbol)
            sym_entry: Dict[str, Any] = {
                "table": table,
                "timestamp_column": ts_col,
                "present_target_features": sorted(present_cols.keys()),
                "absent_target_features": sorted(set(PROBE_COLUMNS) - set(present_cols)),
                "sessions_sampled": sessions,
                "session_coverage": [],
            }
            for session in sessions:
                if not present_cols:
                    continue
                cov = _coverage_for_session(conn, table, ts_col, session, present_cols, rows_per_session)
                sym_entry["session_coverage"].append(cov)
                for feat, stat in cov["columns"].items():
                    eff = _effective_coverage(feat, stat)
                    coverage_log[feat].append((table, session, eff))
                    if stat["min"] is not None:
                        sanity[feat]["min"] = min(sanity[feat]["min"], stat["min"])
                    if stat["max"] is not None:
                        sanity[feat]["max"] = max(sanity[feat]["max"], stat["max"])
            per_symbol.append(sym_entry)

        # Aggregate verdict per feature.
        verdicts: Dict[str, Any] = {}
        for feat in PROBE_COLUMNS:
            obs = coverage_log[feat]
            exists = len(obs) > 0
            if not exists:
                verdicts[feat] = {
                    "exists": False,
                    "sessions_observed": 0,
                    "min_coverage": None,
                    "worst_session": None,
                    "verdict": "drop-or-fallback",
                    "note": "source column not present in any sampled symbol",
                }
                continue
            covs = [c for _, _, c in obs]
            worst_idx = int(np.argmin(covs))
            worst = obs[worst_idx]
            min_cov = float(min(covs))
            verdict = "add" if min_cov >= COVERAGE_THRESHOLD else "fallback-or-drop"
            smin = sanity[feat]["min"]
            smax = sanity[feat]["max"]
            verdicts[feat] = {
                "exists": True,
                "sessions_observed": len(obs),
                "min_coverage": min_cov,
                "mean_coverage": float(np.mean(covs)),
                "worst_session": {"symbol": worst[0], "session": worst[1], "coverage": worst[2]},
                "value_min": None if smin == np.inf else float(smin),
                "value_max": None if smax == -np.inf else float(smax),
                "coverage_basis": "non_zero" if feat in ZERO_MEANS_MISSING else "non_null",
                "verdict": verdict,
            }

        return {
            "db_path": str(Path(db_path).resolve()),
            "params": {
                "symbols": symbols,
                "sessions_per_symbol": sessions_per_symbol,
                "rows_per_session": rows_per_session,
                "symbol_scan_cap": symbol_scan_cap,
                "coverage_threshold": COVERAGE_THRESHOLD,
            },
            "chosen_symbols": chosen,
            "candidate_tables_with_new_columns": candidate_tables,
            "per_symbol": per_symbol,
            "verdicts": verdicts,
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage C-0 DB feature feasibility probe (read-only).")
    parser.add_argument("--db", required=True)
    parser.add_argument("--symbols", type=int, default=8)
    parser.add_argument("--sessions-per-symbol", type=int, default=3)
    parser.add_argument("--rows-per-session", type=int, default=3000)
    parser.add_argument("--symbol-scan-cap", type=int, default=40,
                        help="bounded number of tables to scan for column discovery")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    result = run_probe(
        db_path=args.db,
        symbols=args.symbols,
        sessions_per_symbol=args.sessions_per_symbol,
        rows_per_session=args.rows_per_session,
        symbol_scan_cap=args.symbol_scan_cap,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"[c0-probe] wrote {out_path}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
