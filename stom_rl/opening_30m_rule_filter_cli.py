"""Bounded CLI for opening 30m RULE filter smoke runs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from .opening_30m_rl_oos_split import OosSplitError, build_oos_split_manifest, validate_oos_split_manifest
from .opening_30m_rl_realdata_adapter import RealdataAdapterConfig, RealdataNoGoDataError, load_opening_realdata_frames
from .opening_30m_rule_filter_ablations import build_rule_filter_ablation_artifact
from .opening_30m_rule_filter_artifacts import write_rule_filter_artifacts
from .opening_30m_rule_filter_contract import RULE_FILTER_FEATURE_SET_IDS, RuleFilterConfig
from .opening_30m_rule_filter_controls import build_rule_filter_control_artifact
from .opening_30m_rule_filter_dataset import build_rule_filter_dataset
from .opening_30m_rule_filter_gate import RuleFilterGateInput, evaluate_rule_filter_gate
from .opening_30m_rule_filter_policy import evaluate_rule_filter_metrics, select_rule_filter_policy
from .opening_30m_rule_filter_transforms import build_rule_filter_ablation_returns

_RUN_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_.-]+$")


def main(argv: Sequence[str] | None = None) -> int:
    """Run a bounded read-only RULE filter smoke workflow."""

    args = _parse_args(argv)
    split_path = Path(str(args.split_manifest)) if args.split_manifest else None
    if split_path is not None and not split_path.is_file():
        print(f"split manifest not found: {split_path}", file=sys.stderr)
        return 2
    output_dir = _resolve_output_dir(Path(str(args.output_dir)), str(args.run_id))
    if output_dir is None:
        print(f"invalid run id: {args.run_id}", file=sys.stderr)
        return 2
    if output_dir.exists():
        print(f"run output directory already exists: {output_dir}", file=sys.stderr)
        return 2
    config = RuleFilterConfig(cost_bps=float(args.cost_bps), decision_second=int(args.decision_second), min_oos_take_trades=int(args.min_oos_take_trades), feature_set_id=str(args.feature_set))
    adapter_config = RealdataAdapterConfig(
        db_path=Path(str(args.db)),
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
        split_manifest = _load_or_create_split(adapter.frames, split_path, bool(args.create_split), output_dir)
    except (RealdataNoGoDataError, OosSplitError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    dataset = build_rule_filter_dataset(adapter.frames, split_manifest=split_manifest, config=config)
    policy = select_rule_filter_policy(dataset["rows"], config=config, split_hash=str(split_manifest["split_hash"]))
    controls = _controls(policy, dataset, config, str(split_manifest["split_hash"]))
    ablations = _ablations(policy, dataset, config, str(split_manifest["split_hash"]))
    gate = _gate(policy, dataset, controls, ablations, config, str(split_manifest["split_hash"]))
    summary = write_rule_filter_artifacts(
        output_dir=output_dir,
        split_manifest=split_manifest,
        policy=policy,
        controls=controls,
        ablations=ablations,
        gate=gate,
        dataset_rows=dataset["rows"],
    )
    print(json.dumps({"artifact_type": summary["artifact_type"], "run_id": str(args.run_id), "verdict": summary["verdict"], "summary_json": str(output_dir / "opening_rule_filter_summary.json"), "split_hash": summary["split_hash"]}, ensure_ascii=False))
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded opening 30m RULE filter smoke workflow.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", default="opening_30m_rule_filter_smoke")
    parser.add_argument("--split-manifest", default="")
    parser.add_argument("--create-split", action="store_true")
    parser.add_argument("--max-tables", type=int, default=1)
    parser.add_argument("--max-sessions-per-table", type=int, default=3)
    parser.add_argument("--max-rows-per-session", type=int, default=1800)
    parser.add_argument("--min-rows-per-session", type=int, default=4)
    parser.add_argument("--time-start", default="090000")
    parser.add_argument("--time-end", default="093000")
    parser.add_argument("--cost-bps", type=float, default=23.0)
    parser.add_argument("--decision-second", type=int, default=0)
    parser.add_argument("--min-oos-take-trades", type=int, default=1)
    parser.add_argument("--feature-set", choices=RULE_FILTER_FEATURE_SET_IDS, default="full_context")
    return parser.parse_args(argv)


def _resolve_output_dir(output_root: Path, run_id: str) -> Path | None:
    if not _is_safe_run_id(run_id):
        return None
    return output_root / run_id


def _is_safe_run_id(run_id: str) -> bool:
    return run_id not in {".", ".."} and _RUN_ID_PATTERN.fullmatch(run_id) is not None


def _load_or_create_split(frames: Sequence[object], split_path: Path | None, create_split: bool, output_dir: Path) -> dict[str, object]:
    if split_path is not None:
        manifest = json.loads(split_path.read_text(encoding="utf-8-sig"))
        validate_oos_split_manifest(manifest)
        return manifest
    if not create_split:
        raise OosSplitError("rule filter smoke requires --create-split or --split-manifest")
    sessions = sorted({str(frame["session"].iloc[0]) for frame in frames})
    if len(sessions) < 3:
        raise OosSplitError("rule filter smoke requires at least three sessions")
    train_end = max(1, int(len(sessions) * 0.6))
    validation_end = max(train_end + 1, int(len(sessions) * 0.8))
    validation_end = min(validation_end, len(sessions) - 1)
    symbol_sessions: dict[str, list[str]] = {}
    for frame in frames:
        symbol = str(frame["symbol"].iloc[0])
        symbol_sessions.setdefault(symbol, []).append(str(frame["session"].iloc[0]))
    return build_oos_split_manifest(
        {
            "train": sessions[:train_end],
            "validation": sessions[train_end:validation_end],
            "oos": sessions[validation_end:],
        },
        symbol_sessions=symbol_sessions,
        output_path=output_dir / "opening_rule_filter_split_manifest.json",
    )


def _controls(policy: dict[str, object], dataset: dict[str, object], config: RuleFilterConfig, split_hash: str) -> dict[str, object]:
    rows = _rows(dataset)
    oos_rows = [row for row in rows if str(row.get("split")) == "oos"]
    threshold = _threshold(policy)
    filter_return = float(policy["oos_metrics"]["net_return_pct"])
    return build_rule_filter_control_artifact(
        filter_oos_net_return_pct=filter_return,
        baseline_returns={
            "no_trade": 0.0,
            "buy_and_hold": _buy_and_hold_return(oos_rows),
            "ts_imb_rule": _ts_imb_return(oos_rows),
        },
        split_hash=split_hash,
        cost_bps=config.cost_bps,
        shuffled_label_return_pct=float(evaluate_rule_filter_metrics(_shuffled_returns(oos_rows), threshold, feature_set_id=config.feature_set_id)["net_return_pct"]),
        time_session_shuffle_return_pct=float(evaluate_rule_filter_metrics(_rotated_features(oos_rows), threshold, feature_set_id=config.feature_set_id)["net_return_pct"]),
        randomized_feature_return_pct=float(evaluate_rule_filter_metrics(_randomized_features(oos_rows), threshold, feature_set_id=config.feature_set_id)["net_return_pct"]),
    )


def _ablations(policy: dict[str, object], dataset: dict[str, object], config: RuleFilterConfig, split_hash: str) -> dict[str, object]:
    rows = _rows(dataset)
    full = float(policy["oos_metrics"]["net_return_pct"])
    return build_rule_filter_ablation_artifact(
        full_context_return_pct=full,
        ablation_returns=build_rule_filter_ablation_returns(rows, config, split_hash),
        split_hash=split_hash,
    )


def _gate(policy: dict[str, object], dataset: dict[str, object], controls: dict[str, object], ablations: dict[str, object], config: RuleFilterConfig, split_hash: str) -> dict[str, object]:
    oos = policy["oos_metrics"]
    control_rows = {str(row["control_type"]): row for row in controls.get("controls", []) if isinstance(row, dict)}
    return evaluate_rule_filter_gate(
        RuleFilterGateInput(
            split_hash=split_hash,
            cost_bps=config.cost_bps,
            validation_net_return_pct=float(policy["validation_metrics"]["net_return_pct"]),
            oos_net_return_pct=float(oos["net_return_pct"]),
            no_trade_net_return_pct=float(control_rows.get("no_trade", {}).get("control_net_return_pct", 0.0)),
            buy_and_hold_net_return_pct=float(control_rows.get("buy_and_hold", {}).get("control_net_return_pct", 0.0)),
            ts_imb_rule_net_return_pct=float(control_rows.get("ts_imb_rule", {}).get("control_net_return_pct", 0.0)),
            controls_passed=bool(controls["negative_control_passed"]),
            ablations_passed=bool(ablations["feature_ablation_passed"]),
            oos_take_count=int(oos["take_count"]),
            min_oos_take_count=int(config.min_oos_take_trades),
            max_drawdown_pct=_max_drawdown_pct(_taken_oos_returns(policy, dataset)),
            max_allowed_drawdown_pct=float(config.max_drawdown_pct),
            skipped_opportunity_cost_pct=float(oos["skipped_opportunity_cost_pct"]),
        )
    )


def _rows(dataset: Mapping[str, object]) -> list[dict[str, Any]]:
    return [dict(row) for row in dataset.get("rows", []) if isinstance(row, dict)]


def _threshold(policy: Mapping[str, object]) -> dict[str, float]:
    raw = policy.get("selected_thresholds", {})
    return {str(key): float(value) for key, value in raw.items()} if isinstance(raw, dict) else {}


def _copy_row(row: Mapping[str, Any], features: Mapping[str, Any] | None = None, base_return: float | None = None) -> dict[str, Any]:
    copied = dict(row)
    copied["feature_values"] = dict(features if features is not None else row.get("feature_values", {}))
    if base_return is not None:
        copied["base_net_return_pct"] = float(base_return)
        copied["skipped_opportunity_net_return_pct"] = float(base_return) if str(copied.get("base_action")) == "TAKE" else 0.0
    return copied


def _rotate(values: list[Any]) -> list[Any]:
    return values[1:] + values[:1] if len(values) > 1 else values


def _shuffled_returns(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    returns = _rotate([float(row.get("base_net_return_pct", 0.0)) for row in rows])
    return [_copy_row(row, base_return=returns[index]) for index, row in enumerate(rows)]


def _rotated_features(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    feature_sets = _rotate([dict(row.get("feature_values", {})) for row in rows])
    return [_copy_row(row, features=feature_sets[index]) for index, row in enumerate(rows)]


def _randomized_features(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [_copy_row(row, features={key: _pseudo_unit(str(row.get("episode_id", "")) + key) for key in dict(row.get("feature_values", {}))}) for row in rows]


def _pseudo_unit(seed: str) -> float:
    return (sum((idx + 1) * ord(ch) for idx, ch in enumerate(seed)) % 1000) / 1000.0


def _ts_imb_return(rows: Sequence[Mapping[str, Any]]) -> float:
    return sum(float(row.get("base_net_return_pct", 0.0)) for row in rows)


def _buy_and_hold_return(rows: Sequence[Mapping[str, Any]]) -> float:
    return sum(float(row.get("base_net_return_pct", 0.0)) for row in rows if str(row.get("base_action")) == "TAKE")


def _taken_oos_returns(policy: Mapping[str, object], dataset: Mapping[str, object]) -> list[float]:
    actions = policy.get("actions_by_episode", {})
    action_map = actions if isinstance(actions, dict) else {}
    returns: list[float] = []
    for row in _rows(dataset):
        if str(row.get("split")) == "oos" and str(action_map.get(str(row.get("episode_id")))) == "TAKE":
            returns.append(float(row.get("base_net_return_pct", 0.0)))
    return returns


def _max_drawdown_pct(returns: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in returns:
        equity += float(value)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


if __name__ == "__main__":
    raise SystemExit(main())
