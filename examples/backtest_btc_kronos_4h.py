"""Backtest walk-forward de Kronos para BTC-USD en velas de cuatro horas."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Un override gfx11 hace fallar las GPU RDNA 4 (gfx1200), como la RX 9060 XT.
if os.environ.get("HSA_OVERRIDE_GFX_VERSION") == "11.0.0":
    print("⚠️ Ignorando HSA_OVERRIDE_GFX_VERSION=11.0.0; se usará gfx1200 nativo.")
    os.environ.pop("HSA_OVERRIDE_GFX_VERSION")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model import Kronos, KronosPredictor, KronosTokenizer


@dataclass(frozen=True)
class Config:
    ticker: str = "BTC-USD"
    timeframe: str = "4h"
    months: int = 6
    initial_bank: float = 10_000.0
    threshold: float = 0.005
    leverage: float = 10.0
    base_margin_fraction: float = 0.05
    fee_rate: float = 0.001
    slippage_rate: float = 0.0002
    stop_liquidation_fraction: float = 0.90
    take_profit_roi: float = 1.0
    lookback: int = 400
    batch_size: int = 16
    model_name: str = "NeoQuasar/Kronos-base"
    tokenizer_name: str = "NeoQuasar/Kronos-Tokenizer-base"
    seed: int = 42


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest walk-forward BTC-USD 4h con Kronos y sizing Fibonacci."
    )
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--initial-bank", type=float, default=10_000.0)
    parser.add_argument("--threshold", type=float, default=0.005)
    parser.add_argument("--leverage", type=float, default=10.0)
    parser.add_argument("--base-size", type=float, default=0.05)
    parser.add_argument("--fee", type=float, default=0.001)
    parser.add_argument("--slippage", type=float, default=0.0002)
    parser.add_argument("--stop-liquidation-fraction", type=float, default=0.90)
    parser.add_argument("--take-profit-roi", type=float, default=1.0)
    parser.add_argument("--lookback", type=int, default=400)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "btc_4h_backtest")
    return parser.parse_args()


def download_4h_data(ticker: str, months: int, lookback: int) -> tuple[pd.DataFrame, pd.Timestamp]:
    # Se descarga un año de 1h: cubre seis meses de prueba y 400 velas 4h de contexto.
    required_days = months * 31 + int(np.ceil(lookback * 4 / 24)) + 10
    period = "2y" if required_days > 365 else "1y"
    print(f"📥 Descargando {ticker} ({period}, velas 1h) y agregando a 4h...")
    raw = yf.download(ticker, period=period, interval="1h", progress=False, timeout=60)
    if raw.empty:
        raise RuntimeError("Yahoo Finance no devolvió datos.")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.columns = [str(column).lower() for column in raw.columns]
    raw = raw[["open", "high", "low", "close", "volume"]].dropna()
    raw["amount"] = raw["volume"] * raw["close"]

    bars = raw.resample("4h", origin="epoch").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "amount": "sum",
        }
    )
    bars = bars.dropna().sort_index()
    test_start = bars.index.max() - pd.DateOffset(months=months)
    first_test_position = int(bars.index.searchsorted(test_start))
    if first_test_position < lookback:
        raise RuntimeError(
            f"Sólo hay {first_test_position} velas antes del backtest; se necesitan {lookback}."
        )
    return bars, bars.index[first_test_position]


def load_predictor(config: Config) -> KronosPredictor:
    if not torch.cuda.is_available():
        raise RuntimeError("PyTorch ROCm no detecta la GPU AMD.")
    print(
        f"🧠 Cargando {config.model_name} en {torch.cuda.get_device_name(0)} "
        f"({torch.cuda.get_device_properties(0).gcnArchName})..."
    )
    tokenizer = KronosTokenizer.from_pretrained(config.tokenizer_name)
    model = Kronos.from_pretrained(config.model_name)
    return KronosPredictor(model, tokenizer, device="cuda:0", max_context=512)


def walk_forward_predictions(
    bars: pd.DataFrame,
    test_start: pd.Timestamp,
    predictor: KronosPredictor,
    config: Config,
) -> pd.DataFrame:
    first_position = int(bars.index.get_loc(test_start))
    # Cada predicción usa datos hasta i inclusive y pronostica i+1.
    decision_positions = list(range(first_position, len(bars) - 1))
    records: list[dict[str, object]] = []
    features = ["open", "high", "low", "close", "volume", "amount"]

    print(f"🔮 Generando {len(decision_positions):,} predicciones walk-forward... ")
    for chunk_start in range(0, len(decision_positions), config.batch_size):
        chunk = decision_positions[chunk_start : chunk_start + config.batch_size]
        df_list: list[pd.DataFrame] = []
        x_timestamp_list: list[pd.Series] = []
        y_timestamp_list: list[pd.Series] = []

        for position in chunk:
            history = bars.iloc[position - config.lookback + 1 : position + 1]
            df_list.append(history[features].reset_index(drop=True))
            x_timestamp_list.append(pd.Series(history.index).reset_index(drop=True))
            y_timestamp_list.append(pd.Series([bars.index[position + 1]]))

        predicted = predictor.predict_batch(
            df_list=df_list,
            x_timestamp_list=x_timestamp_list,
            y_timestamp_list=y_timestamp_list,
            pred_len=1,
            sample_count=1,
            verbose=False,
        )

        for position, prediction in zip(chunk, predicted, strict=True):
            current = bars.iloc[position]
            following = bars.iloc[position + 1]
            predicted_close = float(prediction["close"].iloc[0])
            records.append(
                {
                    "decision_time": bars.index[position],
                    "exit_time": bars.index[position + 1],
                    "entry": float(current["close"]),
                    "next_open": float(following["open"]),
                    "next_high": float(following["high"]),
                    "next_low": float(following["low"]),
                    "exit": float(following["close"]),
                    "predicted_close": predicted_close,
                    "predicted_return": predicted_close / float(current["close"]) - 1.0,
                }
            )

        completed = min(chunk_start + len(chunk), len(decision_positions))
        print(f"   {completed:,}/{len(decision_positions):,}", end="\r", flush=True)
    print()
    return pd.DataFrame.from_records(records)


def fibonacci_units(loss_streak: int) -> int:
    """1, 1, 2, 3, 5...; loss_streak=0 usa la apuesta mínima."""
    if loss_streak <= 1:
        return 1
    previous, current = 1, 1
    for _ in range(2, loss_streak + 1):
        previous, current = current, previous + current
    return current


def simulate(predictions: pd.DataFrame, config: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    equity = config.initial_bank
    loss_streak = 0
    trades: list[dict[str, object]] = []
    curve: list[dict[str, object]] = [
        {"timestamp": predictions.iloc[0]["decision_time"], "equity": equity}
    ]

    position: dict[str, object] | None = None
    for row in predictions.itertuples(index=False):
        if equity <= 0:
            break

        if position is None:
            if row.predicted_return > config.threshold:
                side, side_name = 1, "LONG"
            elif row.predicted_return < -config.threshold:
                side, side_name = -1, "SHORT"
            else:
                curve.append({"timestamp": row.exit_time, "equity": equity})
                continue

            units = fibonacci_units(loss_streak)
            planned_margin = config.initial_bank * config.base_margin_fraction * units
            margin = min(planned_margin, equity)
            notional = margin * config.leverage
            entry_exec = row.entry * (1 + config.slippage_rate * side)
            stop_distance = config.stop_liquidation_fraction / config.leverage
            target_distance = config.take_profit_roi / config.leverage
            position = {
                "decision_time": row.decision_time,
                "direction": side,
                "side": side_name,
                "entry": row.entry,
                "entry_exec": entry_exec,
                "predicted_close": row.predicted_close,
                "predicted_return": row.predicted_return,
                "fibonacci_units": units,
                "margin": margin,
                "notional": notional,
                "quantity": notional / entry_exec,
                "stop_price": entry_exec * (1 - side * stop_distance),
                "take_profit_price": entry_exec * (1 + side * target_distance),
                "liquidation_price": entry_exec * (1 - side / config.leverage),
                "equity_before": equity,
                "holding_bars": 0,
            }

        position["holding_bars"] = int(position["holding_bars"]) + 1
        side = int(position["direction"])
        stop_price = float(position["stop_price"])
        take_profit_price = float(position["take_profit_price"])
        liquidation_price = float(position["liquidation_price"])

        # Si la vela abre más allá de la liquidación, el stop no pudo protegernos.
        liquidated = (side == 1 and row.next_open <= liquidation_price) or (
            side == -1 and row.next_open >= liquidation_price
        )
        stop_hit = (side == 1 and row.next_low <= stop_price) or (
            side == -1 and row.next_high >= stop_price
        )
        target_hit = (side == 1 and row.next_high >= take_profit_price) or (
            side == -1 and row.next_low <= take_profit_price
        )

        exit_reason: str | None = None
        raw_exit: float | None = None
        if liquidated:
            exit_reason = "LIQUIDATION"
        elif stop_hit:  # Conservador si stop y TP aparecen dentro de la misma vela.
            exit_reason, raw_exit = "STOP_LOSS", stop_price
        elif target_hit:
            exit_reason, raw_exit = "TAKE_PROFIT", take_profit_price
        elif row.exit_time == predictions.iloc[-1]["exit_time"]:
            exit_reason, raw_exit = "END_OF_TEST", row.exit

        if exit_reason is None:
            quantity = float(position["quantity"])
            unrealized = side * quantity * (row.exit - float(position["entry_exec"]))
            curve.append({"timestamp": row.exit_time, "equity": max(0.0, equity + unrealized)})
            continue

        margin = float(position["margin"])
        if liquidated:
            exit_exec = liquidation_price
            gross_pnl, fees, net_pnl = -margin, 0.0, -margin
        else:
            exit_exec = float(raw_exit) * (1 - config.slippage_rate * side)
            quantity = float(position["quantity"])
            gross_pnl = side * quantity * (exit_exec - float(position["entry_exec"]))
            exit_notional = quantity * exit_exec
            fees = config.fee_rate * (float(position["notional"]) + exit_notional)
            net_pnl = max(gross_pnl - fees, -margin)

        equity = max(0.0, equity + net_pnl)
        loss_streak = 0 if net_pnl > 0 else loss_streak + 1
        trades.append(
            {
                **position,
                "exit_time": row.exit_time,
                "exit": raw_exit if raw_exit is not None else liquidation_price,
                "exit_exec": exit_exec,
                "exit_reason": exit_reason,
                "liquidated": liquidated,
                "gross_pnl": gross_pnl,
                "fees": fees,
                "net_pnl": net_pnl,
                "equity_after": equity,
                "loss_streak_after": loss_streak,
            }
        )
        position = None
        curve.append({"timestamp": row.exit_time, "equity": equity})

    return pd.DataFrame(trades), pd.DataFrame(curve).drop_duplicates("timestamp", keep="last")


def calculate_metrics(
    predictions: pd.DataFrame,
    trades: pd.DataFrame,
    equity_curve: pd.DataFrame,
    config: Config,
) -> dict[str, object]:
    equity = equity_curve["equity"]
    peaks = equity.cummax()
    drawdown = equity / peaks - 1.0
    final_equity = float(equity.iloc[-1])
    total_return = final_equity / config.initial_bank - 1.0
    elapsed_days = max(
        1.0,
        (pd.Timestamp(equity_curve["timestamp"].iloc[-1]) - pd.Timestamp(equity_curve["timestamp"].iloc[0])).total_seconds()
        / 86_400,
    )
    annualized_return = (max(final_equity, 1e-9) / config.initial_bank) ** (365 / elapsed_days) - 1

    if trades.empty:
        wins = pd.Series(dtype=bool)
        profit_factor = 0.0
    else:
        wins = trades["net_pnl"] > 0
        gross_profit = float(trades.loc[trades["net_pnl"] > 0, "net_pnl"].sum())
        gross_loss = abs(float(trades.loc[trades["net_pnl"] < 0, "net_pnl"].sum()))
        profit_factor = gross_profit / gross_loss if gross_loss else float("inf")

    benchmark_return = predictions.iloc[-1]["exit"] / predictions.iloc[0]["entry"] - 1.0
    return {
        "initial_bank": config.initial_bank,
        "final_equity": final_equity,
        "total_return_pct": total_return * 100,
        "annualized_return_pct": annualized_return * 100,
        "max_drawdown_pct": float(drawdown.min()) * 100,
        "buy_hold_return_pct": float(benchmark_return) * 100,
        "trades": int(len(trades)),
        "win_rate_pct": float(wins.mean() * 100) if len(wins) else 0.0,
        "profit_factor": profit_factor,
        "longs": int((trades["side"] == "LONG").sum()) if not trades.empty else 0,
        "shorts": int((trades["side"] == "SHORT").sum()) if not trades.empty else 0,
        "liquidations": int(trades["liquidated"].sum()) if not trades.empty else 0,
        "fees_paid": float(trades["fees"].sum()) if not trades.empty else 0.0,
        "test_start": str(predictions.iloc[0]["decision_time"]),
        "test_end": str(predictions.iloc[-1]["exit_time"]),
    }


def save_outputs(
    predictions: pd.DataFrame,
    trades: pd.DataFrame,
    equity_curve: pd.DataFrame,
    metrics: dict[str, object],
    config: Config,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(output_dir / "predictions.csv", index=False)
    trades.to_csv(output_dir / "trades.csv", index=False)
    equity_curve.to_csv(output_dir / "equity_curve.csv", index=False)
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump({"config": asdict(config), "metrics": metrics}, handle, indent=2, ensure_ascii=False)

    timestamps = pd.to_datetime(equity_curve["timestamp"])
    equity = equity_curve["equity"].astype(float)
    drawdown = equity / equity.cummax() - 1.0
    price_time = pd.to_datetime(predictions["exit_time"])
    benchmark = config.initial_bank * predictions["exit"].astype(float) / float(predictions.iloc[0]["entry"])

    figure, axes = plt.subplots(3, 1, figsize=(16, 12), sharex=True)
    axes[0].plot(timestamps, equity, label="Kronos + Fibonacci", color="#2563eb", linewidth=1.5)
    axes[0].plot(price_time, benchmark, label="BTC buy & hold", color="#f59e0b", alpha=0.8)
    axes[0].axhline(config.initial_bank, color="gray", linestyle="--", linewidth=1)
    axes[0].set_ylabel("Equity (USD)")
    axes[0].legend()
    axes[0].grid(alpha=0.25)

    axes[1].fill_between(timestamps, drawdown * 100, 0, color="#dc2626", alpha=0.35)
    axes[1].set_ylabel("Drawdown (%)")
    axes[1].grid(alpha=0.25)

    axes[2].plot(price_time, predictions["exit"], color="#111827", linewidth=1)
    if not trades.empty:
        long_trades = trades[trades["side"] == "LONG"]
        short_trades = trades[trades["side"] == "SHORT"]
        axes[2].scatter(long_trades["decision_time"], long_trades["entry"], marker="^", s=12, color="#16a34a", label="Long")
        axes[2].scatter(short_trades["decision_time"], short_trades["entry"], marker="v", s=12, color="#dc2626", label="Short")
    axes[2].set_ylabel("BTC-USD")
    axes[2].set_xlabel("Fecha")
    axes[2].legend()
    axes[2].grid(alpha=0.25)
    figure.suptitle(
        f"Backtest walk-forward Kronos · {config.ticker} · {config.timeframe} "
        f"· apalancamiento {config.leverage:g}x"
    )
    figure.tight_layout()
    figure.savefig(output_dir / "backtest.png", dpi=180, bbox_inches="tight")
    plt.close(figure)


def main() -> int:
    args = parse_args()
    config = Config(
        months=args.months,
        initial_bank=args.initial_bank,
        threshold=args.threshold,
        leverage=args.leverage,
        base_margin_fraction=args.base_size,
        fee_rate=args.fee,
        slippage_rate=args.slippage,
        stop_liquidation_fraction=args.stop_liquidation_fraction,
        take_profit_roi=args.take_profit_roi,
        lookback=args.lookback,
        batch_size=args.batch_size,
    )
    if config.initial_bank <= 0 or config.lookback <= 0 or config.batch_size <= 0:
        raise ValueError("Banca, lookback y batch-size deben ser positivos.")
    if not 0 < config.base_margin_fraction <= 1:
        raise ValueError("base-size debe estar entre 0 y 1.")
    if not 0 < config.stop_liquidation_fraction < 1:
        raise ValueError("stop-liquidation-fraction debe estar entre 0 y 1.")
    if config.take_profit_roi <= 0:
        raise ValueError("take-profit-roi debe ser positivo.")

    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    bars, test_start = download_4h_data(config.ticker, config.months, config.lookback)
    predictor = load_predictor(config)
    predictions = walk_forward_predictions(bars, test_start, predictor, config)
    trades, equity_curve = simulate(predictions, config)
    metrics = calculate_metrics(predictions, trades, equity_curve, config)
    save_outputs(predictions, trades, equity_curve, metrics, config, args.output_dir)

    print("\n✅ Backtest terminado")
    print(f"   Periodo: {metrics['test_start']} → {metrics['test_end']}")
    print(f"   Banca: ${metrics['initial_bank']:,.2f} → ${metrics['final_equity']:,.2f}")
    print(f"   Rentabilidad: {metrics['total_return_pct']:.2f}%")
    print(f"   Drawdown máximo: {metrics['max_drawdown_pct']:.2f}%")
    print(f"   Operaciones: {metrics['trades']} | Acierto: {metrics['win_rate_pct']:.2f}%")
    print(f"   Liquidaciones: {metrics['liquidations']} | Comisiones: ${metrics['fees_paid']:,.2f}")
    print(f"   Resultados: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
