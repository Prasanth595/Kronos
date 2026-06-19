"""Small deterministic rankers for daily OHLCV research artifacts.

These helpers intentionally avoid black-box training stacks.  They fit only on the
D2 train split, expose their coefficients, and are used as supervised baselines
rather than profit/live readiness evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable


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


@dataclass(frozen=True)
class LinearRankerModel:
    feature_columns: tuple[str, ...]
    target_column: str
    means: dict[str, float]
    stds: dict[str, float]
    weights: dict[str, float]
    intercept: float
    train_row_count: int
    model_kind: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_kind": self.model_kind,
            "target_column": self.target_column,
            "feature_columns": list(self.feature_columns),
            "means": self.means,
            "stds": self.stds,
            "weights": self.weights,
            "intercept": self.intercept,
            "train_row_count": self.train_row_count,
            "training_policy": "fit_train_split_only_no_oos_retuning",
        }


def _mean(values: Iterable[float]) -> float:
    clean = list(values)
    return sum(clean) / len(clean) if clean else 0.0


def _std(values: Iterable[float]) -> float:
    clean = list(values)
    if not clean:
        return 1.0
    avg = _mean(clean)
    var = sum((value - avg) ** 2 for value in clean) / len(clean)
    return math.sqrt(var) or 1.0


def _eligible_train_rows(rows: Iterable[dict[str, Any]], target_column: str) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if str(row.get("split")) == "train"
        and row.get("eligible_for_training") in {True, "True", "true", "1", 1}
        and _safe_float(row.get(target_column)) is not None
    ]


def fit_linear_ranker(
    rows: Iterable[dict[str, Any]],
    *,
    feature_columns: Iterable[str],
    target_column: str = "future_return_1d",
    model_kind: str = "supervised_linear_ranker",
) -> LinearRankerModel:
    """Fit transparent correlation weights on train rows only."""

    features = tuple(str(col) for col in feature_columns)
    train_rows = _eligible_train_rows(rows, target_column)
    if not train_rows:
        raise ValueError("No eligible train rows available for ranker fit")
    means: dict[str, float] = {}
    stds: dict[str, float] = {}
    for column in features:
        values = [_safe_float(row.get(column)) for row in train_rows]
        clean = [value for value in values if value is not None]
        means[column] = _mean(clean)
        stds[column] = _std(clean)
    targets = [_safe_float(row.get(target_column)) for row in train_rows]
    y_values = [target if target is not None else 0.0 for target in targets]
    y_mean = _mean(y_values)
    weights: dict[str, float] = {}
    for column in features:
        xs: list[float] = []
        ys: list[float] = []
        for row, target in zip(train_rows, y_values):
            x = _safe_float(row.get(column))
            if x is None:
                continue
            xs.append((x - means[column]) / stds[column])
            ys.append(target - y_mean)
        weights[column] = _mean([x * y for x, y in zip(xs, ys)]) if xs else 0.0
    return LinearRankerModel(
        feature_columns=features,
        target_column=target_column,
        means=means,
        stds=stds,
        weights=weights,
        intercept=y_mean,
        train_row_count=len(train_rows),
        model_kind=model_kind,
    )


def score_row(model: LinearRankerModel, row: dict[str, Any]) -> float:
    score = model.intercept
    for column in model.feature_columns:
        value = _safe_float(row.get(column))
        if value is None:
            value = model.means[column]
        score += model.weights[column] * ((value - model.means[column]) / model.stds[column])
    return score


def score_rows(model: LinearRankerModel, rows: Iterable[dict[str, Any]], *, output_column: str = "supervised_score") -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        out[output_column] = score_row(model, row)
        scored.append(out)
    return scored


def sigmoid(value: float) -> float:
    clipped = max(-40.0, min(40.0, value))
    return 1.0 / (1.0 + math.exp(-clipped))


def fit_direction_classifier(
    rows: Iterable[dict[str, Any]],
    *,
    feature_columns: Iterable[str],
    target_column: str = "future_direction_1d",
) -> LinearRankerModel:
    return fit_linear_ranker(
        rows,
        feature_columns=feature_columns,
        target_column=target_column,
        model_kind="supervised_direction_classifier",
    )


def score_direction_probability(model: LinearRankerModel, row: dict[str, Any]) -> float:
    return sigmoid(score_row(model, row))


__all__ = [
    "LinearRankerModel",
    "fit_direction_classifier",
    "fit_linear_ranker",
    "score_direction_probability",
    "score_row",
    "score_rows",
    "sigmoid",
]
