"""Recalcula el backtest 10m permitiendo múltiples entradas en la misma dirección."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if os.environ.get("HSA_OVERRIDE_GFX_VERSION") == "11.0.0":
    os.environ.pop("HSA_OVERRIDE_GFX_VERSION")

import pandas as pd
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, EXAMPLES_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from backtest_btc_kronos_4h import Config, calculate_metrics, fibonacci_units, save_outputs

SOURCE_DIR = PROJECT_ROOT / "outputs" / "btc_10m_backtest"
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "btc_10m_backtest_separate"


def simulate_pyramiding(
    predictions: pd.DataFrame, config: Config, allowed_direction: int
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    equity = config.initial_bank
    loss_streak = 0
    positions: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []
    skipped_no_margin = 0
    curve = [{"timestamp": predictions.iloc[0]["decision_time"], "equity": equity}]
    final_time = predictions.iloc[-1]["exit_time"]

    for row in predictions.itertuples(index=False):
        if equity <= 0:
            break
        signal = 1 if row.predicted_return > config.threshold else -1 if row.predicted_return < -config.threshold else 0
        # Cada ejecución representa una estrategia direccional independiente.
        if signal == allowed_direction:
            units = fibonacci_units(loss_streak)
            margin = config.initial_bank * config.base_margin_fraction * units
            reserved_margin = sum(float(position["margin"]) for position in positions)
            available_margin = max(0.0, equity - reserved_margin)
            if available_margin >= margin:
                entry_exec = row.entry * (1 + config.slippage_rate * signal)
                stop_distance = config.stop_liquidation_fraction / config.leverage
                target_distance = config.take_profit_roi / config.leverage
                notional = margin * config.leverage
                positions.append(
                    {
                        "decision_time": row.decision_time,
                        "direction": signal,
                        "side": "LONG" if signal == 1 else "SHORT",
                        "entry": row.entry,
                        "entry_exec": entry_exec,
                        "predicted_close": row.predicted_close,
                        "predicted_return": row.predicted_return,
                        "fibonacci_units": units,
                        "margin": margin,
                        "notional": notional,
                        "quantity": notional / entry_exec,
                        "stop_price": entry_exec * (1 - signal * stop_distance),
                        "take_profit_price": entry_exec * (1 + signal * target_distance),
                        "liquidation_price": entry_exec * (1 - signal / config.leverage),
                        "equity_before": equity,
                        "holding_bars": 0,
                    }
                )
            else:
                skipped_no_margin += 1

        survivors: list[dict[str, object]] = []
        unrealized = 0.0
        for position in positions:
            position["holding_bars"] = int(position["holding_bars"]) + 1
            side = int(position["direction"])
            stop = float(position["stop_price"])
            target = float(position["take_profit_price"])
            liquidation = float(position["liquidation_price"])
            liquidated = (side == 1 and row.next_open <= liquidation) or (
                side == -1 and row.next_open >= liquidation
            )
            stop_hit = (side == 1 and row.next_low <= stop) or (side == -1 and row.next_high >= stop)
            target_hit = (side == 1 and row.next_high >= target) or (side == -1 and row.next_low <= target)

            reason: str | None = None
            raw_exit: float | None = None
            if liquidated:
                reason = "LIQUIDATION"
            elif stop_hit:
                reason, raw_exit = "STOP_LOSS", stop
            elif target_hit:
                reason, raw_exit = "TAKE_PROFIT", target
            elif row.exit_time == final_time:
                reason, raw_exit = "END_OF_TEST", row.exit

            if reason is None:
                unrealized += side * float(position["quantity"]) * (
                    row.exit - float(position["entry_exec"])
                )
                survivors.append(position)
                continue

            margin = float(position["margin"])
            if liquidated:
                exit_exec = liquidation
                gross_pnl, fees, net_pnl = -margin, 0.0, -margin
            else:
                exit_exec = float(raw_exit) * (1 - config.slippage_rate * side)
                quantity = float(position["quantity"])
                gross_pnl = side * quantity * (exit_exec - float(position["entry_exec"]))
                fees = config.fee_rate * (float(position["notional"]) + quantity * exit_exec)
                net_pnl = max(gross_pnl - fees, -margin)
            equity = max(0.0, equity + net_pnl)
            loss_streak = 0 if net_pnl > 0 else loss_streak + 1
            trades.append(
                {
                    **position,
                    "exit_time": row.exit_time,
                    "exit": raw_exit if raw_exit is not None else liquidation,
                    "exit_exec": exit_exec,
                    "exit_reason": reason,
                    "liquidated": liquidated,
                    "gross_pnl": gross_pnl,
                    "fees": fees,
                    "net_pnl": net_pnl,
                    "equity_after": equity,
                    "loss_streak_after": loss_streak,
                }
            )
        positions = survivors
        curve.append({"timestamp": row.exit_time, "equity": max(0.0, equity + unrealized)})

    return pd.DataFrame(trades), pd.DataFrame(curve).drop_duplicates("timestamp", keep="last"), skipped_no_margin


def main() -> int:
    predictions_file = SOURCE_DIR / "predictions.csv"
    if not predictions_file.exists():
        raise FileNotFoundError(f"No existe {predictions_file}")
    predictions = pd.read_csv(predictions_file)
    for column in ("decision_time", "exit_time"):
        predictions[column] = pd.to_datetime(predictions[column], utc=True)

    print("✅ Backtests 10m independientes con múltiples posiciones")
    curves: dict[str, pd.DataFrame] = {}
    strategy_metrics: dict[str, dict[str, object]] = {}
    for name, direction in (("LONG", 1), ("SHORT", -1)):
        config = Config(
            ticker="BTCUSDT",
            timeframe=f"10m · estrategia {name}",
            months=6,
            initial_bank=5_000.0,
            threshold=0.005,
            leverage=10.0,
            base_margin_fraction=0.05,
            fee_rate=0.001,
            slippage_rate=0.0002,
            stop_liquidation_fraction=0.90,
            take_profit_roi=1.0,
            lookback=400,
            batch_size=16,
            seed=42,
        )
        trades, curve, skipped = simulate_pyramiding(predictions, config, direction)
        metrics = calculate_metrics(predictions, trades, curve, config)
        metrics["signals_skipped_no_margin"] = skipped
        metrics["strategy_direction"] = name
        output_dir = OUTPUT_ROOT / name.lower()
        save_outputs(predictions, trades, curve, metrics, config, output_dir)
        curves[name] = curve.copy()
        strategy_metrics[name] = metrics
        print(f"\n{name}")
        print(f"  Banca: ${config.initial_bank:,.2f} → ${metrics['final_equity']:,.2f}")
        print(f"  Rentabilidad: {metrics['total_return_pct']:.2f}%")
        print(f"  Drawdown: {metrics['max_drawdown_pct']:.2f}%")
        print(f"  Operaciones: {metrics['trades']} | Acierto: {metrics['win_rate_pct']:.2f}%")
        print(f"  Liquidaciones: {metrics['liquidations']} | Señales sin margen: {skipped}")

    combined = curves["LONG"].rename(columns={"equity": "long_equity"}).merge(
        curves["SHORT"].rename(columns={"equity": "short_equity"}),
        on="timestamp",
        how="outer",
    ).sort_values("timestamp")
    combined[["long_equity", "short_equity"]] = combined[
        ["long_equity", "short_equity"]
    ].ffill().fillna(5_000.0)
    combined["equity"] = combined["long_equity"] + combined["short_equity"]
    combined_peak = combined["equity"].cummax()
    combined_drawdown = combined["equity"] / combined_peak - 1.0
    final_equity = float(combined["equity"].iloc[-1])
    combined_metrics = {
        "initial_bank": 10_000.0,
        "long_initial_bank": 5_000.0,
        "short_initial_bank": 5_000.0,
        "final_equity": final_equity,
        "total_return_pct": (final_equity / 10_000.0 - 1.0) * 100,
        "max_drawdown_pct": float(combined_drawdown.min()) * 100,
        "long": strategy_metrics["LONG"],
        "short": strategy_metrics["SHORT"],
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUTPUT_ROOT / "combined_equity.csv", index=False)
    with (OUTPUT_ROOT / "combined_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(combined_metrics, handle, indent=2, ensure_ascii=False)

    figure, axis = plt.subplots(figsize=(16, 8))
    timestamps = pd.to_datetime(combined["timestamp"])
    axis.plot(timestamps, combined["equity"], label="Cartera total", linewidth=1.6)
    axis.plot(timestamps, combined["long_equity"], label="Estrategia LONG", alpha=0.8)
    axis.plot(timestamps, combined["short_equity"], label="Estrategia SHORT", alpha=0.8)
    axis.axhline(10_000.0, color="gray", linestyle="--", label="Banca total inicial")
    axis.set_title("BTCUSDT 10m · estrategias LONG y SHORT independientes")
    axis.set_ylabel("Equity (USD)")
    axis.set_xlabel("Fecha")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(OUTPUT_ROOT / "combined_backtest.png", dpi=180, bbox_inches="tight")
    plt.close(figure)

    print("\nCOMBINADO (5.000 LONG + 5.000 SHORT)")
    print(f"  Banca: $10,000.00 → ${final_equity:,.2f}")
    print(f"  Rentabilidad: {combined_metrics['total_return_pct']:.2f}%")
    print(f"  Drawdown: {combined_metrics['max_drawdown_pct']:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
