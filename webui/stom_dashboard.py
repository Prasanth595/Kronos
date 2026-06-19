import csv
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.utils


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREDICTION_DIRS = [
    PROJECT_ROOT / "webui" / "stom_predictions",
    PROJECT_ROOT / "finetune_csv" / "predictions",
]
QLIB_BACKTEST_DIRS = [
    PROJECT_ROOT / "webui" / "qlib_backtests",
    PROJECT_ROOT / "finetune" / "qlib_backtests",
]
FILTER_REPORT_DIRS = QLIB_BACKTEST_DIRS
HORIZON_COMPARISON_FILE = "stom_1s_2025_full_small_horizon_comparison.json"
EVIDENCE_DIR = PROJECT_ROOT / ".omx" / "specs" / "stom-ohlcv-finetune-research"
SCORE_FILTER_NAMES = [
    "all_scored",
    "buy_candidate_score60",
    "score65_consistency80",
    "score70_pred_return_0_5",
    "stable_positive_filter",
    "early_session_score60",
]
ADAPTER_EXPORT_FIELDS = [
    "rank",
    "source_file",
    "window_id",
    "symbol",
    "session",
    "asof_timestamp",
    "adapter_action",
    "signal",
    "kronos_score",
    "score_band",
    "pred_return_pct",
    "prediction_consistency",
    "pred_range_pct",
    "asof_minute_bucket",
    "filter_labels",
    "diagnostic_actual_return_pct",
    "diagnostic_direction_hit",
    "diagnostic_realized_mape",
]


def _safe_path_in_dirs(file_name: str, directories: Optional[List[Path]] = None) -> Path:
    directories = directories or PREDICTION_DIRS
    requested = Path(file_name)
    if requested.is_absolute() or ".." in requested.parts:
        raise ValueError("Invalid file path")

    for directory in directories:
        candidate = (directory / requested).resolve()
        if candidate.exists() and directory.resolve() in candidate.parents:
            return candidate
    raise FileNotFoundError(f"Prediction file not found: {file_name}")


def load_training_summary() -> Dict[str, Any]:
    inspect_path = EVIDENCE_DIR / "all_tables_inspect_close_only.json"
    scale_path = EVIDENCE_DIR / "all_tables_sample_scale_lookback300_predict60.json"
    summary: Dict[str, Any] = {
        "inspect_available": inspect_path.exists(),
        "scale_available": scale_path.exists(),
        "table_count": None,
        "compatible_stock_table_count": None,
        "eligible_group_count": None,
        "estimated_samples": None,
        "excluded_tables": ["moneytop", "stockinfo"],
    }

    if inspect_path.exists():
        data = json.loads(inspect_path.read_text(encoding="utf-8"))
        summary.update(
            {
                "table_count": data.get("table_count"),
                "compatible_stock_table_count": data.get("compatible_table_count"),
                "eligible_group_count": data.get("eligible_group_count"),
                "db_size_bytes": data.get("db_size_bytes"),
                "warnings": data.get("warnings", []),
            }
        )
    if scale_path.exists():
        scale = json.loads(scale_path.read_text(encoding="utf-8"))
        summary.update(
            {
                "estimated_samples": scale.get("estimated_samples_lookback300_predict60"),
                "total_rows_stock_groups": scale.get("total_rows_stock_groups"),
                "compatible_stock_table_count": scale.get("compatible_stock_table_count"),
            }
        )
    return summary


def list_prediction_files() -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    for directory in PREDICTION_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.csv")):
            stat = path.stat()
            files.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "directory": str(directory),
                    "size_bytes": stat.st_size,
                    "modified_at": stat.st_mtime,
                }
            )
    return files


