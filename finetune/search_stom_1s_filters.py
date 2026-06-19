"""Search prediction-time STOM 1s score filters for Top-K diagnostics."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if np.isnan(result) or np.isinf(result):
        return default
    return result


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer, np.floating)):
        return _json_safe(value.item())
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    return value


@dataclass(frozen=True)
class FilterSpec:
    min_pred_return: float
    min_consistency: float
    max_pred_range: Optional[float]
    min_amount_quantile: float
    max_volatility: Optional[float]

    @property
    def name(self) -> str:
        range_part = "none" if self.max_pred_range is None else f"{self.max_pred_range:g}"
        vol_part = "none" if self.max_volatility is None else f"{self.max_volatility:g}"
        return (
            f"ret>={self.min_pred_return:g}|cons>={self.min_consistency:g}|"
            f"range<={range_part}|amt_q>={self.min_amount_quantile:g}|vol<={vol_part}"
        )


BASELINE_SPEC = FilterSpec(-999.0, 0.0, None, 0.0, None)


def generate_filter_specs() -> List[FilterSpec]:
    return [
        FilterSpec(*values)
        for values in product(
            [-0.10, -0.05, 0.0, 0.02, 0.05, 0.10],
            [0.0, 0.50, 0.60, 0.70, 0.80],
            [None, 0.05, 0.10, 0.20, 0.50, 1.00],
            [0.0, 0.25, 0.50, 0.75],
            [None, 0.05, 0.10, 0.20, 0.50, 1.00],
        )
    ]


def _spec_from_row(row: Mapping[str, Any]) -> FilterSpec:
    def optional_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        if np.isnan(result) or np.isinf(result):
            return None
        return result

    return FilterSpec(
        min_pred_return=_safe_float(row.get("min_pred_return")),
        min_consistency=_safe_float(row.get("min_consistency")),
        max_pred_range=optional_float(row.get("max_pred_range")),
        min_amount_quantile=_safe_float(row.get("min_amount_quantile")),
        max_volatility=optional_float(row.get("max_volatility")),
    )


def _latest_windows(df: pd.DataFrame) -> pd.DataFrame:
    required = {"window_id", "asof_timestamp", "pred_return_window", "actual_return_window"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Prediction CSV missing required columns: {missing}")

    latest = df.sort_values(["window_id", "horizon_step" if "horizon_step" in df.columns else "target_timestamp"])
    latest = latest.groupby("window_id", sort=False).tail(1).copy()
    latest["asof_timestamp"] = pd.to_datetime(latest["asof_timestamp"], errors="coerce")
    numeric_defaults = {
        "pred_return_window": 0.0,
        "actual_return_window": 0.0,
        "direction_hit_window": 0.0,
        "pred_path_consistency": 0.0,
        "pred_range_pct": 0.0,
        "history_mean_amount": 0.0,
        "history_volatility_pct": 0.0,
    }
    for column, default in numeric_defaults.items():
        if column not in latest.columns:
            latest[column] = default
        latest[column] = pd.to_numeric(latest[column], errors="coerce").fillna(default)
    return latest


def _selected_rows(latest: pd.DataFrame, spec: FilterSpec, top_k: int) -> pd.DataFrame:
    amount_threshold = float(latest["history_mean_amount"].quantile(spec.min_amount_quantile))
    mask = (
        (latest["pred_return_window"] >= spec.min_pred_return)
        & (latest["pred_path_consistency"] >= spec.min_consistency)
        & (latest["history_mean_amount"] >= amount_threshold)
    )
    if spec.max_pred_range is not None:
        mask &= latest["pred_range_pct"] <= spec.max_pred_range
    if spec.max_volatility is not None:
        mask &= latest["history_volatility_pct"] <= spec.max_volatility
    candidates = latest[mask]
    if candidates.empty:
        return candidates
    return (
        candidates.sort_values(["asof_timestamp", "pred_return_window"], ascending=[True, False])
        .groupby("asof_timestamp", sort=True)
        .head(top_k)
        .reset_index(drop=True)
    )


def _metrics(selected: pd.DataFrame, latest: pd.DataFrame, spec: FilterSpec, top_k: int, cost_pct: float) -> Dict[str, Any]:
    payload = asdict(spec)
    payload["filter_name"] = spec.name
    payload["top_k"] = top_k
    payload["period_count_total"] = int(latest["asof_timestamp"].nunique())
    payload["window_count_total"] = int(len(latest))
    if selected.empty:
        payload.update(
            {
                "period_count": 0,
                "trade_count": 0,
                "avg_trades_per_period": 0.0,
                "avg_gross_return_pct": 0.0,
                "avg_net_return_pct": 0.0,
                "direction_hit_rate": 0.0,
                "win_rate": 0.0,
                "coverage": 0.0,
                "cumulative_return_pct": 0.0,
            }
        )
        return payload

    period_returns = []
    for _, group in selected.groupby("asof_timestamp", sort=True):
        gross = float(group["actual_return_window"].mean())
        period_returns.append(gross - cost_pct)
    cumulative = float(np.prod([1.0 + value / 100.0 for value in period_returns]) - 1.0) * 100.0
    payload.update(
        {
            "period_count": int(selected["asof_timestamp"].nunique()),
            "trade_count": int(len(selected)),
            "avg_trades_per_period": float(len(selected) / max(selected["asof_timestamp"].nunique(), 1)),
            "avg_gross_return_pct": float(selected["actual_return_window"].mean()),
            "avg_net_return_pct": float(np.mean(period_returns)),
            "direction_hit_rate": float(selected["direction_hit_window"].mean()),
            "win_rate": float((selected["actual_return_window"] > 0).mean()),
            "coverage": float(selected["asof_timestamp"].nunique() / max(latest["asof_timestamp"].nunique(), 1)),
            "cumulative_return_pct": cumulative,
        }
    )
    return payload


def _evaluate_specs(latest: pd.DataFrame, specs: Sequence[FilterSpec], top_k: int, cost_pct: float) -> pd.DataFrame:
    rows = []
    for spec in specs:
        selected = _selected_rows(latest, spec, top_k=top_k)
        rows.append(_metrics(selected, latest, spec, top_k=top_k, cost_pct=cost_pct))
    return pd.DataFrame(rows)


def _rank_feasible_results(
    all_results: pd.DataFrame,
    min_trades: int,
    min_periods: int,
    min_coverage: float,
) -> pd.DataFrame:
    feasible = all_results[
        (all_results["trade_count"] >= min_trades)
        & (all_results["period_count"] >= min_periods)
        & (all_results["coverage"] >= min_coverage)
    ].copy()
    if feasible.empty:
        feasible = all_results.copy()
    return feasible.sort_values(
        ["avg_net_return_pct", "cumulative_return_pct", "direction_hit_rate", "trade_count"],
        ascending=[False, False, False, False],
    )


def _sorted_periods(latest: pd.DataFrame) -> List[pd.Timestamp]:
    periods = latest["asof_timestamp"].dropna().drop_duplicates().sort_values()
    return [pd.Timestamp(value) for value in periods.tolist()]


def _period_subset(latest: pd.DataFrame, periods: Sequence[pd.Timestamp]) -> pd.DataFrame:
    period_set = set(pd.Timestamp(value) for value in periods)
    return latest[latest["asof_timestamp"].isin(period_set)].copy()


def _iso_timestamp(value: pd.Timestamp) -> str:
    return pd.Timestamp(value).isoformat()


def _mean_float(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    return float(pd.to_numeric(values, errors="coerce").fillna(0.0).mean())


def _weighted_mean(frame: pd.DataFrame, value_column: str, weight_column: str) -> float:
    if frame.empty:
        return 0.0
    values = pd.to_numeric(frame[value_column], errors="coerce").fillna(0.0)
    weights = pd.to_numeric(frame[weight_column], errors="coerce").fillna(0.0)
    weight_sum = float(weights.sum())
    if weight_sum <= 0:
        return 0.0
    return float((values * weights).sum() / weight_sum)


def _parse_bps_grid(raw: str) -> List[float]:
    values = []
    for part in str(raw).split(","):
        text = part.strip()
        if not text:
            continue
        value = float(text)
        if value < 0:
            raise ValueError("Cost bps values must be non-negative")
        values.append(value)
    if not values:
        raise ValueError("At least one cost bps value is required")
    return sorted(dict.fromkeys(values))


def _cost_pct_from_total_bps(total_bps: float) -> float:
    return float(total_bps) * 0.01


def _shift_net_to_total_cost(
    net_return_pct: Any,
    original_total_cost_bps: float,
    target_total_cost_bps: float,
) -> float:
    return _safe_float(net_return_pct) + _cost_pct_from_total_bps(original_total_cost_bps) - _cost_pct_from_total_bps(
        target_total_cost_bps
    )


def _scenario_passes(summary: Mapping[str, Any], thresholds: Mapping[str, float]) -> bool:
    return bool(
        _safe_float(summary.get("avg_test_net_return_pct")) >= _safe_float(thresholds.get("min_avg_test_net_pct"))
        and _safe_float(summary.get("positive_test_fold_rate")) >= _safe_float(
            thresholds.get("min_positive_test_fold_rate")
        )
        and _safe_float(summary.get("avg_test_improvement_net_pct")) >= _safe_float(
            thresholds.get("min_improvement_net_pct")
        )
        and _safe_float(summary.get("total_test_trade_count")) >= _safe_float(thresholds.get("min_total_test_trades"))
    )


def _filter_cost_sensitivity(
    filter_report: Mapping[str, Any],
    total_cost_bps_grid: Sequence[float],
) -> List[Dict[str, Any]]:
    rows = []
    original_total_cost_bps = _safe_float(filter_report.get("cost_bps")) + _safe_float(filter_report.get("slippage_bps"))
    candidates = []
    baseline = dict(filter_report.get("baseline_topk") or {})
    baseline["candidate_type"] = "baseline_topk"
    candidates.append(baseline)
    best = dict(filter_report.get("best_filter") or {})
    if best:
        best["candidate_type"] = "filter"
        candidates.append(best)
    for row in filter_report.get("top_filters") or []:
        candidate = dict(row)
        candidate["candidate_type"] = "filter"
        candidates.append(candidate)

    for total_cost_bps in total_cost_bps_grid:
        ranked = []
        for candidate in candidates:
            gross = _safe_float(candidate.get("avg_gross_return_pct"))
            ranked.append(
                {
                    "total_cost_bps": float(total_cost_bps),
                    "candidate_type": candidate.get("candidate_type", "filter"),
                    "filter_name": candidate.get("filter_name", ""),
                    "period_count": int(_safe_float(candidate.get("period_count"))),
                    "trade_count": int(_safe_float(candidate.get("trade_count"))),
                    "coverage": _safe_float(candidate.get("coverage")),
                    "avg_gross_return_pct": gross,
                    "avg_net_return_pct": _shift_net_to_total_cost(
                        candidate.get("avg_net_return_pct"), original_total_cost_bps, total_cost_bps
                    ),
                    "direction_hit_rate": _safe_float(candidate.get("direction_hit_rate")),
                }
            )
        ranked.sort(
            key=lambda row: (
                row["avg_net_return_pct"],
                row["avg_gross_return_pct"],
                row["direction_hit_rate"],
                row["trade_count"],
            ),
            reverse=True,
        )
        if ranked:
            rows.append(ranked[0])
    return rows


def _rolling_cost_sensitivity(
    rolling_report: Mapping[str, Any],
    total_cost_bps_grid: Sequence[float],
    thresholds: Mapping[str, float],
) -> List[Dict[str, Any]]:
    original_total_cost_bps = _safe_float(rolling_report.get("cost_bps")) + _safe_float(
        rolling_report.get("slippage_bps")
    )
    folds = list(rolling_report.get("folds") or [])
    rows = []
    for total_cost_bps in total_cost_bps_grid:
        adjusted_folds = []
        for fold in folds:
            test_net = _shift_net_to_total_cost(
                fold.get("test_avg_net_return_pct"), original_total_cost_bps, total_cost_bps
            )
            train_net = _shift_net_to_total_cost(
                fold.get("train_avg_net_return_pct"), original_total_cost_bps, total_cost_bps
            )
            baseline_test_net = _shift_net_to_total_cost(
                fold.get("baseline_test_avg_net_return_pct"), original_total_cost_bps, total_cost_bps
            )
            adjusted_folds.append(
                {
                    "fold": fold.get("fold"),
                    "selected_filter": fold.get("selected_filter"),
                    "train_avg_net_return_pct": train_net,
                    "test_avg_net_return_pct": test_net,
                    "baseline_test_avg_net_return_pct": baseline_test_net,
                    "test_vs_baseline_net_pct": test_net - baseline_test_net,
                    "test_trade_count": int(_safe_float(fold.get("test_trade_count"))),
                    "test_direction_hit_rate": _safe_float(fold.get("test_direction_hit_rate")),
                }
            )

        fold_frame = pd.DataFrame(adjusted_folds)
        if fold_frame.empty:
            summary = {
                "total_cost_bps": float(total_cost_bps),
                "fold_count": 0,
                "total_test_trade_count": 0,
                "avg_train_net_return_pct": 0.0,
                "avg_test_net_return_pct": 0.0,
                "avg_test_baseline_net_return_pct": 0.0,
                "avg_test_improvement_net_pct": 0.0,
                "test_direction_hit_rate_weighted": 0.0,
                "positive_test_fold_rate": 0.0,
                "overfit_gap_pct": 0.0,
            }
        else:
            avg_train = _mean_float(fold_frame["train_avg_net_return_pct"])
            avg_test = _mean_float(fold_frame["test_avg_net_return_pct"])
            summary = {
                "total_cost_bps": float(total_cost_bps),
                "fold_count": int(len(adjusted_folds)),
                "total_test_trade_count": int(fold_frame["test_trade_count"].sum()),
                "avg_train_net_return_pct": avg_train,
                "avg_test_net_return_pct": avg_test,
                "avg_test_baseline_net_return_pct": _mean_float(fold_frame["baseline_test_avg_net_return_pct"]),
                "avg_test_improvement_net_pct": _mean_float(fold_frame["test_vs_baseline_net_pct"]),
                "test_direction_hit_rate_weighted": _weighted_mean(
                    fold_frame, "test_direction_hit_rate", "test_trade_count"
                ),
                "positive_test_fold_rate": float((fold_frame["test_avg_net_return_pct"] > 0).mean()),
                "overfit_gap_pct": avg_train - avg_test,
            }
        summary["passes_gate"] = _scenario_passes(summary, thresholds)
        rows.append(summary)
    return rows


def build_cost_gate_report(
    filter_report_path: Path,
    rolling_report_path: Path,
    total_cost_bps_grid: Sequence[float],
    target_total_cost_bps: Optional[float] = None,
    min_avg_test_net_pct: float = 0.0,
    min_positive_test_fold_rate: float = 0.5,
    min_improvement_net_pct: float = 0.0,
    min_total_test_trades: int = 100,
) -> Dict[str, Any]:
    """Build a cost-sensitivity gate from existing filter-search and rolling artifacts.

    This reuses already generated validation artifacts, so it is safe to run
    before launching expensive staged GPU fine-tuning.
    """

    filter_report = json.loads(filter_report_path.read_text(encoding="utf-8"))
    rolling_report = json.loads(rolling_report_path.read_text(encoding="utf-8"))
    cost_grid = list(total_cost_bps_grid)
    target_cost = float(target_total_cost_bps if target_total_cost_bps is not None else max(cost_grid))
    thresholds = {
        "min_avg_test_net_pct": float(min_avg_test_net_pct),
        "min_positive_test_fold_rate": float(min_positive_test_fold_rate),
        "min_improvement_net_pct": float(min_improvement_net_pct),
        "min_total_test_trades": float(min_total_test_trades),
    }
    filter_sensitivity = _filter_cost_sensitivity(filter_report, cost_grid)
    rolling_sensitivity = _rolling_cost_sensitivity(rolling_report, cost_grid, thresholds)
    target = min(rolling_sensitivity, key=lambda row: abs(row["total_cost_bps"] - target_cost))
    expand_allowed = bool(target.get("passes_gate"))
    return {
        "created_at": _utc_now(),
        "artifact_type": "cost_sensitivity_gate",
        "filter_report": str(filter_report_path),
        "rolling_report": str(rolling_report_path),
        "total_cost_bps_grid": [float(value) for value in cost_grid],
        "target_total_cost_bps": target["total_cost_bps"],
        "gate_thresholds": thresholds,
        "filter_cost_sensitivity": filter_sensitivity,
        "rolling_cost_sensitivity": rolling_sensitivity,
        "target_cost_summary": target,
        "expand_training_allowed": expand_allowed,
        "decision": "allow_expand_200k" if expand_allowed else "hold_expand_200k",
        "decision_reason": (
            "target cost scenario passed rolling net, fold-rate, improvement, and trade-count gates"
            if expand_allowed
            else "target cost scenario failed at least one rolling profitability/stability gate"
        ),
    }


def search_filters(
    prediction_csv: Path,
    top_k: int = 5,
    cost_bps: float = 15.0,
    slippage_bps: float = 10.0,
    min_trades: int = 10,
    min_periods: int = 3,
    min_coverage: float = 0.5,
) -> Dict[str, Any]:
    df = pd.read_csv(prediction_csv, dtype={"symbol": str, "session": str}, encoding="utf-8-sig")
    latest = _latest_windows(df)
    cost_pct = (cost_bps + slippage_bps) * 0.01
    feasible = _rank_feasible_results(
        _evaluate_specs(latest, generate_filter_specs(), top_k=top_k, cost_pct=cost_pct),
        min_trades=min_trades,
        min_periods=min_periods,
        min_coverage=min_coverage,
    )

    baseline = _metrics(_selected_rows(latest, BASELINE_SPEC, top_k=top_k), latest, BASELINE_SPEC, top_k, cost_pct)
    best = feasible.head(1).to_dict(orient="records")[0]
    return {
        "created_at": _utc_now(),
        "prediction_csv": str(prediction_csv),
        "top_k": top_k,
        "cost_bps": cost_bps,
        "slippage_bps": slippage_bps,
        "min_trades": min_trades,
        "min_periods": min_periods,
        "min_coverage": min_coverage,
        "baseline_topk": baseline,
        "best_filter": best,
        "improvement_vs_baseline_net_pct": _safe_float(best.get("avg_net_return_pct")) - _safe_float(
            baseline.get("avg_net_return_pct")
        ),
        "top_filters": feasible.head(20).to_dict(orient="records"),
    }


def rolling_validate_filters(
    prediction_csv: Path,
    top_k: int = 5,
    cost_bps: float = 15.0,
    slippage_bps: float = 10.0,
    min_trades: int = 10,
    min_periods: int = 3,
    min_coverage: float = 0.5,
    train_periods: int = 30,
    test_periods: int = 10,
    step_periods: int = 10,
) -> Dict[str, Any]:
    """Pick the best filter on earlier periods and apply it to later periods."""

    df = pd.read_csv(prediction_csv, dtype={"symbol": str, "session": str}, encoding="utf-8-sig")
    latest = _latest_windows(df)
    periods = _sorted_periods(latest)
    if len(periods) < train_periods + test_periods:
        raise ValueError(
            f"Need at least train_periods + test_periods periods; got {len(periods)} "
            f"for train={train_periods}, test={test_periods}"
        )

    cost_pct = (cost_bps + slippage_bps) * 0.01
    specs = generate_filter_specs()
    folds: List[Dict[str, Any]] = []
    last_start = len(periods) - train_periods - test_periods
    for fold_id, start in enumerate(range(0, last_start + 1, max(1, step_periods)), start=1):
        train_slice = periods[start : start + train_periods]
        test_slice = periods[start + train_periods : start + train_periods + test_periods]
        train_latest = _period_subset(latest, train_slice)
        test_latest = _period_subset(latest, test_slice)

        train_ranked = _rank_feasible_results(
            _evaluate_specs(train_latest, specs, top_k=top_k, cost_pct=cost_pct),
            min_trades=min_trades,
            min_periods=min_periods,
            min_coverage=min_coverage,
        )
        train_best = train_ranked.head(1).to_dict(orient="records")[0]
        selected_spec = _spec_from_row(train_best)
        test_metrics = _metrics(
            _selected_rows(test_latest, selected_spec, top_k=top_k),
            test_latest,
            selected_spec,
            top_k,
            cost_pct,
        )
        baseline_test = _metrics(
            _selected_rows(test_latest, BASELINE_SPEC, top_k=top_k),
            test_latest,
            BASELINE_SPEC,
            top_k,
            cost_pct,
        )
        folds.append(
            {
                "fold": fold_id,
                "train_start": _iso_timestamp(train_slice[0]),
                "train_end": _iso_timestamp(train_slice[-1]),
                "test_start": _iso_timestamp(test_slice[0]),
                "test_end": _iso_timestamp(test_slice[-1]),
                "selected_filter": selected_spec.name,
                "train_avg_net_return_pct": _safe_float(train_best.get("avg_net_return_pct")),
                "train_direction_hit_rate": _safe_float(train_best.get("direction_hit_rate")),
                "train_trade_count": int(_safe_float(train_best.get("trade_count"))),
                "test_avg_net_return_pct": _safe_float(test_metrics.get("avg_net_return_pct")),
                "test_avg_gross_return_pct": _safe_float(test_metrics.get("avg_gross_return_pct")),
                "test_direction_hit_rate": _safe_float(test_metrics.get("direction_hit_rate")),
                "test_trade_count": int(_safe_float(test_metrics.get("trade_count"))),
                "test_coverage": _safe_float(test_metrics.get("coverage")),
                "test_cumulative_return_pct": _safe_float(test_metrics.get("cumulative_return_pct")),
                "baseline_test_avg_net_return_pct": _safe_float(baseline_test.get("avg_net_return_pct")),
                "test_vs_baseline_net_pct": _safe_float(test_metrics.get("avg_net_return_pct"))
                - _safe_float(baseline_test.get("avg_net_return_pct")),
            }
        )

    fold_frame = pd.DataFrame(folds)
    avg_train = _mean_float(fold_frame["train_avg_net_return_pct"])
    avg_test = _mean_float(fold_frame["test_avg_net_return_pct"])
    summary = {
        "fold_count": int(len(folds)),
        "total_period_count": int(len(periods)),
        "train_periods": int(train_periods),
        "test_periods": int(test_periods),
        "step_periods": int(step_periods),
        "total_test_trade_count": int(pd.to_numeric(fold_frame["test_trade_count"], errors="coerce").fillna(0).sum()),
        "avg_train_net_return_pct": avg_train,
        "avg_test_net_return_pct": avg_test,
        "avg_test_baseline_net_return_pct": _mean_float(fold_frame["baseline_test_avg_net_return_pct"]),
        "avg_test_improvement_net_pct": _mean_float(fold_frame["test_vs_baseline_net_pct"]),
        "test_direction_hit_rate_weighted": _weighted_mean(
            fold_frame, "test_direction_hit_rate", "test_trade_count"
        ),
        "positive_test_fold_rate": float((fold_frame["test_avg_net_return_pct"] > 0).mean()),
        "overfit_gap_pct": avg_train - avg_test,
        "is_profitable_after_cost": bool(avg_test > 0),
    }
    return {
        "created_at": _utc_now(),
        "prediction_csv": str(prediction_csv),
        "top_k": top_k,
        "cost_bps": cost_bps,
        "slippage_bps": slippage_bps,
        "min_trades": min_trades,
        "min_periods": min_periods,
        "min_coverage": min_coverage,
        "summary": summary,
        "folds": folds,
    }


def write_filter_report(result: Dict[str, Any], output_dir: Path, prefix: str) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result = _json_safe(result)
    json_path = output_dir / f"{prefix}.filter_search.json"
    csv_path = output_dir / f"{prefix}.filter_search_top20.csv"
    pd.DataFrame(result["top_filters"]).to_csv(csv_path, index=False, encoding="utf-8-sig")
    result["artifact_paths"] = {"json": str(json_path), "csv": str(csv_path)}
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def write_rolling_filter_report(result: Dict[str, Any], output_dir: Path, prefix: str) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result = _json_safe(result)
    json_path = output_dir / f"{prefix}.rolling_filter_validation.json"
    csv_path = output_dir / f"{prefix}.rolling_filter_validation_folds.csv"
    pd.DataFrame(result["folds"]).to_csv(csv_path, index=False, encoding="utf-8-sig")
    result["artifact_paths"] = {"json": str(json_path), "csv": str(csv_path)}
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def write_cost_gate_report(result: Dict[str, Any], output_dir: Path, prefix: str) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result = _json_safe(result)
    json_path = output_dir / f"{prefix}.cost_gate.json"
    csv_path = output_dir / f"{prefix}.cost_gate_rolling_sensitivity.csv"
    pd.DataFrame(result["rolling_cost_sensitivity"]).to_csv(csv_path, index=False, encoding="utf-8-sig")
    result["artifact_paths"] = {"json": str(json_path), "csv": str(csv_path)}
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search STOM 1s prediction-time score filters.")
    parser.add_argument("--prediction-csv", default=None)
    parser.add_argument("--output-dir", default="webui/qlib_backtests")
    parser.add_argument("--prefix", default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--cost-bps", type=float, default=15.0)
    parser.add_argument("--slippage-bps", type=float, default=10.0)
    parser.add_argument("--min-trades", type=int, default=10)
    parser.add_argument("--min-periods", type=int, default=3)
    parser.add_argument("--min-coverage", type=float, default=0.5)
    parser.add_argument("--rolling-validate", action="store_true")
    parser.add_argument("--rolling-train-periods", type=int, default=30)
    parser.add_argument("--rolling-test-periods", type=int, default=10)
    parser.add_argument("--rolling-step-periods", type=int, default=10)
    parser.add_argument("--gate-analysis", action="store_true")
    parser.add_argument("--filter-report", default=None)
    parser.add_argument("--rolling-report", default=None)
    parser.add_argument("--total-cost-bps-grid", default="5,10,15,25")
    parser.add_argument("--target-total-cost-bps", type=float, default=None)
    parser.add_argument("--min-avg-test-net-pct", type=float, default=0.0)
    parser.add_argument("--min-positive-test-fold-rate", type=float, default=0.5)
    parser.add_argument("--min-improvement-net-pct", type=float, default=0.0)
    parser.add_argument("--min-total-test-trades", type=int, default=100)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.gate_analysis:
        if not args.filter_report or not args.rolling_report:
            raise ValueError("--gate-analysis requires --filter-report and --rolling-report")
        result = build_cost_gate_report(
            filter_report_path=Path(args.filter_report),
            rolling_report_path=Path(args.rolling_report),
            total_cost_bps_grid=_parse_bps_grid(args.total_cost_bps_grid),
            target_total_cost_bps=args.target_total_cost_bps,
            min_avg_test_net_pct=args.min_avg_test_net_pct,
            min_positive_test_fold_rate=args.min_positive_test_fold_rate,
            min_improvement_net_pct=args.min_improvement_net_pct,
            min_total_test_trades=args.min_total_test_trades,
        )
        prefix = args.prefix or Path(args.rolling_report).stem
        result = write_cost_gate_report(result, Path(args.output_dir), prefix)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if not args.prediction_csv:
        raise ValueError("--prediction-csv is required unless --gate-analysis is used")
    prediction_csv = Path(args.prediction_csv)
    prefix = args.prefix or prediction_csv.stem
    if args.rolling_validate:
        result = rolling_validate_filters(
            prediction_csv=prediction_csv,
            top_k=args.top_k,
            cost_bps=args.cost_bps,
            slippage_bps=args.slippage_bps,
            min_trades=args.min_trades,
            min_periods=args.min_periods,
            min_coverage=args.min_coverage,
            train_periods=args.rolling_train_periods,
            test_periods=args.rolling_test_periods,
            step_periods=args.rolling_step_periods,
        )
        result = write_rolling_filter_report(result, Path(args.output_dir), prefix)
    else:
        result = search_filters(
            prediction_csv=prediction_csv,
            top_k=args.top_k,
            cost_bps=args.cost_bps,
            slippage_bps=args.slippage_bps,
            min_trades=args.min_trades,
            min_periods=args.min_periods,
            min_coverage=args.min_coverage,
        )
        result = write_filter_report(result, Path(args.output_dir), prefix)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
