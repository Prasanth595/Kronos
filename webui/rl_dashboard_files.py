"""Path-safe file and CSV helpers for STOM RL dashboard artifacts."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
WEBUI_ROOT = Path(__file__).resolve().parent
RL_RUN_ROOTS = [WEBUI_ROOT / "rl_runs"]
MAX_TABLE_LIMIT = 5000


ARTIFACT_SIGNATURES = (
    ("opening_30m_rule_filter", "opening_rule_filter_summary.json"),
    ("opening_30m_rl_workflow", "opening_30m_rl_workflow_summary.json"),
    ("orderbook_rl_readiness", "orderbook_rl_readiness_summary.json"),
    ("portfolio_paper", "portfolio_paper_summary.json"),
    ("performance_leaderboard", "performance_leaderboard.json"),
    ("sb3_smoke", "sb3_smoke_summary.json"),
    ("contextual_bandit", "eval_summary.json"),
    ("cost_gate", "cost_gate_report.json"),
    ("baseline", "baseline_summary.json"),
    ("episode_manifest", "episode_manifest.json"),
)

TABLE_ALIASES = {
    "action": "actions",
    "actions": "actions",
    "trade": "trades",
    "trades": "trades",
    "equity": "equity",
    "equity_curve": "equity",
    "episodes": "episodes",
    "episode": "episodes",
    "summary": "summary",
    "manifest": "manifest",
    "scenario": "scenario",
    "scenarios": "scenario",
    "rolling": "rolling",
    "folds": "rolling",
    "gate": "gate",
    "cost_gate": "gate",
    "leaderboard": "leaderboard",
    "performance": "leaderboard",
    "performance_leaderboard": "leaderboard",
    "nav": "nav",
    "nav_curve": "nav",
    "decision": "decisions",
    "decisions": "decisions",
    "position": "decisions",
    "positions": "decisions",
    "candidate": "candidates",
    "candidates": "candidates",
    "portfolio_fold": "portfolio_folds",
    "portfolio_folds": "portfolio_folds",
    "event": "events",
    "events": "events",
    "live": "events",
    "live_events": "events",
    "stage": "stages",
    "stages": "stages",
    "workflow_stage": "stages",
    "workflow_stages": "stages",
    "control": "controls",
    "controls": "controls",
    "negative_control": "controls",
    "negative_controls": "controls",
    "proxy": "proxy_availability",
    "proxy_availability": "proxy_availability",
    "participant_proxy": "proxy_availability",
    "participant_study": "participant_study_groups",
    "participant_studies": "participant_study_groups",
    "participant_study_group": "participant_study_groups",
    "participant_study_groups": "participant_study_groups",
    "participant_study_episode": "participant_study_episodes",
    "participant_study_episodes": "participant_study_episodes",
    "orderbook_persistence": "orderbook_persistence",
    "orderbook_persistence_score": "orderbook_persistence",
    "feature_ablation": "feature_ablation",
    "feature_ablations": "feature_ablation",
    "candidate_lifecycle": "candidate_lifecycle",
    "candidate_splits": "candidate_splits",
    "candidate_controls": "candidate_controls",
    "candidate_ablations": "candidate_ablations",
    "candidate_feature_ablation": "candidate_feature_ablation",
    "candidate_equity_curve": "candidate_equity_curve",
    "candidate_time_buckets": "candidate_time_buckets",
    "candidate_failure_reasons": "candidate_failure_reasons",
    "context_feature_sample": "context_feature_sample",
    "context_features": "context_feature_sample",
    "rule_filter_lifecycle": "rule_filter_lifecycle",
    "rule_filter_splits": "rule_filter_splits",
    "rule_filter_controls": "rule_filter_controls",
    "rule_filter_ablations": "rule_filter_ablations",
    "rule_filter_equity_curve": "rule_filter_equity_curve",
    "rule_filter_time_buckets": "rule_filter_time_buckets",
    "rule_filter_failure_reasons": "rule_filter_failure_reasons",
    "rule_filter_opportunity_cost": "rule_filter_opportunity_cost",
    "rule_filter_proxy_availability": "rule_filter_proxy_availability",
    "rule_filter_orderbook_persistence": "rule_filter_orderbook_persistence",
    "rule_filter_context_sample": "rule_filter_context_sample",
    "orderbook_readiness": "orderbook_readiness",
    "orderbook-readiness": "orderbook_readiness",
    "readiness": "orderbook_readiness",
}

ROOT_TABLE_CANDIDATES = {
    "actions": ("actions.csv",),
    "trades": ("trades.csv",),
    "equity": ("equity_curve.csv", "equity.csv"),
    "episodes": ("episodes.csv",),
    "summary": ("summary.csv", "sb3_smoke_summary.csv", "baseline_summary.csv", "gate_summary.csv"),
    "manifest": ("episode_manifest.csv",),
    "scenario": ("scenario_summary.csv",),
    "rolling": ("rolling_folds.csv",),
    "gate": ("gate_summary.csv",),
    "leaderboard": ("opening_leaderboard.csv", "performance_leaderboard.csv", "leaderboard.csv"),
    "controls": ("controls.csv", "opening_controls.csv", "negative_controls.csv"),
    "participant_study_groups": ("market_participant_study_groups.csv",),
    "participant_study_episodes": ("market_participant_study_episodes.csv",),
    "nav": ("nav.csv",),
    "decisions": ("decisions.csv",),
    "candidates": ("candidates.csv",),
    "portfolio_folds": ("portfolio_walk_forward_folds.csv",),
    "orderbook_readiness": ("orderbook_rl_readiness.csv",),
}

LIVE_EVENT_FILE_NAMES = ("rl_live_events.jsonl", "live_events.jsonl", "events.jsonl")
LIVE_SUMMARY_FILE_NAMES = ("rl_live_summary.json", "live_summary.json")


class RlDashboardPathError(ValueError):
    """Raised when a dashboard artifact path escapes its read-only boundary."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