def _is_qlib_backtest_artifact(path: Path) -> bool:
    """Return true only for dashboard-loadable Qlib Top-K metric artifacts."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    return isinstance(payload, dict) and isinstance(payload.get("metrics"), dict)


def _filter_report_type(payload: Dict[str, Any]) -> Optional[str]:
    if payload.get("artifact_type") == "cost_sensitivity_gate":
        return "cost_sensitivity_gate"
    if isinstance(payload.get("summary"), dict) and isinstance(payload.get("folds"), list):
        return "rolling_filter_validation"
    if isinstance(payload.get("best_filter"), dict) and isinstance(payload.get("baseline_topk"), dict):
        return "filter_search"
    if isinstance(payload.get("rolling_cost_sensitivity"), list) and isinstance(payload.get("target_cost_summary"), dict):
        return "cost_sensitivity_gate"
    return None


def _read_filter_report(path: Path) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    artifact_type = _filter_report_type(payload)
    if artifact_type is None:
        return None
    payload["artifact_type"] = artifact_type
    return payload


def list_qlib_backtest_files() -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    for directory in QLIB_BACKTEST_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            if not _is_qlib_backtest_artifact(path):
                continue
            stat = path.stat()
            files.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "directory": str(directory),
                    "size_bytes": stat.st_size,
                    "modified_at": stat.st_mtime,
                }
            )
    return files


def list_filter_report_files() -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    for directory in FILTER_REPORT_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            payload = _read_filter_report(path)
            if payload is None:
                continue
            stat = path.stat()
            files.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "directory": str(directory),
                    "size_bytes": stat.st_size,
                    "modified_at": stat.st_mtime,
                    "artifact_type": payload["artifact_type"],
                }
            )
    return files


def load_qlib_backtest_artifact(file_name: str) -> Dict[str, Any]:
    path = _safe_path_in_dirs(file_name, QLIB_BACKTEST_DIRS)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "metrics" not in payload:
        raise ValueError("Qlib backtest artifact missing metrics")
    payload["source_file"] = path.name
    return payload


def load_filter_report_artifact(file_name: str) -> Dict[str, Any]:
    path = _safe_path_in_dirs(file_name, FILTER_REPORT_DIRS)
    payload = _read_filter_report(path)
    if payload is None:
        raise ValueError("Filter report artifact missing filter-search or rolling-validation payload")
    payload["source_file"] = path.name
    return payload


def _load_json_if_exists(path: Path) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _find_artifact(file_name: str, directories: List[Path]) -> Optional[Path]:
    try:
        return _safe_path_in_dirs(file_name, directories)
    except (FileNotFoundError, ValueError):
        return None


def _metric_at(payload: Dict[str, Any], *keys: str, default: float = 0.0) -> float:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return _safe_float(current, default)


def load_horizon_comparison() -> Dict[str, Any]:
    """Return horizon-level evidence for the STOM 1s full-small checkpoint.

    The evaluator writes large CSV/JSON files as runtime artifacts.  This helper
    intentionally summarizes only the dashboard-safe evidence so the frontend can
    compare 30/60/120/300 second horizons without loading prediction CSVs.
    """

    for directory in QLIB_BACKTEST_DIRS:
        path = directory / HORIZON_COMPARISON_FILE
        payload = _load_json_if_exists(path)
        if payload and isinstance(payload.get("rows"), list):
            rows = payload["rows"]
            break
    else:
        rows = []
        for horizon in [30, 60, 120, 300]:
            prefix = f"stom_1s_pred{horizon}_2025_full_small_walkforward36x3x50_eval"
            comparison_path = _find_artifact(f"{prefix}_comparison.json", PREDICTION_DIRS)
            qlib_path = _find_artifact(f"{prefix}_kronos.qlib_topk5.json", QLIB_BACKTEST_DIRS)
            filter_path = _find_artifact(f"{prefix}_kronos_cost25.filter_search.json", FILTER_REPORT_DIRS)
            gate_path = _find_artifact(f"{prefix}_kronos_cost25.cost_gate.json", FILTER_REPORT_DIRS)
            if not comparison_path:
                continue
            comparison = _load_json_if_exists(comparison_path) or {}
            qlib = _load_json_if_exists(qlib_path) if qlib_path else {}
            filters = _load_json_if_exists(filter_path) if filter_path else {}
            gate = _load_json_if_exists(gate_path) if gate_path else {}
            rows.append(_horizon_row(horizon, comparison, qlib or {}, filters or {}, gate or {}))

    clean_rows = [_normalize_horizon_row(row) for row in rows]
    clean_rows.sort(key=lambda row: int(row.get("horizon", 0)))
    best_by_direction = max(clean_rows, key=lambda row: row.get("direction_accuracy", 0.0), default=None)
    best_by_net = max(clean_rows, key=lambda row: row.get("rolling_net_return_pct", -999.0), default=None)
    any_pass = any(bool(row.get("passes_gate")) for row in clean_rows)
    return {
        "rows": clean_rows,
        "best_by_direction": best_by_direction,
        "best_by_rolling_net": best_by_net,
        "passes_any_gate": any_pass,
        "decision": "expand_allowed" if any_pass else "hold_expand_200k",
        "message": (
            "rolling validation gate를 통과한 horizon이 있습니다."
            if any_pass
            else "300초가 상대적으로 가장 유망하지만 아직 rolling cost gate는 통과하지 못했습니다."
        ),
    }


def _horizon_row(
    horizon: int,
    comparison: Dict[str, Any],
    qlib: Dict[str, Any],
    filters: Dict[str, Any],
    gate: Dict[str, Any],
) -> Dict[str, Any]:
    metrics = comparison.get("metrics", {}) if isinstance(comparison, dict) else {}
    kronos = metrics.get("kronos", {}) if isinstance(metrics, dict) else {}
    random = metrics.get("random", {}) if isinstance(metrics, dict) else {}
    qlib_metrics = qlib.get("metrics", {}) if isinstance(qlib, dict) else {}
    best_filter = filters.get("best_filter", {}) if isinstance(filters, dict) else {}
    target = gate.get("target_cost_summary", {}) if isinstance(gate, dict) else {}
    return {
        "horizon": horizon,
        "direction_accuracy": _safe_float(kronos.get("direction_accuracy")),
        "random_direction_accuracy": _safe_float(random.get("direction_accuracy")),
        "direction_edge_vs_random": _safe_float(kronos.get("direction_accuracy"))
        - _safe_float(random.get("direction_accuracy")),
        "mape": _safe_float(kronos.get("mape")),
        "topk_hit_rate": _metric_at(kronos, "topk", "hit_rate"),
        "topk_gross_return_pct": _safe_float(qlib_metrics.get("avg_gross_return_pct")),
        "topk_net_return_pct": _safe_float(qlib_metrics.get("avg_net_return_pct")),
        "topk_cumulative_return_pct": _safe_float(qlib_metrics.get("cumulative_return_pct")),
        "best_filter": str(best_filter.get("filter_name", "")),
        "best_filter_net_return_pct": _safe_float(best_filter.get("avg_net_return_pct")),
        "best_filter_hit_rate": _safe_float(best_filter.get("direction_hit_rate")),
        "best_filter_trade_count": int(_safe_float(best_filter.get("trade_count"))),
        "rolling_net_return_pct": _safe_float(target.get("avg_test_net_return_pct")),
        "rolling_direction_hit_rate": _safe_float(target.get("test_direction_hit_rate_weighted")),
        "rolling_positive_fold_rate": _safe_float(target.get("positive_test_fold_rate")),
        "passes_gate": bool(target.get("passes_gate")),
        "decision": str(gate.get("decision", "")),
    }


def _normalize_horizon_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "horizon": int(_safe_float(row.get("horizon"))),
        "direction_accuracy": _safe_float(row.get("direction_accuracy", row.get("direction"))),
        "random_direction_accuracy": _safe_float(row.get("random_direction_accuracy", row.get("random_direction"))),
        "direction_edge_vs_random": _safe_float(row.get("direction_edge_vs_random", row.get("dir_edge"))),
        "mape": _safe_float(row.get("mape")),
        "topk_hit_rate": _safe_float(row.get("topk_hit_rate", row.get("topk_hit"))),
        "topk_gross_return_pct": _safe_float(row.get("topk_gross_return_pct", row.get("topk_gross"))),
        "topk_net_return_pct": _safe_float(row.get("topk_net_return_pct", row.get("topk_net"))),
        "topk_cumulative_return_pct": _safe_float(row.get("topk_cumulative_return_pct", row.get("topk_cum"))),
        "best_filter": str(row.get("best_filter", "")),
        "best_filter_net_return_pct": _safe_float(row.get("best_filter_net_return_pct", row.get("best_filter_net"))),
        "best_filter_hit_rate": _safe_float(row.get("best_filter_hit_rate", row.get("best_filter_hit"))),
        "best_filter_trade_count": int(_safe_float(row.get("best_filter_trade_count", row.get("best_filter_trades")))),
        "rolling_net_return_pct": _safe_float(row.get("rolling_net_return_pct", row.get("rolling_net"))),
        "rolling_direction_hit_rate": _safe_float(row.get("rolling_direction_hit_rate", row.get("rolling_hit"))),
        "rolling_positive_fold_rate": _safe_float(
            row.get("rolling_positive_fold_rate", row.get("rolling_positive_fold_rate"))
        ),
        "passes_gate": bool(row.get("passes_gate")),
        "decision": str(row.get("decision", "")),
    }


def qlib_backtest_chart_json(payload: Dict[str, Any]) -> str:
    curve = pd.DataFrame(payload.get("curve", []))
    fig = go.Figure()
    if not curve.empty:
        curve["asof_timestamp"] = pd.to_datetime(curve["asof_timestamp"], errors="coerce")
        fig.add_trace(
            go.Scatter(
                x=curve["asof_timestamp"],
                y=curve["equity"],
                mode="lines+markers",
                name="Qlib Top-K equity",
                line={"color": "#0f766e", "width": 2},
            )
        )
    fig.update_layout(
        title="Qlib-style Top-K 누적 수익 곡선",
        xaxis_title="리밸런싱 시각",
        yaxis_title="Equity",
        template="plotly_white",
        height=420,
        legend={"orientation": "h"},
    )
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def load_prediction_frame(file_name: str) -> pd.DataFrame:
    path = _safe_path_in_dirs(file_name)
    df = pd.read_csv(path, dtype={"symbol": str, "session": str})
    required = {"window_id", "symbol", "session", "target_timestamp", "pred_close", "actual_close"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Prediction file missing required columns: {missing}")
    for column in ["pred_close", "actual_close", "error", "abs_error", "pred_return_window", "actual_return_window"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    df["target_timestamp"] = pd.to_datetime(df["target_timestamp"])
    if "asof_timestamp" in df.columns:
        df["asof_timestamp"] = pd.to_datetime(df["asof_timestamp"])
    return df


def prediction_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    error = pd.to_numeric(df.get("error", df["pred_close"] - df["actual_close"]), errors="coerce")
    abs_error = error.abs()
    actual = pd.to_numeric(df["actual_close"], errors="coerce").replace(0, np.nan)
    latest = df.sort_values(["window_id", "target_timestamp"]).groupby("window_id").tail(1)
    direction = pd.to_numeric(latest.get("direction_hit_window", pd.Series(dtype=float)), errors="coerce")
    mape = (abs_error / actual).replace([np.inf, -np.inf], np.nan).mean() * 100.0
    return {
        "rows": int(len(df)),
        "windows": int(df["window_id"].nunique()),
        "symbols": int(df["symbol"].nunique()),
        "mae": float(abs_error.mean()),
        "rmse": float(np.sqrt((error**2).mean())),
        "mape": float(0.0 if np.isnan(mape) else mape),
        "direction_accuracy": float(0.0 if direction.empty else direction.mean()),
        "avg_pred_return": float(pd.to_numeric(latest.get("pred_return_window", pd.Series(dtype=float)), errors="coerce").mean()),
        "avg_actual_return": float(pd.to_numeric(latest.get("actual_return_window", pd.Series(dtype=float)), errors="coerce").mean()),
    }


def _latest_prediction_rows(df: pd.DataFrame) -> pd.DataFrame:
    latest = df.sort_values(["window_id", "target_timestamp"]).groupby("window_id", sort=False).tail(1).copy()
    for column in [
        "pred_return_window",
        "actual_return_window",
        "direction_hit_window",
        "pred_path_consistency",
        "pred_range_pct",
    ]:
        if column not in latest.columns:
            latest[column] = 0.0
        latest[column] = pd.to_numeric(latest[column], errors="coerce").fillna(0.0)
    return latest


def _prediction_error_series(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    frame["error"] = pd.to_numeric(frame.get("error", frame["pred_close"] - frame["actual_close"]), errors="coerce")
    frame["abs_error"] = frame["error"].abs()
    actual = pd.to_numeric(frame["actual_close"], errors="coerce").replace(0, np.nan)
    frame["abs_pct_error"] = (frame["abs_error"] / actual).replace([np.inf, -np.inf], np.nan) * 100.0
    return frame


def _symbol_metric_frame(df: pd.DataFrame) -> pd.DataFrame:
    error_frame = _prediction_error_series(df)
    latest = _latest_prediction_rows(df)
    rows: List[Dict[str, Any]] = []
    for symbol, group in error_frame.groupby("symbol", sort=True):
        latest_group = latest[latest["symbol"] == symbol]
        error = pd.to_numeric(group["error"], errors="coerce")
        abs_error = error.abs()
        abs_pct_error = pd.to_numeric(group["abs_pct_error"], errors="coerce")
        pred_return = pd.to_numeric(latest_group["pred_return_window"], errors="coerce")
        actual_return = pd.to_numeric(latest_group["actual_return_window"], errors="coerce")
        direction = pd.to_numeric(latest_group["direction_hit_window"], errors="coerce")
        return_gap = (pred_return - actual_return).abs()
        rows.append(
            {
                "symbol": str(symbol),
                "rows": int(len(group)),
                "windows": int(latest_group["window_id"].nunique()),
                "sessions": int(group["session"].nunique()),
                "mae": _safe_float(abs_error.mean()),
                "rmse": _safe_float(np.sqrt((error**2).mean())),
                "mape": _safe_float(abs_pct_error.mean()),
                "direction_accuracy": _safe_float(direction.mean()),
                "avg_pred_return": _safe_float(pred_return.mean()),
                "avg_actual_return": _safe_float(actual_return.mean()),
                "avg_abs_return_gap": _safe_float(return_gap.mean()),
                "win_rate": _safe_float((actual_return > 0).mean()),
            }
        )
    return pd.DataFrame(rows)


def _records(frame: pd.DataFrame, limit: int) -> List[Dict[str, Any]]:
    if frame.empty:
        return []
    clean = frame.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return clean.head(max(0, int(limit))).to_dict(orient="records")


def error_distribution_chart_json(df: pd.DataFrame) -> str:
    error_frame = _prediction_error_series(df)
    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=error_frame["abs_pct_error"].dropna(),
            nbinsx=60,
            name="Absolute percentage error",
            marker={"color": "#2563eb"},
        )
    )
    fig.update_layout(
        title="전체 예측 오차 분포",
        xaxis_title="Absolute percentage error (%)",
        yaxis_title="Count",
        template="plotly_white",
        height=360,
    )
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def return_scatter_chart_json(df: pd.DataFrame, max_points: int = 5000) -> str:
    latest = _latest_prediction_rows(df).sort_values("window_id").head(max(1, int(max_points)))
    color = latest["direction_hit_window"].map({1: "#16a34a", 0: "#dc2626"}).fillna("#64748b")
    fig = go.Figure()
    fig.add_trace(
        go.Scattergl(
            x=latest["pred_return_window"],
            y=latest["actual_return_window"],
            mode="markers",
            marker={"color": color, "size": 7, "opacity": 0.75},
            text=latest["symbol"].astype(str),
            customdata=np.stack([latest["window_id"], latest["session"].astype(str)], axis=-1),
            hovertemplate="symbol=%{text}<br>window=%{customdata[0]}<br>session=%{customdata[1]}<br>pred=%{x:.4f}%<br>actual=%{y:.4f}%<extra></extra>",
            name="window",
        )
    )
    fig.add_hline(y=0, line={"color": "#94a3b8", "dash": "dot"})
    fig.add_vline(x=0, line={"color": "#94a3b8", "dash": "dot"})
    fig.update_layout(
        title="예측 등락률 vs 실제 등락률",
        xaxis_title="Predicted return (%)",
        yaxis_title="Actual return (%)",
        template="plotly_white",
        height=420,
    )
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def symbol_heatmap_chart_json(symbol_metrics: pd.DataFrame, max_symbols: int = 50) -> str:
    if symbol_metrics.empty:
        fig = go.Figure()
        return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    display = symbol_metrics.sort_values(["windows", "mape"], ascending=[False, True]).head(max(1, int(max_symbols)))
    z = np.array(
        [
            display["mape"].astype(float).to_numpy(),
            (display["direction_accuracy"].astype(float) * 100.0).to_numpy(),
            display["avg_abs_return_gap"].astype(float).to_numpy(),
        ]
    )
    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=display["symbol"].astype(str),
            y=["MAPE %", "Direction hit %", "Abs return gap %p"],
            colorscale="Viridis",
            colorbar={"title": "Value"},
        )
    )
    fig.update_layout(
        title="종목별 핵심 지표 heatmap",
        xaxis_title="Symbol",
        yaxis_title="Metric",
        template="plotly_white",
        height=420,
    )
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def prediction_diagnostics(df: pd.DataFrame, max_symbols: int = 50, min_windows: int = 1) -> Dict[str, Any]:
    symbol_metrics = _symbol_metric_frame(df)
    if min_windows > 1 and not symbol_metrics.empty:
        symbol_metrics = symbol_metrics[symbol_metrics["windows"] >= int(min_windows)].copy()
    symbol_metrics = symbol_metrics.sort_values(["windows", "mape"], ascending=[False, True])
    latest = _latest_prediction_rows(df)
    overall = prediction_metrics(df)
    overall.update(
        {
            "periods": int(latest["asof_timestamp"].nunique()) if "asof_timestamp" in latest.columns else 0,
            "sessions": int(df["session"].nunique()),
            "symbol_metric_count": int(len(symbol_metrics)),
        }
    )
    best_symbols = symbol_metrics.sort_values(
        ["direction_accuracy", "mape", "windows"], ascending=[False, True, False]
    )
    worst_symbols = symbol_metrics.sort_values(
        ["mape", "direction_accuracy", "windows"], ascending=[False, True, False]
    )
    limit = max(1, int(max_symbols))
    return {
        "overall": overall,
        "symbol_summary": _records(symbol_metrics, limit),
        "best_symbols": _records(best_symbols, limit),
        "worst_symbols": _records(worst_symbols, limit),
        "charts": {
            "error_distribution": error_distribution_chart_json(df),
            "return_scatter": return_scatter_chart_json(df),
            "symbol_heatmap": symbol_heatmap_chart_json(symbol_metrics, max_symbols=limit),
        },
    }


def prediction_chart_json(df: pd.DataFrame, window_id: Optional[int] = None) -> str:
    if window_id is None:
        window_id = int(df["window_id"].iloc[0])
    chart_df = df[df["window_id"] == window_id].sort_values("target_timestamp")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=chart_df["target_timestamp"],
            y=chart_df["actual_close"],
            mode="lines+markers",
            name="실제 close",
            line={"color": "#111827", "width": 2},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=chart_df["target_timestamp"],
            y=chart_df["pred_close"],
            mode="lines+markers",
            name="예측 close",
            line={"color": "#dc2626", "width": 2, "dash": "dash"},
        )
    )
    title = f"STOM 실제값 vs 예측값 - window {window_id}"
    if len(chart_df):
        first = chart_df.iloc[0]
        title += f" ({first['symbol']} / {first['session']})"
    fig.update_layout(
        title=title,
        xaxis_title="시각",
        yaxis_title="가격",
        template="plotly_white",
        height=520,
        legend={"orientation": "h"},
    )
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def topk_rows(df: pd.DataFrame, k: int = 20) -> List[Dict[str, Any]]:
    latest = df.sort_values(["window_id", "target_timestamp"]).groupby("window_id").tail(1)
    latest = latest.sort_values("pred_return_window", ascending=False).head(k)
    columns = [
        "window_id",
        "symbol",
        "session",
        "asof_timestamp",
        "pred_return_window",
        "actual_return_window",
        "direction_hit_window",
    ]
    return latest[[col for col in columns if col in latest.columns]].to_dict(orient="records")


def prediction_visual_payload(
    df: pd.DataFrame,
    window_id: Optional[int] = None,
    max_windows: int = 500,
    max_scatter: int = 5000,
) -> Dict[str, Any]:
    """Return frontend-native series for actual-vs-prediction dashboards.

    Plotly JSON is still kept for the legacy dashboard, but the Svelte v2 UI uses
    ECharts. This payload keeps the data small and explains the selected window
    without requiring the browser to parse CSV or Plotly traces.
    """

    if df.empty:
        return {
            "default_window_id": None,
            "selected_window": None,
            "window_series": [],
            "windows": [],
            "return_scatter": [],
        }

    sorted_df = df.sort_values(["window_id", "target_timestamp"]).copy()
    latest = _latest_prediction_rows(sorted_df).sort_values(["asof_timestamp", "window_id"])
    available_windows = [int(value) for value in latest["window_id"].dropna().tolist()]
    if window_id is None or int(window_id) not in set(available_windows):
        # Pick the strongest positive predicted-return window first: it is the
        # easiest default view for "why did Kronos select this?" review.
        ranked = latest.sort_values(["pred_return_window", "window_id"], ascending=[False, True])
        window_id = int(ranked["window_id"].iloc[0])

    chart_df = sorted_df[sorted_df["window_id"] == int(window_id)].sort_values("target_timestamp")
    selected_latest = latest[latest["window_id"] == int(window_id)]
    selected_record = selected_latest.iloc[0].to_dict() if not selected_latest.empty else {}

    def clean_ts(value: Any) -> str:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return str(value)
        return ts.isoformat()

    def row_float(row: pd.Series, column: str) -> float:
        return _safe_float(row.get(column))

    window_series = [
        {
            "timestamp": clean_ts(row.get("target_timestamp")),
            "actual_close": row_float(row, "actual_close"),
            "pred_close": row_float(row, "pred_close"),
            "error": row_float(row, "error"),
            "abs_error": row_float(row, "abs_error"),
        }
        for _, row in chart_df.iterrows()
    ]

    windows = []
    for _, row in latest.head(max(1, int(max_windows))).iterrows():
        windows.append(
            {
                "window_id": int(row.get("window_id")),
                "symbol": str(row.get("symbol", "")),
                "session": str(row.get("session", "")),
                "asof_timestamp": clean_ts(row.get("asof_timestamp")),
                "pred_return_window": row_float(row, "pred_return_window"),
                "actual_return_window": row_float(row, "actual_return_window"),
                "direction_hit_window": int(_safe_float(row.get("direction_hit_window"))),
            }
        )

    scatter_source = latest.sort_values(["asof_timestamp", "window_id"]).head(max(1, int(max_scatter)))
    return_scatter = [
        {
            "window_id": int(row.get("window_id")),
            "symbol": str(row.get("symbol", "")),
            "session": str(row.get("session", "")),
            "asof_timestamp": clean_ts(row.get("asof_timestamp")),
            "pred_return_window": row_float(row, "pred_return_window"),
            "actual_return_window": row_float(row, "actual_return_window"),
            "direction_hit_window": int(_safe_float(row.get("direction_hit_window"))),
        }
        for _, row in scatter_source.iterrows()
    ]

    return {
        "default_window_id": int(window_id),
        "selected_window": {
            "window_id": int(window_id),
            "symbol": str(selected_record.get("symbol", "")),
            "session": str(selected_record.get("session", "")),
            "asof_timestamp": clean_ts(selected_record.get("asof_timestamp")),
            "pred_return_window": _safe_float(selected_record.get("pred_return_window")),
            "actual_return_window": _safe_float(selected_record.get("actual_return_window")),
            "direction_hit_window": int(_safe_float(selected_record.get("direction_hit_window"))),
        },
        "window_series": window_series,
        "windows": windows,
        "return_scatter": return_scatter,
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if np.isnan(result) or np.isinf(result):
        return default
    return result


def _pct(numerator: float, denominator: float) -> float:
    if denominator == 0 or np.isnan(denominator):
        return 0.0
    return numerator / denominator * 100.0


def ranked_recommendations(
    df: pd.DataFrame,
    k: int = 20,
    long_only: bool = True,
    min_score: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Rank prediction windows by a live-usable Kronos score.

    The score intentionally uses predicted fields only:
    predicted window return, path consistency, and predicted path volatility.
    Actual return / hit fields are included only as backtest diagnostics.
    """

    rows: List[Dict[str, Any]] = []
    for window_id, group in df.sort_values(["window_id", "target_timestamp"]).groupby("window_id", sort=True):
        latest = group.iloc[-1]
        t0_close = _safe_float(latest.get("actual_close_t0"), _safe_float(group["actual_close"].iloc[0]))
        pred_return = _safe_float(latest.get("pred_return_window"))
        actual_return = _safe_float(latest.get("actual_return_window"))
        pred_close = pd.to_numeric(group["pred_close"], errors="coerce").dropna()
        actual_close = pd.to_numeric(group["actual_close"], errors="coerce").replace(0, np.nan)
        abs_error = pd.to_numeric(group.get("abs_error", pd.Series(dtype=float)), errors="coerce")

        if pred_close.empty:
            continue

        if pred_return >= 0:
            consistency = float((pred_close >= t0_close).mean())
        else:
            consistency = float((pred_close <= t0_close).mean())

        pred_range_pct = _pct(float(pred_close.max() - pred_close.min()), t0_close)
        realized_mape = float((abs_error / actual_close).replace([np.inf, -np.inf], np.nan).mean() * 100.0)
        if np.isnan(realized_mape):
            realized_mape = 0.0

        raw_score = 50.0 + pred_return * 5.0 + (consistency - 0.5) * 30.0 - min(pred_range_pct, 20.0) * 0.5
        if long_only and pred_return <= 0:
            raw_score -= 20.0 + min(abs(pred_return) * 3.0, 20.0)
        score = float(np.clip(raw_score, 0.0, 100.0))

        if score >= 60.0 and pred_return > 0:
            signal = "BUY_CANDIDATE"
        elif score >= 45.0:
            signal = "WATCH"
        else:
            signal = "AVOID"

        rows.append(
            {
                "window_id": int(window_id),
                "symbol": str(latest.get("symbol", "")),
                "session": str(latest.get("session", "")),
                "asof_timestamp": str(latest.get("asof_timestamp", "")),
                "kronos_score": score,
                "signal": signal,
                "pred_return_window": pred_return,
                "actual_return_window": actual_return,
                "direction_hit_window": int(_safe_float(latest.get("direction_hit_window"))),
                "prediction_consistency": consistency,
                "pred_range_pct": pred_range_pct,
                "realized_mape": realized_mape,
            }
        )

    if min_score is not None:
        rows = [row for row in rows if row["kronos_score"] >= min_score]
    rows = sorted(rows, key=lambda row: (row["kronos_score"], row["pred_return_window"]), reverse=True)
    return rows[: max(0, int(k))]


