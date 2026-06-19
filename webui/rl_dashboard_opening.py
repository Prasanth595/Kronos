"""Opening 30-minute RL workflow dashboard adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

try:
    from .rl_dashboard_files import _read_run_json
except ImportError:  # pragma: no cover - supports direct script-style imports
    from rl_dashboard_files import _read_run_json


def opening_workflow_summary(run_dir: Path) -> Dict[str, Any]:
    """Return a compact summary for an opening workflow run."""

    payload = _read_run_json(run_dir, run_dir / "opening_30m_rl_workflow_summary.json")
    config = payload.get("config", {})
    guardrails = payload.get("guardrails", {})
    realdata = payload.get("realdata", {})
    validation_gate = payload.get("realdata_validation_gate", {})
    stages = payload.get("stages", [])
    candidate_history = payload.get("candidate_history", [])
    candidate_lifecycle = payload.get("candidate_lifecycle", {})
    if not isinstance(config, Mapping):
        config = {}
    if not isinstance(guardrails, Mapping):
        guardrails = {}
    if not isinstance(realdata, Mapping):
        realdata = {}
    if not isinstance(validation_gate, Mapping):
        validation_gate = {}
    if not isinstance(candidate_lifecycle, Mapping):
        candidate_lifecycle = {}
    if not isinstance(candidate_history, list):
        candidate_history = []
    realdata_bounds = realdata.get("bounds", {})
    sampled_tables = realdata.get("sampled_tables", [])
    if not isinstance(realdata_bounds, Mapping):
        realdata_bounds = {}
    if not isinstance(sampled_tables, list):
        sampled_tables = []
    stage_rows = stages if isinstance(stages, list) else []
    passed_statuses = {"complete", "completed", "passed"}
    blocked_statuses = {"blocked", "failed"}
    return {
        "run_id": payload.get("run_id", run_dir.name),
        "verdict": payload.get("verdict"),
        "cost_bps": config.get("cost_bps"),
        "baseline": guardrails.get("baseline"),
        "time_start": config.get("time_start"),
        "time_end": config.get("time_end"),
        "realdata_time_start": realdata_bounds.get("time_start"),
        "realdata_time_end": realdata_bounds.get("time_end"),
        "realdata_sampled_table_count": len(sampled_tables),
        "model_status": realdata.get("model_status"),
        "training_status": realdata.get("training_status"),
        "validation_verdict": validation_gate.get("verdict") or realdata.get("verdict") or payload.get("candidate_verdict"),
        "candidate_count": len(candidate_history),
        "candidate_verdict": payload.get("candidate_verdict"),
        "split_hash": _nested(candidate_lifecycle, "split_manifest", "split_hash"),
        "stage_count": len(stage_rows),
        "passed_stage_count": sum(
            1
            for stage in stage_rows
            if isinstance(stage, Mapping) and str(stage.get("status", "")).lower() in passed_statuses
        ),
        "blocked_stage_count": sum(
            1
            for stage in stage_rows
            if isinstance(stage, Mapping) and str(stage.get("status", "")).lower() in blocked_statuses
        ),
        "participant_context_version": payload.get("participant_context_version"),
        "missing_proxy_columns": payload.get("missing_proxy_columns", []),
    }


def load_opening_workflow_detail(run_dir: Path) -> Dict[str, Any]:
    """Load the full opening workflow manifest for a detail view."""

    return _read_run_json(run_dir, run_dir / "opening_30m_rl_workflow_summary.json")


def _nested(mapping: Mapping[str, Any], first: str, second: str) -> Any:
    value = mapping.get(first, {})
    if isinstance(value, Mapping):
        return value.get(second)
    return None
