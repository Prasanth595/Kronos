"""Negative/shuffle control gate for opening RL workflow evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


SUMMARY_JSON = "opening_negative_controls_summary.json"


def _control_row(raw: Mapping[str, Any], seed: int) -> dict[str, Any]:
    return {
        "control_type": str(raw.get("control_type", "unknown_control")),
        "verdict": str(raw.get("verdict", "NO-GO")),
        "seed": int(raw.get("seed", seed)),
        "metric": raw.get("metric"),
        "is_negative_control": True,
    }


def apply_opening_negative_controls(
    *,
    primary_verdict: str,
    controls: Sequence[Mapping[str, Any]],
    seed: int,
) -> dict[str, Any]:
    """Apply deterministic opening negative controls to a primary verdict."""

    rows = [_control_row(control, seed) for control in controls]
    all_controls_no_go = bool(rows) and all(row["verdict"] == "NO-GO" for row in rows)
    primary_is_candidate = primary_verdict == "GO_CANDIDATE"
    blocked = primary_is_candidate and not all_controls_no_go
    final_verdict = "NO-GO" if blocked else primary_verdict
    return {
        "artifact_type": "opening_30m_negative_controls",
        "mode": "opening_30m_negative_control_gate",
        "seed": int(seed),
        "primary_verdict_before_controls": primary_verdict,
        "final_verdict": final_verdict,
        "negative_control_passed": all_controls_no_go,
        "negative_control_blocked_go": blocked,
        "blocked_reason": "negative_control_not_no_go" if blocked else "",
        "controls": rows,
        "strategy_context": {
            "line": "opening_rl_controls",
            "label": "NEGATIVE CONTROL GATE",
            "is_live_ready": False,
            "is_profit_model": False,
        },
    }


def write_opening_controls_artifact(
    *,
    output_dir: Path,
    primary_verdict: str,
    controls: Sequence[Mapping[str, Any]],
    seed: int,
) -> dict[str, Any]:
    """Write opening negative-control verdict metadata."""

    payload = apply_opening_negative_controls(primary_verdict=primary_verdict, controls=controls, seed=seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / SUMMARY_JSON
    payload["artifacts"] = {"summary_json": str(summary_path)}
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
