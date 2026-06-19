"""Opening workflow JSON table adapters for the RL dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .rl_dashboard_files import MAX_TABLE_LIMIT, _is_run_file, _read_run_json
except ImportError:  # pragma: no cover
    from rl_dashboard_files import MAX_TABLE_LIMIT, _is_run_file, _read_run_json


def _limited_rows(rows: List[Dict[str, Any]], *, limit: int) -> Tuple[List[Dict[str, Any]], bool]:
    capped_limit = max(0, min(int(limit), MAX_TABLE_LIMIT))
    return rows[:capped_limit], len(rows) > capped_limit


def _mapping_rows(mapping: Any, *, key_name: str, value_name: str) -> List[Dict[str, Any]]:
    if not isinstance(mapping, dict):
        return []
    rows: List[Dict[str, Any]] = []
    for key, value in mapping.items():
        row: Dict[str, Any] = {key_name: str(key)}
        if isinstance(value, dict):
            row.update(value)
        else:
            row[value_name] = value
        rows.append(row)
    return rows


def _proxy_availability_rows(run_dir: Path) -> List[Dict[str, Any]]:
    summary = _read_run_json(run_dir, run_dir / "opening_30m_rl_workflow_summary.json")
    readiness_path = _first_run_file(
        run_dir,
        (
            run_dir / "participant_pressure_readiness_summary.json",
            run_dir / "participant_pressure" / "participant_pressure_readiness_summary.json",
        ),
    )
    readiness = _read_run_json(run_dir, readiness_path) if readiness_path is not None else {}
    availability = readiness.get("proxy_availability", summary.get("proxy_availability", {}))
    schema_rows = readiness.get("feature_schema", [])
    schema_by_name = {
        str(row.get("name")): row
        for row in schema_rows
        if isinstance(row, dict) and row.get("name") is not None
    }
    rows = _mapping_rows(availability, key_name="proxy", value_name="status")
    for row in rows:
        schema = schema_by_name.get(str(row["proxy"]), {})
        if isinstance(schema, dict):
            row.setdefault("feature_group", schema.get("feature_group"))
            row.setdefault("source_column", schema.get("source_column"))
    return rows


def _first_run_file(run_dir: Path, paths: Tuple[Path, ...]) -> Optional[Path]:
    for path in paths:
        if _is_run_file(run_dir, path):
            return path
    return None


def _table_payload(
    *,
    run_name: str,
    artifact_type: str,
    table: str,
    source_file: str,
    rows: List[Dict[str, Any]],
    limit: int,
) -> Dict[str, Any]:
    limited, truncated = _limited_rows(rows, limit=limit)
    return {
        "run": run_name,
        "artifact_type": artifact_type,
        "table": table,
        "policy": None,
        "source_file": source_file,
        "rows": limited,
        "row_count": len(limited),
        "truncated": truncated,
    }


def _candidate_lifecycle(run_dir: Path) -> Dict[str, Any]:
    payload = _read_run_json(run_dir, run_dir / "opening_30m_rl_workflow_summary.json")
    lifecycle = payload.get("candidate_lifecycle", {})
    return lifecycle if isinstance(lifecycle, dict) else {}


def _rule_filter_lifecycle(run_dir: Path) -> Dict[str, Any]:
    path = run_dir / "opening_rule_filter_lifecycle.json"
    if not _is_run_file(run_dir, path):
        return {}
    payload = _read_run_json(run_dir, path)
    return payload if isinstance(payload, dict) else {}


def _rule_filter_split_rows(run_dir: Path) -> List[Dict[str, Any]]:
    lifecycle = _rule_filter_lifecycle(run_dir)
    manifest = lifecycle.get("split_manifest", {})
    split_sessions = manifest.get("split_sessions", {}) if isinstance(manifest, dict) else {}
    rows: List[Dict[str, Any]] = []
    if isinstance(split_sessions, dict):
        split_hash = manifest.get("split_hash") if isinstance(manifest, dict) else ""
        for split, sessions in split_sessions.items():
            if isinstance(sessions, list):
                rows.extend({"split": split, "session": session, "split_hash": split_hash} for session in sessions)
    return rows


def _rule_filter_table(run_name: str, run_dir: Path, artifact_type: str, table: str, limit: int) -> Optional[Dict[str, Any]]:
    lifecycle = _rule_filter_lifecycle(run_dir)
    if not lifecycle:
        return None
    gate = lifecycle.get("promotion_gate", {})
    controls = lifecycle.get("controls", {})
    ablations = lifecycle.get("ablations", {})
    rows: List[Dict[str, Any]] | None = None
    if table == "rule_filter_lifecycle":
        policy = lifecycle.get("policy", {})
        rows = [dict(policy)] if isinstance(policy, dict) else []
    elif table == "rule_filter_splits":
        rows = _rule_filter_split_rows(run_dir)
    elif table == "rule_filter_controls":
        raw = controls.get("controls", []) if isinstance(controls, dict) else []
        rows = [dict(row) for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
    elif table == "rule_filter_ablations":
        raw = ablations.get("ablations", []) if isinstance(ablations, dict) else []
        rows = [dict(row) for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
    elif table == "rule_filter_equity_curve":
        raw = gate.get("equity_curve", []) if isinstance(gate, dict) else []
        rows = [dict(row) for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
    elif table == "rule_filter_time_buckets":
        raw = gate.get("time_bucket_performance", []) if isinstance(gate, dict) else []
        rows = [dict(row) for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
    elif table == "rule_filter_failure_reasons":
        raw = gate.get("blocking_reasons", []) if isinstance(gate, dict) else []
        rows = [{"reason": str(reason)} for reason in raw] if isinstance(raw, list) else []
    elif table == "rule_filter_opportunity_cost":
        raw = gate.get("opportunity_cost_curve", []) if isinstance(gate, dict) else []
        rows = [dict(row) for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
    elif table == "rule_filter_context_sample":
        rows = _rule_filter_context_rows(lifecycle)
    elif table == "rule_filter_proxy_availability":
        rows = _rule_filter_proxy_rows(lifecycle)
    elif table == "rule_filter_orderbook_persistence":
        rows = _rule_filter_orderbook_rows(lifecycle)
    if rows is None:
        return None
    return _table_payload(run_name=run_name, artifact_type=artifact_type, table=table, source_file="opening_rule_filter_lifecycle.json", rows=rows, limit=limit)


def _rule_filter_context_rows(lifecycle: Dict[str, Any]) -> List[Dict[str, Any]]:
    context = lifecycle.get("context_features", {})
    names = context.get("feature_names", []) if isinstance(context, dict) else []
    sample = context.get("sample", {}) if isinstance(context, dict) else {}
    vector = sample.get("vector", []) if isinstance(sample, dict) else []
    if not isinstance(names, list):
        return []
    return [{"feature_name": str(name), "value": vector[index] if isinstance(vector, list) and index < len(vector) else None} for index, name in enumerate(names)]


def _rule_filter_proxy_rows(lifecycle: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = lifecycle.get("dataset_rows", [])
    if not isinstance(rows, list) or not rows:
        return []
    first = rows[0]
    availability = first.get("proxy_availability", {}) if isinstance(first, dict) else {}
    return _mapping_rows(availability, key_name="proxy", value_name="status")


def _rule_filter_orderbook_rows(lifecycle: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = lifecycle.get("dataset_rows", [])
    if not isinstance(rows, list) or not rows:
        return []
    first = rows[0]
    diagnostics = first.get("diagnostics", {}) if isinstance(first, dict) else {}
    components = diagnostics.get("orderbook_components", {}) if isinstance(diagnostics, dict) else {}
    return _mapping_rows(components, key_name="component", value_name="value")


def _candidate_rows(run_dir: Path) -> List[Dict[str, Any]]:
    lifecycle = _candidate_lifecycle(run_dir)
    training = lifecycle.get("training", {})
    rows = training.get("candidates", []) if isinstance(training, dict) else []
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _split_rows(run_dir: Path) -> List[Dict[str, Any]]:
    lifecycle = _candidate_lifecycle(run_dir)
    manifest = lifecycle.get("split_manifest", {})
    split_sessions = manifest.get("split_sessions", {}) if isinstance(manifest, dict) else {}
    rows: List[Dict[str, Any]] = []
    if isinstance(split_sessions, dict):
        split_hash = manifest.get("split_hash") if isinstance(manifest, dict) else ""
        for split, sessions in split_sessions.items():
            if isinstance(sessions, list):
                for session in sessions:
                    rows.append({"split": split, "session": session, "split_hash": split_hash})
    return rows


def _lifecycle_rows(run_dir: Path, section: str, key: str) -> List[Dict[str, Any]]:
    lifecycle = _candidate_lifecycle(run_dir)
    payload = lifecycle.get(section, {})
    rows = payload.get(key, []) if isinstance(payload, dict) else []
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _gate_rows(run_dir: Path, key: str) -> List[Dict[str, Any]]:
    lifecycle = _candidate_lifecycle(run_dir)
    gate = lifecycle.get("promotion_gate", {})
    rows = gate.get(key, []) if isinstance(gate, dict) else []
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _candidate_table(run_name: str, run_dir: Path, artifact_type: str, table: str, limit: int) -> Optional[Dict[str, Any]]:
    table_rows: List[Dict[str, Any]] | None = None
    if table == "candidate_lifecycle":
        table_rows = _candidate_rows(run_dir)
    elif table == "candidate_splits":
        table_rows = _split_rows(run_dir)
    elif table in {"candidate_controls", "negative_controls"}:
        table_rows = _lifecycle_rows(run_dir, "controls", "controls")
    elif table in {"candidate_ablations", "candidate_feature_ablation"}:
        table_rows = _lifecycle_rows(run_dir, "ablations", "ablations")
    elif table == "candidate_equity_curve":
        table_rows = _gate_rows(run_dir, "equity_curve")
    elif table == "candidate_time_buckets":
        table_rows = _gate_rows(run_dir, "time_bucket_performance")
    elif table == "candidate_failure_reasons":
        lifecycle = _candidate_lifecycle(run_dir)
        gate = lifecycle.get("promotion_gate", {})
        reasons = gate.get("blocking_reasons", []) if isinstance(gate, dict) else []
        table_rows = [{"reason": str(reason)} for reason in reasons] if isinstance(reasons, list) else []
    elif table == "context_feature_sample":
        table_rows = _context_feature_rows(run_dir)
    if table_rows is None:
        return None
    return _table_payload(
        run_name=run_name,
        artifact_type=artifact_type,
        table=table,
        source_file="opening_candidate_lifecycle.json",
        rows=table_rows,
        limit=limit,
    )


def _context_feature_rows(run_dir: Path) -> List[Dict[str, Any]]:
    lifecycle = _candidate_lifecycle(run_dir)
    context = lifecycle.get("context_features", {})
    if not isinstance(context, dict):
        return []
    names = context.get("feature_names", [])
    sample = context.get("sample", {})
    vector = sample.get("vector", []) if isinstance(sample, dict) else []
    if not isinstance(names, list):
        return []
    rows: List[Dict[str, Any]] = []
    for index, name in enumerate(names):
        value = vector[index] if isinstance(vector, list) and index < len(vector) else None
        rows.append({"feature_name": str(name), "value": value, "status": context.get("status", "")})
    return rows


def load_opening_json_table(
    run_name: str,
    run_dir: Path,
    artifact_type: str,
    table: str,
    *,
    limit: int,
) -> Optional[Dict[str, Any]]:
    """Load JSON-backed table aliases for opening workflow artifacts."""

    rule_filter_payload = _rule_filter_table(run_name, run_dir, artifact_type, table, limit)
    if rule_filter_payload is not None:
        return rule_filter_payload

    candidate_payload = _candidate_table(run_name, run_dir, artifact_type, table, limit)
    if candidate_payload is not None:
        return candidate_payload

    summary_path = run_dir / "opening_30m_rl_workflow_summary.json"
    if table == "stages":
        payload = _read_run_json(run_dir, summary_path)
        raw_rows = payload.get("stages", [])
        rows = [dict(row) for row in raw_rows if isinstance(row, dict)] if isinstance(raw_rows, list) else []
        return _table_payload(run_name=run_name, artifact_type=artifact_type, table=table, source_file=summary_path.name, rows=rows, limit=limit)
    if table == "controls":
        controls_path = run_dir / "opening_negative_controls_summary.json"
        if not _is_run_file(run_dir, controls_path):
            return None
        payload = _read_run_json(run_dir, controls_path)
        raw_rows = payload.get("controls", [])
        rows = [dict(row) for row in raw_rows if isinstance(row, dict)] if isinstance(raw_rows, list) else []
        return _table_payload(run_name=run_name, artifact_type=artifact_type, table=table, source_file=controls_path.name, rows=rows, limit=limit)
    if table == "proxy_availability":
        rows = _proxy_availability_rows(run_dir)
        if not rows:
            return None
        return _table_payload(run_name=run_name, artifact_type=artifact_type, table=table, source_file="participant_pressure_readiness_summary.json", rows=rows, limit=limit)
    if table == "orderbook_persistence":
        score_path = run_dir / "orderbook_persistence_score_summary.json"
        if not _is_run_file(run_dir, score_path):
            return None
        payload = _read_run_json(run_dir, score_path)
        rows = _mapping_rows(payload.get("components", {}), key_name="component", value_name="value")
        return _table_payload(run_name=run_name, artifact_type=artifact_type, table=table, source_file=score_path.name, rows=rows, limit=limit)
    if table == "feature_ablation":
        payload = _read_run_json(run_dir, summary_path)
        raw_results = payload.get("feature_ablation_results", {})
        if not raw_results and isinstance(payload.get("realdata_validation_gate"), dict):
            raw_results = payload["realdata_validation_gate"].get("feature_ablation_results", {})
        rows = _mapping_rows(raw_results, key_name="feature_ablation", value_name="value")
        if not rows:
            return None
        return _table_payload(run_name=run_name, artifact_type=artifact_type, table=table, source_file=summary_path.name, rows=rows, limit=limit)
    return None
