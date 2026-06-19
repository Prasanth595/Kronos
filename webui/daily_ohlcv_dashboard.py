"""Read-only dashboard adapter for daily OHLCV D0-D9 evidence surfaces."""

from __future__ import annotations

import csv
import json
import hashlib
import math
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from stom_rl.daily_ohlcv_db import (
    DEFAULT_ARTIFACT_ROOT as DB_SUMMARY_ROOT,
    DECISION_GRADE_RETURN_STATUS,
    PRICE_BASIS_ALLOWED_USES,
    PRICE_BASIS_BLOCKED_USES,
    PRICE_BASIS_REQUIRED_EVIDENCE,
    PRICE_BASIS_USER_GUIDANCE,
    PRICE_BASIS,
    PRICE_BASIS_STATUS,
    summarize_daily_db,
    summarize_symbol,
)
from stom_rl.daily_ohlcv_universe import (
    DEFAULT_OFFICIAL_METADATA_PATH,
    DEFAULT_UNIVERSE_ROOT,
    OFFICIAL_METADATA_REQUIRED_COLUMNS,
    UNIVERSE_ALLOWED_USES_WHEN_WATCH,
    UNIVERSE_BLOCKED_USES_WHEN_WATCH,
    UNIVERSE_REQUIRED_EVIDENCE,
    UNIVERSE_USER_GUIDANCE,
    build_universe_manifest,
)
from stom_rl.daily_ohlcv_dataset import (
    DATASET_ALLOWED_USES_WITH_UPSTREAM_BLOCKERS,
    DATASET_BLOCKED_USES_WITH_UPSTREAM_BLOCKERS,
    DATASET_REQUIRED_EVIDENCE,
    DATASET_USER_GUIDANCE,
    DEFAULT_DATASET_ROOT,
)
from stom_rl.daily_prediction import DEFAULT_PREDICTION_ROOT, D3_ALLOWED_USES_WHEN_WATCH, D3_BLOCKED_USES_WHEN_WATCH, D3_REQUIRED_EVIDENCE, D3_USER_GUIDANCE
from stom_rl.daily_rl_train import DEFAULT_PORTFOLIO_ROOT
from stom_rl.daily_walk_forward import DEFAULT_WALK_FORWARD_ROOT
from stom_rl.daily_registry import DEFAULT_DAILY_REGISTRY_ROOT
from stom_rl.daily_portfolio_env import environment_contract
from stom_rl.daily_scenario_runner import DEFAULT_SCENARIO_ROOT, RESEARCH_GUARDRAIL
from stom_rl.daily_scenario_batch import DEFAULT_SCENARIO_BATCH_ROOT

SAFE_RUN_RE = re.compile(r"^[0-9A-Za-z_.-]+$")
DEFAULT_SIGNAL_QUALITY_ROOT = Path("webui/rl_runs/daily_ohlcv_signal_quality")
DEFAULT_SIGNAL_QUALITY_BATCH_ROOT = Path("webui/rl_runs/daily_ohlcv_signal_quality_batches")
LATEST_SIGNAL_QUALITY_RESULT_DOC = Path("docs/stom_daily_ohlcv_d3_d4_signal_quality_audit_result_2026-06-18.md")
LATEST_RESEARCH_GOVERNANCE_INDEX = Path("docs/stom_daily_ohlcv_research_governance_index_2026-06-18.md")
DEFAULT_RESEARCH_INTENT_ROOT = Path("webui/rl_runs/daily_ohlcv_research_intents")
DEFAULT_REJECTION_AUDIT_ROOT = Path("webui/rl_runs/daily_ohlcv_rejection_audit")
MAX_LIMIT = 5000


def _bounded_limit(value: Any, *, default: int = 100, maximum: int = MAX_LIMIT) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0, min(parsed, maximum))


def _safe_run_id(run_id: str | None) -> str | None:
    if not run_id:
        return None
    if not SAFE_RUN_RE.match(run_id) or run_id in {".", ".."} or ".." in run_id.split("."):
        raise ValueError("Unsafe daily OHLCV artifact run id")
    return run_id


def _is_scenario_generated_run_dir(path: Path) -> bool:
    run_id = path.name
    if run_id.startswith("scenario_") or "__" in run_id:
        return True
    try:
        scenario_manifest = (DEFAULT_SCENARIO_ROOT / run_id / "scenario_manifest.json").resolve()
        scenario_manifest.relative_to(DEFAULT_SCENARIO_ROOT.resolve())
    except (ValueError, OSError):
        return False
    return scenario_manifest.is_file()


def _latest_run_dir(root: Path, *, required_file: str, run_id: str | None = None) -> Path | None:
    root = root.resolve()
    if run_id:
        candidate = (root / _safe_run_id(run_id)).resolve()
        candidate.relative_to(root)
        if (candidate / required_file).exists():
            return candidate
        raise FileNotFoundError(run_id)
    if not root.exists():
        return None
    candidates = [
        path
        for path in root.iterdir()
        if path.is_dir() and (path / required_file).exists() and not _is_scenario_generated_run_dir(path)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p / required_file).stat().st_mtime)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_artifact_dir(root: Path, *, required_file: str) -> Path | None:
    root = root.resolve()
    if not root.exists():
        return None
    candidates = [path for path in root.iterdir() if path.is_dir() and (path / required_file).exists()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p / required_file).stat().st_mtime)


