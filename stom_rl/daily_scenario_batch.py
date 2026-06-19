"""Batch runner for research-only Daily OHLCV scenario/model experiments.

The dashboard API remains read-only. This module is the explicit CLI path for
running multiple pre-registered scenario configurations through the existing
D2 -> D3 -> D4 -> D5 pipeline and writing comparison artifacts under
``webui/rl_runs``.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .daily_ohlcv_db import REPO_ROOT
from .daily_scenario_runner import RESEARCH_GUARDRAIL, _validate_run_id, run_daily_model_scenario

DEFAULT_SCENARIO_BATCH_ROOT = REPO_ROOT / "webui" / "rl_runs" / "daily_ohlcv_scenario_batches"
RUNNER_DEFAULTS: dict[str, Any] = {
    "max_symbols": None,
    "max_rows_per_symbol": None,
    "quality_table_limit": 0,
    "horizon_days": 1,
    "train_fraction": 0.6,
    "val_fraction": 0.2,
    "purge_days": 5,
    "embargo_days": 5,
    "candidate_limit": 20,
    "max_positions": 5,
    "episodes": 8,
    "rl_seed": 7,
    "n_folds": 5,
    "top_k": 20,
    "wf_seed": 17,
    "observation_mode": "v1",
    "action_prior_mode": "none",
    "action_prior_strength": 0.0,
    "action_filter_mode": "none",
}
SCENARIO_PARAM_KEYS = set(RUNNER_DEFAULTS)
MIN_REQUIRED_FOLDS = 5
MIN_REQUIRED_PURGE_DAYS = 5
MIN_REQUIRED_EMBARGO_DAYS = 5


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _scenario_batch_dir(batch_id: str, *, root: Path | str | None = None, overwrite: bool = False) -> Path:
    base = Path(root or DEFAULT_SCENARIO_BATCH_ROOT).resolve()
    default_root = DEFAULT_SCENARIO_BATCH_ROOT.resolve()
    try:
        base.relative_to(default_root)
    except ValueError:
        if base != default_root:
            raise ValueError("Batch artifacts must stay under webui/rl_runs/daily_ohlcv_scenario_batches")
    bid = _validate_run_id(batch_id)
    out_dir = (base / bid).resolve()
    try:
        out_dir.relative_to(base)
    except ValueError as exc:
        raise ValueError("batch_id escapes daily scenario batch artifact root") from exc
    if out_dir.exists() and any(out_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"Scenario batch artifact batch_id already exists: {bid}")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def load_batch_plan(path: Path | str) -> dict[str, Any]:
    plan_path = Path(path)
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Scenario batch plan must be a JSON object")
    return payload


def default_batch_plan(*, batch_id: str = "scenario_batch_smoke_001") -> dict[str, Any]:
    """Return a small valid plan users can save and edit before running."""

    return {
        "batch_id": batch_id,
        "description": "Research-only Daily OHLCV scenario smoke matrix; no live/broker/orders.",
        "defaults": {
            "max_symbols": 8,
            "max_rows_per_symbol": 120,
            "quality_table_limit": 0,
            "episodes": 3,
            "candidate_limit": 10,
            "max_positions": 3,
            "n_folds": 5,
            "top_k": 10,
            "purge_days": 5,
            "embargo_days": 5,
        },
        "scenarios": [
            {
                "scenario_id": "baseline_seed7_top10",
                "hypothesis": "Current-evidence baseline using top-k momentum controls.",
                "overrides": {"rl_seed": 7, "wf_seed": 17, "top_k": 10},
            },
            {
                "scenario_id": "seed11_top10",
                "hypothesis": "Seed robustness check without changing OOS gate rules.",
                "overrides": {"rl_seed": 11, "wf_seed": 31, "top_k": 10},
            },
            {
                "scenario_id": "top5_concentrated",
                "hypothesis": "Concentration stress test with fewer selected names.",
                "overrides": {"rl_seed": 7, "wf_seed": 17, "top_k": 5, "max_positions": 3},
            },
        ],
    }


def _merge_config(defaults: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    unknown_default_keys = set(defaults) - SCENARIO_PARAM_KEYS
    if unknown_default_keys:
        raise ValueError(f"Unknown scenario default keys: {sorted(unknown_default_keys)}")

    overrides = scenario.get("overrides", {})
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise ValueError("scenario.overrides must be an object")

    inline_overrides = {key: value for key, value in scenario.items() if key in SCENARIO_PARAM_KEYS}
    unknown_override_keys = (set(overrides) | set(inline_overrides)) - SCENARIO_PARAM_KEYS
    if unknown_override_keys:
        raise ValueError(f"Unknown scenario override keys: {sorted(unknown_override_keys)}")

    config = dict(RUNNER_DEFAULTS)
    config.update(defaults)
    config.update(overrides)
    config.update(inline_overrides)
    _validate_research_gate_config(config)
    return config


def _validate_research_gate_config(config: dict[str, Any]) -> None:
    if int(config.get("n_folds") or 0) < MIN_REQUIRED_FOLDS:
        raise ValueError("n_folds must be >= 5 for scenario batch runs")
    if int(config.get("purge_days") or 0) < MIN_REQUIRED_PURGE_DAYS:
        raise ValueError("purge_days must be >= 5 for scenario batch runs")
    if int(config.get("embargo_days") or 0) < MIN_REQUIRED_EMBARGO_DAYS:
        raise ValueError("embargo_days must be >= 5 for scenario batch runs")


def _scenario_id(scenario: dict[str, Any], index: int) -> str:
    raw = scenario.get("scenario_id") or scenario.get("name") or f"scenario_{index:02d}"
    return _validate_run_id(str(raw))


def _comparison_row_from_manifest(*, scenario_id: str, run_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    gate = manifest.get("gate_verdict_summary") or {}
    return {
        "scenario_id": scenario_id,
        "run_id": run_id,
        "status": manifest.get("status", "NO-GO"),
        "readiness_status": manifest.get("readiness_status", "D5_NO_GO_RESEARCH_ONLY_GATE"),
        "selected_strategy": gate.get("selected_strategy"),
        "n_folds": gate.get("n_folds"),
        "purge_days": gate.get("purge_days"),
        "embargo_days": gate.get("embargo_days"),
        "cost_sensitivity_bp": gate.get("cost_sensitivity_bp"),
        "blocking_reasons": gate.get("reasons", []),
        "artifact_paths": manifest.get("artifact_paths", {}),
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
    }


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    return counts


def run_daily_scenario_batch(
    *,
    plan: dict[str, Any] | None = None,
    plan_path: Path | str | None = None,
    batch_id: str | None = None,
    overwrite: bool = False,
    stop_on_error: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run or preview a pre-registered batch of Daily OHLCV model scenarios."""

    if plan is None:
        if plan_path is None:
            plan = default_batch_plan(batch_id=batch_id or "scenario_batch_smoke_001")
        else:
            plan = load_batch_plan(plan_path)
    if not isinstance(plan, dict):
        raise ValueError("Scenario batch plan must be an object")

    resolved_batch_id = _validate_run_id(str(batch_id or plan.get("batch_id") or "").strip())
    scenarios = plan.get("scenarios") or []
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("Scenario batch plan requires a non-empty scenarios list")
    defaults = plan.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise ValueError("Scenario batch defaults must be an object")

    out_dir = _scenario_batch_dir(resolved_batch_id, overwrite=overwrite)
    _write_json(out_dir / "scenario_batch_plan.json", plan)

    comparison_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    started_at = _utc_now()

    for index, raw_scenario in enumerate(scenarios, start=1):
        if not isinstance(raw_scenario, dict):
            raise ValueError("Each scenario entry must be an object")
        scenario_id = _scenario_id(raw_scenario, index)
        run_id = _validate_run_id(f"{resolved_batch_id}__{scenario_id}")
        config = _merge_config(defaults, raw_scenario)
        row_base = {
            "scenario_id": scenario_id,
            "run_id": run_id,
            "hypothesis": raw_scenario.get("hypothesis"),
            "assumption_tags": raw_scenario.get("assumption_tags", []),
            "config": config,
        }
        if dry_run:
            comparison_rows.append(
                {
                    **row_base,
                    "status": "DRY_RUN_NOT_EXECUTED",
                    "readiness_status": "SCENARIO_BATCH_DRY_RUN_ONLY",
                    "cost_sensitivity_bp": [0, 23, 46],
                    "blocking_reasons": ["DRY_RUN_NOT_EXECUTED"],
                    "model_build_allowed": False,
                    "go_summary_allowed": False,
                    "paper_forward_allowed": False,
                    "live_broker_order_allowed": False,
                }
            )
            continue
        try:
            child_manifest = run_daily_model_scenario(run_id=run_id, overwrite=overwrite, **config)
            comparison_rows.append(
                {
                    **row_base,
                    **_comparison_row_from_manifest(
                        scenario_id=scenario_id,
                        run_id=run_id,
                        manifest=child_manifest,
                    ),
                }
            )
        except Exception as exc:
            error_row = {
                **row_base,
                "status": "ERROR",
                "readiness_status": "SCENARIO_RUN_FAILED_RESEARCH_ONLY",
                "error": str(exc),
                "cost_sensitivity_bp": [0, 23, 46],
                "blocking_reasons": ["SCENARIO_RUN_FAILED", str(exc)],
                "model_build_allowed": False,
                "go_summary_allowed": False,
                "paper_forward_allowed": False,
                "live_broker_order_allowed": False,
            }
            errors.append(error_row)
            comparison_rows.append(error_row)
            if stop_on_error:
                break

    failed_count = sum(1 for row in comparison_rows if row.get("status") == "ERROR")
    manifest = {
        "schema_version": 1,
        "batch_id": resolved_batch_id,
        "generated_at": _utc_now(),
        "started_at": started_at,
        "mode": "daily_ohlcv_model_scenario_batch",
        "platform_stage": "SCENARIO_BATCH_RUNNER_MVP",
        "status": "DRY_RUN" if dry_run else ("PARTIAL_ERROR_RESEARCH_ONLY" if failed_count else "COMPLETED_RESEARCH_ONLY"),
        "read_only_artifact": True,
        "dry_run": dry_run,
        "guardrail": RESEARCH_GUARDRAIL,
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "no_live_broker_order_readiness": True,
        "scenario_count": len(scenarios),
        "completed_count": len(comparison_rows) - failed_count,
        "failed_count": failed_count,
        "gate_status_counts": _status_counts(comparison_rows),
        "plan": plan,
        "comparison_rows": comparison_rows,
        "errors": errors,
        "artifact_paths": {
            "scenario_batch_manifest": str(out_dir / "scenario_batch_manifest.json"),
            "scenario_batch_plan": str(out_dir / "scenario_batch_plan.json"),
        },
    }
    _write_json(out_dir / "scenario_batch_manifest.json", manifest)
    return manifest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a research-only Daily OHLCV scenario batch from a JSON plan.")
    parser.add_argument("--plan", type=Path, help="JSON plan containing batch_id, defaults, and scenarios")
    parser.add_argument("--batch-id", help="Override or provide the batch id")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-template", action="store_true", help="Print a small JSON batch plan template and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.emit_template:
        print(json.dumps(default_batch_plan(batch_id=args.batch_id or "scenario_batch_smoke_001"), ensure_ascii=False, indent=2))
        return 0
    payload = run_daily_scenario_batch(
        plan_path=args.plan,
        batch_id=args.batch_id,
        overwrite=args.overwrite,
        stop_on_error=args.stop_on_error,
        dry_run=args.dry_run,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_SCENARIO_BATCH_ROOT",
    "RUNNER_DEFAULTS",
    "build_arg_parser",
    "default_batch_plan",
    "load_batch_plan",
    "main",
    "run_daily_scenario_batch",
]
