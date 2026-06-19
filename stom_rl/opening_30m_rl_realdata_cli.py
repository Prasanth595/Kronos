"""CLI for bounded opening real-data workflow smoke runs."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Sequence

from .opening_30m_rl_realdata_adapter import (
    RealdataAdapterConfig,
    RealdataNoGoDataError,
    load_opening_realdata_frames,
)
from .opening_30m_rl_runner import run_opening_workflow_stages
from .opening_30m_rl_candidate_smoke import attach_candidate_smoke_artifacts
from .opening_30m_rl_workflow import OpeningWorkflowConfig, build_opening_workflow_manifest

SUMMARY_FILENAME = "opening_30m_rl_workflow_summary.json"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded opening 30-minute real-data smoke workflow.")
    parser.add_argument("--db", required=True, help="Read-only STOM SQLite DB path.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-tables", type=int, default=5)
    parser.add_argument("--max-sessions-per-table", type=int, default=1)
    parser.add_argument("--max-rows-per-session", type=int, default=1800)
    parser.add_argument("--min-rows-per-session", type=int, default=4)
    parser.add_argument("--time-start", default="090000")
    parser.add_argument("--time-end", default="093000")
    parser.add_argument("--cost-bps", type=float, default=23.0)
    parser.add_argument("--create-split", action="store_true")
    parser.add_argument("--split-manifest", default="")
    parser.add_argument("--candidate-algos", default="")
    parser.add_argument("--tiny-train", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the real-data smoke CLI and return a process exit code."""

    args = _parse_args(argv)
    db_path = Path(args.db)
    candidate_mode = bool(args.candidate_algos)
    output_dir = _effective_output_dir(Path(args.output_dir), str(args.run_id), candidate_mode)
    if args.candidate_algos and not args.create_split and not args.split_manifest:
        print("candidate OOS smoke requires --split-manifest or explicit --create-split", file=sys.stderr)
        return 2
    if args.split_manifest and not Path(str(args.split_manifest)).is_file():
        print(f"split manifest not found: {args.split_manifest}", file=sys.stderr)
        return 2
    if not db_path.is_file():
        print(f"SQLite DB not found: {db_path}", file=sys.stderr)
        return 2

    workflow_config = OpeningWorkflowConfig(
        run_id=str(args.run_id),
        output_dir=output_dir,
        cost_bps=float(args.cost_bps),
        time_start=str(args.time_start),
        time_end=str(args.time_end),
        mode="realdata_smoke",
    )
    adapter_config = RealdataAdapterConfig(
        db_path=db_path,
        output_dir=output_dir / "realdata_adapter",
        max_tables=int(args.max_tables),
        max_sessions_per_table=int(args.max_sessions_per_table),
        max_rows_per_session=int(args.max_rows_per_session),
        min_rows_per_session=int(args.min_rows_per_session),
        time_start=str(args.time_start),
        time_end=str(args.time_end),
    )

    try:
        adapter = load_opening_realdata_frames(adapter_config)
    except RealdataNoGoDataError as exc:
        payload = _no_go_data_payload(workflow_config, adapter_config, str(exc))
        frames = []
    else:
        frames = adapter.frames
        payload = run_opening_workflow_stages(adapter.frames, workflow_config, request_training=False)
        if str(payload.get("verdict", "")) in {"PENDING", "PENDING_TRAINING"}:
            payload["verdict"] = "INCONCLUSIVE"
        payload["realdata"] = _realdata_context(adapter.summary)
        _write_summary(output_dir, payload)

    if args.candidate_algos:
        attach_candidate_smoke_artifacts(
            output_dir,
            payload,
            frames=frames,
            candidate_algos=str(args.candidate_algos),
            create_split=bool(args.create_split),
            split_manifest_path=str(args.split_manifest),
            tiny_train=bool(args.tiny_train),
            cost_bps=float(args.cost_bps),
        )
        _write_summary(output_dir, payload)

    print(json.dumps(_stdout_summary(payload), ensure_ascii=False))
    return 0


def _no_go_data_payload(
    workflow_config: OpeningWorkflowConfig,
    adapter_config: RealdataAdapterConfig,
    reason: str,
) -> dict[str, object]:
    payload = build_opening_workflow_manifest(workflow_config)
    payload["verdict"] = "NO-GO_DATA"
    payload["realdata"] = {
        "verdict": "NO-GO_DATA",
        "reason": reason,
        "bounds": _bounds(adapter_config),
        "sampled_tables": [],
        "training_status": _training_status(),
    }
    _write_summary(Path(workflow_config.output_dir), payload)
    return payload


def _effective_output_dir(output_dir: Path, run_id: str, candidate_mode: bool) -> Path:
    if candidate_mode and output_dir.name != run_id:
        return output_dir / run_id
    return output_dir


def _realdata_context(summary: dict[str, object]) -> dict[str, object]:
    return {
        "verdict": summary.get("verdict", "INCONCLUSIVE"),
        "bounds": summary.get("bounds", {}),
        "sampled_tables": summary.get("sampled_tables", []),
        "training_status": _training_status(),
        "model_status": "no_model_trained",
        "guardrail": "RL EXPERIMENT; bounded real-data smoke; not live-ready.",
    }


def _bounds(config: RealdataAdapterConfig) -> dict[str, object]:
    return {
        "max_tables": int(config.max_tables),
        "max_sessions_per_table": int(config.max_sessions_per_table),
        "max_rows_per_session": int(config.max_rows_per_session),
        "min_rows_per_session": int(config.min_rows_per_session),
        "time_start": config.time_start,
        "time_end": config.time_end,
    }


def _training_status() -> str:
    if importlib.util.find_spec("stable_baselines3") is None:
        return "skipped_sb3_unavailable"
    return "available_not_requested"


def _write_summary(output_dir: Path, payload: dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / SUMMARY_FILENAME).write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _stdout_summary(payload: dict[str, object]) -> dict[str, object]:
    return {
        "artifact_type": payload.get("artifact_type"),
        "run_id": payload.get("run_id"),
        "verdict": payload.get("verdict"),
        "summary_json": str(Path(str(payload["artifacts"]["summary_json"]))),
    }