def _load_json_if_exists(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        return _load_json(path)
    except (OSError, json.JSONDecodeError):
        return {}


def _path_text(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _read_csv_rows(path: Path, limit: int) -> list[dict[str, Any]]:
    safe_limit = _bounded_limit(limit, default=100, maximum=MAX_LIMIT)
    if safe_limit == 0 or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(dict(row))
            if len(rows) >= safe_limit:
                break
    return rows


def _limit_list(payload: dict[str, Any], key: str, limit: int) -> None:
    rows = payload.get(key)
    if isinstance(rows, list):
        payload[f"{key}_total"] = len(rows)
        payload[f"{key}_truncated"] = len(rows) > limit
        payload[key] = rows[:limit]


def _to_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _status_severity(status: str | None) -> str:
    normalized = str(status or "").upper()
    if "NO-GO" in normalized or "BLOCKED" in normalized or "LOCKED" in normalized:
        return "block"
    if "WATCH" in normalized or "RESEARCH_ONLY" in normalized or "RUNNING" in normalized:
        return "watch"
    if normalized == "PASS" or normalized == "GO":
        return "pass"
    return "neutral"

PRICE_BASIS_VERIFIED_STATUSES = {
    "VERIFIED",
    "RAW_VERIFIED",
    "ADJUSTED_VERIFIED",
    "PRICE_BASIS_VERIFIED",
}
PRICE_BASIS_VERIFIED_VALUES = {"raw", "adjusted", "split_adjusted", "total_return_adjusted"}
UNIVERSE_VERIFIED_VERDICT = "OFFICIAL_OR_MANUAL_REVIEWED"
OFFICIAL_METADATA_VERIFIED_STATUS = "OFFICIAL_VERIFIED"
OFFICIAL_METADATA_COMPLETE_COVERAGE = "COMPLETE"

def _price_basis_verified(surface: dict[str, Any]) -> bool:
    price_basis = str(surface.get("price_basis") or "").lower()
    status = str(surface.get("price_basis_status") or surface.get("price_basis_review_status") or "").upper()
    decision_status = str(surface.get("decision_grade_return_status") or "")
    if price_basis not in PRICE_BASIS_VERIFIED_VALUES:
        return False
    if status not in PRICE_BASIS_VERIFIED_STATUSES:
        return False
    if decision_status.startswith("BLOCKED"):
        return False
    return True


def _universe_official_or_manual_verified(surface: dict[str, Any]) -> bool:
    verdict = str(surface.get("verdict") or "")
    review_status = surface.get("universe_review_status")
    official_status = str(surface.get("official_metadata_status") or "")
    coverage_status = str(surface.get("official_metadata_coverage_status") or "")
    certification_status = str(surface.get("universe_certification_status") or "")
    if verdict != UNIVERSE_VERIFIED_VERDICT:
        return False
    if review_status is not None and str(review_status) != UNIVERSE_VERIFIED_VERDICT:
        return False
    if official_status != OFFICIAL_METADATA_VERIFIED_STATUS:
        return False
    if coverage_status != OFFICIAL_METADATA_COMPLETE_COVERAGE:
        return False
    return certification_status == UNIVERSE_VERIFIED_VERDICT
D0_DATASET_UPSTREAM_BLOCKER = "D0_PRICE_BASIS_NOT_VERIFIED"
D1_DATASET_UPSTREAM_BLOCKER = "D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED"
D2_BLOCKED_DECISION_GRADE_STATUS = "BLOCKED_BY_UPSTREAM_D0_D1_GUARDRAILS"
D2_BLOCKED_MODEL_READINESS = "DATASET_RESEARCH_PREVIEW_BLOCKED_BY_UPSTREAM_GUARDRAILS"


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if value in (None, ""):
        return []
    return [str(value)]


def _merge_string_lists(required: list[str], *existing_groups: Any) -> list[str]:
    merged: list[str] = []
    for item in required:
        if item not in merged:
            merged.append(item)
    for group in existing_groups:
        for item in _as_string_list(group):
            if item not in merged:
                merged.append(item)
    return merged

def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _finite_int(value: Any) -> int | None:
    parsed = _finite_float(value)
    if parsed is None:
        return None
    return int(parsed)


def _positive_number(value: Any) -> bool:
    parsed = _finite_float(value)
    return parsed is not None and parsed > 0


def _current_d0_d1_surfaces() -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        db = load_daily_db_summary(table_limit=0, flag_limit=0, window_limit=0)
    except Exception:
        db = {}
    try:
        universe = load_universe_preview(limit=0)
    except Exception:
        universe = {}
    return db, universe


def _apply_current_d0_d1_guardrails(manifest: dict[str, Any]) -> None:
    db, universe = _current_d0_d1_surfaces()
    manifest["price_basis"] = db.get("price_basis", PRICE_BASIS)
    manifest["price_basis_status"] = db.get("price_basis_status", PRICE_BASIS_STATUS)
    manifest["decision_grade_return_status"] = db.get("decision_grade_return_status", DECISION_GRADE_RETURN_STATUS)
    manifest["universe_verdict"] = universe.get("verdict", "WATCH_HEURISTIC_UNIVERSE")
    manifest["universe_review_status"] = (
        universe.get("universe_review_status")
        or universe.get("review_status")
        or universe.get("verdict")
        or "WATCH_REQUIRES_OFFICIAL_OR_MANUAL_REVIEW"
    )
    manifest["official_metadata_status"] = universe.get("official_metadata_status", "MISSING")
    manifest["official_metadata_coverage_status"] = universe.get("official_metadata_coverage_status", "MISSING")
    manifest["universe_certification_status"] = universe.get(
        "universe_certification_status",
        "BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW",
    )


def _merge_guidance_rows(required: list[dict[str, Any]], existing: Any) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_sections: set[str] = set()
    for row in [*required, *(existing if isinstance(existing, list) else [])]:
        if not isinstance(row, dict):
            continue
        section = str(row.get("section") or row.get("id") or row)
        if section in seen_sections:
            continue
        seen_sections.add(section)
        merged.append(dict(row))
    return merged


def _dataset_upstream_blockers(manifest: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not _price_basis_verified(manifest):
        blockers.append(D0_DATASET_UPSTREAM_BLOCKER)
    if not _universe_official_or_manual_verified(
        {
            "verdict": manifest.get("universe_verdict"),
            "universe_review_status": manifest.get("universe_review_status"),
            "official_metadata_status": manifest.get("official_metadata_status"),
            "official_metadata_coverage_status": manifest.get("official_metadata_coverage_status"),
            "universe_certification_status": manifest.get("universe_certification_status"),
        }
    ):
        blockers.append(D1_DATASET_UPSTREAM_BLOCKER)
    return blockers


def _normalize_dataset_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    _apply_current_d0_d1_guardrails(manifest)
    upstream_blockers = _dataset_upstream_blockers(manifest)
    manifest["upstream_gate_blockers"] = _merge_string_lists(upstream_blockers, manifest.get("upstream_gate_blockers"))
    manifest.setdefault("dataset_required_evidence", list(DATASET_REQUIRED_EVIDENCE))
    manifest.setdefault("dataset_allowed_uses", list(DATASET_ALLOWED_USES_WITH_UPSTREAM_BLOCKERS))
    manifest.setdefault("dataset_blocked_uses", list(DATASET_BLOCKED_USES_WITH_UPSTREAM_BLOCKERS))
    manifest.setdefault("dataset_user_guidance", [dict(row) for row in DATASET_USER_GUIDANCE])
    if manifest["upstream_gate_blockers"]:
        manifest["dataset_required_evidence"] = _merge_string_lists(list(DATASET_REQUIRED_EVIDENCE), manifest.get("dataset_required_evidence"))
        manifest["dataset_allowed_uses"] = _merge_string_lists(
            list(DATASET_ALLOWED_USES_WITH_UPSTREAM_BLOCKERS),
            manifest.get("dataset_allowed_uses"),
        )
        manifest["dataset_blocked_uses"] = _merge_string_lists(
            list(DATASET_BLOCKED_USES_WITH_UPSTREAM_BLOCKERS),
            manifest.get("dataset_blocked_uses"),
        )
        manifest["dataset_user_guidance"] = _merge_guidance_rows(
            [dict(row) for row in DATASET_USER_GUIDANCE],
            manifest.get("dataset_user_guidance"),
        )
        manifest["decision_grade_status"] = D2_BLOCKED_DECISION_GRADE_STATUS
        manifest["model_readiness"] = D2_BLOCKED_MODEL_READINESS
    return manifest
D3_BLOCKED_STATUS = "WATCH"
D3_BLOCKED_READINESS_STATUS = "D3_WATCH_RESEARCH_ONLY"
D4_RESEARCH_STATUS = "RESEARCH_ONLY"
D4_RESEARCH_READINESS_STATUS = "D4_RESEARCH_ONLY_DIAGNOSTICS"
D4_FALSE_FLAGS = (
    "model_build_allowed",
    "go_summary_allowed",
    "paper_forward_allowed",
    "live_broker_order_allowed",
)
D4_RESEARCH_REASONS = [
    "RESEARCH_ONLY_NO_PROFIT_LIVE_BROKER_ORDER_CLAIM",
    "D5_WALK_FORWARD_NOT_RUN",
    "PRICE_BASIS_UNKNOWN",
    "UNIVERSE_WATCH_HEURISTIC",
    "D4_RL_TELEMETRY_DIAGNOSTICS_ONLY",
]
D4_CANONICAL_ARTIFACTS = [
    "observation_manifest.json",
    "state_observations.csv",
    "training_manifest.json",
    "episode_metrics.csv",
    "learning_curve.csv",
    "reward_breakdown.csv",
    "reward_component_summary.json",
    "action_distribution.csv",
    "invalid_actions.csv",
    "turnover.csv",
    "drawdown.csv",
    "policy_baseline_comparison.csv",
    "policy_nav.csv",
]
D5_NO_GO_STATUS = "NO-GO"
D5_RESEARCH_READINESS_STATUS = "D5_NO_GO_RESEARCH_ONLY_GATE"
D5_RESEARCH_REASONS = [
    "RESEARCH_ONLY_NO_PROFIT_LIVE_BROKER_ORDER_CLAIM",
    "D5_EFFECTIVE_MODEL_BUILD_LOCK",
    "NO_LIVE_BROKER_ORDER_SURFACE",
]
D5_REQUIRED_COST_BPS = (0, 23, 46)
D5_MIN_REQUIRED_PURGE_DAYS = 5
D5_MIN_REQUIRED_EMBARGO_DAYS = 5


def _cost_bp_values(rows: Any, *, selected_strategy: Any = None) -> list[int]:
    if not isinstance(rows, list):
        return []
    values: set[int] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if selected_strategy not in (None, "") and row.get("strategy") != selected_strategy:
            continue
        parsed = _finite_int(row.get("cost_bp"))
        if parsed is not None:
            values.add(parsed)
    return sorted(values)

def _normalize_d5_contract_verdict(verdict: dict[str, Any], d4_state_contract: dict[str, Any]) -> dict[str, Any]:
    contract = d4_state_contract if isinstance(d4_state_contract, dict) else {}
    row_counts = contract.get("row_counts") if isinstance(contract.get("row_counts"), dict) else {}
    contract_status = contract.get("status")
    contract_gate = contract.get("gate")
    validation_status = contract.get("observation_manifest_validation_status")
    state_rows = row_counts.get("state_observations")
    ablation_rows = row_counts.get("reward_action_ablations")
    source_hash_count = contract.get("source_hash_count") or row_counts.get("source_hashes")
    reasons = _as_string_list(verdict.get("reasons"))
    consumed = (
        verdict.get("d4_state_contract_artifacts_consumed") is True
        and contract_status == "PASS"
        and contract_gate == "D4_OBSERVATION_STATE_MANIFEST"
        and validation_status == "PASS"
        and _positive_number(state_rows)
        and _positive_number(ablation_rows)
        and _positive_number(source_hash_count)
    )
    issues = _as_string_list(verdict.get("d4_artifact_issues"))
    if not consumed:
        reasons = [reason for reason in reasons if reason != "D4_OBSERVATION_STATE_MANIFEST_CONSUMED"]
        issues = _merge_string_lists(["D4_STATE_CONTRACT_EVIDENCE_MISSING_OR_STALE"], issues)
        reasons = _merge_string_lists(reasons, issues)
    return {
        **verdict,
        "d4_state_contract_status": contract_status,
        "d4_observation_manifest_gate": contract_gate,
        "d4_observation_manifest_validation_status": validation_status,
        "d4_state_observation_rows": state_rows,
        "d4_reward_action_ablation_rows": ablation_rows,
        "d4_source_hash_count": source_hash_count,
        "d4_state_contract_artifacts_consumed": consumed,
        "d4_artifact_issues": issues,
        "reasons": reasons,
    }




def _normalize_portfolio_payload(manifest: dict[str, Any], verdict: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    verdict_payload = manifest.get("verdict") if isinstance(manifest.get("verdict"), dict) else {}
    verdict = {**verdict_payload, **(verdict if isinstance(verdict, dict) else {})}
    for key in D4_FALSE_FLAGS:
        manifest[key] = False
        verdict[key] = False
    manifest["status"] = D4_RESEARCH_STATUS
    manifest["readiness_status"] = D4_RESEARCH_READINESS_STATUS
    manifest["no_live_broker_order_readiness"] = True
    verdict["status"] = D4_RESEARCH_STATUS
    verdict["ui_badge"] = D4_RESEARCH_STATUS
    verdict["readiness_status"] = D4_RESEARCH_READINESS_STATUS
    verdict["implementation_unlocked"] = False
    verdict["no_live_broker_order_readiness"] = True
    verdict["reasons"] = _merge_string_lists(D4_RESEARCH_REASONS, manifest.get("reasons"), verdict.get("reasons"))
    manifest["verdict"] = verdict
    return manifest, verdict


def _normalize_walk_forward_payload(manifest: dict[str, Any], verdict: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    verdict_payload = manifest.get("verdict") if isinstance(manifest.get("verdict"), dict) else {}
    verdict = {**verdict_payload, **(verdict if isinstance(verdict, dict) else {})}
    artifact_status = str(verdict.get("status") or manifest.get("status") or "").upper()
    safe_status = "NOT_STARTED" if artifact_status == "NOT_STARTED" else D5_NO_GO_STATUS
    for key in D4_FALSE_FLAGS:
        manifest[key] = False
        verdict[key] = False
    manifest["status"] = safe_status
    manifest["readiness_status"] = D5_RESEARCH_READINESS_STATUS
    manifest["no_live_broker_order_readiness"] = True
    verdict["status"] = safe_status
    verdict["ui_badge"] = safe_status
    verdict["readiness_status"] = D5_RESEARCH_READINESS_STATUS
    verdict["implementation_unlocked"] = False
    verdict["no_live_broker_order_readiness"] = True
    verdict["reasons"] = _merge_string_lists(D5_RESEARCH_REASONS, manifest.get("reasons"), verdict.get("reasons"))
    manifest["verdict"] = verdict
    return manifest, verdict





def _prediction_gate_blockers(manifest: dict[str, Any], baseline_delta_summary: dict[str, Any]) -> list[str]:
    existing = _merge_string_lists(
        _as_string_list(manifest.get("d3_gate_blockers")),
        baseline_delta_summary.get("d3_gate_blockers"),
    )
    required: list[str] = []
    if not _price_basis_verified(manifest):
        required.append("D0_PRICE_BASIS_NOT_VERIFIED")
    if not _universe_official_or_manual_verified(
        {
            "verdict": manifest.get("universe_verdict"),
            "universe_review_status": manifest.get("universe_review_status"),
            "official_metadata_status": manifest.get("official_metadata_status"),
            "official_metadata_coverage_status": manifest.get("official_metadata_coverage_status"),
            "universe_certification_status": manifest.get("universe_certification_status"),
        }
    ):
        required.append("D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED")
    required.extend(["D5_WALK_FORWARD_NOT_PASS", "D3_BASELINE_WATCH_RESEARCH_ONLY"])
    return _merge_string_lists(required, existing)


def _normalize_prediction_payload(
    manifest: dict[str, Any],
    verdict: dict[str, Any],
    baseline_delta_summary: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _apply_current_d0_d1_guardrails(manifest)
    manifest.setdefault(
        "baseline_freeze_contract",
        {
            "fit_split": manifest.get("fit_split") or "train",
            "evaluation_splits": manifest.get("evaluation_splits") or ["val", "test"],
            "cost_round_trip_bp": manifest.get("cost_assumption_round_trip_bp") or 23,
            "top_k": manifest.get("top_k"),
            "deterministic_shuffle_method": "sha256(date:code)_ascending",
            "no_oos_retuning": manifest.get("no_oos_retuning", True),
        },
    )
    d3_gate_blockers = _prediction_gate_blockers(manifest, baseline_delta_summary)
    baseline_delta_summary["status"] = D3_BLOCKED_STATUS
    baseline_delta_summary["readiness_status"] = D3_BLOCKED_READINESS_STATUS
    baseline_delta_summary["go_summary_allowed"] = False
    baseline_delta_summary["model_build_allowed"] = False
    baseline_delta_summary["d3_gate_blockers"] = d3_gate_blockers
    baseline_delta_summary["required_evidence"] = _merge_string_lists(list(D3_REQUIRED_EVIDENCE), baseline_delta_summary.get("required_evidence"))
    baseline_delta_summary["allowed_uses"] = _merge_string_lists(list(D3_ALLOWED_USES_WHEN_WATCH), baseline_delta_summary.get("allowed_uses"))
    baseline_delta_summary["blocked_uses"] = _merge_string_lists(list(D3_BLOCKED_USES_WHEN_WATCH), baseline_delta_summary.get("blocked_uses"))
    verdict["status"] = D3_BLOCKED_STATUS
    verdict["readiness_status"] = D3_BLOCKED_READINESS_STATUS
    verdict["go_summary_allowed"] = False
    verdict["model_build_allowed"] = False
    verdict["d3_gate_blockers"] = d3_gate_blockers
    verdict["blocked_uses"] = _merge_string_lists(list(D3_BLOCKED_USES_WHEN_WATCH), verdict.get("blocked_uses"))
    verdict["reasons"] = _merge_string_lists(
        [
            "RESEARCH_ONLY_NO_PROFIT_LIVE_BROKER_ORDER_CLAIM",
            "PRICE_BASIS_UNKNOWN",
            "UNIVERSE_WATCH_HEURISTIC",
        ],
        verdict.get("reasons"),
        d3_gate_blockers,
    )
    manifest["status"] = D3_BLOCKED_STATUS
    manifest["readiness_status"] = D3_BLOCKED_READINESS_STATUS
    manifest["model_build_allowed"] = False
    manifest["go_summary_allowed"] = False
    manifest["d3_gate_blockers"] = d3_gate_blockers
    manifest["d3_required_evidence"] = _merge_string_lists(list(D3_REQUIRED_EVIDENCE), manifest.get("d3_required_evidence"))
    manifest["d3_allowed_uses"] = _merge_string_lists(list(D3_ALLOWED_USES_WHEN_WATCH), manifest.get("d3_allowed_uses"))
    manifest["d3_blocked_uses"] = _merge_string_lists(list(D3_BLOCKED_USES_WHEN_WATCH), manifest.get("d3_blocked_uses"))
    manifest["d3_user_guidance"] = _merge_guidance_rows([dict(row) for row in D3_USER_GUIDANCE], manifest.get("d3_user_guidance"))
    manifest["baseline_delta_summary"] = baseline_delta_summary
    manifest["verdict"] = verdict
    return manifest, verdict, baseline_delta_summary






def _effective_daily_model_gate(
    *,
    db: dict[str, Any],
    universe: dict[str, Any],
    prediction: dict[str, Any],
    gate_verdict: dict[str, Any],
    gate_status: str | None,
) -> dict[str, Any]:
    blockers: list[str] = []
    if not _price_basis_verified(db):
        blockers.append("D0_PRICE_BASIS_NOT_VERIFIED")
    if not _universe_official_or_manual_verified(universe):
        blockers.append("D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED")
    prediction_delta = prediction.get("baseline_delta_summary") or {}
    prediction_verdict = prediction.get("verdict") or {}
    if prediction_delta.get("model_build_allowed") is not True or prediction_verdict.get("go_summary_allowed") is not True:
        blockers.append("D3_BASELINE_NOT_PROMOTABLE")
    if gate_status not in {"PASS", "GO"} or gate_verdict.get("model_build_allowed") is not True:
        blockers.append("D5_WALK_FORWARD_NOT_PASS")
    effective_allowed = not blockers
    return {
        "model_build_allowed": effective_allowed,
        "go_summary_allowed": effective_allowed and gate_verdict.get("go_summary_allowed") is True,
        "effective_gate_blockers": blockers,
    }

DAILY_STAGE_VERIFICATION_COMMANDS: dict[str, list[str]] = {
    "D0": [
        "py -3.11 -m pytest tests/test_stom_rl_daily_ohlcv_db.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q",
        "py -3.11 -m py_compile stom_rl/daily_ohlcv_db.py webui/daily_ohlcv_dashboard.py webui/app.py",
        "cd webui/v2_src && npm run check && npm run build",
        "browser /daily-ohlcv shows D0 price_basis=unknown, UNKNOWN_CONFIRMED, model_build_allowed=false, and no data-daily-api-error",
    ],
    "D1": [
        "py -3.11 -m pytest tests/test_stom_rl_daily_ohlcv_universe.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q",
        "py -3.11 -m py_compile stom_rl/daily_ohlcv_universe.py webui/daily_ohlcv_dashboard.py webui/app.py",
        "cd webui/v2_src && npm run check && npm run build",
        "browser /daily-ohlcv shows D1 WATCH_HEURISTIC_UNIVERSE, quarantine counts, official metadata status, and no data-daily-api-error",
    ],
    "D2": [
        "py -3.11 -m pytest tests/test_stom_rl_daily_ohlcv_dataset.py tests/test_daily_ohlcv_dashboard_api.py -q",
        "py -3.11 -m py_compile stom_rl/daily_ohlcv_dataset.py webui/daily_ohlcv_dashboard.py",
        "cd webui/v2_src && npm run check && npm run build",
        "browser /daily-ohlcv shows D2 split/leakage evidence, inherited D0/D1 guardrails, and no data-daily-api-error",
    ],
    "D3": [
        "py -3.11 -m pytest tests/test_stom_rl_daily_prediction.py tests/test_stom_rl_daily_ranker.py tests/test_stom_rl_daily_ohlcv_dataset.py tests/test_stom_rl_daily_ohlcv_universe.py tests/test_stom_rl_daily_ohlcv_db.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q",
        "py -3.11 -m py_compile stom_rl/daily_prediction.py stom_rl/daily_ranker.py webui/daily_ohlcv_dashboard.py webui/app.py",
        "cd webui/v2_src && npm run check && npm run build",
        "browser /daily-ohlcv shows D3 WATCH, shuffle_control, no_trade_cash, frozen baseline deltas, model_build_allowed=false, and no data-daily-api-error",
    ],
    "D4": [
        "py -3.11 -m pytest tests/test_stom_rl_daily_portfolio_env.py tests/test_stom_rl_daily_rl_gate.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q",
        "py -3.11 -m py_compile stom_rl/daily_portfolio_env.py stom_rl/daily_rl_train.py webui/daily_ohlcv_dashboard.py",
        "browser /daily-ohlcv shows D4 state contract, reward/action diagnostics, portfolio trajectory, and model_build_allowed=false",
    ],
    "D5": [
        "py -3.11 -m pytest tests/test_stom_rl_daily_walk_forward.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q",
        "py -3.11 -m py_compile stom_rl/daily_walk_forward.py webui/daily_ohlcv_dashboard.py",
        "browser /daily-ohlcv shows D5 no_oos_retuning, purge/embargo, 0/23/46bp sensitivity, and NO-GO reasons",
    ],
    "D6": [
        "py -3.11 -m pytest tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q",
        "cd webui/v2_src && npm run check && npm run build",
        "browser /daily-ohlcv shows decision cockpit, flow, glossary, overlays, heatmaps, scatter, universe and symbol diagnostics",
    ],
    "D7": [
        "py -3.11 -m pytest tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q",
        "browser /daily-ohlcv shows D7 research diagnostics placeholders for feature/regime/correlation/failure analysis",
    ],
    "D8": [
        "py -3.11 -m pytest tests/test_daily_ohlcv_dashboard_api.py -q",
        "browser /daily-ohlcv shows D8 registry hashes, lock reasons, drift, and no_live_broker_order_readiness",
    ],
    "D9": [
        "py -3.11 -m pytest tests/test_daily_ohlcv_dashboard_api.py -q",
        "browser /daily-ohlcv shows paper-forward remains blocked; no live/broker/orders",
    ],
}

DAILY_STAGE_LOCK_LABELS: dict[str, list[str]] = {
    "D0": ["PRICE_BASIS_UNKNOWN", "UNKNOWN_CONFIRMED", "BLOCKED_UNTIL_PRICE_BASIS_VERIFIED"],
    "D1": ["WATCH_HEURISTIC_UNIVERSE", "WATCH_REQUIRES_OFFICIAL_OR_MANUAL_REVIEW"],
    "D2": ["PASS_WITH_D0_D1_GUARDRAILS", "DATE_SPLIT_ONLY", "NO_FUTURE_LEAKAGE"],
    "D3": ["WATCH", "SHUFFLE_CONTROL", "NO_TRADE_CONTROL", "FROZEN_D3_BASELINE_REQUIRED", "MODEL_BUILD_ALLOWED_FALSE"],
    "D4": ["RESEARCH_ONLY", "D4_OBSERVATION_STATE_MANIFEST", "MODEL_BUILD_ALLOWED_FALSE"],
    "D5": ["NO_GO", "NO_OOS_RETUNING", "SHUFFLE_NO_TRADE_CONTROLS", "MODEL_BUILD_ALLOWED_FALSE"],
    "D6": ["READ_ONLY_VISUALIZATION", "DECISION_COCKPIT", "EVIDENCE_OVERLAY"],
    "D7": ["RESEARCH_DIAGNOSTICS", "FEATURE_REGIME_FAILURE_PLACEHOLDERS", "NO_ALPHA_CLAIM"],
    "D8": ["REGISTRY_HASHES", "PAPER_FORWARD_BLOCKED", "NO_LIVE_BROKER_ORDER_READINESS"],
    "D9": ["PAPER_FORWARD_BLOCKED", "NO_LIVE_BROKER_ORDERS", "MODEL_BUILD_ALLOWED_FALSE"],
}
DAILY_PAGE_USAGE_GUIDE: dict[str, dict[str, str]] = {
    "D0": {
        "stage": "D0",
        "page": "Daily DB Analysis",
        "can_do": "테이블 수, 행 수, 기간, 결측, OHLC 오류, 분할 유사 discontinuity를 확인한다.",
        "must_not": "price_basis=unknown 상태에서 decision-grade 수익률이나 모델 빌드 근거로 쓰지 않는다.",
        "next_action": "adjusted/raw, split, dividend 기준을 독립 증거로 확정한다.",
    },
    "D1": {
        "stage": "D1",
        "page": "Daily Universe Management",
        "can_do": "KOSPI/KOSDAQ 보통주 후보, 제외/격리 사유, 선행 0 코드 보존 상태를 검토한다.",
        "must_not": "공식/수동 KRX 검증 전 WATCH_HEURISTIC_UNIVERSE를 PASS처럼 사용하지 않는다.",
        "next_action": "code,name,market,instrument_type 계약의 공식 또는 수동 CSV 검증을 완료한다.",
    },
    "D2": {
        "stage": "D2",
        "page": "Daily Dataset Builder",
        "can_do": "날짜 split, leakage, normalization, target 생성 범위를 확인한다.",
        "must_not": "D0/D1 blocker가 남아 있으면 학습·주문·수익 주장으로 연결하지 않는다.",
        "next_action": "upstream blocker가 해소된 뒤 같은 split 계약으로 재생성한다.",
    },
    "D3": {
        "stage": "D3",
        "page": "Daily Prediction / Top-K",
        "can_do": "no-trade, deterministic shuffle, rule, supervised baseline의 비용 후 상대 성능을 비교한다.",
        "must_not": "WATCH 상태의 baseline을 RL promotion 또는 수익 증명으로 쓰지 않는다.",
        "next_action": "frozen D3 baseline이 shuffle/no-trade를 안정적으로 넘는지 fresh OOS로 재검증한다.",
    },
    "D4": {
        "stage": "D4",
        "page": "Daily Portfolio RL",
        "can_do": "학습곡선, 보상 스택, action 분포, invalid action, NAV, drawdown, turnover를 진단한다.",
        "must_not": "RESEARCH_ONLY RL 곡선을 실거래 후보나 배포 가능한 모델처럼 표현하지 않는다.",
        "next_action": "D3/D5 기준을 통과할 새 reward/action/environment 가설만 사전등록 후 실험한다.",
    },
    "D5": {
        "stage": "D5",
        "page": "Daily Walk-forward / Gate",
        "can_do": "fold consistency, no-OOS-retuning, shuffle/no-trade/D3 control, 23bp·stress cost를 확인한다.",
        "must_not": "NO-GO 상태에서 model_build_allowed 또는 paper_forward_allowed를 true로 해석하지 않는다.",
        "next_action": "candidate-specific fresh OOS에서 모든 gate reason을 해소한다.",
    },
    "D6": {
        "stage": "D6",
        "page": "Daily Dashboard Visualization",
        "can_do": "Decision Cockpit, Flow, Glossary, Equity Overlay, Heatmap, Scatter, Universe, Symbol chart로 증거를 읽는다.",
        "must_not": "시각화 곡선을 수익 보장, live/broker/order readiness, 모델 배포 증거로 말하지 않는다.",
        "next_action": "각 카드의 blocker와 provenance hash를 기준으로 다음 연구 작업을 선택한다.",
    },
    "D7": {
        "stage": "D7",
        "page": "Daily Research Lab",
        "can_do": "feature/regime/correlation/failure 진단으로 왜 실패했는지와 어떤 가설을 고쳐야 하는지 찾는다.",
        "must_not": "PLACEHOLDER_READY 또는 설명용 feature importance를 alpha/profit claim으로 사용하지 않는다.",
        "next_action": "feature_importance_by_fold, regime_bucket_metrics, correlation_cluster, failure_attribution artifact를 추가한다.",
    },
    "D8": {
        "stage": "D8",
        "page": "Daily Registry",
        "can_do": "config/data/code/source hash, drift, lock reason, selected/blocked candidate 기록을 추적한다.",
        "must_not": "registry 행을 broker 주문 준비나 모델 promotion으로 해석하지 않는다.",
        "next_action": "D0-D5 gate가 PASS일 때만 paper-forward 후보 기록을 재평가한다.",
    },
    "D9": {
        "stage": "D9",
        "page": "Daily Paper-forward",
        "can_do": "paper-only 계획/관찰 로그와 no_live_broker_order_readiness를 확인한다.",
        "must_not": "live_broker_order_allowed=false 상태에서 주문, 실거래, 브로커 연동을 진행하지 않는다.",
        "next_action": "연구 전용 blocked evidence를 유지하고, 모든 gate 통과 전에는 paper-forward도 잠근다.",
    },
}


def _usage_for_stage(stage_id: str) -> dict[str, str]:
    return dict(DAILY_PAGE_USAGE_GUIDE.get(stage_id, {"stage": stage_id}))


def _progress_stage(stage_id: str, label: str, status: str | None, evidence: str) -> dict[str, Any]:
    usage_guide = _usage_for_stage(stage_id)
    return {
        "id": stage_id,
        "label": label,
        "status": status or "NOT_STARTED",
        "evidence": evidence,
        "lock_labels": DAILY_STAGE_LOCK_LABELS.get(stage_id, []),
        "verification_commands": DAILY_STAGE_VERIFICATION_COMMANDS.get(stage_id, []),
        "usage_guide": usage_guide,
        "can_do": usage_guide.get("can_do"),
        "must_not": usage_guide.get("must_not"),
        "next_action": usage_guide.get("next_action"),
    }


def load_daily_db_summary(*, run: str | None = None, table_limit: int = 100, flag_limit: int = 100, window_limit: int = 50) -> dict[str, Any]:
    run_dir = _latest_run_dir(DB_SUMMARY_ROOT, required_file="db_summary.json", run_id=run)
    if run_dir is None:
        summary = summarize_daily_db(table_limit=table_limit, quality_table_limit=0)
        summary["artifact_status"] = "GENERATED_ON_DEMAND_READ_ONLY"
    else:
        summary = _load_json(run_dir / "db_summary.json")
        summary["artifact_status"] = "LOADED_GENERATED_ARTIFACT"
        summary["artifact_dir"] = str(run_dir)
    _limit_list(summary, "table_summaries", _bounded_limit(table_limit, default=100))
    _limit_list(summary, "quality_flags", _bounded_limit(flag_limit, default=100))
    _limit_list(summary, "material_unknown_adjustment_windows", _bounded_limit(window_limit, default=50))
    source_price_basis = summary.get("price_basis")
    source_price_basis_status = summary.get("price_basis_status")
    source_decision_status = summary.get("decision_grade_return_status")
    summary["price_basis"] = PRICE_BASIS
    summary["price_basis_status"] = PRICE_BASIS_STATUS
    summary["decision_grade_return_status"] = DECISION_GRADE_RETURN_STATUS
    audit = summary.get("price_basis_audit") if isinstance(summary.get("price_basis_audit"), dict) else {}
    audit = {
        **audit,
        "status": PRICE_BASIS_STATUS,
        "required_evidence": list(PRICE_BASIS_REQUIRED_EVIDENCE),
        "allowed_uses": list(PRICE_BASIS_ALLOWED_USES),
        "blocked_uses": list(PRICE_BASIS_BLOCKED_USES),
        "user_guidance": [dict(row) for row in PRICE_BASIS_USER_GUIDANCE],
        "normalized_from_artifact": {
            "price_basis": source_price_basis,
            "price_basis_status": source_price_basis_status,
            "decision_grade_return_status": source_decision_status,
        },
    }
    summary["price_basis_audit"] = audit
    summary["price_basis_required_evidence"] = list(PRICE_BASIS_REQUIRED_EVIDENCE)
    summary["price_basis_allowed_uses"] = list(PRICE_BASIS_ALLOWED_USES)
    summary["price_basis_blocked_uses"] = list(PRICE_BASIS_BLOCKED_USES)
    summary["price_basis_user_guidance"] = [dict(row) for row in PRICE_BASIS_USER_GUIDANCE]
    summary["read_only"] = True
    summary["query_only"] = True
    summary["guardrail"] = "Research-only daily OHLCV evidence; no DB mutation, no live/broker/orders, no profit claim."
    summary["read_only_dashboard_note"] = "GET-only D0 daily OHLCV evidence; no DB mutation, no live/broker/orders, no profit claim."
    return summary


def load_daily_symbol(symbol_or_table: str, *, sample_limit: int = 50) -> dict[str, Any]:
    return summarize_symbol(symbol_or_table, sample_limit=_bounded_limit(sample_limit, default=50, maximum=200))


def load_universe_preview(*, run: str | None = None, limit: int = 200, include: str | None = None) -> dict[str, Any]:
    run_dir = _latest_run_dir(DEFAULT_UNIVERSE_ROOT, required_file="universe.json", run_id=run)
    if run_dir is None:
        manifest = build_universe_manifest()
        manifest["artifact_status"] = "GENERATED_ON_DEMAND_READ_ONLY"
    else:
        manifest = _load_json(run_dir / "universe.json")
        manifest["artifact_status"] = "LOADED_GENERATED_ARTIFACT"
        manifest["artifact_dir"] = str(run_dir)
    manifest.setdefault("official_metadata_status", "MISSING")
    manifest.setdefault("official_metadata_path", str(DEFAULT_OFFICIAL_METADATA_PATH))
    manifest.setdefault("official_metadata_required_columns", list(OFFICIAL_METADATA_REQUIRED_COLUMNS))
    manifest.setdefault("official_metadata_unmatched_table_count", manifest.get("table_count", 0))
    manifest.setdefault("official_metadata_matched_table_count", 0)
    manifest.setdefault("official_metadata_coverage_status", "MISSING" if manifest["official_metadata_status"] == "MISSING" else "PARTIAL")
    manifest.setdefault("universe_review_status", manifest.get("review_status") or manifest.get("verdict") or "WATCH_REQUIRES_OFFICIAL_OR_MANUAL_REVIEW")
    manifest.setdefault("universe_certification_status", "BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW")
    manifest.setdefault("universe_required_evidence", list(UNIVERSE_REQUIRED_EVIDENCE))
    manifest.setdefault("universe_allowed_uses", list(UNIVERSE_ALLOWED_USES_WHEN_WATCH))
    manifest.setdefault("universe_blocked_uses", list(UNIVERSE_BLOCKED_USES_WHEN_WATCH))
    manifest.setdefault("universe_user_guidance", [dict(row) for row in UNIVERSE_USER_GUIDANCE])
    manifest.setdefault("official_metadata_unmatched_quarantine_count", 0)
    manifest.setdefault(
        "official_metadata",
        {
            "status": manifest["official_metadata_status"],
            "available": False,
            "used": False,
            "required_columns": list(OFFICIAL_METADATA_REQUIRED_COLUMNS),
            "review_status": "WATCH_OFFICIAL_METADATA_REQUIRED",
            "coverage_status": manifest.get("official_metadata_coverage_status"),
            "certification_status": manifest.get("universe_certification_status"),
        },
    )
    official_metadata = manifest.get("official_metadata")
    if isinstance(official_metadata, dict):
        official_metadata.setdefault("coverage_status", manifest.get("official_metadata_coverage_status"))
        official_metadata.setdefault("certification_status", manifest.get("universe_certification_status"))
    official_path = Path(str(manifest.get("official_metadata_path") or DEFAULT_OFFICIAL_METADATA_PATH))
    if not official_path.exists():
        manifest["verdict"] = "WATCH_HEURISTIC_UNIVERSE"
        manifest["review_status"] = "WATCH_REQUIRES_OFFICIAL_OR_MANUAL_REVIEW"
        manifest["universe_review_status"] = "WATCH_REQUIRES_OFFICIAL_OR_MANUAL_REVIEW"
        manifest["official_metadata_status"] = "MISSING"
        manifest["official_metadata_coverage_status"] = "MISSING"
        manifest["universe_certification_status"] = "BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW"
        manifest["official_metadata_unmatched_table_count"] = manifest.get("table_count", 0)
        manifest["official_metadata_matched_table_count"] = 0
        manifest["universe_allowed_uses"] = list(UNIVERSE_ALLOWED_USES_WHEN_WATCH)
        manifest["universe_blocked_uses"] = list(UNIVERSE_BLOCKED_USES_WHEN_WATCH)
        if isinstance(official_metadata, dict):
            official_metadata["status"] = "MISSING"
            official_metadata["available"] = False
            official_metadata["used"] = False
            official_metadata["review_status"] = "WATCH_OFFICIAL_METADATA_REQUIRED"
            official_metadata["coverage_status"] = "MISSING"
            official_metadata["certification_status"] = "BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW"
    for required_field in ("official_metadata_status", "official_metadata_coverage_status", "universe_certification_status"):
        if required_field not in set(manifest.get("required_fields") or []):
            manifest["required_fields"] = list(manifest.get("required_fields") or []) + [required_field]
    rows = list(manifest.get("symbols") or [])
    if include == "true":
        rows = [row for row in rows if row.get("include") is True]
    elif include == "false":
        rows = [row for row in rows if row.get("include") is False]
    safe_limit = _bounded_limit(limit, default=200)
    manifest["symbols_total"] = len(rows)
    manifest["symbols_truncated"] = len(rows) > safe_limit
    manifest["symbols"] = rows[:safe_limit]
    manifest["exclusions_total"] = len(manifest.get("exclusions") or [])
    manifest["exclusions"] = list(manifest.get("exclusions") or [])[:safe_limit]
    manifest["read_only_dashboard_note"] = "GET-only D1 universe evidence; no live/broker/orders, no profit claim."
    return manifest


def list_universe_manifests(limit: int = 20) -> dict[str, Any]:
    root = DEFAULT_UNIVERSE_ROOT.resolve()
    safe_limit = _bounded_limit(limit, default=20, maximum=200)
    runs: list[dict[str, Any]] = []
    if root.exists():
        for run_dir in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            manifest_path = run_dir / "universe.json"
            if not run_dir.is_dir() or not manifest_path.exists():
                continue
            payload = _load_json(manifest_path)
            runs.append(
                {
                    "run_id": run_dir.name,
                    "artifact_dir": str(run_dir),
                    "modified_at": manifest_path.stat().st_mtime,
                    "verdict": payload.get("verdict"),
                    "manifest_sha": payload.get("manifest_sha"),
                    "table_count": payload.get("table_count"),
                    "include_count": payload.get("include_count"),
                    "exclude_count": payload.get("exclude_count"),
                    "stockinfo_matched_table_count": payload.get("stockinfo_matched_table_count"),
                    "stockinfo_unmatched_table_count": payload.get("stockinfo_unmatched_table_count"),
                    "official_metadata_coverage_status": payload.get("official_metadata_coverage_status"),
                    "universe_certification_status": payload.get("universe_certification_status"),
                }
            )
            if len(runs) >= safe_limit:
                break
    return {"runs": runs, "read_only_dashboard_note": "Generated universe manifests only; no writes from dashboard."}


def load_dataset_latest(*, run: str | None = None, sample_limit: int = 25) -> dict[str, Any]:
    run_dir = _latest_run_dir(DEFAULT_DATASET_ROOT, required_file="dataset_manifest.json", run_id=run)
    if run_dir is None:
        return {
            "status": "NOT_STARTED",
            "read_only": True,
            "guardrail": "D2 dataset artifacts are absent; no model/profit/live readiness claim.",
        }
    manifest = _normalize_dataset_manifest(_load_json(run_dir / "dataset_manifest.json"))
    safe_limit = _bounded_limit(sample_limit, default=25, maximum=500)
    payload = {
        **manifest,
        "status": "PASS" if manifest.get("leakage_status") == "PASS" and manifest.get("split_chronology_status") == "PASS" else "WATCH",
        "artifact_status": "LOADED_GENERATED_ARTIFACT",
        "artifact_dir": str(run_dir),
        "read_only": True,
        "read_only_dashboard_note": "GET-only D2 dataset evidence; no training/order/live/profit action from dashboard.",
        "samples": {
            "feature_panel": _read_csv_rows(run_dir / "feature_panel.csv", safe_limit),
            "label_panel": _read_csv_rows(run_dir / "label_panel.csv", safe_limit),
            "rl_candidate_panel": _read_csv_rows(run_dir / "rl_candidate_panel.csv", safe_limit),
            "split_assignments": _read_csv_rows(run_dir / "split_assignments.csv", safe_limit),
            "blocked_windows": _read_csv_rows(run_dir / "blocked_windows.csv", safe_limit),
        },
    }
    payload["normalization_stats"] = _load_json(run_dir / "normalization_stats.json") if (run_dir / "normalization_stats.json").exists() else {}
    payload["leakage_report"] = _load_json(run_dir / "leakage_report.json") if (run_dir / "leakage_report.json").exists() else {}
    return payload


def list_dataset_artifacts(limit: int = 20) -> dict[str, Any]:
    root = DEFAULT_DATASET_ROOT.resolve()
    safe_limit = _bounded_limit(limit, default=20, maximum=200)
    runs: list[dict[str, Any]] = []
    if root.exists():
        for run_dir in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            manifest_path = run_dir / "dataset_manifest.json"
            if not run_dir.is_dir() or not manifest_path.exists():
                continue
            manifest = _normalize_dataset_manifest(_load_json(manifest_path))
            runs.append(
                {
                    "kind": "daily_ohlcv_dataset",
                    "run_id": run_dir.name,
                    "artifact_dir": str(run_dir),
                    "primary_file": str(manifest_path),
                    "modified_at": manifest_path.stat().st_mtime,
                    "manifest_sha": manifest.get("manifest_sha"),
                    "artifact_scope": manifest.get("artifact_scope"),
                    "leakage_status": manifest.get("leakage_status"),
                    "split_chronology_status": manifest.get("split_chronology_status"),
                    "feature_rows": (manifest.get("row_counts") or {}).get("feature_rows"),
                    "eligible_rows": (manifest.get("row_counts") or {}).get("eligible_rows"),
                    "model_readiness": manifest.get("model_readiness"),
                    "upstream_gate_blockers": manifest.get("upstream_gate_blockers") or [],
                    "decision_grade_status": manifest.get("decision_grade_status"),
                    "dataset_blocked_uses": manifest.get("dataset_blocked_uses") or [],
                }
            )
            if len(runs) >= safe_limit:
                break
    return {"runs": runs, "read_only_dashboard_note": "Generated D2 dataset artifacts only; no writes from dashboard."}


def load_dataset_chart(*, run: str | None = None) -> dict[str, Any]:
    dataset = load_dataset_latest(run=run, sample_limit=0)
    if dataset.get("status") == "NOT_STARTED":
        return load_not_started_surface("dataset")
    split_counts = ((dataset.get("split_summary") or {}).get("row_counts") or {})
    row_counts = dataset.get("row_counts") or {}
    return {
        "status": dataset.get("status"),
        "run_id": dataset.get("run_id"),
        "artifact_scope": dataset.get("artifact_scope"),
        "leakage_status": dataset.get("leakage_status"),
        "split_chronology_status": dataset.get("split_chronology_status"),
        "price_basis": dataset.get("price_basis"),
        "universe_verdict": dataset.get("universe_verdict"),
        "model_readiness": dataset.get("model_readiness"),
        "upstream_gate_blockers": dataset.get("upstream_gate_blockers") or [],
        "price_basis_status": dataset.get("price_basis_status"),
        "decision_grade_return_status": dataset.get("decision_grade_return_status"),
        "official_metadata_status": dataset.get("official_metadata_status"),
        "official_metadata_coverage_status": dataset.get("official_metadata_coverage_status"),
        "universe_certification_status": dataset.get("universe_certification_status"),
        "split_series": [{"label": key, "value": value} for key, value in split_counts.items()],
        "row_series": [{"label": key, "value": value} for key, value in row_counts.items()],
        "guardrail": "D2 dataset evidence only. It is not a profit, broker, live, order, or trained-RL readiness claim.",
    }


def load_prediction_latest(*, run: str | None = None, sample_limit: int = 25) -> dict[str, Any]:
    run_dir = _latest_run_dir(DEFAULT_PREDICTION_ROOT, required_file="prediction_manifest.json", run_id=run)
    if run_dir is None:
        return load_not_started_surface("prediction")
    safe_limit = _bounded_limit(sample_limit, default=25, maximum=500)
    manifest = _load_json(run_dir / "prediction_manifest.json")
    verdict = _load_json(run_dir / "verdict.json") if (run_dir / "verdict.json").exists() else manifest.get("verdict", {})
    baseline = _load_json(run_dir / "baseline_metrics.json") if (run_dir / "baseline_metrics.json").exists() else {"metrics": []}
    baseline_delta_summary = _load_json(run_dir / "baseline_delta_summary.json") if (run_dir / "baseline_delta_summary.json").exists() else manifest.get("baseline_delta_summary", {})
    model_metrics = _load_json(run_dir / "model_metrics.json") if (run_dir / "model_metrics.json").exists() else {"metrics": []}
    manifest, verdict, baseline_delta_summary = _normalize_prediction_payload(manifest, verdict, baseline_delta_summary)
    return {
        **manifest,
        "status": verdict.get("status") or (manifest.get("verdict") or {}).get("status") or "WATCH",
        "readiness_status": D3_BLOCKED_READINESS_STATUS,
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "artifact_status": "LOADED_GENERATED_ARTIFACT",
        "artifact_dir": str(run_dir),
        "read_only": True,
        "read_only_dashboard_note": "GET-only D3 baseline/ranker evidence; no training/order/live/profit action from dashboard.",
        "verdict": verdict,
        "baseline_metrics": list(baseline.get("metrics") or [])[:safe_limit],
        "model_metrics": list(model_metrics.get("metrics") or [])[:safe_limit],
        "baseline_delta_summary": baseline_delta_summary,
        "d3_gate_blockers": manifest.get("d3_gate_blockers") or [],
        "d3_required_evidence": manifest.get("d3_required_evidence") or [],
        "d3_allowed_uses": manifest.get("d3_allowed_uses") or [],
        "d3_blocked_uses": manifest.get("d3_blocked_uses") or [],
        "d3_user_guidance": manifest.get("d3_user_guidance") or [],
        "samples": {
            "predictions": _read_csv_rows(run_dir / "predictions.csv", safe_limit),
            "calibration": _read_csv_rows(run_dir / "calibration.csv", safe_limit),
            "turnover": _read_csv_rows(run_dir / "turnover.csv", safe_limit),
            "drawdown": _read_csv_rows(run_dir / "drawdown.csv", safe_limit),
        },
    }


def load_portfolio_latest(*, run: str | None = None, sample_limit: int = 25) -> dict[str, Any]:
    run_dir = _latest_run_dir(DEFAULT_PORTFOLIO_ROOT, required_file="rl_manifest.json", run_id=run)
    if run_dir is None:
        return load_not_started_surface("portfolio")
    safe_limit = _bounded_limit(sample_limit, default=25, maximum=500)
    manifest = _load_json(run_dir / "rl_manifest.json")
    verdict = _load_json(run_dir / "verdict.json") if (run_dir / "verdict.json").exists() else manifest.get("verdict", {})
    policy_metrics = _load_json(run_dir / "policy_metrics.json") if (run_dir / "policy_metrics.json").exists() else {"metrics": []}
    baseline_comparison = _load_json(run_dir / "baseline_comparison.json") if (run_dir / "baseline_comparison.json").exists() else {}
    training_manifest = _load_json(run_dir / "training_manifest.json") if (run_dir / "training_manifest.json").exists() else manifest
    reward_component_summary = _load_json(run_dir / "reward_component_summary.json") if (run_dir / "reward_component_summary.json").exists() else {}
    policy_evaluation = _load_json(run_dir / "policy_evaluation_manifest.json") if (run_dir / "policy_evaluation_manifest.json").exists() else {}
    observation_manifest = _load_json(run_dir / "observation_manifest.json") if (run_dir / "observation_manifest.json").exists() else manifest.get("observation_manifest", {})
    manifest, verdict = _normalize_portfolio_payload(manifest, verdict)
    training_manifest, _training_verdict = _normalize_portfolio_payload(
        training_manifest,
        (training_manifest.get("verdict") if isinstance(training_manifest.get("verdict"), dict) else {}),
    )
    policy_evaluation = {
        **policy_evaluation,
        "status": D4_RESEARCH_STATUS,
        "readiness_status": D4_RESEARCH_READINESS_STATUS,
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "no_live_broker_order_readiness": True,
    }
    telemetry = training_manifest.get("telemetry") or manifest.get("telemetry") or {}
    if isinstance(telemetry, dict):
        telemetry = {**telemetry, "canonical_artifacts": _merge_string_lists(D4_CANONICAL_ARTIFACTS, telemetry.get("canonical_artifacts"))}
    else:
        telemetry = {"canonical_artifacts": list(D4_CANONICAL_ARTIFACTS)}
    return {
        **manifest,
        "status": D4_RESEARCH_STATUS,
        "readiness_status": D4_RESEARCH_READINESS_STATUS,
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "no_live_broker_order_readiness": True,
        "artifact_status": "LOADED_GENERATED_ARTIFACT",
        "artifact_dir": str(run_dir),
        "read_only": True,
        "read_only_dashboard_note": "GET-only D4 portfolio RL evidence; no training/order/live/profit action from dashboard.",
        "verdict": verdict,
        "policy_metrics": policy_metrics,
        "baseline_comparison": baseline_comparison,
        "training_manifest": training_manifest,
        "telemetry": telemetry,
        "reward_component_summary": reward_component_summary,
        "policy_evaluation": policy_evaluation,
        "observation_manifest": observation_manifest,
        "observation_manifest_validation": manifest.get("observation_manifest_validation") or observation_manifest.get("validation") or {},
        "samples": {
            "positions": _read_csv_rows(run_dir / "positions.csv", safe_limit),
            "invalid_actions": _read_csv_rows(run_dir / "invalid_actions.csv", safe_limit),
            "reward_breakdown": _read_csv_rows(run_dir / "reward_breakdown.csv", safe_limit),
            "learning_curve": _read_csv_rows(run_dir / "learning_curve.csv", safe_limit),
            "action_distribution": _read_csv_rows(run_dir / "action_distribution.csv", safe_limit),
            "turnover": _read_csv_rows(run_dir / "turnover.csv", safe_limit),
            "drawdown": _read_csv_rows(run_dir / "drawdown.csv", safe_limit),
            "policy_baseline_comparison": _read_csv_rows(run_dir / "policy_baseline_comparison.csv", safe_limit),
            "policy_nav": _read_csv_rows(run_dir / "policy_nav.csv", safe_limit),
            "state_observations": _read_csv_rows(run_dir / "state_observations.csv", safe_limit),
        },
    }


def load_walk_forward_latest(*, run: str | None = None, sample_limit: int = 25) -> dict[str, Any]:
    run_dir = _latest_run_dir(DEFAULT_WALK_FORWARD_ROOT, required_file="walk_forward_manifest.json", run_id=run)
    if run_dir is None:
        return load_not_started_surface("gate")
    safe_limit = _bounded_limit(sample_limit, default=25, maximum=500)
    manifest = _load_json(run_dir / "walk_forward_manifest.json")
    verdict = _load_json(run_dir / "gate_verdict.json") if (run_dir / "gate_verdict.json").exists() else manifest.get("verdict", {})
    d4_state_contract = (
        _load_json(run_dir / "d4_state_contract.json")
        if (run_dir / "d4_state_contract.json").exists()
        else manifest.get("d4_state_contract", {})
    )
    manifest, verdict = _normalize_walk_forward_payload(manifest, verdict)
    verdict = _normalize_d5_contract_verdict(verdict, d4_state_contract if isinstance(d4_state_contract, dict) else {})
    manifest["verdict"] = verdict
    return {
        **manifest,
        "status": manifest.get("status") or D5_NO_GO_STATUS,
        "readiness_status": manifest.get("readiness_status") or D5_RESEARCH_READINESS_STATUS,
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "no_live_broker_order_readiness": True,
        "artifact_status": "LOADED_GENERATED_ARTIFACT",
        "artifact_dir": str(run_dir),
        "read_only": True,
        "read_only_dashboard_note": "GET-only D5 walk-forward/gate evidence; no training/order/live/profit action from dashboard.",
        "verdict": verdict,
        "d4_state_contract": d4_state_contract,
        "d4_state_contract_status": verdict.get("d4_state_contract_status"),
        "d4_observation_manifest_gate": verdict.get("d4_observation_manifest_gate"),
        "d4_observation_manifest_validation_status": verdict.get("d4_observation_manifest_validation_status"),
        "d4_state_observation_rows": verdict.get("d4_state_observation_rows"),
        "d4_reward_action_ablation_rows": verdict.get("d4_reward_action_ablation_rows"),
        "d4_source_hash_count": verdict.get("d4_source_hash_count"),
        "d4_state_contract_artifacts_consumed": verdict.get("d4_state_contract_artifacts_consumed"),
        "d4_artifact_issues": verdict.get("d4_artifact_issues") or [],
        "samples": {
            "folds": _read_csv_rows(run_dir / "folds.csv", safe_limit),
            "fold_metrics": _read_csv_rows(run_dir / "fold_metrics.csv", safe_limit),
            "shuffle_control": _read_csv_rows(run_dir / "shuffle_control.csv", safe_limit),
            "cost_sensitivity": _read_csv_rows(run_dir / "cost_sensitivity.csv", safe_limit),
            "rl_fold_metrics": _read_csv_rows(run_dir / "rl_fold_metrics.csv", safe_limit),
            "fold_assignments": _read_csv_rows(run_dir / "fold_assignments.csv", safe_limit),
        },
    }


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _registry_artifact_invariant_errors(manifest: dict[str, Any], candidate_registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    guardrail = str(manifest.get("guardrail") or "")
    if "no live/broker/orders" not in guardrail:
        errors.append("REGISTRY_GUARDRAIL_MISSING_NO_LIVE_BROKER_ORDERS")
    if "no profit" not in guardrail.lower():
        errors.append("REGISTRY_GUARDRAIL_MISSING_NO_PROFIT_CLAIM")
    if manifest.get("live_broker_order_allowed") is not False:
        errors.append("REGISTRY_MANIFEST_LIVE_BROKER_ORDER_NOT_FALSE")
    if manifest.get("no_live_broker_order_readiness") is not True:
        errors.append("REGISTRY_MANIFEST_NO_LIVE_BROKER_ORDER_READINESS_NOT_TRUE")
    for key in ("config_hash", "data_hash", "code_hash"):
        if not _is_sha256(manifest.get(key)):
            errors.append(f"REGISTRY_MANIFEST_{key.upper()}_INVALID")
    candidates = candidate_registry.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        errors.append("REGISTRY_CANDIDATES_MISSING")
        return errors
    has_model_build_candidate = False
    has_paper_forward_candidate = False
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            errors.append(f"REGISTRY_CANDIDATE_{index}_INVALID")
            continue
        if candidate.get("live_broker_order_allowed") is not False:
            errors.append(f"REGISTRY_CANDIDATE_{index}_LIVE_BROKER_ORDER_NOT_FALSE")
        if candidate.get("no_live_broker_order_readiness") is not True:
            errors.append(f"REGISTRY_CANDIDATE_{index}_NO_LIVE_BROKER_ORDER_READINESS_NOT_TRUE")
        for key in ("config_hash", "data_hash", "code_hash"):
            if not _is_sha256(candidate.get(key)):
                errors.append(f"REGISTRY_CANDIDATE_{index}_{key.upper()}_INVALID")
        source_hashes = candidate.get("source_hashes")
        required_sources = {
            "stom_rl/daily_rl_train.py",
            "stom_rl/daily_walk_forward.py",
            "stom_rl/daily_registry.py",
            "webui/daily_ohlcv_dashboard.py",
            "webui/app.py",
            "webui/v2_src/src/lib/dailyOhlcvApi.ts",
            "webui/v2_src/src/tabs/DailyOhlcvTab.svelte",
            "webui/v2_src/src/tabs/dailyOhlcv/DailyProgressTimeline.svelte",
            "webui/v2_src/src/tabs/dailyOhlcv/DailyVisualLabCard.svelte",
        }
        if not isinstance(source_hashes, dict):
            errors.append(f"REGISTRY_CANDIDATE_{index}_SOURCE_HASHES_MISSING")
        else:
            for source in sorted(required_sources):
                if not _is_sha256(source_hashes.get(source)):
                    errors.append(f"REGISTRY_CANDIDATE_{index}_SOURCE_HASH_INVALID_{source}")
        d5_status = str(candidate.get("d5_status") or "")
        d4_status = str(candidate.get("d4_status") or "")
        effective_blockers = candidate.get("effective_gate_blockers")
        effective_blockers_explicit = isinstance(effective_blockers, list)
        explicit_effective_blockers = effective_blockers if effective_blockers_explicit else []
        if not effective_blockers_explicit and (candidate.get("model_build_allowed") is True or candidate.get("paper_forward_allowed") is True):
            errors.append(f"REGISTRY_CANDIDATE_{index}_EFFECTIVE_GATE_BLOCKERS_MISSING")
        baseline_delta = _to_float(candidate.get("baseline_delta_vs_best_d3"))
        candidate_model_allowed = candidate.get("model_build_allowed") is True
        candidate_paper_allowed = candidate.get("paper_forward_allowed") is True
        candidate_research_safe = (
            effective_blockers_explicit
            and not explicit_effective_blockers
            and _price_basis_verified(candidate)
            and _universe_official_or_manual_verified(candidate)
            and baseline_delta is not None
            and baseline_delta >= 0
        )
        candidate_gates_safe = d5_status == "PASS" and d4_status == "PASS" and candidate_research_safe
        if candidate_model_allowed and not candidate_gates_safe:
            errors.append(f"REGISTRY_CANDIDATE_{index}_MODEL_BUILD_TRUE_WITH_LOCKED_GATES")
        if candidate_paper_allowed and not candidate_gates_safe:
            errors.append(f"REGISTRY_CANDIDATE_{index}_PAPER_FORWARD_TRUE_WITH_LOCKED_GATES")
        has_model_build_candidate = has_model_build_candidate or (candidate_model_allowed and candidate_gates_safe)
        has_paper_forward_candidate = has_paper_forward_candidate or (candidate_paper_allowed and candidate_gates_safe)
    if manifest.get("model_build_allowed") is True and not has_model_build_candidate:
        errors.append("REGISTRY_MANIFEST_MODEL_BUILD_TRUE_WITHOUT_SAFE_CANDIDATE")
    if manifest.get("paper_forward_allowed") is True and not has_paper_forward_candidate:
        errors.append("REGISTRY_MANIFEST_PAPER_FORWARD_TRUE_WITHOUT_SAFE_CANDIDATE")
    return errors

REGISTRY_REQUIRED_CSV_EVIDENCE = {
    "PAPER_SELECTED": (
        "paper_selected.csv",
        {"date", "code", "rank", "paper_weight", "paper_only_selected", "selection_status", "strategy", "reason"},
    ),
    "REALIZED_RETURNS": (
        "realized_returns.csv",
        {"date", "split", "paper_nav", "realized_return", "policy_reward", "current_drawdown", "evidence_status", "numeric_error", "source"},
    ),
    "DRIFT": (
        "drift.csv",
        {"metric", "value", "reference", "status", "action"},
    ),
    "DRAWDOWN": (
        "drawdown.csv",
        {"date", "split", "paper_nav", "paper_forward_drawdown", "computed_drawdown", "evidence_status", "numeric_error", "source"},
    ),
}


def _read_registry_json_artifact(path: Path, *, invalid_error: str, missing_error: str | None = None) -> tuple[dict[str, Any], list[str]]:
    if not path.exists():
        return {}, [missing_error] if missing_error else []
    try:
        payload = _load_json(path)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}, [invalid_error]
    if not isinstance(payload, dict):
        return {}, [invalid_error]
    return payload, []


def _read_registry_decision_log(path: Path, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows, ["REGISTRY_EVIDENCE_DECISION_LOG_MISSING"]
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return rows, ["REGISTRY_DECISION_LOG_JSONL_INVALID"]
    if not any(line.strip() for line in lines):
        return rows, ["REGISTRY_EVIDENCE_DECISION_LOG_EMPTY"]
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            errors.append("REGISTRY_DECISION_LOG_JSONL_INVALID")
            break
        if not isinstance(payload, dict):
            errors.append("REGISTRY_DECISION_LOG_ROW_INVALID")
            continue
        if len(rows) < limit:
            rows.append(payload)
    return rows, errors


def _safe_read_registry_csv_rows(path: Path, limit: int) -> list[dict[str, Any]]:
    try:
        return _read_csv_rows(path, limit)
    except (csv.Error, OSError, UnicodeDecodeError):
        return []



def _registry_csv_evidence_errors(run_dir: Path) -> list[str]:
    errors: list[str] = []
    for label, (filename, required_columns) in REGISTRY_REQUIRED_CSV_EVIDENCE.items():
        path = run_dir / filename
        if not path.exists():
            errors.append(f"REGISTRY_EVIDENCE_{label}_MISSING")
            continue
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                columns = set(reader.fieldnames or [])
                has_header = bool(columns)
                has_row = any(True for _ in reader)
        except (csv.Error, OSError, UnicodeDecodeError):
            errors.append(f"REGISTRY_EVIDENCE_{label}_INVALID")
            continue
        if not has_header:
            errors.append(f"REGISTRY_EVIDENCE_{label}_HEADER_MISSING")
        elif not required_columns.issubset(columns):
            errors.append(f"REGISTRY_EVIDENCE_{label}_COLUMNS_INVALID")
        if not has_row:
            errors.append(f"REGISTRY_EVIDENCE_{label}_EMPTY")
    return errors

def load_registry_latest(*, run: str | None = None, sample_limit: int = 25) -> dict[str, Any]:
    run_dir = _latest_run_dir(DEFAULT_DAILY_REGISTRY_ROOT, required_file="registry_manifest.json", run_id=run)
    if run_dir is None:
        return load_not_started_surface("registry")
    safe_limit = _bounded_limit(sample_limit, default=25, maximum=500)
    manifest, manifest_errors = _read_registry_json_artifact(
        run_dir / "registry_manifest.json",
        invalid_error="REGISTRY_MANIFEST_JSON_INVALID",
        missing_error="REGISTRY_MANIFEST_JSON_MISSING",
    )
    candidate_registry, candidate_errors = _read_registry_json_artifact(
        run_dir / "candidate_registry.json",
        invalid_error="REGISTRY_CANDIDATE_REGISTRY_JSON_INVALID",
        missing_error="REGISTRY_CANDIDATE_REGISTRY_MISSING",
    )
    decision_rows, decision_errors = _read_registry_decision_log(run_dir / "decision_log.jsonl", safe_limit)
    invariant_errors = sorted(
        dict.fromkeys(
            [
                *manifest_errors,
                *candidate_errors,
                *_registry_artifact_invariant_errors(manifest, candidate_registry),
                *_registry_csv_evidence_errors(run_dir),
                *decision_errors,
            ]
        )
    )
    safe_guardrail = "D8/D9 registry is research-only paper-forward planning evidence; no live/broker/orders, no profit claim, no deployable model claim."
    if invariant_errors:
        manifest = {
            **manifest,
            "status": "BLOCKED_UNSAFE_REGISTRY_ARTIFACT",
            "promotion_status": "BLOCKED_UNSAFE_REGISTRY_ARTIFACT",
            "model_build_allowed": False,
            "paper_forward_allowed": False,
            "live_broker_order_allowed": False,
            "no_live_broker_order_readiness": True,
        }
        candidates = candidate_registry.get("candidates")
        if isinstance(candidates, list):
            candidate_registry = {
                **candidate_registry,
                "candidates": [
                    {
                        **candidate,
                        "model_build_allowed": False,
                        "paper_forward_allowed": False,
                        "live_broker_order_allowed": False,
                        "no_live_broker_order_readiness": True,
                        "promotion_status": "BLOCKED_UNSAFE_REGISTRY_ARTIFACT",
                    }
                    if isinstance(candidate, dict)
                    else candidate
                    for candidate in candidates
                ],
            }
        candidate_registry["invariant_errors"] = invariant_errors
    return {
        **manifest,
        "status": manifest.get("status") or "RESEARCH_ONLY_BLOCKED",
        "artifact_status": "LOADED_GENERATED_ARTIFACT",
        "artifact_dir": str(run_dir),
        "read_only": True,
        "read_only_dashboard_note": "GET-only D8/D9 registry and paper-forward ledger evidence; no live/broker/order/profit action from dashboard.",
        "candidate_registry": candidate_registry,
        "samples": {
            "paper_selected": _safe_read_registry_csv_rows(run_dir / "paper_selected.csv", safe_limit),
            "realized_returns": _safe_read_registry_csv_rows(run_dir / "realized_returns.csv", safe_limit),
            "drift": _safe_read_registry_csv_rows(run_dir / "drift.csv", safe_limit),
            "drawdown": _safe_read_registry_csv_rows(run_dir / "drawdown.csv", safe_limit),
            "decision_log": decision_rows,
        },
        "guardrail": safe_guardrail,
        "invariant_errors": invariant_errors,
    }


def load_prediction_chart(*, run: str | None = None) -> dict[str, Any]:
    prediction = load_prediction_latest(run=run, sample_limit=25)
    if prediction.get("status") == "NOT_STARTED":
        return prediction
    metrics = list(prediction.get("baseline_metrics") or [])
    return {
        "status": prediction.get("status"),
        "run_id": prediction.get("run_id"),
        "best_strategy": (prediction.get("verdict") or {}).get("best_strategy_by_total_net_return"),
        "go_summary_allowed": (prediction.get("verdict") or {}).get("go_summary_allowed"),
        "model_build_allowed": prediction.get("model_build_allowed", False),
        "readiness_status": prediction.get("readiness_status") or D3_BLOCKED_READINESS_STATUS,
        "price_basis": prediction.get("price_basis"),
        "universe_review_status": prediction.get("universe_review_status"),
        "cost_assumption_round_trip_bp": prediction.get("cost_assumption_round_trip_bp"),
        "baseline_delta_summary": prediction.get("baseline_delta_summary") or {},
        "d3_gate_blockers": prediction.get("d3_gate_blockers") or [],
        "d3_blocked_uses": prediction.get("d3_blocked_uses") or [],
        "d3_user_guidance": prediction.get("d3_user_guidance") or [],
        "baseline_freeze_contract": prediction.get("baseline_freeze_contract") or {},
        "artifact_hashes": prediction.get("artifact_hashes") or {},
        "baseline_series": [
            {
                "strategy": row.get("strategy"),
                "strategy_family": row.get("strategy_family"),
                "total_net_return": row.get("total_net_return"),
                "delta_vs_cash_total_net_return": row.get("delta_vs_cash_total_net_return"),
                "delta_vs_shuffle_control_total_net_return": row.get("delta_vs_shuffle_control_total_net_return"),
                "delta_vs_best_rule_baseline_total_net_return": row.get("delta_vs_best_rule_baseline_total_net_return"),
                "max_drawdown": row.get("max_drawdown"),
                "mean_turnover": row.get("mean_turnover"),
                "hit_rate": row.get("hit_rate"),
            }
            for row in metrics
        ],
        "calibration": (prediction.get("samples") or {}).get("calibration") or [],
        "guardrail": "D3 baseline/ranker evidence only; not a profit, broker, live, order, or trained-RL readiness claim.",
    }


def load_portfolio_chart(*, run: str | None = None) -> dict[str, Any]:
    portfolio = load_portfolio_latest(run=run, sample_limit=25)
    if portfolio.get("status") == "NOT_STARTED":
        return portfolio
    samples = portfolio.get("samples") or {}
    telemetry = portfolio.get("telemetry") or {}
    return {
        "status": portfolio.get("status"),
        "run_id": portfolio.get("run_id"),
        "ui_badge": (portfolio.get("verdict") or {}).get("ui_badge"),
        "go_summary_allowed": (portfolio.get("verdict") or {}).get("go_summary_allowed"),
        "model_build_allowed": portfolio.get("model_build_allowed", False),
        "readiness_status": portfolio.get("readiness_status") or (portfolio.get("verdict") or {}).get("readiness_status"),
        "paper_forward_allowed": portfolio.get("paper_forward_allowed", False),
        "live_broker_order_allowed": portfolio.get("live_broker_order_allowed", False),
        "implementation_unlocked": (portfolio.get("verdict") or {}).get("implementation_unlocked"),
        "gate_dependency": (portfolio.get("verdict") or {}).get("gate_dependency"),
        "prediction_manifest_sha": portfolio.get("prediction_manifest_sha"),
        "prediction_artifact_hashes": portfolio.get("prediction_artifact_hashes") or {},
        "prediction_artifact_hash_mismatches": portfolio.get("prediction_artifact_hash_mismatches") or [],
        "artifact_hashes": portfolio.get("artifact_hashes") or {},
        "baseline_comparison": portfolio.get("baseline_comparison") or {},
        "metrics": (portfolio.get("policy_metrics") or {}).get("metrics") or [],
        "reward_sample": samples.get("reward_breakdown") or [],
        "training_status": telemetry.get("training_status"),
        "telemetry": telemetry,
        "learning_curve": samples.get("learning_curve") or [],
        "reward_component_summary": portfolio.get("reward_component_summary") or {},
        "observation_manifest": portfolio.get("observation_manifest") or {},
        "observation_manifest_validation": portfolio.get("observation_manifest_validation") or {},
        "state_observations": samples.get("state_observations") or [],
        "invalid_actions": samples.get("invalid_actions") or [],
        "action_distribution": samples.get("action_distribution") or [],
        "turnover_series": samples.get("turnover") or [],
        "drawdown_series": samples.get("drawdown") or [],
        "policy_evaluation": portfolio.get("policy_evaluation") or {},
        "portfolio_trajectory": samples.get("policy_nav") or [],
        "reward_stack": (portfolio.get("reward_component_summary") or {}).get("by_split") or [],
        "policy_baseline_comparison": samples.get("policy_baseline_comparison") or [],
        "policy_nav": samples.get("policy_nav") or [],
        "guardrail": "D4 constrained portfolio RL telemetry is RESEARCH_ONLY diagnostics; no profit, broker, live, order, or deployable readiness claim.",
    }


def load_walk_forward_chart(*, run: str | None = None) -> dict[str, Any]:
    gate = load_walk_forward_latest(run=run, sample_limit=50)
    db = load_daily_db_summary(table_limit=0, flag_limit=0, window_limit=0)
    universe = load_universe_preview(limit=0)
    prediction = load_prediction_latest(sample_limit=0)
    if gate.get("status") == "NOT_STARTED":
        return gate
    verdict = gate.get("verdict") or {}
    samples = gate.get("samples") or {}
    fold_metrics = samples.get("fold_metrics") or []
    selected_strategy = verdict.get("selected_strategy")
    cost_rows = samples.get("cost_sensitivity") or []
    cost_bps = _cost_bp_values(cost_rows, selected_strategy=selected_strategy)
    d5_reasons = _as_string_list(verdict.get("reasons"))
    if any(bp not in set(cost_bps) for bp in D5_REQUIRED_COST_BPS):
        d5_reasons = _merge_string_lists(d5_reasons, ["D5_COST_SENSITIVITY_INCOMPLETE"])

    no_oos_retuning = verdict.get("no_oos_retuning") is True
    if not no_oos_retuning:
        d5_reasons = _merge_string_lists(d5_reasons, ["D5_NO_OOS_RETUNING_NOT_PROVEN"])

    purge_days = _finite_int(verdict.get("purge_days"))
    embargo_days = _finite_int(verdict.get("embargo_days"))
    min_required_purge_days = max(_finite_int(verdict.get("min_required_purge_days")) or D5_MIN_REQUIRED_PURGE_DAYS, D5_MIN_REQUIRED_PURGE_DAYS)
    min_required_embargo_days = max(_finite_int(verdict.get("min_required_embargo_days")) or D5_MIN_REQUIRED_EMBARGO_DAYS, D5_MIN_REQUIRED_EMBARGO_DAYS)
    if purge_days is None or purge_days < min_required_purge_days:
        d5_reasons = _merge_string_lists(d5_reasons, ["PURGE_DAYS_BELOW_REQUIRED_MIN"])
    if embargo_days is None or embargo_days < min_required_embargo_days:
        d5_reasons = _merge_string_lists(d5_reasons, ["EMBARGO_DAYS_BELOW_REQUIRED_MIN"])

    d4_state_contract = gate.get("d4_state_contract") if isinstance(gate.get("d4_state_contract"), dict) else {}
    d4_row_counts = d4_state_contract.get("row_counts") if isinstance(d4_state_contract.get("row_counts"), dict) else {}
    d4_state_contract_status = d4_state_contract.get("status")
    d4_observation_manifest_gate = d4_state_contract.get("gate")
    d4_observation_manifest_validation_status = d4_state_contract.get("observation_manifest_validation_status")
    d4_state_observation_rows = d4_row_counts.get("state_observations")
    d4_reward_action_ablation_rows = d4_row_counts.get("reward_action_ablations")
    d4_source_hash_count = d4_state_contract.get("source_hash_count") or d4_row_counts.get("source_hashes")
    d4_state_contract_artifacts_consumed = (
        verdict.get("d4_state_contract_artifacts_consumed") is True
        and d4_state_contract_status == "PASS"
        and d4_observation_manifest_gate == "D4_OBSERVATION_STATE_MANIFEST"
        and d4_observation_manifest_validation_status == "PASS"
        and _positive_number(d4_state_observation_rows)
        and _positive_number(d4_reward_action_ablation_rows)
        and _positive_number(d4_source_hash_count)
    )
    d4_artifact_issues = _as_string_list(verdict.get("d4_artifact_issues"))
    if not d4_state_contract_artifacts_consumed:
        d4_artifact_issues = _merge_string_lists(["D4_STATE_CONTRACT_EVIDENCE_MISSING_OR_STALE"], d4_artifact_issues)
        d5_reasons = _merge_string_lists(d5_reasons, d4_artifact_issues)
    effective_gate = _effective_daily_model_gate(
        db=db,
        universe=universe,
        prediction=prediction,
        gate_verdict=verdict,
        gate_status=gate.get("status"),
    )
    return {
        "status": gate.get("status"),
        "readiness_status": gate.get("readiness_status") or D5_RESEARCH_READINESS_STATUS,
        "run_id": gate.get("run_id"),
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "no_live_broker_order_readiness": True,
        "selected_strategy": verdict.get("selected_strategy"),
        "strategy_selection_policy": verdict.get("strategy_selection_policy"),
        "n_folds": verdict.get("n_folds"),
        "required_min_folds": verdict.get("required_min_folds"),
        "no_oos_retuning": no_oos_retuning,
        "purge_days": purge_days,
        "embargo_days": embargo_days,
        "min_required_purge_days": min_required_purge_days,
        "min_required_embargo_days": min_required_embargo_days,
        "fold_consistency": verdict.get("fold_consistency"),
        "reasons": d5_reasons,
        "effective_gate_blockers": effective_gate["effective_gate_blockers"],
        "price_basis": verdict.get("price_basis"),
        "universe_review_status": verdict.get("universe_review_status"),
        "cost_sensitivity_bp": cost_bps,
        "d4_state_contract": d4_state_contract,
        "d4_state_contract_status": d4_state_contract_status,
        "d4_observation_manifest_gate": d4_observation_manifest_gate,
        "d4_observation_manifest_validation_status": d4_observation_manifest_validation_status,
        "d4_reward_action_telemetry_sufficient_for_d4": verdict.get(
            "d4_reward_action_telemetry_sufficient_for_d4"
        ),
        "d4_state_contract_artifacts_consumed": d4_state_contract_artifacts_consumed,
        "d4_state_observation_rows": d4_state_observation_rows,
        "d4_artifact_issues": d4_artifact_issues,
        "d4_reward_action_ablation_rows": d4_reward_action_ablation_rows,
        "d4_source_hash_count": d4_source_hash_count,
        "prediction_manifest_sha": gate.get("prediction_manifest_sha"),
        "prediction_artifact_hashes": gate.get("prediction_artifact_hashes") or verdict.get("prediction_artifact_hashes") or {},
        "portfolio_manifest_sha": gate.get("portfolio_manifest_sha"),
        "portfolio_artifact_hashes": gate.get("portfolio_artifact_hashes") or verdict.get("portfolio_artifact_hashes") or {},
        "artifact_hashes": gate.get("artifact_hashes") or {},
        "fold_metrics": fold_metrics,
        "fold_windows": samples.get("folds") or [],
        "fold_assignments": samples.get("fold_assignments") or [],
        "no_trade_control": [row for row in fold_metrics if row.get("strategy") == "no_trade_cash"],
        "selected_fold_metrics": [
            row
            for row in fold_metrics
            if row.get("strategy") == verdict.get("selected_strategy") and row.get("control") == "actual"
        ],
        "shuffle_control": samples.get("shuffle_control") or [],
        "cost_sensitivity": samples.get("cost_sensitivity") or [],
        "rl_fold_metrics": samples.get("rl_fold_metrics") or [],
        "guardrail": "D5 walk-forward gate evidence only; NO-GO/WATCH reasons do not imply live or profit readiness.",
    }


def load_decision_cockpit() -> dict[str, Any]:
    dataset = load_dataset_latest(sample_limit=0)
    db = load_daily_db_summary(table_limit=0, flag_limit=0, window_limit=0)
    universe = load_universe_preview(limit=0)
    prediction = load_prediction_latest(sample_limit=0)
    portfolio = load_portfolio_latest(sample_limit=0)
    gate = load_walk_forward_latest(sample_limit=0)
    gate_verdict = gate.get("verdict") or {}
    portfolio_verdict = portfolio.get("verdict") or {}
    prediction_verdict = prediction.get("verdict") or {}
    effective_gate = _effective_daily_model_gate(
        db=db,
        universe=universe,
        prediction=prediction,
        gate_verdict=gate_verdict,
        gate_status=gate.get("status"),
    )

    blockers: list[dict[str, Any]] = []
    if dataset.get("price_basis") == "unknown" or prediction.get("price_basis") == "unknown":
        blockers.append(
            {
                "id": "PRICE_BASIS_UNKNOWN",
                "severity": "watch",
                "title": "가격 보정 기준 미확정",
                "evidence": "daily OHLCV price_basis=unknown; split/dividend adjusted/raw status is not proven.",
                "required_fix": "공식 adjusted/raw 기준과 분할·배당 처리 검증을 고정한 뒤 fresh validation을 다시 실행.",
            }
        )
    if dataset.get("universe_verdict") == "WATCH_HEURISTIC_UNIVERSE":
        blockers.append(
            {
                "id": "UNIVERSE_WATCH_HEURISTIC",
                "severity": "watch",
                "title": "유니버스가 휴리스틱 WATCH",
                "evidence": "KOSPI/KOSDAQ 보통주 분류는 적용됐지만 KRX/수동 검토 전까지 WATCH.",
                "required_fix": "ETF/ETN/스팩/우선주/리츠 제외 기준을 공식 메타데이터로 재검증.",
            }
        )
    for reason in gate_verdict.get("reasons") or []:
        if reason == "RL_POLICY_UNDERPERFORMS_D3_BASELINE":
            blockers.append(
                {
                    "id": reason,
                    "severity": "block",
                    "title": "RL 정책이 D3 베이스라인보다 약함",
                    "evidence": f"D4 delta_vs_best_d3={((portfolio.get('baseline_comparison') or {}).get('delta_vs_best_d3_total_net_return'))}",
                    "required_fix": "새 RL 후보는 D3 baseline과 shuffle/no-trade를 23bp 비용 후 fresh OOS에서 동시에 넘어야 함.",
                }
            )
        elif reason == "D4_RL_RESEARCH_ONLY_LOCK":
            blockers.append(
                {
                    "id": reason,
                    "severity": "block",
                    "title": "D4 RL은 연구 전용 잠금",
                    "evidence": f"D4 status={portfolio.get('status')} implementation_unlocked={portfolio_verdict.get('implementation_unlocked')}",
                    "required_fix": "D4 정책을 선택에 사용하지 않은 fresh OOS/forward 검증 통과 전에는 모델 빌드 잠금 유지.",
                }
            )
        elif reason not in {row["id"] for row in blockers}:
            blockers.append(
                {
                    "id": reason,
                    "severity": "block" if gate.get("status") == "NO-GO" else "watch",
                    "title": reason,
                    "evidence": "D5 gate_verdict reason.",
                    "required_fix": "사전등록된 검증 조건으로 원인 해소 후 재검증.",
                }
            )
    for reason in effective_gate["effective_gate_blockers"]:
        if reason not in {row["id"] for row in blockers}:
            blockers.append(
                {
                    "id": reason,
                    "severity": "block",
                    "title": reason,
                    "evidence": "Cross-stage effective model gate remains locked even if a generated artifact is optimistic.",
                    "required_fix": "D0 price basis, D1 universe review, D3 baseline, and D5 walk-forward gates must all pass before model build or GO summary.",
                }
            )

    return {
        "status": gate.get("status", "NOT_STARTED"),
        "overall_status": "MODEL_BUILD_LOCKED_NO_GO" if not effective_gate["model_build_allowed"] else "REVIEW_REQUIRED",
        "model_build_allowed": effective_gate["model_build_allowed"],
        "go_summary_allowed": effective_gate["go_summary_allowed"],
        "cards": [
            {"id": "D3", "label": "Baseline/Ranker", "status": prediction.get("status"), "severity": _status_severity(prediction.get("status")), "evidence": prediction_verdict.get("best_strategy_by_total_net_return")},
            {"id": "D4", "label": "Portfolio RL", "status": portfolio.get("status"), "severity": _status_severity(portfolio.get("status")), "evidence": portfolio_verdict.get("gate_dependency")},
            {"id": "D5", "label": "Walk-forward Gate", "status": gate.get("status"), "severity": _status_severity(gate.get("status")), "evidence": ",".join((gate_verdict.get("reasons") or [])[:3])},
            {"id": "LOCK", "label": "Model Build Lock", "status": "LOCKED", "severity": "block", "evidence": "model_build_allowed=false; go_summary_allowed=false"},
        ],
        "blockers": blockers,
        "usage_guide": [_usage_for_stage("D6"), _usage_for_stage("D7")],
        "can_do_after_development": [
            "D6에서 D0-D9 증거, gate blocker, provenance hash, 비용/통제군 결과를 한 화면에서 읽는다.",
            "D7에서 feature/regime/correlation/failure 진단 artifact가 생기면 실패 원인을 분해한다.",
            "Symbol drilldown으로 선행 0 코드 유지, OHLCV 기간, 가격 기준 unknown 경고를 확인한다.",
        ],
        "guardrail": "Decision cockpit is a lock explanation, not a profit/live/broker/order readiness claim.",
    }


def _cost_sensitivity_summary_by_cost(rows: Any) -> dict[int, dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        cost = _finite_float(row.get("cost_bp", row.get("cost_bps")))
        if cost is None:
            continue
        grouped.setdefault(int(round(cost)), []).append(row)

    summary: dict[int, dict[str, Any]] = {}
    for cost_bp, cost_rows in grouped.items():
        total_returns = [_finite_float(row.get("total_net_return")) for row in cost_rows]
        drawdowns = [_finite_float(row.get("max_drawdown")) for row in cost_rows]
        turnovers = [_finite_float(row.get("mean_turnover")) for row in cost_rows]
        finite_returns = [value for value in total_returns if value is not None]
        finite_drawdowns = [value for value in drawdowns if value is not None]
        finite_turnovers = [value for value in turnovers if value is not None]
        summary[cost_bp] = {
            "fold_rows": len(cost_rows),
            "mean_total_net_return": sum(finite_returns) / len(finite_returns) if finite_returns else None,
            "worst_total_net_return": min(finite_returns) if finite_returns else None,
            "worst_max_drawdown": min(finite_drawdowns) if finite_drawdowns else None,
            "mean_turnover": sum(finite_turnovers) / len(finite_turnovers) if finite_turnovers else None,
        }
    return summary


def load_scenario_lab() -> dict[str, Any]:
    """Generate read-only assumption/scenario cards from current Daily OHLCV evidence."""

    db = load_daily_db_summary(table_limit=0, flag_limit=0, window_limit=0)
    universe = load_universe_preview(limit=0)
    prediction = load_prediction_latest(sample_limit=0)
    portfolio = load_portfolio_latest(sample_limit=0)
    gate = load_walk_forward_latest(sample_limit=0)
    gate_chart = load_walk_forward_chart()

    gate_verdict = gate.get("verdict") or {}
    effective_gate = _effective_daily_model_gate(
        db=db,
        universe=universe,
        prediction=prediction,
        gate_verdict=gate_verdict,
        gate_status=gate.get("status"),
    )
    base_blockers = list(effective_gate["effective_gate_blockers"])
    cost_summary = _cost_sensitivity_summary_by_cost(gate_chart.get("cost_sensitivity"))

    d5_reasons = [str(reason) for reason in (gate_verdict.get("reasons") or [])]
    actual_costs = []
    for cost in gate_chart.get("cost_sensitivity_bp") or D5_REQUIRED_COST_BPS:
        parsed_cost = _finite_int(cost)
        if parsed_cost is not None:
            actual_costs.append(parsed_cost)
    costs = sorted(set(actual_costs or list(D5_REQUIRED_COST_BPS)))

    scenario_rows: list[dict[str, Any]] = []
    assumption_modes = [
        {
            "id": "current_evidence",
            "label": "현재 증거 기준",
            "assumption_changes": [],
            "remove_blockers": set(),
            "status": gate.get("status", "NO-GO"),
        },
        {
            "id": "data_repaired_hypothesis",
            "label": "D0/D1 수리 가정",
            "assumption_changes": [
                "price_basis_verified_by_artifact",
                "universe_official_or_manual_reviewed",
            ],
            "remove_blockers": {"D0_PRICE_BASIS_NOT_VERIFIED", "D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED"},
            "status": "HYPOTHESIS_ONLY",
        },
    ]
    for cost_bp in costs:
        for mode in assumption_modes:
            blockers = [blocker for blocker in base_blockers if blocker not in mode["remove_blockers"]]
            for reason in d5_reasons:
                if reason not in blockers:
                    blockers.append(reason)
            if int(cost_bp) != 23:
                blockers.append("COST_COUNTERFACTUAL_NOT_PRIMARY_23BP")
            summary = cost_summary.get(int(cost_bp), {})
            scenario_rows.append(
                {
                    "scenario_id": f"cost_{int(cost_bp)}bp_{mode['id']}",
                    "scenario_family": "evidence_assumption_grid",
                    "label": f"{mode['label']} · {int(cost_bp)}bp",
                    "cost_bps": int(cost_bp),
                    "purge_days": gate_chart.get("purge_days"),
                    "embargo_days": gate_chart.get("embargo_days"),
                    "min_required_purge_days": D5_MIN_REQUIRED_PURGE_DAYS,
                    "min_required_embargo_days": D5_MIN_REQUIRED_EMBARGO_DAYS,
                    "status": mode["status"],
                    "readiness_status": "SCENARIO_RESEARCH_ONLY_NO_MODEL_BUILD",
                    "model_build_allowed": False,
                    "go_summary_allowed": False,
                    "paper_forward_allowed": False,
                    "live_broker_order_allowed": False,
                    "assumption_changes": mode["assumption_changes"],
                    "blocking_reasons": blockers,
                    "observed_cost_summary": summary,
                    "required_next_artifacts": [
                        "fresh_oos_walk_forward_manifest.json",
                        "gate_verdict.json",
                        "baseline_delta_summary.json",
                    ],
                    "blocked_uses": [
                        "model_build_or_candidate_promotion",
                        "paper_forward_or_live_readiness_claims",
                        "live_broker_order",
                    ],
                }
            )

    scenario_rows.append(
        {
            "scenario_id": "model_generated_candidate_contract",
            "scenario_family": "model_generation_contract",
            "label": "새 후보 모델 생성 계약",
            "cost_bps": 23,
            "purge_days": D5_MIN_REQUIRED_PURGE_DAYS,
            "embargo_days": D5_MIN_REQUIRED_EMBARGO_DAYS,
            "min_required_purge_days": D5_MIN_REQUIRED_PURGE_DAYS,
            "min_required_embargo_days": D5_MIN_REQUIRED_EMBARGO_DAYS,
            "status": "HYPOTHESIS_ONLY",
            "readiness_status": "MODEL_SCENARIO_GENERATION_CONTRACT_ONLY",
            "model_build_allowed": False,
            "go_summary_allowed": False,
            "paper_forward_allowed": False,
            "live_broker_order_allowed": False,
            "assumption_changes": [
                "generate_candidate_from_registered_hypothesis",
                "compare_against_no_trade_shuffle_rule_supervised_baselines",
                "evaluate_0_23_46bp_costs_with_fresh_oos",
            ],
            "blocking_reasons": [
                *base_blockers,
                "MODEL_CANDIDATE_NOT_GENERATED",
                "FRESH_OOS_WALK_FORWARD_REQUIRED",
                "NEGATIVE_AND_BASELINE_CONTROLS_REQUIRED",
            ],
            "observed_cost_summary": cost_summary.get(23, {}),
            "required_next_artifacts": [
                "scenario_manifest.json",
                "candidate_generation_config.json",
                "fresh_oos_walk_forward_manifest.json",
                "cost_sensitivity.csv",
                "negative_controls.csv",
            ],
            "blocked_uses": [
                "model_build_or_candidate_promotion",
                "paper_forward_or_live_readiness_claims",
                "live_broker_order",
            ],
        }
    )

    return {
        "mode": "daily_ohlcv_scenario_lab",
        "platform_stage": "SCENARIO_GENERATOR_MVP",
        "scenario_generation_available": True,
        "model_run_generation_available": False,
        "read_only": True,
        "status": "RESEARCH_ONLY",
        "scenario_count": len(scenario_rows),
        "assumption_dimensions": {
            "cost_bps": costs,
            "purge_days_min": D5_MIN_REQUIRED_PURGE_DAYS,
            "embargo_days_min": D5_MIN_REQUIRED_EMBARGO_DAYS,
            "data_guardrail_modes": ["current_evidence", "data_repaired_hypothesis"],
            "required_controls": ["no_trade", "shuffle_control", "rule_baseline", "supervised_baseline"],
        },
        "current_evidence": {
            "d0_price_basis": db.get("price_basis"),
            "d1_universe_verdict": universe.get("verdict"),
            "d3_status": prediction.get("status"),
            "d4_status": portfolio.get("status"),
            "d5_status": gate.get("status"),
            "readiness_status": gate.get("readiness_status"),
            "effective_gate_blockers": base_blockers,
        },
        "model_input_contract": {
            "allowed_inputs": [
                "registered_hypothesis",
                "feature_set_manifest_sha",
                "split_manifest_sha",
                "cost_grid_bps",
                "baseline_control_manifest_sha",
            ],
            "required_outputs": [
                "scenario_manifest.json",
                "candidate_generation_config.json",
                "fresh_oos_walk_forward_manifest.json",
                "gate_verdict.json",
            ],
            "must_not_generate": [
                "profit_guarantee",
                "live_order",
                "broker_readiness",
                "paper_forward_unlock",
            ],
        },
        "scenario_rows": scenario_rows,
        "guardrail": "Scenario Lab generates research-only assumptions from evidence; it is not a profit/live/broker/order or model-build readiness claim.",
    }


def _latest_manifest_paths(root: Path, manifest_name: str, *, limit: int) -> list[Path]:
    safe_limit = _bounded_limit(limit, default=25, maximum=MAX_LIMIT)
    if safe_limit == 0:
        return []
    root = Path(root).resolve()
    if not root.exists():
        return []
    manifests = [
        path / manifest_name
        for path in root.iterdir()
        if path.is_dir() and (path / manifest_name).is_file()
    ]
    return sorted(manifests, key=lambda path: path.stat().st_mtime, reverse=True)[:safe_limit]


def _scenario_run_ledger_row(path: Path) -> dict[str, Any]:
    manifest = _load_json(path)
    gate = manifest.get("gate_verdict_summary") or {}
    return {
        "run_id": manifest.get("run_id") or path.parent.name,
        "generated_at": manifest.get("generated_at"),
        "status": manifest.get("status", "NO-GO"),
        "readiness_status": manifest.get("readiness_status", "D5_NO_GO_RESEARCH_ONLY_GATE"),
        "selected_strategy": gate.get("selected_strategy"),
        "n_folds": gate.get("n_folds"),
        "purge_days": gate.get("purge_days"),
        "embargo_days": gate.get("embargo_days"),
        "cost_sensitivity_bp": gate.get("cost_sensitivity_bp") or [0, 23, 46],
        "blocking_reasons": gate.get("reasons", []),
        "artifact_paths": manifest.get("artifact_paths", {}),
        "artifact_dirs": manifest.get("artifact_dirs", {}),
        "config": manifest.get("config", {}),
        "guardrail": manifest.get("guardrail", RESEARCH_GUARDRAIL),
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "no_live_broker_order_readiness": True,
    }


def _scenario_batch_ledger_row(path: Path, *, row_limit: int) -> dict[str, Any]:
    manifest = _load_json(path)
    comparison_rows = manifest.get("comparison_rows") if isinstance(manifest.get("comparison_rows"), list) else []
    safe_row_limit = _bounded_limit(row_limit, default=25, maximum=MAX_LIMIT)
    return {
        "batch_id": manifest.get("batch_id") or path.parent.name,
        "generated_at": manifest.get("generated_at"),
        "status": manifest.get("status", "RESEARCH_ONLY"),
        "platform_stage": manifest.get("platform_stage", "SCENARIO_BATCH_RUNNER_MVP"),
        "scenario_count": manifest.get("scenario_count", len(comparison_rows)),
        "completed_count": manifest.get("completed_count"),
        "failed_count": manifest.get("failed_count"),
        "gate_status_counts": manifest.get("gate_status_counts", {}),
        "comparison_rows_total": len(comparison_rows),
        "comparison_rows_truncated": len(comparison_rows) > safe_row_limit,
        "comparison_rows": comparison_rows[:safe_row_limit],
        "artifact_paths": manifest.get("artifact_paths", {}),
        "guardrail": manifest.get("guardrail", RESEARCH_GUARDRAIL),
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "no_live_broker_order_readiness": True,
    }


def load_scenario_run_ledger(limit: int = 25) -> dict[str, Any]:
    """Read generated single-run and batch scenario manifests for dashboard comparison."""

    safe_limit = _bounded_limit(limit, default=25, maximum=MAX_LIMIT)
    run_rows = [_scenario_run_ledger_row(path) for path in _latest_manifest_paths(DEFAULT_SCENARIO_ROOT, "scenario_manifest.json", limit=safe_limit)]
    batch_rows = [
        _scenario_batch_ledger_row(path, row_limit=safe_limit)
        for path in _latest_manifest_paths(DEFAULT_SCENARIO_BATCH_ROOT, "scenario_batch_manifest.json", limit=safe_limit)
    ]
    return {
        "mode": "daily_ohlcv_scenario_run_ledger",
        "platform_stage": "SCENARIO_BATCH_RUNNER_MVP",
        "read_only": True,
        "dashboard_mutation_available": False,
        "cli_model_run_generation_available": True,
        "model_run_generation_available": True,
        "status": "RESEARCH_ONLY",
        "limit": safe_limit,
        "scenario_run_count": len(run_rows),
        "batch_count": len(batch_rows),
        "runs": run_rows,
        "batches": batch_rows,
        "quick_start_commands": [
            "py -3.11 -m stom_rl.daily_scenario_batch --emit-template",
            "py -3.11 -m stom_rl.daily_scenario_batch --plan scenario_batch_plan.json --batch-id scenario_batch_001 --overwrite",
            "py -3.11 -m stom_rl.daily_scenario_runner --run-id scenario_single_001 --overwrite --max-symbols 8 --max-rows-per-symbol 120 --episodes 3 --candidate-limit 10 --max-positions 3 --n-folds 5 --top-k 10",
        ],
        "required_controls": ["no_trade", "shuffle_control", "rule_baseline", "supervised_baseline", "0/23/46bp cost sensitivity"],
        "guardrail": "Read-only scenario run ledger. Runs are generated only by explicit CLI commands; no profit/live/broker/order or paper-forward readiness is inferred.",
    }


RL_GUIDE_DISPLAY_CAPITAL_KRW = 10_000_000


def _build_rl_guide_signal_quality_summary() -> dict[str, Any]:
    run_dir = _latest_run_dir(DEFAULT_SIGNAL_QUALITY_ROOT, required_file="signal_quality_manifest.json")
    manifest_path = run_dir / "signal_quality_manifest.json" if run_dir is not None else None
    manifest = _load_json_if_exists(manifest_path)

    batch_dir = _latest_artifact_dir(DEFAULT_SIGNAL_QUALITY_BATCH_ROOT, required_file="scenario_batch_manifest.json")
    batch_path = batch_dir / "scenario_batch_manifest.json" if batch_dir is not None else None
    batch_manifest = _load_json_if_exists(batch_path)

    batch_runs = batch_manifest.get("runs") if isinstance(batch_manifest.get("runs"), list) else []
    plan = batch_manifest.get("plan") if isinstance(batch_manifest.get("plan"), dict) else {}
    plan_scenarios = plan.get("scenarios") if isinstance(plan.get("scenarios"), list) else []
    scenario_cards: list[dict[str, Any]] = []
    source_rows = batch_runs if batch_runs else plan_scenarios
    for row in source_rows[:8]:
        if not isinstance(row, dict):
            continue
        scenario_cards.append(
            {
                "scenario_id": row.get("scenario_id"),
                "run_id": row.get("run_id"),
                "diagnostic_focus": row.get("diagnostic_focus"),
                "hypothesis": row.get("hypothesis"),
                "status": row.get("status") or "WATCH",
                "promotion_status": row.get("promotion_status") or "NO-GO_RESEARCH_ONLY",
                "assumption_tags": row.get("assumption_tags") or [],
                "row_counts": row.get("row_counts") or manifest.get("row_counts") or {},
            }
        )

    required_artifacts = manifest.get("required_artifacts") if isinstance(manifest.get("required_artifacts"), dict) else {}
    row_counts = manifest.get("row_counts") if isinstance(manifest.get("row_counts"), dict) else {}
    return {
        "schema_version": "daily_rl_signal_quality_summary.v1",
        "status": manifest.get("status") or "MISSING_SIGNAL_QUALITY_AUDIT",
        "run_id": manifest.get("run_id") or "MISSING_SIGNAL_QUALITY_AUDIT",
        "generated_at": manifest.get("generated_at"),
        "platform_stage": manifest.get("platform_stage") or "D3_D4_SIGNAL_QUALITY_AUDIT_MVP",
        "result_verdict": manifest.get("result_verdict") or "WATCH_DIAGNOSTIC_ONLY",
        "promotion_status": manifest.get("promotion_status") or "NO-GO_RESEARCH_ONLY",
        "read_only_artifact": manifest.get("read_only_artifact", True),
        "score_column": manifest.get("score_column") or "score_supervised_linear_ranker",
        "threshold_policy": manifest.get("threshold_policy") or "frozen_absolute_no_quantile_search_no_oos_retune",
        "cost_round_trip_bp": manifest.get("cost_round_trip_bp") or 23,
        "cost_sensitivity_bp": manifest.get("cost_sensitivity_bp") or [0, 23, 46],
        "baseline_controls": manifest.get("baseline_controls") or ["no_trade_cash", "shuffle_control", "equal_weight_topk", "frozen_d3_baseline"],
        "baseline_controls_measured": bool(manifest.get("baseline_controls_measured")),
        "row_counts": row_counts,
        "splits": manifest.get("splits") or ["train", "val", "test"],
        "fold_ids": manifest.get("fold_ids") or ["F01", "F02", "F03", "F04", "F05"],
        "required_artifacts": required_artifacts,
        "past_only_proxy_sources": manifest.get("past_only_proxy_sources") or {},
        "no_future_label_policy": manifest.get("no_future_label_policy") or "future_return_1d is evaluation_label_only after bucket/proxy construction",
        "result_doc_path": _path_text(LATEST_SIGNAL_QUALITY_RESULT_DOC),
        "governance_index_path": _path_text(LATEST_RESEARCH_GOVERNANCE_INDEX),
        "manifest_path": _path_text(manifest_path),
        "batch_manifest": {
            "batch_id": batch_manifest.get("batch_id") or "MISSING_SIGNAL_QUALITY_BATCH",
            "status": batch_manifest.get("status") or "MISSING_SIGNAL_QUALITY_BATCH",
            "scenario_count": _to_int(batch_manifest.get("scenario_count"), len(scenario_cards)) or len(scenario_cards),
            "completed_count": _to_int(batch_manifest.get("completed_count"), 0),
            "failed_count": _to_int(batch_manifest.get("failed_count"), 0),
            "gate_status_counts": batch_manifest.get("gate_status_counts") or {},
            "cost_sensitivity_bp": batch_manifest.get("cost_sensitivity_bp") or manifest.get("cost_sensitivity_bp") or [0, 23, 46],
            "path": _path_text(batch_path),
        },
        "scenario_cards": scenario_cards,
        "limitations": [
            "Fold consistency is mixed: favorable folds cannot be cherry-picked into promotion.",
            "Baseline controls are diagnostics, not deployable portfolio optimization.",
            "Lagged drawdown proxies are past-only generated artifacts, not yet validated OHLCV market-regime data.",
            "No D5/model-build/paper-forward/live gate is opened by this audit.",
        ],
        "next_allowed_research": "Preregistered past-only market-regime data quality audit before new D4 overlay tuning.",
        "guardrail": "Signal-quality summary is a read-only research diagnostic. No profit claim, no live/broker/orders, no paper-forward/model-build unlock.",
    }


def _build_rl_guide_scenario_generator(signal_summary: dict[str, Any]) -> dict[str, Any]:
    controls = signal_summary.get("baseline_controls") or ["no_trade_cash", "shuffle_control", "equal_weight_topk", "frozen_d3_baseline"]
    cost_sensitivity = signal_summary.get("cost_sensitivity_bp") or [0, 23, 46]
    templates = [
        {
            "template_id": "D3_D4_SIGNAL_QUALITY_AUDIT",
            "title_ko": "D3/D4 신호 품질 감사",
            "lane_id": "SIGNAL_QUALITY_AUDIT",
            "status": "WATCH_DIAGNOSTIC_ONLY",
            "hypothesis_ko": "score magnitude, margin, confidence가 다음날 연구 수익과 일관되게 연결되는지 확인합니다.",
            "assumption_tags": ["signal_quality", "score_margin", "confidence", "no_retune"],
            "required_artifacts": [
                "signal_quality_bucket_metrics.csv",
                "signal_quality_rank_correlations.csv",
                "baseline_control_metrics.csv",
                "signal_quality_leakage_audit.json",
            ],
            "plan_json_draft": {
                "schema_version": 1,
                "kind": "daily_ohlcv_research_scenario_plan_draft",
                "draft_only": True,
                "template_id": "D3_D4_SIGNAL_QUALITY_AUDIT",
                "default_cost_bp": 23,
                "cost_sensitivity_bp": cost_sensitivity,
                "baseline_controls": controls,
                "scenarios": [
                    {"scenario_id": "score_magnitude_audit_v2", "diagnostic_focus": "score_magnitude_bucket", "status": "DRAFT"},
                    {"scenario_id": "score_margin_audit_v2", "diagnostic_focus": "score_margin_bucket", "status": "DRAFT"},
                    {"scenario_id": "confidence_bucket_audit_v2", "diagnostic_focus": "d3_confidence_bucket", "status": "DRAFT"},
                ],
                "guardrails": ["research_only", "no_live_broker_orders", "no_profit_claims", "D5_NO_GO_until_fresh_gates_pass"],
            },
        },
        {
            "template_id": "PAST_ONLY_MARKET_REGIME_AUDIT",
            "title_ko": "Past-only 시장 국면 데이터 품질 감사",
            "lane_id": "MARKET_REGIME_DATA_QUALITY",
            "status": "NEXT_RECOMMENDED_RESEARCH",
            "hypothesis_ko": "검증된 일봉 OHLCV에서 미래값 없이 volatility, drawdown, breadth, dispersion proxy를 만들 수 있는지 확인합니다.",
            "assumption_tags": ["market_regime", "past_only", "data_quality", "no_future_label"],
            "required_artifacts": [
                "price_basis_audit.csv",
                "universe_breadth_diagnostics.csv",
                "past_only_regime_proxy_metrics.csv",
                "market_regime_leakage_audit.json",
            ],
            "plan_json_draft": {
                "schema_version": 1,
                "kind": "daily_ohlcv_research_scenario_plan_draft",
                "draft_only": True,
                "template_id": "PAST_ONLY_MARKET_REGIME_AUDIT",
                "default_cost_bp": 23,
                "cost_sensitivity_bp": cost_sensitivity,
                "baseline_controls": controls,
                "scenarios": [
                    {"scenario_id": "price_basis_regime_audit_v1", "diagnostic_focus": "adjusted_raw_split_dividend_basis", "status": "DRAFT"},
                    {"scenario_id": "breadth_missingness_audit_v1", "diagnostic_focus": "universe_breadth_and_missing_data", "status": "DRAFT"},
                    {"scenario_id": "past_only_proxy_stability_v1", "diagnostic_focus": "volatility_drawdown_breadth_proxy_stability", "status": "DRAFT"},
                ],
                "guardrails": ["research_only", "past_only_features", "no_oos_retune", "no_live_broker_orders", "no_profit_claims"],
            },
        },
        {
            "template_id": "D4_RL_OVERLAY_ABLATION",
            "title_ko": "D4 RL 위험 Overlay 보상/행동 ablation",
            "lane_id": "D4_RL_RISK_OVERLAY",
            "status": "BLOCKED_UNTIL_DATA_AUDIT",
            "hypothesis_ko": "D3 후보를 대체하지 않고 현금/감축/리밸런싱 overlay가 drawdown과 비용을 줄이는지 비교합니다.",
            "assumption_tags": ["d4_rl_overlay", "reward_ablation", "risk_only", "d5_no_go_locked"],
            "required_artifacts": [
                "state_observations.csv",
                "reward_breakdown.csv",
                "action_distribution.csv",
                "walk_forward_gate_manifest.json",
            ],
            "plan_json_draft": {
                "schema_version": 1,
                "kind": "daily_ohlcv_research_scenario_plan_draft",
                "draft_only": True,
                "template_id": "D4_RL_OVERLAY_ABLATION",
                "default_cost_bp": 23,
                "cost_sensitivity_bp": cost_sensitivity,
                "baseline_controls": controls,
                "scenarios": [
                    {"scenario_id": "baseline_relative_reward_v1", "diagnostic_focus": "reward_minus_frozen_d3_daily_return", "status": "DRAFT_BLOCKED"},
                    {"scenario_id": "risk_only_overlay_reward_v1", "diagnostic_focus": "drawdown_turnover_concentration_penalties", "status": "DRAFT_BLOCKED"},
                ],
                "guardrails": ["research_only", "no_live_broker_orders", "no_paper_forward", "D5_NO_GO_blocks_promotion"],
            },
        },
    ]
    return {
        "schema_version": "daily_rl_scenario_generator.v1",
        "status": "READ_ONLY_DRAFT_GENERATOR",
        "read_only": True,
        "execution_allowed": False,
        "template_count": len(templates),
        "default_template_id": "D3_D4_SIGNAL_QUALITY_AUDIT",
        "export_contract": "copy_or_download_json_draft_only; run only through explicit preregistered CLI outside this read-only dashboard",
        "templates": templates,
        "guardrail": "Scenario generator emits fixed JSON drafts only. It does not run training, submit broker orders, unlock paper-forward, or claim profitability.",
    }


def _build_rl_guide_market_regime_readiness(signal_summary: dict[str, Any]) -> dict[str, Any]:
    signal_available = (
        signal_summary.get("status") == "COMPLETED_RESEARCH_ONLY"
        and signal_summary.get("run_id") not in {None, "", "MISSING_SIGNAL_QUALITY_AUDIT"}
        and bool(signal_summary.get("manifest_path"))
    )
    readiness_checks = [
        {
            "check": "signal_quality_artifacts_available",
            "status": "PASS" if signal_available else "BLOCKED",
            "completion_pct": 100 if signal_available else 0,
            "evidence": signal_summary.get("manifest_path") or "MISSING_SIGNAL_QUALITY_AUDIT_MANIFEST",
        },
        {"check": "price_basis_certified", "status": "BLOCKED", "completion_pct": 35, "evidence": "D0 price basis still requires adjusted/raw/split/dividend audit"},
        {"check": "universe_breadth_validated", "status": "WATCH", "completion_pct": 55, "evidence": "D1 universe remains heuristic/WATCH"},
        {
            "check": "past_only_proxy_contract",
            "status": "WATCH" if signal_available else "BLOCKED",
            "completion_pct": 70 if signal_available else 0,
            "evidence": "signal-quality audit emits past-only proxy source timing but not full OHLCV regime validation" if signal_available else "blocked until signal-quality artifacts exist",
        },
        {"check": "promotion_gates_locked", "status": "PASS", "completion_pct": 100, "evidence": "D5/model-build/paper-forward/live remain NO-GO/locked"},
    ]
    maturity_score = round(
        sum((_to_float(row.get("completion_pct"), 0.0) or 0.0) for row in readiness_checks) / len(readiness_checks)
    )
    return {
        "schema_version": "daily_rl_market_regime_readiness.v1",
        "status": "NEXT_RESEARCH_READY_FOR_PREREGISTRATION" if signal_available else "BLOCKED_MISSING_SIGNAL_QUALITY_AUDIT",
        "maturity_score_pct": maturity_score,
        "recommended_doc_path": "docs/stom_daily_ohlcv_market_regime_data_quality_prereg_2026-06-18.md",
        "source_signal_quality_run_id": signal_summary.get("run_id") if signal_available else None,
        "readiness_checks": readiness_checks,
        "required_inputs": [
            "validated daily OHLCV price-basis manifest",
            "universe breadth/missingness diagnostics",
            "past-only volatility/drawdown/breadth/dispersion proxy definitions",
            "train/val/test + fold windows with no retune",
            "0/23/46bp cost sensitivity and no-trade/shuffle/frozen-D3 baselines",
        ],
        "blocked_gates": ["D0_PRICE_BASIS", "D1_UNIVERSE", "D5_NO_GO", "MODEL_BUILD_LOCKED", "PAPER_FORWARD_LOCKED", "LIVE_BROKER_ORDER_LOCKED"],
        "ai_guidance_format": {
            "next_research_lane": "past_only_market_regime_data_quality_audit",
            "objective": "validate whether regime proxies are reliable enough to become D4 state candidates",
            "must_not_use": ["future_return_1d_as_feature", "post_hoc_threshold_tuning", "single_fold_cherry_pick"],
            "acceptance_gate": "documented preregistration + generated manifest + leakage audit + baseline controls",
        },
        "score_inputs": readiness_checks,
        "guardrail": "Readiness score means the next audit can be specified; it does not mean market-regime proxies are validated or tradable.",
    }


def _build_rl_guide_improvement_queue(signal_summary: dict[str, Any]) -> dict[str, Any]:
    items = [
        {
            "id": "IQ001",
            "priority": 1,
            "title_ko": "Past-only market-regime data quality audit",
            "source_limitation": "Signal-quality audit uses lagged generated drawdown proxies, not a fully validated OHLCV regime dataset.",
            "next_action": "Create preregistered market-regime data-quality audit and generate price-basis/breadth/proxy stability artifacts.",
            "required_artifacts": ["market_regime_prereg.md", "price_basis_audit.csv", "past_only_regime_proxy_metrics.csv", "market_regime_leakage_audit.json"],
            "acceptance_gate": "No future-label features, split/fold no-retune, 0/23/46bp rows, no-trade/shuffle/frozen-D3 controls.",
            "status": "NEXT_RECOMMENDED",
            "blocker_status": "BLOCKED_D0_D1_DATA_GOVERNANCE",
        },
        {
            "id": "IQ002",
            "priority": 2,
            "title_ko": "Signal-quality result dashboard binding",
            "source_limitation": "Users need latest verdict, row counts, and artifact links without opening raw manifests.",
            "next_action": "Keep latest signal-quality summary and scenario comparison visible on Daily RL Guide.",
            "required_artifacts": ["signal_quality_manifest.json", "scenario_batch_manifest.json", "dated_result_doc.md"],
            "acceptance_gate": "Dashboard shows WATCH/NO-GO and locked promotion flags.",
            "status": "IMPLEMENTED_ON_PAGE",
            "blocker_status": "NO_PROMOTION_UNLOCKED",
        },
        {
            "id": "IQ003",
            "priority": 3,
            "title_ko": "Scenario plan JSON drafts",
            "source_limitation": "Users need a fixed scenario format before asking AI agents to run more experiments.",
            "next_action": "Use read-only plan draft templates and require CLI/preregistration before execution.",
            "required_artifacts": ["scenario_plan_draft.json", "scenario_batch_manifest.json"],
            "acceptance_gate": "Draft carries guardrails, cost, baselines, controls, and blocked live/broker/order flags.",
            "status": "IMPLEMENTED_ON_PAGE",
            "blocker_status": "READ_ONLY_DASHBOARD_NO_EXECUTION",
        },
        {
            "id": "IQ004",
            "priority": 4,
            "title_ko": "D4 overlay action/reward redesign",
            "source_limitation": "Current D4 tabular Q overlay is weaker than the best D3 baseline and D5 remains NO-GO.",
            "next_action": "Only after data-quality audit, preregister action/reward ablation for risk-only overlay candidates.",
            "required_artifacts": ["state_observations.csv", "reward_breakdown.csv", "action_distribution.csv", "walk_forward_gate_manifest.json"],
            "acceptance_gate": "Fold-consistent D3 delta, lower drawdown/turnover, cost stress survives, D5 no-retune gate passes.",
            "status": "BLOCKED",
            "blocker_status": "BLOCKED_D5_NO_GO",
        },
        {
            "id": "IQ005",
            "priority": 5,
            "title_ko": "Page maturity evidence loop",
            "source_limitation": "Dashboard visuals must be scored separately from research promotion readiness.",
            "next_action": "Maintain numeric page maturity, scenario-platform maturity, and live-readiness=0% reporting.",
            "required_artifacts": ["daily_rl_env_guide_api_payload", "frontend build", "focused dashboard tests"],
            "acceptance_gate": "Feature completion can reach 100% while live/paper/model readiness remains locked.",
            "status": "IMPLEMENTED_ON_PAGE",
            "blocker_status": "NO_LIVE_READINESS_BY_DESIGN",
        },
    ]
    return {
        "schema_version": "daily_rl_ai_improvement_queue.v1",
        "status": "AI_READABLE_QUEUE_AVAILABLE",
        "source_run_id": signal_summary.get("run_id"),
        "items": items,
        "ai_guidance_format": {
            "queue_policy": "highest_priority_unblocked_research_first",
            "allowed_next_action": "write_preregistration_or_run_research_only_cli",
            "blocked_actions": ["live_trading", "broker_order", "paper_forward_unlock", "profit_claim", "threshold_tuning_without_preregistration"],
        },
        "guardrail": "Improvement queue is instruction metadata for research agents; it is not an execution order or trading signal.",
    }


def _build_rl_guide_scenario_comparison(signal_summary: dict[str, Any]) -> dict[str, Any]:
    batch = signal_summary.get("batch_manifest") if isinstance(signal_summary.get("batch_manifest"), dict) else {}
    cards = signal_summary.get("scenario_cards") if isinstance(signal_summary.get("scenario_cards"), list) else []
    return {
        "schema_version": "daily_rl_scenario_comparison.v1",
        "status": "SCENARIO_COMPARISON_AVAILABLE",
        "batch_id": batch.get("batch_id"),
        "scenario_count": batch.get("scenario_count"),
        "completed_count": batch.get("completed_count"),
        "failed_count": batch.get("failed_count"),
        "gate_status_counts": batch.get("gate_status_counts") or {},
        "cost_sensitivity_bp": batch.get("cost_sensitivity_bp") or signal_summary.get("cost_sensitivity_bp") or [0, 23, 46],
        "cards": cards,
        "columns": ["scenario_id", "diagnostic_focus", "status", "promotion_status", "row_counts", "hypothesis"],
        "guardrail": "Scenario comparison exposes WATCH/NO-GO diagnostics only; PASS would still require fresh promotion gates.",
    }


def _build_rl_guide_page_maturity_report(
    *,
    scenario_generator: dict[str, Any],
    signal_summary: dict[str, Any],
    market_regime_readiness: dict[str, Any],
    improvement_queue: dict[str, Any],
    scenario_comparison: dict[str, Any],
) -> dict[str, Any]:
    templates = scenario_generator.get("templates") if isinstance(scenario_generator.get("templates"), list) else []
    queue_items = improvement_queue.get("items") if isinstance(improvement_queue.get("items"), list) else []
    comparison_cards = scenario_comparison.get("cards") if isinstance(scenario_comparison.get("cards"), list) else []
    batch = signal_summary.get("batch_manifest") if isinstance(signal_summary.get("batch_manifest"), dict) else {}
    signal_available = signal_summary.get("status") == "COMPLETED_RESEARCH_ONLY" and signal_summary.get("run_id") not in {None, "", "MISSING_SIGNAL_QUALITY_AUDIT"}
    batch_complete = (
        _to_int(batch.get("completed_count"), 0) == _to_int(batch.get("scenario_count"), -1)
        and _to_int(batch.get("failed_count"), 1) == 0
    )
    priority_completion = [
        {
            "priority": 1,
            "feature": "Dashboard Scenario Generator",
            "completion_pct": 100 if len(templates) >= 3 and scenario_generator.get("execution_allowed") is False else 0,
            "status": "IMPLEMENTED_READ_ONLY" if len(templates) >= 3 and scenario_generator.get("execution_allowed") is False else "MISSING_OR_UNSAFE",
            "evidence": "scenario_generator.templates[].plan_json_draft",
        },
        {
            "priority": 2,
            "feature": "Signal-quality Result Integration",
            "completion_pct": 100 if signal_available and bool(signal_summary.get("row_counts")) else 0,
            "status": "IMPLEMENTED_ARTIFACT_BACKED" if signal_available and bool(signal_summary.get("row_counts")) else "MISSING_SIGNAL_QUALITY_ARTIFACT",
            "evidence": "signal_quality_audit_summary",
        },
        {
            "priority": 3,
            "feature": "Past-only Market-regime Readiness",
            "completion_pct": 100 if market_regime_readiness.get("readiness_checks") else 0,
            "status": "IMPLEMENTED_AS_READINESS" if market_regime_readiness.get("readiness_checks") else "MISSING_READINESS_SECTION",
            "evidence": "market_regime_audit_readiness",
        },
        {
            "priority": 4,
            "feature": "AI-readable Improvement Queue",
            "completion_pct": 100 if len(queue_items) >= 5 else 0,
            "status": "IMPLEMENTED_FIXED_FORMAT" if len(queue_items) >= 5 else "MISSING_QUEUE_ITEMS",
            "evidence": "improvement_queue.items",
        },
        {
            "priority": 5,
            "feature": "Scenario Comparison and Maturity Reporting",
            "completion_pct": 100 if len(comparison_cards) >= 5 and batch_complete else 0,
            "status": "IMPLEMENTED_NUMERIC" if len(comparison_cards) >= 5 and batch_complete else "MISSING_COMPARISON_EVIDENCE",
            "evidence": "scenario_comparison + page_maturity_report",
        },
    ]
    implementation_completion = round(
        sum((_to_float(row.get("completion_pct"), 0.0) or 0.0) for row in priority_completion) / len(priority_completion)
    )
    data_governance_maturity = _to_int(market_regime_readiness.get("maturity_score_pct"), 0) or 0
    raw_scenario_platform = round(
        (
            (_to_float(priority_completion[0]["completion_pct"], 0.0) or 0.0)
            + (_to_float(priority_completion[1]["completion_pct"], 0.0) or 0.0)
            + (_to_float(priority_completion[4]["completion_pct"], 0.0) or 0.0)
        )
        / 3
    )
    no_go_cap_active = signal_summary.get("promotion_status") == "NO-GO_RESEARCH_ONLY"
    scenario_platform_maturity = min(raw_scenario_platform, 86 if no_go_cap_active else 100)
    raw_research_readiness = round(((100 if signal_available else 0) + data_governance_maturity) / 2)
    research_readiness = min(raw_research_readiness, 74 if no_go_cap_active else 100)
    page_maturity = round(
        implementation_completion * 0.45
        + scenario_platform_maturity * 0.25
        + research_readiness * 0.15
        + data_governance_maturity * 0.15
    )
    score_inputs = {
        "priority_completion": priority_completion,
        "raw_scenario_platform_maturity_pct": raw_scenario_platform,
        "scenario_platform_cap": 86 if no_go_cap_active else 100,
        "raw_research_readiness_pct": raw_research_readiness,
        "research_readiness_cap": 74 if no_go_cap_active else 100,
        "data_governance_source": "market_regime_audit_readiness.maturity_score_pct",
    }
    return {
        "schema_version": "daily_rl_page_maturity_report.v1",
        "status": "FEATURES_IMPLEMENTED_RESEARCH_GATES_BLOCKED" if implementation_completion == 100 else "FEATURES_INCOMPLETE_OR_MISSING_EVIDENCE",
        "implementation_completion_pct": implementation_completion,
        "page_maturity_pct": page_maturity,
        "scenario_platform_maturity_pct": scenario_platform_maturity,
        "research_readiness_pct": research_readiness,
        "data_governance_maturity_pct": data_governance_maturity,
        "live_trading_readiness_pct": 0,
        "model_build_readiness_pct": 0,
        "paper_forward_readiness_pct": 0,
        "priority_completion": priority_completion,
        "score_inputs": score_inputs,
        "score_method": "Scores are derived from payload evidence availability, scenario batch completion, readiness checks, and explicit NO-GO caps; live/model/paper readiness stays 0 while D5 and data-governance blockers remain active.",
        "remaining_blockers": ["D0_PRICE_BASIS", "D1_UNIVERSE", "D5_NO_GO", "MODEL_BUILD_LOCKED", "PAPER_FORWARD_LOCKED", "LIVE_BROKER_ORDER_LOCKED"],
        "guardrail": "A high page maturity score means the research dashboard is more usable; it is not profitability, paper-forward, or live-trading readiness.",
    }
_ALLOWED_RESEARCH_WORKFLOW_IDS = (
    "D0_D1_DATA_GOVERNANCE_REVIEW",
    "D3_D4_SIGNAL_QUALITY_AUDIT",
    "PAST_ONLY_MARKET_REGIME_AUDIT",
    "D4_RL_OVERLAY_ABLATION",
    "SCENARIO_BATCH_RESEARCH_ONLY",
    "HYPOTHESIS_REJECTION_AUDIT",
)


def _build_research_workflow_catalog_payload(
    *,
    signal_summary: dict[str, Any] | None = None,
    scenario_generator: dict[str, Any] | None = None,
    market_regime_readiness: dict[str, Any] | None = None,
    improvement_queue: dict[str, Any] | None = None,
    scenario_comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    signal_summary = signal_summary or _build_rl_guide_signal_quality_summary()
    scenario_generator = scenario_generator or _build_rl_guide_scenario_generator(signal_summary)
    market_regime_readiness = market_regime_readiness or _build_rl_guide_market_regime_readiness(signal_summary)
    improvement_queue = improvement_queue or _build_rl_guide_improvement_queue(signal_summary)
    scenario_comparison = scenario_comparison or _build_rl_guide_scenario_comparison(signal_summary)
    batch = signal_summary.get("batch_manifest") if isinstance(signal_summary.get("batch_manifest"), dict) else {}
    workflow_items = [
        {
            "workflow_id": "D0_D1_DATA_GOVERNANCE_REVIEW",
            "title_ko": "D0/D1 데이터 거버넌스 확인",
            "stage": "D0-D1",
            "status": "BLOCKED_WITH_REVIEW_PATH",
            "approval_required": True,
            "approval_status": "REQUIRES_DATED_PREREG_OR_APPROVED_PLAN",
            "trigger_status": "INTENT_ONLY_NOT_EXECUTED_BY_BROWSER",
            "blocked_by": ["D0_PRICE_BASIS", "D1_UNIVERSE_WATCH"],
            "artifact_dependencies": [
                "daily_ohlcv_price_basis_audit.json",
                "universe.json",
                "official_metadata_audit.json",
            ],
            "next_allowed_action": "Inspect evidence and create a preregistered data-governance audit intent.",
            "maturity_pct": 72,
        },
        {
            "workflow_id": "D3_D4_SIGNAL_QUALITY_AUDIT",
            "title_ko": "D3/D4 신호 품질 감사",
            "stage": "D3-D4",
            "status": signal_summary.get("promotion_status") or "NO-GO_RESEARCH_ONLY",
            "approval_required": True,
            "approval_status": "COMPLETED_ARTIFACT_BACKED_REFERENCE",
            "trigger_status": "INTENT_ONLY_FOR_FOLLOW_UP",
            "blocked_by": ["D5_NO_GO", "MODEL_BUILD_LOCKED", "PAPER_FORWARD_LOCKED", "LIVE_BROKER_ORDER_LOCKED"],
            "artifact_dependencies": list((signal_summary.get("required_artifacts") or {}).values()),
            "next_allowed_action": signal_summary.get("next_allowed_research"),
            "maturity_pct": 100 if signal_summary.get("status") == "COMPLETED_RESEARCH_ONLY" else 0,
        },
        {
            "workflow_id": "PAST_ONLY_MARKET_REGIME_AUDIT",
            "title_ko": "Past-only 시장 국면 데이터 품질 감사",
            "stage": "D3-D4",
            "status": market_regime_readiness.get("status") or "NEXT_RESEARCH_READY_FOR_PREREGISTRATION",
            "approval_required": True,
            "approval_status": "PREREGISTRATION_REQUIRED",
            "trigger_status": "INTENT_ONLY_NOT_EXECUTED_BY_BROWSER",
            "blocked_by": market_regime_readiness.get("blocked_gates") or [],
            "artifact_dependencies": market_regime_readiness.get("required_inputs") or [],
            "next_allowed_action": "Write/read preregistration, then request an approved research-only intent.",
            "maturity_pct": market_regime_readiness.get("maturity_score_pct"),
        },
        {
            "workflow_id": "D4_RL_OVERLAY_ABLATION",
            "title_ko": "D4 RL 위험 Overlay ablation",
            "stage": "D4-D5",
            "status": "BLOCKED_UNTIL_DATA_AUDIT",
            "approval_required": True,
            "approval_status": "BLOCKED_BY_D0_D1_D5",
            "trigger_status": "DISABLED_UNTIL_BLOCKERS_RESOLVE",
            "blocked_by": ["D0_PRICE_BASIS", "D1_UNIVERSE_WATCH", "D5_NO_GO"],
            "artifact_dependencies": ["state_observations.csv", "reward_breakdown.csv", "action_distribution.csv", "walk_forward_gate_manifest.json"],
            "next_allowed_action": "Do not run overlay ablation until market-regime/data quality blockers are addressed.",
            "maturity_pct": 35,
        },
        {
            "workflow_id": "SCENARIO_BATCH_RESEARCH_ONLY",
            "title_ko": "Scenario batch research-only 실행 검토",
            "stage": "Automation",
            "status": "WATCH_RESEARCH_ONLY",
            "approval_required": True,
            "approval_status": "APPROVAL_REQUIRED_FOR_NEW_BATCH",
            "trigger_status": "INTENT_ONLY_NOT_EXECUTED_BY_BROWSER",
            "blocked_by": ["NO_LIVE_BROKER_ORDERS", "NO_PROFIT_CLAIMS"],
            "artifact_dependencies": ["scenario_plan.json", "scenario_batch_manifest.json"],
            "next_allowed_action": "Create fixed scenario draft and approval-linked intent record only.",
            "maturity_pct": 86 if _to_int(batch.get("scenario_count"), 0) else 50,
        },
        {
            "workflow_id": "HYPOTHESIS_REJECTION_AUDIT",
            "title_ko": "가설 탈락 / 조기 dropout 감사",
            "stage": "Research QA",
            "status": "PREREGISTERED_RESEARCH_ONLY",
            "approval_required": True,
            "approval_status": "PREREGISTRATION_AVAILABLE",
            "trigger_status": "INTENT_ONLY_NOT_EXECUTED_BY_BROWSER",
            "blocked_by": ["REVIEW_ONLY_FALSE_NEGATIVES", "NO_NO_GO_REVERSAL"],
            "artifact_dependencies": [
                "gate_funnel_metrics.csv",
                "rejection_reason_taxonomy.csv",
                "calibration_metrics.csv",
                "threshold_sensitivity.csv",
                "false_negative_candidates.csv",
                "audit_manifest.json",
            ],
            "next_allowed_action": "Generate review-only rejection analytics after approved research intent.",
            "maturity_pct": 65,
        },
    ]
    for item in workflow_items:
        item["read_only_dashboard"] = True
        item["execution_allowed_from_browser"] = False
        item["model_build_allowed"] = False
        item["paper_forward_allowed"] = False
        item["live_broker_order_allowed"] = False
        item["default_cost_bp"] = 23
        item["cost_sensitivity_bp"] = [0, 23, 46]
        item["guardrail"] = "Dashboard workflow surface is inspection/configuration/intent-only; no live/broker/orders, no paper/model unlock, no profit claim."
    completion_pct = round(sum((_to_float(item.get("maturity_pct"), 0.0) or 0.0) for item in workflow_items) / len(workflow_items))
    return {
        "schema_version": "daily_ohlcv_research_workflow_catalog.v1",
        "status": "DASHBOARD_FIRST_RESEARCH_WORKFLOWS_VISIBLE",
        "read_only": True,
        "execution_allowed_from_browser": False,
        "job_intent_mode": "APPROVAL_GATED_INTENT_RECORD_ONLY",
        "workflow_count": len(workflow_items),
        "completion_pct": completion_pct,
        "allowed_workflow_ids": list(_ALLOWED_RESEARCH_WORKFLOW_IDS),
        "workflows": workflow_items,
        "dashboard_contract": [
            "catalog",
            "inspector",
            "safe_config_preview",
            "approval_blocker_or_intent_record",
            "ledger",
            "artifact_review",
        ],
        "forbidden_fields": [
            "command",
            "shell",
            "argv",
            "cwd",
            "env",
            "broker",
            "account",
            "order",
            "live",
            "paper_forward_unlock",
            "model_build_unlock",
            "profit_target",
            "symbol_order",
            "paper_forward",
            "model_build",
            "arbitrary_path",
            "model_build_allowed",
            "paper_forward_allowed",
            "live_broker_order_allowed",
            "go_summary_allowed",
            "execution_allowed_from_browser",
        ],
        "source_docs": [
            "docs/stom_daily_ohlcv_dashboard_first_research_platform_adr_2026-06-18.md",
            "docs/stom_daily_ohlcv_hypothesis_rejection_audit_prereg_2026-06-18.md",
            "docs/stom_daily_ohlcv_research_governance_index_2026-06-18.md",
        ],
        "guardrail": "Research workflow catalog is dashboard-visible planning/inspection metadata only; browser execution and live/broker/order/model/paper/profit behavior are blocked.",
    }


def load_research_workflow_catalog() -> dict[str, Any]:
    return _build_research_workflow_catalog_payload()


def load_research_workflow_detail(workflow_id: str) -> dict[str, Any]:
    safe_id = str(workflow_id or "").strip().upper()
    catalog = load_research_workflow_catalog()
    workflows = catalog.get("workflows") if isinstance(catalog.get("workflows"), list) else []
    workflow = next((item for item in workflows if isinstance(item, dict) and item.get("workflow_id") == safe_id), None)
    if workflow is None:
        return {
            "schema_version": "daily_ohlcv_research_workflow_detail.v1",
            "status": "UNKNOWN_WORKFLOW_ID",
            "workflow_id": safe_id,
            "read_only": True,
            "execution_allowed_from_browser": False,
            "model_build_allowed": False,
            "paper_forward_allowed": False,
            "live_broker_order_allowed": False,
            "blockers": ["UNKNOWN_WORKFLOW_ID"],
            "guardrail": "Unknown workflow ids fail closed and cannot create research intents.",
        }
    return {
        "schema_version": "daily_ohlcv_research_workflow_detail.v1",
        "status": workflow.get("status"),
        "workflow": workflow,
        "inspector_sections": [
            {"id": "blockers", "title_ko": "현재 blocker", "items": workflow.get("blocked_by") or []},
            {"id": "artifacts", "title_ko": "필요 artifact", "items": workflow.get("artifact_dependencies") or []},
            {"id": "approval", "title_ko": "승인 상태", "items": [workflow.get("approval_status"), workflow.get("trigger_status")]},
            {"id": "guardrails", "title_ko": "금지된 사용", "items": ["no live/broker/orders", "no model/paper unlock", "no profit claim", "no arbitrary shell"]},
        ],
        "config_preview_contract": {
            "schema_version": "daily_ohlcv_safe_config_preview.v1",
            "workflow_id": workflow.get("workflow_id"),
            "default_cost_bp": 23,
            "cost_sensitivity_bp": [0, 23, 46],
            "approval_required": True,
            "forbidden_fields": catalog.get("forbidden_fields") or [],
            "status": "INTENT_CREATION_AVAILABLE_G003",
            "post_endpoint_template": "/api/daily-ohlcv/research-workflows/{workflow_id}/job-intents",
            "ledger_endpoint": "/api/daily-ohlcv/research-jobs",
        },
        "read_only": True,
        "execution_allowed_from_browser": False,
        "guardrail": "Workflow detail is read-only inspector metadata; job-intent creation is handled by a later approval-gated story.",
    }

def _json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_relative_repo_path(value: Any) -> Path:
    raw = str(value or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/") or raw.startswith("~") or ":" in raw:
        raise ValueError("UNSAFE_PATH")
    path = Path(raw)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("UNSAFE_PATH_TRAVERSAL")
    return path


def _approval_path_allowed(path: Path) -> bool:
    normalized = path.as_posix()
    return normalized.startswith("docs/") or normalized.startswith(".gjc/plans/ralplan/") or normalized.startswith(".gjc/ultragoal/")


def _collect_forbidden_payload_keys(value: Any, forbidden: set[str], *, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            child_prefix = f"{prefix}.{key_text}" if prefix else key_text
            if key_text.lower() in forbidden:
                found.append(child_prefix)
            found.extend(_collect_forbidden_payload_keys(child, forbidden, prefix=child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_collect_forbidden_payload_keys(child, forbidden, prefix=f"{prefix}[{index}]"))
    return found


_ALLOWED_CONFIG_FIELDS = {
    "workflow_id",
    "hypothesis_id",
    "cost_sensitivity_bp",
    "fold_policy",
    "controls",
    "data_window_id",
    "artifact_dependencies",
    "reviewer_notes",
    "default_cost_bp",
}


_ALLOWED_INTENT_PAYLOAD_FIELDS = {
    "schema_version",
    "workflow_id",
    "approval_ref",
    "approval_ref_sha256",
    "approval_status",
    "idempotency_key",
    "requested_by",
    "config",
    "authz_mode",
    "authz_decision",
}


def _validate_intent_payload(payload: dict[str, Any], workflow_id: str) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    catalog = load_research_workflow_catalog()
    forbidden = {str(item).lower() for item in catalog.get("forbidden_fields") or []}
    forbidden_hits = _collect_forbidden_payload_keys(payload, forbidden)
    if forbidden_hits:
        errors.append(f"FORBIDDEN_FIELDS:{','.join(forbidden_hits)}")
    unsupported_top_level = sorted(str(key) for key in payload if str(key) not in _ALLOWED_INTENT_PAYLOAD_FIELDS)
    if unsupported_top_level:
        errors.append(f"UNSUPPORTED_TOP_LEVEL_FIELDS:{','.join(unsupported_top_level)}")
    safe_workflow_id = str(workflow_id or "").strip().upper()
    if safe_workflow_id not in _ALLOWED_RESEARCH_WORKFLOW_IDS:
        errors.append("UNKNOWN_WORKFLOW_ID")
    body_workflow = str(payload.get("workflow_id") or safe_workflow_id).strip().upper()
    if body_workflow != safe_workflow_id:
        errors.append("WORKFLOW_ID_MISMATCH")
    approval_ref_raw = payload.get("approval_ref")
    approval_ref_sha = str(payload.get("approval_ref_sha256") or "")
    approval_path: Path | None = None
    if not approval_ref_raw or not approval_ref_sha:
        errors.append("APPROVAL_REF_AND_SHA_REQUIRED")
    else:
        try:
            approval_path = _safe_relative_repo_path(approval_ref_raw)
            if not _approval_path_allowed(approval_path):
                errors.append("APPROVAL_REF_OUTSIDE_ALLOWED_ROOTS")
            elif not approval_path.is_file():
                errors.append("APPROVAL_REF_NOT_FOUND")
            elif _file_sha256(approval_path) != approval_ref_sha:
                errors.append("APPROVAL_REF_SHA_MISMATCH")
        except ValueError as exc:
            errors.append(str(exc))
    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if not SAFE_RUN_RE.match(idempotency_key) or idempotency_key in {"", ".", ".."}:
        errors.append("INVALID_IDEMPOTENCY_KEY")
    requested_by = str(payload.get("requested_by") or "local-dashboard-user")
    approval_status = str(payload.get("approval_status") or "").strip().upper()
    if approval_status not in {"APPROVED", "APPROVED_FOR_RESEARCH_INTENT"}:
        errors.append("APPROVAL_STATUS_NOT_APPROVED")
    authz_mode = str(payload.get("authz_mode") or "local_trusted_dashboard").strip()
    authz_decision = str(payload.get("authz_decision") or "ALLOW_RESEARCH_INTENT_RECORD_ONLY").strip().upper()
    if authz_mode != "local_trusted_dashboard":
        errors.append("UNSUPPORTED_AUTHZ_MODE")
    if authz_decision != "ALLOW_RESEARCH_INTENT_RECORD_ONLY":
        errors.append("AUTHZ_DECISION_MUST_BE_RESEARCH_INTENT_ONLY")
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    unexpected_config = sorted(str(key) for key in config if str(key) not in _ALLOWED_CONFIG_FIELDS)
    if unexpected_config:
        errors.append(f"UNSUPPORTED_CONFIG_FIELDS:{','.join(unexpected_config)}")
    config_workflow = str(config.get("workflow_id") or safe_workflow_id).strip().upper()
    if config_workflow != safe_workflow_id:
        errors.append("CONFIG_WORKFLOW_ID_MISMATCH")
    if config.get("cost_sensitivity_bp", [0, 23, 46]) != [0, 23, 46]:
        errors.append("COST_SENSITIVITY_MUST_BE_0_23_46")
    if config.get("default_cost_bp", 23) != 23:
        errors.append("DEFAULT_COST_BP_MUST_BE_23")
    artifact_dependencies = config.get("artifact_dependencies")
    if artifact_dependencies is not None:
        if not isinstance(artifact_dependencies, list):
            errors.append("ARTIFACT_DEPENDENCIES_MUST_BE_LIST")
        else:
            for index, artifact in enumerate(artifact_dependencies):
                try:
                    _safe_relative_repo_path(artifact)
                except ValueError as exc:
                    errors.append(f"UNSAFE_ARTIFACT_DEPENDENCY[{index}]:{exc}")
    if errors:
        return None, errors
    normalized_config = {key: config.get(key) for key in sorted(_ALLOWED_CONFIG_FIELDS) if key in config}
    normalized_config.setdefault("cost_sensitivity_bp", [0, 23, 46])
    normalized_config.setdefault("default_cost_bp", 23)
    plan_hash = _json_hash(
        {
            "workflow_id": safe_workflow_id,
            "config": normalized_config,
            "approval_ref": str(approval_path),
            "approval_ref_sha256": approval_ref_sha,
            "approval_status": approval_status,
            "authz_mode": authz_mode,
            "authz_decision": authz_decision,
        }
    )
    config_hash = _json_hash(normalized_config)
    intent_hash = hashlib.sha256(f"{safe_workflow_id}:{idempotency_key}".encode("utf-8")).hexdigest()[:16]
    return {
        "schema_version": "daily_ohlcv_research_job_intent.v1",
        "intent_id": f"{safe_workflow_id.lower()}_{intent_hash}",
        "workflow_id": safe_workflow_id,
        "approval_ref": str(approval_path),
        "approval_ref_sha256": approval_ref_sha,
        "requested_by": requested_by,
        "approval_status": approval_status,
        "approval_validation": {
            "status": "APPROVED_SHA256_CURRENT",
            "stale_check": "approval_ref_sha256_must_match_current_file",
            "workflow_id": safe_workflow_id,
        },
        "requested_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "idempotency_key": idempotency_key,
        "plan_hash": plan_hash,
        "config_hash": config_hash,
        "normalized_config": normalized_config,
        "source_governance_index_path": "docs/stom_daily_ohlcv_research_governance_index_2026-06-18.md",
        "default_cost_bp": 23,
        "cost_sensitivity_bp": [0, 23, 46],
        "baseline_controls": ["no_trade", "shuffle_control", "frozen_d3_baseline"],
        "no_retune": True,
        "authz_mode": authz_mode,
        "authz_decision": authz_decision,
        "model_build_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "artifact_root": str(DEFAULT_RESEARCH_INTENT_ROOT),
        "status": "INTENT_RECORDED",
        "guardrails": ["research_only", "no_live_broker_orders", "no_profit_claims", "no_paper_forward", "no_model_build", "no_arbitrary_shell"],
    }, []


def create_research_job_intent(workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"schema_version": "daily_ohlcv_research_job_intent_response.v1", "status": "VALIDATION_FAILED", "errors": ["JSON_OBJECT_REQUIRED"], "http_status": 400, "model_build_allowed": False, "paper_forward_allowed": False, "live_broker_order_allowed": False}
    normalized, errors = _validate_intent_payload(payload, workflow_id)
    if errors or normalized is None:
        return {"schema_version": "daily_ohlcv_research_job_intent_response.v1", "status": "VALIDATION_FAILED", "errors": errors, "http_status": 400, "model_build_allowed": False, "paper_forward_allowed": False, "live_broker_order_allowed": False, "guardrail": "Invalid research intent requests fail closed and never execute."}
    root = DEFAULT_RESEARCH_INTENT_ROOT.resolve()
    intent_dir = (root / normalized["intent_id"]).resolve()
    intent_dir.relative_to(root)
    intent_path = intent_dir / "intent.json"
    if intent_path.exists():
        existing = _load_json_if_exists(intent_path)
        if existing.get("plan_hash") == normalized["plan_hash"] and existing.get("config_hash") == normalized["config_hash"]:
            existing["http_status"] = 200
            existing["idempotency_result"] = "existing_intent_returned"
            return existing
        return {"schema_version": "daily_ohlcv_research_job_intent_response.v1", "status": "IDEMPOTENCY_CONFLICT", "errors": ["IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PLAN_OR_CONFIG"], "http_status": 409, "model_build_allowed": False, "paper_forward_allowed": False, "live_broker_order_allowed": False}
    try:
        intent_dir.relative_to(root)
    except ValueError:
        return {"schema_version": "daily_ohlcv_research_job_intent_response.v1", "status": "UNSAFE_INTENT_PATH", "errors": ["UNSAFE_INTENT_PATH"], "http_status": 400, "model_build_allowed": False, "paper_forward_allowed": False, "live_broker_order_allowed": False}
    intent_dir.mkdir(parents=True, exist_ok=True)
    normalized["idempotency_result"] = "created"
    normalized["intent_path"] = str(intent_path)
    intent_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    normalized["http_status"] = 201
    return normalized


def load_research_job_intent_ledger(*, limit: int = 25) -> dict[str, Any]:
    root = DEFAULT_RESEARCH_INTENT_ROOT.resolve()
    safe_limit = _bounded_limit(limit, default=25, maximum=200)
    intents: list[dict[str, Any]] = []
    if root.exists():
        for path in sorted(root.glob("*/intent.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                path.resolve().relative_to(root)
            except (OSError, ValueError):
                continue
            payload = _load_json_if_exists(path)
            if not payload:
                continue
            intents.append(
                {
                    "intent_id": payload.get("intent_id"),
                    "workflow_id": payload.get("workflow_id"),
                    "status": payload.get("status"),
                    "requested_at_utc": payload.get("requested_at_utc"),
                    "requested_by": payload.get("requested_by"),
                    "approval_ref": payload.get("approval_ref"),
                    "approval_ref_sha256": payload.get("approval_ref_sha256"),
                    "approval_status": payload.get("approval_status"),
                    "authz_mode": payload.get("authz_mode"),
                    "authz_decision": payload.get("authz_decision"),
                    "plan_hash": payload.get("plan_hash"),
                    "config_hash": payload.get("config_hash"),
                    "intent_path": _path_text(path),
                    "model_build_allowed": False,
                    "paper_forward_allowed": False,
                    "live_broker_order_allowed": False,
                    "next_allowed_action": "Review immutable intent and wait for separately approved internal worker consumption.",
                    "artifact_refs": [
                        {
                            "id": "intent_json",
                            "kind": "immutable-job-intent",
                            "path": _path_text(path),
                            "description": "Approval-gated research intent record; this is not an execution transcript.",
                        }
                    ],
                }
            )
            if len(intents) >= safe_limit:
                break
    return {
        "schema_version": "daily_ohlcv_research_job_intent_ledger.v1",
        "status": "READY" if intents else "EMPTY",
        "read_only": True,
        "execution_allowed_from_browser": False,
        "model_build_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "intent_root": _path_text(DEFAULT_RESEARCH_INTENT_ROOT),
        "count": len(intents),
        "limit": safe_limit,
        "intents": intents,
        "guardrail": "The ledger lists immutable approval-gated research intents only; recorded intents do not execute CLI, spawn workers, or unlock live/model/paper behavior.",
        "next_allowed_action": "Create a new approved research intent or review existing immutable intent records; browser does not execute them.",
        "artifact_refs": [
            {
                "id": "intent_root",
                "kind": "research-intent-root",
                "path": _path_text(DEFAULT_RESEARCH_INTENT_ROOT),
                "description": "Generated intent record root under webui/rl_runs.",
            }
        ],
    }


def load_research_job_intent(intent_id: str) -> dict[str, Any]:
    safe_intent_id = str(intent_id or "").strip()
    if not SAFE_RUN_RE.match(safe_intent_id) or safe_intent_id in {"", ".", ".."}:
        return {
            "schema_version": "daily_ohlcv_research_job_intent_detail.v1",
            "status": "INVALID_INTENT_ID",
            "http_status": 400,
            "errors": ["INVALID_INTENT_ID"],
            "model_build_allowed": False,
            "paper_forward_allowed": False,
            "live_broker_order_allowed": False,
        }
    root = DEFAULT_RESEARCH_INTENT_ROOT.resolve()
    intent_path = (root / safe_intent_id / "intent.json").resolve()
    try:
        intent_path.relative_to(root)
    except ValueError:
        return {
            "schema_version": "daily_ohlcv_research_job_intent_detail.v1",
            "status": "UNSAFE_INTENT_PATH",
            "http_status": 400,
            "errors": ["UNSAFE_INTENT_PATH"],
            "model_build_allowed": False,
            "paper_forward_allowed": False,
            "live_broker_order_allowed": False,
        }
    payload = _load_json_if_exists(intent_path)
    if not payload:
        return {
            "schema_version": "daily_ohlcv_research_job_intent_detail.v1",
            "status": "INTENT_NOT_FOUND",
            "http_status": 404,
            "intent_id": safe_intent_id,
            "model_build_allowed": False,
            "paper_forward_allowed": False,
            "live_broker_order_allowed": False,
        }
    payload["schema_version"] = "daily_ohlcv_research_job_intent_detail.v1"
    payload["http_status"] = 200
    payload["read_only"] = True
    payload["execution_allowed_from_browser"] = False
    payload["model_build_allowed"] = False
    payload["paper_forward_allowed"] = False
    payload["live_broker_order_allowed"] = False
    payload["guardrail"] = "Intent detail is immutable research metadata; it is not a worker execution, order, model build, or paper-forward unlock."
    return payload


def _load_rejection_audit_csv(run_dir: Path, filename: str, *, limit: int) -> list[dict[str, Any]]:
    path = run_dir / filename
    if not path.exists():
        return []
    return _read_csv_rows(path, limit)


def _rejection_audit_artifact_hashes(run_dir: Path) -> dict[str, str]:
    filenames = [
        "gate_funnel_metrics.csv",
        "rejection_reason_taxonomy.csv",
        "calibration_metrics.csv",
        "threshold_sensitivity.csv",
        "false_negative_candidates.csv",
        "audit_manifest.json",
    ]
    return {filename: _file_sha256(run_dir / filename) for filename in filenames if (run_dir / filename).is_file()}


def _validate_rejection_audit_payload(
    *,
    run_dir: Path,
    manifest: dict[str, Any],
    artifact_hashes: dict[str, str],
    row_counts: dict[str, int],
    false_negative_candidates: list[dict[str, Any]],
) -> list[str]:
    required_files = [
        "gate_funnel_metrics.csv",
        "rejection_reason_taxonomy.csv",
        "calibration_metrics.csv",
        "threshold_sensitivity.csv",
        "false_negative_candidates.csv",
        "audit_manifest.json",
    ]
    errors: list[str] = []
    if manifest.get("schema_version") != "daily_ohlcv_rejection_audit_manifest.v1":
        errors.append("INVALID_MANIFEST_SCHEMA_VERSION")
    if manifest.get("status") != "COMPLETED_RESEARCH_ONLY":
        errors.append("INVALID_MANIFEST_STATUS")
    for filename in required_files:
        if not (run_dir / filename).is_file():
            errors.append(f"MISSING_REQUIRED_ARTIFACT:{filename}")
    manifest_hashes = manifest.get("artifact_hashes") if isinstance(manifest.get("artifact_hashes"), dict) else {}
    for filename in required_files:
        if filename == "audit_manifest.json":
            continue
        expected = str(manifest_hashes.get(filename) or "")
        actual = artifact_hashes.get(filename)
        if not expected or expected != actual:
            errors.append(f"ARTIFACT_HASH_MISMATCH:{filename}")
    manifest_counts = manifest.get("row_counts") if isinstance(manifest.get("row_counts"), dict) else {}
    for key, actual_count in row_counts.items():
        if _to_int(manifest_counts.get(key), -1) != actual_count:
            errors.append(f"ROW_COUNT_MISMATCH:{key}")
    guardrails = set(str(item) for item in manifest.get("guardrails") or [])
    for guardrail in ("research_only", "review_only_false_negatives", "no_no_go_reversal", "no_model_build", "no_paper_forward", "no_live_broker_orders"):
        if guardrail not in guardrails:
            errors.append(f"MISSING_GUARDRAIL:{guardrail}")
    if manifest.get("promotion_allowed") is not False:
        errors.append("PROMOTION_ALLOWED_NOT_FALSE")
    if manifest.get("model_build_allowed") is not False:
        errors.append("MODEL_BUILD_ALLOWED_NOT_FALSE")
    if manifest.get("paper_forward_allowed") is not False:
        errors.append("PAPER_FORWARD_ALLOWED_NOT_FALSE")
    if manifest.get("live_broker_order_allowed") is not False:
        errors.append("LIVE_BROKER_ORDER_ALLOWED_NOT_FALSE")
    for row in false_negative_candidates:
        if str(row.get("review_status") or "") != "REVIEW_ONLY":
            errors.append("FALSE_NEGATIVE_NOT_REVIEW_ONLY")
        if str(row.get("promotion_allowed") or "").lower() not in {"false", "0", ""} and row.get("promotion_allowed") is not False:
            errors.append("FALSE_NEGATIVE_PROMOTION_ALLOWED")
        if str(row.get("requires_new_preregistration") or "").lower() not in {"true", "1"} and row.get("requires_new_preregistration") is not True:
            errors.append("FALSE_NEGATIVE_MISSING_NEW_PREREG")
        later_path = str(row.get("later_independent_evidence_manifest_path") or "")
        later_sha = str(row.get("later_independent_evidence_sha256") or "")
        if not later_path or not later_sha:
            errors.append("FALSE_NEGATIVE_MISSING_LATER_EVIDENCE")
            continue
        try:
            evidence_path = _safe_relative_repo_path(later_path)
        except ValueError:
            errors.append("FALSE_NEGATIVE_UNSAFE_LATER_EVIDENCE_PATH")
            continue
        if not evidence_path.is_file():
            errors.append("FALSE_NEGATIVE_LATER_EVIDENCE_NOT_FOUND")
            continue
        if _file_sha256(evidence_path) != later_sha:
            errors.append("FALSE_NEGATIVE_LATER_EVIDENCE_SHA_MISMATCH")
            continue
        evidence_manifest = _load_json_if_exists(evidence_path)
        if evidence_manifest.get("schema_version") != "daily_ohlcv_false_negative_followup_evidence.v1":
            errors.append("FALSE_NEGATIVE_LATER_EVIDENCE_INVALID_SCHEMA")
        if evidence_manifest.get("status") != "FOLLOW_UP_PREREGISTRATION_REQUIRED_REVIEW_ONLY":
            errors.append("FALSE_NEGATIVE_LATER_EVIDENCE_INVALID_STATUS")
        if row.get("candidate_id") not in (evidence_manifest.get("candidate_ids") or []):
            errors.append("FALSE_NEGATIVE_LATER_EVIDENCE_CANDIDATE_MISMATCH")
        if evidence_manifest.get("promotion_allowed") is not False:
            errors.append("FALSE_NEGATIVE_LATER_EVIDENCE_PROMOTION_ALLOWED")
        if evidence_manifest.get("requires_new_preregistration") is not True:
            errors.append("FALSE_NEGATIVE_LATER_EVIDENCE_MISSING_NEW_PREREG")
        evidence_guardrails = set(str(item) for item in evidence_manifest.get("guardrails") or [])
        for guardrail in ("review_only_false_negatives", "no_no_go_reversal", "no_model_build", "no_paper_forward", "no_live_broker_orders"):
            if guardrail not in evidence_guardrails:
                errors.append(f"FALSE_NEGATIVE_LATER_EVIDENCE_MISSING_GUARDRAIL:{guardrail}")
        expected_later_hash = str(manifest_hashes.get(evidence_path.name) or "")
        if expected_later_hash and expected_later_hash != later_sha:
            errors.append("FALSE_NEGATIVE_LATER_EVIDENCE_MANIFEST_HASH_MISMATCH")
    return errors


def load_rejection_analytics(*, run: str | None = None, limit: int = 25) -> dict[str, Any]:
    safe_limit = _bounded_limit(limit, default=25, maximum=200)
    try:
        run_dir = _latest_run_dir(DEFAULT_REJECTION_AUDIT_ROOT, run_id=run, required_file="audit_manifest.json")
    except (FileNotFoundError, ValueError):
        return {
            "schema_version": "daily_ohlcv_rejection_analytics.v1",
            "status": "INVALID_RUN_ID",
            "errors": ["INVALID_RUN_ID"],
            "read_only": True,
            "promotion_allowed": False,
            "model_build_allowed": False,
            "paper_forward_allowed": False,
            "live_broker_order_allowed": False,
        }
    if run_dir is None:
        return {
            "schema_version": "daily_ohlcv_rejection_analytics.v1",
            "status": "MISSING_REJECTION_AUDIT_ARTIFACTS",
            "run_id": None,
            "read_only": True,
            "promotion_allowed": False,
            "false_negative_review_only": True,
            "model_build_allowed": False,
            "paper_forward_allowed": False,
            "live_broker_order_allowed": False,
            "required_artifacts": [
                "gate_funnel_metrics.csv",
                "rejection_reason_taxonomy.csv",
                "calibration_metrics.csv",
                "threshold_sensitivity.csv",
                "false_negative_candidates.csv",
                "audit_manifest.json",
            ],
            "guardrail": "Missing rejection-audit artifacts fail closed; no NO-GO reversal or promotion is allowed.",
        }
    manifest = _load_json_if_exists(run_dir / "audit_manifest.json")
    artifact_hashes = _rejection_audit_artifact_hashes(run_dir)
    gate_funnel_all = _load_rejection_audit_csv(run_dir, "gate_funnel_metrics.csv", limit=MAX_LIMIT)
    taxonomy_all = _load_rejection_audit_csv(run_dir, "rejection_reason_taxonomy.csv", limit=MAX_LIMIT)
    calibration_all = _load_rejection_audit_csv(run_dir, "calibration_metrics.csv", limit=MAX_LIMIT)
    sensitivity_all = _load_rejection_audit_csv(run_dir, "threshold_sensitivity.csv", limit=MAX_LIMIT)
    false_negatives_all = _load_rejection_audit_csv(run_dir, "false_negative_candidates.csv", limit=MAX_LIMIT)
    gate_funnel = gate_funnel_all[:safe_limit]
    taxonomy = taxonomy_all[:safe_limit]
    calibration = calibration_all[:safe_limit]
    sensitivity = sensitivity_all[:safe_limit]
    false_negatives = false_negatives_all[:safe_limit]
    row_counts = {
        "gate_funnel_metrics": len(gate_funnel_all),
        "rejection_reason_taxonomy": len(taxonomy_all),
        "calibration_metrics": len(calibration_all),
        "threshold_sensitivity": len(sensitivity_all),
        "false_negative_candidates": len(false_negatives_all),
    }
    rejected_total = sum(_to_int(row.get("rejected_count"), 0) or 0 for row in gate_funnel_all)
    early_dropout_total = sum(_to_int(row.get("early_dropout_count"), 0) or 0 for row in gate_funnel_all)
    entered_total = sum(_to_int(row.get("entered_count"), 0) or 0 for row in gate_funnel_all)
    false_negative_candidates_all = [
        {
            **row,
            "review_status": row.get("review_status") or "REVIEW_ONLY",
            "promotion_allowed": False,
            "requires_new_preregistration": True,
        }
        for row in false_negatives_all
    ]
    false_negative_candidates = false_negative_candidates_all[:safe_limit]
    validation_errors = _validate_rejection_audit_payload(
        run_dir=run_dir,
        manifest=manifest,
        artifact_hashes=artifact_hashes,
        row_counts=row_counts,
        false_negative_candidates=false_negatives_all,
    )
    if validation_errors:
        return {
            "schema_version": "daily_ohlcv_rejection_analytics.v1",
            "status": "INVALID_REJECTION_AUDIT_ARTIFACTS",
            "run_id": manifest.get("audit_run_id") or run_dir.name,
            "errors": validation_errors,
            "read_only": True,
            "promotion_allowed": False,
            "false_negative_review_only": True,
            "model_build_allowed": False,
            "paper_forward_allowed": False,
            "live_broker_order_allowed": False,
            "artifact_hashes": artifact_hashes,
            "row_counts": row_counts,
            "guardrail": "Invalid rejection-audit artifacts fail closed; no NO-GO reversal or promotion is allowed.",
        }
    return {
        "schema_version": "daily_ohlcv_rejection_analytics.v1",
        "status": manifest.get("status") or "COMPLETED_RESEARCH_ONLY",
        "run_id": manifest.get("audit_run_id") or run_dir.name,
        "generated_at_utc": manifest.get("generated_at_utc"),
        "read_only": True,
        "artifact_root": _path_text(DEFAULT_REJECTION_AUDIT_ROOT),
        "run_path": _path_text(run_dir),
        "manifest_path": _path_text(run_dir / "audit_manifest.json"),
        "artifact_hashes": artifact_hashes,
        "row_counts": row_counts,
        "summary": {
            "entered_total": entered_total,
            "rejected_total": rejected_total,
            "early_dropout_total": early_dropout_total,
            "false_negative_candidate_count": len(false_negative_candidates),
            "review_only_candidate_count": len(false_negative_candidates),
            "promotion_allowed": False,
        },
        "denominator_policy": manifest.get("denominator_policy") or "pre-outcome eligible hypotheses/scenarios only",
        "timing_policy": manifest.get("timing_policy") or "decision_time_utc is frozen from then-available evidence",
        "independent_evidence_policy": manifest.get("independent_evidence_policy") or "later evidence must be separately timestamped and hashed",
        "gate_funnel_metrics": gate_funnel,
        "rejection_reason_taxonomy": taxonomy,
        "calibration_metrics": calibration,
        "threshold_sensitivity": sensitivity,
        "false_negative_candidates": false_negative_candidates,
        "audit_manifest": manifest,
        "promotion_allowed": False,
        "model_build_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "guardrail": "Rejection analytics are research QA only. False-negative candidates are review-only, require a new preregistration, and cannot reverse NO-GO or unlock model/paper/live behavior.",
    }


def _build_dashboard_first_completion_report(
    *,
    workflow_catalog: dict[str, Any],
    intent_ledger: dict[str, Any],
    rejection_analytics: dict[str, Any],
) -> dict[str, Any]:
    workflow_count = _to_int(workflow_catalog.get("workflow_count"), 0) or 0
    completion_items = [
        {
            "id": "workflow_center",
            "label_ko": "연구 workflow 센터",
            "completion_pct": 100 if workflow_count >= 6 and workflow_catalog.get("execution_allowed_from_browser") is False else 0,
            "evidence": "/api/daily-ohlcv/research-workflows",
        },
        {
            "id": "workflow_inspector",
            "label_ko": "workflow inspector / safe config",
            "completion_pct": 100 if "safe_config_preview" in (workflow_catalog.get("dashboard_contract") or []) else 0,
            "evidence": "/api/daily-ohlcv/research-workflows/<workflow_id>",
        },
        {
            "id": "intent_ledger",
            "label_ko": "approval-gated intent ledger",
            "completion_pct": 100 if intent_ledger.get("schema_version") == "daily_ohlcv_research_job_intent_ledger.v1" and intent_ledger.get("execution_allowed_from_browser") is False else 0,
            "evidence": "/api/daily-ohlcv/research-jobs",
        },
        {
            "id": "rejection_analytics",
            "label_ko": "가설 탈락 / 조기 dropout analytics",
            "completion_pct": 100 if rejection_analytics.get("status") == "COMPLETED_RESEARCH_ONLY" and rejection_analytics.get("promotion_allowed") is False else 0,
            "evidence": "/api/daily-ohlcv/rejection-analytics",
        },
        {
            "id": "docs_governance",
            "label_ko": "ADR / prereg / result / governance 문서",
            "completion_pct": 100,
            "evidence": "docs/stom_daily_ohlcv_dashboard_first_research_platform_completion_result_2026-06-18.md",
        },
    ]
    non_live_completion_pct = round(sum((_to_float(item.get("completion_pct"), 0.0) or 0.0) for item in completion_items) / len(completion_items))
    return {
        "schema_version": "daily_ohlcv_dashboard_first_completion_report.v1",
        "status": "NON_LIVE_RESEARCH_PLATFORM_COMPLETE" if non_live_completion_pct == 100 else "NON_LIVE_RESEARCH_PLATFORM_INCOMPLETE",
        "non_live_goal_completion_pct": non_live_completion_pct,
        "live_trading_readiness_pct": 0,
        "model_build_readiness_pct": 0,
        "paper_forward_readiness_pct": 0,
        "execution_allowed_from_browser": False,
        "model_build_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "completed_surfaces": completion_items,
        "can_do": [
            "대시보드에서 workflow/blocker/prerequisite/approval 상태 확인",
            "safe config preview와 approval-gated intent ledger 검토",
            "가설 탈락, 조기 dropout, false-negative review-only 후보 확인",
            "artifact hash, row count, guardrail, next action 확인",
        ],
        "cannot_do": [
            "실거래/live trading",
            "broker/order/account 연결",
            "paper-forward unlock",
            "model-build unlock",
            "수익성/profitability 주장",
            "대시보드 arbitrary shell 실행",
        ],
        "completion_evidence": [
            "G001 ADR/preregistration/governance complete",
            "G002 workflow catalog/inspector complete",
            "G003 safe config and intent ledger complete",
            "G004 rejection analytics complete",
            "G005 dashboard/docs/verification completion report integrated",
        ],
        "source_docs": [
            "docs/stom_daily_ohlcv_dashboard_first_research_platform_adr_2026-06-18.md",
            "docs/stom_daily_ohlcv_hypothesis_rejection_audit_prereg_2026-06-18.md",
            "docs/stom_daily_ohlcv_dashboard_first_research_platform_completion_result_2026-06-18.md",
            "docs/stom_daily_ohlcv_research_governance_index_2026-06-18.md",
        ],
        "guardrail": "Non-live research/dashboard platform completion can be 100% while live/model/paper readiness remains 0%; this is not profitability or broker/order readiness.",
    }


def _rl_guide_performance_card(
    *,
    label: str,
    split: str,
    total_return: Any,
    max_drawdown: Any = None,
    mean_turnover: Any = None,
    starting_capital_krw: int = RL_GUIDE_DISPLAY_CAPITAL_KRW,
) -> dict[str, Any]:
    return_value = _to_float(total_return, 0.0) or 0.0
    final_capital = starting_capital_krw * (1.0 + return_value)
    return {
        "label": label,
        "split": split,
        "total_return": return_value,
        "total_return_pct": return_value * 100.0,
        "simulated_profit_krw": round(starting_capital_krw * return_value),
        "simulated_final_capital_krw": round(final_capital),
        "max_drawdown_pct": (_to_float(max_drawdown, 0.0) or 0.0) * 100.0,
        "mean_turnover_pct": (_to_float(mean_turnover, 0.0) or 0.0) * 100.0,
    }


def _build_rl_guide_learning_performance(portfolio: dict[str, Any]) -> dict[str, Any]:
    baseline_comparison = portfolio.get("baseline_comparison") or {}
    samples = portfolio.get("samples") or {}
    policy_metrics = (portfolio.get("policy_metrics") or {}).get("metrics") or []
    metric_by_split = {
        str(row.get("split") or ""): row
        for row in policy_metrics
        if isinstance(row, dict)
    }
    policy_split = str(baseline_comparison.get("policy_split") or "val+test")
    policy_metric = metric_by_split.get(policy_split) or metric_by_split.get("test") or {}
    policy_return = baseline_comparison.get("policy_total_net_return")
    if policy_return is None:
        policy_return = policy_metric.get("total_net_return")
    policy_drawdown = baseline_comparison.get("policy_max_drawdown")
    if policy_drawdown is None:
        policy_drawdown = policy_metric.get("max_drawdown")
    policy_turnover = baseline_comparison.get("policy_mean_turnover")
    if policy_turnover is None:
        policy_turnover = policy_metric.get("mean_turnover")

    policy_card = _rl_guide_performance_card(
        label="D4 RL 정책",
        split=policy_split,
        total_return=policy_return,
        max_drawdown=policy_drawdown,
        mean_turnover=policy_turnover,
    )
    baseline_card = _rl_guide_performance_card(
        label=str(baseline_comparison.get("best_d3_strategy") or "D3 baseline"),
        split="best_d3_baseline",
        total_return=baseline_comparison.get("best_d3_total_net_return"),
    )
    delta_card = _rl_guide_performance_card(
        label="D4 RL - best D3 baseline",
        split="delta",
        total_return=baseline_comparison.get("delta_vs_best_d3_total_net_return"),
    )
    delta_return = delta_card["total_return"]
    interpretation = (
        "현재 D4 RL 정책은 같은 연구 원금 가정에서 D3 baseline보다 약합니다. "
        "따라서 학습 성과 화면은 설명·진단용이며 GO/수익성 주장으로 쓰면 안 됩니다."
        if delta_return < 0
        else "현재 D4 RL 정책은 baseline 대비 우위처럼 보일 수 있으나, D5 walk-forward와 비용 민감도 통과 전에는 연구 진단용입니다."
    )

    learning_curve_preview = [
        {
            "episode": _to_int(row.get("episode")),
            "total_reward": _to_float(row.get("total_reward")),
            "rolling_mean_reward": _to_float(row.get("rolling_mean_reward")),
            "final_equity": _to_float(row.get("final_equity")),
            "invalid_action_rate_pct": (_to_float(row.get("invalid_action_rate"), 0.0) or 0.0) * 100.0,
        }
        for row in (samples.get("learning_curve") or [])[:8]
        if isinstance(row, dict)
    ]
    portfolio_nav_preview = []
    for row in (samples.get("policy_nav") or [])[:12]:
        if not isinstance(row, dict):
            continue
        nav = _to_float(row.get("policy_nav"))
        portfolio_nav_preview.append(
            {
                "date": row.get("date"),
                "nav": nav,
                "simulated_capital_krw": round(RL_GUIDE_DISPLAY_CAPITAL_KRW * nav) if nav is not None else None,
                "current_drawdown_pct": (_to_float(row.get("policy_current_drawdown"), 0.0) or 0.0) * 100.0,
            }
        )

    return {
        "status": "RESEARCH_ONLY_PERFORMANCE_DIAGNOSTIC",
        "display_capital_krw": RL_GUIDE_DISPLAY_CAPITAL_KRW,
        "currency": "KRW",
        "run_id": portfolio.get("run_id"),
        "policy": policy_card,
        "best_d3_baseline": baseline_card,
        "delta_vs_best_d3": delta_card,
        "interpretation_ko": interpretation,
        "metric_definitions": [
            {"metric": "수익률", "meaning_ko": "연구용 평가 구간에서 NAV가 몇 % 변했는지입니다."},
            {"metric": "수익금", "meaning_ko": "가정 원금 1,000만원에 수익률을 곱한 모의 금액입니다."},
            {"metric": "MDD", "meaning_ko": "고점 대비 최대 낙폭입니다. 수익률과 함께 봐야 합니다."},
            {"metric": "turnover", "meaning_ko": "교체/거래 강도입니다. 높으면 23bp 비용 압력이 커집니다."},
        ],
        "learning_curve_preview": learning_curve_preview,
        "portfolio_nav_preview": portfolio_nav_preview,
        "guardrail": "All PnL/return figures are simulated research diagnostics from generated artifacts; no profit guarantee, no live/broker/orders, no deployable readiness.",
    }
def _rl_guide_action_distribution(samples: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in samples.get("action_distribution") or []:
        if not isinstance(row, dict):
            continue
        action = str(row.get("executed_action") or row.get("action") or "")
        if not action:
            continue
        rows.append(
            {
                "split": row.get("split"),
                "action": action,
                "requested_action": row.get("requested_action"),
                "executed_action": row.get("executed_action"),
                "invalid_action": str(row.get("invalid_action") or "False"),
                "invalid_action_reason": row.get("invalid_action_reason") or "",
                "no_trade_action": str(row.get("no_trade_action") or "False"),
                "count": _to_int(row.get("count"), 0),
                "action_rate": _to_float(row.get("action_rate"), 0.0),
            }
        )
    return rows


def _rl_guide_mask_reasons(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "hold": row.get("mask_reason_hold"),
        "buy": row.get("mask_reason_buy"),
        "add": row.get("mask_reason_add"),
        "sell": row.get("mask_reason_sell"),
        "reduce": row.get("mask_reason_reduce"),
    }


def _build_rl_guide_active_replay(portfolio: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Build an artifact-backed replay payload without fake policy-network outputs."""

    samples = portfolio.get("samples") if isinstance(portfolio.get("samples"), dict) else {}
    state_rows = [row for row in samples.get("state_observations") or [] if isinstance(row, dict)]
    reward_rows = [row for row in samples.get("reward_breakdown") or [] if isinstance(row, dict)]
    nav_rows = [row for row in samples.get("policy_nav") or [] if isinstance(row, dict)]
    learning_rows = [row for row in samples.get("learning_curve") or [] if isinstance(row, dict)]
    action_distribution = _rl_guide_action_distribution(samples)

    def replay_key(row: dict[str, Any]) -> tuple[str, str]:
        return (str(row.get("split") or ""), str(row.get("date") or ""))

    reward_by_key = {replay_key(row): row for row in reward_rows if row.get("date")}
    nav_by_key = {replay_key(row): row for row in nav_rows if row.get("date")}
    frame_keys: list[tuple[str, str]] = []
    for row in state_rows:
        key = replay_key(row)
        if key[1]:
            frame_keys.append(key)
    if not frame_keys:
        for row in reward_rows:
            key = replay_key(row)
            if key[1]:
                frame_keys.append(key)
    frame_keys = frame_keys[:8]

    frames: list[dict[str, Any]] = []
    for index, key in enumerate(frame_keys):
        state = next((row for row in state_rows if replay_key(row) == key), {})
        reward = reward_by_key.get(key, {})
        nav = nav_by_key.get(key, {})
        learning = learning_rows[index % len(learning_rows)] if learning_rows else {}
        frame_status = "LOADED_GENERATED_ARTIFACT" if state and reward else "MISSING_REPLAY_JOIN_KEY"
        frames.append(
            {
                "frame": index + 1,
                "status": frame_status,
                "join_key": {"split": key[0], "date": key[1]},
                "split": key[0] or state.get("split") or reward.get("split") or nav.get("split"),
                "date": key[1] or state.get("date") or reward.get("date") or nav.get("date"),
                "state": {
                    "position_count": _to_int(state.get("observation_position_count"), 0),
                    "top_score_bucket": _to_int(state.get("observation_top_score_bucket"), None),
                    "cash_fraction": _to_float(state.get("cash_fraction"), None),
                    "exposure_fraction": _to_float(state.get("exposure_fraction"), None),
                    "top_candidate_code": state.get("top_candidate_code"),
                    "candidate_count": _to_int(state.get("candidate_count"), None),
                    "future_label_exposed": str(state.get("future_label_exposed") or "UNKNOWN"),
                },
                "action": {
                    "requested": reward.get("requested_action") or reward.get("action"),
                    "executed": reward.get("executed_action") or reward.get("action"),
                    "invalid": str(reward.get("invalid_action") or "False"),
                    "invalid_reason": reward.get("invalid_action_reason") or "",
                    "no_trade": str(reward.get("no_trade_action") or "False"),
                    "mask": state.get("action_mask_hold_buy_add_sell_reduce") or reward.get("action_mask_hold_buy_add_sell_reduce"),
                    "mask_reasons": _rl_guide_mask_reasons(state or reward),
                },
                "reward": {
                    "reward": _to_float(reward.get("reward"), None),
                    "gross_return": _to_float(reward.get("gross_return"), None),
                    "net_return_after_cost": _to_float(reward.get("net_return_after_cost"), None),
                    "turnover_cost": _to_float(reward.get("cost"), None),
                    "turnover": _to_float(reward.get("turnover"), None),
                    "drawdown_penalty": _to_float(reward.get("drawdown_penalty"), None),
                    "concentration_penalty": _to_float(reward.get("concentration_penalty"), None),
                    "invalid_action_penalty": _to_float(reward.get("invalid_action_penalty"), None),
                    "churn_penalty": _to_float(reward.get("churn_penalty"), None),
                    "equity": _to_float(reward.get("equity"), None),
                },
                "learning": {
                    "episode": _to_int(learning.get("episode"), None),
                    "total_reward": _to_float(learning.get("total_reward"), None),
                    "final_equity": _to_float(learning.get("final_equity"), None),
                },
                "nav": {
                    "policy_nav": _to_float(nav.get("policy_nav"), None),
                    "policy_turnover": _to_float(nav.get("policy_turnover"), None),
                    "policy_current_drawdown": _to_float(nav.get("policy_current_drawdown"), None),
                },
            }
        )

    policy_strategy = str((portfolio.get("baseline_comparison") or {}).get("policy_strategy") or "tabular_q_constrained_daily_portfolio_rl")
    policy_type = "tabular_q"
    replay_status = "LOADED_GENERATED_ARTIFACT" if frames and any(frame["status"] == "LOADED_GENERATED_ARTIFACT" for frame in frames) else "MISSING_REPLAY_ARTIFACT"
    return {
        "schema_version": "daily_rl_active_replay.v1",
        "status": replay_status,
        "source_run_id": portfolio.get("run_id") or "MISSING_SOURCE_RUN_ID",
        "artifact_hashes": portfolio.get("artifact_hashes") or {"status": "MISSING_ARTIFACT_HASHES"},
        "policy_type": policy_type,
        "policy_strategy": policy_strategy,
        "policy_network_available": False,
        "policy_network_status": "MISSING_POLICY_ARTIFACT",
        "policy_representation_ko": "현재 산출물은 신경망 정책이 아니라 tabular Q 학습/평가 telemetry입니다.",
        "action_schema_version": contract.get("schema_version"),
        "action_distribution": action_distribution,
        "frames": frames,
        "source_tables": [
            "state_observations.csv",
            "reward_breakdown.csv",
            "learning_curve.csv",
            "action_distribution.csv",
            "policy_nav.csv",
        ],
        "guardrail": "Artifact-backed replay only. No fake neural/probability fallback, no live/broker/orders, no profit or deployment claim.",
    }


def _build_rl_guide_process_lane(
    *,
    lane_id: str,
    title_ko: str,
    stage: str,
    status: str,
    goal_ko: str,
    state_setup: list[str],
    action_setup: list[str],
    reward_setup: list[str],
    current_limitations: list[str],
    improvement_directions: list[str],
    metrics_to_watch: list[str],
    required_artifacts: list[str],
    baseline: str,
    controls: list[str],
    next_step_ko: str,
    guardrails: list[str],
) -> dict[str, Any]:
    return {
        "id": lane_id,
        "title_ko": title_ko,
        "stage": stage,
        "status": status,
        "severity": _status_severity(status),
        "goal_ko": goal_ko,
        "visual_nodes": [
            {"label": "Environment", "detail": "일봉 날짜 단위 연구 환경", "status": "RESEARCH_ONLY"},
            {"label": "State", "detail": " · ".join(state_setup[:3]), "status": status},
            {"label": "Action", "detail": " · ".join(action_setup[:3]), "status": status},
            {"label": "Reward", "detail": " · ".join(reward_setup[:3]), "status": status},
            {"label": "Gate", "detail": "D5 NO-GO면 승격 금지", "status": "NO-GO"},
        ],
        "environment_setup": "일봉 OHLCV/D2-D3 산출물을 날짜 순서대로 읽는 research-only 포트폴리오 환경입니다.",
        "state_setup": state_setup,
        "action_setup": action_setup,
        "reward_setup": reward_setup,
        "baseline": baseline,
        "controls": controls,
        "current_limitations": current_limitations,
        "improvement_directions": improvement_directions,
        "metrics_to_watch": metrics_to_watch,
        "required_artifacts": required_artifacts,
        "user_questions_to_improve": [
            "이 연구는 D3 baseline 대비 어떤 위험/행동을 줄이려는가?",
            "비용 23bp와 46bp stress에서도 같은 결론인가?",
            "D5 5-fold OOS에서 특정 fold만 골라 설명하지 않았는가?",
            "NO-GO 원인을 개선할 다음 산출물이 명확한가?",
        ],
        "ai_guidance_format": {
            "lane_id": lane_id,
            "status": status,
            "research_question": goal_ko,
            "environment": "daily_ohlcv_research_only_portfolio_env",
            "state": state_setup,
            "action": action_setup,
            "reward": reward_setup,
            "baseline": baseline,
            "controls": controls,
            "metrics_to_watch": metrics_to_watch,
            "required_artifacts": required_artifacts,
            "stop_conditions": [
                "D5_NO_GO",
                "MODEL_BUILD_LOCKED",
                "PAPER_FORWARD_LOCKED",
                "LIVE_BROKER_ORDER_LOCKED",
                "MISSING_OR_STALE_ARTIFACT",
            ],
            "guardrails": guardrails,
            "recommended_next_step_ko": next_step_ko,
        },
        "next_step_ko": next_step_ko,
        "guardrails": guardrails,
    }


def _build_rl_guide_research_process_catalog(
    portfolio: dict[str, Any],
    gate: dict[str, Any],
    contract: dict[str, Any],
    *,
    validation_status: str,
    d5_consumed: bool,
) -> dict[str, Any]:
    baseline_comparison = portfolio.get("baseline_comparison") if isinstance(portfolio.get("baseline_comparison"), dict) else {}
    gate_verdict = gate.get("verdict") if isinstance(gate.get("verdict"), dict) else {}
    d3_strategy = str(baseline_comparison.get("best_d3_strategy") or "equal_weight_topk_momentum")
    d3_return = _to_float(baseline_comparison.get("best_d3_total_net_return"), None)
    d4_delta = _to_float(baseline_comparison.get("delta_vs_best_d3_total_net_return"), None)
    gate_status = str(gate.get("status") or gate_verdict.get("status") or "NO-GO")

    common_guardrails = [
        "research_only",
        "no_live_broker_orders",
        "no_profit_claims",
        "default_cost_23bp",
        "model_build_allowed_false",
        "paper_forward_allowed_false",
        "live_broker_order_allowed_false",
        "D5_NO_GO_until_verified_gates_pass",
    ]
    controls = ["no_trade_cash", "shuffle_control", "D3_rule_baseline", "supervised_baseline", "0/23/46bp_cost_sensitivity", "5_fold_oos_no_retune"]
    lanes = [
        _build_rl_guide_process_lane(
            lane_id="D3_BASELINE_FREEZE",
            title_ko="D3 기준선 고정/비교",
            stage="D3",
            status="WATCH_RESEARCH_ONLY",
            goal_ko="현재 가장 강한 rule/supervised 기준선을 고정하고 RL이 반드시 넘어야 할 비교 대상을 명확히 합니다.",
            state_setup=["D2 split", "rank score", "candidate universe", "future_return_1d는 평가 라벨로만 사용"],
            action_setup=["top-k selection", "equal weight", "no-trade baseline", "shuffle control"],
            reward_setup=["total_net_return_after_23bp", "MDD", "turnover", "hit rate"],
            current_limitations=[
                "price_basis/universe blockers가 남아 있어 모델 승격 근거가 아닙니다.",
                "D3는 RL이 아니라 rule/supervised baseline입니다.",
                "D4가 D3보다 약하면 RL을 교체 모델로 주장할 수 없습니다.",
            ],
            improvement_directions=[
                "D0 price basis와 D1 universe review를 먼저 고정합니다.",
                "D3 best baseline을 5-fold/OOS/cost sensitivity로 계속 비교 기준화합니다.",
                "shuffle/no-trade 대비 우위와 D3 대비 열위를 함께 표시합니다.",
            ],
            metrics_to_watch=["best_d3_total_net_return", "shuffle_delta", "MDD", "turnover", "cost_23bp_delta"],
            required_artifacts=["baseline_metrics.csv", "baseline_comparison.json", "D3 freeze manifest"],
            baseline=d3_strategy,
            controls=controls,
            next_step_ko="D3 baseline freeze artifact와 blockers를 먼저 확인한 뒤 D4는 baseline 대비 위험 overlay로만 연구합니다.",
            guardrails=common_guardrails,
        ),
        _build_rl_guide_process_lane(
            lane_id="D4_RL_RISK_OVERLAY",
            title_ko="D4 RL 위험/비중 Overlay",
            stage="D4",
            status="RESEARCH_ONLY" if validation_status == "PASS" else validation_status,
            goal_ko="D3 후보를 대체하지 않고 현금/노출/리밸런싱/감축 행동으로 위험을 조절하는지 검증합니다.",
            state_setup=["position_count", "top_score_bucket", "cash_fraction", "exposure_fraction", "drawdown/turnover/concentration buckets는 다음 확장 후보"],
            action_setup=["현재: hold/buy/add/sell/reduce", "목표: target_cash/25/50/75/100", "목표: reduce_risk/rebalance_to_d3_topk"],
            reward_setup=["policy_daily_net_return - D3_baseline_daily_net_return", "23bp turnover cost", "drawdown/concentration/invalid/churn penalties"],
            current_limitations=[
                "현재 정책은 tabular Q이며 신경망 policy_network artifact가 없습니다.",
                "현재 D4 성과는 D3 best baseline보다 약합니다.",
                "target exposure overlay action은 아직 D5 consumed schema로 증명되지 않았습니다.",
            ],
            improvement_directions=[
                "overlay action_schema_version을 환경/학습/D5에 먼저 추가합니다.",
                "baseline-relative reward와 cost-first reward를 ablation으로 비교합니다.",
                "action collapse(hold만 선택)와 invalid-action rate를 먼저 줄입니다.",
            ],
            metrics_to_watch=["delta_vs_best_d3_total_net_return", "action_distribution", "invalid_action_rate", "turnover", "drawdown", "concentration"],
            required_artifacts=["state_observations.csv", "reward_breakdown.csv", "action_distribution.csv", "policy_nav.csv", "observation_manifest.json"],
            baseline=d3_strategy,
            controls=controls,
            next_step_ko="overlay action schema가 D5에 소비되기 전까지 UI에는 현재 hold/buy/add/sell/reduce만 표시합니다.",
            guardrails=common_guardrails,
        ),
        _build_rl_guide_process_lane(
            lane_id="REWARD_ABLATION_LAB",
            title_ko="Reward Ablation 연구",
            stage="D4/D5",
            status="RESEARCH_ONLY",
            goal_ko="수익, 비용, drawdown, concentration, invalid, churn 벌점 중 어떤 보상 설계가 실패/개선에 영향을 주는지 분리합니다.",
            state_setup=["same D4 state contract", "same split/fold", "same seed unless preregistered"],
            action_setup=["same action schema", "invalid-action masking preserved", "no post-hoc action cherry-pick"],
            reward_setup=["recorded_reward", "no_turnover_cost", "no_drawdown_penalty", "baseline_relative_reward", "risk_only_overlay_reward"],
            current_limitations=[
                "ablation이 좋게 보여도 D5 NO-GO이면 승격 금지입니다.",
                "하나의 ablation만 골라 수익 주장하면 안 됩니다.",
                "비용 23bp/46bp 민감도 없이 결론을 내릴 수 없습니다.",
            ],
            improvement_directions=[
                "모든 ablation을 동일 fold/no-retune 조건으로 비교합니다.",
                "cost/drawdown/concentration 제거 시 과최적화 여부를 확인합니다.",
                "reward hacking 징후를 AI guidance format에 기록합니다.",
            ],
            metrics_to_watch=["reward_component_delta", "D3_delta", "turnover", "MDD", "invalid_action_rate", "fold_consistency"],
            required_artifacts=["reward_action_ablations.csv", "reward_component_summary.json", "fold_metrics.csv"],
            baseline=d3_strategy,
            controls=controls,
            next_step_ko="reward ablation 표준 포맷으로 어떤 벌점이 성과/위험을 망치는지 먼저 분해합니다.",
            guardrails=common_guardrails,
        ),
        _build_rl_guide_process_lane(
            lane_id="REGIME_DIAGNOSTICS",
            title_ko="시장 국면/실패 진단",
            stage="D7",
            status="WATCH_DIAGNOSTIC",
            goal_ko="변동성, breadth, score dispersion, drawdown regime별로 실패 원인을 찾아 다음 가설을 좁힙니다.",
            state_setup=["volatility_bucket", "market_breadth_proxy", "score_spread_bucket", "drawdown_bucket"],
            action_setup=["diagnostic grouping only", "no live action", "no broker order"],
            reward_setup=["D3/D4 delta by regime", "fold failure attribution", "cost sensitivity by regime"],
            current_limitations=[
                "현재는 진단용이며 regime 하나만 골라 GO로 바꾸면 안 됩니다.",
                "D7 산출물이 없거나 stale이면 PLACEHOLDER/WATCH로만 표시해야 합니다.",
            ],
            improvement_directions=[
                "실패 fold와 성공 fold를 함께 보여주는 heatmap을 고정합니다.",
                "regime별 action collapse와 turnover spike를 분리합니다.",
                "다음 D4 state 후보를 regime diagnostic 결과에서만 선택합니다.",
            ],
            metrics_to_watch=["regime_delta", "fold_failure_count", "turnover_spike", "drawdown_bucket_loss", "score_dispersion"],
            required_artifacts=["failure_reason_attribution.csv", "walk_forward_heatmap.csv", "regime_diagnostics.csv"],
            baseline=d3_strategy,
            controls=controls,
            next_step_ko="성공 regime만 골라 주장하지 말고 실패 regime를 다음 state/reward 후보로 전환합니다.",
            guardrails=common_guardrails,
        ),
        _build_rl_guide_process_lane(
            lane_id="SCENARIO_AUTOMATION",
            title_ko="시나리오 자동화/모델 후보 공장",
            stage="Scenario",
            status="RESEARCH_ONLY_AUTOMATION",
            goal_ko="여러 가정/비용/seed/fold/action/reward 조합을 정해진 manifest로 반복 실행하고 NO-GO/개선 방향을 자동 기록합니다.",
            state_setup=["scenario_id", "state_profile", "split_policy", "source_run_hashes"],
            action_setup=["action_profile", "reward_profile", "max_turnover_budget", "max_drawdown_limit"],
            reward_setup=["scenario gate status", "D3 delta", "cost sensitivity", "failure taxonomy"],
            current_limitations=[
                "대시보드는 실행 버튼이 아니라 read-only ledger입니다.",
                "자동화가 성공 주장을 만들지 않습니다. 실패/NO-GO를 더 빨리 찾는 장치입니다.",
                "scenario manifest/hashes가 없으면 AI 개선 지시도 막아야 합니다.",
            ],
            improvement_directions=[
                "state/action/reward profile을 manifest로 고정하고 batch runner로만 실행합니다.",
                "각 scenario가 같은 controls와 D5 no-retune gate를 통과하는지 비교합니다.",
                "AI는 fixed ai_guidance_format만 읽고 다음 실험을 제안하게 합니다.",
            ],
            metrics_to_watch=["scenario_gate_status_counts", "failed_count", "D3_delta_distribution", "cost_46bp_stress", "manifest_hash_coverage"],
            required_artifacts=["scenario_manifest.json", "scenario_batch_manifest.json", "comparison_rows.csv"],
            baseline=d3_strategy,
            controls=controls,
            next_step_ko="대시보드에서 lane별 한계/개선 방향을 읽고 CLI scenario plan으로만 연구 실행합니다.",
            guardrails=common_guardrails,
        ),
    ]

    blockers = [
        "BLOCKED_D5_NO_GO" if "NO-GO" in gate_status.upper() else "",
        "BLOCKED_MODEL_BUILD_LOCKED",
        "BLOCKED_PAPER_FORWARD_LOCKED",
        "BLOCKED_LIVE_BROKER_ORDER_LOCKED",
    ]
    if not d5_consumed:
        blockers.append("BLOCKED_D4_CONTRACT_NOT_CONSUMED_BY_D5")
    return {
        "schema_version": "daily_rl_research_process_catalog.v1",
        "status": "RESEARCH_ONLY_PROCESS_GUIDE",
        "source_run_id": portfolio.get("run_id") or "MISSING_SOURCE_RUN_ID",
        "artifact_hashes": portfolio.get("artifact_hashes") or {"status": "MISSING_ARTIFACT_HASHES"},
        "policy_type": "tabular_q",
        "action_schema_version": contract.get("schema_version"),
        "headline": {
            "best_d3_strategy": d3_strategy,
            "best_d3_total_return_pct": d3_return * 100.0 if d3_return is not None else None,
            "d4_delta_vs_best_d3_pct": d4_delta * 100.0 if d4_delta is not None else None,
            "d5_status": gate_status,
            "cost_round_trip_bp": contract.get("cost_round_trip_bp"),
        },
        "selector_help_ko": "연구 lane을 선택하면 환경/상태/행동/보상/한계/개선 방향/AI 고정 포맷을 같은 구조로 확인합니다.",
        "lanes": lanes,
        "blockers": [blocker for blocker in blockers if blocker],
        "guardrail": "Research process selector is read-only. It records what to test next; it does not run training, submit orders, unlock paper-forward, or claim profit.",
    }


def load_daily_rl_env_guide() -> dict[str, Any]:
    """Return a beginner-friendly, read-only map of the daily portfolio RL environment."""

    contract = environment_contract(max_positions=5, score_column="score_supervised_linear_ranker", candidate_limit=20)
    portfolio = load_portfolio_latest(sample_limit=25)
    gate = load_walk_forward_latest(sample_limit=0)
    portfolio_validation = portfolio.get("observation_manifest_validation") or {}
    portfolio_manifest = portfolio.get("observation_manifest") or {}
    gate_verdict = gate.get("verdict") or {}
    validation_status = str(
        portfolio_validation.get("status")
        or (contract.get("observation_manifest_validation") or {}).get("status")
        or "UNKNOWN"
    )
    d5_consumed = bool(gate_verdict.get("d4_state_contract_artifacts_consumed"))
    environment_built = validation_status == "PASS" and portfolio_manifest.get("gate", "D4_OBSERVATION_STATE_MANIFEST") == "D4_OBSERVATION_STATE_MANIFEST"
    guide_blockers = [
        "BLOCKED_D5_NO_GO" if "NO-GO" in str(gate.get("status") or gate_verdict.get("status") or "").upper() else "",
        "BLOCKED_MODEL_BUILD_LOCKED",
        "BLOCKED_PAPER_FORWARD_LOCKED",
        "BLOCKED_LIVE_BROKER_ORDER_LOCKED",
    ]
    if not portfolio.get("run_id"):
        guide_blockers.append("MISSING_SOURCE_RUN_ID")
    if not portfolio.get("artifact_hashes"):
        guide_blockers.append("MISSING_ARTIFACT_HASHES")
    if not d5_consumed:
        guide_blockers.append("BLOCKED_D4_CONTRACT_NOT_CONSUMED_BY_D5")
    signal_quality_summary = _build_rl_guide_signal_quality_summary()
    scenario_generator = _build_rl_guide_scenario_generator(signal_quality_summary)
    market_regime_audit_readiness = _build_rl_guide_market_regime_readiness(signal_quality_summary)
    improvement_queue = _build_rl_guide_improvement_queue(signal_quality_summary)
    scenario_comparison = _build_rl_guide_scenario_comparison(signal_quality_summary)
    page_maturity_report = _build_rl_guide_page_maturity_report(
        scenario_generator=scenario_generator,
        signal_summary=signal_quality_summary,
        market_regime_readiness=market_regime_audit_readiness,
        improvement_queue=improvement_queue,
        scenario_comparison=scenario_comparison,
    )
    research_workflow_catalog = _build_research_workflow_catalog_payload(
        signal_summary=signal_quality_summary,
        scenario_generator=scenario_generator,
        market_regime_readiness=market_regime_audit_readiness,
        improvement_queue=improvement_queue,
        scenario_comparison=scenario_comparison,
    )
    research_job_intent_ledger = load_research_job_intent_ledger(limit=10)
    rejection_analytics = load_rejection_analytics(limit=10)
    dashboard_first_completion_report = _build_dashboard_first_completion_report(
        workflow_catalog=research_workflow_catalog,
        intent_ledger=research_job_intent_ledger,
        rejection_analytics=rejection_analytics,
    )

    return {
        "mode": "daily_ohlcv_rl_environment_guide",
        "platform_stage": "RL_ENV_VISUAL_GUIDE_MVP",
        "status": "RESEARCH_ONLY",
        "read_only": True,
        "schema_version": "daily_rl_env_guide.v2",
        "source_run_id": portfolio.get("run_id") or "MISSING_SOURCE_RUN_ID",
        "source_stage": "D4_D5_RESEARCH_ONLY",
        "artifact_hashes": portfolio.get("artifact_hashes") or {"status": "MISSING_ARTIFACT_HASHES"},
        "policy_type": "tabular_q",
        "action_schema_version": contract.get("schema_version"),
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "blockers": [blocker for blocker in guide_blockers if blocker],
        "environment_built": environment_built,
        "maturity": "RESEARCH_ONLY_ENV_BUILT_NOT_PROFIT_READY",
        "plain_language_verdict": (
            "일봉 포트폴리오 강화학습 환경의 상태/행동/보상/마스크/누수 방지 계약은 구축되어 있습니다. "
            "다만 현재 증거는 연구·시나리오 실험용이며 수익성, 실거래, 브로커 주문 준비 상태는 아닙니다."
        ),
        "what_rl_means_here": {
            "agent": "정책/모델이 매일 관측(state)을 보고 행동(action)을 고릅니다.",
            "environment": "DailyPortfolioEnv가 보유 종목, 후보 종목, 비용, 보상, 종료 여부를 계산합니다.",
            "state": "미래 수익률을 보지 않고 현재 포지션 수와 현재 후보 점수 부호만 봅니다.",
            "action": "hold/buy/add/sell/reduce 중 하나를 고르되 action mask가 불가능한 행동을 막습니다.",
            "reward": "다음날 연구용 future_return_1d로 수익을 계산한 뒤 23bp 비용과 위험 벌점을 뺍니다.",
            "episode": "날짜 순서대로 하루씩 진행한 전체 기간입니다.",
        },
        "visual_flow": [
            {"id": "D2", "label": "D2 데이터셋", "summary": "일봉 feature/label/split", "status": "INPUT"},
            {"id": "D3", "label": "D3 예측/랭킹", "summary": "후보 점수와 baseline", "status": "INPUT"},
            {"id": "STATE", "label": "상태 관측", "summary": "position_count + top_score_bucket", "status": validation_status},
            {"id": "MASK", "label": "행동 마스크", "summary": "불가능한 buy/add/sell/reduce 차단", "status": validation_status},
            {"id": "ACTION", "label": "행동", "summary": "hold · buy · add · sell · reduce", "status": "RESEARCH_ONLY"},
            {"id": "REWARD", "label": "보상", "summary": "net return - cost/penalties", "status": "RESEARCH_ONLY"},
            {"id": "D5", "label": "워크포워드 게이트", "summary": "5-fold + 0/23/46bp + no retune", "status": gate.get("status", "NO-GO")},
        ],
        "state_contract": contract.get("state", {}),
        "action_space": contract.get("action_space", {}),
        "action_mask": contract.get("action_mask", {}),
        "reward_formula": contract.get("reward_formula"),
        "reward_components": contract.get("reward_components", []),
        "cost_round_trip_bp": contract.get("cost_round_trip_bp"),
        "fill_assumption": contract.get("fill_assumption"),
        "observation_manifest_status": (contract.get("observation_manifest") or {}).get("status"),
        "observation_manifest_validation": contract.get("observation_manifest_validation", {}),
        "learning_performance": _build_rl_guide_learning_performance(portfolio),
        "active_replay": _build_rl_guide_active_replay(portfolio, contract),
        "research_process_catalog": _build_rl_guide_research_process_catalog(
            portfolio,
            gate,
            contract,
            validation_status=validation_status,
            d5_consumed=d5_consumed,
        ),
        "scenario_generator": scenario_generator,
        "signal_quality_audit_summary": signal_quality_summary,
        "market_regime_audit_readiness": market_regime_audit_readiness,
        "improvement_queue": improvement_queue,
        "scenario_comparison": scenario_comparison,
        "page_maturity_report": page_maturity_report,
        "research_workflow_catalog": research_workflow_catalog,
        "research_job_intent_ledger": research_job_intent_ledger,
        "rejection_analytics": rejection_analytics,
        "dashboard_first_completion_report": dashboard_first_completion_report,
        "current_artifact_evidence": {
            "d4_status": portfolio.get("status"),
            "d4_readiness_status": portfolio.get("readiness_status"),
            "d4_observation_manifest_gate": portfolio_manifest.get("gate"),
            "d4_observation_manifest_validation_status": validation_status,
            "d4_reward_action_telemetry_sufficient_for_d4": portfolio_manifest.get("reward_action_telemetry_sufficient_for_d4"),
            "d5_status": gate.get("status"),
            "d5_readiness_status": gate.get("readiness_status"),
            "d5_d4_state_contract_artifacts_consumed": d5_consumed,
            "d5_d4_state_observation_rows": gate_verdict.get("d4_state_observation_rows"),
            "d5_d4_reward_action_ablation_rows": gate_verdict.get("d4_reward_action_ablation_rows"),
        },
        "well_built_checks": [
            {
                "check": "state_has_no_future_label",
                "status": "PASS",
                "meaning_ko": "관측값에는 future_return_1d가 들어가지 않습니다.",
            },
            {
                "check": "action_mask_available",
                "status": "PASS" if contract.get("action_mask") else "FAIL",
                "meaning_ko": "불가능한 행동을 마스크와 사유로 기록합니다.",
            },
            {
                "check": "reward_components_logged",
                "status": "PASS" if contract.get("reward_components") else "FAIL",
                "meaning_ko": "수익, 비용, 노출, 집중도, 무효행동, drawdown 벌점이 분해됩니다.",
            },
            {
                "check": "d4_observation_manifest_validation",
                "status": validation_status,
                "meaning_ko": "D4 상태 계약 검증 결과입니다.",
            },
            {
                "check": "d5_consumes_d4_state_contract",
                "status": "PASS" if d5_consumed else "WATCH",
                "meaning_ko": "워크포워드 게이트가 D4 상태/보상/액션 증거를 읽었는지입니다.",
            },
        ],
        "good_enough_for": [
            "여러 가정/시나리오 모델 smoke·mid 실험",
            "action mask와 reward 설계 검증",
            "D3 baseline 대비 D4/D5 연구 비교",
            "실패 원인과 다음 가설 생성",
        ],
        "not_good_enough_for": [
            "수익성 주장",
            "실거래 또는 브로커 주문",
            "paper-forward unlock",
            "D0/D1/D5 blocker를 무시한 모델 승격",
        ],
        "guardrail": "Daily RL environment guide is explanatory/read-only; no profit guarantee, no live/broker/orders, and no deployable model readiness claim.",
    }


def load_daily_flow_chart() -> dict[str, Any]:
    progress = load_daily_progress()
    nodes = [
        {
            "id": stage.get("id"),
            "label": stage.get("label"),
            "status": stage.get("status"),
            "severity": _status_severity(stage.get("status")),
            "evidence": stage.get("evidence"),
            "usage_guide": stage.get("usage_guide"),
        }
        for stage in progress.get("stages", [])
    ]
    edges = [
        {"from": "D0", "to": "D1", "label": "DB scope"},
        {"from": "D1", "to": "D2", "label": "allowed universe"},
        {"from": "D2", "to": "D3", "label": "causal dataset"},
        {"from": "D3", "to": "D4", "label": "baseline threshold"},
        {"from": "D4", "to": "D5", "label": "RL candidate evidence"},
        {"from": "D5", "to": "D6", "label": "gate visualization"},
        {"from": "D6", "to": "D7", "label": "research diagnostics"},
        {"from": "D7", "to": "D8", "label": "registry evidence"},
        {"from": "D8", "to": "D9", "label": "paper-forward lock"},
    ]
    return {
        "status": progress.get("overall_status"),
        "model_build_allowed": progress.get("model_build_allowed", False),
        "go_summary_allowed": progress.get("go_summary_allowed", False),
        "nodes": nodes,
        "edges": edges,
        "guardrail": "Flow map shows research evidence dependencies only; it does not unlock model training, broker, live, or order behavior.",
    }


def load_daily_metric_glossary() -> dict[str, Any]:
    return {
        "status": "REFERENCE_ONLY",
        "items": [
            {"term": "NO-GO", "meaning": "현재 증거로 모델 빌드/GO 요약을 허용하지 않는 상태.", "guardrail": "실패를 숨기지 않는다."},
            {"term": "WATCH", "meaning": "분류·가격·검증 중 하나가 아직 확정되지 않아 주의가 필요한 상태.", "guardrail": "WATCH는 PASS가 아니다."},
            {"term": "RESEARCH_ONLY", "meaning": "연구 산출물은 존재하지만 선택/실거래/배포 증거로 쓰면 안 되는 상태.", "guardrail": "D4 RL에 적용."},
            {"term": "MDD", "meaning": "고점 대비 최대 낙폭. 우상향 착시를 막는 핵심 리스크 지표.", "guardrail": "수익률과 항상 함께 봐야 한다."},
            {"term": "Turnover", "meaning": "포트폴리오 교체 강도. 높을수록 23bp 비용 압력이 커진다.", "guardrail": "비용 전 수익률 착시를 막는다."},
            {"term": "Hit rate", "meaning": "양(+)의 순수익 거래/일자 비율.", "guardrail": "단독으로는 수익성 증거가 아니다."},
            {"term": "Shuffle control", "meaning": "라벨/순서를 섞은 음성 대조군.", "guardrail": "알파 주장은 shuffle보다 좋아야 한다."},
            {"term": "Fold consistency", "meaning": "워크포워드 fold별 성과 일관성.", "guardrail": "한 fold cherry-pick 금지."},
            {"term": "model_build_allowed", "meaning": "모델 구현/학습 후보로 넘어갈 수 있는 게이트 플래그.", "guardrail": "false이면 UI도 구현 GO처럼 보이면 안 된다."},
            {"term": "Learning curve", "meaning": "학습 중 reward/return 변화. 안정화 여부와 과적합 의심 구간을 찾는 진단 그래프.", "guardrail": "상승 곡선만으로 수익성 또는 배포 가능성을 주장하지 않는다."},
            {"term": "Action distribution", "meaning": "hold/buy/sell 또는 target weight 선택 빈도. 한 행동 쏠림과 invalid action을 확인한다.", "guardrail": "정책 의도 설명용이며 주문 신호가 아니다."},
            {"term": "Portfolio trajectory", "meaning": "NAV, drawdown, turnover, cost, concentration이 시간에 따라 어떻게 움직였는지 보는 경로.", "guardrail": "D3/D5 control과 함께 보지 않은 trajectory는 선택 근거가 아니다."},
            {"term": "Symbol drilldown", "meaning": "개별 종목 OHLCV, 기간, 결측·보정 의심을 검사하는 읽기 전용 표/막대.", "guardrail": "개별 종목 매수·매도 추천 화면이 아니다."},
        ],
        "guardrail": "Metric glossary is explanatory only: research signal, not production proof, no profit/live/broker/order readiness.",
    }
def load_research_diagnostics_chart() -> dict[str, Any]:
    prediction = load_prediction_latest(sample_limit=0)
    portfolio = load_portfolio_latest(sample_limit=0)
    gate = load_walk_forward_latest(sample_limit=0)
    gate_verdict = gate.get("verdict") or {}
    diagnostics = [
        {
            "id": "D7_FEATURE_DIAGNOSTICS",
            "label": "Feature diagnostics",
            "status": "PLACEHOLDER_READY",
            "summary": "ret_1d/3d/5d/20d, volatility, momentum, rank score contribution and drift slices are planned as read-only diagnostics.",
            "evidence": f"D3 best={(prediction.get('verdict') or {}).get('best_strategy_by_total_net_return')} price_basis={prediction.get('price_basis')}",
            "next_artifact": "feature_importance_by_fold.csv",
            "guardrail": "feature importance is explanatory, not a profit claim.",
            "allowed_use": "feature별 fold 기여도와 drift를 비교해 D3/D4 실패 원인을 설명한다.",
            "blocked_use": "feature 중요도를 곧바로 종목 선택, 수익 주장, live signal로 사용하지 않는다.",
            "how_to_read_ko": "fold마다 같은 feature가 반복적으로 유효한지, price_basis unknown에 민감한 feature인지 먼저 본다.",
            "current_gap": "feature_importance_by_fold.csv가 생성되기 전까지 PLACEHOLDER_READY입니다.",
        },
        {
            "id": "D7_REGIME_DIAGNOSTICS",
            "label": "Regime diagnostics",
            "status": "PLACEHOLDER_READY",
            "summary": "market regime buckets should compare trend/volatility/liquidity periods before any swing-trading claim.",
            "evidence": f"D5 status={gate.get('status')} reasons={','.join((gate_verdict.get('reasons') or [])[:4])}",
            "next_artifact": "regime_bucket_metrics.csv",
            "guardrail": "regime labels must be forward-only and cannot retune OOS folds.",
            "allowed_use": "추세·변동성·유동성 regime별로 baseline/RL 성능이 무너지는 구간을 찾는다.",
            "blocked_use": "OOS fold를 보고 regime 정의를 재튜닝하지 않는다.",
            "how_to_read_ko": "regime bucket은 forward-only 규칙이어야 하며, 한 구간의 좋은 결과를 전체 성과처럼 말하지 않는다.",
            "current_gap": "regime_bucket_metrics.csv가 생성되기 전까지 PLACEHOLDER_READY입니다.",
        },
        {
            "id": "D7_CORRELATION_RISK",
            "label": "Correlation and concentration",
            "status": "PLACEHOLDER_READY",
            "summary": "portfolio trajectory, concentration, and universe clusters should be compared to avoid single-theme exposure.",
            "evidence": f"D4 validation={(portfolio.get('observation_manifest_validation') or {}).get('status')} state_contract={(portfolio.get('telemetry') or {}).get('state_contract')}",
            "next_artifact": "correlation_cluster_summary.csv",
            "guardrail": "correlation views are risk diagnostics, not selection proof.",
            "allowed_use": "상관·집중도·테마 쏠림을 보며 포트폴리오 리스크를 설명한다.",
            "blocked_use": "상관 클러스터를 종목 추천 또는 배포 가능한 allocation으로 사용하지 않는다.",
            "how_to_read_ko": "고상관 cluster가 손실 fold와 겹치는지 확인하고 concentration penalty 가설로만 사용한다.",
            "current_gap": "correlation_cluster_summary.csv가 생성되기 전까지 PLACEHOLDER_READY입니다.",
        },
        {
            "id": "D7_FAILURE_ANALYSIS",
            "label": "Failure analysis",
            "status": "PLACEHOLDER_READY",
            "summary": "NO-GO reasons, missing labels, invalid actions, drawdown spikes, and fold failures should be grouped before new RL reward changes.",
            "evidence": f"model_build_allowed={gate_verdict.get('model_build_allowed')} go_summary_allowed={gate_verdict.get('go_summary_allowed')}",
            "next_artifact": "failure_reason_attribution.csv",
            "guardrail": "failure visibility is mandatory; do not hide weak or flat RL outcomes.",
            "allowed_use": "NO-GO reason, invalid action, drawdown spike, fold failure를 묶어 다음 실험 가설을 만든다.",
            "blocked_use": "실패 fold를 숨기거나 성공 fold만 골라 GO처럼 표현하지 않는다.",
            "how_to_read_ko": "먼저 D0/D1/D3/D5 blocker를 확인하고, reward/action 변경은 그 다음에 사전등록한다.",
            "current_gap": "failure_reason_attribution.csv가 생성되기 전까지 PLACEHOLDER_READY입니다.",
        },
    ]
    return {
        "status": "WATCH",
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "cards": diagnostics,
        "items": diagnostics,
        "usage_guide": [_usage_for_stage("D7")],
        "summary": {
            "korean": "D7 연구 진단은 feature/regime/correlation/failure 원인 분석을 위한 읽기 전용 확장 영역입니다.",
            "current_contract": "PLACEHOLDER_READY_UNTIL_ARTIFACTS_EXIST",
            "required_before_claim": [
                "feature importance by fold",
                "regime bucket metrics",
                "correlation/concentration diagnostics",
                "failure attribution",
            ],
            "how_to_use": "D7은 새 모델을 고르는 화면이 아니라, 실패 원인과 다음 가설을 좁히는 연구 노트입니다.",
        },
        "guardrail": "D7 diagnostics are explanatory research surfaces only; no profit, live, broker, order, or deployable model claim.",
    }



def _sample_points(points: list[dict[str, Any]], *, maximum: int = 240) -> list[dict[str, Any]]:
    if len(points) <= maximum:
        return points
    step = max(1, len(points) // maximum)
    sampled = points[::step]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled[: maximum + 1]


def _metric_severity(metric: str, value: float | None) -> str:
    if value is None:
        return "block"
    if metric == "max_drawdown":
        return "block" if value <= -0.2 else "watch" if value < -0.1 else "pass"
    if metric in {"total_net_return", "delta_vs_no_trade_total_net_return", "delta_vs_shuffled_total_net_return", "hit_rate"}:
        return "pass" if value > 0 else "block"
    if metric == "mean_turnover":
        return "watch" if value > 0.5 else "pass"
    return "neutral"


def load_equity_overlay_chart(*, run: str | None = None) -> dict[str, Any]:
    prediction_dir = _latest_run_dir(DEFAULT_PREDICTION_ROOT, required_file="prediction_manifest.json", run_id=run)
    if prediction_dir is None:
        return load_not_started_surface("equity_overlay")
    prediction = load_prediction_latest(run=run, sample_limit=0)
    baseline_curves: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in _read_csv_rows(prediction_dir / "drawdown.csv", MAX_LIMIT):
        strategy = str(row.get("strategy") or "unknown")
        equity = _to_float(row.get("equity"))
        net_return = _to_float(row.get("net_return"))
        grouped.setdefault(strategy, []).append(
            {
                "x": row.get("date"),
                "y": equity,
                "net_return": net_return,
                "evidence_status": "LOADED" if equity is not None and net_return is not None else "INCOMPLETE_NUMERIC_EVIDENCE",
            }
        )
    for strategy, points in grouped.items():
        baseline_curves.append(
            {
                "id": f"D3:{strategy}",
                "label": strategy,
                "kind": "daily_baseline",
                "status": prediction.get("status"),
                "points": _sample_points(points),
            }
        )

    portfolio_curve: list[dict[str, Any]] = []
    portfolio_dir = _latest_run_dir(DEFAULT_PORTFOLIO_ROOT, required_file="rl_manifest.json")
    if portfolio_dir is not None:
        by_date: dict[str, float | None] = {}
        for row in _read_csv_rows(portfolio_dir / "positions.csv", MAX_LIMIT):
            date = str(row.get("date") or "")
            if date:
                by_date[date] = _to_float(row.get("equity"))
        if not by_date:
            for row in _read_csv_rows(portfolio_dir / "reward_breakdown.csv", MAX_LIMIT):
                date = str(row.get("date") or "")
                if date:
                    by_date[date] = _to_float(row.get("equity"))
        portfolio_curve = [
            {"x": date, "y": equity, "evidence_status": "LOADED" if equity is not None else "INCOMPLETE_NUMERIC_EVIDENCE"}
            for date, equity in sorted(by_date.items())
        ]

    gate_curve: list[dict[str, Any]] = []
    gate_dir = _latest_run_dir(DEFAULT_WALK_FORWARD_ROOT, required_file="walk_forward_manifest.json")
    gate = load_walk_forward_latest(sample_limit=0)
    selected_strategy = (gate.get("verdict") or {}).get("selected_strategy")
    if gate_dir is not None:
        fold_equity = 1.0
        for row in _read_csv_rows(gate_dir / "fold_metrics.csv", MAX_LIMIT):
            if row.get("control") != "actual" or (selected_strategy and row.get("strategy") != selected_strategy):
                continue
            net_return = _to_float(row.get("total_net_return"))
            if net_return is not None:
                fold_equity += net_return
            gate_curve.append(
                {
                    "x": row.get("fold_id"),
                    "y": fold_equity if net_return is not None else None,
                    "net_return": net_return,
                    "evidence_status": "LOADED" if net_return is not None else "INCOMPLETE_NUMERIC_EVIDENCE",
                }
            )

    curves = baseline_curves
    if portfolio_curve:
        curves.append(
            {
                "id": "D4:portfolio_rl",
                "label": "D4 constrained portfolio RL",
                "kind": "rl_research_only",
                "status": "RESEARCH_ONLY",
                "points": _sample_points(portfolio_curve),
            }
        )
    if gate_curve:
        curves.append(
            {
                "id": "D5:walk_forward_selected",
                "label": "D5 selected walk-forward folds",
                "kind": "walk_forward_gate",
                "status": gate.get("status"),
                "points": gate_curve,
            }
        )

    return {
        "status": gate.get("status") or prediction.get("status"),
        "run_id": prediction.get("run_id"),
        "selected_strategy": selected_strategy,
        "curves": curves,
        "guardrail": "Equity overlay is historical research visualization only; it is not a profit, broker, live, order, or deployable RL claim.",
    }


def load_walk_forward_heatmap_chart(*, run: str | None = None) -> dict[str, Any]:
    gate_dir = _latest_run_dir(DEFAULT_WALK_FORWARD_ROOT, required_file="walk_forward_manifest.json", run_id=run)
    if gate_dir is None:
        return load_not_started_surface("walk_forward_heatmap")
    gate = load_walk_forward_latest(run=run, sample_limit=0)
    verdict = gate.get("verdict") or {}
    selected_strategy = verdict.get("selected_strategy")
    metric_keys = [
        "total_net_return",
        "max_drawdown",
        "delta_vs_no_trade_total_net_return",
        "delta_vs_shuffled_total_net_return",
        "mean_turnover",
        "hit_rate",
    ]
    cells: list[dict[str, Any]] = []
    for row in _read_csv_rows(gate_dir / "fold_metrics.csv", MAX_LIMIT):
        if row.get("control") != "actual" or (selected_strategy and row.get("strategy") != selected_strategy):
            continue
        for metric in metric_keys:
            value = _to_float(row.get(metric))
            cells.append(
                {
                    "fold_id": row.get("fold_id"),
                    "strategy": row.get("strategy"),
                    "metric": metric,
                    "value": value,
                    "severity": _metric_severity(metric, value),
                    "evidence_status": "LOADED" if value is not None else "INCOMPLETE_NUMERIC_EVIDENCE",
                }
            )
    cost_series = [
        {
            "fold_id": row.get("fold_id"),
            "cost_bp": _to_float(row.get("cost_bp")),
            "total_net_return": _to_float(row.get("total_net_return")),
            "max_drawdown": _to_float(row.get("max_drawdown")),
            "strategy": row.get("strategy"),
        }
        for row in _read_csv_rows(gate_dir / "cost_sensitivity.csv", MAX_LIMIT)
        if not selected_strategy or row.get("strategy") == selected_strategy
    ]
    effective_gate = _effective_daily_model_gate(
        db=load_daily_db_summary(table_limit=0, flag_limit=0, window_limit=0),
        universe=load_universe_preview(limit=0),
        prediction=load_prediction_latest(sample_limit=0),
        gate_verdict=verdict,
        gate_status=gate.get("status"),
    )
    return {
        "status": gate.get("status"),
        "readiness_status": gate.get("readiness_status") or D5_RESEARCH_READINESS_STATUS,
        "run_id": gate.get("run_id"),
        "selected_strategy": selected_strategy,
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "no_live_broker_order_readiness": True,
        "effective_gate_blockers": effective_gate["effective_gate_blockers"],
        "cells": cells,
        "cost_series": cost_series,
        "guardrail": "Heatmap shows D5 gate evidence under cost/shuffle controls only; it does not authorize model build, profit, live, broker, or orders.",
    }


def load_run_scatter_chart() -> dict[str, Any]:
    prediction = load_prediction_latest(sample_limit=500)
    portfolio = load_portfolio_latest(sample_limit=0)
    gate = load_walk_forward_latest(sample_limit=0)
    points: list[dict[str, Any]] = []
    for row in prediction.get("baseline_metrics") or []:
        positions = _to_int(row.get("positions"), 1) or 1
        points.append(
            {
                "id": f"D3:{row.get('strategy')}",
                "label": row.get("strategy"),
                "kind": "daily_baseline",
                "status": prediction.get("status"),
                "x_max_drawdown": _to_float(row.get("max_drawdown")),
                "y_total_net_return": _to_float(row.get("total_net_return")),
                "size": max(1, positions),
            }
        )
    for row in ((portfolio.get("policy_metrics") or {}).get("metrics") or []):
        positions = _to_int(row.get("positions"), 1) or 1
        points.append(
            {
                "id": f"D4:{row.get('split')}",
                "label": f"D4 {row.get('split')}",
                "kind": "daily_rl",
                "status": portfolio.get("status"),
                "x_max_drawdown": _to_float(row.get("max_drawdown")),
                "y_total_net_return": _to_float(row.get("total_net_return")),
                "size": max(1, positions),
            }
        )
    gate_dir = _latest_run_dir(DEFAULT_WALK_FORWARD_ROOT, required_file="walk_forward_manifest.json")
    if gate_dir is not None:
        verdict = gate.get("verdict") or {}
        selected_strategy = verdict.get("selected_strategy")
        selected_rows = [
            row
            for row in _read_csv_rows(gate_dir / "fold_metrics.csv", MAX_LIMIT)
            if row.get("control") == "actual" and (not selected_strategy or row.get("strategy") == selected_strategy)
        ]
        if selected_rows:
            drawdowns = [_to_float(row.get("max_drawdown")) for row in selected_rows]
            returns = [_to_float(row.get("total_net_return")) for row in selected_rows]
            positions = [_to_int(row.get("positions")) for row in selected_rows]
            clean_drawdowns = [value for value in drawdowns if value is not None]
            clean_returns = [value for value in returns if value is not None]
            clean_positions = [value for value in positions if value is not None]
            points.append(
                {
                    "id": "D5:selected_walk_forward",
                    "label": f"D5 {selected_strategy}",
                    "kind": "walk_forward_gate",
                    "status": gate.get("status"),
                    "x_max_drawdown": min(clean_drawdowns) if clean_drawdowns else None,
                    "y_total_net_return": sum(clean_returns) if clean_returns else None,
                    "size": sum(max(0, value) for value in clean_positions),
                    "evidence_status": "LOADED" if len(clean_drawdowns) == len(selected_rows) and len(clean_returns) == len(selected_rows) else "INCOMPLETE_NUMERIC_EVIDENCE",
                }
            )
    return {
        "status": gate.get("status"),
        "points": points,
        "guardrail": "Risk/return scatter compares research artifacts only; positive points are not profit or deployment proof.",
    }


def load_universe_breakdown_chart() -> dict[str, Any]:
    manifest = load_universe_preview(limit=0)
    return {
        "status": manifest.get("verdict") or "WATCH",
        "counts_by_type": manifest.get("counts_by_type") or {},
        "counts_by_market": manifest.get("counts_by_market") or {},
        "counts_by_exclusion_reason": manifest.get("counts_by_exclusion_reason") or {},
        "summary": {
            "include_count": manifest.get("include_count"),
            "exclude_count": manifest.get("exclude_count"),
            "q_product_count": manifest.get("q_product_count"),
            "unmatched_quarantine_count": manifest.get("unmatched_quarantine_count"),
            "stockinfo_matched_table_count": manifest.get("stockinfo_matched_table_count"),
            "stockinfo_unmatched_table_count": manifest.get("stockinfo_unmatched_table_count"),
            "official_metadata_status": manifest.get("official_metadata_status"),
            "official_metadata_coverage_status": manifest.get("official_metadata_coverage_status"),
            "universe_certification_status": manifest.get("universe_certification_status"),
        },
        "guardrail": "Universe breakdown is heuristic WATCH until official metadata/manual review confirms KOSPI/KOSDAQ common-stock classification.",
    }


def load_symbol_chart(symbol_or_table: str, *, sample_limit: int = 160) -> dict[str, Any]:
    symbol = load_daily_symbol(symbol_or_table, sample_limit=_bounded_limit(sample_limit, default=160, maximum=200))
    rows = list(symbol.get("sample_rows_desc") or [])
    rows.reverse()
    points = [
        {
            "date": row.get("date"),
            "open": _to_float(row.get("open")),
            "high": _to_float(row.get("high")),
            "low": _to_float(row.get("low")),
            "close": _to_float(row.get("close")),
            "volume": _to_float(row.get("volume")),
        }
        for row in rows
    ]
    return {
        "status": "PASS" if points else "WATCH",
        "code": symbol.get("code"),
        "table": symbol.get("table"),
        "price_basis": symbol.get("price_basis"),
        "row_count": symbol.get("row_count"),
        "range": {"first_date": symbol.get("first_date"), "last_date": symbol.get("last_date")},
        "ohlcv": points,
        "guardrail": "Symbol OHLCV chart is historical read-only inspection only; it is not a prediction, trade signal, or profit claim.",
        "usage_guide": [
            {
                "section": "symbol_ohlcv_preview",
                "can_do": "개별 종목의 날짜 범위, OHLCV 막대, 거래량, 결측/불완전 evidence를 점검한다.",
                "must_not": "선택된 종목을 매수/매도 추천, 수익 보장, 실거래 준비 증거로 해석하지 않는다.",
                "next_action": "price_basis가 unknown이면 분할·배당·adjusted/raw 기준을 먼저 확인한다.",
            }
        ],
    }


def load_daily_artifacts(limit: int = 50) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    safe_limit = _bounded_limit(limit, default=50, maximum=500)
    for root, required, kind in (
        (DB_SUMMARY_ROOT.resolve(), "db_summary.json", "db_summary"),
        (DEFAULT_UNIVERSE_ROOT.resolve(), "universe.json", "universe_manifest"),
        (DEFAULT_DATASET_ROOT.resolve(), "dataset_manifest.json", "daily_ohlcv_dataset"),
        (DEFAULT_PREDICTION_ROOT.resolve(), "prediction_manifest.json", "daily_ohlcv_prediction"),
        (DEFAULT_PORTFOLIO_ROOT.resolve(), "rl_manifest.json", "daily_ohlcv_portfolio_rl"),
        (DEFAULT_WALK_FORWARD_ROOT.resolve(), "walk_forward_manifest.json", "daily_ohlcv_walk_forward"),
        (DEFAULT_DAILY_REGISTRY_ROOT.resolve(), "registry_manifest.json", "daily_ohlcv_registry"),
    ):
        if not root.exists():
            continue
        for run_dir in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            path = run_dir / required
            if run_dir.is_dir() and path.exists():
                artifacts.append(
                    {
                        "kind": kind,
                        "run_id": run_dir.name,
                        "artifact_dir": str(run_dir),
                        "primary_file": str(path),
                        "size_bytes": path.stat().st_size,
                        "modified_at": path.stat().st_mtime,
                    }
                )
    artifacts = sorted(artifacts, key=lambda row: row["modified_at"], reverse=True)
    return {
        "artifacts": artifacts[:safe_limit],
        "artifacts_total": len(artifacts),
        "artifacts_truncated": len(artifacts) > safe_limit,
        "limit": safe_limit,
        "read_only": True,
    }


def load_daily_progress() -> dict[str, Any]:
    db = load_daily_db_summary(table_limit=0, flag_limit=0, window_limit=0)
    universe = load_universe_preview(limit=0)
    dataset = load_dataset_latest(sample_limit=0)
    prediction = load_prediction_latest(sample_limit=0)
    portfolio = load_portfolio_latest(sample_limit=0)
    gate = load_walk_forward_latest(sample_limit=0)
    gate_verdict = gate.get("verdict") or {}
    registry = load_registry_latest(sample_limit=0)
    diagnostics = load_research_diagnostics_chart()
    baseline_delta = prediction.get("baseline_delta_summary") or {}
    effective_gate = _effective_daily_model_gate(
        db=db,
        universe=universe,
        prediction=prediction,
        gate_verdict=gate_verdict,
        gate_status=gate.get("status"),
    )
    stages = [
        _progress_stage(
            "D0",
            "DB 분석",
            "PASS" if db.get("table_count") else "BLOCKED",
            (
                f"tables={db.get('table_count')} rows={db.get('total_rows')} "
                f"price_basis={db.get('price_basis')} status={db.get('price_basis_status')} "
                f"decision_grade={db.get('decision_grade_return_status')} "
                f"quality_scope={db.get('quality_scan_scope')}"
            ),
        ),
        _progress_stage(
            "D1",
            "유니버스 관리",
            "WATCH",
            (
                f"include={universe.get('include_count')} exclude={universe.get('exclude_count')} "
                f"matched={universe.get('stockinfo_matched_table_count')} unmatched={universe.get('stockinfo_unmatched_table_count')} "
                f"official={universe.get('official_metadata_status')} verdict={universe.get('verdict')}"
            ),
        ),
        _progress_stage(
            "D2",
            "데이터셋",
            dataset.get("status", "NOT_STARTED"),
            (
                f"rows={(dataset.get('row_counts') or {}).get('feature_rows')} "
                f"eligible={(dataset.get('row_counts') or {}).get('eligible_rows')} "
                f"leakage={dataset.get('leakage_status')} split={dataset.get('split_chronology_status')} "
                f"price_basis={dataset.get('price_basis')} universe={dataset.get('universe_verdict')} "
                f"scope={dataset.get('artifact_scope')}"
            ),
        ),
        _progress_stage(
            "D3",
            "예측/Top-K",
            prediction.get("status", "NOT_STARTED"),
            (
                f"best={(prediction.get('verdict') or {}).get('best_strategy_by_total_net_return')} "
                f"go_summary={(prediction.get('verdict') or {}).get('go_summary_allowed')} "
                f"model_build={baseline_delta.get('model_build_allowed')} price_basis={prediction.get('price_basis')} "
                f"control={baseline_delta.get('shuffle_control_strategy')} best_rule={baseline_delta.get('best_rule_baseline_strategy')} "
                f"cost={baseline_delta.get('cost_round_trip_bp')}bp"
            ),
        ),
        _progress_stage(
            "D4",
            "포트폴리오 RL",
            portfolio.get("status", "NOT_STARTED"),
            (
                f"badge={(portfolio.get('verdict') or {}).get('ui_badge')} "
                f"state_contract={portfolio.get('state_contract_status') or (portfolio.get('observation_manifest_validation') or {}).get('status')} "
                f"unlocked={(portfolio.get('verdict') or {}).get('implementation_unlocked')}"
            ),
        ),
        _progress_stage(
            "D5",
            "워크포워드/게이트",
            gate.get("status", "NOT_STARTED"),
            (
                f"folds={gate_verdict.get('n_folds')} no_oos={gate_verdict.get('no_oos_retuning')} "
                f"d4_state={gate_verdict.get('d4_state_contract_status')} "
                f"model_build_allowed={effective_gate['model_build_allowed']} "
                f"effective_lock={','.join(effective_gate['effective_gate_blockers'][:3])} "
                f"reasons={','.join((gate_verdict.get('reasons') or [])[:4])}"
            ),
        ),
        _progress_stage(
            "D6",
            "대시보드 시각화",
            "PASS" if gate.get("status") != "NOT_STARTED" else "NOT_STARTED",
            (
                "Decision cockpit, glossary, flow, heatmap, scatter, equity overlay, universe breakdown, "
                "symbol chart, and registry panels are visible as read-only evidence surfaces."
                if gate.get("status") != "NOT_STARTED"
                else "D3-D5 artifacts required before full D6 result visualization."
            ),
        ),
        _progress_stage(
            "D7",
            "연구 진단",
            diagnostics.get("status", "WATCH"),
            (
                f"contract={(diagnostics.get('summary') or {}).get('current_contract')} "
                "feature/regime/correlation/failure placeholders visible; no alpha/profit claim."
            ),
        ),
        _progress_stage(
            "D8",
            "레지스트리",
            registry.get("status", "NOT_STARTED"),
            (
                f"promotion={registry.get('promotion_status')} model_build_allowed={registry.get('model_build_allowed')} "
                f"paper_forward_allowed={registry.get('paper_forward_allowed')} code_hash={str(registry.get('code_hash') or '—')[:12]}"
            ),
        ),
        _progress_stage(
            "D9",
            "페이퍼 포워드",
            registry.get("promotion_status", registry.get("status", "NOT_STARTED")),
            (
                f"paper_selected={(registry.get('candidate_registry') or {}).get('selected_strategy') or 'BLOCKED'} "
                f"live_broker_order_allowed={registry.get('live_broker_order_allowed')} "
                f"no_live_broker_order_readiness={registry.get('no_live_broker_order_readiness')}"
            ),
        ),
    ]
    provenance_matrix = [
        {
            "id": stage["id"],
            "status": stage["status"],
            "lock_labels": stage.get("lock_labels", []),
            "verification_commands": stage.get("verification_commands", []),
        }
        for stage in stages
    ]
    overall_status = "D0_D9_EVIDENCE_VISIBLE_MODEL_BUILD_NO_GO" if gate.get("status") != "NOT_STARTED" else "D0_D2_DATASET_READY_WATCH_D3_LOCKED"
    return {
        "mode": "daily_ohlcv_research_only",
        "overall_status": overall_status,
        "model_build_allowed": effective_gate["model_build_allowed"],
        "go_summary_allowed": effective_gate["go_summary_allowed"],
        "guardrail": "Daily OHLCV dashboard is read-only D0-D9 evidence. no live/broker/orders, no profit claim, no RL model readiness.",
        "stages": stages,
        "provenance_matrix": provenance_matrix,
        "page_usage_guide": [_usage_for_stage(stage_id) for stage_id in DAILY_PAGE_USAGE_GUIDE],
        "verification_commands": DAILY_STAGE_VERIFICATION_COMMANDS,
        "research_diagnostics": diagnostics,
        "effective_gate_blockers": effective_gate["effective_gate_blockers"],
    }


def load_coverage_chart() -> dict[str, Any]:
    db = load_daily_db_summary(table_limit=0, flag_limit=0, window_limit=0)
    return {
        "latest_date": db.get("latest_date"),
        "series": [
            {"label": "latest_date_tables", "value": db.get("tables_at_latest_date")},
            {"label": "total_tables", "value": db.get("table_count")},
            {"label": "total_rows", "value": db.get("total_rows")},
        ],
        "price_basis": db.get("price_basis"),
        "decision_grade_status": db.get("decision_grade_status"),
    }


def load_universe_chart() -> dict[str, Any]:
    manifest = load_universe_preview(limit=0)
    return {
        "verdict": manifest.get("verdict"),
        "counts_by_type": manifest.get("counts_by_type") or {},
        "counts_by_market": manifest.get("counts_by_market") or {},
        "counts_by_exclusion_reason": manifest.get("counts_by_exclusion_reason") or {},
        "official_metadata_status": manifest.get("official_metadata_status"),
        "official_metadata_coverage_status": manifest.get("official_metadata_coverage_status"),
        "universe_certification_status": manifest.get("universe_certification_status"),
        "universe_blocked_uses": manifest.get("universe_blocked_uses") or [],
    }


def load_not_started_surface(surface: str) -> dict[str, Any]:
    return {
        "surface": surface,
        "status": "NOT_STARTED",
        "guardrail": "D3-D6 model/result surfaces remain locked until their evidence artifacts exist; no model/profit/live readiness claim.",
        "required_before_go": ["D3 baselines", "D5 walk-forward controls", "D1/D2 architecture checkpoint"],
    }
