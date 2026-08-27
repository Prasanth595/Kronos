"""Evaluación temporal robusta del ensemble Kronos BTCUSDT 4h.

La selección usa únicamente el primer 80 % del histórico y el último 20 % queda
bloqueado hasta elegir una única regla. No utiliza apalancamiento ni martingala.
"""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "outputs" / "kronos_research_4h_3y"
OUTPUT_DIR = SOURCE_DIR / "evaluation"
INITIAL_BANK = 10_000.0
FEE_PER_SIDE = 0.001
SLIPPAGE_PER_SIDE = 0.0002
ROUNDTRIP_COST = 2 * (FEE_PER_SIDE + SLIPPAGE_PER_SIDE)
LOCKED_FRACTION = 0.20


def load_data() -> pd.DataFrame:
    predictions = pd.read_csv(SOURCE_DIR / "ensemble_predictions.csv")
    market = pd.read_csv(SOURCE_DIR / "market_data_4h.csv")
    for column in ("decision_time", "exit_time"):
        predictions[column] = pd.to_datetime(predictions[column], utc=True)
    market["timestamps"] = pd.to_datetime(market["timestamps"], utc=True)
    market = market.sort_values("timestamps")
    market["sma50"] = market["close"].rolling(50).mean()
    market["trend50"] = market["close"] > market["sma50"]
    data = predictions.merge(
        market[["timestamps", "trend50"]], left_on="decision_time", right_on="timestamps", how="left"
    ).drop(columns="timestamps")
    seed_columns = [column for column in data if column.startswith("predicted_return_seed_")]
    data["positive_votes"] = (data[seed_columns] > 0).sum(axis=1)
    # Ejecución conservadora: deslizamiento y comisión en entrada y salida.
    entry_exec = data["entry"] * (1 + SLIPPAGE_PER_SIDE)
    exit_exec = data["exit"] * (1 - SLIPPAGE_PER_SIDE)
    ratio = exit_exec / entry_exec
    data["net_trade_return"] = ratio - 1 - FEE_PER_SIDE * (1 + ratio)
    return data


def signal(frame: pd.DataFrame, rule: dict[str, object]) -> pd.Series:
    selected = (frame["predicted_return_mean"] > rule["threshold"]) & (
        frame["positive_votes"] >= rule["votes"]
    )
    if rule["std_cap"] is not None:
        selected &= frame["predicted_return_std"] <= rule["std_cap"]
    if rule["trend50"]:
        selected &= frame["trend50"].fillna(False)
    return selected


def simulate(frame: pd.DataFrame, rule: dict[str, object]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float | int]]:
    chosen = signal(frame, rule).to_numpy()
    returns = np.where(chosen, frame["net_trade_return"].to_numpy(), 0.0)
    equity = INITIAL_BANK * np.cumprod(1 + returns)
    curve = pd.DataFrame({"timestamp": frame["exit_time"], "equity": equity, "bar_return": returns})
    trades = frame.loc[chosen].copy()
    trades["strategy_return"] = trades["net_trade_return"]
    trades["equity_after"] = equity[chosen]
    peak = np.maximum.accumulate(np.r_[INITIAL_BANK, equity])
    dd = np.r_[INITIAL_BANK, equity] / peak - 1
    wins = trades.loc[trades["strategy_return"] > 0, "strategy_return"].sum()
    losses = -trades.loc[trades["strategy_return"] < 0, "strategy_return"].sum()
    std = returns.std(ddof=1)
    stats: dict[str, float | int] = {
        "start": str(frame.iloc[0]["decision_time"]),
        "end": str(frame.iloc[-1]["exit_time"]),
        "final_equity": float(equity[-1]),
        "return_pct": float((equity[-1] / INITIAL_BANK - 1) * 100),
        "max_drawdown_pct": float(dd.min() * 100),
        "trades": int(chosen.sum()),
        "win_rate_pct": float((trades["strategy_return"] > 0).mean() * 100) if len(trades) else 0.0,
        "profit_factor": float(wins / losses) if losses > 0 else float("inf"),
        "annualized_sharpe": float(returns.mean() / std * np.sqrt(6 * 365)) if std > 0 else 0.0,
    }
    return trades, curve, stats


def rules() -> list[dict[str, object]]:
    return [
        {"threshold": threshold, "votes": votes, "std_cap": std_cap, "trend50": trend50}
        for threshold, votes, std_cap, trend50 in product(
            (0.005, 0.010, 0.015, 0.020, 0.025), (2, 3), (None, 0.01), (False, True)
        )
    ]


