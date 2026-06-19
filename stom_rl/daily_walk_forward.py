"""Daily OHLCV forward-validation gates for research-only model/RL evidence.

D5 consumes frozen D3 prediction artifacts and D4 constrained-RL artifacts.  It
creates forward-only evaluation folds and gate evidence; it does not retune on
out-of-sample data, place orders, claim profit, or unlock live/broker readiness.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .daily_ohlcv_db import PRICE_BASIS, PRICE_BASIS_EVIDENCE, REPO_ROOT
from .daily_prediction import DEFAULT_PREDICTION_ROOT, ROUND_TRIP_COST_BP, evaluate_strategy
from .daily_rl_train import DEFAULT_PORTFOLIO_ROOT

DEFAULT_WALK_FORWARD_ROOT = REPO_ROOT / "webui" / "rl_runs" / "daily_ohlcv_walk_forward"
WALK_FORWARD_SCHEMA_VERSION = 1
SAFE_RUN_RE = re.compile(r"^[0-9A-Za-z_.-]+$")
PREREGISTERED_D5_STRATEGY = "equal_weight_topk_momentum"
MAX_ALLOWED_FOLD_DRAWDOWN = -0.20
MAX_ALLOWED_MEAN_TURNOVER = 1.00
MIN_REQUIRED_PURGE_DAYS = 5
MIN_REQUIRED_EMBARGO_DAYS = 5
REQUIRED_BASELINE_COMPARISON_FIELDS = (
    "policy_total_net_return",
    "best_d3_total_net_return",
    "delta_vs_best_d3_total_net_return",
    "cost_round_trip_bp",
)
REQUIRED_D4_BASELINES = (
    "no_trade_cash",
    "shuffle_control",
    PREREGISTERED_D5_STRATEGY,
)
REQUIRED_D4_CSV_FIELDS = {
    "state_observations": {"split", "date", "future_label_exposed"},
    "reward_breakdown": {"split", "date", "reward", "turnover", "exposure", "invalid_action"},
    "invalid_actions": {"split", "date", "invalid_action"},
    "policy_baseline_comparison": {"baseline_strategy", "baseline_status", "cost_round_trip_bp"},
    "policy_nav": {"split", "date", "policy_nav"},
    "reward_action_ablations": {"split", "ablation_family", "ablation", "cost_round_trip_bp"},
}
D4_CSV_SCHEMA_ISSUES = {
    "state_observations": "D4_STATE_OBSERVATIONS_SCHEMA_INVALID",
    "reward_breakdown": "D4_REWARD_BREAKDOWN_SCHEMA_INVALID",
    "invalid_actions": "D4_INVALID_ACTIONS_SCHEMA_INVALID",
    "policy_baseline_comparison": "D4_POLICY_BASELINE_COMPARISON_SCHEMA_INVALID",
    "policy_nav": "D4_POLICY_NAV_SCHEMA_INVALID",
    "reward_action_ablations": "D4_REWARD_ACTION_ABLATIONS_SCHEMA_INVALID",
}
SCORE_BY_STRATEGY = {
    "equal_weight_topk_momentum": "score_equal_weight_topk_momentum",
    "vol_adjusted_momentum": "score_vol_adjusted_momentum",
    "mean_reversion": "score_mean_reversion",
    "supervised_linear_ranker": "score_supervised_linear_ranker",
    "supervised_direction_classifier": "score_supervised_direction_classifier",
}
RESEARCH_GUARDRAIL = (
    "Research-only D5 daily walk-forward/gate evidence; no profit guarantee, "
    "no live/broker/orders, no deployable model readiness claim."
)
D4_STATE_MANIFEST_GATE = "D4_OBSERVATION_STATE_MANIFEST"
REQUIRED_D4_STATE_ARTIFACTS = {
    "observation_manifest": "observation_manifest.json",
    "state_observations": "state_observations.csv",
    "reward_breakdown": "reward_breakdown.csv",
    "invalid_actions": "invalid_actions.csv",
    "policy_baseline_comparison": "policy_baseline_comparison.csv",
    "policy_nav": "policy_nav.csv",
    "reward_action_ablations": "reward_action_ablations.csv",
    "reward_action_ablation_summary": "reward_action_ablation_summary.json",
    "source_hashes": "source_hashes.json",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_run_id(run_id: str) -> str:
    rid = str(run_id or "").strip()
    if not SAFE_RUN_RE.match(rid) or rid in {".", ".."} or "/" in rid or "\\" in rid:
        raise ValueError("run_id contains unsafe characters")
    return rid


def _latest_run_dir(root: Path, required_file: str) -> Path:
    candidates = sorted(root.glob(f"*/{required_file}"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No {required_file} under {root}")
    return candidates[0].parent


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_json_contract(path: Path, *, issue: str, issues: list[str]) -> dict[str, Any]:
    try:
        payload = _read_json(path)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        issues.append(issue)
        return {}
    if not isinstance(payload, dict):
        issues.append(issue)
        return {}
    return payload


def _read_csv_contract(path: Path, *, issue: str, issues: list[str]) -> list[dict[str, Any]]:
    try:
        return _read_csv(path)
    except (csv.Error, OSError, UnicodeDecodeError):
        issues.append(issue)
        return []

def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_hashes(paths: dict[str, Path]) -> dict[str, str]:
    return {key: _file_sha256(path) for key, path in paths.items() if path.exists()}


def _load_d4_state_contract(portfolio_dir: Path, portfolio_manifest: dict[str, Any]) -> dict[str, Any]:
    artifact_paths = {key: portfolio_dir / filename for key, filename in REQUIRED_D4_STATE_ARTIFACTS.items()}
    missing_artifacts = [filename for filename in REQUIRED_D4_STATE_ARTIFACTS.values() if not (portfolio_dir / filename).exists()]
    issues = [f"D4_REQUIRED_ARTIFACT_MISSING_{name}" for name in missing_artifacts]
    observation_manifest = (
        _read_json_contract(
            artifact_paths["observation_manifest"],
            issue="D4_OBSERVATION_MANIFEST_JSON_INVALID",
            issues=issues,
        )
        if artifact_paths["observation_manifest"].exists()
        else dict(portfolio_manifest.get("observation_manifest") or {})
    )
    validation = dict(portfolio_manifest.get("observation_manifest_validation") or {})
    state_rows = (
        _read_csv_contract(
            artifact_paths["state_observations"],
            issue="D4_STATE_OBSERVATIONS_CSV_INVALID",
            issues=issues,
        )
        if artifact_paths["state_observations"].exists()
        else []
    )
    invalid_rows = (
        _read_csv_contract(artifact_paths["invalid_actions"], issue="D4_INVALID_ACTIONS_CSV_INVALID", issues=issues)
        if artifact_paths["invalid_actions"].exists()
        else []
    )
    reward_rows = (
        _read_csv_contract(artifact_paths["reward_breakdown"], issue="D4_REWARD_BREAKDOWN_CSV_INVALID", issues=issues)
        if artifact_paths["reward_breakdown"].exists()
        else []
    )
    baseline_rows = (
        _read_csv_contract(
            artifact_paths["policy_baseline_comparison"],
            issue="D4_POLICY_BASELINE_COMPARISON_CSV_INVALID",
            issues=issues,
        )
        if artifact_paths["policy_baseline_comparison"].exists()
        else []
    )
    nav_rows = (
        _read_csv_contract(artifact_paths["policy_nav"], issue="D4_POLICY_NAV_CSV_INVALID", issues=issues)
        if artifact_paths["policy_nav"].exists()
        else []
    )
    ablation_rows = (
        _read_csv_contract(
            artifact_paths["reward_action_ablations"],
            issue="D4_REWARD_ACTION_ABLATIONS_CSV_INVALID",
            issues=issues,
        )
        if artifact_paths["reward_action_ablations"].exists()
        else []
    )
    ablation_summary = (
        _read_json_contract(
            artifact_paths["reward_action_ablation_summary"],
            issue="D4_REWARD_ACTION_ABLATION_SUMMARY_JSON_INVALID",
            issues=issues,
        )
        if artifact_paths["reward_action_ablation_summary"].exists()
        else {}
    )
    source_hash_payload = (
        _read_json_contract(artifact_paths["source_hashes"], issue="D4_SOURCE_HASHES_JSON_INVALID", issues=issues)
        if artifact_paths["source_hashes"].exists()
        else {}
    )
    source_hashes = (
        source_hash_payload.get("source_hashes")
        if isinstance(source_hash_payload.get("source_hashes"), dict)
        else {}
    )

    csv_rows_by_artifact = {
        "state_observations": state_rows,
        "reward_breakdown": reward_rows,
        "invalid_actions": invalid_rows,
        "policy_baseline_comparison": baseline_rows,
        "policy_nav": nav_rows,
        "reward_action_ablations": ablation_rows,
    }
    for artifact_key, required_fields in REQUIRED_D4_CSV_FIELDS.items():
        rows = csv_rows_by_artifact[artifact_key]
        if artifact_paths[artifact_key].exists() and rows:
            observed_fields = {field for row in rows for field in row.keys()}
            if not required_fields <= observed_fields:
                issues.append(D4_CSV_SCHEMA_ISSUES[artifact_key])

    manifest_required_baselines = (
        observation_manifest.get("frozen_d3_comparison", {}).get("required_baselines")
        if isinstance(observation_manifest.get("frozen_d3_comparison"), dict)
        else None
    )
    if not isinstance(manifest_required_baselines, list) or not manifest_required_baselines:
        issues.append("D4_FROZEN_D3_BASELINE_REQUIREMENTS_MISSING")
        manifest_required_baselines = []
    required_baselines = sorted({*(str(baseline) for baseline in manifest_required_baselines), *REQUIRED_D4_BASELINES})
    loaded_baselines = {
        str(row.get("baseline_strategy") or "")
        for row in baseline_rows
        if str(row.get("baseline_status") or "") == "LOADED"
    }
    missing_baselines = [baseline for baseline in required_baselines if baseline not in loaded_baselines]

    if observation_manifest.get("gate") != D4_STATE_MANIFEST_GATE:
        issues.append("D4_OBSERVATION_STATE_MANIFEST_GATE_INVALID")
    if validation.get("status") != "PASS":
        issues.append("D4_OBSERVATION_MANIFEST_VALIDATION_NOT_PASS")
    if portfolio_manifest.get("state_contract_status") != "PASS":
        issues.append("D4_STATE_CONTRACT_STATUS_NOT_PASS")
    if observation_manifest.get("reward_action_telemetry_sufficient_for_d4") is not False:
        issues.append("D4_REWARD_ACTION_TELEMETRY_FLAG_NOT_FALSE")
    if not state_rows:
        issues.append(
            "D4_STATE_OBSERVATIONS_EMPTY"
            if artifact_paths["state_observations"].exists()
            else "D4_STATE_OBSERVATIONS_MISSING"
        )
    if not reward_rows:
        issues.append("D4_REWARD_BREAKDOWN_EMPTY")
    if not invalid_rows:
        issues.append("D4_INVALID_ACTIONS_EMPTY")
    if not baseline_rows:
        issues.append("D4_POLICY_BASELINE_COMPARISON_EMPTY")
    if not nav_rows:
        issues.append("D4_POLICY_NAV_EMPTY")
    if missing_baselines:
        issues.extend(f"D4_FROZEN_D3_BASELINE_MISSING_{baseline}" for baseline in missing_baselines)
    if artifact_paths["reward_action_ablations"].exists() and not ablation_rows:
        issues.append("D4_REWARD_ACTION_ABLATIONS_EMPTY")
    if artifact_paths["reward_action_ablation_summary"].exists() and not ablation_summary:
        issues.append("D4_REWARD_ACTION_ABLATION_SUMMARY_EMPTY")
    if artifact_paths["source_hashes"].exists() and not source_hashes:
        issues.append("D4_SOURCE_HASHES_MISSING")

    return {
        "schema_version": WALK_FORWARD_SCHEMA_VERSION,
        "required_gate": D4_STATE_MANIFEST_GATE,
        "status": "PASS" if not issues else "BLOCKED",
        "gate": observation_manifest.get("gate"),
        "observation_manifest_status": observation_manifest.get("status"),
        "observation_manifest_validation_status": validation.get("status"),
        "state_contract_status": portfolio_manifest.get("state_contract_status"),
        "reward_action_telemetry_sufficient_for_d4": observation_manifest.get(
            "reward_action_telemetry_sufficient_for_d4"
        ),
        "observation_fields": validation.get("observation_fields") or [],
        "missing_artifacts": missing_artifacts,
        "missing_frozen_d3_baselines": missing_baselines,
        "source_hash_count": len(source_hashes),
        "reward_action_ablation_summary_status": "PASS" if ablation_summary else "MISSING",
        "row_counts": {
            "state_observations": len(state_rows),
            "invalid_actions": len(invalid_rows),
            "reward_breakdown": len(reward_rows),
            "policy_baseline_comparison": len(baseline_rows),
            "policy_nav": len(nav_rows),
            "reward_action_ablations": len(ablation_rows),
            "source_hashes": len(source_hashes),
        },
        "artifacts": {key: str(path) for key, path in artifact_paths.items()},
        "issues": issues,
        "guardrail": "D5 consumes D4 state-aware artifacts only as research evidence; no live/broker/orders or profit claim.",
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fallback_fields: list[str]) -> None:
    if rows:
        field_set = {key for row in rows for key in row.keys()}
        fields = [field for field in fallback_fields if field in field_set]
        fields.extend(sorted(field_set - set(fields)))
    else:
        fields = fallback_fields
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _resolve_run(run_dir: Path | str | None, root: Path, required_file: str) -> Path:
    if run_dir is not None:
        resolved = Path(run_dir).resolve()
        resolved.relative_to(root.resolve())
        if not (resolved / required_file).exists():
            raise FileNotFoundError(resolved / required_file)
        return resolved
    return _latest_run_dir(root, required_file)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _finite_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _baseline_comparison_issues(baseline_comparison: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for field in REQUIRED_BASELINE_COMPARISON_FIELDS:
        if _finite_float(baseline_comparison.get(field)) is None:
            issues.append(f"D5_BASELINE_COMPARISON_FIELD_INVALID_{field}")
    cost_bp = _finite_float(baseline_comparison.get("cost_round_trip_bp"))
    if cost_bp is not None and cost_bp != float(ROUND_TRIP_COST_BP):
        issues.append("D5_BASELINE_COMPARISON_COST_MISMATCH")
    return issues


def _mean(values: Iterable[float]) -> float:
    clean = [float(value) for value in values]
    return sum(clean) / len(clean) if clean else 0.0


def _max_drawdown(equity_values: Iterable[float]) -> float:
    peak = 1.0
    max_dd = 0.0
    for value in equity_values:
        peak = max(peak, value)
        if peak:
            max_dd = min(max_dd, value / peak - 1.0)
    return max_dd


def _product_return(returns: Iterable[float]) -> tuple[float, list[float]]:
    equity = 1.0
    curve: list[float] = []
    for value in returns:
        equity *= 1.0 + float(value)
        curve.append(equity)
    return equity - 1.0, curve


def _selected_d5_strategy(_baseline_metrics: list[dict[str, Any]]) -> str:
    return PREREGISTERED_D5_STRATEGY


def _dates_from_rows(rows: Iterable[dict[str, Any]], *, splits: set[str] | None = None) -> list[str]:
    selected = []
    for row in rows:
        if splits is not None and str(row.get("split")) not in splits:
            continue
        date = row.get("date")
        if date is not None:
            selected.append(str(date))
    return sorted(set(selected))


def assign_forward_folds(
    all_dates: list[str],
    eval_dates: list[str],
    *,
    n_folds: int = 5,
    purge_days: int = 5,
    embargo_days: int = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    fold_errors: list[str] = []
    try:
        fold_count = int(n_folds)
    except (TypeError, ValueError):
        fold_count = 0
        fold_errors.append("N_FOLDS_INVALID")
    try:
        purge_count = int(purge_days)
    except (TypeError, ValueError):
        purge_count = 0
        fold_errors.append("PURGE_DAYS_INVALID")
    try:
        embargo_count = int(embargo_days)
    except (TypeError, ValueError):
        embargo_count = 0
        fold_errors.append("EMBARGO_DAYS_INVALID")
    if fold_count < 5:
        fold_errors.append("N_FOLDS_BELOW_5")
    if purge_count < MIN_REQUIRED_PURGE_DAYS:
        fold_errors.append("PURGE_DAYS_BELOW_REQUIRED_MIN")
    if embargo_count < MIN_REQUIRED_EMBARGO_DAYS:
        fold_errors.append("EMBARGO_DAYS_BELOW_REQUIRED_MIN")
    if fold_errors:
        return [], [], fold_errors
    ordered_all = sorted(set(all_dates))
    ordered_eval = sorted(set(eval_dates))
    if len(ordered_eval) < fold_count:
        return [], [], ["INSUFFICIENT_EVAL_DATES_FOR_5_FOLDS"]

    fold_rows: list[dict[str, Any]] = []
    assignment_rows: list[dict[str, Any]] = []
    fold_size = math.ceil(len(ordered_eval) / fold_count)
    for fold_index in range(fold_count):
        start = fold_index * fold_size
        end = min(len(ordered_eval), (fold_index + 1) * fold_size)
        test_dates = ordered_eval[start:end]
        if not test_dates:
            continue
        test_start = test_dates[0]
        test_end = test_dates[-1]
        all_start_index = ordered_all.index(test_start)
        all_end_index = ordered_all.index(test_end)
        purge_window = ordered_all[max(0, all_start_index - purge_count) : all_start_index]
        train_dates = ordered_all[: max(0, all_start_index - purge_count)]
        embargo_window = ordered_all[all_end_index + 1 : all_end_index + 1 + embargo_count]
        fold_id = f"F{fold_index + 1:02d}"
        fold_rows.append(
            {
                "fold_id": fold_id,
                "fold_index": fold_index + 1,
                "train_start_date": train_dates[0] if train_dates else "",
                "train_end_date": train_dates[-1] if train_dates else "",
                "test_start_date": test_start,
                "test_end_date": test_end,
                "test_days": len(test_dates),
                "purge_days": purge_count,
                "embargo_days": embargo_count,
                "purge_start_date": purge_window[0] if purge_window else "",
                "purge_end_date": purge_window[-1] if purge_window else "",
                "embargo_start_date": embargo_window[0] if embargo_window else "",
                "embargo_end_date": embargo_window[-1] if embargo_window else "",
                "forward_only": (not train_dates) or train_dates[-1] < test_start,
                "retuned_on_oos": False,
            }
        )
        for date in test_dates:
            assignment_rows.append({"fold_id": fold_id, "date": date, "role": "test"})
        for date in purge_window:
            assignment_rows.append({"fold_id": fold_id, "date": date, "role": "purge"})
        for date in embargo_window:
            assignment_rows.append({"fold_id": fold_id, "date": date, "role": "embargo"})
    if len(fold_rows) < 5:
        return fold_rows, assignment_rows, ["N_FOLDS_BELOW_5_AFTER_ASSIGNMENT"]
    return fold_rows, assignment_rows, []


def _rows_for_dates(rows: list[dict[str, Any]], dates: set[str]) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("date")) in dates]


def _shuffle_scores(rows: list[dict[str, Any]], *, score_column: str, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("date"))].append(row)
    shuffled_rows: list[dict[str, Any]] = []
    for date, date_rows in sorted(grouped.items()):
        values = [row.get(score_column) for row in date_rows]
        rng.shuffle(values)
        for row, value in zip(date_rows, values):
            copied = dict(row)
            copied[score_column] = value
            shuffled_rows.append(copied)
    return shuffled_rows


def _evaluate_prediction_fold(
    rows: list[dict[str, Any]],
    *,
    fold_id: str,
    strategy: str,
    top_k: int,
    cost_bp: float,
    control: str = "actual",
) -> dict[str, Any]:
    _positions, metrics, _daily, _turnover = evaluate_strategy(
        rows,
        strategy=strategy,
        top_k=top_k,
        cost_rate=float(cost_bp) / 10_000.0,
        splits=("val", "test"),
    )
    return {
        "fold_id": fold_id,
        "strategy": strategy,
        "control": control,
        "cost_bp": float(cost_bp),
        "trade_days": metrics.get("trade_days", 0),
        "positions": metrics.get("positions", 0),
        "total_net_return": metrics.get("total_net_return", 0.0),
        "mean_daily_net_return": metrics.get("mean_daily_net_return", 0.0),
        "hit_rate": metrics.get("hit_rate", 0.0),
        "max_drawdown": metrics.get("max_drawdown", 0.0),
        "mean_turnover": metrics.get("mean_turnover", 0.0),
    }


def _evaluate_rl_fold(rows: list[dict[str, Any]], *, fold_id: str) -> dict[str, Any]:
    rewards = [_safe_float(row.get("reward")) for row in rows]
    total_return, equity_curve = _product_return(rewards)
    return {
        "fold_id": fold_id,
        "strategy": "tabular_q_constrained_daily_portfolio_rl",
        "trade_days": len(rows),
        "total_net_return": total_return,
        "mean_daily_reward": _mean(rewards),
        "max_drawdown": _max_drawdown(equity_curve),
        "mean_turnover": _mean(_safe_float(row.get("turnover")) for row in rows),
        "mean_exposure": _mean(_safe_float(row.get("exposure")) for row in rows),
        "invalid_action_rate": _mean(1.0 if str(row.get("invalid_action", "False")) == "True" else 0.0 for row in rows),
    }


def _fold_summary(rows: list[dict[str, Any]], *, strategy: str) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if row.get("strategy") == strategy
        and row.get("control") == "actual"
        and float(row.get("cost_bp") or 0.0) == ROUND_TRIP_COST_BP
    ]
    values = [_safe_float(row.get("total_net_return")) for row in selected]
    drawdowns = [_safe_float(row.get("max_drawdown")) for row in selected]
    turnovers = [_safe_float(row.get("mean_turnover")) for row in selected]
    deltas_vs_no_trade = [_safe_float(row.get("delta_vs_no_trade_total_net_return")) for row in selected]
    deltas_vs_shuffle = [_safe_float(row.get("delta_vs_shuffled_total_net_return")) for row in selected]
    return {
        "strategy": strategy,
        "fold_count": len(selected),
        "positive_folds": sum(1 for value in values if value > 0),
        "negative_folds": sum(1 for value in values if value <= 0),
        "folds_beating_no_trade": sum(1 for value in deltas_vs_no_trade if value > 0),
        "folds_beating_shuffle": sum(1 for value in deltas_vs_shuffle if value > 0),
        "mean_fold_total_net_return": _mean(values),
        "worst_fold_total_net_return": min(values) if values else 0.0,
        "best_fold_total_net_return": max(values) if values else 0.0,
        "worst_fold_max_drawdown": min(drawdowns) if drawdowns else 0.0,
        "mean_fold_turnover": _mean(turnovers),
    }

def _attach_fold_deltas(rows: list[dict[str, Any]], *, strategy: str) -> None:
    no_trade_by_fold = {
        str(row.get("fold_id")): _safe_float(row.get("total_net_return"))
        for row in rows
        if row.get("strategy") == "no_trade_cash" and row.get("control") == "actual"
    }
    shuffled_by_fold = {
        str(row.get("fold_id")): _safe_float(row.get("total_net_return"))
        for row in rows
        if row.get("strategy") == strategy and row.get("control") == "shuffled_score"
    }
    for row in rows:
        fold_id = str(row.get("fold_id"))
        total_return = _safe_float(row.get("total_net_return"))
        row["delta_vs_no_trade_total_net_return"] = total_return - no_trade_by_fold.get(fold_id, 0.0)
        if row.get("strategy") == strategy and row.get("control") == "actual":
            row["delta_vs_shuffled_total_net_return"] = total_return - shuffled_by_fold.get(fold_id, 0.0)
        else:
            row["delta_vs_shuffled_total_net_return"] = ""



def run_daily_walk_forward(
    *,
    prediction_run_dir: Path | str | None = None,
    portfolio_run_dir: Path | str | None = None,
    n_folds: int = 5,
    purge_days: int = 5,
    embargo_days: int = 5,
    top_k: int = 20,
    seed: int = 17,
) -> dict[str, Any]:
    prediction_dir = _resolve_run(prediction_run_dir, DEFAULT_PREDICTION_ROOT, "prediction_manifest.json")
    portfolio_dir = _resolve_run(portfolio_run_dir, DEFAULT_PORTFOLIO_ROOT, "rl_manifest.json")
    prediction_manifest = _read_json(prediction_dir / "prediction_manifest.json")
    prediction_verdict = _read_json(prediction_dir / "verdict.json")
    baseline_metrics = _read_json(prediction_dir / "baseline_metrics.json").get("metrics", [])
    prediction_rows = _read_csv(prediction_dir / "predictions.csv")
    portfolio_manifest = _read_json(portfolio_dir / "rl_manifest.json")
    portfolio_verdict = _read_json(portfolio_dir / "verdict.json")
    prediction_artifact_hashes = _artifact_hashes(
        {
            "prediction_manifest": prediction_dir / "prediction_manifest.json",
            "predictions": prediction_dir / "predictions.csv",
            "baseline_metrics": prediction_dir / "baseline_metrics.json",
            "verdict": prediction_dir / "verdict.json",
        }
    )
    portfolio_artifact_hashes = _artifact_hashes(
        {
            "rl_manifest": portfolio_dir / "rl_manifest.json",
            "verdict": portfolio_dir / "verdict.json",
            "baseline_comparison": portfolio_dir / "baseline_comparison.json",
            **{key: portfolio_dir / filename for key, filename in REQUIRED_D4_STATE_ARTIFACTS.items()},
        }
    )
    d4_state_contract = _load_d4_state_contract(portfolio_dir, portfolio_manifest)
    d5_input_artifact_issues: list[str] = []
    reward_breakdown_path = portfolio_dir / "reward_breakdown.csv"
    rl_reward_rows = (
        [
            row
            for row in _read_csv_contract(
                reward_breakdown_path,
                issue="D4_REWARD_BREAKDOWN_CSV_INVALID",
                issues=d5_input_artifact_issues,
            )
            if row.get("split") == "val+test"
        ]
        if reward_breakdown_path.exists()
        else []
    )
    baseline_comparison_path = portfolio_dir / "baseline_comparison.json"
    baseline_comparison: dict[str, Any] = {}
    baseline_comparison_loaded = False
    if baseline_comparison_path.exists():
        try:
            baseline_payload = _read_json(baseline_comparison_path)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            d5_input_artifact_issues.append("D5_BASELINE_COMPARISON_JSON_INVALID")
        else:
            if isinstance(baseline_payload, dict):
                baseline_comparison = baseline_payload
                baseline_comparison_loaded = True
            else:
                d5_input_artifact_issues.append("D5_BASELINE_COMPARISON_JSON_INVALID")
    else:
        d5_input_artifact_issues.append("D5_BASELINE_COMPARISON_MISSING")
    if baseline_comparison_loaded:
        d5_input_artifact_issues.extend(_baseline_comparison_issues(baseline_comparison))

    selected_strategy = _selected_d5_strategy(baseline_metrics)
    selected_score_column = SCORE_BY_STRATEGY.get(selected_strategy, "score_equal_weight_topk_momentum")
    all_dates = _dates_from_rows(prediction_rows)
    eval_dates = _dates_from_rows(prediction_rows, splits={"val", "test"})
    fold_rows, assignment_rows, fold_errors = assign_forward_folds(
        all_dates,
        eval_dates,
        n_folds=n_folds,
        purge_days=purge_days,
        embargo_days=embargo_days,
    )

    metric_rows: list[dict[str, Any]] = []
    shuffle_rows: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    rl_rows: list[dict[str, Any]] = []
    if not fold_errors:
        for fold in fold_rows:
            fold_dates = {row["date"] for row in assignment_rows if row["fold_id"] == fold["fold_id"] and row["role"] == "test"}
            fold_prediction_rows = _rows_for_dates(prediction_rows, fold_dates)
            metric_rows.append(
                _evaluate_prediction_fold(
                    fold_prediction_rows,
                    fold_id=fold["fold_id"],
                    strategy=selected_strategy,
                    top_k=top_k,
                    cost_bp=ROUND_TRIP_COST_BP,
                    control="actual",
                )
            )
            metric_rows.append(
                _evaluate_prediction_fold(
                    fold_prediction_rows,
                    fold_id=fold["fold_id"],
                    strategy="no_trade_cash",
                    top_k=top_k,
                    cost_bp=ROUND_TRIP_COST_BP,
                    control="actual",
                )
            )
            shuffled = _shuffle_scores(fold_prediction_rows, score_column=selected_score_column, seed=seed + int(fold["fold_index"]))
            shuffle_metric = _evaluate_prediction_fold(
                shuffled,
                fold_id=fold["fold_id"],
                strategy=selected_strategy,
                top_k=top_k,
                cost_bp=ROUND_TRIP_COST_BP,
                control="shuffled_score",
            )
            shuffle_rows.append(shuffle_metric)
            metric_rows.append(shuffle_metric)
            for cost_bp in (0.0, float(ROUND_TRIP_COST_BP), float(ROUND_TRIP_COST_BP * 2)):
                cost_rows.append(
                    _evaluate_prediction_fold(
                        fold_prediction_rows,
                        fold_id=fold["fold_id"],
                        strategy=selected_strategy,
                        top_k=top_k,
                        cost_bp=cost_bp,
                        control="cost_sensitivity",
                    )
                )
            fold_rl_rows = _rows_for_dates(rl_reward_rows, fold_dates)
            rl_rows.append(_evaluate_rl_fold(fold_rl_rows, fold_id=fold["fold_id"]))
        _attach_fold_deltas(metric_rows, strategy=selected_strategy)

    selected_summary = _fold_summary(metric_rows, strategy=selected_strategy)
    shuffled_total = sum(_safe_float(row.get("total_net_return")) for row in shuffle_rows)
    selected_total = sum(
        _safe_float(row.get("total_net_return"))
        for row in metric_rows
        if row.get("strategy") == selected_strategy and row.get("control") == "actual" and float(row.get("cost_bp") or 0.0) == ROUND_TRIP_COST_BP
    )
    rl_total = sum(_safe_float(row.get("total_net_return")) for row in rl_rows)
    rl_delta_vs_best_d3 = _safe_float(baseline_comparison.get("delta_vs_best_d3_total_net_return"))
    max_drawdown_limit_exceeded = float(selected_summary.get("worst_fold_max_drawdown") or 0.0) < MAX_ALLOWED_FOLD_DRAWDOWN
    mean_turnover_limit_exceeded = float(selected_summary.get("mean_fold_turnover") or 0.0) > MAX_ALLOWED_MEAN_TURNOVER
    d4_issues = [*d5_input_artifact_issues, *list(d4_state_contract.get("issues") or [])]
    reasons: list[str] = ["RESEARCH_ONLY_NO_PROFIT_LIVE_BROKER_ORDER_CLAIM"]
    status = "NO-GO"
    if fold_errors or d4_issues:
        reasons.extend(fold_errors)
        reasons.extend(d4_issues)
        reasons.append("D5_REQUIRED_EVIDENCE_INCOMPLETE")
    else:
        reasons.append("FORWARD_FOLDS_COMPLETE_NO_OOS_RETUNING")
        reasons.append("D4_OBSERVATION_STATE_MANIFEST_CONSUMED")
        if selected_total <= shuffled_total:
            reasons.append("SHUFFLE_CONTROL_NOT_BEATEN_BY_SELECTED_BASELINE")
        if str(prediction_manifest.get("price_basis") or PRICE_BASIS) == "unknown":
            reasons.append("PRICE_BASIS_UNKNOWN")
        if "WATCH" in str(prediction_manifest.get("universe_review_status") or ""):
            reasons.append("UNIVERSE_WATCH_HEURISTIC")
        if rl_delta_vs_best_d3 <= 0 or rl_total <= selected_total:
            reasons.append("RL_POLICY_UNDERPERFORMS_D3_BASELINE")
        else:
            reasons.append("D5_RESEARCH_ONLY_MODEL_BUILD_LOCK")
        if str(portfolio_verdict.get("status")) == "RESEARCH_ONLY":
            reasons.append("D4_RL_RESEARCH_ONLY_LOCK")
        if max_drawdown_limit_exceeded:
            reasons.append("MAX_DRAWDOWN_LIMIT_EXCEEDED")
        if mean_turnover_limit_exceeded:
            reasons.append("MEAN_TURNOVER_LIMIT_EXCEEDED")
        if not max_drawdown_limit_exceeded and not mean_turnover_limit_exceeded:
            reasons.append("MDD_TURNOVER_LIMITS_CHECKED")
    readiness_status = "D5_NO_GO_RESEARCH_ONLY_GATE"
    gate_verdict = {
        "schema_version": WALK_FORWARD_SCHEMA_VERSION,
        "status": status,
        "readiness_status": readiness_status,
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "no_live_broker_order_readiness": True,
        "selected_strategy": selected_strategy,
        "strategy_selection_policy": "preregistered_equal_weight_topk_momentum_no_oos_metric_selection",
        "n_folds": len(fold_rows),
        "required_min_folds": 5,
        "no_oos_retuning": True,
        "purge_days": _safe_int(purge_days),
        "embargo_days": _safe_int(embargo_days),
        "min_required_purge_days": MIN_REQUIRED_PURGE_DAYS,
        "min_required_embargo_days": MIN_REQUIRED_EMBARGO_DAYS,
        "d4_state_contract_status": d4_state_contract.get("status"),
        "d4_observation_manifest_gate": d4_state_contract.get("gate"),
        "d4_observation_manifest_validation_status": d4_state_contract.get("observation_manifest_validation_status"),
        "d4_state_contract_artifacts_consumed": d4_state_contract.get("status") == "PASS",
        "d4_state_observation_rows": (d4_state_contract.get("row_counts") or {}).get("state_observations", 0),
        "d4_reward_action_ablation_rows": (d4_state_contract.get("row_counts") or {}).get("reward_action_ablations", 0),
        "d4_source_hash_count": (d4_state_contract.get("row_counts") or {}).get("source_hashes", 0),
        "d4_reward_action_telemetry_sufficient_for_d4": d4_state_contract.get(
            "reward_action_telemetry_sufficient_for_d4"
        ),
        "d4_artifact_issues": d4_issues,
        "max_allowed_fold_drawdown": MAX_ALLOWED_FOLD_DRAWDOWN,
        "max_drawdown_limit_exceeded": max_drawdown_limit_exceeded,
        "max_allowed_mean_turnover": MAX_ALLOWED_MEAN_TURNOVER,
        "mean_turnover_limit_exceeded": mean_turnover_limit_exceeded,
        "selected_total_net_return_sum": selected_total,
        "shuffled_total_net_return_sum": shuffled_total,
        "rl_total_net_return_sum": rl_total,
        "rl_delta_vs_best_d3_total_net_return": rl_delta_vs_best_d3,
        "fold_consistency": selected_summary,
        "price_basis": prediction_manifest.get("price_basis") or PRICE_BASIS,
        "price_basis_evidence": prediction_manifest.get("price_basis_evidence") or PRICE_BASIS_EVIDENCE,
        "universe_review_status": prediction_manifest.get("universe_review_status"),
        "cost_sensitivity_bp": [0, ROUND_TRIP_COST_BP, ROUND_TRIP_COST_BP * 2],
        "slippage_assumption": portfolio_manifest.get("slippage_assumption") or "Daily OHLCV has no separate slippage model; use 23bp and D5 sensitivity.",
        "prediction_artifact_hashes": prediction_artifact_hashes,
        "portfolio_artifact_hashes": portfolio_artifact_hashes,
        "reasons": reasons,
    }
    manifest = {
        "schema_version": WALK_FORWARD_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "guardrail": RESEARCH_GUARDRAIL,
        "prediction_run_dir": str(prediction_dir),
        "portfolio_run_dir": str(portfolio_dir),
        "prediction_verdict_status": prediction_verdict.get("status"),
        "portfolio_verdict_status": portfolio_verdict.get("status"),
        "prediction_manifest_sha": prediction_artifact_hashes.get("prediction_manifest"),
        "prediction_artifact_hashes": prediction_artifact_hashes,
        "portfolio_manifest_sha": portfolio_artifact_hashes.get("rl_manifest"),
        "portfolio_artifact_hashes": portfolio_artifact_hashes,
        "required_d4_state_artifacts": dict(REQUIRED_D4_STATE_ARTIFACTS),
        "portfolio_run_id": portfolio_manifest.get("run_id"),
        "d4_state_contract_status": d4_state_contract.get("status"),
        "d4_state_contract": d4_state_contract,
        "selected_strategy": selected_strategy,
        "strategy_selection_policy": "preregistered_equal_weight_topk_momentum_no_oos_metric_selection",
        "top_k": int(top_k),
        "seed": int(seed),
        "n_folds_requested": _safe_int(n_folds),
        "n_folds": len(fold_rows),
        "purge_days": _safe_int(purge_days),
        "embargo_days": _safe_int(embargo_days),
        "min_required_purge_days": MIN_REQUIRED_PURGE_DAYS,
        "min_required_embargo_days": MIN_REQUIRED_EMBARGO_DAYS,
        "cost_assumption_round_trip_bp": ROUND_TRIP_COST_BP,
        "no_oos_retuning": True,
        "price_basis": gate_verdict["price_basis"],
        "universe_review_status": gate_verdict.get("universe_review_status"),
        "no_live_broker_order_readiness": True,
        "go_summary_allowed": False,
        "model_build_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "readiness_status": readiness_status,
        "row_counts": {
            "fold_rows": len(fold_rows),
            "assignment_rows": len(assignment_rows),
            "fold_metric_rows": len(metric_rows),
            "shuffle_control_rows": len(shuffle_rows),
            "cost_sensitivity_rows": len(cost_rows),
            "rl_fold_rows": len(rl_rows),
            "d4_state_observation_rows": (d4_state_contract.get("row_counts") or {}).get("state_observations", 0),
            "d4_invalid_action_rows": (d4_state_contract.get("row_counts") or {}).get("invalid_actions", 0),
            "d4_policy_nav_rows": (d4_state_contract.get("row_counts") or {}).get("policy_nav", 0),
            "d4_reward_action_ablation_rows": (d4_state_contract.get("row_counts") or {}).get("reward_action_ablations", 0),
            "d4_source_hash_count": (d4_state_contract.get("row_counts") or {}).get("source_hashes", 0),
        },
        "verdict": gate_verdict,
    }
    return {
        "manifest": manifest,
        "fold_assignments": assignment_rows,
        "folds": fold_rows,
        "fold_metrics": metric_rows,
        "shuffle_control": shuffle_rows,
        "cost_sensitivity": cost_rows,
        "rl_fold_metrics": rl_rows,
        "d4_state_contract": d4_state_contract,
        "gate_verdict": gate_verdict,
    }


def write_walk_forward_artifacts(
    result: dict[str, Any],
    *,
    run_id: str | None = None,
    artifact_root: Path | str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    root = Path(artifact_root or DEFAULT_WALK_FORWARD_ROOT).resolve()
    default_root = DEFAULT_WALK_FORWARD_ROOT.resolve()
    try:
        root.relative_to(default_root)
    except ValueError:
        if root != default_root:
            raise ValueError("Daily OHLCV walk-forward artifacts must stay under webui/rl_runs/daily_ohlcv_walk_forward")
    rid = _validate_run_id(run_id or f"walk_forward_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    out_dir = (root / rid).resolve()
    out_dir.relative_to(root)
    if out_dir.exists() and any(out_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"Walk-forward artifact run_id already exists: {rid}")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "walk_forward_manifest": out_dir / "walk_forward_manifest.json",
        "fold_assignments": out_dir / "fold_assignments.csv",
        "folds": out_dir / "folds.csv",
        "fold_metrics": out_dir / "fold_metrics.csv",
        "shuffle_control": out_dir / "shuffle_control.csv",
        "cost_sensitivity": out_dir / "cost_sensitivity.csv",
        "rl_fold_metrics": out_dir / "rl_fold_metrics.csv",
        "gate_verdict": out_dir / "gate_verdict.json",
        "d4_state_contract": out_dir / "d4_state_contract.json",
    }
    manifest = {**result["manifest"], "run_id": rid, "artifact_dir": str(out_dir), "artifacts": {key: str(path) for key, path in paths.items()}}
    _write_json(paths["walk_forward_manifest"], manifest)
    _write_json(paths["gate_verdict"], result["gate_verdict"])
    _write_json(paths["d4_state_contract"], result["d4_state_contract"])
    _write_csv(paths["fold_assignments"], result["fold_assignments"], ["fold_id", "date", "role"])
    _write_csv(paths["folds"], result["folds"], ["fold_id", "fold_index", "test_start_date", "test_end_date", "forward_only", "retuned_on_oos"])
    _write_csv(paths["fold_metrics"], result["fold_metrics"], ["fold_id", "strategy", "control", "cost_bp", "total_net_return", "delta_vs_no_trade_total_net_return", "delta_vs_shuffled_total_net_return", "max_drawdown", "mean_turnover"])
    _write_csv(paths["shuffle_control"], result["shuffle_control"], ["fold_id", "strategy", "control", "cost_bp", "total_net_return", "max_drawdown", "mean_turnover"])
    _write_csv(paths["cost_sensitivity"], result["cost_sensitivity"], ["fold_id", "strategy", "control", "cost_bp", "total_net_return", "max_drawdown", "mean_turnover"])
    _write_csv(paths["rl_fold_metrics"], result["rl_fold_metrics"], ["fold_id", "strategy", "trade_days", "total_net_return", "max_drawdown", "mean_turnover", "invalid_action_rate"])
    artifact_hashes = {
        key: _file_sha256(path)
        for key, path in paths.items()
        if key != "walk_forward_manifest"
    }
    manifest["artifact_hashes"] = artifact_hashes
    _write_json(paths["walk_forward_manifest"], manifest)
    manifest_sha = _file_sha256(paths["walk_forward_manifest"])
    return {
        "run_id": rid,
        "artifact_dir": str(out_dir),
        "walk_forward_manifest_sha256": manifest_sha,
        "artifact_hashes": {**artifact_hashes, "walk_forward_manifest": manifest_sha},
        **{f"{key}_path": str(path) for key, path in paths.items()},
    }


def run_and_write_daily_walk_forward(
    *,
    run_id: str | None = None,
    artifact_root: Path | str | None = None,
    overwrite: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    result = run_daily_walk_forward(**kwargs)
    written = write_walk_forward_artifacts(result, run_id=run_id, artifact_root=artifact_root, overwrite=overwrite)
    return {"result": result, "written": written}


__all__ = [
    "DEFAULT_WALK_FORWARD_ROOT",
    "WALK_FORWARD_SCHEMA_VERSION",
    "assign_forward_folds",
    "PREREGISTERED_D5_STRATEGY",
    "run_and_write_daily_walk_forward",
    "run_daily_walk_forward",
    "write_walk_forward_artifacts",
]
