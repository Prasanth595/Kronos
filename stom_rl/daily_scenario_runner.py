"""Scenario runner for research-only Daily OHLCV model experiments.

This module wires the existing D2 -> D3 -> D4 -> D5 pipeline into one
pre-registered scenario run. It writes only generated artifacts under
``webui/rl_runs`` and keeps all model/paper/live flags locked until the normal
D5 gate proves otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .daily_ohlcv_db import REPO_ROOT
from .daily_ohlcv_dataset import DEFAULT_DATASET_ROOT, build_and_write_daily_ohlcv_dataset
from .daily_prediction import DEFAULT_PREDICTION_ROOT, run_and_write_daily_prediction
from .daily_rl_train import DEFAULT_PORTFOLIO_ROOT, run_and_write_daily_rl
from .daily_walk_forward import DEFAULT_WALK_FORWARD_ROOT, run_and_write_daily_walk_forward

DEFAULT_SCENARIO_ROOT = REPO_ROOT / "webui" / "rl_runs" / "daily_ohlcv_scenarios"
SAFE_RUN_RE = re.compile(r"^[0-9A-Za-z_.-]+$")
SCENARIO_PIPELINE_SUBDIR = "_scenario_runs"
RESEARCH_GUARDRAIL = (
    "Research-only scenario/model experiment; no profit guarantee, no live/broker/orders, "
    "no paper-forward unlock, and no deployable model readiness claim."
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_run_id(run_id: str) -> str:
    rid = str(run_id or "").strip()
    if not rid or not SAFE_RUN_RE.fullmatch(rid):
        raise ValueError("run_id must match [0-9A-Za-z_.-]+")
    return rid


def _scenario_run_dir(run_id: str, *, root: Path | str | None = None, overwrite: bool = False) -> Path:
    base = Path(root or DEFAULT_SCENARIO_ROOT).resolve()
    default_root = DEFAULT_SCENARIO_ROOT.resolve()
    try:
        base.relative_to(default_root)
    except ValueError:
        if base != default_root:
            raise ValueError("Scenario artifacts must stay under webui/rl_runs/daily_ohlcv_scenarios")
    rid = _validate_run_id(run_id)
    out_dir = (base / rid).resolve()
    try:
        out_dir.relative_to(base)
    except ValueError as exc:
        raise ValueError("run_id escapes daily scenario artifact root") from exc
    if out_dir.exists() and any(out_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"Scenario artifact run_id already exists: {rid}")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_daily_model_scenario(
    *,
    run_id: str,
    overwrite: bool = False,
    max_symbols: int | None = None,
    max_rows_per_symbol: int | None = None,
    quality_table_limit: int | None = 0,
    horizon_days: int = 1,
    train_fraction: float = 0.6,
    val_fraction: float = 0.2,
    purge_days: int = 5,
    embargo_days: int = 5,
    candidate_limit: int = 20,
    max_positions: int = 5,
    episodes: int = 8,
    rl_seed: int = 7,
    n_folds: int = 5,
    top_k: int = 20,
    wf_seed: int = 17,
    observation_mode: str = "v1",
    action_prior_mode: str = "none",
    action_prior_strength: float = 0.0,
    action_filter_mode: str = "none",
) -> dict[str, Any]:
    """Run one bounded research scenario through D2/D3/D4/D5 and write a manifest."""

    rid = _validate_run_id(run_id)
    out_dir = _scenario_run_dir(rid, overwrite=overwrite)
    started_at = _utc_now()

    config = {
        "run_id": rid,
        "max_symbols": max_symbols,
        "max_rows_per_symbol": max_rows_per_symbol,
        "quality_table_limit": quality_table_limit,
        "horizon_days": horizon_days,
        "train_fraction": train_fraction,
        "val_fraction": val_fraction,
        "purge_days": purge_days,
        "embargo_days": embargo_days,
        "candidate_limit": candidate_limit,
        "max_positions": max_positions,
        "episodes": episodes,
        "rl_seed": rl_seed,
        "n_folds": n_folds,
        "top_k": top_k,
        "wf_seed": wf_seed,
        "observation_mode": observation_mode,
        "action_prior_mode": action_prior_mode,
        "action_prior_strength": action_prior_strength,
        "action_filter_mode": action_filter_mode,
    }
    _write_json(out_dir / "candidate_generation_config.json", config)

    dataset = build_and_write_daily_ohlcv_dataset(
        run_id=rid,
        overwrite=overwrite,
        artifact_root=DEFAULT_DATASET_ROOT / SCENARIO_PIPELINE_SUBDIR,
        max_symbols=max_symbols,
        max_rows_per_symbol=max_rows_per_symbol,
        quality_table_limit=quality_table_limit,
        horizon_days=horizon_days,
        train_fraction=train_fraction,
        val_fraction=val_fraction,
        purge_days=purge_days,
        embargo_days=embargo_days,
    )
    dataset_dir = Path(dataset["written"]["artifact_dir"])

    prediction = run_and_write_daily_prediction(
        run_id=rid,
        overwrite=overwrite,
        artifact_root=DEFAULT_PREDICTION_ROOT / SCENARIO_PIPELINE_SUBDIR,
        dataset_run_dir=dataset_dir,
    )
    prediction_dir = Path(prediction["written"]["artifact_dir"])

    portfolio = run_and_write_daily_rl(
        run_id=rid,
        overwrite=overwrite,
        artifact_root=DEFAULT_PORTFOLIO_ROOT / SCENARIO_PIPELINE_SUBDIR,
        prediction_run_dir=prediction_dir,
        candidate_limit=candidate_limit,
        max_positions=max_positions,
        episodes=episodes,
        seed=rl_seed,
        observation_mode=observation_mode,
        action_prior_mode=action_prior_mode,
        action_prior_strength=action_prior_strength,
        action_filter_mode=action_filter_mode,
    )
    portfolio_dir = Path(portfolio["written"]["artifact_dir"])

    walk_forward = run_and_write_daily_walk_forward(
        run_id=rid,
        overwrite=overwrite,
        artifact_root=DEFAULT_WALK_FORWARD_ROOT / SCENARIO_PIPELINE_SUBDIR,
        prediction_run_dir=prediction_dir,
        portfolio_run_dir=portfolio_dir,
        n_folds=n_folds,
        purge_days=purge_days,
        embargo_days=embargo_days,
        top_k=top_k,
        seed=wf_seed,
    )

    gate_verdict = walk_forward["result"].get("gate_verdict", {})
    manifest = {
        "schema_version": 1,
        "run_id": rid,
        "generated_at": _utc_now(),
        "started_at": started_at,
        "mode": "daily_ohlcv_model_scenario_run",
        "guardrail": RESEARCH_GUARDRAIL,
        "config": config,
        "status": gate_verdict.get("status", "NO-GO"),
        "readiness_status": gate_verdict.get("readiness_status", "D5_NO_GO_RESEARCH_ONLY_GATE"),
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "no_live_broker_order_readiness": True,
        "artifact_dirs": {
            "scenario": str(out_dir),
            "dataset": str(dataset_dir),
            "prediction": str(prediction_dir),
            "portfolio": str(portfolio_dir),
            "walk_forward": walk_forward["written"]["artifact_dir"],
        },
        "artifact_paths": {
            "candidate_generation_config": str(out_dir / "candidate_generation_config.json"),
            "scenario_manifest": str(out_dir / "scenario_manifest.json"),
            "dataset_manifest": dataset["written"].get("dataset_manifest_path"),
            "prediction_manifest": prediction["written"].get("prediction_manifest_path"),
            "portfolio_manifest": portfolio["written"].get("rl_manifest_path"),
            "walk_forward_manifest": walk_forward["written"].get("walk_forward_manifest_path"),
            "gate_verdict": walk_forward["written"].get("gate_verdict_path"),
        },
        "gate_verdict_summary": {
            "status": gate_verdict.get("status"),
            "readiness_status": gate_verdict.get("readiness_status"),
            "selected_strategy": gate_verdict.get("selected_strategy"),
            "n_folds": gate_verdict.get("n_folds"),
            "purge_days": gate_verdict.get("purge_days"),
            "embargo_days": gate_verdict.get("embargo_days"),
            "cost_sensitivity_bp": gate_verdict.get("cost_sensitivity_bp"),
            "reasons": gate_verdict.get("reasons", []),
        },
    }
    _write_json(out_dir / "scenario_manifest.json", manifest)
    return manifest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one research-only Daily OHLCV scenario through D2-D5.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--max-rows-per-symbol", type=int, default=None)
    parser.add_argument("--quality-table-limit", type=int, default=0)
    parser.add_argument("--horizon-days", type=int, default=1)
    parser.add_argument("--train-fraction", type=float, default=0.6)
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument("--purge-days", type=int, default=5)
    parser.add_argument("--embargo-days", type=int, default=5)
    parser.add_argument("--candidate-limit", type=int, default=20)
    parser.add_argument("--max-positions", type=int, default=5)
    parser.add_argument("--episodes", type=int, default=8)
    parser.add_argument("--rl-seed", type=int, default=7)
    parser.add_argument("--n-folds", type=int, default=5)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--wf-seed", type=int, default=17)
    parser.add_argument("--observation-mode", default="v1")
    parser.add_argument("--action-prior-mode", default="none")
    parser.add_argument("--action-prior-strength", type=float, default=0.0)
    parser.add_argument("--action-filter-mode", default="none")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = run_daily_model_scenario(**vars(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_SCENARIO_ROOT",
    "SCENARIO_PIPELINE_SUBDIR",
    "RESEARCH_GUARDRAIL",
    "build_arg_parser",
    "main",
    "run_daily_model_scenario",
]
