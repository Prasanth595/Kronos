"""Stage runner for the opening 30-minute RL workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd  # noqa: PANDAS_OK - STOM opening workflow stages use pandas frames

from .opening_30m_rl_baselines import OpeningBaselineConfig, OpeningBaselineError, evaluate_opening_baselines
from .opening_30m_rl_context import CANONICAL_FEATURE_GROUPS, OPENING_RL_CONTEXT_FEATURE_NAMES
from .opening_30m_rl_env_contract import OpeningEnvContractError, build_opening_env_contract_stage
from .opening_30m_rl_manifest import OpeningEpisodeManifestConfig, OpeningManifestError, build_opening_episode_manifest
from .opening_30m_rl_workflow import OpeningWorkflowConfig, build_opening_workflow_manifest, record_workflow_stage
from .orderbook_persistence import OrderbookPersistenceError, write_orderbook_persistence_artifact
from .participant_pressure_features import ParticipantPressureError, build_participant_pressure_readiness


FEATURE_GROUPS = list(CANONICAL_FEATURE_GROUPS)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _stage(name: str, status: str, evidence: str, reason: str = "") -> dict[str, Any]:
    return {"stage": name, "status": status, "evidence": evidence, "reason": reason}


def _stage_status(payload: Mapping[str, Any], name: str) -> str:
    for stage in payload["stages"]:
        if stage["name"] == name:
            return str(stage["status"])
    return "missing"


def _record(payload: Mapping[str, Any], name: str, result: Mapping[str, Any]) -> dict[str, Any]:
    updated = record_workflow_stage(payload, name, result)
    evidence = list(updated.get("evidence", []))
    evidence_path = str(result.get("evidence", ""))
    if evidence_path and evidence_path not in evidence:
        evidence.append(evidence_path)
    updated["evidence"] = evidence
    return updated


def _block_pending(payload: Mapping[str, Any], stages: Sequence[str], reason: str) -> dict[str, Any]:
    updated = dict(payload)
    for stage_name in stages:
        if _stage_status(updated, stage_name) == "pending":
            updated = _record(updated, stage_name, _stage(stage_name, "blocked", "", reason))
    return updated


def _skip_pending(payload: Mapping[str, Any], stages: Sequence[str], reason: str) -> dict[str, Any]:
    updated = dict(payload)
    for stage_name in stages:
        if _stage_status(updated, stage_name) == "pending":
            updated = _record(updated, stage_name, _stage(stage_name, "skipped", "", reason))
    return updated


def _write_baseline(output_dir: Path, baseline: Mapping[str, Any]) -> str:
    summary_path = output_dir / "baseline" / "opening_baseline_summary.json"
    _write_json(summary_path, baseline)
    return str(summary_path)


def _base_payload(config: OpeningWorkflowConfig) -> dict[str, Any]:
    payload = build_opening_workflow_manifest(config)
    payload["feature_groups"] = list(FEATURE_GROUPS)
    payload["proxy_availability"] = {}
    payload["missing_proxy_columns"] = []
    payload["participant_study_artifacts"] = {}
    payload["feature_ablation_results"] = {}
    payload["participant_context_version"] = "market_participant_proxy_v1"
    payload["opening_rl_context_feature_names"] = list(OPENING_RL_CONTEXT_FEATURE_NAMES)
    return payload


def _run_manifest_stage(
    payload: Mapping[str, Any],
    frames: Sequence[pd.DataFrame],
    output_dir: Path,
) -> dict[str, Any]:
    manifest = build_opening_episode_manifest(
        frames,
        OpeningEpisodeManifestConfig(output_dir=output_dir / "episodes"),
    )
    evidence = str(output_dir / "episodes" / "opening_episode_manifest_summary.json")
    result = _stage("manifest", "passed", evidence) | {
        "artifact_type": manifest["artifact_type"],
        "episode_count": manifest["summary"]["episode_count"],
        "artifacts": manifest["artifacts"],
    }
    return _record(payload, "manifest", result)


def _run_participant_stage(
    payload: Mapping[str, Any],
    frames: Sequence[pd.DataFrame],
    output_dir: Path,
) -> dict[str, Any]:
    participant = build_participant_pressure_readiness(
        frames[0],
        output_dir=output_dir / "participant_pressure",
        decision_second=min(3, len(frames[0]) - 1),
    )
    evidence = participant["artifacts"]["summary_json"]
    result = _stage("participant_pressure", "passed", evidence) | {
        "artifact_type": participant["artifact_type"],
        "proxy_availability": participant["proxy_availability"],
        "missing_proxy_columns": participant["missing_proxy_columns"],
    }
    updated = _record(payload, "participant_pressure", result)
    updated["proxy_availability"] = participant["proxy_availability"]
    updated["missing_proxy_columns"] = participant["missing_proxy_columns"]
    updated["participant_study_artifacts"] = {
        "participant_pressure_readiness_summary_json": str(evidence),
    }
    return updated


def _run_orderbook_stage(
    payload: Mapping[str, Any],
    frames: Sequence[pd.DataFrame],
    output_dir: Path,
) -> dict[str, Any]:
    orderbook = write_orderbook_persistence_artifact(
        frames[0],
        output_dir=output_dir,
        decision_second=min(3, len(frames[0]) - 1),
    )
    evidence = orderbook["artifacts"]["summary_json"]
    result = _stage("orderbook_persistence", "passed", evidence) | {
        "artifact_type": orderbook["artifact_type"],
        "score": orderbook["score"],
        "feature_groups": orderbook["feature_groups"],
        "components": orderbook["components"],
    }
    return _record(payload, "orderbook_persistence", result)


def _run_env_stage(
    payload: Mapping[str, Any],
    frames: Sequence[pd.DataFrame],
) -> dict[str, Any]:
    env_result = build_opening_env_contract_stage(frames, fixed_entry_exit_only=True)
    status = "failed" if env_result["check_env_status"] == "failed" else "passed"
    result = dict(env_result)
    result["status"] = status
    result["evidence"] = "env_contract"
    return _record(payload, "readiness_env", result)


def _run_baseline_stage(
    payload: Mapping[str, Any],
    frames: Sequence[pd.DataFrame],
    config: OpeningWorkflowConfig,
    output_dir: Path,
) -> dict[str, Any]:
    baseline = evaluate_opening_baselines(frames, OpeningBaselineConfig(cost_bps=float(config.cost_bps)))
    evidence = _write_baseline(output_dir, baseline)
    result = _stage("baseline", "passed", evidence) | {
        "artifact_type": baseline["artifact_type"],
        "summary": baseline["summary"],
    }
    return _record(payload, "baseline", result)


def _apply_training_state(
    payload: Mapping[str, Any],
    *,
    request_training: bool,
    reason: str | None,
) -> dict[str, Any]:
    if reason:
        blocked = _block_pending(payload, ("baseline", "training", "evaluation", "controls", "cost_gate", "dashboard"), reason)
        blocked["verdict"] = "NO-GO_DATA"
        return blocked
    if request_training:
        blocked = _block_pending(
            payload,
            ("training", "evaluation", "controls", "cost_gate", "dashboard"),
            "training stage waits for Task 7",
        )
        blocked["verdict"] = "PENDING_TRAINING"
        return blocked
    skipped = _skip_pending(payload, ("training",), "training flag not set")
    return _skip_pending(skipped, ("evaluation", "controls", "cost_gate", "dashboard"), "requires training output")


def run_opening_workflow_stages(
    frames: Sequence[pd.DataFrame],
    config: OpeningWorkflowConfig,
    *,
    request_training: bool = False,
) -> dict[str, Any]:
    """Run non-training opening workflow stages and write the workflow summary."""

    output_dir = Path(config.output_dir)
    payload = _base_payload(config)
    payload = _record(payload, "contract", _stage("contract", "passed", str(output_dir / "contract")))
    failure_reason: str | None = None
    try:
        payload = _run_manifest_stage(payload, frames, output_dir)
        payload = _run_participant_stage(payload, frames, output_dir)
        payload = _run_orderbook_stage(payload, frames, output_dir)
        payload = _run_env_stage(payload, frames)
        if _stage_status(payload, "readiness_env") == "failed":
            failure_reason = "NO-GO_DATA: readiness_env failed"
        if failure_reason is None:
            payload = _run_baseline_stage(payload, frames, config, output_dir)
    except (
        OpeningManifestError,
        ParticipantPressureError,
        OpeningEnvContractError,
        OpeningBaselineError,
        OrderbookPersistenceError,
        KeyError,
        ValueError,
    ) as exc:
        current = next((stage["name"] for stage in payload["stages"] if stage["status"] == "pending"), "readiness_env")
        payload = _record(payload, str(current), _stage(str(current), "failed", "", str(exc)))
        failure_reason = f"NO-GO_DATA: {current} failed: {exc}"
    payload = _apply_training_state(payload, request_training=request_training, reason=failure_reason)
    summary_path = output_dir / "opening_30m_rl_workflow_summary.json"
    payload["artifacts"]["summary_json"] = str(summary_path)
    _write_json(summary_path, payload)
    return payload
