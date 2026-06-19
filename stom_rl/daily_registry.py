"""Research-only daily RL registry and paper-forward ledger artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .daily_ohlcv_db import REPO_ROOT
from .daily_rl_train import DEFAULT_PORTFOLIO_ROOT, ROUND_TRIP_COST_BP
from .daily_walk_forward import DEFAULT_WALK_FORWARD_ROOT

DEFAULT_DAILY_REGISTRY_ROOT = REPO_ROOT / "webui" / "rl_runs" / "daily_ohlcv_registry"
REGISTRY_SCHEMA_VERSION = 1
SAFE_RUN_RE = re.compile(r"^[0-9A-Za-z_.-]+$")
RESEARCH_GUARDRAIL = (
    "Research-only daily RL registry and paper-forward ledger; no live/broker/orders, "
    "no profit guarantee, no deployable readiness."
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_run_id(run_id: str) -> str:
    rid = str(run_id or "").strip()
    if not SAFE_RUN_RE.match(rid) or rid in {".", ".."} or "/" in rid or "\\" in rid:
        raise ValueError("run_id contains unsafe characters")
    return rid


def _safe_resolve_dir(path: Path | str) -> Path:
    return Path(path).resolve()


def _latest_run_dir(root: Path, required_file: str) -> Path:
    root = root.resolve()
    if not root.exists():
        raise FileNotFoundError(f"No artifact root: {root}")
    candidates = [path.parent for path in root.glob(f"*/{required_file}") if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"No {required_file} under {root}")
    return max(candidates, key=lambda p: (p / required_file).stat().st_mtime)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _optional_json(path: Path) -> dict[str, Any]:
    return _read_json(path) if path.exists() else {}


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_payload(payload: Any) -> str:
    return _sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))


def _sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_hashes() -> dict[str, str]:
    source_paths = [
        REPO_ROOT / "stom_rl" / "daily_rl_train.py",
        REPO_ROOT / "stom_rl" / "daily_walk_forward.py",
        REPO_ROOT / "stom_rl" / "daily_registry.py",
        REPO_ROOT / "webui" / "daily_ohlcv_dashboard.py",
        REPO_ROOT / "webui" / "app.py",
        REPO_ROOT / "webui" / "v2_src" / "src" / "lib" / "dailyOhlcvApi.ts",
        REPO_ROOT / "webui" / "v2_src" / "src" / "tabs" / "DailyOhlcvTab.svelte",
        REPO_ROOT / "webui" / "v2_src" / "src" / "tabs" / "dailyOhlcv" / "DailyProgressTimeline.svelte",
        REPO_ROOT / "webui" / "v2_src" / "src" / "tabs" / "dailyOhlcv" / "DailyVisualLabCard.svelte",
    ]
    hashes: dict[str, str] = {}
    for path in source_paths:
        digest = _sha256_file(path)
        if digest is None:
            raise FileNotFoundError(f"Required registry source hash file is missing: {path}")
        hashes[str(path.relative_to(REPO_ROOT)).replace("\\", "/")] = digest
    return hashes


def _bool_false(value: Any) -> bool:
    return value is False or str(value).lower() in {"false", "0", "no"}


def _strict_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        result = float(value)
        if result != result or result in {float("inf"), float("-inf")}:
            return None
        return result
    except (TypeError, ValueError):
        return None


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


def _stage_surface(*, portfolio_manifest: dict[str, Any], gate_verdict: dict[str, Any]) -> dict[str, Any]:
    surface = {**gate_verdict, **portfolio_manifest}
    if "verdict" not in surface and surface.get("universe_verdict") is not None:
        surface["verdict"] = surface.get("universe_verdict")
    return surface


def _price_basis_verified(surface: dict[str, Any]) -> bool:
    price_basis = str(surface.get("price_basis") or "").lower()
    status = str(surface.get("price_basis_status") or surface.get("price_basis_review_status") or "").upper()
    decision_status = str(surface.get("decision_grade_return_status") or "")
    return (
        price_basis in PRICE_BASIS_VERIFIED_VALUES
        and status in PRICE_BASIS_VERIFIED_STATUSES
        and not decision_status.startswith("BLOCKED")
    )


def _universe_official_or_manual_verified(surface: dict[str, Any]) -> bool:
    verdict = str(surface.get("verdict") or "")
    review_status = surface.get("universe_review_status")
    official_status = str(surface.get("official_metadata_status") or "")
    coverage_status = str(surface.get("official_metadata_coverage_status") or "")
    certification_status = str(surface.get("universe_certification_status") or "")
    return (
        verdict == UNIVERSE_VERIFIED_VERDICT
        and (review_status is None or str(review_status) == UNIVERSE_VERIFIED_VERDICT)
        and official_status == OFFICIAL_METADATA_VERIFIED_STATUS
        and coverage_status == OFFICIAL_METADATA_COMPLETE_COVERAGE
        and certification_status == UNIVERSE_VERIFIED_VERDICT
    )



def _registry_effective_blockers(
    *,
    portfolio_verdict: dict[str, Any],
    gate_verdict: dict[str, Any],
    portfolio_manifest: dict[str, Any],
    baseline_comparison: dict[str, Any],
    baseline_comparison_missing: bool,
    policy_nav_missing: bool,
    policy_nav_rows: list[dict[str, str]],
    policy_nav_numeric_invalid: bool,
) -> list[str]:
    blockers: list[str] = []
    stage_surface = _stage_surface(portfolio_manifest=portfolio_manifest, gate_verdict=gate_verdict)
    if not _price_basis_verified(stage_surface):
        blockers.append("D0_PRICE_BASIS_NOT_VERIFIED")
    if not _universe_official_or_manual_verified(stage_surface):
        blockers.append("D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED")
    baseline_delta = _strict_float(baseline_comparison.get("delta_vs_best_d3_total_net_return"))
    gate_reasons = {str(reason) for reason in gate_verdict.get("reasons") or []}
    if baseline_comparison_missing or baseline_delta is None:
        blockers.append("D3_BASELINE_EVIDENCE_MISSING")
    elif baseline_delta < 0:
        blockers.append("D3_BASELINE_NOT_PROMOTABLE")
    elif "RL_POLICY_UNDERPERFORMS_D3_BASELINE" in gate_reasons:
        blockers.append("D3_BASELINE_NOT_PROMOTABLE")
    if portfolio_verdict.get("implementation_unlocked") is not True:
        blockers.append("D4_IMPLEMENTATION_NOT_UNLOCKED")
    if gate_verdict.get("status") != "PASS" or gate_verdict.get("model_build_allowed") is not True:
        blockers.append("D5_WALK_FORWARD_NOT_PASS")
    if policy_nav_missing or not policy_nav_rows:
        blockers.append("D9_POLICY_NAV_EVIDENCE_MISSING")
    elif policy_nav_numeric_invalid:
        blockers.append("D9_POLICY_NAV_NUMERIC_EVIDENCE_INVALID")
    return sorted(dict.fromkeys(blockers))

def _registry_reasons(
    *,
    portfolio_verdict: dict[str, Any],
    gate_verdict: dict[str, Any],
    portfolio_manifest: dict[str, Any],
) -> list[str]:
    stage_surface = _stage_surface(portfolio_manifest=portfolio_manifest, gate_verdict=gate_verdict)
    reasons: list[str] = []
    reasons.extend(str(reason) for reason in gate_verdict.get("reasons") or [])
    if _bool_false(gate_verdict.get("model_build_allowed")):
        reasons.append("MODEL_BUILD_LOCKED_BY_D5_GATE")
    if _bool_false(portfolio_verdict.get("implementation_unlocked")):
        reasons.append("D4_IMPLEMENTATION_LOCKED_RESEARCH_ONLY")
    if not _price_basis_verified(stage_surface):
        if str(stage_surface.get("price_basis") or "").lower() == "unknown":
            reasons.append("PRICE_BASIS_UNKNOWN")
        else:
            reasons.append("PRICE_BASIS_NOT_VERIFIED")
    if not _universe_official_or_manual_verified(stage_surface):
        if str(stage_surface.get("universe_review_status") or "").startswith("WATCH"):
            reasons.append("UNIVERSE_WATCH_HEURISTIC")
        else:
            reasons.append("UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED")
    reasons.append("NO_LIVE_BROKER_ORDER_SURFACE")
    return sorted(dict.fromkeys(reasons))


def _build_realized_returns(policy_nav_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    realized: list[dict[str, Any]] = []
    previous_nav: float | None = None
    for row in policy_nav_rows:
        nav = _strict_float(row.get("policy_nav"))
        reward = _strict_float(row.get("policy_reward"))
        current_drawdown = _strict_float(row.get("policy_current_drawdown"))
        numeric_errors: list[str] = []
        if nav is None:
            numeric_errors.append("INVALID_POLICY_NAV")
        if reward is None and row.get("policy_reward") not in (None, ""):
            numeric_errors.append("INVALID_POLICY_REWARD")
        if current_drawdown is None and row.get("policy_current_drawdown") not in (None, ""):
            numeric_errors.append("INVALID_POLICY_CURRENT_DRAWDOWN")
        realized_return = None if nav is None or previous_nav in (None, 0.0) else (nav / previous_nav) - 1.0
        if nav is not None:
            previous_nav = nav
        realized.append(
            {
                "date": row.get("date"),
                "split": row.get("split"),
                "paper_nav": nav,
                "realized_return": realized_return,
                "policy_reward": reward,
                "current_drawdown": current_drawdown,
                "evidence_status": "BLOCKED_NUMERIC_EVIDENCE" if numeric_errors else "COMPLETE_NUMERIC_EVIDENCE",
                "numeric_error": ";".join(numeric_errors),
                "source": "policy_nav_research_artifact_not_live_trade",
            }
        )
    return realized


def _build_drawdown_rows(policy_nav_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    peak: float | None = None
    for row in policy_nav_rows:
        nav = _strict_float(row.get("policy_nav"))
        reported = _strict_float(row.get("policy_current_drawdown"))
        numeric_errors: list[str] = []
        if nav is None:
            numeric_errors.append("INVALID_POLICY_NAV")
            computed = None
        else:
            peak = nav if peak is None else max(peak, nav)
            computed = 0.0 if not peak else (nav / peak) - 1.0
        if reported is None and row.get("policy_current_drawdown") not in (None, ""):
            numeric_errors.append("INVALID_POLICY_CURRENT_DRAWDOWN")
        paper_forward_drawdown = reported if reported is not None else computed
        rows.append(
            {
                "date": row.get("date"),
                "split": row.get("split"),
                "paper_nav": nav,
                "paper_forward_drawdown": paper_forward_drawdown,
                "computed_drawdown": computed,
                "evidence_status": "BLOCKED_NUMERIC_EVIDENCE" if numeric_errors else "COMPLETE_NUMERIC_EVIDENCE",
                "numeric_error": ";".join(numeric_errors),
                "source": "research_policy_nav_not_live_account",
            }
        )
    return rows


def _policy_nav_numeric_invalid(policy_nav_rows: list[dict[str, str]]) -> bool:
    for row in policy_nav_rows:
        if _strict_float(row.get("policy_nav")) is None:
            return True
        if row.get("policy_reward") not in (None, "") and _strict_float(row.get("policy_reward")) is None:
            return True
        if row.get("policy_current_drawdown") not in (None, "") and _strict_float(row.get("policy_current_drawdown")) is None:
            return True
    return False

def _blocked_realized_return_row(reason: str) -> dict[str, Any]:
    return {
        "date": "",
        "split": "",
        "paper_nav": None,
        "realized_return": None,
        "policy_reward": None,
        "current_drawdown": None,
        "evidence_status": "BLOCKED_MISSING_POLICY_NAV",
        "numeric_error": reason,
        "source": "missing_policy_nav_research_artifact_not_live_trade",
    }


def _blocked_drawdown_row(reason: str) -> dict[str, Any]:
    return {
        "date": "",
        "split": "",
        "paper_nav": None,
        "paper_forward_drawdown": None,
        "computed_drawdown": None,
        "evidence_status": "BLOCKED_MISSING_POLICY_NAV",
        "numeric_error": reason,
        "source": "missing_policy_nav_research_artifact_not_live_account",
    }


def _build_paper_selection_rows(
    *,
    gate_verdict: dict[str, Any],
    portfolio_manifest: dict[str, Any],
    reasons: list[str],
    model_build_allowed: bool,
) -> list[dict[str, Any]]:
    selected_strategy = gate_verdict.get("selected_strategy") or portfolio_manifest.get("score_column") or "tabular_q_constrained_daily_portfolio_rl"
    if model_build_allowed:
        return [
            {
                "date": gate_verdict.get("generated_at") or "",
                "code": "",
                "rank": "",
                "paper_weight": 0,
                "paper_only_selected": True,
                "selection_status": "PAPER_ONLY_PLANNING_ALLOWED_NOT_LIVE",
                "strategy": selected_strategy,
                "reason": "MODEL_BUILD_GATE_TRUE_BUT_LIVE_BROKER_ORDERS_STILL_DISABLED",
            }
        ]
    selection_status = "BLOCKED_BY_D5_NO_GO" if gate_verdict.get("status") != "PASS" else "BLOCKED_BY_EFFECTIVE_RESEARCH_GATE"
    return [
        {
            "date": gate_verdict.get("generated_at") or "",
            "code": "",
            "rank": "",
            "paper_weight": 0,
            "paper_only_selected": False,
            "selection_status": selection_status,
            "strategy": selected_strategy,
            "reason": ";".join(reasons),
        }
    ]


def _build_drift_rows(
    *,
    portfolio_manifest: dict[str, Any],
    gate_verdict: dict[str, Any],
    config_hash: str,
    data_hash: str,
    code_hash: str,
    effective_blockers: list[str],
) -> list[dict[str, Any]]:
    stage_surface = _stage_surface(portfolio_manifest=portfolio_manifest, gate_verdict=gate_verdict)
    price_basis = stage_surface.get("price_basis") or "unknown"
    universe_status = stage_surface.get("universe_review_status") or stage_surface.get("verdict") or "unknown"
    price_basis_verified = _price_basis_verified(stage_surface)
    universe_verified = _universe_official_or_manual_verified(stage_surface)
    return [
        {
            "metric": "price_basis",
            "value": price_basis,
            "reference": "verified adjusted/raw/split/dividend basis required",
            "status": "PASS" if price_basis_verified else "BLOCKED",
            "action": "keep model_build_allowed=false until price basis is verified",
        },
        {
            "metric": "universe_review_status",
            "value": universe_status,
            "reference": "official KRX/manual metadata validation required",
            "status": "PASS" if universe_verified else "WATCH",
            "action": "keep heuristic universe warning visible until official/manual review evidence is complete",
        },
        {
            "metric": "d5_gate_status",
            "value": gate_verdict.get("status") or "unknown",
            "reference": "NO-GO blocks model build",
            "status": "BLOCKED" if gate_verdict.get("status") != "PASS" else "PASS",
            "action": "block promotion when D5 is not PASS",
        },
        {
            "metric": "model_build_allowed",
            "value": not effective_blockers,
            "reference": "strict D0/D1/D3/D4/D5 effective gates",
            "status": "BLOCKED" if effective_blockers else "PASS",
            "action": "no trained model build or deployable readiness claim",
        },
        {
            "metric": "effective_model_gate",
            "value": "PASS" if not effective_blockers else ";".join(effective_blockers),
            "reference": "cross-stage D0/D1/D3/D4/D5 lock reasons",
            "status": "PASS" if not effective_blockers else "BLOCKED",
            "action": "paper-forward remains blocked until every effective blocker is cleared",
        },
        {"metric": "config_hash", "value": config_hash, "reference": "registry reproducibility", "status": "TRACKED", "action": "compare before paper-forward continuation"},
        {"metric": "data_hash", "value": data_hash, "reference": "source artifact reproducibility", "status": "TRACKED", "action": "compare before paper-forward continuation"},
        {"metric": "code_hash", "value": code_hash, "reference": "source implementation reproducibility", "status": "TRACKED", "action": "compare before paper-forward continuation"},
    ]


def build_daily_registry(
    *,
    portfolio_run_dir: Path | str | None = None,
    walk_forward_run_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Build a research-only registry payload from the latest daily RL evidence runs."""

    portfolio_dir = _safe_resolve_dir(portfolio_run_dir) if portfolio_run_dir else _latest_run_dir(DEFAULT_PORTFOLIO_ROOT, "rl_manifest.json")
    walk_dir = _safe_resolve_dir(walk_forward_run_dir) if walk_forward_run_dir else _latest_run_dir(DEFAULT_WALK_FORWARD_ROOT, "walk_forward_manifest.json")

    portfolio_manifest = _read_json(portfolio_dir / "rl_manifest.json")
    portfolio_verdict = _optional_json(portfolio_dir / "verdict.json") or portfolio_manifest.get("verdict", {})
    baseline_comparison_path = portfolio_dir / "baseline_comparison.json"
    baseline_comparison = _optional_json(baseline_comparison_path)
    policy_evaluation = _optional_json(portfolio_dir / "policy_evaluation_manifest.json")
    walk_manifest = _read_json(walk_dir / "walk_forward_manifest.json")
    gate_verdict = _optional_json(walk_dir / "gate_verdict.json") or walk_manifest.get("verdict", {})

    file_hashes = {
        "portfolio_rl_manifest": _sha256_file(portfolio_dir / "rl_manifest.json"),
        "portfolio_verdict": _sha256_file(portfolio_dir / "verdict.json"),
        "portfolio_baseline_comparison": _sha256_file(portfolio_dir / "baseline_comparison.json"),
        "portfolio_policy_nav": _sha256_file(portfolio_dir / "policy_nav.csv"),
        "walk_forward_manifest": _sha256_file(walk_dir / "walk_forward_manifest.json"),
        "walk_forward_gate_verdict": _sha256_file(walk_dir / "gate_verdict.json"),
        "walk_forward_fold_metrics": _sha256_file(walk_dir / "fold_metrics.csv"),
    }
    policy_nav_path = portfolio_dir / "policy_nav.csv"
    policy_nav_missing = not policy_nav_path.exists()
    policy_nav_rows = _read_csv_rows(policy_nav_path)
    policy_nav_numeric_invalid = _policy_nav_numeric_invalid(policy_nav_rows) if policy_nav_rows else False
    source_hashes = _source_hashes()
    config_hash = _sha256_payload(
        {
            "portfolio_manifest": portfolio_manifest,
            "portfolio_verdict": portfolio_verdict,
            "baseline_comparison": baseline_comparison,
            "policy_evaluation": policy_evaluation,
            "walk_forward_manifest": walk_manifest,
            "gate_verdict": gate_verdict,
        }
    )
    data_hash = _sha256_payload(
        {
            "prediction_manifest_sha": portfolio_manifest.get("prediction_manifest_sha"),
            "portfolio_dir": portfolio_dir.name,
            "walk_forward_dir": walk_dir.name,
            "file_hashes": file_hashes,
        }
    )
    code_hash = _sha256_payload(source_hashes)
    effective_blockers = _registry_effective_blockers(
        portfolio_verdict=portfolio_verdict,
        gate_verdict=gate_verdict,
        portfolio_manifest=portfolio_manifest,
        baseline_comparison=baseline_comparison,
        baseline_comparison_missing=not baseline_comparison_path.exists(),
        policy_nav_missing=policy_nav_missing,
        policy_nav_rows=policy_nav_rows,
        policy_nav_numeric_invalid=policy_nav_numeric_invalid,
    )
    reasons = _registry_reasons(portfolio_verdict=portfolio_verdict, gate_verdict=gate_verdict, portfolio_manifest=portfolio_manifest)
    reasons = sorted(dict.fromkeys([*reasons, *effective_blockers]))
    model_build_allowed = not effective_blockers
    promotion_status = "PAPER_ONLY_REVIEW_REQUIRED" if model_build_allowed else "BLOCKED_RESEARCH_ONLY_NO_LIVE_BROKER_ORDER"
    stage_surface = _stage_surface(portfolio_manifest=portfolio_manifest, gate_verdict=gate_verdict)
    candidate = {
        "candidate_id": portfolio_manifest.get("run_id") or portfolio_dir.name,
        "strategy": baseline_comparison.get("policy_strategy") or "tabular_q_constrained_daily_portfolio_rl",
        "portfolio_run_id": portfolio_manifest.get("run_id") or portfolio_dir.name,
        "walk_forward_run_id": walk_manifest.get("run_id") or walk_dir.name,
        "promotion_status": promotion_status,
        "model_build_allowed": model_build_allowed,
        "paper_forward_allowed": model_build_allowed,
        "live_broker_order_allowed": False,
        "no_live_broker_order_readiness": True,
        "config_hash": config_hash,
        "data_hash": data_hash,
        "code_hash": code_hash,
        "file_hashes": file_hashes,
        "source_hashes": source_hashes,
        "price_basis": stage_surface.get("price_basis") or "unknown",
        "price_basis_status": stage_surface.get("price_basis_status") or stage_surface.get("price_basis_review_status"),
        "decision_grade_return_status": stage_surface.get("decision_grade_return_status"),
        "verdict": stage_surface.get("verdict") or stage_surface.get("universe_review_status"),
        "universe_review_status": stage_surface.get("universe_review_status"),
        "official_metadata_status": stage_surface.get("official_metadata_status"),
        "official_metadata_coverage_status": stage_surface.get("official_metadata_coverage_status"),
        "universe_certification_status": stage_surface.get("universe_certification_status"),
        "d4_status": portfolio_verdict.get("status") or portfolio_manifest.get("status"),
        "d5_status": gate_verdict.get("status"),
        "cost_round_trip_bp": gate_verdict.get("cost_round_trip_bp") or baseline_comparison.get("cost_round_trip_bp") or ROUND_TRIP_COST_BP,
        "baseline_delta_vs_best_d3": baseline_comparison.get("delta_vs_best_d3_total_net_return"),
        "reasons": reasons,
        "effective_gate_blockers": effective_blockers,
    }
    if policy_nav_missing:
        realized_returns = [_blocked_realized_return_row("POLICY_NAV_CSV_MISSING")]
        drawdown_rows = [_blocked_drawdown_row("POLICY_NAV_CSV_MISSING")]
    elif not policy_nav_rows:
        realized_returns = [_blocked_realized_return_row("POLICY_NAV_CSV_EMPTY")]
        drawdown_rows = [_blocked_drawdown_row("POLICY_NAV_CSV_EMPTY")]
    else:
        realized_returns = _build_realized_returns(policy_nav_rows)
        drawdown_rows = _build_drawdown_rows(policy_nav_rows)
    paper_selected = _build_paper_selection_rows(gate_verdict=gate_verdict, portfolio_manifest=portfolio_manifest, reasons=reasons, model_build_allowed=model_build_allowed)
    drift = _build_drift_rows(
        portfolio_manifest=portfolio_manifest,
        gate_verdict=gate_verdict,
        config_hash=config_hash,
        data_hash=data_hash,
        code_hash=code_hash,
        effective_blockers=effective_blockers,
    )
    generated_at = _utc_now()
    decision_log = [
        {
            "timestamp": generated_at,
            "event": "registry_created",
            "candidate_id": candidate["candidate_id"],
            "status": "RESEARCH_ONLY",
            "detail": "Registry assembled from generated D4/D5 evidence artifacts only.",
        },
        {
            "timestamp": generated_at,
            "event": "promotion_status_set",
            "candidate_id": candidate["candidate_id"],
            "status": promotion_status,
            "reasons": reasons,
        },
        {
            "timestamp": generated_at,
            "event": "live_broker_order_blocked",
            "candidate_id": candidate["candidate_id"],
            "status": "BLOCKED",
            "detail": "Dashboard/API registry surface is read-only and cannot place orders.",
        },
    ]
    manifest = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "RESEARCH_ONLY_BLOCKED" if not model_build_allowed else "PAPER_ONLY_REVIEW_REQUIRED",
        "guardrail": RESEARCH_GUARDRAIL,
        "source_portfolio_run_dir": str(portfolio_dir),
        "source_walk_forward_run_dir": str(walk_dir),
        "portfolio_run_id": candidate["portfolio_run_id"],
        "walk_forward_run_id": candidate["walk_forward_run_id"],
        "promotion_status": promotion_status,
        "model_build_allowed": model_build_allowed,
        "paper_forward_allowed": model_build_allowed,
        "live_broker_order_allowed": False,
        "no_live_broker_order_readiness": True,
        "cost_assumption_round_trip_bp": candidate["cost_round_trip_bp"],
        "config_hash": config_hash,
        "data_hash": data_hash,
        "code_hash": code_hash,
        "effective_gate_blockers": effective_blockers,
        "source_hashes": source_hashes,
        "row_counts": {
            "candidate_registry_rows": 1,
            "paper_selected_rows": len(paper_selected),
            "realized_return_rows": len(realized_returns),
            "drift_rows": len(drift),
            "drawdown_rows": len(drawdown_rows),
            "decision_log_rows": len(decision_log),
        },
    }
    return {
        "manifest": manifest,
        "candidate_registry": {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": manifest["status"],
            "guardrail": RESEARCH_GUARDRAIL,
            "candidates": [candidate],
        },
        "paper_selected": paper_selected,
        "realized_returns": realized_returns,
        "drift": drift,
        "drawdown": drawdown_rows,
        "decision_log": decision_log,
    }


