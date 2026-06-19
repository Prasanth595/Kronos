"""Daily OHLCV prediction baselines and transparent supervised rankers.

D3 is a research evidence step.  It consumes D2 dataset artifacts, evaluates
explicit baselines before any RL work, and emits WATCH/NO-GO-ready artifacts.
It does not place orders, tune on OOS data, or claim profitability.
"""

from __future__ import annotations

import csv
import json
import hashlib
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .daily_ohlcv_dataset import DEFAULT_DATASET_ROOT, DEFAULT_FEATURE_COLUMNS, DEFAULT_LABEL_COLUMNS
from .daily_ohlcv_db import PRICE_BASIS, PRICE_BASIS_EVIDENCE, REPO_ROOT
from .daily_ranker import fit_direction_classifier, fit_linear_ranker, score_direction_probability, score_row

DEFAULT_PREDICTION_ROOT = REPO_ROOT / "webui" / "rl_runs" / "daily_ohlcv_prediction"
PREDICTION_SCHEMA_VERSION = 1
ROUND_TRIP_COST_BP = 23
ROUND_TRIP_COST_RATE = ROUND_TRIP_COST_BP / 10_000.0
SAFE_RUN_RE = re.compile(r"^[0-9A-Za-z_.-]+$")
BASELINE_STRATEGIES = [
    "no_trade_cash",
    "shuffle_control",
    "equal_weight_topk_momentum",
    "vol_adjusted_momentum",
    "mean_reversion",
    "market_proxy",
    "supervised_linear_ranker",
    "supervised_direction_classifier",
]
CONTROL_STRATEGIES = {"no_trade_cash", "shuffle_control"}
RULE_BASELINE_STRATEGIES = {
    "equal_weight_topk_momentum",
    "vol_adjusted_momentum",
    "mean_reversion",
    "market_proxy",
}
SUPERVISED_STRATEGIES = {"supervised_linear_ranker", "supervised_direction_classifier"}
PRICE_BASIS_VERIFIED_STATUSES = {"VERIFIED", "RAW_VERIFIED", "ADJUSTED_VERIFIED", "PRICE_BASIS_VERIFIED"}
PRICE_BASIS_VERIFIED_VALUES = {"raw", "adjusted", "split_adjusted", "total_return_adjusted"}
D3_REQUIRED_EVIDENCE = [
    "frozen_dataset_manifest_sha",
    "train_only_supervised_fit",
    "deterministic_shuffle_control",
    "no_trade_cash_control",
    "rule_topk_baselines",
    "supervised_ranker_classifier_baselines",
    "23bp_cost_net_metrics",
    "val_test_evaluation_splits",
    "mdd_turnover_hit_rate_deltas",
]
D3_ALLOWED_USES_WHEN_WATCH = [
    "baseline_comparison_for_research",
    "feature_and_ranker_diagnostics",
    "d4_rl_design_reference",
]
D3_BLOCKED_USES_WHEN_WATCH = [
    "model_build_or_candidate_promotion",
    "go_summary_or_profit_claim",
    "paper_forward_or_live_readiness_claims",
]
D3_USER_GUIDANCE = [
    {
        "section": "D3 summary",
        "meaning": "D3 compares no-trade, deterministic shuffle, rule Top-K, market proxy, and supervised baselines after 23bp cost.",
        "action": "Use it to decide whether an RL experiment has a strong enough frozen baseline to beat.",
    },
    {
        "section": "Promotion lock",
        "meaning": "D3 WATCH evidence is not a model-build or GO summary approval.",
        "action": "Keep model_build_allowed=false until D0/D1 evidence and D5 walk-forward gates pass.",
    },
    {
        "section": "Controls",
        "meaning": "Shuffle/no-trade/rule baselines and MDD/turnover/hit-rate deltas are required context.",
        "action": "Treat any model that fails these controls as research-only or NO-GO.",
    },
]



def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any) -> bool:
    return value in {True, 1, "1", "true", "True", "TRUE"}


def _validate_run_id(run_id: str) -> str:
    rid = str(run_id or "").strip()
    if not SAFE_RUN_RE.match(rid) or rid in {".", ".."} or ".." in rid.split("."):
        raise ValueError("run_id contains unsafe characters")
    return rid


