"""Page 16 — full-universe execution gate (checkpoint/resume runner).

This module is the *named finish line* for running the whole STOM tick DB
end-to-end: for every recording **session date** it builds the co-dated panel
(Page 7.5) → screens it into candidates with one rule (Page 9) → runs the
expanding-window holdout walk-forward (Page 11), writing per-session artifacts.

Why per-session (and never a full DB scan)
------------------------------------------
Symbols in the STOM tick DB have **disjoint recording dates** — an arbitrary
set of symbols cannot be mixed into one panel because they were not recorded on
the same day.  The only sound unit of work is therefore a single **session date**
grouping exactly the symbols that have data on that date.  We discover those
groups with a cheap per-table ``SELECT DISTINCT substr(index,1,8)`` query (the
``index`` column is ``YYYYMMDDHHMMSS``); this touches each table's index but
never materialises a full table.  The enumeration is cached to JSON so a rerun
skips the ~100s scan of 2400+ tables.

Checkpoint / resume
-------------------
A JSON **manifest** records each session's status
(``pending`` / ``running`` / ``done`` / ``failed``) with timestamps and row
counts.  On rerun with ``--resume`` a session already marked ``done`` is
**skipped** (its prior artifacts stand).  A ``running`` session that exceeds a
configurable wall-clock budget is flagged ``stuck`` in the progress log so an
operator can intervene; a session that raises is recorded ``failed`` (never
silently lost) and the run continues with the next session.

This module deliberately does **not** launch the full 29.7 GB run itself — the
full run is a long background job (see ``docs/stom_rl_page16_full_universe_*``).
The CLI is validated on a bounded slice (``--sessions`` / ``--max-sessions`` /
``--max-symbols-per-session``) end-to-end.

Reuse only — no duplicated pipeline logic
-----------------------------------------
* session panel:    :func:`stom_rl.panel_join.build_panel_from_db` (as-of join)
* candidates:       :func:`stom_rl.candidate_gen.generate_candidates` (T+1 fill)
* holdout eval:     :func:`stom_rl.portfolio_walk_forward.run_portfolio_walk_forward`
* symbol/table key: :mod:`stom_rl.symbol_norm` / DB table name == padded code
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from finetune_csv.stom_tick_dataset import connect_readonly, list_stock_tables
from stom_rl.candidate_gen import build_topk_report, generate_candidates, write_topk_report
from stom_rl.condition_screener import load_rules
from stom_rl.panel_join import build_panel_from_db
from stom_rl.portfolio_walk_forward import (
    PortfolioWalkForwardConfig,
    run_portfolio_walk_forward,
)

# Status vocabulary for the manifest.  ``stuck`` is a *log* flag (a long-running
# ``running`` entry), not a terminal manifest status.
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

MANIFEST_NAME = "_manifest.json"
ENUM_CACHE_NAME = "_session_index.json"
PROGRESS_LOG_NAME = "_progress.log"

# Default wall-clock budget (seconds) before a running session is flagged stuck.
DEFAULT_STUCK_SECONDS: float = 1800.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Session enumeration (cheap per-table DISTINCT date query; never a full scan)
# ---------------------------------------------------------------------------
def enumerate_sessions(
    db_path: Union[str, os.PathLike],
    *,
    max_symbols: int = 0,
    timestamp_column: str = "index",
) -> Dict[str, List[str]]:
    """Return ``{session_date(YYYYMMDD): [symbol tables with data on it]}``.

    For every symbol table we run a single ``SELECT DISTINCT
    substr(CAST(<ts> AS TEXT), 1, 8)`` — the recorded session dates of that
    table.  This touches the table's timestamp column only (SQLite scans the
    column, not the row payload) and is the only sound grouping because symbols
    have disjoint recording dates.  ``max_symbols`` bounds the number of tables
    scanned (for in-session validation); ``0`` means all tables.

    Symbols are returned sorted within each session and the dict is ordered by
    session date so callers (and tests) get a deterministic ordering.
    """

    conn = connect_readonly(db_path)
    try:
        tables = list_stock_tables(conn, max_tables=max_symbols if max_symbols and max_symbols > 0 else None)
        quoted_ts = '"' + str(timestamp_column).replace('"', '""') + '"'
        session_map: Dict[str, List[str]] = defaultdict(list)
        for table in tables:
            quoted_table = '"' + str(table).replace('"', '""') + '"'
            query = f"SELECT DISTINCT substr(CAST({quoted_ts} AS TEXT), 1, 8) FROM {quoted_table}"
            for (date_text,) in conn.execute(query).fetchall():
                if date_text is None:
                    continue
                date_str = str(date_text)
                if len(date_str) == 8 and date_str.isdigit():
                    session_map[date_str].append(str(table))
    finally:
        conn.close()

    return {date: sorted(symbols) for date, symbols in sorted(session_map.items())}


def load_or_build_session_index(
    db_path: Union[str, os.PathLike],
    output_dir: Union[str, os.PathLike],
    *,
    max_symbols: int = 0,
    refresh: bool = False,
) -> Dict[str, List[str]]:
    """Load the cached session index, or build (and cache) it once.

    The enumeration over 2400+ tables costs ~100s, so we cache it to
    ``<output_dir>/_session_index.json`` keyed by ``max_symbols`` so a bounded
    cache is never mistaken for the full one.  ``refresh=True`` forces a rebuild.
    """

    cache_path = Path(output_dir) / ENUM_CACHE_NAME
    cache_key = int(max_symbols or 0)
    if cache_path.exists() and not refresh:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8-sig"))
            if int(cached.get("max_symbols", -1)) == cache_key:
                return {str(k): list(v) for k, v in cached.get("sessions", {}).items()}
        except (json.JSONDecodeError, OSError):
            pass  # rebuild on a corrupt cache

    sessions = enumerate_sessions(db_path, max_symbols=max_symbols)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {"max_symbols": cache_key, "built_at": _utc_now_iso(), "sessions": sessions},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )
    return sessions


# ---------------------------------------------------------------------------
# Manifest (checkpoint/resume state)
# ---------------------------------------------------------------------------
@dataclass
class SessionManifestEntry:
    """One session's checkpoint row in the manifest."""

    session: str
    status: str = STATUS_PENDING
    symbol_count: int = 0
    candidate_count: int = 0
    fold_count: int = 0
    panel_rows: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session": self.session,
            "status": self.status,
            "symbol_count": int(self.symbol_count),
            "candidate_count": int(self.candidate_count),
            "fold_count": int(self.fold_count),
            "panel_rows": int(self.panel_rows),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": self.elapsed_seconds,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SessionManifestEntry":
        return cls(
            session=str(data["session"]),
            status=str(data.get("status", STATUS_PENDING)),
            symbol_count=int(data.get("symbol_count", 0)),
            candidate_count=int(data.get("candidate_count", 0)),
            fold_count=int(data.get("fold_count", 0)),
            panel_rows=int(data.get("panel_rows", 0)),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            elapsed_seconds=data.get("elapsed_seconds"),
            error=data.get("error"),
        )


