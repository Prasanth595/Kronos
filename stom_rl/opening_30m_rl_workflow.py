"""Contract-first opening 30-minute RL workflow manifest.

The workflow manifest is an evidence contract, not a training routine.  It
lets later stages attach readiness, baseline, training, control, cost-gate, and
dashboard artifacts while preserving the project guardrails: research-only,
not live-ready, and not a profit model.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from .opening_30m_rl_env_contract import build_opening_env_contract_stage


DEFAULT_COST_BPS = 23.0
DEFAULT_TIME_START = "090000"
DEFAULT_TIME_END = "093000"
DEFAULT_RUN_ID = "opening_30m_rl_workflow"
SUMMARY_FILENAME = "opening_30m_rl_workflow_summary.json"
GUARDRAIL = "research evidence only; not live-ready and not a profit model"


@dataclass(frozen=True, slots=True)
class UnsafeWorkflowClaimError(Exception):
    """Raised when a workflow manifest tries to claim unsafe readiness."""

    field_name: str

    def __str__(self) -> str:
        return f"opening workflow cannot set {self.field_name}=true"


@dataclass(frozen=True, slots=True)
class WorkflowStageError(ValueError):
    """Raised when workflow stage evidence cannot be attached."""

    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class OpeningWorkflowConfig:
    """Boundary config for the opening RL workflow contract."""

    run_id: str = DEFAULT_RUN_ID
    output_dir: Path | str = Path("webui") / "rl_runs" / DEFAULT_RUN_ID
    cost_bps: float = DEFAULT_COST_BPS
    time_start: str = DEFAULT_TIME_START
    time_end: str = DEFAULT_TIME_END
    seed: int = 100
    mode: str = "fixture_contract"
    is_live_ready: bool = False
    is_profit_model: bool = False


def _assert_research_only(config: OpeningWorkflowConfig) -> None:
    if config.is_live_ready:
        raise UnsafeWorkflowClaimError("is_live_ready")
    if config.is_profit_model:
        raise UnsafeWorkflowClaimError("is_profit_model")


def _config_payload(config: OpeningWorkflowConfig) -> dict[str, Any]:
    return {
        "run_id": config.run_id,
        "output_dir": str(Path(config.output_dir)),
        "cost_bps": float(config.cost_bps),
        "time_start": config.time_start,
        "time_end": config.time_end,
        "seed": int(config.seed),
        "mode": config.mode,
        "is_live_ready": False,
        "is_profit_model": False,
    }


def _strategy_context() -> dict[str, Any]:
    return {
        "line": "rl_experiment",
        "label": "RL EXPERIMENT",
        "primary_baseline": "ts_imb",
        "is_reinforcement_learning": True,
        "is_environment_readiness": False,
        "is_live_ready": False,
        "is_profit_model": False,
        "guardrail": GUARDRAIL,
    }


def _stages() -> list[dict[str, str]]:
    return [
        {
            "name": "contract",
            "status": "complete",
            "evidence": "opening workflow contract emitted",
        },
        {"name": "manifest", "status": "pending", "evidence": ""},
        {"name": "participant_pressure", "status": "pending", "evidence": ""},
        {"name": "orderbook_persistence", "status": "pending", "evidence": ""},
        {"name": "readiness_env", "status": "pending", "evidence": ""},
        {"name": "baseline", "status": "pending", "evidence": ""},
        {"name": "training", "status": "pending", "evidence": ""},
        {"name": "evaluation", "status": "pending", "evidence": ""},
        {"name": "controls", "status": "pending", "evidence": ""},
        {"name": "cost_gate", "status": "pending", "evidence": ""},
        {"name": "dashboard", "status": "pending", "evidence": ""},
    ]


def record_workflow_stage(
    payload: Mapping[str, Any],
    stage_name: str,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach a stage result to an opening workflow manifest payload."""

    updated = dict(payload)
    stages = [dict(stage) for stage in payload.get("stages", [])]
    stage_found = False
    for stage in stages:
        if stage.get("name") == stage_name:
            stage["status"] = str(result.get("status", "complete"))
            stage["evidence"] = str(result.get("evidence", stage_name))
            stage_found = True
            break
    if not stage_found:
        raise WorkflowStageError(f"unknown workflow stage: {stage_name}")
    stage_results = dict(payload.get("stage_results", {}))
    stage_results[stage_name] = dict(result)
    updated["stages"] = stages
    updated["stage_results"] = stage_results
    return updated


def build_opening_workflow_manifest(config: OpeningWorkflowConfig) -> dict[str, Any]:
    """Build a minimal research-only opening workflow manifest."""

    _assert_research_only(config)
    output_dir = Path(config.output_dir)
    summary_path = output_dir / SUMMARY_FILENAME
    return {
        "mode": "opening_30m_rl_workflow",
        "artifact_type": "opening_30m_rl_workflow",
        "run_id": config.run_id,
        "created_at_kst": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "config": _config_payload(config),
        "stages": _stages(),
        "evidence": [],
        "verdict": "PENDING",
        "strategy_context": _strategy_context(),
        "guardrails": {
            "not_live_ready": True,
            "not_profit_model": True,
            "research_only": True,
            "baseline": "ts_imb RULE baseline",
            "cost_bps": float(config.cost_bps),
        },
        "artifacts": {
            "output_dir": str(output_dir),
            "summary_json": str(summary_path),
        },
    }


def write_opening_workflow_manifest(config: OpeningWorkflowConfig) -> dict[str, Any]:
    """Write the opening workflow manifest and return the payload."""

    payload = build_opening_workflow_manifest(config)
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / SUMMARY_FILENAME
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _load_input_frames(csv_paths: Sequence[str]) -> list[Any]:
    if not csv_paths:
        raise WorkflowStageError("--run-stages requires at least one --input-csv path")
    import pandas as pd  # noqa: PANDAS_OK - explicit CLI fixture CSV input for workflow stages

    return [pd.read_csv(Path(path), encoding="utf-8-sig") for path in csv_paths]


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write an opening 30-minute RL workflow manifest.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--output-dir", default=str(Path("webui") / "rl_runs" / DEFAULT_RUN_ID))
    parser.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    parser.add_argument("--time-start", default=DEFAULT_TIME_START)
    parser.add_argument("--time-end", default=DEFAULT_TIME_END)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--mode", default="fixture_contract")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--run-stages", action="store_true")
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--input-csv", action="append", default=[])
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    config = OpeningWorkflowConfig(
        run_id=args.run_id,
        output_dir=args.output_dir,
        cost_bps=args.cost_bps,
        time_start=args.time_start,
        time_end=args.time_end,
        seed=args.seed,
        mode=args.mode,
    )
    if args.run_stages:
        from .opening_30m_rl_runner import run_opening_workflow_stages

        payload = run_opening_workflow_stages(
            _load_input_frames(args.input_csv),
            config,
            request_training=bool(args.train),
        )
    else:
        payload = build_opening_workflow_manifest(config) if args.no_write else write_opening_workflow_manifest(config)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
