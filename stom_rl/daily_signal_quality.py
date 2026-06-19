"""Daily OHLCV D3/D4 signal-quality diagnostics.

Research-only CLI for auditing whether existing D3 scores, score margins,
confidence buckets, and past-only risk proxies contain usable information before
another D4 overlay experiment.  This module never submits orders and never claims
profitability; it writes diagnostic artifacts only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

DEFAULT_SCORE_COLUMN = "score_supervised_linear_ranker"
DEFAULT_RUN_ID = "signal_quality_audit_001"
DEFAULT_OUTPUT_ROOT = Path("webui/rl_runs/daily_ohlcv_signal_quality")
DEFAULT_PREDICTION_DIR = Path("webui/rl_runs/daily_ohlcv_prediction/_scenario_runs/scenario_batch_d4_trade_quality_filter_001__confidence_abstain_v1")
DEFAULT_WALK_FORWARD_DIR = Path("webui/rl_runs/daily_ohlcv_walk_forward/_scenario_runs/scenario_batch_d4_trade_quality_filter_001__confidence_abstain_v1")
DEFAULT_PORTFOLIO_DIR = Path("webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_d4_trade_quality_filter_001__confidence_abstain_v1")
DEFAULT_SCORE_THRESHOLDS = (0.001, 0.005, 0.02)
DEFAULT_COST_SENSITIVITY_BP = (0, 23, 46)
RESEARCH_GUARDRAIL = (
    "Research-only signal-quality diagnostics; no live/broker/orders, no profit guarantee, "
    "no model-build or paper-forward unlock."
)


@dataclass(frozen=True)
class PredictionRow:
    code: str
    date: str
    split: str
    score: float
    future_return_1d: float
    future_direction_1d: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _bucket_by_threshold(value: float | None, thresholds: Sequence[float] = DEFAULT_SCORE_THRESHOLDS) -> int:
    if value is None:
        return 0
    clean = abs(float(value))
    return sum(clean > threshold for threshold in thresholds)


def _score_sign_bucket(value: float | None) -> int:
    if value is None:
        return 0
    return 1 if value > 0 else -1 if value < 0 else 0


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_predictions(prediction_dir: Path, *, score_column: str = DEFAULT_SCORE_COLUMN) -> list[PredictionRow]:
    path = prediction_dir / "predictions.csv"
    rows: list[PredictionRow] = []
    for raw in _read_csv(path):
        score = _safe_float(raw.get(score_column))
        future_return = _safe_float(raw.get("future_return_1d"))
        if score is None or future_return is None:
            continue
        code = str(raw.get("code", "")).zfill(6)
        direction_value = _safe_float(raw.get("future_direction_1d"))
        rows.append(
            PredictionRow(
                code=code,
                date=str(raw.get("date", "")),
                split=str(raw.get("split", "unknown")),
                score=score,
                future_return_1d=future_return,
                future_direction_1d=1 if (direction_value or 0.0) > 0 else 0,
            )
        )
    if not rows:
        raise ValueError(f"No usable prediction rows with {score_column} and future_return_1d in {path}")
    return rows


def load_fold_assignments(walk_forward_dir: Path | None) -> dict[str, str]:
    if walk_forward_dir is None:
        return {}
    path = walk_forward_dir / "fold_assignments.csv"
    if not path.exists():
        return {}
    assignments: dict[str, str] = {}
    for raw in _read_csv(path):
        if str(raw.get("role", "")).lower() == "test":
            assignments[str(raw.get("date", ""))] = str(raw.get("fold_id", "fold_unknown"))
    return assignments
def load_lagged_portfolio_context(portfolio_dir: Path | None) -> dict[str, dict[str, Any]]:
    """Load t-1 generated path context without using current-day labels.

    The prereg permits drawdown from a past research equity path and requires
    fail-closed behavior when a past-return proxy is not available.  This loader
    uses only rows strictly before the current date from drawdown.csv: prior
    rewards build a volatility proxy and the prior current_drawdown becomes the
    drawdown proxy.  Current-row rewards/drawdown are appended only after the
    current date's context has been emitted.
    """
    if portfolio_dir is None:
        return {}
    path = portfolio_dir / "drawdown.csv"
    if not path.exists():
        return {}

    rows_by_date: dict[str, list[dict[str, str]]] = defaultdict(list)
    for raw in _read_csv(path):
        date = str(raw.get("date", ""))
        if date:
            rows_by_date[date].append(raw)

    context: dict[str, dict[str, Any]] = {}
    prior_rewards: list[float] = []
    prior_drawdown = 0.0
    for date in sorted(rows_by_date):
        date_rows = rows_by_date[date]
        context[date] = {
            "past_return_volatility": _stddev(prior_rewards[-5:]),
            "drawdown": prior_drawdown,
            "past_return_volatility_source": "drawdown.csv lagged date-deduplicated reward lookback",
            "drawdown_source": "drawdown.csv lagged date-deduplicated current_drawdown",
            "past_return_volatility_status": "AVAILABLE_T_MINUS_1_GENERATED_PATH",
            "drawdown_status": "AVAILABLE_T_MINUS_1_GENERATED_PATH",
        }
        rewards = [value for value in (_safe_float(raw.get("reward")) for raw in date_rows) if value is not None]
        drawdowns = [value for value in (_safe_float(raw.get("current_drawdown")) for raw in date_rows) if value is not None]
        if rewards:
            prior_rewards.append(_mean(rewards))
        if drawdowns:
            prior_drawdown = min(drawdowns)
    return context




def _group_by_date(rows: Iterable[PredictionRow]) -> dict[str, list[PredictionRow]]:
    grouped: dict[str, list[PredictionRow]] = defaultdict(list)
    for row in rows:
        grouped[row.date].append(row)
    for date_rows in grouped.values():
        date_rows.sort(key=lambda row: row.score, reverse=True)
    return dict(sorted(grouped.items()))


def _missing_portfolio_context() -> dict[str, Any]:
    return {
        "past_return_volatility": 0.0,
        "drawdown": 0.0,
        "past_return_volatility_source": "MISSING_PAST_OHLCV_PROXY",
        "drawdown_source": "MISSING_PAST_OHLCV_PROXY",
        "past_return_volatility_status": "MISSING_PAST_OHLCV_PROXY_FAIL_CLOSED",
        "drawdown_status": "MISSING_PAST_OHLCV_PROXY_FAIL_CLOSED",
    }


def _daily_context(
    rows: list[PredictionRow],
    fold_by_date: dict[str, str],
    portfolio_context: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    by_date = _group_by_date(rows)

    contexts: dict[str, dict[str, Any]] = {}
    prior_top_scores: list[float] = []
    prior_top_codes: set[str] | None = None
    prior_top_code: str | None = None
    for date, date_rows in by_date.items():
        top = date_rows[0]
        second_score = date_rows[1].score if len(date_rows) > 1 else 0.0
        scores = [row.score for row in date_rows]
        mean_score = sum(scores) / len(scores)
        score_dispersion = math.sqrt(sum((score - mean_score) ** 2 for score in scores) / len(scores)) if scores else 0.0
        breadth = sum(1 for score in scores if score > 0) / len(scores) if scores else 0.0
        current_top_codes = {row.code for row in date_rows[:10]}
        turnover_pressure = 0.0 if prior_top_codes is None else len(current_top_codes - prior_top_codes) / max(len(current_top_codes), 1)
        top_code_turnover_pressure = 0.0 if prior_top_code is None or prior_top_code == top.code else 1.0
        lookback_scores = prior_top_scores[-5:]
        recent_score_volatility = _stddev(lookback_scores)
        lagged_path_context = (portfolio_context or {}).get(date) or _missing_portfolio_context()
        past_return_volatility = _safe_float(lagged_path_context.get("past_return_volatility")) or 0.0
        drawdown = _safe_float(lagged_path_context.get("drawdown")) or 0.0
        margin = top.score - second_score
        contexts[date] = {
            "top_score": top.score,
            "top_code": top.code,
            "score_margin": margin,
            "score_dispersion": score_dispersion,
            "breadth_proxy": breadth,
            "turnover_pressure": turnover_pressure,
            "top_code_turnover_pressure": top_code_turnover_pressure,
            "recent_score_volatility": recent_score_volatility,
            "past_return_volatility": past_return_volatility,
            "drawdown": drawdown,
            "past_return_volatility_source": lagged_path_context["past_return_volatility_source"],
            "drawdown_source": lagged_path_context["drawdown_source"],
            "past_return_volatility_status": lagged_path_context["past_return_volatility_status"],
            "drawdown_status": lagged_path_context["drawdown_status"],
            "score_magnitude_bucket": _bucket_by_threshold(top.score),
            "score_sign_bucket": _score_sign_bucket(top.score),
            "score_margin_bucket": _bucket_by_threshold(margin),
            "d3_confidence_bucket": _bucket_by_threshold(top.score),
            "candidate_count_bucket": min(len(date_rows), 3),
            "score_dispersion_bucket": _bucket_by_threshold(score_dispersion),
            "recent_score_volatility_bucket": _bucket_by_threshold(recent_score_volatility),
            "past_return_volatility_bucket": _bucket_by_threshold(past_return_volatility),
            "drawdown_bucket": _bucket_by_threshold(drawdown),
            "breadth_proxy_bucket": _bucket_by_threshold(breadth, (0.25, 0.50, 0.75)),
            "turnover_pressure_bucket": _bucket_by_threshold(turnover_pressure, (0.25, 0.50, 0.75)),
            "fold_id": fold_by_date.get(date, "FULL"),
        }
        prior_top_scores.append(top.score)
        prior_top_codes = current_top_codes
        prior_top_code = top.code
    return contexts


def _stddev(values: Sequence[float]) -> float:
    if len(values) <= 1:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _rank(values: Sequence[float]) -> list[float]:
    order = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * len(values)
    idx = 0
    while idx < len(order):
        j = idx + 1
        while j < len(order) and order[j][1] == order[idx][1]:
            j += 1
        avg_rank = (idx + 1 + j) / 2.0
        for k in range(idx, j):
            ranks[order[k][0]] = avg_rank
        idx = j
    return ranks


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx = _mean(xs)
    my = _mean(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0.0 or vy <= 0.0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / math.sqrt(vx * vy)


def _spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 2:
        return None
    return _pearson(_rank(xs), _rank(ys))


def _fold_for(row: PredictionRow, contexts: dict[str, dict[str, Any]]) -> str:
    return str(contexts.get(row.date, {}).get("fold_id") or "FULL")


def _signal_bucket_metadata(bucket_name: str) -> dict[str, Any]:
    if bucket_name in {"score_magnitude_bucket", "score_sign_bucket"}:
        return {
            "source_timing": "t/current/pre_action",
            "source_artifact": "predictions.csv score column",
            "future_label_used_for_bucket": False,
        }
    if bucket_name == "score_margin_bucket":
        return {
            "source_timing": "t/current/pre_action",
            "source_artifact": "current date candidate score ranking",
            "future_label_used_for_bucket": False,
        }
    if bucket_name == "d3_confidence_bucket":
        return {
            "source_timing": "t/current/pre_action",
            "source_artifact": "current top D3 score",
            "future_label_used_for_bucket": False,
        }
    raise KeyError(bucket_name)


def _risk_proxy_metadata(proxy_name: str, sample_context: dict[str, Any]) -> dict[str, Any]:
    if proxy_name == "score_dispersion_bucket":
        return {
            "source_timing": "t/current/pre_action",
            "source_artifact": "current candidate panel D3 score dispersion",
            "proxy_status": "AVAILABLE_CURRENT_SCORE_PANEL",
        }
    if proxy_name == "recent_score_volatility_bucket":
        return {
            "source_timing": "t-1/lookback/pre_action",
            "source_artifact": "prior top D3 scores",
            "proxy_status": "AVAILABLE_T_MINUS_1_SCORE_LOOKBACK",
        }
    if proxy_name == "past_return_volatility_bucket":
        return {
            "source_timing": "t-1/lookback/pre_action",
            "source_artifact": sample_context["past_return_volatility_source"],
            "proxy_status": sample_context["past_return_volatility_status"],
        }
    if proxy_name == "drawdown_bucket":
        return {
            "source_timing": "t-1/lookback/pre_action",
            "source_artifact": sample_context["drawdown_source"],
            "proxy_status": sample_context["drawdown_status"],
        }
    if proxy_name == "breadth_proxy_bucket":
        return {
            "source_timing": "t/current/pre_action",
            "source_artifact": "current candidate panel positive-score breadth",
            "proxy_status": "AVAILABLE_CURRENT_SCORE_PANEL",
        }
    if proxy_name == "turnover_pressure_bucket":
        return {
            "source_timing": "t/current_plus_t_minus_1/pre_action",
            "source_artifact": "current top-k candidate replacement versus prior top-k candidates",
            "proxy_status": "AVAILABLE_SCORE_PANEL_TURNOVER_PROXY",
        }
    raise KeyError(proxy_name)


def signal_bucket_metrics(
    rows: list[PredictionRow],
    contexts: dict[str, dict[str, Any]],
    *,
    cost_bp_values: Sequence[int] = DEFAULT_COST_SENSITIVITY_BP,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        ctx = contexts[row.date]
        enriched.append(
            {
                "split": row.split,
                "fold": _fold_for(row, contexts),
                "future_return_1d": row.future_return_1d,
                "future_direction_1d": row.future_direction_1d,
                "score": row.score,
                "score_magnitude_bucket": _bucket_by_threshold(row.score),
                "score_sign_bucket": _score_sign_bucket(row.score),
                "score_margin_bucket": ctx["score_margin_bucket"],
                "d3_confidence_bucket": ctx["d3_confidence_bucket"],
                "score_margin": ctx["score_margin"],
            }
        )
    metric_rows: list[dict[str, Any]] = []
    for bucket_name in ["score_magnitude_bucket", "score_sign_bucket", "score_margin_bucket", "d3_confidence_bucket"]:
        metadata = _signal_bucket_metadata(bucket_name)
        grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
        for row in enriched:
            grouped[(row["split"], row["fold"], int(row[bucket_name]))].append(row)
        for (split, fold, bucket_value), bucket_rows in sorted(grouped.items()):
            returns = [float(row["future_return_1d"]) for row in bucket_rows]
            scores = [float(row["score"]) for row in bucket_rows]
            margins = [float(row["score_margin"]) for row in bucket_rows]
            for cost_bp in cost_bp_values:
                cost_rate = cost_bp / 10000.0
                net_returns = [value - cost_rate for value in returns]
                metric_rows.append(
                    {
                        "split": split,
                        "fold": fold,
                        "bucket_name": bucket_name,
                        "bucket_value": bucket_value,
                        "count": len(bucket_rows),
                        "mean_future_return_1d": _mean(returns),
                        "mean_net_return_1d": _mean(net_returns),
                        "median_future_return_1d": _median(returns),
                        "hit_rate": _mean([1.0 if value > 0 else 0.0 for value in returns]),
                        "mean_score": _mean(scores),
                        "mean_margin": _mean(margins),
                        "cost_bp": cost_bp,
                        "source_timing": metadata["source_timing"],
                        "source_artifact": metadata["source_artifact"],
                        "future_label_used_for_bucket": metadata["future_label_used_for_bucket"],
                        "future_label_used_for_evaluation": True,
                        "threshold_policy": "frozen_absolute_no_quantile_search_no_oos_retune",
                    }
                )
    return metric_rows


def rank_correlations(rows: list[PredictionRow], contexts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[PredictionRow]] = defaultdict(list)
    for row in rows:
        groups[(row.split, _fold_for(row, contexts))].append(row)
    output: list[dict[str, Any]] = []
    for (split, fold), group_rows in sorted(groups.items()):
        scores = [row.score for row in group_rows]
        returns = [row.future_return_1d for row in group_rows]
        output.append(
            {
                "split": split,
                "fold": fold,
                "score_field": DEFAULT_SCORE_COLUMN,
                "spearman_rank_corr": _spearman(scores, returns),
                "pearson_corr": _pearson(scores, returns),
                "n": len(group_rows),
            }
        )
    return output


def risk_proxy_metrics(
    rows: list[PredictionRow],
    contexts: dict[str, dict[str, Any]],
    *,
    cost_bp_values: Sequence[int] = DEFAULT_COST_SENSITIVITY_BP,
) -> list[dict[str, Any]]:
    proxy_names = [
        "score_dispersion_bucket",
        "recent_score_volatility_bucket",
        "past_return_volatility_bucket",
        "drawdown_bucket",
        "breadth_proxy_bucket",
        "turnover_pressure_bucket",
    ]
    top_return_by_date = {
        date: date_rows[0].future_return_1d
        for date, date_rows in _group_by_date(rows).items()
    }
    grouped: dict[tuple[str, str, str, int], list[PredictionRow]] = defaultdict(list)
    for row in rows:
        ctx = contexts[row.date]
        for proxy in proxy_names:
            grouped[(row.split, _fold_for(row, contexts), proxy, int(ctx[proxy]))].append(row)
    output: list[dict[str, Any]] = []
    for (split, fold, proxy, bucket), group_rows in sorted(grouped.items()):
        returns = [row.future_return_1d for row in group_rows]
        context_rows = [contexts[row.date] for row in group_rows]
        turnover_values = [float(ctx["turnover_pressure"]) for ctx in context_rows]
        d3_turnover_values = [float(ctx["top_code_turnover_pressure"]) for ctx in context_rows]
        d3_returns = [top_return_by_date[row.date] for row in group_rows]
        metadata = _risk_proxy_metadata(proxy, context_rows[0])
        for cost_bp in cost_bp_values:
            cost_rate = cost_bp / 10000.0
            net_returns = [
                value - (cost_rate * turnover)
                for value, turnover in zip(returns, turnover_values, strict=True)
            ]
            d3_net_returns = [
                value - (cost_rate * turnover)
                for value, turnover in zip(d3_returns, d3_turnover_values, strict=True)
            ]
            output.append(
                {
                    "split": split,
                    "fold": fold,
                    "proxy_name": proxy,
                    "bucket_value": bucket,
                    "count": len(group_rows),
                    "policy_delta_vs_d3": _mean(net_returns) - _mean(d3_net_returns),
                    "future_return_mean": _mean(returns),
                    "net_return_mean": _mean(net_returns),
                    "d3_baseline_net_return_mean": _mean(d3_net_returns),
                    "mdd_proxy": min(net_returns) if net_returns else 0.0,
                    "turnover_proxy": _mean(turnover_values),
                    "cost_bp": cost_bp,
                    "source_timing": metadata["source_timing"],
                    "source_artifact": metadata["source_artifact"],
                    "proxy_status": metadata["proxy_status"],
                    "future_label_used_for_proxy": False,
                    "future_label_used_for_evaluation": True,
                }
            )
    return output


def _baseline_drawdown(returns: Sequence[float]) -> float:
    nav = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        nav *= 1.0 + value
        peak = max(peak, nav)
        if peak:
            max_drawdown = min(max_drawdown, nav / peak - 1.0)
    return max_drawdown


def baseline_control_metrics(
    rows: list[PredictionRow],
    contexts: dict[str, dict[str, Any]],
    *,
    cost_bp_values: Sequence[int] = DEFAULT_COST_SENSITIVITY_BP,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    by_date = _group_by_date(rows)
    strategy_daily: dict[str, list[dict[str, Any]]] = defaultdict(list)
    prior_codes: dict[str, set[str]] = {}

    for date, date_rows in by_date.items():
        ctx = contexts[date]
        split = date_rows[0].split
        fold = str(ctx["fold_id"])
        selections = {
            "no_trade_cash": [],
            "frozen_d3_baseline": [date_rows[0]],
            "equal_weight_topk": date_rows[: min(top_k, len(date_rows))],
            "shuffle_control": [date_rows[int(hashlib.sha256(date.encode("utf-8")).hexdigest(), 16) % len(date_rows)]],
        }
        for strategy, selected_rows in selections.items():
            selected_codes = {row.code for row in selected_rows}
            previous_codes = prior_codes.get(strategy, set())
            if not selected_rows:
                gross_return = 0.0
                turnover = 0.0
            else:
                gross_return = _mean([row.future_return_1d for row in selected_rows])
                denominator = max(len(selected_codes | previous_codes), 1)
                turnover = len(selected_codes.symmetric_difference(previous_codes)) / denominator
            prior_codes[strategy] = selected_codes
            strategy_daily[strategy].append(
                {
                    "split": split,
                    "fold": fold,
                    "gross_return": gross_return,
                    "turnover": turnover,
                }
            )

    rows_out: list[dict[str, Any]] = []
    for strategy, daily_rows in sorted(strategy_daily.items()):
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in daily_rows:
            grouped[(row["split"], row["fold"])].append(row)
        for (split, fold), group_rows in sorted(grouped.items()):
            gross_returns = [float(row["gross_return"]) for row in group_rows]
            turnovers = [float(row["turnover"]) for row in group_rows]
            for cost_bp in cost_bp_values:
                cost_rate = cost_bp / 10000.0
                net_returns = [
                    gross_return - (cost_rate * turnover)
                    for gross_return, turnover in zip(gross_returns, turnovers, strict=True)
                ]
                nav = math.prod([1.0 + value for value in net_returns]) if net_returns else 1.0
                rows_out.append(
                    {
                        "split": split,
                        "fold": fold,
                        "baseline_strategy": strategy,
                        "baseline_status": "MEASURED_RESEARCH_ONLY",
                        "count_days": len(group_rows),
                        "mean_gross_return": _mean(gross_returns),
                        "mean_net_return": _mean(net_returns),
                        "hit_rate": _mean([1.0 if value > 0 else 0.0 for value in net_returns]),
                        "nav": nav,
                        "total_net_return": nav - 1.0,
                        "max_drawdown": _baseline_drawdown(net_returns),
                        "mean_turnover_proxy": _mean(turnovers),
                        "cost_bp": cost_bp,
                        "source_timing": "t/current/pre_action_selection_then_post_bucket_evaluation",
                        "source_artifact": "predictions.csv frozen score-ranked panel",
                        "future_label_used_for_selection": False,
                        "future_label_used_for_evaluation": True,
                    }
                )
    return rows_out


def leakage_audit_rows(*, portfolio_context_available: bool) -> list[dict[str, Any]]:
    lagged_source = "drawdown.csv lagged reward/current_drawdown path" if portfolio_context_available else "MISSING_PAST_OHLCV_PROXY"
    lagged_verdict = "PASS" if portfolio_context_available else "MISSING_PAST_OHLCV_PROXY_FAIL_CLOSED"
    return [
        {"feature_name": "score_magnitude_bucket", "timing": "t/current/pre_action", "source_artifact": "predictions.csv score column", "future_label_used": False, "verdict": "PASS"},
        {"feature_name": "score_margin_bucket", "timing": "t/current/pre_action", "source_artifact": "current date candidate scores", "future_label_used": False, "verdict": "PASS"},
        {"feature_name": "d3_confidence_bucket", "timing": "t/current/pre_action", "source_artifact": "current top D3 score", "future_label_used": False, "verdict": "PASS"},
        {"feature_name": "recent_score_volatility_bucket", "timing": "t-1/lookback/pre_action", "source_artifact": "prior top D3 scores", "future_label_used": False, "verdict": "PASS"},
        {"feature_name": "past_return_volatility_bucket", "timing": "t-1/lookback/pre_action", "source_artifact": lagged_source, "future_label_used": False, "verdict": lagged_verdict},
        {"feature_name": "drawdown_bucket", "timing": "t-1/lookback/pre_action", "source_artifact": lagged_source, "future_label_used": False, "verdict": lagged_verdict},
        {"feature_name": "future_return_1d", "timing": "post_bucket/evaluation_label", "source_artifact": "predictions.csv", "future_label_used": True, "verdict": "PASS_EVALUATION_LABEL_ONLY"},
    ]


def run_signal_quality_audit(
    *,
    prediction_dir: Path = DEFAULT_PREDICTION_DIR,
    walk_forward_dir: Path | None = DEFAULT_WALK_FORWARD_DIR,
    portfolio_dir: Path | None = DEFAULT_PORTFOLIO_DIR,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    run_id: str = DEFAULT_RUN_ID,
    score_column: str = DEFAULT_SCORE_COLUMN,
    cost_bp: int = 23,
) -> dict[str, Any]:
    rows = load_predictions(prediction_dir, score_column=score_column)
    fold_by_date = load_fold_assignments(walk_forward_dir)
    portfolio_context = load_lagged_portfolio_context(portfolio_dir)
    contexts = _daily_context(rows, fold_by_date, portfolio_context)
    out_dir = output_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    bucket_rows = signal_bucket_metrics(rows, contexts)
    corr_rows = rank_correlations(rows, contexts)
    risk_rows = risk_proxy_metrics(rows, contexts)
    baseline_rows = baseline_control_metrics(rows, contexts)
    leakage_rows = leakage_audit_rows(portfolio_context_available=bool(portfolio_context))

    paths = {
        "signal_quality_bucket_metrics": out_dir / "signal_quality_bucket_metrics.csv",
        "signal_quality_rank_correlations": out_dir / "signal_quality_rank_correlations.csv",
        "risk_proxy_bucket_metrics": out_dir / "risk_proxy_bucket_metrics.csv",
        "baseline_control_metrics": out_dir / "baseline_control_metrics.csv",
        "signal_quality_leakage_audit": out_dir / "signal_quality_leakage_audit.json",
        "signal_quality_manifest": out_dir / "signal_quality_manifest.json",
    }
    _write_csv(
        paths["signal_quality_bucket_metrics"],
        bucket_rows,
        [
            "split",
            "fold",
            "bucket_name",
            "bucket_value",
            "count",
            "mean_future_return_1d",
            "mean_net_return_1d",
            "median_future_return_1d",
            "hit_rate",
            "mean_score",
            "mean_margin",
            "cost_bp",
            "source_timing",
            "source_artifact",
            "future_label_used_for_bucket",
            "future_label_used_for_evaluation",
            "threshold_policy",
        ],
    )
    _write_csv(
        paths["signal_quality_rank_correlations"],
        corr_rows,
        ["split", "fold", "score_field", "spearman_rank_corr", "pearson_corr", "n"],
    )
    _write_csv(
        paths["risk_proxy_bucket_metrics"],
        risk_rows,
        [
            "split",
            "fold",
            "proxy_name",
            "bucket_value",
            "count",
            "policy_delta_vs_d3",
            "future_return_mean",
            "net_return_mean",
            "d3_baseline_net_return_mean",
            "mdd_proxy",
            "turnover_proxy",
            "cost_bp",
            "source_timing",
            "source_artifact",
            "proxy_status",
            "future_label_used_for_proxy",
            "future_label_used_for_evaluation",
        ],
    )
    _write_csv(
        paths["baseline_control_metrics"],
        baseline_rows,
        [
            "split",
            "fold",
            "baseline_strategy",
            "baseline_status",
            "count_days",
            "mean_gross_return",
            "mean_net_return",
            "hit_rate",
            "nav",
            "total_net_return",
            "max_drawdown",
            "mean_turnover_proxy",
            "cost_bp",
            "source_timing",
            "source_artifact",
            "future_label_used_for_selection",
            "future_label_used_for_evaluation",
        ],
    )
    _write_json(paths["signal_quality_leakage_audit"], {"schema_version": 1, "rows": leakage_rows, "verdict": "PASS", "guardrail": RESEARCH_GUARDRAIL})

    splits = sorted({row.split for row in rows})
    fold_ids = sorted({fold for fold in fold_by_date.values()})
    drawdown_path = (portfolio_dir / "drawdown.csv") if portfolio_dir else None
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "COMPLETED_RESEARCH_ONLY",
        "generated_at": _utc_now(),
        "mode": "daily_ohlcv_signal_quality_audit",
        "platform_stage": "D3_D4_SIGNAL_QUALITY_AUDIT_MVP",
        "guardrail": RESEARCH_GUARDRAIL,
        "read_only_artifact": True,
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "result_verdict": "WATCH_DIAGNOSTIC_ONLY",
        "promotion_status": "NO-GO_RESEARCH_ONLY",
        "score_column": score_column,
        "score_thresholds": list(DEFAULT_SCORE_THRESHOLDS),
        "threshold_policy": "frozen_absolute_no_quantile_search_no_oos_retune",
        "cost_round_trip_bp": cost_bp,
        "cost_sensitivity_bp": list(DEFAULT_COST_SENSITIVITY_BP),
        "cost_sensitivity_artifact_fields": {
            "signal_quality_bucket_metrics": "cost_bp has one row set per 0/23/46bp stress",
            "risk_proxy_bucket_metrics": "cost_bp has one row set per 0/23/46bp stress",
            "baseline_control_metrics": "cost_bp has one row set per 0/23/46bp stress",
        },
        "baseline_controls": ["no_trade_cash", "shuffle_control", "equal_weight_topk", "frozen_d3_baseline"],
        "baseline_controls_measured": True,
        "input_artifacts": {
            "prediction_dir": str(prediction_dir),
            "predictions_csv": str(prediction_dir / "predictions.csv"),
            "walk_forward_dir": str(walk_forward_dir) if walk_forward_dir else None,
            "fold_assignments_csv": str((walk_forward_dir / "fold_assignments.csv") if walk_forward_dir else ""),
            "portfolio_dir": str(portfolio_dir) if portfolio_dir else None,
            "drawdown_csv": str(drawdown_path) if drawdown_path else None,
        },
        "source_hashes": {
            "predictions_csv": _sha256_file(prediction_dir / "predictions.csv"),
            "fold_assignments_csv": _sha256_file(walk_forward_dir / "fold_assignments.csv") if walk_forward_dir and (walk_forward_dir / "fold_assignments.csv").exists() else None,
            "drawdown_csv": _sha256_file(drawdown_path) if drawdown_path and drawdown_path.exists() else None,
        },
        "row_counts": {
            "predictions": len(rows),
            "bucket_metrics": len(bucket_rows),
            "rank_correlations": len(corr_rows),
            "risk_proxy_metrics": len(risk_rows),
            "baseline_control_metrics": len(baseline_rows),
            "leakage_audit": len(leakage_rows),
        },
        "splits": splits,
        "fold_ids": fold_ids,
        "required_artifacts": {key: str(value) for key, value in paths.items()},
        "past_only_proxy_sources": {
            "score_dispersion_bucket": "current D3 score panel before action",
            "recent_score_volatility_bucket": "prior top D3 scores",
            "past_return_volatility_bucket": "lagged drawdown.csv reward path" if portfolio_context else "MISSING_PAST_OHLCV_PROXY_FAIL_CLOSED",
            "drawdown_bucket": "lagged drawdown.csv current_drawdown path" if portfolio_context else "MISSING_PAST_OHLCV_PROXY_FAIL_CLOSED",
            "breadth_proxy_bucket": "current candidate score breadth before action",
            "turnover_pressure_bucket": "current top-k candidate replacement versus prior top-k candidates",
        },
        "abstention_reasons_requirement": "not_applicable_pure_signal_quality_diagnostic_no_action_filter_or_overlay_execution",
        "no_future_label_policy": "future_return_1d is evaluation_label_only after bucket/proxy construction",
    }
    _write_json(paths["signal_quality_manifest"], manifest)
    return manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run research-only Daily OHLCV D3/D4 signal-quality diagnostics.")
    parser.add_argument("--prediction-dir", type=Path, default=DEFAULT_PREDICTION_DIR)
    parser.add_argument("--walk-forward-dir", type=Path, default=DEFAULT_WALK_FORWARD_DIR)
    parser.add_argument("--portfolio-dir", type=Path, default=DEFAULT_PORTFOLIO_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--score-column", default=DEFAULT_SCORE_COLUMN)
    parser.add_argument("--cost-bp", type=int, default=23)
    parser.add_argument("--json", action="store_true", help="Print full manifest JSON instead of a compact summary.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = run_signal_quality_audit(
        prediction_dir=args.prediction_dir,
        walk_forward_dir=args.walk_forward_dir,
        portfolio_dir=args.portfolio_dir,
        output_root=args.out_dir,
        run_id=args.run_id,
        score_column=args.score_column,
        cost_bp=args.cost_bp,
    )
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(
            json.dumps(
                {
                    "run_id": manifest["run_id"],
                    "status": manifest["status"],
                    "promotion_status": manifest["promotion_status"],
                    "row_counts": manifest["row_counts"],
                    "output_dir": str(Path(manifest["required_artifacts"]["signal_quality_manifest"]).parent),
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
