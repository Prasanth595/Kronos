"""Run listing and detail loading for STOM RL dashboard artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

try:
    from .rl_strategy_context import build_strategy_context
    from . import rl_dashboard_files as _files
    from .rl_dashboard_opening import load_opening_workflow_detail, opening_workflow_summary
    from .rl_dashboard_files import ARTIFACT_SIGNATURES, LIVE_SUMMARY_FILE_NAMES, RlDashboardPathError, _int_or_zero, _is_relative_to_root, _is_run_file, _read_run_json, _safe_direct_child_name, _utc_mtime
except ImportError:  # pragma: no cover - supports direct script-style imports
    from rl_strategy_context import build_strategy_context
    import rl_dashboard_files as _files
    from rl_dashboard_opening import load_opening_workflow_detail, opening_workflow_summary
    from rl_dashboard_files import ARTIFACT_SIGNATURES, LIVE_SUMMARY_FILE_NAMES, RlDashboardPathError, _int_or_zero, _is_relative_to_root, _is_run_file, _read_run_json, _safe_direct_child_name, _utc_mtime

def _detect_artifact_type(run_dir: Path) -> str:
    for artifact_type, file_name in ARTIFACT_SIGNATURES:
        if _is_run_file(run_dir, run_dir / file_name):
            return artifact_type
    return "unknown"


def _find_json_summary(run_dir: Path, artifact_type: str) -> Dict[str, Any]:
    if artifact_type == "opening_30m_rule_filter":
        payload = _read_run_json(run_dir, run_dir / "opening_rule_filter_summary.json")
        summary = dict(payload)
        summary.pop("rule_filter_lifecycle", None)
        return summary
    if artifact_type == "opening_30m_rl_workflow":
        return opening_workflow_summary(run_dir)
    if artifact_type == "orderbook_rl_readiness":
        payload = _read_run_json(run_dir, run_dir / "orderbook_rl_readiness_summary.json")
        return dict(payload.get("summary", {}))
    if artifact_type == "portfolio_paper":
        payload = _read_run_json(run_dir, run_dir / "portfolio_paper_summary.json")
        summary = dict(payload.get("summary", {}))
        config = payload.get("config", {})
        if isinstance(config, dict):
            summary.setdefault("cost_bps", config.get("cost_bps"))
            summary.setdefault("max_positions", config.get("max_positions"))
            summary.setdefault("top_k_candidates", config.get("top_k_candidates"))
        return summary
    if artifact_type == "performance_leaderboard":
        payload = _read_run_json(run_dir, run_dir / "performance_leaderboard.json")
        return dict(payload.get("summary", {}))
    if artifact_type == "sb3_smoke":
        payload = _read_run_json(run_dir, run_dir / "sb3_smoke_summary.json")
        summary = dict(payload.get("summary", {}))
        live_summary = payload.get("live_events")
        if isinstance(live_summary, dict):
            summary.setdefault("live_event_count", live_summary.get("event_count"))
            summary.setdefault("live_event_phases", live_summary.get("phases"))
        else:
            for file_name in LIVE_SUMMARY_FILE_NAMES:
                summary_path = run_dir / file_name
                if _is_run_file(run_dir, summary_path):
                    file_summary = _read_run_json(run_dir, summary_path)
                    summary.setdefault("live_event_count", file_summary.get("event_count"))
                    summary.setdefault("live_event_phases", file_summary.get("phases"))
                    break
        models = payload.get("models", [])
        best_model = summary.get("best_model")
        selected_model = next((row for row in models if row.get("model") == best_model), models[0] if models else {})
        summary.setdefault(
            "max_training_timesteps",
            max((_int_or_zero(row.get("training_timesteps")) for row in models), default=0),
        )
        for key in (
            "avg_episode_net_return_pct",
            "trade_count",
            "cost_bps",
            "slippage_bps",
            "passes_cost_gate",
        ):
            if key in selected_model:
                summary.setdefault(key, selected_model[key])
        return summary
    if artifact_type == "contextual_bandit":
        payload = _read_run_json(run_dir, run_dir / "eval_summary.json")
        return dict(payload.get("eval_summary", payload.get("summary", {})))
    if artifact_type == "cost_gate":
        payload = _read_run_json(run_dir, run_dir / "cost_gate_report.json")
        return dict(payload.get("summary", {}))
    if artifact_type == "baseline":
        payload = _read_run_json(run_dir, run_dir / "baseline_summary.json")
        return dict(payload.get("summary", {}))
    if artifact_type == "episode_manifest":
        summary_path = run_dir / "episode_summary.json"
        payload = _read_run_json(run_dir, summary_path if _is_run_file(run_dir, summary_path) else run_dir / "episode_manifest.json")
        return dict(payload.get("summary", payload))
    return {}


def _artifact_files(run_dir: Path) -> List[Dict[str, Any]]:
    files = []
    for path in sorted(run_dir.rglob("*")):
        if _is_run_file(run_dir, path):
            rel = path.relative_to(run_dir).as_posix()
            files.append(
                {
                    "name": rel,
                    "suffix": path.suffix.lower(),
                    "size_bytes": path.stat().st_size,
                    "modified_at": _utc_mtime(path),
                }
            )
    return files


def _baseline_policies(run_dir: Path) -> List[str]:
    policies = []
    for child in sorted(run_dir.iterdir()):
        if child.is_dir() and any((child / file_name).is_file() for file_name in ("actions.csv", "trades.csv", "equity.csv", "episodes.csv")):
            policies.append(child.name)
    return policies


def _run_record(run_dir: Path) -> Dict[str, Any]:
    artifact_type = _detect_artifact_type(run_dir)
    summary = _find_json_summary(run_dir, artifact_type)
    return {
        "name": run_dir.name,
        "artifact_type": artifact_type,
        "modified_at": _utc_mtime(run_dir),
        "summary": summary,
        "strategy_context": build_strategy_context(artifact_type, summary),
        "policies": _baseline_policies(run_dir) if artifact_type == "baseline" else [],
    }


def iter_run_dirs() -> Iterable[Path]:
    seen = set()
    for root in _files.RL_RUN_ROOTS:
        root = Path(root)
        if not root.is_dir():
            continue
        for child in _candidate_run_dirs(root):
            if child.name not in seen and _is_relative_to_root(child, root):
                seen.add(child.name)
                yield child


def _candidate_run_dirs(root: Path) -> Iterable[Path]:
    for child in root.iterdir():
        if not child.is_dir():
            continue
        nested_runs = _nested_run_dirs(child)
        if nested_runs:
            yield from nested_runs
        elif _detect_artifact_type(child) != "unknown":
            yield child


def _nested_run_dirs(parent: Path) -> List[Path]:
    return [
        grandchild
        for grandchild in parent.iterdir()
        if grandchild.is_dir() and _detect_artifact_type(grandchild) != "unknown"
    ]


def list_rl_runs(limit: int = 50) -> List[Dict[str, Any]]:
    """List available independent RL runtime artifact directories."""

    runs = sorted(iter_run_dirs(), key=lambda path: path.stat().st_mtime, reverse=True)
    return [_run_record(path) for path in runs[: max(0, int(limit))]]


def resolve_run_dir(run_name: str) -> Path:
    safe_name = _safe_direct_child_name(run_name, label="run")
    for root in _files.RL_RUN_ROOTS:
        root_path = Path(root)
        candidate = root_path / safe_name
        if candidate.is_dir() and not _nested_run_dirs(candidate):
            if not _is_relative_to_root(candidate, root_path):
                raise RlDashboardPathError(f"Invalid run: resolved path escapes RL root: {run_name!r}")
            return candidate
        for child in root_path.iterdir() if root_path.is_dir() else []:
            nested = child / safe_name
            if nested.is_dir() and _is_relative_to_root(nested, root_path):
                return nested
    raise FileNotFoundError(f"RL run not found: {run_name}")


def load_rl_run(run_name: str) -> Dict[str, Any]:
    """Load a run detail payload without reading large CSV tables."""

    run_dir = resolve_run_dir(run_name)
    artifact_type = _detect_artifact_type(run_dir)
    payload: Dict[str, Any] = {
        **_run_record(run_dir),
        "artifacts": _artifact_files(run_dir),
    }
    if artifact_type == "orderbook_rl_readiness":
        payload["detail"] = _read_run_json(run_dir, run_dir / "orderbook_rl_readiness_summary.json")
        payload["model"] = {
            "model_type": "marketable_only_orderbook_rl_environment",
            "feature_columns": payload["detail"].get("observation_features", []),
            "train_summary": payload.get("summary", {}),
        }
    elif artifact_type == "portfolio_paper":
        signature = _read_run_json(run_dir, run_dir / "portfolio_paper_summary.json")
        wf_report_path = run_dir / "portfolio_walk_forward_report.json"
        walk_forward = _read_run_json(run_dir, wf_report_path) if _is_run_file(run_dir, wf_report_path) else {}
        risk_path = run_dir / "risk_triggers.json"
        risk_payload = _read_run_json(run_dir, risk_path) if _is_run_file(run_dir, risk_path) else {}
        risk_triggers = risk_payload.get("risk_triggers", []) if isinstance(risk_payload, dict) else []
        risk_reasons: Dict[str, int] = {}
        for trigger in risk_triggers if isinstance(risk_triggers, list) else []:
            reason = str(trigger.get("reason", "unknown")) if isinstance(trigger, Mapping) else "unknown"
            risk_reasons[reason] = risk_reasons.get(reason, 0) + 1
        payload["detail"] = {
            "summary": signature.get("summary", {}),
            "config": signature.get("config", {}),
            "walk_forward_summary": walk_forward.get("summary", signature.get("walk_forward_summary", {})),
            "risk_trigger_reasons": risk_reasons,
            "risk_trigger_sample": risk_triggers[:20] if isinstance(risk_triggers, list) else [],
        }
    elif artifact_type == "performance_leaderboard":
        payload["detail"] = _read_run_json(run_dir, run_dir / "performance_leaderboard.json")
    elif artifact_type == "sb3_smoke":
        payload["detail"] = _read_run_json(run_dir, run_dir / "sb3_smoke_summary.json")
        live_summary = payload["detail"].get("live_events")
        if not isinstance(live_summary, dict):
            for file_name in LIVE_SUMMARY_FILE_NAMES:
                summary_path = run_dir / file_name
                if _is_run_file(run_dir, summary_path):
                    live_summary = _read_run_json(run_dir, summary_path)
                    break
        if isinstance(live_summary, dict):
            payload["live_events"] = live_summary
        models = payload["detail"].get("models", [])
        best_model = payload["summary"].get("best_model")
        selected_model = next((row for row in models if row.get("model") == best_model), models[0] if models else {})
        payload["model"] = {
            "model_type": f"stable_baselines3_{selected_model.get('algorithm', 'sb3')}",
            "feature_columns": payload["summary"].get("feature_columns", []),
            "train_summary": selected_model,
        }
    elif artifact_type == "contextual_bandit":
        payload["detail"] = _read_run_json(run_dir, run_dir / "eval_summary.json")
        model_path = run_dir / "model.json"
        if _is_run_file(run_dir, model_path):
            model_payload = _read_run_json(run_dir, model_path)
            model = model_payload.get("model", {})
            payload["model"] = {
                "model_type": model.get("model_type"),
                "feature_columns": model.get("feature_columns", []),
                "train_summary": model.get("train_summary", {}),
            }
    elif artifact_type == "cost_gate":
        payload["detail"] = _read_run_json(run_dir, run_dir / "cost_gate_report.json")
    elif artifact_type == "baseline":
        payload["detail"] = _read_run_json(run_dir, run_dir / "baseline_summary.json")
    elif artifact_type == "episode_manifest":
        manifest = _read_run_json(run_dir, run_dir / "episode_manifest.json")
        payload["detail"] = {"summary": manifest.get("summary", {}), "episode_sample": manifest.get("episodes", [])[:10]}
    elif artifact_type == "opening_30m_rule_filter":
        payload["detail"] = _read_run_json(run_dir, run_dir / "opening_rule_filter_summary.json")
    elif artifact_type == "opening_30m_rl_workflow":
        payload["detail"] = load_opening_workflow_detail(run_dir)
    return payload
