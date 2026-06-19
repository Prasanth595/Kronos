"""Frozen chronological split manifests for opening real-data candidates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .opening_30m_rl_realdata import JsonValue


@dataclass(frozen=True, slots=True)
class OosSplitError(ValueError):
    """Raised when an opening OOS split would leak evaluation data."""

    reason: str

    def __str__(self) -> str:
        return self.reason


def build_oos_split_manifest(
    split_sessions: Mapping[str, Sequence[str]],
    *,
    symbol_sessions: Mapping[str, Sequence[str]] | None = None,
    output_path: Path | None = None,
) -> dict[str, JsonValue]:
    """Build a frozen train/validation/OOS manifest from session dates."""

    normalized = _normalize_splits(split_sessions)
    _assert_no_overlap(normalized)
    _assert_chronological(normalized)
    symbols = _symbol_counts(symbol_sessions or {})
    payload: dict[str, JsonValue] = {
        "artifact_type": "opening_30m_realdata_oos_split",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "split_sessions": normalized,
        "split_ranges": _split_ranges(normalized),
        "symbol_session_counts": symbols,
        "session_count": sum(len(values) for values in normalized.values()),
        "split_hash": _split_hash(normalized),
        "guardrail": "OOS is frozen before training; OOS tuning is forbidden.",
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def validate_oos_split_manifest(manifest: Mapping[str, JsonValue]) -> None:
    """Validate a dashboard or training split manifest."""

    raw = manifest.get("split_sessions")
    if not isinstance(raw, Mapping):
        raise OosSplitError("split_sessions is required")
    normalized = _normalize_splits({str(key): _as_str_sequence(value) for key, value in raw.items()})
    _assert_no_overlap(normalized)
    _assert_chronological(normalized)
    expected_hash = _split_hash(normalized)
    if str(manifest.get("split_hash", "")) != expected_hash:
        raise OosSplitError("split_hash does not match split membership")


def _normalize_splits(split_sessions: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    required = ("train", "validation", "oos")
    normalized: dict[str, list[str]] = {}
    for split in required:
        sessions = sorted(str(session) for session in split_sessions.get(split, ()))
        if not sessions:
            raise OosSplitError(f"{split} split must not be empty")
        normalized[split] = sessions
    return normalized


def _as_str_sequence(value: JsonValue) -> Sequence[str]:
    if not isinstance(value, list):
        raise OosSplitError("split membership must be a list")
    return [str(item) for item in value]


def _assert_no_overlap(split_sessions: Mapping[str, Sequence[str]]) -> None:
    seen: dict[str, str] = {}
    for split, sessions in split_sessions.items():
        for session in sessions:
            if session in seen:
                raise OosSplitError(f"session {session} overlaps {seen[session]} and {split}")
            seen[session] = split


def _assert_chronological(split_sessions: Mapping[str, Sequence[str]]) -> None:
    train_max = max(split_sessions["train"])
    validation_min = min(split_sessions["validation"])
    validation_max = max(split_sessions["validation"])
    oos_min = min(split_sessions["oos"])
    if not train_max < validation_min <= validation_max < oos_min:
        raise OosSplitError("split sessions must be chronological train < validation < oos")


def _split_ranges(split_sessions: Mapping[str, Sequence[str]]) -> dict[str, dict[str, JsonValue]]:
    return {
        split: {"start": min(sessions), "end": max(sessions), "session_count": len(sessions)}
        for split, sessions in split_sessions.items()
    }


def _symbol_counts(symbol_sessions: Mapping[str, Sequence[str]]) -> dict[str, JsonValue]:
    return {str(symbol): len(tuple(sessions)) for symbol, sessions in sorted(symbol_sessions.items())}


def _split_hash(split_sessions: Mapping[str, Sequence[str]]) -> str:
    encoded = json.dumps(split_sessions, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
