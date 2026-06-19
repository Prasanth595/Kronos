"""Table and live-event readers for STOM RL dashboard artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .rl_dashboard_files import (
        LIVE_EVENT_FILE_NAMES,
        MAX_TABLE_LIMIT,
        ROOT_TABLE_CANDIDATES,
        TABLE_ALIASES,
        _is_run_file,
        _read_run_json,
        _read_run_csv_rows,
        _safe_direct_child_name,
    )
    from .rl_dashboard_opening_tables import load_opening_json_table
    from .rl_dashboard_runs import _baseline_policies, _detect_artifact_type, resolve_run_dir
except ImportError:  # pragma: no cover
    from rl_dashboard_files import (
        LIVE_EVENT_FILE_NAMES,
        MAX_TABLE_LIMIT,
        ROOT_TABLE_CANDIDATES,
        TABLE_ALIASES,
        _is_run_file,
        _read_run_json,
        _read_run_csv_rows,
        _safe_direct_child_name,
    )
    from rl_dashboard_opening_tables import load_opening_json_table
    from rl_dashboard_runs import _baseline_policies, _detect_artifact_type, resolve_run_dir


class RlDashboardTableError(ValueError):
    """Raised when a requested dashboard table alias is unknown."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


def _live_events_path(run_dir: Path) -> Optional[Path]:
    for file_name in LIVE_EVENT_FILE_NAMES:
        path = run_dir / file_name
        if _is_run_file(run_dir, path):
            return path
    return None


def _read_jsonl_rows(path: Path, *, limit: int) -> Tuple[List[Dict[str, Any]], bool]:
    limit = max(0, min(int(limit), MAX_TABLE_LIMIT))
    if limit == 0:
        return [], False
    lines = path.read_text(encoding="utf-8").splitlines()
    truncated = len(lines) > limit
    rows: List[Dict[str, Any]] = []
    for line in reversed(lines):
        if len(rows) >= limit:
            break
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    rows.reverse()
    return rows, truncated


def _normalize_table(table_name: str) -> str:
    table = str(table_name or "").strip().lower().replace("-", "_")
    if table not in TABLE_ALIASES:
        raise RlDashboardTableError(f"Unknown RL table: {table_name}")
    return TABLE_ALIASES[table]


def _read_policy_table(run_dir: Path, table: str, policy: Optional[str], limit: int) -> Dict[str, Any]:
    file_name = "equity.csv" if table == "equity" else f"{table}.csv"
    policies = [policy] if policy else _baseline_policies(run_dir)
    rows: List[Dict[str, Any]] = []
    truncated = False
    for policy_name in policies:
        safe_policy = _safe_direct_child_name(policy_name, label="policy")
        path = run_dir / safe_policy / file_name
        if not _is_run_file(run_dir, path):
            if policy:
                raise FileNotFoundError(f"Baseline table not found: {safe_policy}/{file_name}")
            continue
        remaining = max(0, min(int(limit), MAX_TABLE_LIMIT) - len(rows))
        table_rows, table_truncated = _read_run_csv_rows(run_dir, path, limit=remaining)
        rows.extend(table_rows)
        truncated = truncated or table_truncated
        if len(rows) >= min(int(limit), MAX_TABLE_LIMIT):
            truncated = truncated or table_truncated
            break
    return {"rows": rows, "row_count": len(rows), "truncated": truncated, "policies": policies}


def load_rl_table(run_name: str, table_name: str, *, policy: Optional[str] = None, limit: int = 500) -> Dict[str, Any]:
    """Load a CSV table for a run with path-safe table/policy handling."""

    run_dir = resolve_run_dir(run_name)
    artifact_type = _detect_artifact_type(run_dir)
    table = _normalize_table(table_name)
    limit = max(0, min(int(limit), MAX_TABLE_LIMIT))

    if artifact_type in {"opening_30m_rl_workflow", "opening_30m_rule_filter"}:
        opening_payload = load_opening_json_table(run_name, run_dir, artifact_type, table, limit=limit)
        if opening_payload is not None:
            return opening_payload

    if table == "events":
        path = _live_events_path(run_dir)
        if path is None:
            return {
                "run": run_name,
                "artifact_type": artifact_type,
                "table": table,
                "policy": policy,
                "source_file": None,
                "rows": [],
                "row_count": 0,
                "truncated": False,
                "message": "live event log is not available for this run",
            }
        rows, truncated = _read_jsonl_rows(path, limit=limit)
        return {
            "run": run_name,
            "artifact_type": artifact_type,
            "table": table,
            "policy": policy,
            "source_file": path.name,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }

    if artifact_type == "baseline" and table in {"actions", "trades", "equity", "episodes"}:
        payload = _read_policy_table(run_dir, table, policy, limit)
        payload.update({"run": run_name, "artifact_type": artifact_type, "table": table, "policy": policy})
        return payload

    for file_name in ROOT_TABLE_CANDIDATES.get(table, ()):
        path = run_dir / file_name
        if _is_run_file(run_dir, path):
            rows, truncated = _read_run_csv_rows(run_dir, path, limit=limit)
            return {
                "run": run_name,
                "artifact_type": artifact_type,
                "table": table,
                "policy": policy,
                "source_file": file_name,
                "rows": rows,
                "row_count": len(rows),
                "truncated": truncated,
            }
    raise FileNotFoundError(f"RL table not found for run={run_name!r}, table={table!r}")


def load_rl_cost_gate(run_name: str, *, limit: int = 500) -> Dict[str, Any]:
    """Load cost-gate summary and compact CSV tables for a cost-gate run."""

    run_dir = resolve_run_dir(run_name)
    report_path = run_dir / "cost_gate_report.json"
    if not _is_run_file(run_dir, report_path):
        raise FileNotFoundError(f"cost_gate_report.json not found for run: {run_name}")
    report = _read_run_json(run_dir, report_path)
    return {
        "run": run_name,
        "artifact_type": _detect_artifact_type(run_dir),
        "summary": report.get("summary", {}),
        "gate": load_rl_table(run_name, "gate", limit=limit),
        "scenario": load_rl_table(run_name, "scenario", limit=limit),
        "rolling": load_rl_table(run_name, "rolling", limit=limit),
    }


def load_rl_events(run_name: str, *, limit: int = 500) -> Dict[str, Any]:
    """Load realtime RL JSONL event tail for a run."""

    return load_rl_table(run_name, "events", limit=limit)
