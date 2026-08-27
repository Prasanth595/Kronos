"""Evalúa una estrategia tendencial 4h con Kronos como filtro de entrada.

La posición se mantiene hasta que termina la tendencia; Kronos no provoca
entradas/salidas cada vela, evitando que las comisiones destruyan el resultado.
Este estudio no usa apalancamiento ni martingala.
"""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outputs" / "kronos_research_4h_3y"
OUT = SOURCE / "trend_evaluation"
INITIAL = 10_000.0
EXPOSURE = 0.5
ONE_SIDE_COST = 0.0012  # 0.10 % comisión + 0.02 % slippage


def load() -> pd.DataFrame:
    p = pd.read_csv(SOURCE / "ensemble_predictions.csv")
    m = pd.read_csv(SOURCE / "market_data_4h.csv")
    p["decision_time"] = pd.to_datetime(p["decision_time"], utc=True)
    p["exit_time"] = pd.to_datetime(p["exit_time"], utc=True)
    m["timestamps"] = pd.to_datetime(m["timestamps"], utc=True)
    p = p.merge(
        m[["timestamps", "close"]], left_on="decision_time", right_on="timestamps", how="left"
    ).drop(columns="timestamps")
    seeds = [c for c in p if c.startswith("predicted_return_seed_")]
    p["positive_votes"] = (p[seeds] > 0).sum(axis=1)
    # Umbral calculado sólo con observaciones anteriores (aprox. 180 días).
    p["std_q90_past"] = p["predicted_return_std"].shift(1).rolling(1080, min_periods=270).quantile(0.90)
    p["market_return"] = p["exit"] / p["entry"] - 1
    for span in (20, 50, 100, 200):
        p[f"ema_{span}"] = p["close"].ewm(span=span, adjust=False).mean()
    return p


def kronos_ok(frame: pd.DataFrame, mode: str) -> pd.Series:
    if mode == "loose_direction":
        return (frame["predicted_return_mean"] > -0.01) & (frame["positive_votes"] >= 1)
    if mode == "consensus":
        return (frame["predicted_return_mean"] > 0) & (frame["positive_votes"] >= 2)
    if mode == "risk":
        return frame["predicted_return_std"] <= frame["std_q90_past"]
    if mode == "loose_plus_risk":
        return (
            (frame["predicted_return_mean"] > -0.01)
            & (frame["positive_votes"] >= 1)
            & (frame["predicted_return_std"] <= frame["std_q90_past"])
        )
    if mode == "baseline_no_kronos":
        return pd.Series(True, index=frame.index)
    raise ValueError(mode)


def positions(frame: pd.DataFrame, fast: int, slow: int, mode: str) -> np.ndarray:
    fast_ma = frame[f"ema_{fast}"]
    slow_ma = frame[f"ema_{slow}"]
    trend = (fast_ma > slow_ma).to_numpy()
    allowed = kronos_ok(frame, mode).fillna(False).to_numpy()
    result = np.zeros(len(frame), dtype=float)
    active = False
    for i in range(len(frame)):
        if active and not trend[i]:
            active = False
        elif not active and trend[i] and allowed[i]:
            active = True
        result[i] = EXPOSURE if active else 0.0
    return result


def evaluate(frame: pd.DataFrame, fast: int, slow: int, mode: str) -> dict[str, float | int]:
    pos = positions(frame, fast, slow, mode)
    turnover = np.abs(np.diff(np.r_[0.0, pos]))
    returns = pos * frame["market_return"].to_numpy() - turnover * ONE_SIDE_COST
    # Liquidación al final del segmento para no esconder el coste de salida.
    returns[-1] -= pos[-1] * ONE_SIDE_COST
    equity = np.cumprod(1 + returns)
    path = np.r_[1.0, equity]
    dd = path / np.maximum.accumulate(path) - 1
    entries = int(((pos > 0) & (np.r_[0.0, pos[:-1]] == 0)).sum())
    return {
        "return_pct": float((equity[-1] - 1) * 100),
        "max_drawdown_pct": float(dd.min() * 100),
        "entries": entries,
        "exposure_pct": float((pos > 0).mean() * EXPOSURE * 100),
    }


def main() -> int:
    data = load()
    modes = ("loose_direction", "consensus", "risk", "loose_plus_risk")
    candidates = list(product((20, 50), (100, 200), modes))
    selection_end = int(len(data) * 0.75)
    selection = data.iloc[:selection_end]
    final = data.iloc[selection_end:]
    bounds = np.linspace(0, len(selection), 5, dtype=int)
    folds = [selection.iloc[bounds[i] : bounds[i + 1]].copy() for i in range(4)]
    rows: list[dict[str, object]] = []
    for rule_id, (fast, slow, mode) in enumerate(candidates):
        stats = [evaluate(fold, fast, slow, mode) for fold in folds]
        fold_returns = [float(x["return_pct"]) for x in stats]
        rows.append(
            {
                "rule_id": rule_id,
                "fast": fast,
                "slow": slow,
                "kronos_mode": mode,
                "positive_folds": sum(x > 0 for x in fold_returns),
                "median_fold_return_pct": float(np.median(fold_returns)),
                "worst_fold_return_pct": min(fold_returns),
                "worst_fold_drawdown_pct": min(float(x["max_drawdown_pct"]) for x in stats),
                "total_entries": sum(int(x["entries"]) for x in stats),
            }
        )
    ranking = pd.DataFrame(rows)
    eligible = ranking[(ranking.positive_folds >= 3) & (ranking.total_entries >= 8)]
    if eligible.empty:
        eligible = ranking[ranking.total_entries >= 8]
    chosen_row = eligible.sort_values(
        ["median_fold_return_pct", "worst_fold_return_pct", "worst_fold_drawdown_pct"],
        ascending=False,
    ).iloc[0]
    rule = {
        "fast": int(chosen_row.fast),
        "slow": int(chosen_row.slow),
        "mode": str(chosen_row.kronos_mode),
    }
    selected_stats = evaluate(selection, **rule)
    final_stats = evaluate(final, **rule)
    full_stats = evaluate(data, **rule)
    baseline = evaluate(final, rule["fast"], rule["slow"], "baseline_no_kronos")
    gate = bool(
        final_stats["return_pct"] > 0
        and final_stats["max_drawdown_pct"] > -20
        and final_stats["entries"] >= 2
        and chosen_row.positive_folds >= 3
    )
    report = {
        "warning": "El tramo final ya fue observado por un estudio direccional anterior; sirve como diagnóstico, no como test virgen.",
        "method": "16 reglas predefinidas, cuatro folds temporales de selección y último 25% diagnóstico",
        "exposure": EXPOSURE,
        "one_side_cost": ONE_SIDE_COST,
        "chosen_rule": rule,
        "selection_row": chosen_row.to_dict(),
        "selection_75pct": selected_stats,
        "final_25pct": final_stats,
        "final_baseline_without_kronos": baseline,
        "full_period": full_stats,
        "historical_gate_passed": gate,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    ranking.to_csv(OUT / "ranking.csv", index=False)
    with (OUT / "report.json").open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
