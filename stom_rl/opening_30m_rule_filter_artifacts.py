"""Artifact writer for opening RULE filter runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .opening_30m_rule_filter_contract import rule_filter_strategy_context


def write_rule_filter_artifacts(
    *,
    output_dir: Path,
    split_manifest: Mapping[str, Any],
    policy: Mapping[str, Any],
    controls: Mapping[str, Any],
    ablations: Mapping[str, Any],
    gate: Mapping[str, Any],
    dataset_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Write lifecycle and table artifacts for dashboard inspection."""

    output_dir.mkdir(parents=True, exist_ok=True)
    baseline_semantics = _baseline_semantics()
    lifecycle = {
        "artifact_type": "opening_rule_filter_lifecycle",
        "strategy_context": rule_filter_strategy_context(),
        "feature_set_id": policy.get("feature_set_id", "full_context"),
        "baseline_semantics": baseline_semantics,
        "split_manifest": dict(split_manifest),
        "policy": dict(policy),
        "controls": dict(controls),
        "ablations": dict(ablations),
        "promotion_gate": dict(gate),
        "dataset_rows": [dict(row) for row in dataset_rows],
        "context_features": _context_features(dataset_rows),
    }
    _write(output_dir / "opening_rule_filter_lifecycle.json", lifecycle)
    _write(output_dir / "opening_rule_filter_controls.json", dict(controls))
    _write(output_dir / "opening_rule_filter_ablations.json", dict(ablations))
    _write(output_dir / "opening_rule_filter_gate.json", dict(gate))
    summary = {
        "artifact_type": "opening_30m_rule_filter",
        "verdict": gate.get("verdict", "INCONCLUSIVE"),
        "split_hash": split_manifest.get("split_hash"),
        "cost_bps": gate.get("cost_bps"),
        "feature_set_id": policy.get("feature_set_id", "full_context"),
        "baseline_semantics": baseline_semantics,
        "strategy_context": rule_filter_strategy_context(),
        "artifacts": {"output_dir": str(output_dir), "lifecycle_json": str(output_dir / "opening_rule_filter_lifecycle.json")},
        "rule_filter_lifecycle": lifecycle,
    }
    _write(output_dir / "opening_rule_filter_summary.json", summary)
    return summary


def _baseline_semantics() -> dict[str, str]:
    return {
        "artifact_buy_and_hold": "rule-filter control derived from base dataset rows; may equal ts_imb_rule when base_action is already ts_imb-gated",
        "artifact_ts_imb_rule": "RULE baseline derived from base rule-filter dataset rows; never reinforcement learning",
        "independent_buy_and_hold_source": "stom_rl.opening_30m_rl_baselines.evaluate_opening_baselines",
        "guardrail": "Do not report artifact baseline equality as independent outperformance.",
    }


def _context_features(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"feature_names": [], "sample": {}, "status": "empty"}
    first = rows[0]
    features = first.get("feature_values", {})
    if not isinstance(features, dict):
        return {"feature_names": [], "sample": {}, "status": "missing"}
    return {"feature_names": list(features), "sample": {"episode_id": first.get("episode_id"), "vector": list(features.values())}, "status": "available"}


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
