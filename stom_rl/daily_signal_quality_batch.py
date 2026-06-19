"""Batch runner for Daily OHLCV signal-quality diagnostics."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .daily_signal_quality import (
    DEFAULT_COST_SENSITIVITY_BP,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PREDICTION_DIR,
    DEFAULT_SCORE_COLUMN,
    DEFAULT_PORTFOLIO_DIR,
    DEFAULT_WALK_FORWARD_DIR,
    RESEARCH_GUARDRAIL,
    run_signal_quality_audit,
)

DEFAULT_BATCH_ROOT = Path("webui/rl_runs/daily_ohlcv_signal_quality_batches")
DEFAULT_BATCH_ID = "scenario_batch_signal_quality_audit_001"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge_config(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    merged.update(overrides)
    return merged


def run_signal_quality_batch(
    *,
    plan_path: Path,
    batch_id: str | None = None,
    batch_root: Path = DEFAULT_BATCH_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    overwrite: bool = False,
) -> dict[str, Any]:
    plan = _read_json(plan_path)
    resolved_batch_id = batch_id or str(plan.get("batch_id") or DEFAULT_BATCH_ID)
    batch_dir = batch_root / resolved_batch_id
    if batch_dir.exists() and overwrite:
        shutil.rmtree(batch_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)

    defaults = plan.get("defaults") if isinstance(plan.get("defaults"), dict) else {}
    scenarios = plan.get("scenarios") if isinstance(plan.get("scenarios"), list) else []
    if not scenarios:
        raise ValueError("Signal-quality batch plan must include at least one scenario")

    runs: list[dict[str, Any]] = []
    gate_status_counts: dict[str, int] = {}
    started_at = _utc_now()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValueError("Each scenario must be an object")
        scenario_id = str(scenario.get("scenario_id") or "scenario")
        config = _merge_config(defaults, scenario.get("overrides") if isinstance(scenario.get("overrides"), dict) else {})
        run_id = f"{resolved_batch_id}__{scenario_id}"
        manifest = run_signal_quality_audit(
            prediction_dir=Path(config.get("prediction_dir") or DEFAULT_PREDICTION_DIR),
            walk_forward_dir=Path(config.get("walk_forward_dir") or DEFAULT_WALK_FORWARD_DIR),
            portfolio_dir=Path(config.get("portfolio_dir") or DEFAULT_PORTFOLIO_DIR),
            output_root=output_root,
            run_id=run_id,
            score_column=str(config.get("score_column") or DEFAULT_SCORE_COLUMN),
            cost_bp=int(config.get("cost_bp") or 23),
        )
        status = str(scenario.get("status") or "WATCH")
        gate_status_counts[status] = gate_status_counts.get(status, 0) + 1
        runs.append(
            {
                "scenario_id": scenario_id,
                "run_id": run_id,
                "status": status,
                "promotion_status": manifest.get("promotion_status"),
                "hypothesis": scenario.get("hypothesis"),
                "diagnostic_focus": scenario.get("diagnostic_focus"),
                "assumption_tags": scenario.get("assumption_tags") or [],
                "config": config,
                "row_counts": manifest.get("row_counts"),
                "cost_sensitivity_bp": manifest.get("cost_sensitivity_bp"),
                "baseline_controls": manifest.get("baseline_controls"),
                "artifact_paths": manifest.get("required_artifacts"),
                "baseline_control_metrics": (manifest.get("row_counts") or {}).get("baseline_control_metrics"),
                "model_build_allowed": False,
                "go_summary_allowed": False,
                "paper_forward_allowed": False,
                "live_broker_order_allowed": False,
            }
        )

    copied_plan = batch_dir / "scenario_batch_plan.json"
    _write_json(copied_plan, plan)
    manifest_payload = {
        "schema_version": 1,
        "batch_id": resolved_batch_id,
        "generated_at": _utc_now(),
        "started_at": started_at,
        "mode": "daily_ohlcv_signal_quality_batch",
        "platform_stage": "D3_D4_SIGNAL_QUALITY_AUDIT_BATCH_MVP",
        "status": "COMPLETED_RESEARCH_ONLY",
        "read_only_artifact": True,
        "guardrail": RESEARCH_GUARDRAIL,
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "scenario_count": len(runs),
        "completed_count": len(runs),
        "failed_count": 0,
        "gate_status_counts": gate_status_counts,
        "cost_sensitivity_bp": list(DEFAULT_COST_SENSITIVITY_BP),
        "plan": plan,
        "runs": runs,
        "comparison_rows": [
            {
                "scenario_id": row["scenario_id"],
                "status": row["status"],
                "promotion_status": row["promotion_status"],
                "bucket_metric_rows": (row.get("row_counts") or {}).get("bucket_metrics"),
                "rank_correlation_rows": (row.get("row_counts") or {}).get("rank_correlations"),
                "risk_proxy_rows": (row.get("row_counts") or {}).get("risk_proxy_metrics"),
                "baseline_control_rows": (row.get("row_counts") or {}).get("baseline_control_metrics"),
                "baseline_controls_measured": True,
                "model_build_allowed": False,
                "paper_forward_allowed": False,
                "live_broker_order_allowed": False,
            }
            for row in runs
        ],
        "artifact_paths": {
            "scenario_batch_manifest": str(batch_dir / "scenario_batch_manifest.json"),
            "scenario_batch_plan": str(copied_plan),
        },
    }
    _write_json(batch_dir / "scenario_batch_manifest.json", manifest_payload)
    return manifest_payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a research-only Daily OHLCV signal-quality diagnostic batch.")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--batch-root", type=Path, default=DEFAULT_BATCH_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = run_signal_quality_batch(
        plan_path=args.plan,
        batch_id=args.batch_id,
        batch_root=args.batch_root,
        output_root=args.out_dir,
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {
                "batch_id": manifest["batch_id"],
                "status": manifest["status"],
                "scenario_count": manifest["scenario_count"],
                "completed_count": manifest["completed_count"],
                "failed_count": manifest["failed_count"],
                "gate_status_counts": manifest["gate_status_counts"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