def recommendation_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {
            "count": 0,
            "avg_score": 0.0,
            "top_score": 0.0,
            "avg_pred_return": 0.0,
            "avg_actual_return": 0.0,
            "hit_rate": 0.0,
            "buy_candidates": 0,
        }

    return {
        "count": len(rows),
        "avg_score": float(np.mean([row["kronos_score"] for row in rows])),
        "top_score": float(max(row["kronos_score"] for row in rows)),
        "avg_pred_return": float(np.mean([row["pred_return_window"] for row in rows])),
        "avg_actual_return": float(np.mean([row["actual_return_window"] for row in rows])),
        "hit_rate": float(np.mean([row["direction_hit_window"] for row in rows])),
        "buy_candidates": int(sum(row["signal"] == "BUY_CANDIDATE" for row in rows)),
    }


def _backtest_metrics(rows: List[Dict[str, Any]], label: str) -> Dict[str, Any]:
    if not rows:
        return {
            "label": label,
            "count": 0,
            "avg_score": 0.0,
            "avg_pred_return": 0.0,
            "avg_actual_return": 0.0,
            "hit_rate": 0.0,
            "win_rate": 0.0,
            "avg_realized_mape": 0.0,
            "profit_factor": 0.0,
        }

    actual_returns = [_safe_float(row.get("actual_return_window")) for row in rows]
    gross_gain = sum(value for value in actual_returns if value > 0)
    gross_loss = abs(sum(value for value in actual_returns if value < 0))
    return {
        "label": label,
        "count": len(rows),
        "avg_score": float(np.mean([row["kronos_score"] for row in rows])),
        "avg_pred_return": float(np.mean([row["pred_return_window"] for row in rows])),
        "avg_actual_return": float(np.mean(actual_returns)),
        "hit_rate": float(np.mean([row["direction_hit_window"] for row in rows])),
        "win_rate": float(np.mean([1 if value > 0 else 0 for value in actual_returns])),
        "avg_realized_mape": float(np.mean([row["realized_mape"] for row in rows])),
        "profit_factor": float(gross_gain / gross_loss) if gross_loss > 0 else float(gross_gain),
    }