@dataclass
class RunManifest:
    """The full-universe run manifest: rule, output dir, and per-session entries."""

    rule: str = ""
    output_dir: str = ""
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    entries: Dict[str, SessionManifestEntry] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return Path(self.output_dir) / MANIFEST_NAME

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule,
            "output_dir": self.output_dir,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "entries": {s: e.to_dict() for s, e in self.entries.items()},
        }

    def save(self) -> None:
        self.updated_at = _utc_now_iso()
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8-sig")

    @classmethod
    def load(cls, output_dir: Union[str, os.PathLike]) -> Optional["RunManifest"]:
        path = Path(output_dir) / MANIFEST_NAME
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            return None
        manifest = cls(
            rule=str(data.get("rule", "")),
            output_dir=str(data.get("output_dir", str(output_dir))),
            created_at=str(data.get("created_at", _utc_now_iso())),
            updated_at=str(data.get("updated_at", _utc_now_iso())),
        )
        for session, entry in (data.get("entries") or {}).items():
            manifest.entries[str(session)] = SessionManifestEntry.from_dict(entry)
        return manifest


def _load_or_init_manifest(
    output_dir: Union[str, os.PathLike],
    rule: str,
    sessions: Sequence[str],
    *,
    resume: bool,
) -> RunManifest:
    """Load an existing manifest (resume) or initialise a fresh one.

    On resume the existing per-session statuses are preserved (so ``done``
    sessions stay ``done`` and get skipped); any newly requested session not yet
    in the manifest is added as ``pending``.  Without resume a fresh manifest is
    created with every requested session ``pending`` — but pre-existing terminal
    state on disk is still honoured to avoid clobbering completed work.
    """

    manifest = RunManifest.load(output_dir) if resume else None
    if manifest is None:
        manifest = RunManifest(rule=str(rule), output_dir=str(output_dir))
    for session in sessions:
        if session not in manifest.entries:
            manifest.entries[session] = SessionManifestEntry(session=session)
    return manifest


