"""Build STOM RL episode manifests from read-only STOM data sources.

Page 2 of the independent RL lab is deliberately model-free.  Its job is to
turn the already verified STOM 2025 1-second export into a deterministic list
of train/validation/test episode candidates while proving that the source
SQLite database is opened read-only.

The manifest is the contract consumed by later pages:

* Page 3: ``StomTickTradingEnv`` loads one episode at a time.
* Page 4: baseline runners iterate the same manifest.
* Page 5+: reward/cost gates and RL models reuse the same split boundaries.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


DEFAULT_DB_PATH = Path("_database") / "stock_tick_back.db"
DEFAULT_EXPORT_REPORT = (
    Path("finetune") / "qlib_exports" / "stom_1s_grid_pred60_2025" / "stom_qlib_export_report.json"
)
DEFAULT_OUTPUT_DIR = Path("webui") / "rl_runs" / "stom_1s_2025_episode_manifest"
EPISODE_FILE_RE = re.compile(r"^(?P<instrument>KR(?P<symbol>.+))_(?P<session>\d{8})\.csv$")


@dataclass(frozen=True)
class EpisodeManifestConfig:
    """Configuration for a deterministic RL episode manifest."""

    db_path: str = str(DEFAULT_DB_PATH)
    export_report_path: str = str(DEFAULT_EXPORT_REPORT)
    qlib_csv_dir: Optional[str] = None
    output_dir: str = str(DEFAULT_OUTPUT_DIR)
    session_start: str = "20250101"
    session_end: str = "20251231"
    time_start: str = "090000"
    time_end: str = "093000"
    reward_horizon_seconds: int = 300
    lookback_window: int = 300
    max_episodes: int = 0
    count_csv_rows: bool = False
    write_artifacts: bool = True


def _normalize_date_bound(value: str, label: str) -> str:
    text = str(value).replace("-", "").strip()
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"{label} must be YYYYMMDD or YYYY-MM-DD, got: {value}")
    return text


def connect_readonly(db_path: os.PathLike[str] | str) -> sqlite3.Connection:
    """Open a SQLite database in read-only and query-only mode.

    ``mode=ro`` protects the source file at the SQLite URI level.  The
    additional ``PRAGMA query_only=ON`` blocks accidental writes on the
    connection even if a future maintainer changes the URI.
    """

    path = Path(db_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {path}")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def verify_readonly_connection(db_path: os.PathLike[str] | str) -> Dict[str, Any]:
    """Return evidence that the STOM DB is opened without write authority."""

    path = Path(db_path).resolve()
    conn = connect_readonly(path)
    try:
        query_only = int(conn.execute("PRAGMA query_only").fetchone()[0])
        database_list = [
            {"seq": row[0], "name": row[1], "file": row[2]}
            for row in conn.execute("PRAGMA database_list").fetchall()
        ]
        write_probe_blocked = False
        write_probe_error = ""
        try:
            conn.execute("CREATE TABLE __stom_rl_write_probe__(id INTEGER)")
        except sqlite3.DatabaseError as exc:
            write_probe_blocked = True
            write_probe_error = str(exc)
        return {
            "db_path": str(path),
            "db_size_bytes": path.stat().st_size,
            "sqlite_uri_mode": "ro",
            "query_only": query_only,
            "database_list": database_list,
            "write_probe_blocked": write_probe_blocked,
            "write_probe_error": write_probe_error,
        }
    finally:
        conn.close()


def _read_json(path: os.PathLike[str] | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def _parse_episode_file(path: Path) -> Optional[Dict[str, str]]:
    match = EPISODE_FILE_RE.match(path.name)
    if not match:
        return None
    return {
        "instrument": match.group("instrument"),
        "symbol": match.group("symbol"),
        "session": match.group("session"),
        "source_csv": str(path),
    }


def _line_count_data_rows(path: Path) -> int:
    with path.open("rb") as f:
        lines = sum(1 for _ in f)
    return max(0, lines - 1)


def _split_lookup(split_sessions: Mapping[str, Sequence[str]]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for split, sessions in split_sessions.items():
        for session in sessions:
            if session in lookup and lookup[session] != split:
                raise ValueError(f"Session {session} appears in multiple splits: {lookup[session]} and {split}")
            lookup[str(session)] = split
    return lookup


def _validate_split_sessions(split_sessions: Mapping[str, Sequence[str]]) -> Dict[str, Any]:
    split_sets = {split: set(map(str, sessions)) for split, sessions in split_sessions.items()}
    overlaps: List[Tuple[str, str, List[str]]] = []
    names = sorted(split_sets)
    for idx, left in enumerate(names):
        for right in names[idx + 1 :]:
            overlap = sorted(split_sets[left] & split_sets[right])
            if overlap:
                overlaps.append((left, right, overlap))
    ordered_sessions = [session for split in ["train", "val", "test"] for session in sorted(split_sets.get(split, []))]
    monotonic = ordered_sessions == sorted(ordered_sessions)
    return {
        "split_session_counts": {split: len(sessions) for split, sessions in split_sets.items()},
        "overlap_count": sum(len(item[2]) for item in overlaps),
        "overlaps": [
            {"left": left, "right": right, "sessions": sessions}
            for left, right, sessions in overlaps
        ],
        "chronological_train_val_test": monotonic,
    }


def _load_export_context(config: EpisodeManifestConfig) -> Tuple[Dict[str, Any], Path]:
    report = _read_json(config.export_report_path)
    qlib_csv_dir = Path(config.qlib_csv_dir or report.get("qlib_csv_dir") or "").resolve()
    if not qlib_csv_dir.exists():
        raise FileNotFoundError(f"Qlib CSV directory not found: {qlib_csv_dir}")
    return report, qlib_csv_dir


def _episode_sort_key(episode: Mapping[str, Any]) -> Tuple[str, str]:
    return str(episode["session"]), str(episode["symbol"])


def _build_episode_rows(
    qlib_csv_dir: Path,
    split_sessions: Mapping[str, Sequence[str]],
    config: EpisodeManifestConfig,
) -> List[Dict[str, Any]]:
    session_start = _normalize_date_bound(config.session_start, "session_start")
    session_end = _normalize_date_bound(config.session_end, "session_end")
    split_by_session = _split_lookup(split_sessions)

    episodes: List[Dict[str, Any]] = []
    for csv_path in sorted(qlib_csv_dir.glob("*.csv")):
        parsed = _parse_episode_file(csv_path)
        if not parsed:
            continue
        session = parsed["session"]
        if session < session_start or session > session_end:
            continue
        split = split_by_session.get(session, "unknown")
        row_count = _line_count_data_rows(csv_path) if config.count_csv_rows else None
        episode = {
            "episode_id": f"{parsed['symbol']}_{session}",
            "symbol": parsed["symbol"],
            "instrument": parsed["instrument"],
            "session": session,
            "split": split,
            "time_start": config.time_start,
            "time_end": config.time_end,
            "lookback_window": config.lookback_window,
            "reward_horizon_seconds": config.reward_horizon_seconds,
            "row_count": row_count,
            "source_csv": parsed["source_csv"],
        }
        episodes.append(episode)

    episodes = sorted(episodes, key=_episode_sort_key)
    if config.max_episodes and config.max_episodes > 0:
        episodes = episodes[: config.max_episodes]
    return episodes


def _summarize_episodes(
    episodes: Sequence[Mapping[str, Any]],
    report: Mapping[str, Any],
    split_validation: Mapping[str, Any],
) -> Dict[str, Any]:
    by_split: Dict[str, int] = {}
    by_session: Dict[str, int] = {}
    symbols = set()
    counted_rows = 0
    has_counted_rows = False
    for episode in episodes:
        split = str(episode.get("split", "unknown"))
        session = str(episode["session"])
        by_split[split] = by_split.get(split, 0) + 1
        by_session[session] = by_session.get(session, 0) + 1
        symbols.add(str(episode["symbol"]))
        row_count = episode.get("row_count")
        if row_count is not None:
            has_counted_rows = True
            counted_rows += int(row_count)

    report_split_counts = report.get("split_counts", {})
    expected_by_split = {
        split: int(values.get("groups", 0))
        for split, values in report_split_counts.items()
        if isinstance(values, Mapping)
    }
    deltas = {
        split: by_split.get(split, 0) - expected
        for split, expected in expected_by_split.items()
    }
    expected_total = int(report.get("exported_group_count") or sum(expected_by_split.values()))
    manifest_total = len(episodes)

    return {
        "episode_count": manifest_total,
        "symbol_count": len(symbols),
        "session_count": len(by_session),
        "by_split": dict(sorted(by_split.items())),
        "expected_by_split_from_export_report": dict(sorted(expected_by_split.items())),
        "by_split_delta_vs_export_report": dict(sorted(deltas.items())),
        "expected_exported_group_count": expected_total,
        "manifest_group_delta_vs_export_report": manifest_total - expected_total,
        "counted_csv_rows": counted_rows if has_counted_rows else None,
        "export_report_row_count": report.get("exported_row_count"),
        "split_validation": dict(split_validation),
        "data_quality": {
            "unknown_split_episodes": by_split.get("unknown", 0),
            "split_session_overlap_count": split_validation.get("overlap_count", 0),
            "chronological_train_val_test": split_validation.get("chronological_train_val_test"),
            "uses_existing_kronos_export_as_external_data_contract": True,
        },
    }


def _write_manifest_csv(path: Path, episodes: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "episode_id",
        "symbol",
        "instrument",
        "session",
        "split",
        "time_start",
        "time_end",
        "lookback_window",
        "reward_horizon_seconds",
        "row_count",
        "source_csv",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for episode in episodes:
            writer.writerow({key: episode.get(key) for key in fieldnames})


def build_episode_manifest(config: EpisodeManifestConfig) -> Dict[str, Any]:
    """Build a STOM RL episode manifest and optional artifact files."""

    report, qlib_csv_dir = _load_export_context(config)
    split_sessions = report.get("split_sessions") or {}
    if not split_sessions:
        raise ValueError("Export report does not contain split_sessions.")
    split_validation = _validate_split_sessions(split_sessions)
    if split_validation["overlap_count"]:
        raise ValueError("Export report split_sessions overlap; refusing to build RL manifest.")

    db_readonly = verify_readonly_connection(config.db_path)
    episodes = _build_episode_rows(qlib_csv_dir, split_sessions, config)
    if not episodes:
        raise ValueError("No episode CSV files matched the requested manifest bounds.")

    output_dir = Path(config.output_dir)
    manifest_json_path = output_dir / "episode_manifest.json"
    manifest_csv_path = output_dir / "episode_manifest.csv"
    summary_json_path = output_dir / "episode_summary.json"
    summary = _summarize_episodes(episodes, report, split_validation)

    payload: Dict[str, Any] = {
        "mode": "stom_rl_episode_manifest",
        "created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "config": asdict(config),
        "source": {
            "db_path": str(Path(config.db_path)),
            "export_report_path": str(Path(config.export_report_path)),
            "qlib_csv_dir": str(qlib_csv_dir),
        },
        "db_readonly": db_readonly,
        "summary": summary,
        "episodes": episodes,
        "artifacts": {
            "manifest_json": str(manifest_json_path),
            "manifest_csv": str(manifest_csv_path),
            "summary_json": str(summary_json_path),
        },
    }
    if config.write_artifacts:
        _write_json(manifest_json_path, payload)
        _write_json(summary_json_path, {k: v for k, v in payload.items() if k != "episodes"})
        _write_manifest_csv(manifest_csv_path, episodes)
    return payload


def load_episode_manifest(path: os.PathLike[str] | str) -> Dict[str, Any]:
    """Load a previously generated manifest JSON."""

    return _read_json(path)


def _parse_args(argv: Optional[Sequence[str]] = None) -> EpisodeManifestConfig:
    parser = argparse.ArgumentParser(description="Build a STOM RL episode manifest.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Read-only source STOM SQLite DB.")
    parser.add_argument("--export-report", default=str(DEFAULT_EXPORT_REPORT))
    parser.add_argument("--qlib-csv-dir", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--session-start", default="20250101")
    parser.add_argument("--session-end", default="20251231")
    parser.add_argument("--time-start", default="090000")
    parser.add_argument("--time-end", default="093000")
    parser.add_argument("--reward-horizon-seconds", type=int, default=300)
    parser.add_argument("--lookback-window", type=int, default=300)
    parser.add_argument("--max-episodes", type=int, default=0)
    parser.add_argument("--count-csv-rows", action="store_true")
    parser.add_argument("--no-write", action="store_true", help="Return summary without writing artifacts.")
    args = parser.parse_args(argv)
    return EpisodeManifestConfig(
        db_path=args.db,
        export_report_path=args.export_report,
        qlib_csv_dir=args.qlib_csv_dir,
        output_dir=args.output_dir,
        session_start=args.session_start,
        session_end=args.session_end,
        time_start=args.time_start,
        time_end=args.time_end,
        reward_horizon_seconds=args.reward_horizon_seconds,
        lookback_window=args.lookback_window,
        max_episodes=args.max_episodes,
        count_csv_rows=args.count_csv_rows,
        write_artifacts=not args.no_write,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    config = _parse_args(argv)
    payload = build_episode_manifest(config)
    print(json.dumps({k: v for k, v in payload.items() if k != "episodes"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