def _latest_run_dir(root: Path, required_file: str) -> Path:
    candidates = sorted(root.glob(f"*/{required_file}"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No {required_file} found under {root}")
    return candidates[0].parent


def _resolve_dataset_run(dataset_run_dir: Path | str | None = None) -> Path:
    if dataset_run_dir is not None:
        run_dir = Path(dataset_run_dir).resolve()
        root = DEFAULT_DATASET_ROOT.resolve()
        run_dir.relative_to(root)
        if not (run_dir / "dataset_manifest.json").exists():
            raise FileNotFoundError(run_dir / "dataset_manifest.json")
        return run_dir
    return _latest_run_dir(DEFAULT_DATASET_ROOT, "dataset_manifest.json")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fallback_fields: list[str]) -> None:
    fields = sorted({key for row in rows for key in row.keys()}) if rows else fallback_fields
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if value in (None, ""):
        return []
    return [str(value)]


def _unique_strings(*groups: Any) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for item in _string_list(group):
            if item not in merged:
                merged.append(item)
    return merged


def _d3_gate_blockers(dataset_manifest: dict[str, Any]) -> list[str]:
    blockers = _string_list(dataset_manifest.get("upstream_gate_blockers"))
    price_basis = str(dataset_manifest.get("price_basis") or PRICE_BASIS).lower()
    price_status = str(dataset_manifest.get("price_basis_status") or "").upper()
    decision_status = str(dataset_manifest.get("decision_grade_return_status") or "")
    if (
        "D0_PRICE_BASIS_NOT_VERIFIED" not in blockers
        and (price_basis not in PRICE_BASIS_VERIFIED_VALUES or price_status not in PRICE_BASIS_VERIFIED_STATUSES or decision_status.startswith("BLOCKED"))
    ):
        blockers.append("D0_PRICE_BASIS_NOT_VERIFIED")
    universe_verdict = str(dataset_manifest.get("universe_verdict") or "")
    universe_review = str(dataset_manifest.get("universe_review_status") or "")
    official_status = str(dataset_manifest.get("official_metadata_status") or "")
    coverage_status = str(dataset_manifest.get("official_metadata_coverage_status") or "")
    certification_status = str(dataset_manifest.get("universe_certification_status") or "")
    if (
        "D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED" not in blockers
        and (
            universe_verdict != "OFFICIAL_OR_MANUAL_REVIEWED"
            or universe_review != "OFFICIAL_OR_MANUAL_REVIEWED"
            or official_status != "OFFICIAL_VERIFIED"
            or coverage_status != "COMPLETE"
            or certification_status != "OFFICIAL_OR_MANUAL_REVIEWED"
        )
    ):
        blockers.append("D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED")
    blockers.append("D5_WALK_FORWARD_NOT_PASS")
    return _unique_strings(blockers)


def load_dataset_rows(dataset_run_dir: Path | str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run_dir = _resolve_dataset_run(dataset_run_dir)
    manifest = _read_json(run_dir / "dataset_manifest.json")
    features = _read_csv(run_dir / "feature_panel.csv")
    labels = _read_csv(run_dir / "label_panel.csv")
    splits = _read_csv(run_dir / "split_assignments.csv")
    labels_by_key = {(row["date"], row["table"]): row for row in labels}
    splits_by_key = {(row["date"], row["table"]): row for row in splits}
    rows: list[dict[str, Any]] = []
    for feature in features:
        key = (feature["date"], feature["table"])
        label = labels_by_key.get(key, {})
        split = splits_by_key.get(key, {})
        merged = {**feature, **label, **split}
        merged["code"] = str(merged.get("code") or feature.get("code") or "").zfill(6)
        merged["eligible_for_training"] = _safe_bool(merged.get("eligible_for_training"))
        rows.append(merged)
    return manifest, rows


def _eligible_rows(rows: Iterable[dict[str, Any]], *, include_train: bool = True) -> list[dict[str, Any]]:
    allowed_splits = {"train", "val", "test"} if include_train else {"val", "test"}
    return [
        row
        for row in rows
        if row.get("split") in allowed_splits
        and row.get("eligible_for_training") is True
        and _safe_float(row.get("future_return_1d")) is not None
    ]


def _score_predictions(rows: list[dict[str, Any]], feature_columns: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    train_rows = [row for row in rows if str(row.get("split")) == "train"]
    ranker = fit_linear_ranker(train_rows, feature_columns=feature_columns, target_column="future_return_1d")
    classifier = fit_direction_classifier(train_rows, feature_columns=feature_columns, target_column="future_direction_1d")
    predictions: list[dict[str, Any]] = []
    for row in rows:
        ret_5d = _safe_float(row.get("return_5d"))
        vol = _safe_float(row.get("volatility_5d"))
        vol_adj = None if ret_5d is None else ret_5d / max(abs(vol or 0.0), 1e-9)
        supervised_score = score_row(ranker, row)
        direction_probability = score_direction_probability(classifier, row)
        predictions.append(
            {
                "date": row.get("date"),
                "table": row.get("table"),
                "code": str(row.get("code") or "").zfill(6),
                "split": row.get("split"),
                "future_return_1d": _safe_float(row.get("future_return_1d")),
                "future_direction_1d": _safe_float(row.get("future_direction_1d")),
                "score_equal_weight_topk_momentum": ret_5d,
                "score_vol_adjusted_momentum": vol_adj,
                "score_mean_reversion": None if ret_5d is None else -ret_5d,
                "score_market_proxy": 0.0,
                "score_supervised_linear_ranker": supervised_score,
                "score_supervised_direction_classifier": direction_probability,
            }
        )
    return predictions, ranker.to_dict(), classifier.to_dict()


def _group_by_date(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("date"))].append(row)
    return dict(sorted(grouped.items()))


def _strategy_family(strategy: str) -> str:
    if strategy in CONTROL_STRATEGIES:
        return "control"
    if strategy in SUPERVISED_STRATEGIES:
        return "supervised"
    return "rule_baseline"


def _select_for_strategy(strategy: str, rows: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    if strategy == "no_trade_cash":
        return []
    if strategy == "market_proxy":
        return list(rows)
    if strategy == "shuffle_control":
        return sorted(
            rows,
            key=lambda row: hashlib.sha256(f"{row.get('date')}:{row.get('code')}".encode("utf-8")).hexdigest(),
        )[:top_k]
    score_column = {
        "equal_weight_topk_momentum": "score_equal_weight_topk_momentum",
        "vol_adjusted_momentum": "score_vol_adjusted_momentum",
        "mean_reversion": "score_mean_reversion",
        "supervised_linear_ranker": "score_supervised_linear_ranker",
        "supervised_direction_classifier": "score_supervised_direction_classifier",
    }[strategy]
    scored = [row for row in rows if _safe_float(row.get(score_column)) is not None]
    return sorted(scored, key=lambda row: float(row[score_column]), reverse=True)[:top_k]


def _max_drawdown(equity: list[float]) -> float:
    peak = 1.0
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak:
            max_dd = min(max_dd, value / peak - 1.0)
    return max_dd


def evaluate_strategy(
    predictions: list[dict[str, Any]],
    *,
    strategy: str,
    top_k: int = 20,
    cost_rate: float = ROUND_TRIP_COST_RATE,
    splits: Iterable[str] = ("val", "test"),
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    eval_rows = [row for row in predictions if row.get("split") in set(splits)]
    grouped = _group_by_date(eval_rows)
    daily_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    turnover_rows: list[dict[str, Any]] = []
    previous_codes: set[str] = set()
    equity = 1.0
    equity_curve: list[float] = []
    for date, rows in grouped.items():
        selected = _select_for_strategy(strategy, rows, top_k=top_k)
        selected_codes = {str(row["code"]) for row in selected}
        if strategy == "no_trade_cash":
            turnover = 0.0
            gross = 0.0
        elif strategy == "market_proxy":
            # Conservative proxy accounting: this is a daily equal-weight market
            # proxy, not a buy-and-hold index. Charge one full round-trip cost
            # per rebalance day so a broad proxy cannot become the "best" row
            # simply because turnover was under-counted.
            turnover = 1.0 if selected else 0.0
            returns = [_safe_float(row.get("future_return_1d")) for row in selected]
            clean = [value for value in returns if value is not None]
            gross = sum(clean) / len(clean) if clean else 0.0
        else:
            denom = max(1, top_k)
            overlap = len(selected_codes & previous_codes)
            turnover = 1.0 if not previous_codes else max(0.0, min(1.0, 1.0 - overlap / denom))
            returns = [_safe_float(row.get("future_return_1d")) for row in selected]
            clean = [value for value in returns if value is not None]
            gross = sum(clean) / len(clean) if clean else 0.0
        net = gross - turnover * cost_rate
        equity *= 1.0 + net
        equity_curve.append(equity)
        daily_rows.append(
            {
                "strategy": strategy,
                "date": date,
                "split": "+".join(sorted(set(str(row.get("split")) for row in rows))),
                "selected_count": len(selected),
                "gross_return": gross,
                "net_return": net,
                "turnover": turnover,
                "equity": equity,
            }
        )
        turnover_rows.append({"strategy": strategy, "date": date, "turnover": turnover, "selected_count": len(selected)})
        for rank, row in enumerate(selected, start=1):
            position_rows.append(
                {
                    "strategy": strategy,
                    "date": date,
                    "rank": rank,
                    "code": row.get("code"),
                    "split": row.get("split"),
                    "future_return_1d": row.get("future_return_1d"),
                }
            )
        previous_codes = selected_codes
    net_returns = [float(row["net_return"]) for row in daily_rows]
    gross_returns = [float(row["gross_return"]) for row in daily_rows]
    metrics = {
        "strategy": strategy,
        "strategy_family": _strategy_family(strategy),
        "is_control": strategy in CONTROL_STRATEGIES,
        "is_shuffle_control": strategy == "shuffle_control",
        "is_supervised": strategy in SUPERVISED_STRATEGIES,
        "splits": list(splits),
        "top_k": top_k,
        "cost_round_trip_bp": ROUND_TRIP_COST_BP,
        "trade_days": len(daily_rows),
        "positions": len(position_rows),
        "mean_daily_gross_return": sum(gross_returns) / len(gross_returns) if gross_returns else 0.0,
        "mean_daily_net_return": sum(net_returns) / len(net_returns) if net_returns else 0.0,
        "total_net_return": equity - 1.0,
        "hit_rate": sum(1 for value in net_returns if value > 0) / len(net_returns) if net_returns else 0.0,
        "max_drawdown": _max_drawdown(equity_curve),
        "mean_turnover": sum(row["turnover"] for row in turnover_rows) / len(turnover_rows) if turnover_rows else 0.0,
    }
    return position_rows, metrics, daily_rows, turnover_rows


def _best_metric(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return max(rows, key=lambda row: row["total_net_return"]) if rows else None


def _metric_delta(left: dict[str, Any] | None, right: dict[str, Any] | None) -> float | None:
    if left is None or right is None:
        return None
    return float(left["total_net_return"]) - float(right["total_net_return"])


def _baseline_metrics(
    predictions: list[dict[str, Any]],
    *,
    top_k: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    positions: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    drawdown_rows: list[dict[str, Any]] = []
    turnover_rows: list[dict[str, Any]] = []
    for strategy in BASELINE_STRATEGIES:
        p, metric, daily, turnover = evaluate_strategy(predictions, strategy=strategy, top_k=top_k)
        positions.extend(p)
        metrics.append(metric)
        drawdown_rows.extend({"strategy": row["strategy"], "date": row["date"], "equity": row["equity"], "net_return": row["net_return"]} for row in daily)
        turnover_rows.extend(turnover)

    cash = next((row for row in metrics if row["strategy"] == "no_trade_cash"), None)
    shuffle = next((row for row in metrics if row["strategy"] == "shuffle_control"), None)
    control = [row for row in metrics if row.get("strategy_family") == "control"]
    rule_baselines = [row for row in metrics if row.get("strategy_family") == "rule_baseline"]
    supervised = [row for row in metrics if row.get("strategy_family") == "supervised"]
    best_control = _best_metric(control)
    best_rule_baseline = _best_metric(rule_baselines)
    best_supervised = _best_metric(supervised)
    best_overall = _best_metric(metrics)

    for metric in metrics:
        metric["delta_vs_cash_total_net_return"] = _metric_delta(metric, cash)
        metric["delta_vs_shuffle_control_total_net_return"] = _metric_delta(metric, shuffle)
        metric["delta_vs_best_rule_baseline_total_net_return"] = _metric_delta(metric, best_rule_baseline)

    baseline_delta_summary = {
        "status": "WATCH",
        "cost_round_trip_bp": ROUND_TRIP_COST_BP,
        "top_k": top_k,
        "evaluation_splits": ["val", "test"],
        "control_strategies": [strategy for strategy in BASELINE_STRATEGIES if strategy in CONTROL_STRATEGIES],
        "rule_baseline_strategies": [strategy for strategy in BASELINE_STRATEGIES if strategy in RULE_BASELINE_STRATEGIES],
        "supervised_strategies": [strategy for strategy in BASELINE_STRATEGIES if strategy in SUPERVISED_STRATEGIES],
        "best_overall_strategy": best_overall.get("strategy") if best_overall else None,
        "best_control_strategy": best_control.get("strategy") if best_control else None,
        "best_rule_baseline_strategy": best_rule_baseline.get("strategy") if best_rule_baseline else None,
        "best_supervised_strategy": best_supervised.get("strategy") if best_supervised else None,
        "shuffle_control_strategy": shuffle.get("strategy") if shuffle else None,
        "best_supervised_delta_vs_best_rule_baseline": _metric_delta(best_supervised, best_rule_baseline),
        "best_supervised_delta_vs_shuffle_control": _metric_delta(best_supervised, shuffle),
        "best_rule_delta_vs_shuffle_control": _metric_delta(best_rule_baseline, shuffle),
        "best_overall_delta_vs_shuffle_control": _metric_delta(best_overall, shuffle),
        "model_build_allowed": False,
    }
    return positions, metrics, drawdown_rows, turnover_rows, baseline_delta_summary


def _calibration_rows(predictions: list[dict[str, Any]], *, bins: int = 5) -> list[dict[str, Any]]:
    rows = [row for row in predictions if row.get("split") in {"val", "test"} and _safe_float(row.get("score_supervised_direction_classifier")) is not None]
    if not rows:
        return []
    sorted_rows = sorted(rows, key=lambda row: float(row["score_supervised_direction_classifier"]))
    out: list[dict[str, Any]] = []
    for bin_index in range(bins):
        start = int(len(sorted_rows) * bin_index / bins)
        end = int(len(sorted_rows) * (bin_index + 1) / bins)
        chunk = sorted_rows[start:end]
        if not chunk:
            continue
        probs = [float(row["score_supervised_direction_classifier"]) for row in chunk]
        labels = [_safe_float(row.get("future_direction_1d")) or 0.0 for row in chunk]
        out.append(
            {
                "bin": bin_index + 1,
                "count": len(chunk),
                "mean_probability": sum(probs) / len(probs),
                "realized_positive_rate": sum(labels) / len(labels),
            }
        )
    return out


def run_daily_prediction(
    *,
    dataset_run_dir: Path | str | None = None,
    top_k: int = 20,
) -> dict[str, Any]:
    dataset_manifest, rows = load_dataset_rows(dataset_run_dir)
    feature_columns = [str(col) for col in dataset_manifest.get("feature_columns") or DEFAULT_FEATURE_COLUMNS]
    label_columns = [str(col) for col in dataset_manifest.get("label_columns") or DEFAULT_LABEL_COLUMNS]
    if any(col in label_columns or col.startswith(("future_", "label_", "target_")) for col in feature_columns):
        raise ValueError("Feature columns contain future/label leakage")
    eligible = _eligible_rows(rows, include_train=True)
    top_k_value = max(1, int(top_k))
    predictions, ranker_model, classifier_model = _score_predictions(eligible, feature_columns)
    positions, metrics, drawdown_rows, turnover_rows, baseline_delta_summary = _baseline_metrics(predictions, top_k=top_k_value)
    calibration = _calibration_rows(predictions)
    best_strategy = max(metrics, key=lambda row: row["total_net_return"]) if metrics else None
    dataset_run_path = _resolve_dataset_run(dataset_run_dir)
    d3_gate_blockers = _unique_strings(_d3_gate_blockers(dataset_manifest), ["D3_BASELINE_WATCH_RESEARCH_ONLY"])
    baseline_delta_summary.update(
        {
            "readiness_status": "D3_WATCH_RESEARCH_ONLY",
            "go_summary_allowed": False,
            "model_build_allowed": False,
            "d3_gate_blockers": d3_gate_blockers,
            "required_evidence": list(D3_REQUIRED_EVIDENCE),
            "allowed_uses": list(D3_ALLOWED_USES_WHEN_WATCH),
            "blocked_uses": list(D3_BLOCKED_USES_WHEN_WATCH),
            "deterministic_shuffle_method": "sha256(date:code)_ascending",
        }
    )
    verdict_reasons = _unique_strings(
        [
            "RESEARCH_ONLY_NO_PROFIT_LIVE_BROKER_ORDER_CLAIM",
            "PRICE_BASIS_UNKNOWN",
            "UNIVERSE_WATCH_HEURISTIC",
        ],
        d3_gate_blockers,
    )
    verdict = {
        "schema_version": PREDICTION_SCHEMA_VERSION,
        "status": "WATCH",
        "readiness_status": "D3_WATCH_RESEARCH_ONLY",
        "go_summary_allowed": False,
        "model_build_allowed": False,
        "reasons": verdict_reasons,
        "d3_gate_blockers": d3_gate_blockers,
        "best_strategy_by_total_net_return": best_strategy.get("strategy") if best_strategy else None,
        "requires_before_rl_go": ["D5 walk-forward", "shuffle controls", "cost sensitivity", "official/manual universe review", "price-basis verification"],
        "baseline_delta_summary": baseline_delta_summary,
        "blocked_uses": list(D3_BLOCKED_USES_WHEN_WATCH),
    }
    manifest = {
        "schema_version": PREDICTION_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "guardrail": "Research-only D3 prediction/baseline evidence; no profit guarantee, no live/broker/orders, no trained-RL readiness claim.",
        "status": "WATCH",
        "readiness_status": "D3_WATCH_RESEARCH_ONLY",
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "dataset_run_dir": str(dataset_run_path),
        "dataset_run_id": dataset_run_path.name,
        "dataset_manifest_sha": dataset_manifest.get("manifest_sha"),
        "dataset_artifact_scope": dataset_manifest.get("artifact_scope"),
        "dataset_model_readiness": dataset_manifest.get("model_readiness"),
        "dataset_decision_grade_status": dataset_manifest.get("decision_grade_status"),
        "dataset_upstream_gate_blockers": _string_list(dataset_manifest.get("upstream_gate_blockers")),
        "dataset_row_counts": dataset_manifest.get("row_counts") or {},
        "dataset_split_summary": dataset_manifest.get("split_summary") or {},
        "price_basis": dataset_manifest.get("price_basis") or PRICE_BASIS,
        "price_basis_evidence": dataset_manifest.get("price_basis_evidence") or PRICE_BASIS_EVIDENCE,
        "price_basis_status": dataset_manifest.get("price_basis_status"),
        "decision_grade_return_status": dataset_manifest.get("decision_grade_return_status"),
        "universe_verdict": dataset_manifest.get("universe_verdict"),
        "universe_review_status": dataset_manifest.get("universe_review_status"),
        "official_metadata_status": dataset_manifest.get("official_metadata_status"),
        "official_metadata_coverage_status": dataset_manifest.get("official_metadata_coverage_status"),
        "universe_certification_status": dataset_manifest.get("universe_certification_status"),
        "feature_columns": feature_columns,
        "label_columns": label_columns,
        "top_k": top_k_value,
        "cost_assumption_round_trip_bp": ROUND_TRIP_COST_BP,
        "no_oos_retuning": True,
        "fit_split": "train",
        "evaluation_splits": ["val", "test"],
        "baseline_freeze_contract": {
            "frozen_dataset_manifest_sha": dataset_manifest.get("manifest_sha"),
            "dataset_run_id": dataset_run_path.name,
            "feature_columns": feature_columns,
            "label_columns": label_columns,
            "fit_split": "train",
            "evaluation_splits": ["val", "test"],
            "cost_round_trip_bp": ROUND_TRIP_COST_BP,
            "top_k": top_k_value,
            "deterministic_shuffle_method": "sha256(date:code)_ascending",
            "strategies": list(BASELINE_STRATEGIES),
            "no_oos_retuning": True,
        },
        "d3_gate_blockers": d3_gate_blockers,
        "d3_required_evidence": list(D3_REQUIRED_EVIDENCE),
        "d3_allowed_uses": list(D3_ALLOWED_USES_WHEN_WATCH),
        "d3_blocked_uses": list(D3_BLOCKED_USES_WHEN_WATCH),
        "d3_user_guidance": [dict(row) for row in D3_USER_GUIDANCE],
        "row_counts": {
            "eligible_rows": len(eligible),
            "prediction_rows": len(predictions),
            "position_rows": len(positions),
        },
        "models": {
            "supervised_linear_ranker": ranker_model,
            "supervised_direction_classifier": classifier_model,
        },
        "baseline_strategies": BASELINE_STRATEGIES,
        "baseline_delta_summary": baseline_delta_summary,
        "verdict": verdict,
    }
    return {
        "manifest": manifest,
        "predictions": predictions,
        "topk_positions": positions,
        "baseline_metrics": metrics,
        "model_metrics": [row for row in metrics if row["strategy"].startswith("supervised_")],
        "calibration": calibration,
        "turnover": turnover_rows,
        "drawdown": drawdown_rows,
        "verdict": verdict,
        "baseline_delta_summary": baseline_delta_summary,
    }


def write_prediction_artifacts(
    result: dict[str, Any],
    *,
    run_id: str | None = None,
    artifact_root: Path | str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    root = Path(artifact_root or DEFAULT_PREDICTION_ROOT).resolve()
    default_root = DEFAULT_PREDICTION_ROOT.resolve()
    try:
        root.relative_to(default_root)
    except ValueError:
        if root != default_root:
            raise ValueError("Daily OHLCV prediction artifacts must stay under webui/rl_runs/daily_ohlcv_prediction")
    rid = _validate_run_id(run_id or f"prediction_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    out_dir = (root / rid).resolve()
    out_dir.relative_to(root)
    if out_dir.exists() and any(out_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"Prediction artifact run_id already exists: {rid}")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "prediction_manifest": out_dir / "prediction_manifest.json",
        "baseline_metrics": out_dir / "baseline_metrics.json",
        "baseline_delta_summary": out_dir / "baseline_delta_summary.json",
        "model_metrics": out_dir / "model_metrics.json",
        "topk_positions": out_dir / "topk_positions.csv",
        "calibration": out_dir / "calibration.csv",
        "turnover": out_dir / "turnover.csv",
        "drawdown": out_dir / "drawdown.csv",
        "predictions": out_dir / "predictions.csv",
        "verdict": out_dir / "verdict.json",
    }
    manifest = {**result["manifest"], "run_id": rid, "artifact_dir": str(out_dir), "artifacts": {key: str(path) for key, path in paths.items()}}
    _write_json(paths["baseline_metrics"], {"metrics": result["baseline_metrics"]})
    _write_json(paths["baseline_delta_summary"], result["baseline_delta_summary"])
    _write_json(paths["model_metrics"], {"models": manifest["models"], "metrics": result["model_metrics"]})
    _write_json(paths["verdict"], result["verdict"])
    _write_csv(paths["topk_positions"], result["topk_positions"], ["strategy", "date", "rank", "code", "split", "future_return_1d"])
    _write_csv(paths["calibration"], result["calibration"], ["bin", "count", "mean_probability", "realized_positive_rate"])
    _write_csv(paths["turnover"], result["turnover"], ["strategy", "date", "turnover", "selected_count"])
    _write_csv(paths["drawdown"], result["drawdown"], ["strategy", "date", "equity", "net_return"])
    _write_csv(paths["predictions"], result["predictions"], ["date", "table", "code", "split", "future_return_1d"])
    artifact_hashes = {
        key: _file_sha256(path)
        for key, path in paths.items()
        if key != "prediction_manifest"
    }
    manifest["artifact_hashes"] = artifact_hashes
    _write_json(paths["prediction_manifest"], manifest)
    manifest_sha = _file_sha256(paths["prediction_manifest"])
    return {
        "run_id": rid,
        "artifact_dir": str(out_dir),
        "prediction_manifest_sha256": manifest_sha,
        "artifact_hashes": {**artifact_hashes, "prediction_manifest": manifest_sha},
        **{f"{key}_path": str(path) for key, path in paths.items()},
    }


def run_and_write_daily_prediction(
    *,
    run_id: str | None = None,
    artifact_root: Path | str | None = None,
    overwrite: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    result = run_daily_prediction(**kwargs)
    written = write_prediction_artifacts(result, run_id=run_id, artifact_root=artifact_root, overwrite=overwrite)
    return {"result": result, "written": written}


__all__ = [
    "BASELINE_STRATEGIES",
    "DEFAULT_PREDICTION_ROOT",
    "PREDICTION_SCHEMA_VERSION",
    "ROUND_TRIP_COST_BP",
    "D3_ALLOWED_USES_WHEN_WATCH",
    "D3_BLOCKED_USES_WHEN_WATCH",
    "D3_REQUIRED_EVIDENCE",
    "D3_USER_GUIDANCE",
    "evaluate_strategy",
    "load_dataset_rows",
    "run_and_write_daily_prediction",
    "run_daily_prediction",
    "write_prediction_artifacts",
]