def _asof_minute_bucket(asof_timestamp: str, minutes: int = 5) -> str:
    ts = pd.to_datetime(asof_timestamp, errors="coerce")
    if pd.isna(ts):
        return "unknown"
    bucket_minute = int(ts.minute // minutes * minutes)
    end_minute = bucket_minute + minutes - 1
    return f"{ts.hour:02d}:{bucket_minute:02d}-{ts.hour:02d}:{end_minute:02d}"


def _is_early_session(asof_timestamp: str, max_minute: int = 10) -> bool:
    ts = pd.to_datetime(asof_timestamp, errors="coerce")
    if pd.isna(ts):
        return False
    return int(ts.minute) <= max_minute


def _score_band(score: float) -> str:
    if score >= 70:
        return "70+"
    if score >= 60:
        return "60-70"
    if score >= 45:
        return "45-60"
    return "<45"


def _filter_label_matches(row: Dict[str, Any], filter_name: str) -> bool:
    if filter_name == "all_scored":
        return True
    if filter_name == "buy_candidate_score60":
        return row["kronos_score"] >= 60 and row["pred_return_window"] > 0
    if filter_name == "score65_consistency80":
        return row["kronos_score"] >= 65 and row["prediction_consistency"] >= 0.80
    if filter_name == "score70_pred_return_0_5":
        return row["kronos_score"] >= 70 and row["pred_return_window"] >= 0.5
    if filter_name == "stable_positive_filter":
        return (
            row["kronos_score"] >= 60
            and row["pred_return_window"] >= 0.3
            and row["prediction_consistency"] >= 0.80
            and row["pred_range_pct"] <= 2.5
        )
    if filter_name == "early_session_score60":
        return row["kronos_score"] >= 60 and _is_early_session(row["asof_timestamp"])
    raise ValueError(f"Unknown score filter: {filter_name}")


def _filter_labels(row: Dict[str, Any]) -> List[str]:
    labels = ["all_scored"]
    for filter_name in SCORE_FILTER_NAMES[1:]:
        if _filter_label_matches(row, filter_name):
            labels.append(filter_name)
    return labels


def _top_group_metrics(
    rows: List[Dict[str, Any]],
    key: str,
    label: str,
    limit: int = 10,
    min_count: int = 1,
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key, "")), []).append(row)

    result = []
    for group_key, group_rows in grouped.items():
        if len(group_rows) < min_count:
            continue
        metrics = _backtest_metrics(group_rows, group_key)
        metrics["segment"] = label
        result.append(metrics)
    return sorted(result, key=lambda item: (item["avg_actual_return"], item["count"]), reverse=True)[:limit]