def main() -> int:
    data = load_data()
    locked_start = int(len(data) * (1 - LOCKED_FRACTION))
    research = data.iloc[:locked_start].copy()
    locked = data.iloc[locked_start:].copy()
    # Cuatro bloques cronológicos; el primero da contexto y los tres siguientes
    # son las ventanas de validación walk-forward para comparar reglas.
    bounds = np.linspace(0, len(research), 5, dtype=int)
    validation_slices = [research.iloc[bounds[i] : bounds[i + 1]] for i in range(1, 4)]

    rows: list[dict[str, object]] = []
    for rule_id, rule in enumerate(rules()):
        fold_stats = [simulate(fold, rule)[2] for fold in validation_slices]
        trades = [int(stats["trades"]) for stats in fold_stats]
        returns = [float(stats["return_pct"]) for stats in fold_stats]
        dds = [float(stats["max_drawdown_pct"]) for stats in fold_stats]
        rows.append(
            {
                "rule_id": rule_id,
                **rule,
                "min_fold_trades": min(trades),
                "total_validation_trades": sum(trades),
                "median_fold_return_pct": float(np.median(returns)),
                "worst_fold_return_pct": min(returns),
                "mean_fold_return_pct": float(np.mean(returns)),
                "worst_fold_drawdown_pct": min(dds),
                "positive_folds": sum(value > 0 for value in returns),
            }
        )
    ranking = pd.DataFrame(rows)
    eligible = ranking[(ranking["min_fold_trades"] >= 10) & (ranking["positive_folds"] >= 2)].copy()
    if eligible.empty:
        eligible = ranking[ranking["total_validation_trades"] >= 30].copy()
    chosen_row = eligible.sort_values(
        ["median_fold_return_pct", "worst_fold_return_pct", "total_validation_trades"],
        ascending=[False, False, False],
    ).iloc[0]
    chosen = {
        "threshold": float(chosen_row["threshold"]),
        "votes": int(chosen_row["votes"]),
        "std_cap": None if pd.isna(chosen_row["std_cap"]) else float(chosen_row["std_cap"]),
        "trend50": bool(chosen_row["trend50"]),
    }

    research_trades, research_curve, research_stats = simulate(research, chosen)
    locked_trades, locked_curve, locked_stats = simulate(locked, chosen)
    all_trades, all_curve, all_stats = simulate(data, chosen)
    buy_hold_return = float((locked.iloc[-1]["exit"] / locked.iloc[0]["entry"] - 1) * 100)
    pass_gate = bool(
        locked_stats["trades"] >= 20
        and locked_stats["return_pct"] > 0
        and locked_stats["profit_factor"] > 1.10
        and locked_stats["max_drawdown_pct"] > -15
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ranking.to_csv(OUTPUT_DIR / "validation_ranking.csv", index=False)
    research_trades.to_csv(OUTPUT_DIR / "research_trades.csv", index=False)
    locked_trades.to_csv(OUTPUT_DIR / "locked_test_trades.csv", index=False)
    all_trades.to_csv(OUTPUT_DIR / "all_trades.csv", index=False)
    all_curve.to_csv(OUTPUT_DIR / "equity_curve.csv", index=False)
    report = {
        "method": "40 candidates predefined; 3 chronological validation folds; final 20% locked",
        "costs": {"fee_per_side": FEE_PER_SIDE, "slippage_per_side": SLIPPAGE_PER_SIDE, "approx_roundtrip": ROUNDTRIP_COST},
        "chosen_rule": chosen,
        "validation_summary": chosen_row.to_dict(),
        "research_80pct": research_stats,
        "locked_test_20pct": {**locked_stats, "buy_hold_return_pct": buy_hold_return},
        "full_period": all_stats,
        "paper_trade_gate_passed": pass_gate,
    }
    with (OUTPUT_DIR / "report.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)

    fig, axis = plt.subplots(figsize=(15, 7))
    axis.plot(all_curve["timestamp"], all_curve["equity"], label="Kronos ensemble 4h", linewidth=1.6)
    axis.axvline(locked.iloc[0]["decision_time"], color="red", linestyle="--", label="Test final bloqueado")
    axis.axhline(INITIAL_BANK, color="gray", linestyle=":")
    axis.set(title="Validación multianual Kronos 4h", xlabel="Fecha", ylabel="Equity simulada (USD)")
    axis.grid(alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "equity.png", dpi=180)
    plt.close(fig)

    print(f"Regla elegida sin mirar test final: {chosen}")
    print(f"RESEARCH: {research_stats}")
    print(f"LOCKED TEST: {locked_stats} | buy&hold {buy_hold_return:+.2f}%")
    print(f"GATE PAPER: {'APROBADO' if pass_gate else 'RECHAZADO'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
