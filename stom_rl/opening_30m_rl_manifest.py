"""Opening-window episode manifest adapter for orderbook RL workflows."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd  # noqa: PANDAS_OK - interoperates with existing STOM DataFrame pipeline

from .episode_manifest import _validate_split_sessions


DEFAULT_OUTPUT_DIR = Path("webui") / "rl_runs" / "opening_30m_episode_manifest"
DEFAULT_SPLIT_SESSIONS = {
    "train": ("20250103",),
    "val": ("20250106",),
    "test": ("20250107",),
}
MANIFEST_JSON = "opening_episode_manifest.json"
MANIFEST_CSV = "opening_episode_manifest.csv"
SUMMARY_JSON = "opening_episode_manifest_summary.json"


@dataclass(frozen=True, slots=True)
class OpeningEpisodeManifestConfig:
    """Configuration for fixture-safe opening-window manifest generation."""

    output_dir: Path | str = DEFAULT_OUTPUT_DIR
    split_sessions: Mapping[str, Sequence[str]] = field(default_factory=lambda: DEFAULT_SPLIT_SESSIONS)
    time_start: str = "090000"
    time_end: str = "093000"
    lookback_window: int = 30
    reward_horizon_seconds: int = 300
    write_artifacts: bool = True


@dataclass(frozen=True, slots=True)
class OpeningManifestError(ValueError):
    """Typed opening manifest contract error."""

    reason: str

    def __str__(self) -> str:
        return self.reason


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def _quote_coverage(frame: pd.DataFrame) -> float:
    has_quote = (
        frame["매수호가1"].astype(float).gt(0.0)
        & frame["매도호가1"].astype(float).gt(0.0)
        & frame["매수잔량1"].astype(float).gt(0.0)
        & frame["매도잔량1"].astype(float).gt(0.0)
    )
    total_rows = int(len(frame))
    return float(has_quote.sum()) / total_rows if total_rows else 0.0


def _split_lookup(split_sessions: Mapping[str, Sequence[str]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for split, sessions in split_sessions.items():
        for session in sessions:
            session_text = str(session)
            if session_text in lookup and lookup[session_text] != split:
                raise OpeningManifestError(
                    f"split overlap: session {session_text} is both {lookup[session_text]} and {split}"
                )
            lookup[session_text] = split
    return lookup


def _assert_chronological(split_validation: Mapping[str, Any]) -> None:
    if not bool(split_validation.get("chronological_train_val_test")):
        raise OpeningManifestError("split sessions must be chronological train -> val -> test")


def _episode_rows(
    frames: Sequence[pd.DataFrame],
    config: OpeningEpisodeManifestConfig,
    manifest_csv_path: Path,
    summary_json_path: Path,
) -> list[dict[str, Any]]:
    split_by_session = _split_lookup(config.split_sessions)
    rows: list[dict[str, Any]] = []
    for frame in frames:
        if frame.empty:
            continue
        symbol = str(frame["symbol"].iloc[0])
        session = str(frame["session"].iloc[0])
        rows.append(
            {
                "episode_id": f"{symbol}_{session}",
                "symbol": symbol,
                "session": session,
                "split": split_by_session.get(session, "unknown"),
                "time_start": config.time_start,
                "time_end": config.time_end,
                "lookback_window": int(config.lookback_window),
                "reward_horizon_seconds": int(config.reward_horizon_seconds),
                "row_count": int(len(frame)),
                "quote_coverage": _quote_coverage(frame),
                "source_csv": str(manifest_csv_path),
                "stage_evidence_json": str(summary_json_path),
            }
        )
    return sorted(rows, key=lambda item: (str(item["session"]), str(item["symbol"])))


def _summary(
    episodes: Sequence[Mapping[str, Any]],
    split_validation: Mapping[str, Any],
) -> dict[str, Any]:
    by_split: dict[str, int] = {}
    for episode in episodes:
        split = str(episode["split"])
        by_split[split] = by_split.get(split, 0) + 1
    return {
        "episode_count": len(episodes),
        "by_split": dict(sorted(by_split.items())),
        "split_validation": dict(split_validation),
        "min_quote_coverage": min((float(row["quote_coverage"]) for row in episodes), default=0.0),
        "time_start": episodes[0]["time_start"] if episodes else "",
        "time_end": episodes[0]["time_end"] if episodes else "",
    }


def _write_manifest_csv(path: Path, episodes: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = [
        "episode_id",
        "symbol",
        "session",
        "split",
        "time_start",
        "time_end",
        "lookback_window",
        "reward_horizon_seconds",
        "row_count",
        "quote_coverage",
        "source_csv",
        "stage_evidence_json",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for episode in episodes:
            writer.writerow({field: episode.get(field) for field in fieldnames})


def build_opening_episode_manifest(
    frames: Sequence[pd.DataFrame],
    config: OpeningEpisodeManifestConfig,
) -> dict[str, Any]:
    """Build an opening 09:00-09:30 manifest from tick/orderbook frames."""

    split_validation = _validate_split_sessions(config.split_sessions)
    if int(split_validation["overlap_count"]):
        raise OpeningManifestError("split overlap; refusing to write opening episode manifest")
    _assert_chronological(split_validation)

    output_dir = Path(config.output_dir)
    manifest_json_path = output_dir / MANIFEST_JSON
    manifest_csv_path = output_dir / MANIFEST_CSV
    summary_json_path = output_dir / SUMMARY_JSON
    episodes = _episode_rows(frames, config, manifest_csv_path, summary_json_path)
    if not episodes:
        raise OpeningManifestError("opening episode manifest requires at least one episode")

    summary = _summary(episodes, split_validation)
    payload: dict[str, Any] = {
        "mode": "opening_30m_episode_manifest",
        "artifact_type": "opening_30m_episode_manifest",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "config": {
            "output_dir": str(output_dir),
            "split_sessions": {key: list(value) for key, value in config.split_sessions.items()},
            "time_start": config.time_start,
            "time_end": config.time_end,
            "lookback_window": int(config.lookback_window),
            "reward_horizon_seconds": int(config.reward_horizon_seconds),
        },
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
        _write_json(summary_json_path, {key: value for key, value in payload.items() if key != "episodes"})
        _write_manifest_csv(manifest_csv_path, episodes)
    return payload