def score_backtest_report(df: pd.DataFrame, top_k: Optional[int] = None) -> Dict[str, Any]:
    """Build score-filter and segment backtest diagnostics for prediction windows."""

    max_rows = int(df["window_id"].nunique()) if top_k is None else int(top_k)
    rows = ranked_recommendations(df, k=max_rows, long_only=False)
    for row in rows:
        row["score_band"] = _score_band(row["kronos_score"])
        row["asof_minute_bucket"] = _asof_minute_bucket(row["asof_timestamp"])

    conditions = [
        (filter_name, [row for row in rows if _filter_label_matches(row, filter_name)])
        for filter_name in SCORE_FILTER_NAMES
    ]

    return {
        "window_count": int(df["window_id"].nunique()),
        "scored_count": len(rows),
        "filters": [_backtest_metrics(condition_rows, label) for label, condition_rows in conditions],
        "segments": {
            "score_band": _top_group_metrics(rows, "score_band", "score_band", limit=10),
            "symbol": _top_group_metrics(rows, "symbol", "symbol", limit=10),
            "asof_minute_bucket": _top_group_metrics(rows, "asof_minute_bucket", "asof_minute_bucket", limit=10),
        },
    }


def recommendation_export_payload(
    df: pd.DataFrame,
    source_file: str = "",
    limit: Optional[int] = 20,
    min_score: Optional[float] = None,
    selected_filter: str = "buy_candidate_score60",
    long_only: bool = True,
) -> Dict[str, Any]:
    """Build a stable CSV/JSON score export payload for internal review.

    external trading-program integration is intentionally de-scoped. Selection filters use
    prediction-time fields only. Diagnostic actual-return fields are exported for
    review/backtest display and must not be used as live filter inputs.
    """

    if selected_filter not in SCORE_FILTER_NAMES:
        raise ValueError(f"Unknown score filter: {selected_filter}")

    normalized_limit = None if limit is None else max(0, int(limit))
    all_rows = ranked_recommendations(df, k=int(df["window_id"].nunique()), long_only=long_only)
    exported_rows: List[Dict[str, Any]] = []
    for row in all_rows:
        row["score_band"] = _score_band(row["kronos_score"])
        row["asof_minute_bucket"] = _asof_minute_bucket(row["asof_timestamp"])
        labels = _filter_labels(row)
        if selected_filter and selected_filter not in labels:
            continue
        if min_score is not None and row["kronos_score"] < min_score:
            continue
        exported_rows.append(row)

    if normalized_limit is not None:
        exported_rows = exported_rows[:normalized_limit]

    records = []
    for rank, row in enumerate(exported_rows, start=1):
        labels = _filter_labels(row)
        adapter_action = "BUY" if "buy_candidate_score60" in labels else ("WATCH" if row["signal"] == "WATCH" else "AVOID")
        records.append(
            {
                "rank": rank,
                "source_file": source_file,
                "window_id": row["window_id"],
                "symbol": row["symbol"],
                "session": row["session"],
                "asof_timestamp": row["asof_timestamp"],
                "adapter_action": adapter_action,
                "signal": row["signal"],
                "kronos_score": row["kronos_score"],
                "score_band": row["score_band"],
                "pred_return_pct": row["pred_return_window"],
                "prediction_consistency": row["prediction_consistency"],
                "pred_range_pct": row["pred_range_pct"],
                "asof_minute_bucket": row["asof_minute_bucket"],
                "filter_labels": labels,
                "diagnostic_actual_return_pct": row["actual_return_window"],
                "diagnostic_direction_hit": row["direction_hit_window"],
                "diagnostic_realized_mape": row["realized_mape"],
            }
        )

    return {
        "metadata": {
            "adapter_version": "stom-kronos-score-v1",
            "source_file": source_file,
            "created_at": pd.Timestamp.utcnow().isoformat(),
            "window_count": int(df["window_id"].nunique()),
            "selected_filter": selected_filter,
            "min_score": min_score,
            "limit": normalized_limit,
            "long_only": long_only,
            "record_count": len(records),
            "fields": ADAPTER_EXPORT_FIELDS,
            "live_selection_note": "external trading-program integration is de-scoped. Selection fields use Kronos prediction outputs only; diagnostic_* fields are for backtest review.",
        },
        "records": records,
    }


def recommendation_export_csv(records: List[Dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=ADAPTER_EXPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for record in records:
        row = {field: record.get(field, "") for field in ADAPTER_EXPORT_FIELDS}
        row["filter_labels"] = ";".join(record.get("filter_labels", []))
        writer.writerow(row)
    return output.getvalue()