# ---------------------------------------------------------------------------
# Progress / stuck logging
# ---------------------------------------------------------------------------
def _append_progress(output_dir: Union[str, os.PathLike], message: str) -> None:
    log_path = Path(output_dir) / PROGRESS_LOG_NAME
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{_utc_now_iso()}\t{message}\n"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line)


def flag_stuck_sessions(
    manifest: RunManifest,
    *,
    stuck_seconds: float = DEFAULT_STUCK_SECONDS,
    now: Optional[float] = None,
) -> List[str]:
    """Return sessions whose ``running`` entry has exceeded ``stuck_seconds``.

    Used by an external monitor: a ``running`` entry whose ``started_at`` is
    older than the budget is considered stuck (no progress).  This reads only the
    manifest, so a separate watcher process can call it without touching the DB.
    """

    reference = float(now) if now is not None else time.time()
    stuck: List[str] = []
    for session, entry in manifest.entries.items():
        if entry.status != STATUS_RUNNING or not entry.started_at:
            continue
        try:
            started = datetime.strptime(entry.started_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if reference - started.timestamp() > float(stuck_seconds):
            stuck.append(session)
    return stuck


# ---------------------------------------------------------------------------
# Per-session pipeline (reuses Page 7.5 / 9 / 11 — no duplicated logic)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FullUniverseConfig:
    db_path: str
    rule_path: str
    output_dir: str
    time_start: str = "090000"
    time_end: str = "093000"
    max_symbols_per_session: int = 0
    max_rows_per_group: int = 0
    n_folds: int = 2
    cost_bps: float = 25.0
    top_k: int = 3
    freq: str = "1s"
    stuck_seconds: float = DEFAULT_STUCK_SECONDS
    # Bound the *enumeration* table scan for in-session validation (0 = all
    # tables).  Distinct from ``max_symbols_per_session`` which caps symbols
    # *within* a session at run time.
    enum_max_tables: int = 0


def run_session(
    session: str,
    symbols: Sequence[str],
    config: FullUniverseConfig,
) -> Dict[str, Any]:
    """Run the end-to-end pipeline for ONE session and write its artifacts.

    panel (as-of) → candidates (T+1 fill) → holdout walk-forward.  Artifacts land
    under ``<output_dir>/<session>/``.  Returns a summary dict (counts + artifact
    paths).  Raises on any pipeline failure so the caller records ``failed``.
    """

    session_dir = Path(config.output_dir) / session
    session_dir.mkdir(parents=True, exist_ok=True)

    rules = load_rules(Path(config.rule_path))

    panel, panel_report = build_panel_from_db(
        db_path=config.db_path,
        tables=list(symbols),
        session=session,
        time_start=config.time_start,
        time_end=config.time_end,
        max_rows_per_group=config.max_rows_per_group,
        freq=config.freq,
    )

    candidates = generate_candidates(panel, rules)
    candidate_csv = session_dir / "candidates.csv"
    candidates.to_csv(candidate_csv, index=False, encoding="utf-8-sig")

    topk_report = build_topk_report(candidates, top_k=config.top_k)
    write_topk_report(session_dir / "topk_report.json", topk_report)

    walk_forward: Optional[Dict[str, Any]] = None
    fold_count = 0
    distinct_timestamps = int(candidates["timestamp"].nunique()) if not candidates.empty else 0
    # The holdout needs >=2 distinct timestamps to form a train/test split.
    if distinct_timestamps >= 2:
        wf_config = PortfolioWalkForwardConfig(
            candidate_path=str(candidate_csv),
            output_dir=str(session_dir / "walk_forward"),
            n_folds=config.n_folds,
            cost_bps=config.cost_bps,
            top_k_candidates=config.top_k,
        )
        walk_forward = run_portfolio_walk_forward(wf_config)
        fold_count = int(walk_forward.get("summary", {}).get("n_folds", 0))

    summary = {
        "session": session,
        "symbol_count": len(symbols),
        "panel_rows": int(len(panel)),
        "panel_grid_size": int(panel_report.grid_size),
        "candidate_count": int(len(candidates)),
        "distinct_timestamps": distinct_timestamps,
        "fold_count": fold_count,
        "artifacts": {
            "session_dir": str(session_dir),
            "candidates_csv": str(candidate_csv),
            "topk_report": str(session_dir / "topk_report.json"),
            "walk_forward_dir": str(session_dir / "walk_forward") if walk_forward else None,
        },
    }
    (session_dir / "session_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8-sig"
    )
    return summary


def _select_sessions(
    session_index: Mapping[str, Sequence[str]],
    *,
    sessions: Optional[Sequence[str]],
    max_sessions: int,
) -> List[str]:
    """Resolve the requested session list against the enumerated index.

    Explicit ``--sessions`` win (filtered to those present in the index);
    otherwise the first ``max_sessions`` (deterministic date order) are taken, or
    all sessions when ``max_sessions`` is 0.
    """

    available = list(session_index.keys())
    if sessions:
        requested = [s for s in sessions if s in session_index]
        return requested
    if max_sessions and max_sessions > 0:
        return available[: int(max_sessions)]
    return available


def run_full_universe(
    config: FullUniverseConfig,
    *,
    sessions: Optional[Sequence[str]] = None,
    max_sessions: int = 0,
    resume: bool = False,
    refresh_index: bool = False,
) -> Dict[str, Any]:
    """Drive the full-universe gate with checkpoint/resume + progress logging.

    For each selected session: skip if already ``done`` (resume), else run the
    per-session pipeline, marking ``running`` → ``done``/``failed`` in the
    manifest and appending a progress line at each transition.  A failing session
    is recorded ``failed`` (with its error) and the run continues.
    """

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    session_index = load_or_build_session_index(
        config.db_path,
        output_dir,
        max_symbols=int(config.enum_max_tables or 0),
        refresh=refresh_index,
    )
    selected = _select_sessions(session_index, sessions=sessions, max_sessions=max_sessions)

    manifest = _load_or_init_manifest(output_dir, config.rule_path, selected, resume=resume)
    manifest.rule = config.rule_path
    manifest.save()

    _append_progress(
        output_dir,
        f"RUN_START sessions={len(selected)} resume={resume} rule={Path(config.rule_path).name}",
    )

    processed: List[str] = []
    skipped: List[str] = []
    failed: List[str] = []

    for session in selected:
        entry = manifest.entries[session]
        if resume and entry.status == STATUS_DONE:
            skipped.append(session)
            _append_progress(output_dir, f"SKIP session={session} status=done")
            continue

        symbols = list(session_index.get(session, []))
        if config.max_symbols_per_session and config.max_symbols_per_session > 0:
            symbols = symbols[: int(config.max_symbols_per_session)]

        entry.status = STATUS_RUNNING
        entry.symbol_count = len(symbols)
        entry.started_at = _utc_now_iso()
        entry.finished_at = None
        entry.error = None
        manifest.save()
        _append_progress(output_dir, f"SESSION_START session={session} symbols={len(symbols)}")

        started = time.time()
        try:
            summary = run_session(session, symbols, config)
            elapsed = time.time() - started
            entry.status = STATUS_DONE
            entry.candidate_count = int(summary["candidate_count"])
            entry.fold_count = int(summary["fold_count"])
            entry.panel_rows = int(summary["panel_rows"])
            entry.finished_at = _utc_now_iso()
            entry.elapsed_seconds = round(elapsed, 3)
            manifest.save()
            processed.append(session)
            _append_progress(
                output_dir,
                f"SESSION_DONE session={session} candidates={entry.candidate_count} "
                f"folds={entry.fold_count} panel_rows={entry.panel_rows} elapsed={elapsed:.2f}s",
            )
        except Exception as exc:  # noqa: BLE001 — record, never silently lose
            elapsed = time.time() - started
            entry.status = STATUS_FAILED
            entry.finished_at = _utc_now_iso()
            entry.elapsed_seconds = round(elapsed, 3)
            entry.error = f"{type(exc).__name__}: {exc}"
            manifest.save()
            failed.append(session)
            _append_progress(
                output_dir,
                f"SESSION_FAILED session={session} error={type(exc).__name__}: {exc} elapsed={elapsed:.2f}s",
            )

    result = {
        "output_dir": str(output_dir),
        "rule": config.rule_path,
        "selected_sessions": selected,
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "manifest_path": str(manifest.path),
        "progress_log": str(output_dir / PROGRESS_LOG_NAME),
    }
    _append_progress(
        output_dir,
        f"RUN_END processed={len(processed)} skipped={len(skipped)} failed={len(failed)}",
    )
    (output_dir / "_run_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8-sig"
    )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Page 16 — full-universe execution gate with checkpoint/resume.",
    )
    parser.add_argument("--db", required=True, help="STOM tick DB path.")
    parser.add_argument("--rule", required=True, help="Rule JSON path (e.g. stom_rl/rules/buy_demand_pressure.json).")
    parser.add_argument("--output-dir", required=True, help="Artifact + manifest output directory.")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--sessions", default=None, help="Comma-separated session dates (YYYYMMDD) to run.")
    group.add_argument("--max-sessions", type=int, default=0, help="Run the first N enumerated sessions (0=all).")

    parser.add_argument("--max-symbols-per-session", type=int, default=0, help="Cap symbols per session (0=all).")
    parser.add_argument("--enum-max-tables", type=int, default=0, help="Cap tables scanned during session enumeration (0=all).")
    parser.add_argument("--max-rows-per-group", type=int, default=0, help="Cap rows per symbol window (0=window-bounded).")
    parser.add_argument("--time-start", default="090000", help="Window start HHMMSS.")
    parser.add_argument("--time-end", default="093000", help="Window end HHMMSS.")
    parser.add_argument("--n-folds", type=int, default=2, help="Walk-forward folds per session.")
    parser.add_argument("--cost-bps", type=float, default=25.0, help="Round-trip cost in bps.")
    parser.add_argument("--top-k", type=int, default=3, help="Top-K size for candidate report / env.")
    parser.add_argument(
        "--freq",
        default="1s",
        choices=["1s", "1min"],
        help="Bar frequency for the feed path (default 1s; 1min resamples the RL source).",
    )
    parser.add_argument("--stuck-seconds", type=float, default=DEFAULT_STUCK_SECONDS, help="Wall-clock budget before stuck flag.")
    parser.add_argument("--resume", action="store_true", help="Skip sessions already marked done.")
    parser.add_argument("--refresh-index", action="store_true", help="Rebuild the cached session index.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    sessions: Optional[List[str]] = None
    if args.sessions:
        sessions = [s.strip() for s in str(args.sessions).split(",") if s.strip()]

    config = FullUniverseConfig(
        db_path=args.db,
        rule_path=args.rule,
        output_dir=args.output_dir,
        time_start=args.time_start,
        time_end=args.time_end,
        max_symbols_per_session=int(args.max_symbols_per_session),
        max_rows_per_group=int(args.max_rows_per_group),
        n_folds=int(args.n_folds),
        cost_bps=float(args.cost_bps),
        top_k=int(args.top_k),
        freq=str(args.freq),
        stuck_seconds=float(args.stuck_seconds),
        enum_max_tables=int(args.enum_max_tables),
    )
    result = run_full_universe(
        config,
        sessions=sessions,
        max_sessions=int(args.max_sessions),
        resume=bool(args.resume),
        refresh_index=bool(args.refresh_index),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
