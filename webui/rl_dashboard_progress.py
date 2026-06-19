"""Page-progress synthesis for the STOM RL dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from .rl_dashboard_files import _int_or_zero, _repo_path
    from .rl_dashboard_runs import list_rl_runs, load_rl_run
except ImportError:  # pragma: no cover
    from rl_dashboard_files import _int_or_zero, _repo_path
    from rl_dashboard_runs import list_rl_runs, load_rl_run

def _criteria_progress(criteria: Sequence[Tuple[str, bool, str]]) -> Tuple[int, List[Dict[str, Any]]]:
    rows = [{"label": label, "passed": bool(passed), "evidence": evidence} for label, passed, evidence in criteria]
    if not rows:
        return 0, rows
    passed_count = sum(1 for row in rows if row["passed"])
    return int(round((passed_count / len(rows)) * 100)), rows


def _latest_sb3_details() -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    details: List[Dict[str, Any]] = []
    for run in list_rl_runs(limit=200):
        if run.get("artifact_type") != "sb3_smoke":
            continue
        try:
            detail = load_rl_run(str(run["name"]))
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            continue
        models = detail.get("detail", {}).get("models", [])
        max_timesteps = max((_int_or_zero(row.get("training_timesteps")) for row in models), default=0)
        detail["max_training_timesteps"] = max_timesteps
        details.append(detail)
    details.sort(key=lambda row: int(row.get("max_training_timesteps") or 0), reverse=True)
    return details, details[0] if details else None


def _latest_opening_workflow(runs: Sequence[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    for run in runs:
        if run.get("artifact_type") != "opening_30m_rl_workflow":
            continue
        try:
            return load_rl_run(str(run["name"]))
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            continue
    return None


def _has_model_file(detail: Optional[Mapping[str, Any]], algorithm: str) -> bool:
    if not detail:
        return False
    model_files = detail.get("detail", {}).get("artifacts", {}).get("model_files", {})
    path = model_files.get(algorithm) if isinstance(model_files, dict) else None
    return bool(path and _repo_path(str(path)).is_file())


def _opening_stage(detail: Mapping[str, Any], stage_name: str) -> Mapping[str, Any]:
    stages = detail.get("detail", {}).get("stages", [])
    if not isinstance(stages, list):
        return {}
    return next((stage for stage in stages if isinstance(stage, Mapping) and stage.get("name") == stage_name), {})


def _opening_stage_criterion(detail: Mapping[str, Any], stage_name: str, label: str) -> Tuple[str, bool, str]:
    stage = _opening_stage(detail, stage_name)
    status = str(stage.get("status", "missing")).lower()
    evidence = str(stage.get("evidence", "") or "-")
    reason = str(stage.get("reason", "") or "")
    passed = status in {"complete", "completed", "passed"}
    evidence_text = f"{status} | {evidence}" if not reason else f"{status} | {evidence} | {reason}"
    return label, passed, evidence_text


def _opening_workflow_page(detail: Mapping[str, Any]) -> Tuple[str, List[Tuple[str, bool, str]]]:
    cost_stage = _opening_stage_criterion(detail, "cost_gate", "opening cost gate")
    cost_status, cost_evidence = cost_stage[1], cost_stage[2]
    leaderboard_passed = cost_status and "leaderboard" in cost_evidence.lower()
    return (
        "Opening 30M RL Workflow",
        [
            _opening_stage_criterion(detail, "contract", "opening contract"),
            _opening_stage_criterion(detail, "manifest", "opening manifest"),
            _opening_stage_criterion(detail, "readiness_env", "opening env/readiness"),
            _opening_stage_criterion(detail, "baseline", "opening baseline"),
            _opening_stage_criterion(detail, "training", "opening training"),
            _opening_stage_criterion(detail, "evaluation", "opening evaluation"),
            _opening_stage_criterion(detail, "controls", "opening controls"),
            cost_stage,
            ("opening leaderboard", leaderboard_passed, cost_evidence),
            _opening_stage_criterion(detail, "dashboard", "opening dashboard"),
        ],
    )


def load_rl_progress() -> Dict[str, Any]:
    """Return page-level STOM RL completion progress for the dashboard."""

    runs = list_rl_runs(limit=200)
    run_types = {str(run.get("artifact_type")) for run in runs}
    run_names = {str(run.get("name")) for run in runs}
    sb3_details, latest_sb3 = _latest_sb3_details()
    latest_sb3_summary = latest_sb3.get("summary", {}) if latest_sb3 else {}
    latest_models = latest_sb3.get("detail", {}).get("models", []) if latest_sb3 else []
    latest_algorithms = {str(row.get("algorithm")) for row in latest_models}
    max_timesteps = _int_or_zero(latest_sb3.get("max_training_timesteps")) if latest_sb3 else 0

    leaderboard_detail = next((run for run in runs if run.get("artifact_type") == "performance_leaderboard"), None)
    leaderboard_payload: Dict[str, Any] = {}
    leaderboard_rows: List[Dict[str, Any]] = []
    if leaderboard_detail:
        try:
            leaderboard_payload = load_rl_run(str(leaderboard_detail["name"]))
            leaderboard_rows = list(leaderboard_payload.get("detail", {}).get("leaderboard", []))
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            leaderboard_payload = {}
            leaderboard_rows = []
    leaderboard_models = {str(row.get("model")) for row in leaderboard_rows}
    latest_opening = _latest_opening_workflow(runs)

    docs_ready = _repo_path("docs/stom_rl_realtime_learning_dashboard_implementation_2026-05-23.md").is_file()
    completion_doc_ready = _repo_path("docs/stom_rl_page100_completion_report_2026-05-24.md").is_file()

    page_specs = [
        (
            "RL Trading 개요",
            [
                ("run 목록 조회", bool(runs), f"{len(runs)} runs"),
                ("baseline/contextual/cost/SB3/leaderboard 유형", {"baseline", "contextual_bandit", "cost_gate", "sb3_smoke", "performance_leaderboard"}.issubset(run_types), ",".join(sorted(run_types))),
                ("상세 artifact 조회", bool(leaderboard_payload or latest_sb3), "load_rl_run available"),
            ],
        ),
        (
            "실시간 RL",
            [
                ("live event log", int(latest_sb3_summary.get("live_event_count") or 0) > 0, str(latest_sb3_summary.get("live_event_count") or 0)),
                ("DQN/PPO event", {"dqn", "ppo"}.issubset(latest_algorithms), ",".join(sorted(latest_algorithms))),
                ("50k short run", max_timesteps >= 50_000, str(max_timesteps)),
            ],
        ),
        (
            "실제 딥러닝 학습",
            [
                ("check_env 통과", bool(latest_sb3_summary.get("check_env_passed")), str(latest_sb3_summary.get("check_env_passed"))),
                ("CUDA 학습 확인", bool(latest_sb3_summary.get("cuda_available")), str(latest_sb3_summary.get("cuda_available"))),
                ("DQN/PPO 모델 파일", _has_model_file(latest_sb3, "dqn") and _has_model_file(latest_sb3, "ppo"), latest_sb3.get("name", "-") if latest_sb3 else "-"),
            ],
        ),
        (
            "Performance Leaderboard",
            [
                ("leaderboard artifact", "performance_leaderboard" in run_types, leaderboard_detail.get("name", "-") if leaderboard_detail else "-"),
                ("DQN/PPO short 모델 반영", {"dqn_50k", "ppo_50k"}.issubset(leaderboard_models), ",".join(sorted(leaderboard_models))),
                ("row count", int(leaderboard_payload.get("summary", {}).get("row_count") or len(leaderboard_rows)) >= 10, str(len(leaderboard_rows))),
            ],
        ),
        (
            "Artifacts / Models",
            [
                ("summary/csv/jsonl", bool(latest_sb3 and {"sb3_smoke_summary.json", "sb3_smoke_summary.csv", "rl_live_events.jsonl"}.issubset({Path(row.get("name", "")).name for row in latest_sb3.get("artifacts", [])})), latest_sb3.get("name", "-") if latest_sb3 else "-"),
                ("DQN zip", _has_model_file(latest_sb3, "dqn"), "dqn_model.zip"),
                ("PPO zip", _has_model_file(latest_sb3, "ppo"), "ppo_model.zip"),
            ],
        ),
        (
            "Docs / 운영 경계",
            [
                ("구현 문서", docs_ready, "implementation doc"),
                ("완료 보고 문서", completion_doc_ready, "page100 report"),
                ("실주문 분리", True, "read-only historical replay / smoke-short training"),
            ],
        ),
    ]
    if latest_opening:
        page_specs.append(_opening_workflow_page(latest_opening))

    pages: List[Dict[str, Any]] = []
    for page, criteria in page_specs:
        progress_pct, criteria_rows = _criteria_progress(criteria)
        pages.append(
            {
                "page": page,
                "progress_pct": progress_pct,
                "status": "complete" if progress_pct == 100 else "in_progress",
                "criteria": criteria_rows,
            }
        )

    overall_progress = int(round(sum(int(page["progress_pct"]) for page in pages) / len(pages))) if pages else 0
    return {
        "mode": "stom_rl_page_progress",
        "overall_progress_pct": overall_progress,
        "status": "complete" if overall_progress == 100 else "in_progress",
        "pages": pages,
        "evidence": {
            "run_count": len(runs),
            "run_names": sorted(run_names),
            "latest_sb3_run": latest_sb3.get("name") if latest_sb3 else None,
            "latest_opening_workflow_run": latest_opening.get("name") if latest_opening else None,
            "latest_opening_workflow_verdict": latest_opening.get("summary", {}).get("verdict") if latest_opening else None,
            "max_sb3_training_timesteps": max_timesteps,
            "leaderboard_models": sorted(leaderboard_models),
        },
    }
