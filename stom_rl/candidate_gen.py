"""Page 9 — real candidate generation from a Page 7.5 multi-symbol panel.

This is a *thin* module: it does not re-implement panel building or screening.
It glues the Page 7.5 panel (:mod:`stom_rl.panel_join`) to the Page 8 safe
screener (:mod:`stom_rl.condition_screener`) and adds a per-timestamp top-K
distribution report.

Pipeline
--------
1.  A long-format panel ``timestamp, symbol, <14 canonical features>`` is built
    by :func:`stom_rl.panel_join.build_panel_from_db` (per-day-chunk, never a
    full scan) or supplied directly / via CSV.
2.  :func:`stom_rl.condition_screener.screen_frame` applies one rule JSON and
    returns candidates carrying the **T+1 fill contract** (``price`` = decision
    close at ``T``; ``fill_price`` = next-bar close; last bar → ``fill_price``
    NaN / ``fillable == False``).  See the screener module docstring for the
    authoritative contract; Page 10/11/12 reuse it.
3.  :func:`build_topk_report` summarises, per decision timestamp, how many
    symbols passed and the rank_score distribution (for top-K position sizing).

Leakage guard: the panel rows are point-in-time correct (as-of backward join),
``price`` is the close at ``T``, and ``fill_price`` is drawn strictly from a
*later* bar (T+1).  No candidate feature uses data after its decision time.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from stom_rl.condition_screener import (
    ConditionRule,
    load_rules,
    screen_frame,
    write_candidates,
)
from stom_rl.panel_join import build_panel_from_db
from stom_rl.symbol_norm import read_candidates_csv


def generate_candidates(
    panel: pd.DataFrame,
    rules: Sequence[ConditionRule],
    *,
    strategy_side: str = "buy",
    drop_unfillable: bool = False,
) -> pd.DataFrame:
    """Screen a Page 7.5 panel into candidates with the T+1 fill contract.

    A thin pass-through to :func:`screen_frame`; kept as a named entry point so
    the Page 9 pipeline (and tests) have a stable seam over the panel→candidate
    boundary.  The panel must carry ``timestamp``, ``symbol`` and a price column
    (``close`` for the canonical panel).
    """

    return screen_frame(
        panel,
        rules,
        strategy_side=strategy_side,
        drop_unfillable=drop_unfillable,
    )


def build_topk_report(candidates: pd.DataFrame, top_k: int = 3) -> pd.DataFrame:
    """Per-timestamp passing-symbol count + rank_score distribution.

    For every decision timestamp the report records how many symbols passed, the
    rank_score min/mean/max, the top-K symbols (highest rank_score first), and
    how many of the passing rows are fillable (have a real T+1 fill).  This is
    the input a position-sizer needs to know whether a timestamp even has enough
    candidates to fill K positions.
    """

    columns = [
        "timestamp",
        "passing_symbols",
        "fillable_symbols",
        "rank_score_min",
        "rank_score_mean",
        "rank_score_max",
        f"top_{top_k}_symbols",
        f"top_{top_k}_rank_scores",
    ]
    if candidates.empty:
        return pd.DataFrame(columns=columns)

    records: List[Dict[str, Any]] = []
    for timestamp, group in candidates.groupby("timestamp", sort=True):
        ordered = group.sort_values(["rank_score", "symbol"], ascending=[False, True])
        head = ordered.head(int(top_k))
        fillable_count = (
            int(ordered["fillable"].sum()) if "fillable" in ordered.columns else int(len(ordered))
        )
        records.append(
            {
                "timestamp": str(timestamp),
                "passing_symbols": int(len(ordered)),
                "fillable_symbols": fillable_count,
                "rank_score_min": float(ordered["rank_score"].min()),
                "rank_score_mean": float(ordered["rank_score"].mean()),
                "rank_score_max": float(ordered["rank_score"].max()),
                f"top_{top_k}_symbols": list(head["symbol"]),
                f"top_{top_k}_rank_scores": [float(v) for v in head["rank_score"]],
            }
        )
    return pd.DataFrame(records, columns=columns).reset_index(drop=True)


def write_topk_report(path: Path, report: pd.DataFrame) -> None:
    """Write the top-K report as JSON (``.json``) or CSV (any other suffix)."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(
            json.dumps(report.to_dict("records"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8-sig",
        )
    else:
        report.to_csv(path, index=False, encoding="utf-8-sig")


def _load_panel(input_csv: Optional[str]) -> pd.DataFrame:
    if not input_csv:
        raise ValueError("--input-csv is required when --db is not given")
    return read_candidates_csv(input_csv)


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Page 9 — generate real portfolio candidates from a Page 7.5 panel.",
    )
    source = parser.add_argument_group("panel source (CSV or DB window)")
    source.add_argument("--input-csv", default=None, help="Page 7.5 panel CSV (long format).")
    source.add_argument("--db", default=None, help="STOM tick DB path (per-day-chunk window only).")
    source.add_argument("--tables", default=None, help="Comma-separated symbol tables (with --db).")
    source.add_argument("--session", default=None, help="Session date YYYYMMDD (with --db).")
    source.add_argument("--time-start", default="090000", help="Window start HHMMSS (with --db).")
    source.add_argument("--time-end", default="093000", help="Window end HHMMSS (with --db).")
    source.add_argument(
        "--freq",
        default="1s",
        choices=["1s", "1min", "session"],
        help="Bar frequency for the DB feed path (default 1s; 1min resamples the RL "
        "source; session = ONE bar per (symbol, session) — the Story B1 caveated "
        "daily proxy, NOT a clean daily bar).",
    )

    parser.add_argument("--rules", required=True, help="Page 8 rule JSON path.")
    parser.add_argument("--output", required=True, help="Candidate CSV/JSONL output path.")
    parser.add_argument("--topk-report", default=None, help="Optional top-K report path (.json/.csv).")
    parser.add_argument("--top-k", type=int, default=3, help="Top-K size for the distribution report.")
    parser.add_argument(
        "--drop-unfillable",
        action="store_true",
        help="Drop last-bar (no T+1) candidates instead of flagging them.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    rules = load_rules(Path(args.rules))

    if args.db and args.tables:
        tables = [t.strip() for t in str(args.tables).split(",") if t.strip()]
        panel, _report = build_panel_from_db(
            db_path=args.db,
            tables=tables,
            session=args.session,
            time_start=args.time_start,
            time_end=args.time_end,
            freq=args.freq,
        )
    else:
        panel = _load_panel(args.input_csv)

    candidates = generate_candidates(panel, rules, drop_unfillable=bool(args.drop_unfillable))
    write_candidates(Path(args.output), candidates)

    fillable = int(candidates["fillable"].sum()) if "fillable" in candidates.columns and not candidates.empty else 0
    summary: Dict[str, Any] = {
        "candidate_count": int(len(candidates)),
        "fillable_count": fillable,
        "unfillable_count": int(len(candidates)) - fillable,
        "output": str(args.output),
    }

    if args.topk_report:
        report = build_topk_report(candidates, top_k=int(args.top_k))
        write_topk_report(Path(args.topk_report), report)
        summary["topk_report"] = str(args.topk_report)
        summary["timestamps_with_candidates"] = int(len(report))

    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
