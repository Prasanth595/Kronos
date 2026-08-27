"""Señal actual de la estrategia Kronos y gráfico BTC-USD de 10 minutos."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd
import requests
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "btc_10m_strategy"
THRESHOLD = 0.005
LEVERAGE = 10.0
MARGIN_FRACTION = 0.05
STOP_LIQUIDATION_FRACTION = 0.90
TAKE_PROFIT_ROI = 1.0


def download_bars() -> pd.DataFrame:
    print("📥 Descargando BTC-USD en 5m y agregando velas de 10 minutos...")
    raw = yf.download("BTC-USD", period="5d", interval="5m", progress=False, timeout=60)
    if raw.empty:
        raise RuntimeError("Yahoo Finance no devolvió datos.")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.columns = [str(column).lower() for column in raw.columns]
    raw = raw[["open", "high", "low", "close", "volume"]].dropna()
    raw["amount"] = raw["volume"] * raw["close"]
    bars = raw.resample("10min", origin="epoch").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "amount": "sum"}
    )
    return bars.dropna().sort_index().tail(400)


def request_prediction(history: pd.DataFrame) -> pd.DataFrame:
    payload = history.reset_index()
    payload.columns = ["timestamps", *history.columns]
    payload["timestamps"] = pd.to_datetime(payload["timestamps"], utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
    url = os.environ.get("KRONOS_API_URL", "http://127.0.0.1:7080/predict")
    print("🧠 Prediciendo 120 velas de 10m (20 horas)...")
    response = requests.post(
        url,
        json={"history": payload.to_dict(orient="records"), "pred_len": 120, "freq": "10min"},
        timeout=300,
    )
    response.raise_for_status()
    prediction = pd.DataFrame(response.json())
    prediction["timestamps"] = pd.to_datetime(prediction["timestamps"], utc=True)
    return prediction.sort_values("timestamps").reset_index(drop=True)


def strategy_signal(history: pd.DataFrame, prediction: pd.DataFrame) -> dict[str, object]:
    entry = float(history["close"].iloc[-1])
    next_close = float(prediction["close"].iloc[0])
    predicted_return = next_close / entry - 1.0
    if predicted_return > THRESHOLD:
        signal, direction = "LONG", 1
    elif predicted_return < -THRESHOLD:
        signal, direction = "SHORT", -1
    else:
        signal, direction = "NO_TRADE", 0

    result: dict[str, object] = {
        "last_real_timestamp": str(history.index[-1]),
        "entry_reference": entry,
        "next_prediction_timestamp": str(prediction["timestamps"].iloc[0]),
        "next_predicted_close": next_close,
        "next_predicted_return_pct": predicted_return * 100,
        "signal": signal,
        "threshold_pct": THRESHOLD * 100,
        "leverage": LEVERAGE,
        "initial_margin_fraction_pct": MARGIN_FRACTION * 100,
    }
    if direction:
        stop_distance = STOP_LIQUIDATION_FRACTION / LEVERAGE
        target_distance = TAKE_PROFIT_ROI / LEVERAGE
        result.update(
            {
                "stop_loss": entry * (1 - direction * stop_distance),
                "take_profit": entry * (1 + direction * target_distance),
                "theoretical_liquidation": entry * (1 - direction / LEVERAGE),
            }
        )
    return result


def candles(axis: plt.Axes, frame: pd.DataFrame, alpha: float) -> None:
    width = 7.5 / (24 * 60)
    for row in frame.itertuples(index=False):
        x = mdates.date2num(pd.Timestamp(row.timestamps).to_pydatetime())
        color = "#16a34a" if row.close >= row.open else "#dc2626"
        axis.vlines(x, row.low, row.high, color=color, linewidth=0.65, alpha=alpha)
        axis.add_patch(
            Rectangle(
                (x - width / 2, min(row.open, row.close)),
                width,
                max(abs(row.close - row.open), 0.01),
                facecolor=color,
                edgecolor=color,
                linewidth=0.4,
                alpha=alpha,
            )
        )


def save(history: pd.DataFrame, prediction: pd.DataFrame, signal: dict[str, object]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    historical = history.reset_index()
    historical.columns = ["timestamps", *history.columns]
    historical.to_csv(OUTPUT_DIR / "history_10m.csv", index=False)
    prediction.to_csv(OUTPUT_DIR / "prediction_10m.csv", index=False)
    with (OUTPUT_DIR / "signal.json").open("w", encoding="utf-8") as handle:
        json.dump(signal, handle, indent=2, ensure_ascii=False)

    recent = historical.tail(100)
    figure, axis = plt.subplots(figsize=(18, 9))
    candles(axis, recent, 0.88)
    candles(axis, prediction, 0.70)
    first_prediction = prediction["timestamps"].iloc[0]
    axis.axvline(first_prediction, color="#2563eb", linestyle="--", linewidth=1.5, label="Inicio predicción")
    axis.plot(prediction["timestamps"], prediction["close"], color="#2563eb", linewidth=1.3, label="Cierre predicho")
    if signal["signal"] != "NO_TRADE":
        axis.axhline(signal["entry_reference"], color="#111827", linestyle=":", label="Entrada")
        axis.axhline(signal["stop_loss"], color="#dc2626", linestyle="--", label="Stop-loss")
        axis.axhline(signal["take_profit"], color="#16a34a", linestyle="--", label="Take-profit")
    axis.set_title(
        f"BTC-USD · Kronos · 10m · Señal: {signal['signal']} "
        f"({signal['next_predicted_return_pct']:+.2f}% próxima vela)"
    )
    axis.set_ylabel("Precio (USD)")
    axis.set_xlabel("Hora UTC")
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M", tz=prediction["timestamps"].dt.tz))
    axis.grid(alpha=0.2)
    axis.legend()
    figure.tight_layout()
    figure.savefig(OUTPUT_DIR / "btc_10m_strategy.png", dpi=180, bbox_inches="tight")
    plt.close(figure)


def main() -> int:
    try:
        history = download_bars()
        prediction = request_prediction(history)
        signal = strategy_signal(history, prediction)
        save(history, prediction, signal)
    except (RuntimeError, requests.RequestException, KeyError, ValueError) as exc:
        print(f"❌ {exc}")
        return 1

    print("\n✅ Estrategia 10m calculada")
    print(f"   Último precio real: ${signal['entry_reference']:,.2f} ({signal['last_real_timestamp']})")
    print(f"   Siguiente cierre predicho: ${signal['next_predicted_close']:,.2f} ({signal['next_predicted_return_pct']:+.2f}%)")
    print(f"   Señal: {signal['signal']}")
    if signal["signal"] != "NO_TRADE":
        print(f"   Stop: ${signal['stop_loss']:,.2f} | TP: ${signal['take_profit']:,.2f}")
    print(f"   Gráfico: {(OUTPUT_DIR / 'btc_10m_strategy.png').resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
