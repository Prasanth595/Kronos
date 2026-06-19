"""Candidate lifecycle artifacts for bounded opening real-data OOS runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd  # noqa: PANDAS_OK - STOM tick/orderbook episodes are pandas frames

from .opening_30m_rl_candidate_gate import (
    CandidateGateInput,
    REQUIRED_ABLATIONS,
    build_ablation_artifact,
    build_control_artifact,
    evaluate_candidate_gate,
)
from .opening_30m_rl_candidate_diagnostics import ablation_rows, evaluated_control_rows, oos_baseline_inputs
from .opening_30m_rl_candidates import CandidateConfig, default_candidate_configs
from .opening_30m_rl_candidate_training import train_realdata_candidates
from .opening_30m_rl_context import OPENING_RL_CONTEXT_FEATURE_NAMES, build_opening_rl_context
from .opening_30m_rl_candidate_summary import reconcile_candidate_summary
from .opening_30m_rl_dataset import build_dataset_artifact
from .opening_30m_rl_oos_split import build_oos_split_manifest, validate_oos_split_manifest
from .opening_30m_rl_realdata import JsonValue


def attach_candidate_smoke_artifacts(
    output_dir: Path,
    payload: dict[str, object],
    *,
    frames: Sequence[pd.DataFrame],
    candidate_algos: str,
    create_split: bool,
    split_manifest_path: str,
    tiny_train: bool,
    cost_bps: float,
) -> None:
    """Attach real-data split, dataset, training, control, ablation, and gate artifacts."""

    sampled_tables = _sampled_tables(payload)
    split_manifest = _load_or_create_split(output_dir, sampled_tables, create_split, split_manifest_path)
    dataset = build_dataset_artifact(
        _dataset_rows(sampled_tables, split_manifest),
        split_manifest=split_manifest,
        features=["trade_strength", "orderbook_imbalance"],
        participant_proxy_availability={"foreign_net_buy": False},
        orderbook_feature_availability={"best_bid_ask": True},
        output_path=output_dir / "opening_oos_dataset_artifact.json",
    )
    configs = _requested_configs(candidate_algos, str(split_manifest["split_hash"]))
    training = train_realdata_candidates(configs, frames=frames, split_manifest=split_manifest, output_dir=output_dir, tiny_train=tiny_train)
    best = _best_candidate(training)
    baseline_inputs = _baseline_inputs(payload, split_manifest, output_dir)
    base_config = _best_config(configs, best)
    controls = build_control_artifact(
        evaluated_control_rows(
            best,
            baseline_inputs,
            frames=frames,
            split_manifest=split_manifest,
            output_dir=output_dir,
            config=base_config,
        ),
        split_hash=str(split_manifest["split_hash"]),
        cost_bps=cost_bps,
        candidate_id=str(best["candidate_id"]),
    )
    ablation_training = train_realdata_candidates(
        _ablation_configs(configs, best),
        frames=frames,
        split_manifest=split_manifest,
        output_dir=output_dir / "ablations",
        tiny_train=tiny_train,
    )
    ablations = build_ablation_artifact(
        ablation_rows(best, ablation_training),
        split_hash=str(split_manifest["split_hash"]),
        candidate_id=str(best["candidate_id"]),
    )
    gate = evaluate_candidate_gate(
        CandidateGateInput(
            candidate_id=str(best["candidate_id"]),
            split_hash=str(split_manifest["split_hash"]),
            validation_net_return_pct=float(best["validation_net_return_pct"] or 0.0),
            oos_net_return_pct=float(best["oos_net_return_pct"] or 0.0),
            no_trade_net_return_pct=float(baseline_inputs["no_trade"]),
            buy_and_hold_net_return_pct=float(baseline_inputs["buy_and_hold"]),
            ts_imb_rule_net_return_pct=float(baseline_inputs["ts_imb_rule"]),
            cost_bps=cost_bps,
            controls_passed=bool(controls["negative_control_passed"]),
            ablations_passed=bool(ablations["feature_ablation_passed"]),
            trade_count=int(best.get("oos_trade_count", 0) or 0),
            max_drawdown_pct=float(best.get("oos_max_drawdown_pct", 0.0) or 0.0),
        )
    )
    candidate_payload = {
        "split_manifest": split_manifest,
        "dataset": dataset,
        "context_features": _context_features(frames),
        "training": training,
        "ablation_training": ablation_training,
        "controls": controls,
        "ablations": ablations,
        "promotion_gate": gate,
    }
    _write_json(output_dir / "opening_candidate_lifecycle.json", candidate_payload)
    payload["candidate_lifecycle"] = candidate_payload
    payload["candidate_history"] = training.get("candidates", [])
    payload["candidate_verdict"] = gate.get("verdict")
    payload["candidate_count"] = len(training.get("candidates", []))
    payload["split_hash"] = split_manifest.get("split_hash")
    reconcile_candidate_summary(payload, training, controls, ablations)


def _context_features(frames: Sequence[pd.DataFrame]) -> dict[str, JsonValue]:
    if not frames:
        return {
            "artifact_type": "opening_30m_rl_context_features",
            "feature_names": list(OPENING_RL_CONTEXT_FEATURE_NAMES),
            "status": "missing_real_oos_frames",
            "sample": {},
        }
    sample = build_opening_rl_context(frames[0], decision_second=min(3, len(frames[0]) - 1))
    return {
        "artifact_type": "opening_30m_rl_context_features",
        "feature_names": list(OPENING_RL_CONTEXT_FEATURE_NAMES),
        "status": "available",
        "sample": sample,
    }


def _load_or_create_split(
    output_dir: Path,
    sampled_tables: Sequence[Mapping[str, object]],
    create_split: bool,
    split_manifest_path: str,
) -> dict[str, JsonValue]:
    if split_manifest_path:
        manifest = json.loads(Path(split_manifest_path).read_text(encoding="utf-8-sig"))
        validate_oos_split_manifest(manifest)
        _write_json(output_dir / "opening_oos_split_manifest.json", manifest)
        return manifest
    split_manifest = build_oos_split_manifest(
        _split_sessions_from_sampled_tables(sampled_tables),
        symbol_sessions=_symbol_sessions(sampled_tables),
        output_path=output_dir / "opening_oos_split_manifest.json" if create_split else None,
    )
    return split_manifest


def _sampled_tables(payload: Mapping[str, object]) -> list[dict[str, object]]:
    realdata = payload.get("realdata", {})
    if isinstance(realdata, dict):
        sampled = realdata.get("sampled_tables", [])
        if isinstance(sampled, list) and sampled:
            return [dict(row) for row in sampled if isinstance(row, dict)]
    return []


def _dataset_rows(sampled_tables: Sequence[Mapping[str, object]], split_manifest: Mapping[str, JsonValue]) -> list[dict[str, object]]:
    rows = [
        {"symbol": str(table.get("symbol", "")), "session_date": str(row.get("session", "")), "row_count": int(row.get("row_count", 0) or 0)}
        for table in sampled_tables
        for row in table.get("sessions", [])
        if isinstance(row, dict) and bool(row.get("eligible", False))
    ]
    if rows:
        return rows
    return [
        {"symbol": "NO_GO_DATA", "session_date": session, "row_count": 0, "exclusion_reason": "NO-GO_DATA"}
        for split in ("train", "validation", "oos")
        for session in _split_sessions(split_manifest, split)
    ]


def _split_sessions(split_manifest: Mapping[str, JsonValue], split: str) -> list[str]:
    raw = split_manifest.get("split_sessions", {})
    if not isinstance(raw, Mapping):
        return []
    sessions = raw.get(split, [])
    return [str(session) for session in sessions] if isinstance(sessions, list) else []


def _eligible_sessions(sampled_tables: Sequence[Mapping[str, object]]) -> list[str]:
    return sorted(
        {
            str(row.get("session", ""))
            for table in sampled_tables
            for row in table.get("sessions", [])
            if isinstance(row, dict) and bool(row.get("eligible", False)) and row.get("session")
        }
    )


def _split_sessions_from_sampled_tables(sampled_tables: Sequence[Mapping[str, object]]) -> dict[str, list[str]]:
    sessions = _eligible_sessions(sampled_tables) or ["20250102", "20250103", "20250106"]
    train_end = max(1, int(len(sessions) * 0.6))
    validation_end = min(len(sessions) - 1, max(train_end + 1, int(len(sessions) * 0.8)))
    return {"train": sessions[:train_end], "validation": sessions[train_end:validation_end], "oos": sessions[validation_end:]}


def _symbol_sessions(sampled_tables: Sequence[Mapping[str, object]]) -> dict[str, list[str]]:
    return {
        str(table.get("symbol", "")): sorted(
            str(row.get("session", ""))
            for row in table.get("sessions", [])
            if isinstance(row, dict) and bool(row.get("eligible", False)) and row.get("session")
        )
        for table in sampled_tables
        if table.get("symbol")
    }


def _requested_configs(candidate_algos: str, split_hash: str) -> list[CandidateConfig]:
    requested = {part.strip() for part in candidate_algos.split(",") if part.strip()}
    return [config for config in default_candidate_configs(split_hash) if config.algorithm.value in requested]


def _best_candidate(training: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    rows = [row for row in training.get("candidates", []) if isinstance(row, dict)]
    if not rows:
        return {"candidate_id": "opening_candidate_smoke", "validation_net_return_pct": 0.0, "oos_net_return_pct": 0.0}
    return max(rows, key=lambda row: float(row.get("validation_net_return_pct", 0.0) or 0.0))


def _best_config(configs: Sequence[CandidateConfig], best: Mapping[str, JsonValue]) -> CandidateConfig:
    for config in configs:
        if config.candidate_id == best.get("candidate_id"):
            return config
    if configs:
        return configs[0]
    return default_candidate_configs(str(best.get("split_hash", "")))[0]


def _baseline_inputs(payload: Mapping[str, object], split_manifest: Mapping[str, JsonValue], output_dir: Path) -> dict[str, float]:
    oos_values = oos_baseline_inputs(output_dir, _split_sessions(split_manifest, "oos"), split_manifest.get("split_hash"))
    if oos_values:
        return oos_values
    stage_results = payload.get("stage_results", {})
    baseline = stage_results.get("baseline", {}) if isinstance(stage_results, Mapping) else {}
    summary = baseline.get("summary", {}) if isinstance(baseline, Mapping) else {}
    values = summary.get("baseline_delta_inputs", {}) if isinstance(summary, Mapping) else {}
    if not isinstance(values, Mapping):
        values = {}
    return {
        "no_trade": float(values.get("no_trade", 0.0) or 0.0),
        "buy_and_hold": float(values.get("buy_and_hold", 0.0) or 0.0),
        "ts_imb_rule": float(values.get("ts_imb_same_decision_tp5_sl1_time", values.get("ts_imb_rule", 0.0)) or 0.0),
    }

def _ablation_configs(configs: Sequence[CandidateConfig], best: Mapping[str, JsonValue]) -> list[CandidateConfig]:
    base = next((config for config in configs if config.candidate_id == best.get("candidate_id")), configs[0] if configs else None)
    if base is None:
        return []
    feature_sets = REQUIRED_ABLATIONS
    return [
        CandidateConfig(
            candidate_id=f"{base.candidate_id}_{feature_set_id}",
            algorithm=base.algorithm,
            seed=base.seed + index + 1,
            total_timesteps=base.total_timesteps,
            split_hash=base.split_hash,
            feature_set_id=feature_set_id,
            cost_bps=base.cost_bps,
        )
        for index, feature_set_id in enumerate(feature_sets)
    ]


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
