"""Descarga BTC-USD, crea velas 3m, consulta Kronos y guarda gráfico/CSV."""

from __future__ import annotations

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
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "btc_3m_prediction"


def download_3m_bars() -> pd.DataFrame:
    print("📥 Descargando BTC-USD en 1m y agregando velas de 3 minutos...")
    raw = yf.download("BTC-USD", period="7d", interval="1m", progress=False, timeout=60)
    if raw.empty:
        raise RuntimeError("Yahoo Finance no devolvió datos de BTC-USD.")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.columns = [str(column).lower() for column in raw.columns]
    raw = raw[["open", "high", "low", "close", "volume"]].dropna()
    raw["amount"] = raw["volume"] * raw["close"]
    bars = raw.resample("3min", origin="epoch").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "amount": "sum",
        }
    )
    return bars.dropna().sort_index().tail(400)


def predict(history: pd.DataFrame) -> pd.DataFrame:
    payload_history = history.reset_index()
    payload_history.columns = ["timestamps", *history.columns]
    payload_history["timestamps"] = pd.to_datetime(
        payload_history["timestamps"], utc=True
    ).dt.strftime("%Y-%m-%d %H:%M:%S")
    url = os.environ.get("KRONOS_API_URL", "http://127.0.0.1:7080/predict")
    print("🧠 Prediciendo 120 velas de 3m (6 horas) con Kronos...")
    response = requests.post(
        url,
        json={"history": payload_history.to_dict(orient="records"), "pred_len": 120, "freq": "3min"},
        timeout=300,
    )
    response.raise_for_status()
    prediction = pd.DataFrame(response.json())
    required = ["timestamps", "open", "high", "low", "close"]
    missing = [column for column in required if column not in prediction]
    if missing:
        raise RuntimeError(f"Respuesta incompleta de Kronos: faltan {missing}")
    prediction["timestamps"] = pd.to_datetime(prediction["timestamps"], utc=True)
    return prediction.sort_values("timestamps").reset_index(drop=True)


def draw_candles(axis: plt.Axes, frame: pd.DataFrame, width_minutes: float, alpha: float) -> None:
    width = width_minutes / (24 * 60)
    for row in frame.itertuples(index=False):
        timestamp = mdates.date2num(pd.Timestamp(row.timestamps).to_pydatetime())
        color = "#16a34a" if row.close >= row.open else "#dc2626"
        axis.vlines(timestamp, row.low, row.high, color=color, linewidth=0.65, alpha=alpha)
        bottom = min(row.open, row.close)
        height = max(abs(row.close - row.open), 0.01)
        axis.add_patch(
            Rectangle(
                (timestamp - width / 2, bottom),
                width,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.4,
                alpha=alpha,
            )
        )


def save(history: pd.DataFrame, prediction: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    history_csv = history.reset_index()
    history_csv.columns = ["timestamps", *history.columns]
    history_csv.to_csv(OUTPUT_DIR / "history_3m.csv", index=False)
    prediction.to_csv(OUTPUT_DIR / "prediction_3m.csv", index=False)

    recent = history.tail(160).reset_index()
    recent.columns = ["timestamps", *history.columns]
    figure, axis = plt.subplots(figsize=(18, 9))
    draw_candles(axis, recent, width_minutes=2.2, alpha=0.85)
    draw_candles(axis, prediction, width_minutes=2.2, alpha=0.72)
    split = prediction["timestamps"].iloc[0]
    axis.axvline(split, color="#2563eb", linestyle="--", linewidth=1.5, label="Inicio predicción")
    axis.plot(recent["timestamps"], recent["close"], color="#111827", linewidth=0.7, alpha=0.45)
    axis.plot(
        prediction["timestamps"],
        prediction["close"],
        color="#2563eb",
        linewidth=1.3,
        label="Cierre predicho",
    )
    axis.set_title("BTC-USD · Kronos · velas 3m · predicción de 6 horas")
    axis.set_ylabel("Precio (USD)")
    axis.set_xlabel("Hora UTC")
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M", tz=prediction["timestamps"].dt.tz))
    axis.grid(alpha=0.2)
    axis.legend()
    figure.tight_layout()
    figure.savefig(OUTPUT_DIR / "btc_3m_prediction.png", dpi=180, bbox_inches="tight")
    plt.close(figure)


def main() -> int:
    try:
        history = download_3m_bars()
        prediction = predict(history)
        save(history, prediction)
    except (RuntimeError, requests.RequestException) as exc:
        print(f"❌ {exc}")
        return 1

    current = float(history["close"].iloc[-1])
    final = float(prediction["close"].iloc[-1])
    change = final / current - 1
    maximum = float(prediction["high"].max())
    minimum = float(prediction["low"].min())
    print("\n✅ Predicción 3m terminada")
    print(f"   Precio actual: ${current:,.2f}")
    print(f"   Cierre estimado en 6h: ${final:,.2f} ({change:+.2%})")
    print(f"   Rango estimado: ${minimum:,.2f} → ${maximum:,.2f}")
    print(f"   Gráfico: {(OUTPUT_DIR / 'btc_3m_prediction.png').resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