def write_registry_artifacts(
    result: dict[str, Any],
    *,
    run_id: str | None = None,
    artifact_root: Path | str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    root = Path(artifact_root or DEFAULT_DAILY_REGISTRY_ROOT).resolve()
    default_root = DEFAULT_DAILY_REGISTRY_ROOT.resolve()
    try:
        root.relative_to(default_root)
    except ValueError:
        if root != default_root:
            raise ValueError("Daily OHLCV registry artifacts must stay under webui/rl_runs/daily_ohlcv_registry")
    rid = _validate_run_id(run_id or f"registry_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    out_dir = (root / rid).resolve()
    out_dir.relative_to(root)
    if out_dir.exists() and any(out_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"Daily registry artifact run_id already exists: {rid}")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "registry_manifest": out_dir / "registry_manifest.json",
        "candidate_registry": out_dir / "candidate_registry.json",
        "paper_selected": out_dir / "paper_selected.csv",
        "realized_returns": out_dir / "realized_returns.csv",
        "drift": out_dir / "drift.csv",
        "drawdown": out_dir / "drawdown.csv",
        "decision_log": out_dir / "decision_log.jsonl",
    }
    manifest = {**result["manifest"], "run_id": rid, "artifact_dir": str(out_dir), "artifacts": {key: str(path) for key, path in paths.items()}}
    _write_json(paths["registry_manifest"], manifest)
    _write_json(paths["candidate_registry"], result["candidate_registry"])
    _write_csv(paths["paper_selected"], result["paper_selected"], ["date", "code", "rank", "paper_weight", "paper_only_selected", "selection_status", "strategy", "reason"])
    _write_csv(paths["realized_returns"], result["realized_returns"], ["date", "split", "paper_nav", "realized_return", "policy_reward", "current_drawdown", "evidence_status", "numeric_error", "source"])
    _write_csv(paths["drift"], result["drift"], ["metric", "value", "reference", "status", "action"])
    _write_csv(paths["drawdown"], result["drawdown"], ["date", "split", "paper_nav", "paper_forward_drawdown", "computed_drawdown", "evidence_status", "numeric_error", "source"])
    _write_jsonl(paths["decision_log"], result["decision_log"])
    return {"run_id": rid, "artifact_dir": str(out_dir), **{f"{key}_path": str(path) for key, path in paths.items()}}


def run_and_write_daily_registry(*, run_id: str | None = None, overwrite: bool = False, **kwargs: Any) -> dict[str, Any]:
    result = build_daily_registry(**kwargs)
    receipt = write_registry_artifacts(result, run_id=run_id, overwrite=overwrite)
    return {"result": result, "receipt": receipt}


__all__ = [
    "DEFAULT_DAILY_REGISTRY_ROOT",
    "REGISTRY_SCHEMA_VERSION",
    "RESEARCH_GUARDRAIL",
    "build_daily_registry",
    "run_and_write_daily_registry",
    "write_registry_artifacts",
]