def _safe_direct_child_name(name: str, *, label: str) -> str:
    value = str(name or "").strip()
    if not value:
        raise RlDashboardPathError(f"{label} is required")
    path = Path(value)
    if path.is_absolute() or value in {".", ".."} or any(part in {"", ".", ".."} for part in path.parts):
        raise RlDashboardPathError(f"Invalid {label}: {name!r}")
    if "/" in value or "\\" in value:
        raise RlDashboardPathError(f"{label} must be a direct child name: {name!r}")
    return value


def _utc_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _ensure_run_path(run_dir: Path, path: Path, *, label: str) -> Path:
    run_resolved = run_dir.resolve()
    path_resolved = path.resolve()
    if path_resolved != run_resolved and run_resolved not in path_resolved.parents:
        raise RlDashboardPathError(f"{label} resolves outside RL run: {path.name!r}")
    return path


def _is_run_file(run_dir: Path, path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        _ensure_run_path(run_dir, path, label="RL artifact file")
    except ValueError:
        return False
    return True


def _read_run_json(run_dir: Path, path: Path) -> Dict[str, Any]:
    return _read_json(_ensure_run_path(run_dir, path, label="RL JSON artifact"))


def _read_run_csv_rows(run_dir: Path, path: Path, *, limit: int) -> Tuple[List[Dict[str, Any]], bool]:
    return _read_csv_rows(_ensure_run_path(run_dir, path, label="RL CSV artifact"), limit=limit)


def _repo_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def _coerce_scalar(value: str) -> Any:
    if value == "":
        return None
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    # Preserve zero-padded codes (e.g. Korean stock symbol ``000250``) as strings:
    # coercing to int would strip the leading zeros and display ``250``.
    if len(value) > 1 and value[0] == "0" and value.isdigit():
        return value
    if len(value) > 1 and value[0] == "0" and all(ch.isdigit() or ch == "_" for ch in value):
        return value
    try:
        if any(ch in value for ch in (".", "e", "E")):
            return float(value)
        return int(value)
    except ValueError:
        return value


def _float_or_zero(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int_or_zero(value: Any) -> int:
    return int(_float_or_zero(value))


def _read_csv_rows(path: Path, *, limit: int) -> Tuple[List[Dict[str, Any]], bool]:
    limit = max(0, min(int(limit), MAX_TABLE_LIMIT))
    rows: List[Dict[str, Any]] = []
    truncated = False
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            if idx >= limit:
                truncated = True
                break
            rows.append({key: _coerce_scalar(value) for key, value in row.items()})
    return rows, truncated


def _is_relative_to_root(candidate: Path, root: Path) -> bool:
    root_resolved = root.resolve()
    candidate_resolved = candidate.resolve()
    return candidate_resolved == root_resolved or root_resolved in candidate_resolved.parents
