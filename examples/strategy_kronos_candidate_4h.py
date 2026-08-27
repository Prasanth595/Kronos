"""Candidata conservadora Kronos 4h con selección train y evaluación test."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "outputs" / "btc_4h_backtest" / "predictions.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "kronos_candidate_4h"
INITIAL_BANK = 10_000.0
FEE_RATE = 0.001
SLIPPAGE = 0.0002
TRAIN_FRACTION = 0.67
MIN_TRAIN_TRADES = 30


def net_trade_return(frame: pd.DataFrame) -> pd.Series:
    entry = frame["entry"] * (1 + SLIPPAGE)
    exit_price = frame["exit"] * (1 - SLIPPAGE)
    gross = exit_price / entry - 1
    fees = FEE_RATE * (1 + exit_price / entry)
    return gross - fees


def select_threshold(train: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    candidates: list[dict[str, float | int]] = []
    for threshold in np.arange(0.005, 0.0301, 0.001):
        selected = train[train["predicted_return"] > threshold]
        if len(selected) < MIN_TRAIN_TRADES:
            continue
        returns = net_trade_return(selected)
        candidates.append(
            {
                "threshold": float(threshold),
                "trades": len(selected),
                "mean_net_return": float(returns.mean()),
                "total_net_return": float(returns.sum()),
            }
        )
    table = pd.DataFrame(candidates)
    if table.empty:
        raise RuntimeError("No hay umbrales con suficientes operaciones de entrenamiento.")
    best = table.sort_values(["mean_net_return", "trades"], ascending=[False, False]).iloc[0]
    return float(best["threshold"]), table


def simulate(frame: pd.DataFrame, threshold: float, initial_bank: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    equity = initial_bank
    curve: list[dict[str, object]] = [{"timestamp": frame.iloc[0]["decision_time"], "equity": equity}]
    trades: list[dict[str, object]] = []
    for row in frame.itertuples(index=False):
        if row.predicted_return > threshold:
            entry_exec = row.entry * (1 + SLIPPAGE)
            exit_exec = row.exit * (1 - SLIPPAGE)
            gross_return = exit_exec / entry_exec - 1
            fees_return = FEE_RATE * (1 + exit_exec / entry_exec)
            net_return = gross_return - fees_return
            pnl = equity * net_return
            before = equity
            equity = max(0.0, equity + pnl)
            trades.append(
                {
                    "decision_time": row.decision_time,
                    "exit_time": row.exit_time,
                    "entry": row.entry,
                    "exit": row.exit,
                    "predicted_return": row.predicted_return,
                    "actual_return": row.exit / row.entry - 1,
                    "net_return": net_return,
                    "pnl": pnl,
                    "equity_before": before,
                    "equity_after": equity,
                }
            )
        curve.append({"timestamp": row.exit_time, "equity": equity})
    return pd.DataFrame(trades), pd.DataFrame(curve).drop_duplicates("timestamp", keep="last")


def metrics(trades: pd.DataFrame, curve: pd.DataFrame, initial: float) -> dict[str, float | int]:
    peak = curve["equity"].cummax()
    drawdown = curve["equity"] / peak - 1
    final = float(curve["equity"].iloc[-1])
    losses = abs(float(trades.loc[trades["pnl"] < 0, "pnl"].sum()))
    profits = float(trades.loc[trades["pnl"] > 0, "pnl"].sum())
    return {
        "initial_bank": initial,
        "final_equity": final,
        "return_pct": (final / initial - 1) * 100,
        "max_drawdown_pct": float(drawdown.min()) * 100,
        "trades": len(trades),
        "win_rate_pct": float((trades["pnl"] > 0).mean()) * 100 if len(trades) else 0.0,
        "profit_factor": profits / losses if losses else float("inf"),
    }


def main() -> int:
    predictions = pd.read_csv(SOURCE)
    for column in ("decision_time", "exit_time"):
        predictions[column] = pd.to_datetime(predictions[column], utc=True)
    split = int(len(predictions) * TRAIN_FRACTION)
    train = predictions.iloc[:split].copy()
    test = predictions.iloc[split:].copy()
    threshold, search = select_threshold(train)

    train_trades, train_curve = simulate(train, threshold, INITIAL_BANK)
    train_stats = metrics(train_trades, train_curve, INITIAL_BANK)
    test_trades, test_curve = simulate(test, threshold, INITIAL_BANK)
    test_stats = metrics(test_trades, test_curve, INITIAL_BANK)
    all_trades, all_curve = simulate(predictions, threshold, INITIAL_BANK)
    all_stats = metrics(all_trades, all_curve, INITIAL_BANK)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    search.to_csv(OUTPUT_DIR / "threshold_search_train_only.csv", index=False)
    train_trades.to_csv(OUTPUT_DIR / "train_trades.csv", index=False)
    test_trades.to_csv(OUTPUT_DIR / "unseen_test_trades.csv", index=False)
    all_trades.to_csv(OUTPUT_DIR / "all_trades.csv", index=False)
    all_curve.to_csv(OUTPUT_DIR / "equity_curve.csv", index=False)
    report = {
        "rule": {
            "timeframe": "4h",
            "direction": "LONG only",
            "threshold": threshold,
            "holding_period": "1 candle (4h)",
            "exposure": "1x equity",
            "fibonacci": False,
            "fee_rate_per_side": FEE_RATE,
            "slippage_per_side": SLIPPAGE,
        },
        "train": train_stats,
        "unseen_test": test_stats,
        "full_period": all_stats,
        "split_timestamp": str(test.iloc[0]["decision_time"]),
    }
    with (OUTPUT_DIR / "report.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)

    figure, axis = plt.subplots(figsize=(16, 8))
    axis.plot(pd.to_datetime(all_curve["timestamp"]), all_curve["equity"], label="Kronos 4h LONG", linewidth=1.7)
    axis.axvline(test.iloc[0]["decision_time"], color="#dc2626", linestyle="--", label="Inicio test no visto")
    axis.axhline(INITIAL_BANK, color="gray", linestyle=":", label="Banca inicial")
    axis.set_title(f"Candidata Kronos 4h · LONG si predicción > {threshold:.1%} · salida tras 4h")
    axis.set_ylabel("Equity (USD)")
    axis.set_xlabel("Fecha")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(OUTPUT_DIR / "candidate_equity.png", dpi=180, bbox_inches="tight")
    plt.close(figure)

    print(f"✅ Umbral elegido sólo con train: {threshold:.2%}")
    for name, stats in (("TRAIN", train_stats), ("TEST NO VISTO", test_stats), ("TOTAL", all_stats)):
        print(
            f"{name}: ${stats['initial_bank']:,.2f} → ${stats['final_equity']:,.2f} | "
            f"{stats['return_pct']:+.2f}% | DD {stats['max_drawdown_pct']:.2f}% | "
            f"{stats['trades']} trades | acierto {stats['win_rate_pct']:.2f}% | PF {stats['profit_factor']:.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
