"""Dashboard-compatible evaluation artifacts for opening RL workflows."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


SUMMARY_JSON = "summary.json"
SUMMARY_CSV = "summary.csv"
ACTIONS_CSV = "actions.csv"
TRADES_CSV = "trades.csv"
EPISODES_CSV = "episodes.csv"
BASELINE_CSV = "baseline.csv"
DIAGNOSTICS_JSON = "diagnostics.json"
LIVE_EVENTS_JSONL = "rl_live_events.jsonl"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def _config_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _summary_row(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": "opening_30m_eval_artifacts",
        "status": summary["training_status"],
        "algorithm": summary["algorithm"],
        "seed": summary["seed"],
        "cost_bps": summary["cost_bps"],
        "train_episode_count": len(summary["train_episode_ids"]),
        "eval_episode_count": len(summary["eval_episode_ids"]),
        "baseline_delta_inputs": json.dumps(summary["baseline_delta_inputs"], ensure_ascii=False, sort_keys=True),
    }


def _action_rows(training_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode in training_payload.get("evaluation", []):
        rows.append(
            {
                "episode_id": episode.get("episode_id"),
                "policy_step_count": episode.get("steps", 0),
                "policy_action_space": "fixed_entry_exit_only",
                "algorithm": training_payload.get("algorithm", "DQN"),
            }
        )
    return rows


def _trade_rows(training_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode in training_payload.get("evaluation", []):
        rows.append(
            {
                "episode_id": episode.get("episode_id"),
                "trade_count": episode.get("trade_count", 0),
                "reward": episode.get("reward", 0.0),
                "cost_model": "23bp_marketable_fill",
            }
        )
    return rows


def _episode_rows(training_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode_id in training_payload.get("train_episode_ids", []):
        rows.append({"episode_id": episode_id, "split": "train"})
    for episode_id in training_payload.get("eval_episode_ids", []):
        rows.append({"episode_id": episode_id, "split": "eval"})
    return rows


def _live_events(path: Path, training_payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "event": "opening_eval_artifacts_written",
        "status": training_payload.get("status"),
        "algorithm": training_payload.get("algorithm", "DQN"),
    }
    path.write_text(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def write_opening_eval_artifacts(
    *,
    output_dir: Path,
    training_payload: Mapping[str, Any],
    baseline_payload: Mapping[str, Any],
    source_manifest_path: Path,
    seed: int,
    cost_bps: float,
) -> dict[str, Any]:
    """Write reproducibility and dashboard table artifacts for opening RL."""

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "summary_json": str(output_dir / SUMMARY_JSON),
        "summary_csv": str(output_dir / SUMMARY_CSV),
        "actions_csv": str(output_dir / ACTIONS_CSV),
        "trades_csv": str(output_dir / TRADES_CSV),
        "episodes_csv": str(output_dir / EPISODES_CSV),
        "baseline_csv": str(output_dir / BASELINE_CSV),
        "diagnostics_json": str(output_dir / DIAGNOSTICS_JSON),
        "live_events_jsonl": str(output_dir / LIVE_EVENTS_JSONL),
    }
    summary = {
        "training_status": training_payload.get("status"),
        "algorithm": training_payload.get("algorithm", "DQN"),
        "seed": int(seed),
        "config_hash": _config_hash(
            {
                "seed": int(seed),
                "cost_bps": float(cost_bps),
                "source_manifest_path": str(source_manifest_path),
                "train_episode_ids": list(training_payload.get("train_episode_ids", [])),
                "eval_episode_ids": list(training_payload.get("eval_episode_ids", [])),
            }
        ),
        "source_manifest_path": str(source_manifest_path),
        "train_episode_ids": list(training_payload.get("train_episode_ids", [])),
        "eval_episode_ids": list(training_payload.get("eval_episode_ids", [])),
        "cost_bps": float(cost_bps),
        "baseline_delta_inputs": baseline_payload.get("summary", {}).get("baseline_delta_inputs", {}),
        "safety_note": "Opening RL evidence only; not live-ready and not a profit model.",
    }
    payload: dict[str, Any] = {
        "artifact_type": "opening_30m_eval_artifacts",
        "mode": "opening_30m_evaluation_artifacts",
        "summary": summary,
        "training": dict(training_payload),
        "baseline": {
            "artifact_type": baseline_payload.get("artifact_type"),
            "summary": baseline_payload.get("summary", {}),
        },
        "artifacts": artifacts,
        "strategy_context": {
            "line": "opening_rl_experiment",
            "label": "RL EXPERIMENT EVIDENCE",
            "is_live_ready": False,
            "is_profit_model": False,
        },
    }
    _write_json(Path(artifacts["summary_json"]), payload)
    _write_csv(Path(artifacts["summary_csv"]), [_summary_row(summary)], list(_summary_row(summary)))
    _write_csv(Path(artifacts["actions_csv"]), _action_rows(training_payload), ("episode_id", "policy_step_count", "policy_action_space", "algorithm"))
    _write_csv(Path(artifacts["trades_csv"]), _trade_rows(training_payload), ("episode_id", "trade_count", "reward", "cost_model"))
    _write_csv(Path(artifacts["episodes_csv"]), _episode_rows(training_payload), ("episode_id", "split"))
    _write_csv(Path(artifacts["baseline_csv"]), list(baseline_payload.get("rows", [])), ("episode_id", "symbol", "session", "policy", "net_return_pct", "cost_bps"))
    _write_json(
        Path(artifacts["diagnostics_json"]),
        {
            "training_status": training_payload.get("status"),
            "model_files": training_payload.get("model_files", {}),
            "source_manifest_path": str(source_manifest_path),
            "cost_bps": float(cost_bps),
        },
    )
    _live_events(Path(artifacts["live_events_jsonl"]), training_payload)
    return payload
