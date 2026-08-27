"""Informe reproducible de la regla exacta que ejecuta el paper trader."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import evaluate_kronos_trend_4h as study

OUT = study.SOURCE / "paper_candidate_validation"


def returns_for(mode: str) -> tuple[np.ndarray, np.ndarray]:
    data = study.load()
    pairs = ((20, 100), (20, 200), (50, 100), (50, 200))
    allowed = study.kronos_ok(data, mode).fillna(False).to_numpy()
    trends = {(fast, slow): (data[f"ema_{fast}"] > data[f"ema_{slow}"]).to_numpy() for fast, slow in pairs}
    active = {pair: False for pair in pairs}
    equity = 1.0
    peak = 1.0
    halted = False
    day: str | None = None
    day_start = 1.0
    day_return = 0.0
    returns: list[float] = []
    exposures: list[float] = []
    for i, row in enumerate(data.itertuples(index=False)):
        before = equity
        daily_halt = day_return <= -0.04
        if equity / peak - 1 <= -0.20:
            halted = True
        desired: dict[tuple[int, int], bool] = {}
        for pair in pairs:
            trend = bool(trends[pair][i])
            if active[pair]:
                desired[pair] = trend and not daily_halt and not halted
            else:
                desired[pair] = trend and bool(allowed[i]) and not daily_halt and not halted
        exposure = sum(desired.values()) * 0.125
        turnover = sum(abs(float(desired[pair]) - float(active[pair])) for pair in pairs) * 0.125
        equity *= 1 - turnover * study.ONE_SIDE_COST
        # La rentabilidad pronosticada en esta fila termina al cierre de la vela
        # siguiente; Binance etiqueta esa vela por su apertura.
        exit_day = (row.exit_time + pd.Timedelta(hours=4)).strftime("%Y-%m-%d")
        if day != exit_day:
            day = exit_day
            day_start = equity
        equity *= 1 + exposure * float(row.market_return)
        day_return = equity / day_start - 1
        peak = max(peak, equity)
        returns.append(equity / before - 1)
        exposures.append(exposure)
        active = desired
    final_exposure = sum(active.values()) * 0.125
    if final_exposure:
        before = equity
        equity *= 1 - final_exposure * study.ONE_SIDE_COST
        returns[-1] = (1 + returns[-1]) * (equity / before) - 1
    return np.asarray(returns), np.asarray(exposures)


def metrics(returns: np.ndarray, position: np.ndarray) -> dict[str, float | int]:
    equity = np.r_[1.0, np.cumprod(1 + returns)]
    drawdown = equity / np.maximum.accumulate(equity) - 1
    std = returns.std(ddof=1)
    return {
        "return_pct": float((equity[-1] - 1) * 100),
        "max_drawdown_pct": float(drawdown.min() * 100),
        "annualized_sharpe": float(returns.mean() / std * np.sqrt(6 * 365)) if std else 0.0,
        "average_exposure_pct": float(position.mean() * 100),
    }


def main() -> int:
    data = study.load()
    candidate_returns, candidate_position = returns_for("risk")
    baseline_returns, baseline_position = returns_for("baseline_no_kronos")
    bounds = np.linspace(0, len(data), 7, dtype=int)
    folds = []
    for i in range(6):
        segment = slice(bounds[i], bounds[i + 1])
        folds.append(
            {
                "start": str(data.iloc[bounds[i]]["decision_time"]),
                "end": str(data.iloc[bounds[i + 1] - 1]["exit_time"]),
                "candidate": metrics(candidate_returns[segment], candidate_position[segment]),
                "baseline_without_kronos": metrics(baseline_returns[segment], baseline_position[segment]),
            }
        )
    final_start = int(len(data) * 0.75)
    final_slice = slice(final_start, len(data))
    full_candidate = metrics(candidate_returns, candidate_position)
    full_baseline = metrics(baseline_returns, baseline_position)
    final_candidate = metrics(candidate_returns[final_slice], candidate_position[final_slice])
    final_baseline = metrics(baseline_returns[final_slice], baseline_position[final_slice])
    report = {
        "rule": {
            "market": "BTCUSDT",
            "timeframe": "4h",
            "components": ["EMA20/100", "EMA20/200", "EMA50/100", "EMA50/200"],
            "direction": "long-only",
            "max_exposure": 0.50,
            "component_exposure": 0.125,
            "kronos_filter": "permitir entrada si std ensemble <= percentil 90 de las 1080 predicciones anteriores",
            "exit": "cruce bajista del componente",
            "fee_plus_slippage_per_side": study.ONE_SIDE_COST,
            "leverage": 1.0,
            "martingale": False,
        },
        "caveat": "La regla fue concebida tras observar este dataset; sólo el paper trading posterior es completamente no visto.",
        "full_period": full_candidate,
        "full_period_baseline_without_kronos": full_baseline,
        "full_period_kronos_incremental_pct_points": full_candidate["return_pct"] - full_baseline["return_pct"],
        "last_25pct_diagnostic": final_candidate,
        "last_25pct_baseline_without_kronos": final_baseline,
        "last_25pct_kronos_incremental_pct_points": final_candidate["return_pct"] - final_baseline["return_pct"],
        "positive_six_month_folds": sum(f["candidate"]["return_pct"] > 0 for f in folds),
        "folds": folds,
        "paper_gate": bool(
            full_candidate["return_pct"] > 0
            and full_candidate["max_drawdown_pct"] > -20
            and final_candidate["return_pct"] > 0
            and final_candidate["max_drawdown_pct"] > -12
            and sum(f["candidate"]["return_pct"] > 0 for f in folds) >= 4
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
