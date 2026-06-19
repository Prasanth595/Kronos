"""Dataset artifacts for opening real-data candidate training."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

from .opening_30m_rl_oos_split import validate_oos_split_manifest
from .opening_30m_rl_realdata import JsonValue


def build_dataset_artifact(
    rows: Sequence[Mapping[str, JsonValue]],
    *,
    split_manifest: Mapping[str, JsonValue],
    features: Sequence[str],
    participant_proxy_availability: Mapping[str, bool],
    orderbook_feature_availability: Mapping[str, bool],
    output_path: Path | None = None,
) -> dict[str, JsonValue]:
    """Build a dashboard-readable training dataset contract artifact."""

    validate_oos_split_manifest(split_manifest)
    split_sessions = split_manifest["split_sessions"]
    if not isinstance(split_sessions, Mapping):
        raise TypeError("validated split_sessions must be a mapping")
    session_to_split = _session_to_split(split_sessions)
    dataset_rows = [_dataset_row(row, session_to_split) for row in rows]
    payload: dict[str, JsonValue] = {
        "artifact_type": "opening_30m_realdata_dataset",
        "split_hash": str(split_manifest["split_hash"]),
        "features": list(features),
        "rows": dataset_rows,
        "row_count": len(dataset_rows),
        "participant_proxy_availability": _availability(participant_proxy_availability),
        "orderbook_feature_availability": _availability(orderbook_feature_availability),
        "guardrail": "Unavailable proxies are reported, not zero-filled.",
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _session_to_split(split_sessions: Mapping[str, JsonValue]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for split, sessions in split_sessions.items():
        if not isinstance(sessions, list):
            raise TypeError("split sessions must be lists")
        for session in sessions:
            lookup[str(session)] = str(split)
    return lookup


def _dataset_row(row: Mapping[str, JsonValue], session_to_split: Mapping[str, str]) -> dict[str, JsonValue]:
    session = str(row.get("session_date", row.get("session", "")))
    split = session_to_split.get(session)
    if split is None:
        raise ValueError(f"session {session} is absent from the split manifest")
    return {
        "symbol": str(row.get("symbol", "")),
        "session_date": session,
        "split": split,
        "row_count": int(row.get("row_count", 0) or 0),
        "exclusion_reason": str(row.get("exclusion_reason", "")),
        "action_contract_version": str(row.get("action_contract_version", "opening_discrete_v1")),
    }


def _availability(availability: Mapping[str, bool]) -> dict[str, dict[str, JsonValue]]:
    return {
        str(name): {"available": bool(is_available), "filled_with_zero": False}
        for name, is_available in sorted(availability.items())
    }
