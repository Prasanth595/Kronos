"""Summary reconciliation for opening candidate lifecycle artifacts."""

from __future__ import annotations

from typing import Mapping

from .opening_30m_rl_realdata import JsonValue


def reconcile_candidate_summary(
    payload: dict[str, object],
    training: Mapping[str, JsonValue],
    controls: Mapping[str, JsonValue],
    ablations: Mapping[str, JsonValue],
) -> None:
    """Keep dashboard summary fields consistent with candidate lifecycle evidence."""

    candidates = [row for row in training.get("candidates", []) if isinstance(row, dict)]
    trained_count = sum(1 for row in candidates if str(row.get("status")) == "trained")
    candidate_verdict = payload.get("candidate_verdict")
    if candidate_verdict:
        payload["workflow_verdict"] = payload.get("verdict")
        payload["verdict"] = candidate_verdict
    realdata = payload.get("realdata", {})
    if isinstance(realdata, dict):
        realdata["verdict"] = candidate_verdict or realdata.get("verdict", "INCONCLUSIVE")
        realdata["training_status"] = "candidate_tiny_train_complete" if trained_count else "candidate_training_not_completed"
        realdata["model_status"] = "candidate_models_trained_research_only" if trained_count else "no_model_trained"
    stage_results = payload.get("stage_results", {})
    if isinstance(stage_results, dict):
        stage_results["training"] = _stage("training", "passed" if trained_count else "skipped", candidate_count=len(candidates), trained_count=trained_count)
        stage_results["evaluation"] = _stage("evaluation", "passed" if trained_count else "skipped", candidate_count=len(candidates))
        stage_results["controls"] = _stage("controls", "passed" if controls.get("negative_control_passed") else "blocked", verdict=controls.get("verdict"))
        stage_results["cost_gate"] = _stage("cost_gate", "blocked", verdict=payload.get("candidate_verdict"))
        stage_results["dashboard"] = _stage("dashboard", "passed", candidate_count=len(candidates))
        stage_results["feature_ablation"] = _stage("feature_ablation", "passed" if ablations.get("feature_ablation_passed") else "blocked", verdict=ablations.get("verdict"))
    _update_stage_list(payload, stage_results)


def _stage(name: str, status: str, **values: object) -> dict[str, object]:
    return {"stage": name, "status": status, **values}


def _update_stage_list(payload: dict[str, object], stage_results: object) -> None:
    stages = payload.get("stages")
    if not isinstance(stages, list) or not isinstance(stage_results, dict):
        return
    seen: set[str] = set()
    for stage in stages:
        if isinstance(stage, dict):
            name = str(stage.get("name", ""))
            seen.add(name)
        if isinstance(stage, dict) and stage.get("name") in {"training", "evaluation", "controls", "cost_gate", "dashboard", "feature_ablation"}:
            result = stage_results.get(stage["name"], {})
            if isinstance(result, dict):
                stage["status"] = str(result.get("status", stage.get("status", "")))
                stage["evidence"] = "candidate_lifecycle"
    for name in ("feature_ablation",):
        result = stage_results.get(name, {})
        if name not in seen and isinstance(result, dict):
            stages.append({"name": name, "status": str(result.get("status", "")), "evidence": "candidate_lifecycle"})
